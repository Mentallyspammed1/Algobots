"""
Fully-refactored Bybit “WhaleBot” – leaner, faster, clearer
──────────────────────────────────────────────────────────
• ConfigManager……… handles JSON config + validation / backup
• BybitAPI……………..   resilient, signed API wrapper
• TradingAnalyzer…… vectorised indicator engine + signal generator
• main()………………..   orchestrates fetch → analyse → signal loop
"""

# ───────────────────────────── Imports ──────────────────────────────
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime
from decimal import Decimal, getcontext
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
from colorama import Fore, Style, init
from dotenv import load_dotenv
from logger_config import setup_custom_logger

# ───────────────────── Environment / Globals ────────────────────────
getcontext().prec = 10
init(autoreset=True)
load_dotenv()

API_KEY     = os.getenv("BYBIT_API_KEY")
API_SECRET  = os.getenv("BYBIT_API_SECRET")
BASE_URL    = os.getenv("BYBIT_BASE_URL", "https://api.bybit.com")

LOG_DIR     = "bot_logs"
CONFIG_FILE = "config.json"
TIMEZONE    = ZoneInfo("America/Chicago")

os.makedirs(LOG_DIR, exist_ok=True)
logger = setup_custom_logger("whalebot_main")

# Colours
C = {
    "G": Fore.LIGHTGREEN_EX,
    "B": Fore.CYAN,
    "P": Fore.MAGENTA,
    "Y": Fore.YELLOW,
    "R": Fore.LIGHTRED_EX,
    "X": Style.RESET_ALL,
}

# Retry tuning
MAX_RETRY            = 3
RETRY_BACKOFF_SEC    = 5
RETRY_CODES          = {429, 500, 502, 503, 504}
VALID_INTERVALS      = ["1","3","5","15","30","60","120","240","D","W","M"]

# ────────────────────────── Config Manager ──────────────────────────
class ConfigManager:
    """Load / validate / auto-heal JSON configuration."""

    DEFAULT: dict[str, Any] = {
        "interval": "15",
        "analysis_interval": 30,
        "retry_delay": 5,
        "momentum_period": 10,
        "momentum_ma_short": 12,
        "momentum_ma_long": 26,
        "volume_ma_period": 20,
        "atr_period": 14,
        "signal_score_threshold": 1.0,
        "stoch_rsi_oversold_threshold": 20,
        "stoch_rsi_overbought_threshold": 80,
        "stop_loss_multiple": 1.5,
        "take_profit_multiple": 1.0,
        "order_book_debounce_s": 10,
        "signal_cooldown_s": 60,
        "atr_change_threshold": 0.005,
        "indicator_periods": {
            "rsi": 14,
            "mfi": 14,
            "cci": 20,
            "wr": 14,
            "adx": 14,
        },
        "indicators": {
            "ema_alignment": True,
            "stoch_rsi": True,
            "rsi": True,
            "mfi": True,
            "volume_confirmation": True,
        },
        "weight_sets": {
            "low_volatility": {
                "ema_alignment": .3, "stoch_rsi": .5,
                "rsi": .3, "mfi": .3, "volume_confirmation": .2
            },
            "high_volatility": {
                "ema_alignment": .1, "stoch_rsi": .4,
                "rsi": .4, "mfi": .4, "volume_confirmation": .1
            }
        },
    }

    def __init__(self, path: str):
        self.path = path
        self.cfg  = self.load()

    # ── helpers
    def load(self) -> dict[str, Any]:
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            merged = {**self.DEFAULT, **data}
            self.validate(merged)
            return merged
        except FileNotFoundError:
            logger.warning(f"{C['Y']}Config not found → created default{C['X']}")
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"{C['R']}Corrupt config: {e}{C['X']}")
            backup = f"{self.path}.bak_{int(time.time())}"
            try:
                os.rename(self.path, backup)
                logger.warning(f"{C['Y']}Backed up bad config → {backup}{C['X']}")
            except Exception:
                pass
        self.save(self.DEFAULT)
        return self.DEFAULT

    def save(self, cfg: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)

    @staticmethod
    def validate(cfg: dict[str, Any]) -> None:
        if cfg["interval"] not in VALID_INTERVALS:
            raise ValueError("interval invalid")
        if cfg["analysis_interval"] <= 0:
            raise ValueError("analysis_interval invalid")

# ─────────────────────────── Bybit API ──────────────────────────────
class BybitAPI:
    def __init__(self, key: str, secret: str, base: str, log: logging.Logger):
        self.key, self.secret, self.base, self.log = key, secret, base, log

    def _sign(self, params: dict[str, Any]) -> str:
        q = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        return hmac.new(self.secret.encode(), q.encode(), hashlib.sha256).hexdigest()

    def req(self, method: str, ep: str, params: dict[str, Any] | None = None) -> dict | None:
        params = params or {}
        params["timestamp"] = str(int(time.time()*1000))
        headers = {
            "X-BAPI-API-KEY": self.key,
            "X-BAPI-SIGN": self._sign(params),
            "X-BAPI-TIMESTAMP": params["timestamp"],
            "Content-Type": "application/json",
        }
        url = f"{self.base}{ep}"

        for attempt in range(1, MAX_RETRY+1):
            try:
                r = requests.request(method, url, headers=headers,
                                     params=params if method=="GET" else None,
                                     json=params  if method=="POST" else None,
                                     timeout=10)
                r.raise_for_status()
                return r.json()
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in RETRY_CODES:
                    self.log.warning(f"{C['Y']}HTTP {e.response.status_code} retry {attempt}{C['X']}")
                    time.sleep(RETRY_BACKOFF_SEC * 2**(attempt-1))
                else:
                    self._log_api_error(e.response)
                    return None
            except requests.exceptions.RequestException as e:
                self.log.error(f"{C['R']}ReqErr {e}{C['X']}")
                time.sleep(RETRY_BACKOFF_SEC * 2**(attempt-1))
        self.log.error(f"{C['R']}Max retries {method} {ep}{C['X']}")
        return None

    def _log_api_error(self, resp: requests.Response):
        try:
            self.log.error(f"{C['R']}API err {resp.status_code}: {resp.json()}{C['X']}")
        except Exception:
            self.log.error(f"{C['R']}API err {resp.status_code}: {resp.text}{C['X']}")

    # Convenience wrappers
    def price(self, symbol: str) -> Decimal | None:
        d = self.req("GET", "/v5/market/tickers", {"category":"linear","symbol":symbol})
        try:
            return Decimal(next(i["lastPrice"] for i in d["result"]["list"] if i["symbol"]==symbol))
        except Exception:
            return None

    def klines(self, symbol: str, interval: str, limit=200) -> pd.DataFrame:
        d = self.req("GET","/v5/market/kline",
                     {"symbol":symbol,"interval":interval,"limit":limit,"category":"linear"})
        if not d or d["retCode"]!=0:
            return pd.DataFrame()
        cols = ["time","open","high","low","close","vol","turn"]
        df = pd.DataFrame(d["result"]["list"], columns=cols)
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        for c in cols[1:]: df[c] = pd.to_numeric(df[c], errors="coerce")
        return df.dropna().sort_values("time").reset_index(drop=True)

    def orderbook(self, symbol: str, depth: int = 50):
        return self.req("GET","/v5/market/orderbook",
                        {"symbol":symbol,"limit":depth,"category":"linear"})

# ─────────────────────── Indicator Utilities ───────────────────────
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def atr(df: pd.DataFrame, window: int) -> pd.Series:
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - df["close"].shift()).abs(),
        (df["low"]  - df["close"].shift()).abs()
    ], axis=1).max(axis=1)
    return ema(tr, window)

# ───────────────────────── Trading Analyzer ─────────────────────────
class TradingAnalyzer:
    def __init__(self, df: pd.DataFrame, cfg: dict[str,Any], log: logging.Logger):
        self.df, self.cfg, self.log = df, cfg, log
        self.ind: dict[str, Any] = {}
        self._prep()

    def _prep(self):
        self.ind["atr"] = atr(self.df, self.cfg["atr_period"])
        self.df["vol_ma"] = self.df["vol"].rolling(self.cfg["volume_ma_period"]).mean()
        # EMA align
        self.df["ema_s"] = ema(self.df["close"], self.cfg["momentum_ma_short"])
        self.df["ema_l"] = ema(self.df["close"], self.cfg["momentum_ma_long"])

    # ── indicator calculations
    def ema_alignment_score(self) -> float:
        s,l = self.df["ema_s"].iloc[-1], self.df["ema_l"].iloc[-1]
        if pd.isna(s) or pd.isna(l): return 0.0
        return 1.0 if s>l else -1.0 if s<l else 0.0

    def volume_confirm(self) -> bool:
        return self.df["vol"].iloc[-1] > self.df["vol_ma"].iloc[-1]*1.5

    def stoch_rsi(self, k_win=3, d_win=3, rsi_win=14, stoch_win=14) -> tuple[float,float]:
        rsi = self._rsi(rsi_win)
        if rsi.isna().all(): return 0.0,0.0
        min_rsi = rsi.rolling(stoch_win).min()
        max_rsi = rsi.rolling(stoch_win).max()
        stoch = 100*(rsi - min_rsi)/(max_rsi - min_rsi).replace(0,np.nan)
        k = stoch.rolling(k_win).mean()
        d = k.rolling(d_win).mean()
        return float(k.iloc[-1]), float(d.iloc[-1])

    def _rsi(self, window:int) -> pd.Series:
        diff = self.df["close"].diff()
        up, down = diff.clip(lower=0), -diff.clip(upper=0)
        ma_up, ma_down = ema(up, window), ema(down, window)
        rs = ma_up/ma_down.replace(0,np.nan)
        return 100 - 100/(1+rs)

    # ── signal
    def signal(self) -> tuple[str | None, float, list[str], dict[str,Decimal]]:
        score = 0.0
        reasons=[]
        weights = self._weights()

        # EMA alignment
        ea = self.ema_alignment_score()
        if self.cfg["indicators"]["ema_alignment"] and ea!=0:
            score += weights["ema_alignment"]*abs(ea)
            reasons.append("EMA Align "+("Bull" if ea>0 else "Bear"))

        # Volume
        if self.cfg["indicators"]["volume_confirmation"] and self.volume_confirm():
            score += weights["volume_confirmation"]
            reasons.append("Volume spike")

        # Stoch RSI
        if self.cfg["indicators"]["stoch_rsi"]:
            k,d = self.stoch_rsi()
            oversold = k<self.cfg["stoch_rsi_oversold_threshold"] and k>d
            overbought = k>self.cfg["stoch_rsi_overbought_threshold"] and k<d
            if oversold:
                score += weights["stoch_rsi"]; reasons.append("StochRSI oversold")
            if overbought:
                score -= weights["stoch_rsi"]; reasons.append("StochRSI overbought")

        # RSI / MFI basic
        if self.cfg["indicators"]["rsi"]:
            r = self._rsi(self.cfg["indicator_periods"]["rsi"]).iloc[-1]
            if r<30: score += weights["rsi"]; reasons.append("RSI oversold")
            elif r>70: score -= weights["rsi"]; reasons.append("RSI overbought")
        if self.cfg["indicators"]["mfi"] and "mfi" in self.ind:
            m = self.ind["mfi"].iloc[-1]
            if m<20: score += weights["mfi"]; reasons.append("MFI oversold")
            elif m>80: score -= weights["mfi"]; reasons.append("MFI overbought")

        # decision
        if abs(score) < self.cfg["signal_score_threshold"]:
            return None, 0.0, [], {}

        side = "buy" if score>0 else "sell"
        price = Decimal(str(self.df["close"].iloc[-1]))
        last_atr = Decimal(str(self.ind["atr"].iloc[-1] or 0))
        tp = price + last_atr*self.cfg["take_profit_multiple"] * (1 if side=="buy" else -1)
        sl = price - last_atr*self.cfg["stop_loss_multiple"] * (1 if side=="buy" else -1)
        levels={"take_profit":tp.quantize(Decimal('0.0001')),
                "stop_loss":sl.quantize(Decimal('0.0001'))}
        return side, score, reasons, levels

    def _weights(self) -> dict[str,float]:
        vol=self.ind["atr"].iloc[-1]
        set_name = "high_volatility" if vol>self.cfg["atr_change_threshold"] else "low_volatility"
        return self.cfg["weight_sets"][set_name]

# ───────────────────────────── main loop ────────────────────────────
def main():
    if not API_KEY or not API_SECRET:
        logger.error(f"{C['R']}API creds missing .env{C['X']}")
        return
    cfg = ConfigManager(CONFIG_FILE).cfg
    api = BybitAPI(API_KEY, API_SECRET, BASE_URL, logger)

    symbol   = (input("Symbol (BTCUSDT): ") or "BTCUSDT").upper()
    interval = input(f"Interval ({cfg['interval']}): ") or cfg["interval"]
    if interval not in VALID_INTERVALS:
        logger.error(f"{C['R']}Bad interval{C['X']}"); return
    slog = setup_custom_logger(symbol)

    last_sig_t = 0.0
    last_ob_t  = 0.0
    order_book = None

    while True:
        try:
            price = api.price(symbol)
            if price is None:
                slog.error("Price fetch fail"); time.sleep(cfg["retry_delay"]); continue
            df = api.klines(symbol, interval, 200)
            if df.empty:
                slog.error("Kline fetch fail"); time.sleep(cfg["retry_delay"]); continue

            # orderbook debounce
            if time.time()-last_ob_t >= cfg["order_book_debounce_s"]:
                order_book = api.orderbook(symbol, 50)
                last_ob_t = time.time()

            ta = TradingAnalyzer(df, cfg, slog)
            side, score, reasons, levels = ta.signal()

            now = datetime.now(TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
            slog.info(f"{C['B']}{now}{C['X']} Price {price}")

            if side and time.time()-last_sig_t>=cfg["signal_cooldown_s"]:
                slog.info(f"{C['P']}SIGNAL {side.upper()} ({score:.2f}){C['X']} → {', '.join(reasons)}")
                slog.info(f"TP {levels['take_profit']}  SL {levels['stop_loss']}")
                last_sig_t=time.time()

            time.sleep(cfg["analysis_interval"])

        except KeyboardInterrupt:
            slog.info("Stopped by user"); break
        except Exception as e:
            slog.exception(e); time.sleep(cfg["retry_delay"])

if __name__ == "__main__":
    main()
