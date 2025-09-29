import json
import logging
import os
from pathlib import Path
from typing import Any

from colorama import Fore, Style

# Neon Color Scheme
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
NEON_BLUE = Fore.CYAN
RESET = Style.RESET_ALL

# --- Constants ---
DEFAULT_CONFIG_FILE = "config.json"


class Config:
    """Loads and manages bot configuration from a JSON file and environment variables."""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._config_data: dict[str, Any] = {}
        self._load_config_from_file(DEFAULT_CONFIG_FILE)
        self._load_env_vars()
        self._apply_strategy_profile()

    def _load_config_from_file(self, filepath: str) -> None:
        default_config = {
            "symbol": "BTCUSDT",
            "interval": "15m",
            "loop_delay": 15,
            "orderbook_limit": 50,
            "testnet": True,
            "timezone": "America/Chicago",
            "signal_score_threshold": 2.0,
            "volume_confirmation_multiplier": 1.5,
            "cooldown_sec": 60,
            "hysteresis_ratio": 0.85,
            "trade_management": {
                "enabled": True,
                "account_balance": 1000.0,
                "risk_per_trade_percent": 1.0,
                "stop_loss_atr_multiple": 1.5,
                "take_profit_atr_multiple": 2.0,
                "trailing_stop_atr_multiple": 0.5,
                "max_open_positions": 1,
                "default_leverage": 5,
                "slippage_percent": 0.001,
                "trading_fee_percent": 0.0005,
                "enable_trailing_stop": True,
                "break_even_atr_trigger": 0.5,
                "move_to_breakeven_atr_trigger": 1.0,
                "profit_lock_in_atr_multiple": 0.5,
                "close_on_opposite_signal": True,
                "reverse_position_on_opposite_signal": False,
            },
            "mtf_analysis": {
                "enabled": True,
                "higher_timeframes": ["60m", "240m"],
                "trend_indicators": ["ema", "ehlers_supertrend"],
                "trend_period": 50,
                "mtf_request_delay_seconds": 0.5,
            },
            "ml_enhancement": {
                "enabled": False,
                "model_path": "ml_model.pkl",
                "retrain_on_startup": False,
                "training_data_limit": 5000,
                "prediction_lookahead": 12,
                "profit_target_percent": 0.5,
                "feature_lags": [1, 2, 3, 5],
                "cross_validation_folds": 5,
                "sentiment_analysis_enabled": False,
                "bullish_sentiment_threshold": 0.6,
                "bearish_sentiment_threshold": 0.4,
            },
            "current_strategy_profile": "default_scalping",
            "adaptive_strategy_enabled": True,
            "strategy_profiles": {
                "default_scalping": {
                    "description": "Standard scalping strategy for fast markets.",
                    "market_condition_criteria": {
                        "adx_range": [0, 25],
                        "volatility_range": [0.005, 0.02],
                    },
                    "indicators_enabled": {
                        "ema_alignment": True,
                        "sma_trend_filter": True,
                        "momentum": True,
                        "volume_confirmation": True,
                        "stoch_rsi": True,
                        "rsi": True,
                        "bollinger_bands": True,
                        "vwap": True,
                        "cci": True,
                        "wr": True,
                        "psar": True,
                        "sma_10": True,
                        "mfi": True,
                        "orderbook_imbalance": True,
                        "fibonacci_levels": True,
                        "ehlers_supertrend": True,
                        "macd": True,
                        "adx": True,
                        "ichimoku_cloud": True,
                        "obv": True,
                        "cmf": True,
                        "volatility_index": True,
                        "vwma": True,
                        "volume_delta": True,
                        "kaufman_ama": True,
                        "relative_volume": True,
                        "market_structure": True,
                        "dema": True,
                        "keltner_channels": True,
                        "roc": True,
                        "candlestick_patterns": True,
                        "fibonacci_pivot_points": True,
                    },
                    "weights": {
                        "ema_alignment": 0.22,
                        "sma_trend_filter": 0.28,
                        "momentum_rsi_stoch_cci_wr_mfi": 0.18,
                        "volume_confirmation": 0.12,
                        "bollinger_bands": 0.22,
                        "vwap": 0.22,
                        "psar": 0.22,
                        "sma_10": 0.07,
                        "orderbook_imbalance": 0.07,
                        "ehlers_supertrend_alignment": 0.55,
                        "macd_alignment": 0.28,
                        "adx_strength": 0.18,
                        "ichimoku_confluence": 0.38,
                        "obv_momentum": 0.18,
                        "cmf_flow": 0.12,
                        "mtf_trend_confluence": 0.32,
                        "volatility_index_signal": 0.15,
                        "vwma_cross": 0.15,
                        "volume_delta_signal": 0.10,
                        "kaufman_ama_cross": 0.20,
                        "relative_volume_confirmation": 0.10,
                        "market_structure_confluence": 0.25,
                        "dema_crossover": 0.18,
                        "keltner_breakout": 0.20,
                        "roc_signal": 0.12,
                        "candlestick_confirmation": 0.15,
                        "fibonacci_pivot_points_confluence": 0.20,
                    },
                },
                "trend_following": {
                    "description": "Strategy focused on capturing longer trends.",
                    "market_condition_criteria": {
                        "adx_range": [25, 100],
                        "volatility_range": [0.01, 0.05],
                    },
                    "indicators_enabled": {
                        "ema_alignment": True,
                        "sma_trend_filter": True,
                        "macd": True,
                        "adx": True,
                        "ehlers_supertrend": True,
                        "ichimoku_cloud": True,
                        "mtf_analysis": True,
                        "volume_confirmation": True,
                        "volatility_filter": True,
                        "rsi": False,
                        "stoch_rsi": False,
                    },
                    "weights": {
                        "ema_alignment": 0.30,
                        "sma_trend_filter": 0.20,
                        "macd_alignment": 0.40,
                        "adx_strength": 0.35,
                        "ehlers_supertrend_alignment": 0.60,
                        "ichimoku_confluence": 0.50,
                        "mtf_trend_confluence": 0.40,
                        "volume_confirmation": 0.15,
                        "volatility_filter": 0.15,
                        "sentiment_signal": 0.20,
                    },
                },
            },
            "indicator_settings": {
                "atr_period": 14,
                "ema_short_period": 9,
                "ema_long_period": 21,
                "rsi_period": 14,
                "stoch_rsi_period": 14,
                "stoch_k_period": 3,
                "stoch_d_period": 3,
                "bollinger_bands_period": 20,
                "bollinger_bands_std_dev": 2.0,
                "cci_period": 20,
                "williams_r_period": 14,
                "mfi_period": 14,
                "psar_acceleration": 0.02,
                "psar_max_acceleration": 0.2,
                "sma_short_period": 10,
                "sma_long_period": 50,
                "fibonacci_window": 60,
                "ehlers_fast_period": 10,
                "ehlers_fast_multiplier": 2.0,
                "ehlers_slow_period": 20,
                "ehlers_slow_multiplier": 3.0,
                "macd_fast_period": 12,
                "macd_slow_period": 26,
                "macd_signal_period": 9,
                "adx_period": 14,
                "ichimoku_tenkan_period": 9,
                "ichimoku_kijun_period": 26,
                "ichimoku_senkou_span_b_period": 52,
                "ichimoku_chikou_span_offset": 26,
                "obv_ema_period": 20,
                "cmf_period": 20,
                "rsi_oversold": 30,
                "rsi_overbought": 70,
                "stoch_rsi_oversold": 20,
                "stoch_rsi_overbought": 80,
                "cci_oversold": -100,
                "cci_overbought": 100,
                "williams_r_oversold": -80,
                "williams_r_overbought": -20,
                "mfi_oversold": 20,
                "mfi_overbought": 80,
                "volatility_index_period": 20,
                "vwma_period": 20,
                "volume_delta_period": 5,
                "volume_delta_threshold": 0.2,
                "kama_period": 10,
                "kama_fast_period": 2,
                "kama_slow_period": 30,
                "relative_volume_period": 20,
                "relative_volume_threshold": 1.5,
                "market_structure_lookback_period": 20,
                "dema_period": 14,
                "keltner_period": 20,
                "keltner_atr_multiplier": 2.0,
                "roc_period": 12,
                "roc_oversold": -5.0,
                "roc_overbought": 5.0,
                "min_candlestick_patterns_bars": 2,
            },
            "indicators": {},
            "active_weights": {},
        }

        if not Path(filepath).exists():
            self.logger.warning(
                f"{NEON_YELLOW}Configuration file not found. Creating default config at {filepath}{RESET}"
            )
            try:
                with Path(filepath).open("w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=4)
            except OSError as e:
                self.logger.error(
                    f"{NEON_RED}Error creating default config file: {e}{RESET}"
                )
            self._config_data = default_config
        else:
            try:
                with Path(filepath).open(encoding="utf-8") as f:
                    self._config_data = json.load(f)
                self._ensure_config_keys(self._config_data, default_config)
                with Path(filepath).open("w", encoding="utf-8") as f_write:
                    json.dump(self._config_data, f_write, indent=4)
            except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
                self.logger.error(
                    f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
                )
                self._config_data = default_config
                try:
                    with Path(filepath).open("w", encoding="utf-8") as f_default:
                        json.dump(default_config, f_default, indent=4)
                except OSError as e_save:
                    self.logger.error(
                        f"{NEON_RED}Could not save default config: {e_save}{RESET}"
                    )

    def _ensure_config_keys(
        self, config: dict[str, Any], default_config: dict[str, Any]
    ) -> None:
        for key, default_value in default_config.items():
            if key not in config:
                config[key] = default_value
            elif isinstance(default_value, dict) and isinstance(config.get(key), dict):
                self._ensure_config_keys(config[key], default_value)
            elif isinstance(default_value, dict) and not isinstance(
                config.get(key), dict
            ):
                config[key] = default_value

    def _load_env_vars(self) -> None:
        self.BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
        self.BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
        # Add other environment variables if needed

    def _apply_strategy_profile(self) -> None:
        active_profile_name = self._config_data.get(
            "current_strategy_profile", "default_scalping"
        )
        if active_profile_name in self._config_data.get("strategy_profiles", {}):
            active_profile = self._config_data["strategy_profiles"][active_profile_name]
            if "indicators_enabled" in active_profile:
                self._config_data["indicators"] = active_profile["indicators_enabled"]
            if "weights" in active_profile:
                self._config_data["active_weights"] = active_profile["weights"]
            self.logger.info(
                f"{NEON_BLUE}Active strategy profile '{active_profile_name}' loaded successfully.{RESET}"
            )
        else:
            self.logger.warning(
                f"{NEON_YELLOW}Configured strategy profile '{active_profile_name}' not found. Falling back to default.{RESET}"
            )
            if "indicators" not in self._config_data:
                self._config_data["indicators"] = self._config_data[
                    "strategy_profiles"
                ]["default_scalping"]["indicators_enabled"]
            if "active_weights" not in self._config_data:
                self._config_data["active_weights"] = self._config_data[
                    "strategy_profiles"
                ]["default_scalping"]["weights"]

    def __getattr__(self, name: str) -> Any:
        if name in self._config_data:
            return self._config_data[name]
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def get_config(self) -> dict[str, Any]:
        return self._config_data

    def set_active_strategy_profile(self, profile_name: str) -> None:
        if profile_name in self._config_data.get("strategy_profiles", {}):
            self._config_data["current_strategy_profile"] = profile_name
            self._apply_strategy_profile()
            self.logger.info(
                f"{NEON_BLUE}Switched active strategy profile to '{profile_name}'.{RESET}"
            )
        else:
            self.logger.warning(
                f"{NEON_YELLOW}Strategy profile '{profile_name}' not found. Current profile remains '{self.current_strategy_profile}'.{RESET}"
            )
