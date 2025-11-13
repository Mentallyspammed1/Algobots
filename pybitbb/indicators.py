# indicators.py
import logging
from typing import Any

import pandas as pd

# Import the market data helper to fetch historical kline data
from bybit_market_data_helper import BybitMarketDataHelper

# Configure logging for the module
logging.basicConfig(
    level=logging.INFO,  # Changed to INFO for less verbose default output, DEBUG for full details
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


class BybitIndicators:
    """A helper class for fetching historical kline data from Bybit and
    calculating various technical indicators using the pandas_ta library.
    """

    def __init__(self, testnet: bool = False, api_key: str = "", api_secret: str = ""):
        """Initializes the BybitIndicators helper.

        :param testnet: Set to True to connect to the Bybit testnet, False for mainnet.
        :param api_key: Optional. Your Bybit API key. (Needed if market data endpoints become authenticated).
        :param api_secret: Optional. Your Bybit API secret.
        """
        self.market_data_helper = BybitMarketDataHelper(
            testnet=testnet, api_key=api_key, api_secret=api_secret
        )
        logger.info(f"BybitIndicators initialized. Testnet: {testnet}.")

    def _fetch_kline_data(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> pd.DataFrame | None:
        """Internal method to fetch kline data and convert it into a pandas DataFrame.

        :param category: The product type (e.g., "linear", "spot").
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param interval: The kline interval (e.g., "1", "60", "D").
        :param limit: Number of data points to retrieve (max 1000).
        :param start_time: Optional. Start timestamp in milliseconds.
        :param end_time: Optional. End timestamp in milliseconds.
        :return: A pandas DataFrame with columns ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover']
                 or None on failure.
        """
        logger.debug(
            f"Fetching kline data for {symbol}, interval {interval}, limit {limit}..."
        )
        kline_data = self.market_data_helper.get_kline(
            category=category,
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

        if not kline_data or not kline_data.get("list"):
            logger.warning(
                f"No kline data fetched for {symbol} with interval {interval}."
            )
            return None

        # Bybit kline data structure: [timestamp, open, high, low, close, volume, turnover]
        df = pd.DataFrame(
            kline_data["list"],
            columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"],
        )

        # Convert data types
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df[["open", "high", "low", "close", "volume", "turnover"]] = df[
            ["open", "high", "low", "close", "volume", "turnover"]
        ].astype(float)

        # Set timestamp as index for pandas_ta compatibility
        df = df.set_index("timestamp")
        df = df.sort_index()  # Ensure chronological order

        logger.debug(f"Successfully fetched and prepared kline data for {symbol}.")
        return df

    def get_historical_data_with_indicators(
        self,
        category: str,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time: int | None = None,
        end_time: int | None = None,
        indicators: list[str] | None = None,
        indicator_kwargs: dict[str, Any] | None = None,
    ) -> pd.DataFrame | None:
        """Fetches historical kline data and calculates a specified list of technical indicators.

        :param category: The product type (e.g., "linear", "spot").
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param interval: The kline interval (e.g., "1", "60", "D").
        :param limit: Number of data points to retrieve.
        :param start_time: Optional. Start timestamp in milliseconds.
        :param end_time: Optional. End timestamp in milliseconds.
        :param indicators: Optional. A list of indicator names to calculate (e.g., ['sma', 'rsi', 'macd']).
                           If None, only returns raw kline data.
        :param indicator_kwargs: Optional. A dictionary of keyword arguments for specific indicators.
                                 Keys should be indicator names, values should be dicts of args.
                                 Example: {'sma': {'length': 20}, 'rsi': {'length': 14}}.
        :return: A pandas DataFrame containing kline data and calculated indicators, or None on failure.
        """
        df = self._fetch_kline_data(
            category, symbol, interval, limit, start_time, end_time
        )
        if df is None:
            return None

        if indicators:
            if not isinstance(indicators, list) or not all(
                isinstance(i, str) for i in indicators
            ):
                logger.error(
                    "Invalid 'indicators' parameter. Must be a list of strings."
                )
                return None

            indicator_kwargs = indicator_kwargs if indicator_kwargs is not None else {}

            for indicator_name in indicators:
                try:
                    # pandas_ta functions are designed to add columns directly to the DataFrame.
                    # We use df.ta.strategy for a more generic approach, but need to ensure
                    # the indicator is correctly applied.

                    # Create a temporary Strategy object for each indicator
                    strat_kwargs = indicator_kwargs.get(indicator_name, {})

                    if hasattr(df.ta, indicator_name):
                        indicator_method = getattr(df.ta, indicator_name)
                        # All pandas_ta methods support 'append=True' to add to the DataFrame
                        indicator_method(append=True, **strat_kwargs)
                        logger.debug(f"Calculated {indicator_name} for {symbol}.")
                    else:
                        logger.warning(
                            f"Indicator '{indicator_name}' not found in pandas_ta. Skipping."
                        )

                except Exception as e:
                    logger.error(
                        f"Failed to calculate indicator '{indicator_name}' for {symbol}: {e}",
                        exc_info=True,
                    )

        # Drop any rows with NaN values that result from indicator calculations (especially at the beginning)
        # This ensures that all indicator columns have valid data.
        df = df.dropna()
        if df.empty:
            logger.warning(
                f"DataFrame became empty after dropping NaN values for {symbol}. Not enough data for indicators."
            )
            return None

        logger.info(
            f"Successfully calculated indicators for {symbol}, interval {interval}. DataFrame shape: {df.shape}"
        )
        return df

    # --- Convenience Wrapper Methods for Specific Indicators ---
    # Existing Indicators
    def get_sma(
        self, category: str, symbol: str, interval: str, length: int = 20, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Simple Moving Average (SMA)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["sma"],
            indicator_kwargs={"sma": {"length": length, **kwargs}},
        )

    def get_ema(
        self, category: str, symbol: str, interval: str, length: int = 20, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Exponential Moving Average (EMA)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["ema"],
            indicator_kwargs={"ema": {"length": length, **kwargs}},
        )

    def get_rsi(
        self, category: str, symbol: str, interval: str, length: int = 14, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Relative Strength Index (RSI)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["rsi"],
            indicator_kwargs={"rsi": {"length": length, **kwargs}},
        )

    def get_macd(
        self,
        category: str,
        symbol: str,
        interval: str,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Moving Average Convergence Divergence (MACD)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["macd"],
            indicator_kwargs={
                "macd": {"fast": fast, "slow": slow, "signal": signal, **kwargs}
            },
        )

    def get_bollinger_bands(
        self,
        category: str,
        symbol: str,
        interval: str,
        length: int = 20,
        std: int = 2,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Bollinger Bands (BBANDS)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["bbands"],
            indicator_kwargs={"bbands": {"length": length, "std": std, **kwargs}},
        )

    def get_stoch_rsi(
        self,
        category: str,
        symbol: str,
        interval: str,
        rsi_length: int = 14,
        k_length: int = 3,
        d_length: int = 3,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Stochastic RSI (STOCHRSI)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["stochrsi"],
            indicator_kwargs={
                "stochrsi": {
                    "length": rsi_length,
                    "k": k_length,
                    "d": d_length,
                    **kwargs,
                }
            },
        )

    # --- 10+ New Indicators ---
    def get_supertrend(
        self,
        category: str,
        symbol: str,
        interval: str,
        length: int = 7,
        multiplier: float = 3.0,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Supertrend (ST).
        Note: pandas_ta provides a standard Supertrend. If you meant Ehlers Supertrend,
        it might require a custom implementation or a different library.
        """
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["supertrend"],
            indicator_kwargs={
                "supertrend": {"length": length, "multiplier": multiplier, **kwargs}
            },
        )

    def get_atr(
        self, category: str, symbol: str, interval: str, length: int = 14, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Average True Range (ATR)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["atr"],
            indicator_kwargs={"atr": {"length": length, **kwargs}},
        )

    def get_cci(
        self, category: str, symbol: str, interval: str, length: int = 20, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Commodity Channel Index (CCI)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["cci"],
            indicator_kwargs={"cci": {"length": length, **kwargs}},
        )

    def get_mfi(
        self, category: str, symbol: str, interval: str, length: int = 14, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Money Flow Index (MFI)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["mfi"],
            indicator_kwargs={"mfi": {"length": length, **kwargs}},
        )

    def get_obv(
        self, category: str, symbol: str, interval: str, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates On-Balance Volume (OBV)."""
        # OBV typically only needs 'close' and 'volume', no length parameter
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["obv"],
            indicator_kwargs={"obv": {**kwargs}},
        )

    def get_stoch(
        self,
        category: str,
        symbol: str,
        interval: str,
        k_length: int = 14,
        d_length: int = 3,
        smooth_k: int = 3,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Stochastic Oscillator (STOCH)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["stoch"],
            indicator_kwargs={
                "stoch": {"k": k_length, "d": d_length, "smooth_k": smooth_k, **kwargs}
            },
        )

    def get_ao(
        self,
        category: str,
        symbol: str,
        interval: str,
        fast: int = 5,
        slow: int = 34,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Awesome Oscillator (AO)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["ao"],
            indicator_kwargs={"ao": {"fast": fast, "slow": slow, **kwargs}},
        )

    def get_psar(
        self,
        category: str,
        symbol: str,
        interval: str,
        af0: float = 0.02,
        af: float = 0.02,
        max_af: float = 0.2,
        **kwargs,
    ) -> pd.DataFrame | None:
        """Calculates Parabolic SAR (PSAR)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["psar"],
            indicator_kwargs={
                "psar": {"af0": af0, "af": af, "max_af": max_af, **kwargs}
            },
        )

    def get_vwap(
        self, category: str, symbol: str, interval: str, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Volume Weighted Average Price (VWAP)."""
        # VWAP typically needs 'open', 'high', 'low', 'close', 'volume'
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["vwap"],
            indicator_kwargs={"vwap": {**kwargs}},
        )

    def get_kama(
        self, category: str, symbol: str, interval: str, length: int = 10, **kwargs
    ) -> pd.DataFrame | None:
        """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
        return self.get_historical_data_with_indicators(
            category,
            symbol,
            interval,
            indicators=["kama"],
            indicator_kwargs={"kama": {"length": length, **kwargs}},
        )


# Example Usage
if __name__ == "__main__":
    # For public market data, API key/secret are optional.
    # Set USE_TESTNET to False for production (mainnet).
    API_KEY = ""  # Optional for public market data
    API_SECRET = ""  # Optional for public market data
    USE_TESTNET = True

    indicators_helper = BybitIndicators(
        testnet=USE_TESTNET, api_key=API_KEY, api_secret=API_SECRET
    )

    SYMBOL = "BTCUSDT"
    CATEGORY = "linear"
    INTERVAL = "60"  # 1-hour kline

    print(f"\n--- Fetching {SYMBOL} 1-hour kline data with multiple indicators ---")
    # Fetch 200 bars to ensure enough data for various indicator calculations
    df_multi_indicators = indicators_helper.get_historical_data_with_indicators(
        category=CATEGORY,
        symbol=SYMBOL,
        interval=INTERVAL,
        limit=200,
        indicators=[
            "sma",
            "ema",
            "rsi",
            "macd",
            "bbands",
            "supertrend",
            "atr",
            "cci",
            "mfi",
            "obv",
            "stoch",
            "ao",
            "psar",
            "vwap",
            "kama",
        ],
        indicator_kwargs={
            "sma": {"length": 20},
            "ema": {"length": 20},
            "rsi": {"length": 14},
            "macd": {"fast": 12, "slow": 26, "signal": 9},
            "bbands": {"length": 20, "std": 2},
            "supertrend": {"length": 7, "multiplier": 3.0},
            "atr": {"length": 14},
            "cci": {"length": 20},
            "mfi": {"length": 14},
            "stoch": {"k": 14, "d": 3, "smooth_k": 3},
            "ao": {"fast": 5, "slow": 34},
            "psar": {"af0": 0.02, "af": 0.02, "max_af": 0.2},
            "kama": {"length": 10},
            # OBV and VWAP don't typically need specific kwargs for basic use
        },
    )

    if df_multi_indicators is not None:
        print(df_multi_indicators.tail())  # Display last few rows
        print(f"\nColumns available: {df_multi_indicators.columns.tolist()}")

        # Example of accessing some new indicator values
        if "SUPERT_7_3.0" in df_multi_indicators.columns:
            print(
                f"\nLast Supertrend (7,3) value: {df_multi_indicators['SUPERT_7_3.0'].iloc[-1]:.2f}"
            )
        if "ATR_14" in df_multi_indicators.columns:
            print(f"Last ATR(14) value: {df_multi_indicators['ATR_14'].iloc[-1]:.4f}")
        if "CCI_20" in df_multi_indicators.columns:
            print(f"Last CCI(20) value: {df_multi_indicators['CCI_20'].iloc[-1]:.2f}")
        if "MFI_14" in df_multi_indicators.columns:
            print(f"Last MFI(14) value: {df_multi_indicators['MFI_14'].iloc[-1]:.2f}")
        if "OBV" in df_multi_indicators.columns:
            print(f"Last OBV value: {df_multi_indicators['OBV'].iloc[-1]:.0f}")
        if "STOCHk_14_3_3" in df_multi_indicators.columns:
            print(
                f"Last STOCH %K (14,3,3) value: {df_multi_indicators['STOCHk_14_3_3'].iloc[-1]:.2f}"
            )
        if "AO" in df_multi_indicators.columns:
            print(f"Last AO value: {df_multi_indicators['AO'].iloc[-1]:.2f}")
        if (
            "PSARl_0.02_0.2" in df_multi_indicators.columns
        ):  # PSAR can have long/short variants
            print(
                f"Last PSAR Long value: {df_multi_indicators['PSARl_0.02_0.2'].iloc[-1]:.2f}"
            )
        if "VWAP" in df_multi_indicators.columns:
            print(f"Last VWAP value: {df_multi_indicators['VWAP'].iloc[-1]:.2f}")
        if "KAMA_10" in df_multi_indicators.columns:
            print(f"Last KAMA(10) value: {df_multi_indicators['KAMA_10'].iloc[-1]:.2f}")

    else:
        print(f"Failed to get data or calculate complex indicators for {SYMBOL}.")

    print(f"\n--- Using convenience wrapper for Supertrend({SYMBOL}) ---")
    df_supertrend_only = indicators_helper.get_supertrend(
        category=CATEGORY,
        symbol=SYMBOL,
        interval=INTERVAL,
        length=10,
        multiplier=3.5,
        limit=100,
    )
    if df_supertrend_only is not None:
        print(
            df_supertrend_only[
                [
                    "close",
                    "SUPERT_10_3.5",
                    "SUPERTd_10_3.5",
                    "SUPERTl_10_3.5",
                    "SUPERTs_10_3.5",
                ]
            ].tail()
        )
    else:
        print(f"Failed to get Supertrend for {SYMBOL}.")
