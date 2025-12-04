#!/usr/bin/env python3
import argparse
import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
import google.generativeai as genai
import numpy as np
import pandas as pd
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from rich.table import Table
from tenacity import retry, stop_after_attempt, wait_random_exponential


# --- Configuration and Settings ---
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        yaml_file="config.yaml",
    )

    bybit_api_key: str = Field(..., alias="BYBIT_API_KEY")
    bybit_api_secret: str = Field(..., alias="BYBIT_API_SECRET")
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")

    bybit_base_url: str = "https://api.bybit.com"
    gemini_model_name: str = "gemini-1.5-flash-latest"

    symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    interval: str = "1m"
    category: str = "linear"
    kline_limit: int = 200
    min_confidence: int = 70

    gemini_temperature: float = 0.7
    gemini_top_p: float = 0.95
    gemini_top_k: int = 40

    logging_level: str = "INFO"
    max_retries: int = 5
    backoff_factor: float = 0.5

def get_settings() -> Settings:
    return Settings()

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.logging_level), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)
console = Console()

# --- Data Models ---
@dataclass
class IndicatorData:
    rsi: float | None = None
    macd: float | None = None
    macd_signal: float | None = None
    macd_histogram: float | None = None
    bb_upper: float | None = None
    bb_middle: float | None = None
    bb_lower: float | None = None
    sma_20: float | None = None
    sma_50: float | None = None
    ema_12: float | None = None
    ema_26: float | None = None
    atr: float | None = None
    adx: float | None = None
    cci: float | None = None
    stoch_k: float | None = None
    stoch_d: float | None = None
    williams_r: float | None = None
    fisher: float | None = None
    super_smoother: float | None = None
    volume_change_pct: float | None = None

class SignalAnalysis(BaseModel):
    trend: str = Field(..., description="Overall trend: bullish, bearish, or neutral")
    signal: str = Field(..., description="Trading signal: BUY, SELL, or HOLD")
    confidence: int = Field(..., ge=0, le=100, description="Confidence level from 0 to 100")
    explanation: str = Field(..., description="Brief explanation for the decision")
    key_factors: list[str] = Field(default_factory=list, description="List of key factors influencing the decision")
    entry_price: float | None = Field(None, description="Suggested entry price")
    target_price: float | None = Field(None, description="Suggested take-profit price")
    stop_loss_price: float | None = Field(None, description="Suggested stop-loss price")

class AnalysisResult(BaseModel):
    symbol: str
    interval: str
    category: str
    timestamp: datetime
    current_price: float
    analysis: SignalAnalysis
    indicators: IndicatorData
    additional_info: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None

# --- API Clients ---
class RateLimiter:
    def __init__(self, rate_limit: int, period: int = 60):
        self.rate_limit = rate_limit
        self.period = period
        self.tokens = rate_limit
        self.last_update = time.time()
        self.lock = asyncio.Lock()

    async def acquire(self):
        async with self.lock:
            now = time.time()
            time_passed = now - self.last_update
            self.tokens += time_passed * (self.rate_limit / self.period)
            self.tokens = min(self.tokens, self.rate_limit)
            self.last_update = now

            if self.tokens < 1:
                sleep_time = (1 - self.tokens) * (self.period / self.rate_limit)
                logger.debug(f"Rate limit reached. Sleeping for {sleep_time:.2f} seconds.")
                await asyncio.sleep(sleep_time)
                self.tokens = 0
            else:
                self.tokens -= 1

class BybitClient:
    def __init__(self):
        self.api_key = settings.bybit_api_key
        self.api_secret = settings.bybit_api_secret
        self.base_url = settings.bybit_base_url
        self.session: aiohttp.ClientSession | None = None
        self.rate_limiter = RateLimiter(rate_limit=10, period=1)

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _generate_timestamp(self) -> str:
        return str(int(time.time() * 1000))

    def _generate_signature(self, method: str, endpoint: str, params: dict[str, Any]) -> str:
        timestamp = self._generate_timestamp()
        params_str = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        recv_window = 5000 # Default receive window

        sign_str = f"{timestamp}{self.api_key}{recv_window}{method.upper()}{endpoint}{params_str}"

        signature = hmac.new(
            bytes(self.api_secret, "utf-8"),
            bytes(sign_str, "utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature, timestamp, recv_window

    @retry(stop=stop_after_attempt(settings.max_retries), wait=wait_random_exponential(multiplier=settings.backoff_factor, min=1, max=10))
    async def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None, signed: bool = False) -> dict[str, Any]:
        if not self.session:
            raise RuntimeError("ClientSession not initialized. Use 'async with' statement.")

        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        request_params = params if method.upper() == "GET" else None
        request_body = params if method.upper() == "POST" else None

        if signed:
            signature, timestamp, recv_window = self._generate_signature(method, endpoint, params or {})
            headers["X-BAPI-SIGN"] = signature
            headers["X-BAPI-API-KEY"] = self.api_key
            headers["X-BAPI-TIMESTAMP"] = timestamp
            headers["X-BAPI-RECV-WINDOW"] = str(recv_window)

        try:
            async with self.session.request(method, url, headers=headers, params=request_params, json=request_body) as response:
                if response.status == 429:
                    logger.warning(f"Rate limit hit for {method} {endpoint}. Retrying...")
                    response.raise_for_status() # This will raise an exception that tenacity can catch

                response.raise_for_status()
                data = await response.json()

                if data.get("retCode") != 0:
                    ret_msg = data.get("retMsg", "Unknown error")
                    logger.error(f"Bybit API Error: {ret_msg} (Code: {data.get('retCode')}) for {method} {endpoint}")
                    raise Exception(f"Bybit API error: {ret_msg} (Code: {data.get('retCode')})")

                return data.get("result", {})
        except aiohttp.ClientError as e:
            logger.error(f"HTTP Client Error: {e} for {method} {endpoint}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during API request: {e} for {method} {endpoint}")
            raise

    async def get_kline_data(self, symbol: str, interval: str, limit: int = 200, category: str = "linear") -> pd.DataFrame:
        endpoint = "/v5/market/kline"
        params = {"category": category, "symbol": symbol, "interval": interval, "limit": str(limit)}
        result = await self._request("GET", endpoint, params=params)

        klines = result.get("list", [])
        if not klines:
            logger.warning(f"No kline data received for {symbol} with interval {interval}.")
            return pd.DataFrame()

        df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df = df.astype({
            "timestamp": "int64",
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        })
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df.sort_values("timestamp").reset_index(drop=True)

    async def get_tickers(self, category: str, symbol: str | None = None) -> list[dict[str, Any]]:
        endpoint = "/v5/market/tickers"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", endpoint, params=params)
        return result.get("list", [])

    async def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: float | None = None, category: str = "linear") -> dict[str, Any]:
        endpoint = "/v5/order/create"
        params = {"category": category, "symbol": symbol, "side": side, "orderType": order_type, "qty": str(qty)}
        if price is not None:
            params["price"] = str(price)
        return await self._request("POST", endpoint, params=params, signed=True)

    async def cancel_order(self, symbol: str, order_id: str, category: str = "linear") -> dict[str, Any]:
        endpoint = "/v5/order/cancel"
        params = {"category": category, "symbol": symbol, "orderId": order_id}
        return await self._request("POST", endpoint, params=params, signed=True)

    async def get_open_orders(self, symbol: str | None = None, category: str = "linear") -> list[dict[str, Any]]:
        endpoint = "/v5/order/realtime"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", endpoint, params=params, signed=True)
        return result.get("list", [])

    async def get_position_info(self, symbol: str | None = None, category: str = "linear") -> list[dict[str, Any]]:
        endpoint = "/v5/position/list"
        params = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", endpoint, params=params, signed=True)
        return result.get("list", [])

class GeminiAnalyzer:
    def __init__(self):
        try:
            genai.configure(api_key=settings.gemini_api_key)
            self.model = genai.GenerativeModel(settings.gemini_model_name)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini AI: {e}")
            raise

    def _create_prompt(self, symbol: str, timeframe: str, price: float, indicators: IndicatorData) -> str:
        rsi_val = indicators.rsi
        macd_val = indicators.macd
        macd_signal_val = indicators.macd_signal
        bb_upper_val = indicators.bb_upper
        bb_lower_val = indicators.bb_lower
        sma_20_val = indicators.sma_20
        volume_change_pct_val = indicators.volume_change_pct

        rsi_signal = "OVERSOLD" if rsi_val is not None and rsi_val < 30 else "OVERBOUGHT" if rsi_val is not None and rsi_val > 70 else "NEUTRAL"
        macd_trend = "BULLISH" if macd_val is not None and macd_signal_val is not None and macd_val > macd_signal_val else "BEARISH" if macd_val is not None and macd_signal_val is not None and macd_val < macd_signal_val else "NEUTRAL"
        bb_position = "LOWER BAND" if bb_lower_val is not None and price < bb_lower_val else "UPPER BAND" if bb_upper_val is not None and price > bb_upper_val else "MIDDLE"
        sma_trend = "ABOVE" if sma_20_val is not None and price > sma_20_val else "BELOW" if sma_20_val is not None and price < sma_20_val else "NEAR"
        volume_change_str = f"{volume_change_pct_val:.2f}%" if volume_change_pct_val is not None else "N/A"

        prompt = f"""
        You are an expert quantitative trading analyst. Analyze the comprehensive market data for {symbol} on the {timeframe} timeframe.

        **CURRENT MARKET DATA:**
        - Symbol: {symbol}
        - Timeframe: {timeframe}
        - Current Price: ${price:.2f}

        **SECTION 1: PRICE & MOMENTUM INDICATORS**
        - RSI (14): {rsi_val:.2f} ({rsi_signal})
        - MACD: {macd_val:.4f} (Signal: {macd_signal_val:.4f}) ({macd_trend})
        - Bollinger Bands (20, 2): Price is at the {bb_position} band. Upper: ${bb_upper_val:.2f}, Lower: ${bb_lower_val:.2f}
        - SMA 20: Price is {sma_trend} the 20-period SMA (${sma_20_val:.2f})
        - Volume Change (last period): {volume_change_str}

        **SECTION 2: OTHER INDICATORS (Contextual relevance may vary)**
        - ATR (14): {indicators.atr:.4f}
        - ADX (14): {indicators.adx:.2f}
        - CCI (20): {indicators.cci:.2f}
        - Stochastic (%K): {indicators.stoch_k:.2f} (%D: {indicators.stoch_d:.2f})
        - Williams %R: {indicators.williams_r:.2f}
        - Fisher Transform: {indicators.fisher:.4f}
        - Super Smoother (10): {indicators.super_smoother:.4f}

        **TASK:**
        Synthesize all the above information. Prioritize confluence between different indicators (e.g., a bullish MACD cross near the lower Bollinger Band with oversold RSI). Consider the recent volume change for confirmation. Provide a detailed trading recommendation.

        **OUTPUT FORMAT:**
        Respond with a single JSON object only. Do not include any markdown formatting or preamble text. Ensure all keys are present and adhere to the schema.

        {{
            "trend": "bullish/bearish/neutral",
            "signal": "BUY/SELL/HOLD",
            "confidence": 0-100,
            "explanation": "A concise summary of your analysis, mentioning key confluences and supporting factors. Be specific.",
            "key_factors": ["List of specific indicators or patterns supporting the decision."],
            "entry_price": "null" or a float,
            "target_price": "null" or a float,
            "stop_loss_price": "null" or a float
        }}
        """
        return prompt

    @retry(stop=stop_after_attempt(settings.max_retries), wait=wait_random_exponential(multiplier=settings.backoff_factor, min=1, max=10))
    async def analyze(self, symbol: str, timeframe: str, price: float, indicators: IndicatorData) -> SignalAnalysis:
        prompt = self._create_prompt(symbol, timeframe, price, indicators)

        try:
            response = await self.model.generate_content_async(prompt)
            response_text = response.text.strip()

            logger.debug(f"Raw Gemini response for {symbol}:\n{response_text}")

            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif response_text.startswith("```"):
                response_text = response_text.split("```")[1].split("```")[0].strip()

            if not response_text:
                raise ValueError("Received empty response from Gemini.")

            analysis = SignalAnalysis.model_validate_json(response_text)
            logger.info(f"Gemini analysis for {symbol}: {analysis.signal} (Conf: {analysis.confidence}%) - {analysis.explanation[:50]}...")
            return analysis

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from Gemini for {symbol}. Response: '{response_text}'. Error: {e}")
            return SignalAnalysis(
                trend="neutral", signal="HOLD", confidence=0,
                explanation=f"AI response parsing failed. Response snippet: {response_text[:100]}...",
            )
        except ValueError as e:
             logger.error(f"Validation error from Gemini for {symbol}: {e}. Response: '{response_text}'.")
             return SignalAnalysis(
                trend="neutral", signal="HOLD", confidence=0,
                explanation=f"AI response validation failed. Response snippet: {response_text[:100]}...",
            )
        except Exception as e:
            logger.error(f"Error during Gemini analysis for {symbol}: {e}")
            return SignalAnalysis(
                trend="neutral", signal="HOLD", confidence=0,
                explanation=f"An unexpected error occurred during AI analysis: {e!s}",
            )

# --- Technical Indicators ---
def add_technical_indicators(df: pd.DataFrame) -> IndicatorData:
    if df.empty or len(df) < 50:
        logger.warning("DataFrame is empty or too small for indicator calculation. Returning empty IndicatorData.")
        return IndicatorData()

    try:
        df["sma_20"] = df["close"].rolling(window=20).mean()
        df["sma_50"] = df["close"].rolling(window=50).mean()
        df["ema_12"] = df["close"].ewm(span=12, adjust=False).mean()
        df["ema_26"] = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = df["ema_12"] - df["ema_26"]
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_histogram"] = df["macd"] - df["macd_signal"]

        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))

        df["bb_middle"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_middle"] + (bb_std * 2)
        df["bb_lower"] = df["bb_middle"] - (bb_std * 2)

        df["volume_change_pct"] = df["volume"].pct_change() * 100

        # ATR Calculation
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        df["atr"] = true_range.ewm(com=13, adjust=False).mean() # Using Wilder's smoothing for ATR

        # ADX Calculation
        up_move = df["high"].diff()
        down_move = -df["low"].diff()

        up_move[up_move < 0] = 0
        down_move[down_move < 0] = 0

        avg_up = up_move.ewm(com=13, adjust=False).mean()
        avg_down = down_move.ewm(com=13, adjust=False).mean()

        positive_di = (avg_up / df["atr"]) * 100
        negative_di = (avg_down / df["atr"]) * 100

        tr_14 = df["atr"].rolling(14).mean() # Re-calculating ATR for ADX, often done this way
        dx = ((abs(positive_di - negative_di) / (positive_di + negative_di)) * 100)
        df["adx"] = dx.ewm(com=13, adjust=False).mean()

        # CCI Calculation
        tp = (df["high"] + df["low"] + df["close"]) / 3
        df["cci"] = (tp - tp.rolling(20).mean()) / (0.015 * tp.rolling(20).std())

        # Stochastic Oscillator Calculation
        low_min = df["low"].rolling(window=14).min()
        high_max = df["high"].rolling(window=14).max()
        k_percent = 100 * (df["close"] - low_min) / (high_max - low_min)
        df["stoch_k"] = k_percent.rolling(window=3).mean()
        df["stoch_d"] = df["stoch_k"].rolling(window=3).mean()

        # Williams %R Calculation
        df["williams_r"] = -100 * (high_max - df["close"]) / (high_max - low_min)

        # Fisher Transform Calculation
        def _fisher_transform(series: pd.Series, period: int = 9) -> pd.Series:
            min_val = series.rolling(window=period).min()
            max_val = series.rolling(window=period).max()

            # Avoid division by zero or log of non-positive numbers
            ratio = np.where((max_val - min_val) > 1e-9, (series - min_val) / (max_val - min_val), 0.5)

            # Clamp ratio to avoid log(0) or log of negative numbers
            ratio = np.clip(ratio, 1e-9, 1 - 1e-9)

            fisher = 0.25 * np.log((1 + 2 * ratio) / (1 - 2 * ratio))
            return fisher

        df["fisher"] = _fisher_transform(df["close"], period=9)

        # Super Smoother Calculation
        def _super_smoother(series: pd.Series, period: int = 10) -> pd.Series:
            a2 = np.exp(-1.414 * np.pi / period)
            b2 = 2 * a2 * np.cos(1.414 * np.pi / period)
            c2 = a2 * a2
            coef2 = (1 - b2 + c2) / 4
            coef1 = 1 - coef2
            output = np.zeros_like(series)
            # Initialize first few values to NaN or a reasonable starting point if needed
            for i in range(2, len(series)):
                output[i] = coef1 * (series[i] + 2 * series[i-1] + series[i-2]) + b2 * output[i-1] - c2 * output[i-2]
            return output

        df["super_smoother"] = _super_smoother(df["close"], period=10)

        latest = df.iloc[-1]

        return IndicatorData(
            rsi=latest.get("rsi"),
            macd=latest.get("macd"),
            macd_signal=latest.get("macd_signal"),
            macd_histogram=latest.get("macd_histogram"),
            bb_upper=latest.get("bb_upper"),
            bb_middle=latest.get("bb_middle"),
            bb_lower=latest.get("bb_lower"),
            sma_20=latest.get("sma_20"),
            sma_50=latest.get("sma_50"),
            ema_12=latest.get("ema_12"),
            ema_26=latest.get("ema_26"),
            atr=latest.get("atr"),
            adx=latest.get("adx"),
            cci=latest.get("cci"),
            stoch_k=latest.get("stoch_k"),
            stoch_d=latest.get("stoch_d"),
            williams_r=latest.get("williams_r"),
            fisher=latest.get("fisher"),
            super_smoother=latest.get("super_smoother"),
            volume_change_pct=latest.get("volume_change_pct"),
        )
    except Exception as e:
        logger.error(f"Error calculating technical indicators: {e}")
        return IndicatorData()

# --- Main Analysis Engine ---
class TrendAnalysisEngine:
    def __init__(self):
        self.gemini_analyzer = GeminiAnalyzer()

    async def analyze_symbol(self, client: BybitClient, symbol: str) -> AnalysisResult:
        logger.info(f"Analyzing symbol: {symbol}")
        try:
            df = await client.get_kline_data(symbol, settings.interval, settings.kline_limit, settings.category)
            if df.empty:
                logger.warning(f"No market data retrieved for {symbol}. Skipping analysis.")
                return AnalysisResult(symbol=symbol, interval=settings.interval, category=settings.category, timestamp=datetime.utcnow(), current_price=0, error="No market data available.")

            if len(df) < 50: # Ensure enough data for indicators
                logger.warning(f"Insufficient data points ({len(df)}) for {symbol} to calculate indicators reliably. Need at least 50.")
                return AnalysisResult(symbol=symbol, interval=settings.interval, category=settings.category, timestamp=datetime.utcnow(), current_price=df["close"].iloc[-1] if not df.empty else 0, error=f"Insufficient data points ({len(df)}). Need at least 50.")

            current_price = df["close"].iloc[-1]

            indicators = add_technical_indicators(df.copy()) # Use copy to avoid SettingWithCopyWarning

            analysis = await self.gemini_analyzer.analyze(symbol, settings.interval, current_price, indicators)

            ticker_info = {}
            try:
                tickers = await client.get_tickers(settings.category, symbol)
                if tickers:
                    ticker = tickers[0]
                    ticker_info = {
                        "mark_price": ticker.get("markPrice"),
                        "price_24h_pct": float(ticker.get("price24hPcnt", 0)) * 100,
                        "volume_24h": ticker.get("volume24h"),
                        "turnover_24h": ticker.get("turnover24h"),
                    }
            except Exception as e:
                logger.warning(f"Could not fetch ticker info for {symbol}: {e}")

            return AnalysisResult(
                symbol=symbol,
                interval=settings.interval,
                category=settings.category,
                timestamp=datetime.utcnow(),
                current_price=current_price,
                analysis=analysis,
                indicators=indicators,
                additional_info=ticker_info,
            )
        except Exception as e:
            logger.exception(f"Failed to analyze {symbol}: {e}") # Use logger.exception to include traceback
            return AnalysisResult(symbol=symbol, interval=settings.interval, category=settings.category, timestamp=datetime.utcnow(), current_price=0, error=str(e))

    async def run_analysis(self):
        console.print(Panel.fit("🚀 Starting Enhanced Trend Analysis Engine", style="bold blue"))

        async with BybitClient() as client:
            tasks = [self.analyze_symbol(client, symbol) for symbol in settings.symbols]

            results = []
            # Use track for progress visualization
            for task in track(asyncio.as_completed(tasks), total=len(settings.symbols), description="Analyzing symbols..."):
                result = await task
                results.append(result)

            successful_results = [r for r in results if not r.error and r.analysis.confidence >= settings.min_confidence]
            low_confidence_results = [r for r in results if not r.error and r.analysis.confidence < settings.min_confidence]
            failed_results = [r for r in results if r.error]

            if successful_results:
                self.display_results(sorted(successful_results, key=lambda x: x.analysis.confidence, reverse=True))
            else:
                console.print("\n[bold yellow]No high-confidence signals found based on current criteria.[/bold yellow]")

            if low_confidence_results:
                console.print("\n[bold orange]Low Confidence Signals:[/bold orange]")
                self.display_results(sorted(low_confidence_results, key=lambda x: x.analysis.confidence, reverse=True), confidence_threshold=0)

            if failed_results:
                console.print("\n[bold red]Errors during analysis:[/bold red]")
                for res in failed_results:
                    console.print(f"  - {res.symbol}: [red]{res.error}[/red]")

    def display_results(self, results: list[AnalysisResult], confidence_threshold: int | None = None):
        if not results:
            return

        title = "📊 Market Analysis Results (High Confidence)"
        if confidence_threshold == 0 and results:
             title = "📊 Market Analysis Results (All Signals)"
        elif confidence_threshold is not None:
            title = f"📊 Market Analysis Results (Confidence >= {confidence_threshold}%)"

        table = Table(title=title)
        table.add_column("Symbol", style="cyan", no_wrap=True)
        table.add_column("Price", style="magenta", justify="right")
        table.add_column("24h %", style="green", justify="right")
        table.add_column("Trend", style="bold")
        table.add_column("Signal", style="bold")
        table.add_column("Confidence", justify="right")
        table.add_column("Explanation", style="dim")

        for result in results:
            price_24h_pct = result.additional_info.get("price_24h_pct", 0)
            trend = result.analysis.trend
            signal = result.analysis.signal
            confidence = result.analysis.confidence
            explanation = result.analysis.explanation

            trend_style = "green" if trend == "bullish" else "red" if trend == "bearish" else "yellow"
            signal_style = "green" if signal == "BUY" else "red" if signal == "SELL" else "dim"
            confidence_str = f"{confidence}%"

            # Truncate explanation for table display
            display_explanation = explanation[:70] + "..." if len(explanation) > 70 else explanation

            table.add_row(
                result.symbol,
                f"${result.current_price:,.2f}",
                f"{price_24h_pct:+.2f}%",
                f"[{trend_style}]{trend.upper()}[/{trend_style}]",
                f"[{signal_style}]{signal}[/{signal_style}]",
                f"[{signal_style}]{confidence_str}[/{signal_style}]",
                display_explanation,
            )
        console.print(table)

# --- Main CLI ---
async def main():
    parser = argparse.ArgumentParser(description="AI-powered crypto trend analysis.")
    parser.add_argument("--symbols", nargs="+", default=settings.symbols, help="List of trading symbols to analyze (e.g., BTCUSDT ETHUSDT).")
    parser.add_argument("--interval", type=str, default=settings.interval, help="Candlestick interval (e.g., 1m, 5m, 1h).")
    parser.add_argument("--kline_limit", type=int, default=settings.kline_limit, help="Number of historical candles to fetch.")
    parser.add_argument("--min_confidence", type=int, default=settings.min_confidence, help="Minimum confidence level to display as a primary signal.")

    args = parser.parse_args()

    # Update settings based on command-line arguments
    settings.symbols = args.symbols
    settings.interval = args.interval
    settings.kline_limit = args.kline_limit
    settings.min_confidence = args.min_confidence

    if settings.logging_level == "DEBUG":
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled.")

    try:
        engine = TrendAnalysisEngine()
        await engine.run_analysis()
        console.print("\n[bold green]Analysis complete.[/bold green]")
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Analysis interrupted by user.[/bold yellow]")
    except Exception as e:
        logger.exception("A critical error occurred in the main execution loop.")
        console.print(f"\n[bold red]A critical error occurred: {e}[/bold red]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error during script execution: {e}")
