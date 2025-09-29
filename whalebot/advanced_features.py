# advanced_features.py

import logging
from typing import Any

import numpy as np
import pandas as pd

# For sentiment analysis placeholder
try:
    from textblob import TextBlob

    TEXTBLOB_AVAILABLE = True
except ImportError:
    TEXTBLOB_AVAILABLE = False
    print("TextBlob not installed. Sentiment analysis will be a placeholder.")


class PatternRecognitionEngine:
    """1. Advanced pattern recognition using pure Python/Numpy/Pandas.
    Avoids scikit/scipy dependencies.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.min_pattern_length = (
            20  # Minimum data points required for pattern detection
        )

    def _get_peaks_troughs(
        self, series: pd.Series, order: int = 5
    ) -> tuple[list[int], list[int]]:
        """Identifies local peaks and troughs in a series using `order` for local window.
        Returns indices of peaks and troughs.
        """
        peaks = []
        troughs = []

        if len(series) < order * 2 + 1:
            return peaks, troughs  # Not enough data

        for i in range(order, len(series) - order):
            is_peak = True
            is_trough = True
            for j in range(1, order + 1):
                if (
                    series.iloc[i] <= series.iloc[i - j]
                    or series.iloc[i] <= series.iloc[i + j]
                ):
                    is_peak = False
                if (
                    series.iloc[i] >= series.iloc[i - j]
                    or series.iloc[i] >= series.iloc[i + j]
                ):
                    is_trough = False
            if is_peak:
                peaks.append(i)
            if is_trough:
                troughs.append(i)
        return peaks, troughs

    def detect_patterns(self, df: pd.DataFrame) -> list[str]:
        """Detect multiple chart patterns based on OHLCV data."""
        patterns = []
        if df.empty or len(df) < self.min_pattern_length:
            self.logger.debug("Insufficient data for pattern detection.")
            return patterns

        df_copy = df.copy()  # Avoid modifying original DataFrame

        # Head and Shoulders / Inverse Head and Shoulders
        if self._detect_head_shoulders(df_copy):
            patterns.append("HEAD_AND_SHOULDERS")
        if self._detect_inverse_head_shoulders(df_copy):
            patterns.append("INVERSE_HEAD_AND_SHOULDERS")

        # Double Top/Bottom
        if self._detect_double_top(df_copy):
            patterns.append("DOUBLE_TOP")
        if self._detect_double_bottom(df_copy):
            patterns.append("DOUBLE_BOTTOM")

        # Triangles (simplified detection)
        if self._detect_triangle(df_copy) == "ASCENDING_TRIANGLE":
            patterns.append("ASCENDING_TRIANGLE")
        if self._detect_triangle(df_copy) == "DESCENDING_TRIANGLE":
            patterns.append("DESCENDING_TRIANGLE")

        # Channels (simplified)
        if self._detect_channel(df_copy) == "CHANNEL_UP":
            patterns.append("CHANNEL_UP")
        if self._detect_channel(df_copy) == "CHANNEL_DOWN":
            patterns.append("CHANNEL_DOWN")

        self.logger.debug(f"Detected patterns: {patterns}")
        return patterns

    def _detect_head_shoulders(self, df: pd.DataFrame) -> bool:
        """Simplified detection of Head and Shoulders."""
        # Requires at least 3 distinct peaks
        peaks, _ = self._get_peaks_troughs(df["high"], order=5)
        if len(peaks) < 3:
            return False

        # Check for 3 peaks where middle is highest and outer two are similar height
        # This is a highly simplified heuristic and not a robust pattern scanner.
        for i in range(1, len(peaks) - 1):
            left_shoulder_idx = peaks[i - 1]
            head_idx = peaks[i]
            right_shoulder_idx = peaks[i + 1]

            if (
                df["high"].iloc[head_idx] > df["high"].iloc[left_shoulder_idx]
                and df["high"].iloc[head_idx] > df["high"].iloc[right_shoulder_idx]
                and abs(
                    df["high"].iloc[left_shoulder_idx]
                    - df["high"].iloc[right_shoulder_idx]
                )
                / df["high"].iloc[left_shoulder_idx]
                < 0.05
            ):  # Shoulders within 5% of each other
                return True
        return False

    def _detect_inverse_head_shoulders(self, df: pd.DataFrame) -> bool:
        """Simplified detection of Inverse Head and Shoulders."""
        # Requires at least 3 distinct troughs
        _, troughs = self._get_peaks_troughs(df["low"], order=5)
        if len(troughs) < 3:
            return False

        for i in range(1, len(troughs) - 1):
            left_shoulder_idx = troughs[i - 1]
            head_idx = troughs[i]
            right_shoulder_idx = troughs[i + 1]

            if (
                df["low"].iloc[head_idx] < df["low"].iloc[left_shoulder_idx]
                and df["low"].iloc[head_idx] < df["low"].iloc[right_shoulder_idx]
                and abs(
                    df["low"].iloc[left_shoulder_idx]
                    - df["low"].iloc[right_shoulder_idx]
                )
                / df["low"].iloc[left_shoulder_idx]
                < 0.05
            ):
                return True
        return False

    def _detect_double_top(self, df: pd.DataFrame) -> bool:
        """Simplified detection of Double Top."""
        peaks, _ = self._get_peaks_troughs(
            df["high"].tail(30), order=3
        )  # Look at recent 30 bars
        if len(peaks) < 2:
            return False

        # Check for two highest peaks being close in height and separated
        recent_peaks_heights = [
            df["high"].iloc[p] for p in peaks[-2:]
        ]  # Last two peaks
        if (
            len(recent_peaks_heights) == 2
            and abs(recent_peaks_heights[0] - recent_peaks_heights[1])
            / recent_peaks_heights[0]
            < 0.02
        ):  # Within 2%
            if peaks[-1] - peaks[-2] > 5:  # Separated by at least 5 bars
                return True
        return False

    def _detect_double_bottom(self, df: pd.DataFrame) -> bool:
        """Simplified detection of Double Bottom."""
        _, troughs = self._get_peaks_troughs(df["low"].tail(30), order=3)
        if len(troughs) < 2:
            return False

        recent_troughs_heights = [df["low"].iloc[t] for t in troughs[-2:]]
        if (
            len(recent_troughs_heights) == 2
            and abs(recent_troughs_heights[0] - recent_troughs_heights[1])
            / recent_troughs_heights[0]
            < 0.02
        ):
            if troughs[-1] - troughs[-2] > 5:
                return True
        return False

    def _detect_triangle(self, df: pd.DataFrame) -> str | None:
        """Simplified detection of triangle patterns (ascending/descending)."""
        # Look at the last N bars for trendlines
        df_recent = df.tail(self.min_pattern_length)
        if len(df_recent) < self.min_pattern_length:
            return None

        # Fit a line to highs and lows
        x = np.arange(len(df_recent))
        high_slope, _ = np.polyfit(x, df_recent["high"], 1)
        low_slope, _ = np.polyfit(x, df_recent["low"], 1)

        # Ascending: Resistance (highs) is flat/down, Support (lows) is rising
        if high_slope <= 0.001 and low_slope > 0.001:
            return "ASCENDING_TRIANGLE"
        # Descending: Resistance (highs) is falling, Support (lows) is flat/up
        if high_slope < -0.001 and low_slope >= -0.001:
            return "DESCENDING_TRIANGLE"

        return None

    def _detect_channel(self, df: pd.DataFrame) -> str | None:
        """Simplified detection of channel patterns."""
        df_recent = df.tail(self.min_pattern_length)
        if len(df_recent) < self.min_pattern_length:
            return None

        x = np.arange(len(df_recent))
        high_slope, high_intercept = np.polyfit(x, df_recent["high"], 1)
        low_slope, low_intercept = np.polyfit(x, df_recent["low"], 1)

        # Check if lines are roughly parallel (slopes are similar)
        if (
            abs(high_slope - low_slope) < 0.002 * df_recent["close"].mean()
        ):  # Tolerance based on price
            if high_slope > 0.001:
                return "CHANNEL_UP"
            if high_slope < -0.001:
                return "CHANNEL_DOWN"

        return None


class SimpleSentimentAnalysis:
    """2. Sentiment analysis placeholder.
    Uses TextBlob if available, otherwise provides dummy sentiment.
    (Note: TextBlob requires `nltk` data. User specified no scikit/scipy).
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        if not TEXTBLOB_AVAILABLE:
            self.logger.warning(
                "TextBlob not found. Sentiment analysis will return dummy data. Install 'textblob' and run 'python -m textblob.download_corpora' for full functionality."
            )

    def analyze_sentiment(
        self,
        news_headlines: list[str] | None = None,
        social_media_keywords: dict[str, int] | None = None,
    ) -> float:
        """Analyzes sentiment from text data. Returns a score between -1 (bearish) and 1 (bullish)."""
        if not TEXTBLOB_AVAILABLE:
            return np.random.uniform(-0.2, 0.2)  # Dummy sentiment

        combined_text = ""
        if news_headlines:
            combined_text += " ".join(news_headlines)
        if social_media_keywords:
            combined_text += " ".join(social_media_keywords.keys())  # Just use keywords

        if combined_text:
            analysis = TextBlob(combined_text)
            return analysis.sentiment.polarity
        return 0.0  # Neutral sentiment


class SimpleAnomalyDetector:
    """3. Simple Anomaly Detection using rolling Z-score.
    Avoids scikit-learn.
    """

    def __init__(
        self,
        logger: logging.Logger,
        rolling_window: int = 50,
        threshold_std: float = 3.0,
    ):
        self.logger = logger
        self.rolling_window = rolling_window
        self.threshold_std = threshold_std

    def detect_anomalies(self, series: pd.Series) -> pd.Series:
        """Detects anomalies in a given series (e.g., volume, price change)
        using rolling mean and standard deviation.
        Returns a boolean Series where True indicates an anomaly.
        """
        if len(series) < self.rolling_window:
            self.logger.debug("Insufficient data for anomaly detection rolling window.")
            return pd.Series(False, index=series.index)

        rolling_mean = series.rolling(window=self.rolling_window).mean()
        rolling_std = series.rolling(window=self.rolling_window).std()

        # Calculate Z-score relative to rolling window
        # Avoid division by zero if std is 0
        z_score = abs(
            (series - rolling_mean) / rolling_std.replace(0, np.nan).fillna(1)
        )  # Replace 0 std with 1 to avoid NaN from /0

        anomalies = z_score > self.threshold_std
        anomalies = anomalies.fillna(
            False
        )  # Fill NaN from rolling window start with False

        self.logger.debug(f"Anomalies detected: {anomalies.sum()}")
        return anomalies


class DynamicRiskManager:
    """4. Dynamic risk management system.
    Adjusts risk based on market conditions and signal quality.
    """

    def __init__(self, logger: logging.Logger, config: Any):
        self.logger = logger
        self.config = config

    def assess_risk_level(
        self, market_conditions: dict[str, Any], signal_score: float
    ) -> str:
        """Assesses a general risk level for the current trading opportunity.
        Returns 'LOW', 'MEDIUM', 'HIGH', 'VERY HIGH'.
        """
        risk_score = 0
        market_phase = market_conditions.get("market_phase", "UNKNOWN")
        volatility = market_conditions.get("volatility", "NORMAL")
        trend_strength = market_conditions.get("trend_strength", "NEUTRAL")

        # Penalize for unfavorable market conditions
        if market_phase == "RANGING":
            risk_score += 1  # Ranging can be trickier
        if volatility == "HIGH":
            risk_score += 2  # Higher risk in high volatility
        if trend_strength == "WEAK":
            risk_score += 1  # Weak trends are less reliable

        # Adjust based on signal strength
        # Lower absolute score means weaker signal, higher risk
        if (
            abs(signal_score) < self.config.STRATEGY_BUY_SCORE_THRESHOLD
        ):  # Using BUY threshold as a generic weak signal threshold
            risk_score += 1

        if risk_score >= 4:
            return "VERY HIGH"
        if risk_score >= 2:
            return "HIGH"
        if risk_score >= 1:
            return "MEDIUM"
        return "LOW"

    def adjust_position_sizing_factor(
        self, current_risk_level: str, signal_confidence: float
    ) -> float:
        """Returns a factor (0-1) to adjust the base position size.
        `signal_confidence` is assumed to be 0-100.
        """
        risk_multiplier = {
            "LOW": 1.0,
            "MEDIUM": 0.75,
            "HIGH": 0.5,
            "VERY HIGH": 0.25,
        }.get(current_risk_level, 0.5)

        confidence_factor = max(
            0.2, min(1.0, signal_confidence / 100)
        )  # Min 20% factor from confidence (0-1 range)

        return risk_multiplier * confidence_factor


class SimplePriceTargetPredictor:
    """5. Simple Price Target Prediction using ATR and Fib-like extensions.
    Avoids complex ML models.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def predict_targets(
        self, df: pd.DataFrame, entry_price: float, position_side: str
    ) -> list[tuple[float, float]]:
        """Predicts potential price targets and stop loss for a trade.
        Returns a list of (price, probability) tuples.
        """
        if df.empty or "ATR" not in df.columns or len(df) < 1:
            self.logger.warning(
                "Insufficient data for price target prediction (missing ATR)."
            )
            return []

        latest_atr = df["ATR"].iloc[-1]
        current_price = df["close"].iloc[-1]

        targets = []

        # Based on ATR multiples
        if position_side == "Buy":
            # Target 1: 1.5 ATR (conservative TP)
            tp1 = entry_price + (1.5 * latest_atr)
            targets.append((tp1, 0.6))
            # Target 2: 3.0 ATR (aggressive TP)
            tp2 = entry_price + (3.0 * latest_atr)
            targets.append((tp2, 0.3))
        else:  # Sell
            # Target 1: 1.5 ATR (conservative TP)
            tp1 = entry_price - (1.5 * latest_atr)
            targets.append((tp1, 0.6))
            # Target 2: 3.0 ATR (aggressive TP)
            tp2 = entry_price - (3.0 * latest_atr)
            targets.append((tp2, 0.3))

        # Add some Fibonacci retracement/extension like levels (relative to recent price action)
        # This requires more context (e.g., recent swing high/low), simplifying for now
        recent_high = df["high"].iloc[-min(len(df), 20) :].max()
        recent_low = df["low"].iloc[-min(len(df), 20) :].min()
        price_range = recent_high - recent_low

        if price_range > 0 and latest_atr > 0:  # Ensure valid range and ATR
            if position_side == "Buy":
                # Extension levels based on recent swing
                targets.append((current_price + price_range * 0.382, 0.5))
                targets.append((current_price + price_range * 0.618, 0.4))
            else:  # Sell
                targets.append((current_price - price_range * 0.382, 0.5))
                targets.append((current_price - price_range * 0.618, 0.4))

        # Sort by price (ascending for Buy, descending for Sell) and then by probability (descending)
        # Using lambda with a tuple for stable sorting. Convert to float if Decimal.
        sorted_targets = sorted(
            targets,
            key=lambda x: (x[0] if position_side == "Buy" else -x[0], x[1]),
            reverse=True,  # Primary sort on price, then secondary on probability
        )
        return sorted_targets


class SimpleMicrostructureAnalyzer:
    """14. Market microstructure analysis (simplified).
    Focuses on spread, depth, and order imbalance.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def analyze_orderbook_dynamics(
        self, orderbook_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Analyzes order book microstructure.
        `orderbook_data` should contain 'bids' and 'asks' lists of [price, quantity] floats.
        """
        if (
            not orderbook_data
            or "bids" not in orderbook_data
            or "asks" not in orderbook_data
        ):
            return {
                "spread_abs": 0.0,
                "spread_pct": 0.0,
                "depth_imbalance": 0.0,
                "bid_depth_usd": 0.0,
                "ask_depth_usd": 0.0,
                "large_orders_detected": False,
            }

        bids = orderbook_data[
            "bids"
        ]  # Already converted to floats from AdvancedOrderbookManager
        asks = orderbook_data["asks"]

        if not bids or not asks:
            return {
                "spread_abs": 0.0,
                "spread_pct": 0.0,
                "depth_imbalance": 0.0,
                "bid_depth_usd": 0.0,
                "ask_depth_usd": 0.0,
                "large_orders_detected": False,
            }

        best_bid = bids[0].price  # Assuming PriceLevel objects
        best_ask = asks[0].price  # Assuming PriceLevel objects

        spread_abs = best_ask - best_bid
        spread_pct = (spread_abs / best_bid) * 100 if best_bid > 0 else 0.0

        # Depth imbalance (top N levels)
        depth_levels = 10  # Consider top 10 levels
        bid_depth_qty = sum(b.quantity for b in bids[:depth_levels])
        ask_depth_qty = sum(a.quantity for a in asks[:depth_levels])

        # Estimate depth in USD value
        bid_depth_usd = sum(b.price * b.quantity for b in bids[:depth_levels])
        ask_depth_usd = sum(a.price * a.quantity for a in asks[:depth_levels])

        total_depth_qty = bid_depth_qty + ask_depth_qty
        depth_imbalance = (
            (bid_depth_qty - ask_depth_qty) / total_depth_qty
            if total_depth_qty > 0
            else 0.0
        )

        # Large orders detection (simple heuristic)
        # Check if any order in top 5 levels is significantly larger than average
        avg_bid_qty = bid_depth_qty / len(bids[:depth_levels]) if bids else 0
        avg_ask_qty = ask_depth_qty / len(asks[:depth_levels]) if asks else 0

        large_orders_detected = any(
            b.quantity > avg_bid_qty * 5 for b in bids[:5]
        ) or any(a.quantity > avg_ask_qty * 5 for a in asks[:5])

        return {
            "spread_abs": spread_abs,
            "spread_pct": spread_pct,
            "depth_imbalance": depth_imbalance,
            "bid_depth_usd": bid_depth_usd,
            "ask_depth_usd": ask_depth_usd,
            "large_orders_detected": large_orders_detected,
            "liquidity_depth_ratio": bid_depth_usd / ask_depth_usd
            if ask_depth_usd > 0
            else (1.0 if bid_depth_usd > 0 else 0.0),
        }


class SimpleLiquidityAnalyzer:
    """15. Market liquidity analysis (simplified).
    Combines volume and spread metrics.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def analyze_liquidity(
        self, df: pd.DataFrame, microstructure_data: dict[str, Any]
    ) -> float:
        """Analyzes market liquidity and returns a score (0-1).
        Combines volume-based and spread-based liquidity.
        """
        scores = []

        # Volume-based liquidity (relative to recent average)
        if len(df) > 20 and "volume" in df.columns:
            recent_volume = df["volume"].iloc[-1]
            avg_volume_20 = df["volume"].iloc[-20:].mean()

            if avg_volume_20 > 0:
                volume_score = min(
                    recent_volume / (avg_volume_20 * 1.5), 1.0
                )  # Score up to 1.5x avg vol
                scores.append(volume_score)
            else:
                scores.append(0.5)  # Neutral if no avg volume
        else:
            scores.append(0.5)  # Neutral if not enough volume history

        # Spread-based liquidity
        spread_pct = microstructure_data.get("spread_pct", 0.0)
        if spread_pct > 0:
            # Lower spread = higher liquidity. Normalize to 0-1 range.
            # Assuming typical spread < 0.1% (0.001) for liquid assets
            spread_liquidity_score = max(
                0.0, 1.0 - (spread_pct / 0.1)
            )  # Max 0.1% spread is 0 score
            scores.append(spread_liquidity_score)
        else:
            scores.append(0.5)  # Neutral if no spread

        # Depth-based liquidity
        total_depth_usd = microstructure_data.get(
            "bid_depth_usd", 0.0
        ) + microstructure_data.get("ask_depth_usd", 0.0)
        # Normalize total depth (requires calibration for specific market/symbol)
        # Assuming $100,000 depth is "good" for a typical altcoin on a 15m candle
        depth_score = min(1.0, total_depth_usd / 100000.0)
        scores.append(depth_score)

        return np.mean(scores) if scores else 0.5


class SimpleWhaleDetector:
    """16. Whale activity detection (simplified heuristics).
    Avoids complex network analysis.
    """

    def __init__(self, logger: logging.Logger, config: Any):
        self.logger = logger
        self.config = config  # Access ANOMALY_DETECTOR_THRESHOLD_STD

    def detect_whale_activity(
        self, df: pd.DataFrame, microstructure_data: dict[str, Any]
    ) -> bool:
        """Detects potential whale activity based on volume spikes and large order book entries."""
        whale_indicators_count = 0

        # Volume spike detection (uses anomaly detector)
        if "volume" in df.columns:
            anomaly_detector = SimpleAnomalyDetector(
                self.logger,
                rolling_window=self.config.ANOMALY_DETECTOR_ROLLING_WINDOW,
                threshold_std=self.config.ANOMALY_DETECTOR_THRESHOLD_STD,
            )
            volume_anomalies = anomaly_detector.detect_anomalies(df["volume"])
            if volume_anomalies.iloc[-1]:  # Latest volume is an anomaly
                self.logger.info("Whale Detector: Volume spike anomaly detected.")
                whale_indicators_count += 1

        # Large orders in order book
        if microstructure_data.get("large_orders_detected"):
            self.logger.info("Whale Detector: Large orders detected in order book.")
            whale_indicators_count += 1

        # Large price movement with significant volume (from `df`)
        if len(df) > 1 and "close" in df.columns and "volume" in df.columns:
            price_change_pct = (
                abs(df["close"].iloc[-1] - df["close"].iloc[-2])
                / df["close"].iloc[-2]
                * 100
            )
            # Only count if price change is substantial (e.g., > 1% and already some whale indicators)
            if price_change_pct > 1.0 and whale_indicators_count >= 1:
                self.logger.info(
                    f"Whale Detector: Large price move ({price_change_pct:.2f}%) detected with other whale indicators."
                )
                whale_indicators_count += 1

        return (
            whale_indicators_count >= 2
        )  # At least 2 indicators suggest whale activity


class AdvancedFeatures:
    """Consolidates various advanced analysis features."""

    def __init__(self, logger: logging.Logger, config: Any):
        self.logger = logger
        self.config = config

        self.pattern_engine = PatternRecognitionEngine(self.logger)
        self.sentiment_analyzer = SimpleSentimentAnalysis(self.logger)
        self.anomaly_detector_volume = SimpleAnomalyDetector(
            self.logger,
            rolling_window=self.config.ANOMALY_DETECTOR_ROLLING_WINDOW,
            threshold_std=self.config.ANOMALY_DETECTOR_THRESHOLD_STD,
        )
        self.anomaly_detector_price_change = SimpleAnomalyDetector(
            self.logger,
            rolling_window=self.config.ANOMALY_DETECTOR_ROLLING_WINDOW,
            threshold_std=self.config.ANOMALY_DETECTOR_THRESHOLD_STD,
        )
        self.dynamic_risk_manager = DynamicRiskManager(self.logger, self.config)
        self.price_target_predictor = SimplePriceTargetPredictor(self.logger)
        self.microstructure_analyzer = SimpleMicrostructureAnalyzer(self.logger)
        self.liquidity_analyzer = SimpleLiquidityAnalyzer(self.logger)
        self.whale_detector = SimpleWhaleDetector(self.logger, self.config)

        # Conceptual modules (placeholders, require external data/integration)
        self.correlation_analyzer = CorrelationAnalyzer(self.logger)
        self.economic_calendar = EconomicCalendarIntegration(self.logger)

    async def perform_advanced_analysis(
        self,
        df: pd.DataFrame,
        current_market_price: float,
        orderbook_data: dict[str, Any],  # Raw bids/asks from orderbook_manager
        indicator_values: dict[str, float],
    ) -> dict[str, Any]:
        """Performs a consolidated set of advanced analyses."""
        analysis_results: dict[str, Any] = {}

        # 1. Pattern Recognition
        analysis_results["patterns_detected"] = self.pattern_engine.detect_patterns(df)

        # 2. Sentiment Analysis (Placeholder, requires external news/social data)
        # For now, it will return dummy data or analyze placeholder text.
        analysis_results["sentiment_score"] = self.sentiment_analyzer.analyze_sentiment(
            news_headlines=["Market showing strong upward momentum for crypto"],
            social_media_keywords={"bullish crypto": 100, "bearish crypto": 20},
        )

        # 3. Anomaly Detection
        volume_anomalies = self.anomaly_detector_volume.detect_anomalies(df["volume"])
        price_change_pct = df["close"].pct_change().abs() * 100
        price_anomalies = self.anomaly_detector_price_change.detect_anomalies(
            price_change_pct
        )
        analysis_results["volume_anomaly_detected"] = volume_anomalies.iloc[-1]
        analysis_results["price_anomaly_detected"] = price_anomalies.iloc[-1]

        # 4. Market Microstructure Analysis
        microstructure_data = self.microstructure_analyzer.analyze_orderbook_dynamics(
            orderbook_data
        )
        analysis_results["microstructure"] = microstructure_data

        # 5. Liquidity Analysis
