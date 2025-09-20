1,9d0
< """Whalebot: An automated cryptocurrency trading bot for Bybit.
< 
< This bot leverages various technical indicators and multi-timeframe analysis
< to generate trading signals and manage positions on the Bybit exchange.
< It includes features for risk management, performance tracking, and alerts.
< """
< 
< import hashlib
< import hmac
12a4
> import random
15d6
< import urllib.parse
17a9
> from logging.handlers import RotatingFileHandler
19c11
< from typing import Any, Literal
---
> from typing import Any, ClassVar, Literal
20a13
> import indicators  # Import the new indicators module
23c16
< import requests
---
> from alert_system import AlertSystem
25,27c18
< from dotenv import load_dotenv
< from requests.adapters import HTTPAdapter
< from urllib3.util.retry import Retry
---
> from dotenv import dotenv_values
29,30c20,27
< # Scikit-learn is explicitly excluded as per user request.
< SKLEARN_AVAILABLE = False
---
> # Guarded import for the live trading client
> try:
>     import pybit.exceptions
>     from pybit.unified_trading import HTTP as PybitHTTP
> 
>     PYBIT_AVAILABLE = True
> except ImportError:
>     PYBIT_AVAILABLE = False
35d31
< load_dotenv()
37,86c33,37
< # Neon Color Scheme
< NEON_GREEN = Fore.LIGHTGREEN_EX
< NEON_BLUE = Fore.CYAN
< NEON_PURPLE = Fore.MAGENTA
< NEON_YELLOW = Fore.YELLOW
< NEON_RED = Fore.LIGHTRED_EX
< NEON_CYAN = Fore.CYAN
< RESET = Style.RESET_ALL
< 
< # Indicator specific colors (enhanced for new indicators)
< INDICATOR_COLORS = {
<     "SMA_10": Fore.LIGHTBLUE_EX,
<     "SMA_Long": Fore.BLUE,
<     "EMA_Short": Fore.LIGHTMAGENTA_EX,
<     "EMA_Long": Fore.MAGENTA,
<     "ATR": Fore.YELLOW,
<     "RSI": Fore.GREEN,
<     "StochRSI_K": Fore.CYAN,
<     "StochRSI_D": Fore.LIGHTCYAN_EX,
<     "BB_Upper": Fore.RED,
<     "BB_Middle": Fore.WHITE,
<     "BB_Lower": Fore.RED,
<     "CCI": Fore.LIGHTGREEN_EX,
<     "WR": Fore.LIGHTRED_EX,
<     "MFI": Fore.GREEN,
<     "OBV": Fore.BLUE,
<     "OBV_EMA": Fore.LIGHTBLUE_EX,
<     "CMF": Fore.MAGENTA,
<     "Tenkan_Sen": Fore.CYAN,
<     "Kijun_Sen": Fore.LIGHTCYAN_EX,
<     "Senkou_Span_A": Fore.GREEN,
<     "Senkou_Span_B": Fore.RED,
<     "Chikou_Span": Fore.YELLOW,
<     "PSAR_Val": Fore.MAGENTA,
<     "PSAR_Dir": Fore.LIGHTMAGENTA_EX,
<     "VWAP": Fore.WHITE,
<     "ST_Fast_Dir": Fore.BLUE,
<     "ST_Fast_Val": Fore.LIGHTBLUE_EX,
<     "ST_Slow_Dir": Fore.MAGENTA,
<     "ST_Slow_Val": Fore.LIGHTMAGENTA_EX,
<     "MACD_Line": Fore.GREEN,
<     "MACD_Signal": Fore.LIGHTGREEN_EX,
<     "MACD_Hist": Fore.YELLOW,
<     "ADX": Fore.CYAN,
<     "PlusDI": Fore.LIGHTCYAN_EX,
<     "MinusDI": Fore.RED,
<     "Volatility_Index": Fore.YELLOW,
<     "Volume_Delta": Fore.LIGHTCYAN_EX,
<     "VWMA": Fore.WHITE,
< }
---
> # --- Environment & API Key Loading ---
> # Explicitly load .env values from the script's directory for robustness
> script_dir = Path(__file__).resolve().parent
> dotenv_path = script_dir / '.env'
> config_env = dotenv_values(dotenv_path) if dotenv_path.exists() else {}
89,90c40,41
< API_KEY = os.getenv("BYBIT_API_KEY")
< API_SECRET = os.getenv("BYBIT_API_SECRET")
---
> API_KEY = config_env.get("BYBIT_API_KEY")
> API_SECRET = config_env.get("BYBIT_API_SECRET")
92a44
> BOT_STATE_FILE = "bot_state.json" # New constant for bot state file
96,97c48
< # Using UTC for consistency and to avoid timezone issues with API timestamps
< TIMEZONE = timezone.utc  # Changed from ZoneInfo("America/Chicago")
---
> TIMEZONE = timezone.utc
103,111c54,72
< # Magic Numbers as Constants (expanded)
< MIN_DATA_POINTS_TR = 2
< MIN_DATA_POINTS_SMOOTHER = 2
< MIN_DATA_POINTS_OBV = 2
< MIN_DATA_POINTS_PSAR = 2
< ADX_STRONG_TREND_THRESHOLD = 25
< ADX_WEAK_TREND_THRESHOLD = 20
< MIN_DATA_POINTS_VWMA = 2
< MIN_DATA_POINTS_VOLATILITY = 2
---
> # Neon Color Scheme
> NEON_GREEN = Fore.LIGHTGREEN_EX
> NEON_BLUE = Fore.CYAN
> NEON_PURPLE = Fore.MAGENTA
> NEON_YELLOW = Fore.YELLOW
> NEON_RED = Fore.LIGHTRED_EX
> NEON_CYAN = Fore.CYAN
> RESET = Style.RESET_ALL
> 
> # --- Helper Functions for Precision ---
> def round_qty(qty: Decimal, qty_step: Decimal) -> Decimal:
>     if qty_step is None or qty_step.is_zero():
>         return qty.quantize(Decimal("1.000000"), rounding=ROUND_DOWN)
>     return (qty // qty_step) * qty_step
> 
> def round_price(price: Decimal, price_precision: int) -> Decimal:
>     if price_precision < 0:
>         price_precision = 0
>     return price.quantize(Decimal(f"1e-{price_precision}"), rounding=ROUND_DOWN)
112a74,106
> # --- Bot State Management ---
> def save_bot_state(config: dict, position_manager: Any, performance_tracker: Any, logger: logging.Logger):
>     try:
>         state_data = {
>             "timestamp": datetime.now(TIMEZONE).isoformat(),
>             "config_summary": {
>                 "symbol": config.get("symbol"),
>                 "interval": config.get("interval"),
>                 "loop_delay": config.get("loop_delay"),
>                 "use_pybit": config.get("execution", {}).get("use_pybit", False),
>                 "testnet": config.get("execution", {}).get("testnet", False),
>             },
>             "performance_summary": performance_tracker.get_summary(),
>             "open_positions": [
>                 {
>                     "entry_time": pos["entry_time"].isoformat() if isinstance(pos["entry_time"], datetime) else pos["entry_time"],
>                     "symbol": pos["symbol"],
>                     "side": pos["side"],
>                     "entry_price": str(pos["entry_price"]),
>                     "qty": str(pos["qty"]),
>                     "stop_loss": str(pos["stop_loss"]),
>                     "take_profit": str(pos["take_profit"]),
>                     "status": pos["status"],
>                 } for pos in position_manager.get_open_positions()
>             ],
>             "current_price": str(config.get("_last_price", "---")),
>             "last_signal": config.get("_last_signal", "HOLD"),
>             "last_signal_score": config.get("_last_score", 0.0),
>         }
>         with open(BOT_STATE_FILE, "w", encoding="utf-8") as f:
>             json.dump(state_data, f, indent=4)
>     except Exception as e:
>         logger.error(f"{NEON_RED}Error saving bot state: {e}{RESET}")
116d109
<     """Load configuration from JSON file, creating a default if not found."""
118,127c111,113
<         # Core Settings
<         "symbol": "BTCUSDT",
<         "interval": "15",  # Changed "15m" to "15" to match Bybit API requirement
<         "loop_delay": LOOP_DELAY_SECONDS,
<         "orderbook_limit": 50,
<         "signal_score_threshold": 2.0,
<         "cooldown_sec": 60,
<         "hysteresis_ratio": 0.85,
<         "volume_confirmation_multiplier": 1.5,
<         # Position & Risk Management
---
>         "symbol": "BTCUSDT", "interval": "15", "loop_delay": LOOP_DELAY_SECONDS,
>         "orderbook_limit": 50, "signal_score_threshold": 2.0, "cooldown_sec": 60,
>         "hysteresis_ratio": 0.85, "volume_confirmation_multiplier": 1.5,
129,136c115,127
<             "enabled": True,
<             "account_balance": 1000.0,
<             "risk_per_trade_percent": 1.0,
<             "stop_loss_atr_multiple": 1.5,
<             "take_profit_atr_multiple": 2.0,
<             "max_open_positions": 1,
<             "order_precision": 5,  # New: Decimal places for order quantity
<             "price_precision": 3,  # New: Decimal places for price
---
>             "enabled": True, "account_balance": 1000.0, "risk_per_trade_percent": 1.0,
>             "stop_loss_atr_multiple": 1.5, "take_profit_atr_multiple": 2.0,
>             "max_open_positions": 1, "order_precision": 5, "price_precision": 3,
>         },
>         "risk_guardrails": {
>             "enabled": True, "max_day_loss_pct": 3.0, "max_drawdown_pct": 8.0,
>             "cooldown_after_kill_min": 120, "spread_filter_bps": 5.0, "ev_filter_enabled": True,
>         },
>         "session_filter": {
>             "enabled": False, "utc_allowed": [["00:00", "08:00"], ["13:00", "20:00"]],
>         },
>         "pyramiding": {
>             "enabled": False, "max_adds": 2, "step_atr": 0.7, "size_pct_of_initial": 0.5,
138d128
<         # Multi-Timeframe Analysis
140,143c130,131
<             "enabled": True,
<             "higher_timeframes": ["60", "240"],  # Changed "1h", "4h" to "60", "240"
<             "trend_indicators": ["ema", "ehlers_supertrend"],
<             "trend_period": 50,
---
>             "enabled": True, "higher_timeframes": ["60", "240"],
>             "trend_indicators": ["ema", "ehlers_supertrend"], "trend_period": 50,
146,157c134
<         # Machine Learning Enhancement (Explicitly disabled)
<         "ml_enhancement": {
<             "enabled": False,  # ML explicitly disabled
<             "model_path": "ml_model.pkl",
<             "retrain_on_startup": False,
<             "training_data_limit": 5000,
<             "prediction_lookahead": 12,
<             "profit_target_percent": 0.5,
<             "feature_lags": [1, 2, 3, 5],
<             "cross_validation_folds": 5,
<         },
<         # Indicator Periods & Thresholds
---
>         "ml_enhancement": {"enabled": False},
159,203c136,150
<             "atr_period": 14,
<             "ema_short_period": 9,
<             "ema_long_period": 21,
<             "rsi_period": 14,
<             "stoch_rsi_period": 14,
<             "stoch_k_period": 3,
<             "stoch_d_period": 3,
<             "bollinger_bands_period": 20,
<             "bollinger_bands_std_dev": 2.0,
<             "cci_period": 20,
<             "williams_r_period": 14,
<             "mfi_period": 14,
<             "psar_acceleration": 0.02,
<             "psar_max_acceleration": 0.2,
<             "sma_short_period": 10,
<             "sma_long_period": 50,
<             "fibonacci_window": 60,
<             "ehlers_fast_period": 10,
<             "ehlers_fast_multiplier": 2.0,
<             "ehlers_slow_period": 20,
<             "ehlers_slow_multiplier": 3.0,
<             "macd_fast_period": 12,
<             "macd_slow_period": 26,
<             "macd_signal_period": 9,
<             "adx_period": 14,
<             "ichimoku_tenkan_period": 9,
<             "ichimoku_kijun_period": 26,
<             "ichimoku_senkou_span_b_period": 52,
<             "ichimoku_chikou_span_offset": 26,
<             "obv_ema_period": 20,
<             "cmf_period": 20,
<             "rsi_oversold": 30,
<             "rsi_overbought": 70,
<             "stoch_rsi_oversold": 20,
<             "stoch_rsi_overbought": 80,
<             "cci_oversold": -100,
<             "cci_overbought": 100,
<             "williams_r_oversold": -80,
<             "williams_r_overbought": -20,
<             "mfi_oversold": 20,
<             "mfi_overbought": 80,
<             "volatility_index_period": 20,  # New: Volatility Index Period
<             "vwma_period": 20,  # New: VWMA Period
<             "volume_delta_period": 5,  # New: Volume Delta Period
<             "volume_delta_threshold": 0.2,  # New: Volume Delta Threshold for signals
---
>             "atr_period": 14, "ema_short_period": 9, "ema_long_period": 21, "rsi_period": 14,
>             "stoch_rsi_period": 14, "stoch_k_period": 3, "stoch_d_period": 3,
>             "bollinger_bands_period": 20, "bollinger_bands_std_dev": 2.0, "cci_period": 20,
>             "williams_r_period": 14, "mfi_period": 14, "psar_acceleration": 0.02,
>             "psar_max_acceleration": 0.2, "sma_short_period": 10, "sma_long_period": 50,
>             "fibonacci_window": 60, "ehlers_fast_period": 10, "ehlers_fast_multiplier": 2.0,
>             "ehlers_slow_period": 20, "ehlers_slow_multiplier": 3.0, "macd_fast_period": 12,
>             "macd_slow_period": 26, "macd_signal_period": 9, "adx_period": 14,
>             "ichimoku_tenkan_period": 9, "ichimoku_kijun_period": 26,
>             "ichimoku_senkou_span_b_period": 52, "ichimoku_chikou_span_offset": 26,
>             "obv_ema_period": 20, "cmf_period": 20, "rsi_oversold": 30, "rsi_overbought": 70,
>             "stoch_rsi_oversold": 20, "stoch_rsi_overbought": 80, "cci_oversold": -100,
>             "cci_overbought": 100, "williams_r_oversold": -80, "williams_r_overbought": -20,
>             "mfi_oversold": 20, "mfi_overbought": 80, "volatility_index_period": 20,
>             "vwma_period": 20, "volume_delta_period": 5, "volume_delta_threshold": 0.2,
205d151
<         # Active Indicators & Weights (expanded)
207,230c153,158
<             "ema_alignment": True,
<             "sma_trend_filter": True,
<             "momentum": True,  # Now a general category, individual momentum indicators are sub-checked
<             "volume_confirmation": True,
<             "stoch_rsi": True,
<             "rsi": True,
<             "bollinger_bands": True,
<             "vwap": True,
<             "cci": True,
<             "wr": True,
<             "psar": True,
<             "sma_10": True,
<             "mfi": True,
<             "orderbook_imbalance": True,
<             "fibonacci_levels": True,
<             "ehlers_supertrend": True,
<             "macd": True,
<             "adx": True,
<             "ichimoku_cloud": True,
<             "obv": True,
<             "cmf": True,
<             "volatility_index": True,  # New
<             "vwma": True,  # New
<             "volume_delta": True,  # New
---
>             "ema_alignment": True, "sma_trend_filter": True, "momentum": True,
>             "volume_confirmation": True, "stoch_rsi": True, "rsi": True, "bollinger_bands": True,
>             "vwap": True, "cci": True, "wr": True, "psar": True, "sma_10": True, "mfi": True,
>             "orderbook_imbalance": True, "fibonacci_levels": True, "ehlers_supertrend": True,
>             "macd": True, "adx": True, "ichimoku_cloud": True, "obv": True, "cmf": True,
>             "volatility_index": True, "vwma": True, "volume_delta": True,
234,252c162,168
<                 "ema_alignment": 0.22,
<                 "sma_trend_filter": 0.28,
<                 "momentum_rsi_stoch_cci_wr_mfi": 0.18,  # Combined weight for momentum
<                 "volume_confirmation": 0.12,
<                 "bollinger_bands": 0.22,
<                 "vwap": 0.22,
<                 "psar": 0.22,
<                 "sma_10": 0.07,
<                 "orderbook_imbalance": 0.07,
<                 "ehlers_supertrend_alignment": 0.55,
<                 "macd_alignment": 0.28,
<                 "adx_strength": 0.18,
<                 "ichimoku_confluence": 0.38,
<                 "obv_momentum": 0.18,
<                 "cmf_flow": 0.12,
<                 "mtf_trend_confluence": 0.32,
<                 "volatility_index_signal": 0.15,  # New
<                 "vwma_cross": 0.15,  # New
<                 "volume_delta_signal": 0.10,  # New
---
>                 "ema_alignment": 0.30, "sma_trend_filter": 0.20, "ehlers_supertrend_alignment": 0.40,
>                 "macd_alignment": 0.30, "adx_strength": 0.25, "ichimoku_confluence": 0.35,
>                 "psar": 0.15, "vwap": 0.15, "vwma_cross": 0.10, "sma_10": 0.05,
>                 "bollinger_bands": 0.25, "momentum_rsi_stoch_cci_wr_mfi": 0.35,
>                 "volume_confirmation": 0.10, "obv_momentum": 0.15, "cmf_flow": 0.10,
>                 "volume_delta_signal": 0.10, "orderbook_imbalance": 0.10,
>                 "mtf_trend_confluence": 0.25, "volatility_index_signal": 0.10,
254a171,203
>         "execution": {
>             "use_pybit": False, "testnet": False, "account_type": "UNIFIED", "category": "linear",
>             "position_mode": "ONE_WAY", "tpsl_mode": "Partial", "buy_leverage": "3",
>             "sell_leverage": "3", "tp_trigger_by": "LastPrice", "sl_trigger_by": "LastPrice",
>             "default_time_in_force": "GoodTillCancel", "reduce_only_default": False,
>             "post_only_default": False,
>             "position_idx_overrides": {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2},
>             "proxies": {
>                 "enabled": False,
>                 "http": "",
>                 "https": ""
>             },
>             "tp_scheme": {
>                 "mode": "atr_multiples",
>                 "targets": [
>                     {"name": "TP1", "atr_multiple": 1.0, "size_pct": 0.40, "order_type": "Limit", "tif": "PostOnly", "post_only": True},
>                     {"name": "TP2", "atr_multiple": 1.5, "size_pct": 0.40, "order_type": "Limit", "tif": "IOC", "post_only": False},
>                     {"name": "TP3", "atr_multiple": 2.0, "size_pct": 0.20, "order_type": "Limit", "tif": "GoodTillCancel", "post_only": False},
>                 ],
>             },
>             "sl_scheme": {
>                 "type": "atr_multiple", "atr_multiple": 1.5, "percent": 1.0,
>                 "use_conditional_stop": True, "stop_order_type": "Market",
>             },
>             "breakeven_after_tp1": {
>                 "enabled": True, "offset_type": "atr", "offset_value": 0.10,
>                 "lock_in_min_percent": 0, "sl_trigger_by": "LastPrice",
>             },
>             "live_sync": {
>                 "enabled": True, "poll_ms": 2500, "max_exec_fetch": 200,
>                 "only_track_linked": True, "heartbeat": {"enabled": True, "interval_ms": 5000},
>             },
>         },
260,262c209
<             logger.warning(
<                 f"{NEON_YELLOW}Configuration file not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
<             )
---
>             logger.warning(f"{NEON_YELLOW}Created default config at {filepath}{RESET}")
267d213
< 
275,283c221,222
<     except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
<         logger.error(
<             f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
<         )
<         try:
<             with Path(filepath).open("w", encoding="utf-8") as f_default:
<                 json.dump(default_config, f_default, indent=4)
<         except OSError as e_save:
<             logger.error(f"{NEON_RED}Could not save default config: {e_save}{RESET}")
---
>     except (OSError, json.JSONDecodeError) as e:
>         logger.error(f"{NEON_RED}Error loading config: {e}. Using default.{RESET}")
286d224
< 
288d225
<     """Recursively ensure all keys from default_config are in config."""
294a232,285
> # --- Logging Setup ---
> class SensitiveFormatter(logging.Formatter):
>     SENSITIVE_WORDS: ClassVar[list[str]] = ["API_KEY", "API_SECRET"]
>     def format(self, record):
>         original_message = super().format(record)
>         for word in self.SENSITIVE_WORDS:
>             if word in original_message:
>                 original_message = original_message.replace(word, "*" * len(word))
>         return original_message
> 
> def setup_logger(log_name: str, level=logging.INFO) -> logging.Logger:
>     logger = logging.getLogger(log_name)
>     logger.setLevel(level)
>     logger.propagate = False
>     if not logger.handlers:
>         console_handler = logging.StreamHandler(sys.stdout)
>         console_handler.setFormatter(SensitiveFormatter(f"{NEON_BLUE}%(asctime)s - %(levelname)s - %(message)s{RESET}"))
>         logger.addHandler(console_handler)
>         log_file = Path(LOG_DIRECTORY) / f"{log_name}.log"
>         file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
>         file_handler.setFormatter(SensitiveFormatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
>         logger.addHandler(file_handler)
>     return logger
> 
> # --- API Interaction & Live Trading ---
> class PybitTradingClient:
>     def __init__(self, config: dict[str, Any], logger: logging.Logger):
>         self.cfg = config
>         self.logger = logger
>         self.enabled = bool(config.get("execution", {}).get("use_pybit", False))
>         self.category = config.get("execution", {}).get("category", "linear")
>         self.testnet = bool(config.get("execution", {}).get("testnet", False))
>         if not self.enabled:
>             self.session = None
>             self.logger.info(f"{NEON_YELLOW}PyBit execution disabled.{RESET}")
>             return
>         if not PYBIT_AVAILABLE:
>             self.enabled = False
>             self.session = None
>             self.logger.error(f"{NEON_RED}PyBit not installed.{RESET}")
>             return
>         if not API_KEY or not API_SECRET:
>             self.enabled = False
>             self.session = None
>             self.logger.error(f"{NEON_RED}API keys not found for PyBit.{RESET}")
>             return
> 
>         proxies = {}
>         if self.cfg.get("execution", {}).get("proxies", {}).get("enabled", False):
>             proxies = {
>                 "http": self.cfg["execution"]["proxies"].get("http"),
>                 "https": self.cfg["execution"]["proxies"].get("https"),
>             }
>             self.logger.info(f"{NEON_BLUE}Proxy enabled.{RESET}")
296c287,327
< from unanimous_logger import setup_logger
---
>         try:
>             self.session = PybitHTTP(
>                 api_key=API_KEY,
>                 api_secret=API_SECRET,
>                 testnet=self.testnet,
>                 timeout=REQUEST_TIMEOUT,
>                 proxies=proxies if proxies.get("http") or proxies.get("https") else None
>             )
>             self.logger.info(f"{NEON_GREEN}PyBit client initialized. Testnet={self.testnet}{RESET}")
>         except (pybit.exceptions.FailedRequestError, Exception) as e:
>             self.enabled = False
>             self.session = None
>             self.logger.error(f"{NEON_RED}Failed to init PyBit client: {e}{RESET}")
> 
>     def _handle_403_error(self, e):
>         if "403" in str(e):
>             self.logger.error(f"{NEON_RED}Encountered a 403 Forbidden error. This may be due to an IP rate limit or a geographical restriction (e.g., from the USA). The bot will pause for 60 seconds.{RESET}")
>             time.sleep(60)
> 
>     def _pos_idx(self, side: Literal["BUY", "SELL"]) -> int:
>         pmode = self.cfg["execution"].get("position_mode", "ONE_WAY").upper()
>         overrides = self.cfg["execution"].get("position_idx_overrides", {})
>         if pmode == "ONE_WAY":
>             return int(overrides.get("ONE_WAY", 0))
>         return int(overrides.get("HEDGE_BUY" if side == "BUY" else "HEDGE_SELL", 1 if side == "BUY" else 2))
> 
>     def _side_to_bybit(self, side: Literal["BUY", "SELL"]) -> str:
>         return "Buy" if side == "BUY" else "Sell"
> 
>     def _q(self, x: Any) -> str:
>         return str(x)
> 
>     def _ok(self, resp: dict | None) -> bool:
>         return bool(resp and resp.get("retCode") == 0)
> 
>     def _log_api(self, action: str, resp: dict | None):
>         if not resp:
>             self.logger.error(f"{NEON_RED}{action}: No response.{RESET}")
>             return
>         if not self._ok(resp):
>             self.logger.error(f"{NEON_RED}{action}: Error {resp.get('retCode')} - {resp.get('retMsg')}{RESET}")
297a329,338
>     def set_leverage(self, symbol: str, buy: str, sell: str) -> bool:
>         if not self.enabled: return False
>         try:
>             resp = self.session.set_leverage(category=self.category, symbol=symbol, buyLeverage=self._q(buy), sellLeverage=self._q(sell))
>             self._log_api("set_leverage", resp)
>             return self._ok(resp)
>         except (pybit.exceptions.InvalidRequestError, pybit.exceptions.PybitHTTPException) as e:
>             self.logger.error(f"{NEON_RED}set_leverage failed: {e}. Please check symbol, leverage, and account status.{RESET}")
>             self._handle_403_error(e)
>             return False
299,364c340,349
< # --- Logger Setup ---
< # A simple class to adapt the config dict to what setup_logger expects
< class UnanimousLoggerConfig:
<     def __init__(self, config_dict):
<         # Extract log level from config, default to INFO
<         self.LOG_LEVEL = config_dict.get("log_level", "INFO").upper()
< 
<         # Construct log file path from constants defined in the script
<         log_filename = config_dict.get("log_filename", "wb.log")
<         self.LOG_FILE_PATH = os.path.join(LOG_DIRECTORY, log_filename)
< 
<         # Pass color codes
<         self.NEON_BLUE = NEON_BLUE
<         self.RESET = RESET
< 
< # Create a temporary basic logger for the initial config loading
< temp_logger = logging.getLogger("config_loader")
< temp_logger.setLevel(logging.INFO)
< if not temp_logger.handlers:
<     temp_logger.addHandler(logging.StreamHandler(sys.stdout))
< 
< # Load the main configuration using the temporary logger
< config = load_config(CONFIG_FILE, temp_logger)
< 
< # Create the config object for the unanimous logger
< logger_config = UnanimousLoggerConfig(config)
< 
< # Set up the main application logger using the loaded configuration
< logger = setup_logger(logger_config, log_name="wb", json_log_file="wb.json.log")
< # --- End Logger Setup ---
< 
< 
< 
< 
< # --- API Interaction ---
< def create_session() -> requests.Session:
<     """Create a requests session with retry logic."""
<     session = requests.Session()
<     retries = Retry(
<         total=MAX_API_RETRIES,
<         backoff_factor=RETRY_DELAY_SECONDS,
<         status_forcelist=[429, 500, 502, 503, 504],
<         allowed_methods=frozenset(["GET", "POST"]),
<     )
<     session.mount("https://", HTTPAdapter(max_retries=retries))
<     return session
< 
< 
< def generate_signature(payload: str, api_secret: str) -> str:
<     """Generate a Bybit API signature."""
<     return hmac.new(api_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
< 
< 
< def bybit_request(
<     method: Literal["GET", "POST"],
<     endpoint: str,
<     params: dict | None = None,
<     signed: bool = False,
<     logger: logging.Logger | None = None,
< ) -> dict | None:
<     """Send a request to the Bybit API."""
<     if logger is None:
<         raise ValueError("Logger must be provided to bybit_request")
<     session = create_session()
<     url = f"{BASE_URL}{endpoint}"
<     headers = {"Content-Type": "application/json"}
---
>     def get_positions(self, symbol: str | None = None) -> dict | None:
>         if not self.enabled: return None
>         try:
>             params = {"category": self.category}
>             if symbol: params["symbol"] = symbol
>             return self.session.get_positions(**params)
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}get_positions exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
366,370c351,357
<     if signed:
<         if not API_KEY or not API_SECRET:
<             logger.error(
<                 f"{NEON_RED}API_KEY or API_SECRET not set for signed request.{RESET}"
<             )
---
>     def get_wallet_balance(self, coin: str = "USDT") -> dict | None:
>         if not self.enabled: return None
>         try:
>             return self.session.get_wallet_balance(accountType=self.cfg["execution"].get("account_type", "UNIFIED"), coin=coin)
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}get_wallet_balance exception: {e}{RESET}")
>             self._handle_403_error(e)
373,374c360,369
<         timestamp = str(int(time.time() * 1000))
<         recv_window = "20000"  # Standard recommended receive window
---
>     def place_order(self, **kwargs) -> dict | None:
>         if not self.enabled: return None
>         try:
>             resp = self.session.place_order(**kwargs)
>             self._log_api("place_order", resp)
>             return resp
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}place_order exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
376,414c371,382
<         if method == "GET":
<             # For GET, params should be part of the query string and param_str is timestamp + API_KEY + recv_window + query_string
<             query_string = urllib.parse.urlencode(params) if params else ""
<             param_str = timestamp + API_KEY + recv_window + query_string
<             signature = generate_signature(param_str, API_SECRET)
<             headers.update(
<                 {
<                     "X-BAPI-API-KEY": API_KEY,
<                     "X-BAPI-TIMESTAMP": timestamp,
<                     "X-BAPI-SIGN": signature,
<                     "X-BAPI-RECV-WINDOW": recv_window,
<                 }
<             )
<             logger.debug(f"GET Request: {url}?{query_string}")
<             response = session.get(
<                 url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
<             )
<         else:  # POST
<             # For POST, params should be JSON stringified and param_str is timestamp + API_KEY + recv_window + json_params
<             json_params = json.dumps(params) if params else ""
<             param_str = timestamp + API_KEY + recv_window + json_params
<             signature = generate_signature(param_str, API_SECRET)
<             headers.update(
<                 {
<                     "X-BAPI-API-KEY": API_KEY,
<                     "X-BAPI-TIMESTAMP": timestamp,
<                     "X-BAPI-SIGN": signature,
<                     "X-BAPI-RECV-WINDOW": recv_window,
<                 }
<             )
<             logger.debug(f"POST Request: {url} with payload {json_params}")
<             response = session.post(
<                 url, json=params, headers=headers, timeout=REQUEST_TIMEOUT
<             )
<     else:
<         logger.debug(f"Public Request: {url} with params {params}")
<         response = session.get(
<             url, params=params, headers=headers, timeout=REQUEST_TIMEOUT
<         )
---
>     def fetch_current_price(self, symbol: str) -> Decimal | None:
>         if not self.enabled: return None
>         try:
>             response = self.session.get_tickers(category="linear", symbol=symbol)
>             if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
>                 return Decimal(response["result"]["list"][0]["lastPrice"])
>             self.logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
>             return None
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}fetch_current_price exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
416,422c384,390
<     try:
<         response.raise_for_status()
<         data = response.json()
<         if data.get("retCode") != 0:
<             logger.error(
<                 f"{NEON_RED}Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')}){RESET}"
<             )
---
>     def fetch_instrument_info(self, symbol: str) -> dict | None:
>         if not self.enabled: return None
>         try:
>             response = self.session.get_instruments_info(category="linear", symbol=symbol)
>             if response and response.get("retCode") == 0 and response.get("result", {}).get("list"):
>                 return response["result"]["list"][0]
>             self.logger.warning(f"{NEON_YELLOW}Could not fetch instrument info for {symbol}.{RESET}")
424,493c392,447
<         return data
<     except requests.exceptions.HTTPError as e:
<         logger.error(
<             f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}"
<         )
<     except requests.exceptions.ConnectionError as e:
<         logger.error(f"{NEON_RED}Connection Error: {e}{RESET}")
<     except requests.exceptions.Timeout:
<         logger.error(
<             f"{NEON_RED}Request timed out after {REQUEST_TIMEOUT} seconds.{RESET}"
<         )
<     except requests.exceptions.RequestException as e:
<         logger.error(f"{NEON_RED}Request Exception: {e}{RESET}")
<     except json.JSONDecodeError:
<         logger.error(
<             f"{NEON_RED}Failed to decode JSON response: {response.text}{RESET}"
<         )
<     return None
< 
< 
< def fetch_current_price(symbol: str, logger: logging.Logger) -> Decimal | None:
<     """Fetch the current market price for a symbol."""
<     endpoint = "/v5/market/tickers"
<     params = {"category": "linear", "symbol": symbol}
<     response = bybit_request("GET", endpoint, params, logger=logger)
<     if response and response["result"] and response["result"]["list"]:
<         price = Decimal(response["result"]["list"][0]["lastPrice"])
<         logger.debug(f"Fetched current price for {symbol}: {price}")
<         return price
<     logger.warning(f"{NEON_YELLOW}Could not fetch current price for {symbol}.{RESET}")
<     return None
< 
< 
< def fetch_klines(
<     symbol: str, interval: str, limit: int, logger: logging.Logger
< ) -> pd.DataFrame | None:
<     """Fetch kline data for a symbol and interval."""
<     endpoint = "/v5/market/kline"
<     params = {
<         "category": "linear",
<         "symbol": symbol,
<         "interval": interval,
<         "limit": limit,
<     }
<     response = bybit_request("GET", endpoint, params, logger=logger)
<     if response and response["result"] and response["result"]["list"]:
<         df = pd.DataFrame(
<             response["result"]["list"],
<             columns=[
<                 "start_time",
<                 "open",
<                 "high",
<                 "low",
<                 "close",
<                 "volume",
<                 "turnover",
<             ],
<         )
<         df["start_time"] = pd.to_datetime(
<             df["start_time"].astype(int), unit="ms", utc=True
<         ).dt.tz_convert(TIMEZONE)
<         for col in ["open", "high", "low", "close", "volume", "turnover"]:
<             df[col] = pd.to_numeric(df[col], errors="coerce")
<         df.set_index("start_time", inplace=True)
<         df.sort_index(inplace=True)
< 
<         if df.empty:
<             logger.warning(
<                 f"{NEON_YELLOW}Fetched klines for {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
<             )
---
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}fetch_instrument_info exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
> 
>     def fetch_klines(self, symbol: str, interval: str, limit: int) -> pd.DataFrame | None:
>         if not self.enabled: return None
>         try:
>             params = {"category": "linear", "symbol": symbol, "interval": interval, "limit": limit}
>             response = self.session.get_kline(**params)
>             if response and response.get("result", {}).get("list"):
>                 df = pd.DataFrame(response["result"]["list"], columns=["start_time", "open", "high", "low", "close", "volume", "turnover"])
>                 df["start_time"] = pd.to_datetime(df["start_time"].astype(int), unit="ms", utc=True).dt.tz_convert(TIMEZONE)
>                 for col in ["open", "high", "low", "close", "volume", "turnover"]:
>                     df[col] = pd.to_numeric(df[col], errors="coerce")
>                 df.set_index("start_time", inplace=True)
>                 df.sort_index(inplace=True)
>                 return df if not df.empty else None
>             self.logger.warning(f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}.{RESET}")
>             return None
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}fetch_klines exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
> 
>     def fetch_orderbook(self, symbol: str, limit: int) -> dict | None:
>         if not self.enabled: return None
>         try:
>             response = self.session.get_orderbook(category="linear", symbol=symbol, limit=limit)
>             if response and response.get("result"):
>                 return response["result"]
>             self.logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
>             return None
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}fetch_orderbook exception: {e}{RESET}")
>             self._handle_403_error(e)
>             return None
> 
>     def batch_place_orders(self, requests: list[dict]) -> dict | None:
>         if not self.enabled: return None
>         try:
>             resp = self.session.batch_place_order(category=self.category, request=requests)
>             self._log_api("batch_place_order", resp)
>             return resp
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}batch_place_orders exception: {e}{RESET}")
>             return None
> 
>     def cancel_by_link_id(self, symbol: str, order_link_id: str) -> dict | None:
>         if not self.enabled: return None
>         try:
>             resp = self.session.cancel_order(category=self.category, symbol=symbol, orderLinkId=order_link_id)
>             self._log_api("cancel_by_link_id", resp)
>             return resp
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}cancel_by_link_id exception: {e}{RESET}")
496,513c450,456
<         logger.debug(f"Fetched {len(df)} {interval} klines for {symbol}.")
<         return df
<     logger.warning(
<         f"{NEON_YELLOW}Could not fetch klines for {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
<     )
<     return None
< 
< 
< def fetch_orderbook(symbol: str, limit: int, logger: logging.Logger) -> dict | None:
<     """Fetch orderbook data for a symbol."""
<     endpoint = "/v5/market/orderbook"
<     params = {"category": "linear", "symbol": symbol, "limit": limit}
<     response = bybit_request("GET", endpoint, params, logger=logger)
<     if response and response["result"]:
<         logger.debug(f"Fetched orderbook for {symbol} with limit {limit}.")
<         return response["result"]
<     logger.warning(f"{NEON_YELLOW}Could not fetch orderbook for {symbol}.{RESET}")
<     return None
---
>     def get_executions(self, symbol: str, start_time_ms: int, limit: int) -> dict | None:
>         if not self.enabled: return None
>         try:
>             return self.session.get_executions(category=self.category, symbol=symbol, startTime=start_time_ms, limit=limit)
>         except pybit.exceptions.FailedRequestError as e:
>             self.logger.error(f"{NEON_RED}get_executions exception: {e}{RESET}")
>             return None
514a458,479
> # --- Utilities for execution layer ---
> def build_partial_tp_targets(side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal, total_qty: Decimal, cfg: dict, qty_step: Decimal) -> list[dict]:
>     ex = cfg["execution"]
>     tps = ex["tp_scheme"]["targets"]
>     price_prec = cfg["trade_management"]["price_precision"]
>     out = []
>     for i, t in enumerate(tps, start=1):
>         qty = round_qty(total_qty * Decimal(str(t["size_pct"])), qty_step)
>         if qty <= 0: continue
>         if ex["tp_scheme"]["mode"] == "atr_multiples":
>             price = (entry_price + atr_value * Decimal(str(t["atr_multiple"]))) if side == "BUY" else (entry_price - atr_value * Decimal(str(t["atr_multiple"])))
>         else:
>             price = (entry_price * (1 + Decimal(str(t.get("percent", 1))) / 100)) if side == "BUY" else (entry_price * (1 - Decimal(str(t.get("percent", 1))) / 100))
>         tif = t.get("tif", ex.get("default_time_in_force"))
>         if tif == "GoodTillCancel": tif = "GTC"
>         out.append({
>             "name": t.get("name", f"TP{i}"), "price": round_price(price, price_prec), "qty": qty,
>             "order_type": t.get("order_type", "Limit"), "tif": tif,
>             "post_only": bool(t.get("post_only", ex.get("post_only_default", False))),
>             "link_id_suffix": f"tp{i}",
>         })
>     return out
518,521c483
<     """Manages open positions, stop-loss, and take-profit levels."""
< 
<     def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str):
<         """Initializes the PositionManager."""
---
>     def __init__(self, config: dict[str, Any], logger: logging.Logger, symbol: str, pybit_client: "PybitTradingClient | None" = None):
525c487
<         self.open_positions: list[dict] = []  # Stores active positions
---
>         self.open_positions: list[dict] = []
529a492,514
>         self.qty_step = None
>         self.pybit = pybit_client
>         self.live = bool(config.get("execution", {}).get("use_pybit", False))
>         self._update_precision_from_exchange()
> 
>     def _update_precision_from_exchange(self):
>         if not self.pybit or not self.pybit.enabled:
>             self.logger.warning(f"Pybit client not enabled. Using config precision for {self.symbol}.")
>             return
>         info = self.pybit.fetch_instrument_info(self.symbol)
>         if info:
>             if "lotSizeFilter" in info:
>                 self.qty_step = Decimal(str(info["lotSizeFilter"].get("qtyStep")))
>                 if not self.qty_step.is_zero():
>                     self.order_precision = abs(self.qty_step.as_tuple().exponent)
>                 self.logger.info(f"Updated qty_step: {self.qty_step}, order_precision: {self.order_precision}")
>             if "priceFilter" in info:
>                 tick_size = Decimal(str(info["priceFilter"].get("tickSize")))
>                 if not tick_size.is_zero():
>                     self.price_precision = abs(tick_size.as_tuple().exponent)
>                 self.logger.info(f"Updated price_precision: {self.price_precision}")
>         else:
>             self.logger.warning(f"Could not fetch precision for {self.symbol}. Using config values.")
532,542c517,522
<         """Fetch current account balance (simplified for simulation)."""
<         # In a real bot, this would query the exchange.
<         # For simulation, use configured account balance.
<         # Example API call for real balance (needs authentication):
<         # endpoint = "/v5/account/wallet-balance"
<         # params = {"accountType": "UNIFIED"} # Or "CONTRACT" depending on account type
<         # response = bybit_request("GET", endpoint, params, signed=True, logger=self.logger)
<         # if response and response["result"] and response["result"]["list"]:
<         #     for coin_balance in response["result"]["list"][0]["coin"]:
<         #         if coin_balance["coin"] == "USDT": # Assuming USDT as base currency
<         #             return Decimal(coin_balance["walletBalance"])
---
>         if self.live and self.pybit and self.pybit.enabled:
>             resp = self.pybit.get_wallet_balance(coin="USDT")
>             if resp and self.pybit._ok(resp) and resp.get("result", {}).get("list"):
>                 for coin_balance in resp["result"]["list"][0]["coin"]:
>                     if coin_balance["coin"] == "USDT":
>                         return Decimal(coin_balance["walletBalance"])
545,551c525,526
<     def _calculate_order_size(
<         self, current_price: Decimal, atr_value: Decimal
<     ) -> Decimal:
<         """Calculate order size based on risk per trade and ATR."""
<         if not self.trade_management_enabled:
<             return Decimal("0")
< 
---
>     def _calculate_order_size(self, current_price: Decimal, atr_value: Decimal, conviction: float = 1.0) -> Decimal:
>         if not self.trade_management_enabled: return Decimal("0")
553,561c528,531
<         risk_per_trade_percent = (
<             Decimal(str(self.config["trade_management"]["risk_per_trade_percent"]))
<             / 100
<         )
<         stop_loss_atr_multiple = Decimal(
<             str(self.config["trade_management"]["stop_loss_atr_multiple"])
<         )
< 
<         risk_amount = account_balance * risk_per_trade_percent
---
>         base_risk_pct = Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
>         risk_pct = base_risk_pct * Decimal(str(np.clip(0.5 + conviction, 0.5, 1.5)))
>         stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
>         risk_amount = account_balance * risk_pct
563d532
< 
565,567c534
<             self.logger.warning(
<                 f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
<             )
---
>             self.logger.warning(f"{NEON_YELLOW}Stop loss distance is zero. Cannot calculate order size.{RESET}")
568a536,537
>         order_qty = (risk_amount / stop_loss_distance) / current_price
>         return round_qty(order_qty, self.qty_step) if self.qty_step else order_qty.quantize(Decimal(f"1e-{self.order_precision}"), rounding=ROUND_DOWN)
570,595c539,546
<         # Order size in USD value
<         order_value = risk_amount / stop_loss_distance
<         # Convert to quantity of the asset (e.g., BTC)
<         order_qty = order_value / current_price
< 
<         # Round order_qty to appropriate precision for the symbol
<         precision_str = "0." + "0" * (self.order_precision - 1) + "1"
<         order_qty = order_qty.quantize(Decimal(precision_str), rounding=ROUND_DOWN)
< 
<         self.logger.info(
<             f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
<         )
<         return order_qty
< 
<     def open_position(
<         self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal
<     ) -> dict | None:
<         """Open a new position if conditions allow.
< 
<         Returns the new position details or None.
<         """
<         if not self.trade_management_enabled:
<             self.logger.info(
<                 f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
<             )
<             return None
---
>     def open_position(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal, conviction: float) -> dict | None:
>         if self.live and self.pybit and self.pybit.enabled:
>             positions_resp = self.pybit.get_positions(self.symbol)
>             if positions_resp and self.pybit._ok(positions_resp):
>                 pos_list = positions_resp.get("result", {}).get("list", [])
>                 if any(p.get("size") and Decimal(p.get("size")) > 0 for p in pos_list):
>                     self.logger.warning(f"{NEON_YELLOW}Exchange position exists, aborting new position.{RESET}")
>                     return None
597,600c548,549
<         if len(self.open_positions) >= self.max_open_positions:
<             self.logger.info(
<                 f"{NEON_YELLOW}[{self.symbol}] Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
<             )
---
>         if not self.trade_management_enabled or len(self.open_positions) >= self.max_open_positions:
>             self.logger.info(f"{NEON_YELLOW}Cannot open new position (max reached or disabled).{RESET}")
603c552
<         order_qty = self._calculate_order_size(current_price, atr_value)
---
>         order_qty = self._calculate_order_size(current_price, atr_value, conviction)
605,607c554
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}"
<             )
---
>             self.logger.warning(f"{NEON_YELLOW}Order quantity is zero. Cannot open position.{RESET}")
610,624c557,558
<         stop_loss_atr_multiple = Decimal(
<             str(self.config["trade_management"]["stop_loss_atr_multiple"])
<         )
<         take_profit_atr_multiple = Decimal(
<             str(self.config["trade_management"]["take_profit_atr_multiple"])
<         )
< 
<         if signal == "BUY":
<             stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
<             take_profit = current_price + (atr_value * take_profit_atr_multiple)
<         else:  # SELL
<             stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
<             take_profit = current_price - (atr_value * take_profit_atr_multiple)
< 
<         price_precision_str = "0." + "0" * (self.price_precision - 1) + "1"
---
>         stop_loss = self._compute_stop_loss_price(signal, current_price, atr_value)
>         take_profit = self._calculate_take_profit_price(signal, current_price, atr_value)
627,640c561,564
<             "entry_time": datetime.now(TIMEZONE),
<             "symbol": self.symbol,
<             "side": signal,
<             "entry_price": current_price.quantize(
<                 Decimal(price_precision_str), rounding=ROUND_DOWN
<             ),
<             "qty": order_qty,
<             "stop_loss": stop_loss.quantize(
<                 Decimal(price_precision_str), rounding=ROUND_DOWN
<             ),
<             "take_profit": take_profit.quantize(
<                 Decimal(price_precision_str), rounding=ROUND_DOWN
<             ),
<             "status": "OPEN",
---
>             "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": signal,
>             "entry_price": round_price(current_price, self.price_precision), "qty": order_qty,
>             "stop_loss": stop_loss, "take_profit": round_price(take_profit, self.price_precision),
>             "status": "OPEN", "link_prefix": f"wgx_{int(time.time()*1000)}", "adds": 0,
641a566,601
> 
>         if self.live and self.pybit and self.pybit.enabled:
>             entry_link = f"{position['link_prefix']}_entry"
>             resp = self.pybit.place_order(
>                 category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit(signal),
>                 orderType="Market", qty=self.pybit._q(order_qty), orderLinkId=entry_link,
>             )
>             if not self.pybit._ok(resp):
>                 self.logger.error(f"{NEON_RED}Live entry failed. Simulating only.{RESET}")
>             else:
>                 self.logger.info(f"{NEON_GREEN}Live entry submitted: {entry_link}{RESET}")
>                 if self.config["execution"]["tpsl_mode"] == "Partial":
>                     targets = build_partial_tp_targets(signal, position["entry_price"], atr_value, order_qty, self.config, self.qty_step)
>                     for t in targets:
>                         payload = {
>                             "symbol": self.symbol, "side": self.pybit._side_to_bybit("SELL" if signal == "BUY" else "BUY"),
>                             "orderType": t["order_type"], "qty": self.pybit._q(t["qty"]), "timeInForce": t["tif"],
>                             "reduceOnly": True, "positionIdx": self.pybit._pos_idx(signal),
>                             "orderLinkId": f"{position['link_prefix']}_{t['link_id_suffix']}", "category": self.pybit.category,
>                         }
>                         if t["order_type"] == "Limit": payload["price"] = self.pybit._q(t["price"])
>                         if t.get("post_only"): payload["isPostOnly"] = True
>                         resp_tp = self.pybit.place_order(**payload)
>                         if resp_tp and resp_tp.get("retCode") == 0: self.logger.info(f"{NEON_GREEN}Placed individual TP target: {payload.get('orderLinkId')}{RESET}")
>                         else: self.logger.error(f"{NEON_RED}Failed to place TP target: {payload.get('orderLinkId')}. Error: {resp_tp.get('retMsg') if resp_tp else 'No response'}{RESET}")
> 
>                 if self.config["execution"]["sl_scheme"]["use_conditional_stop"]:
>                     sl_link = f"{position['link_prefix']}_sl"
>                     sresp = self.pybit.place_order(
>                         category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit("SELL" if signal == "BUY" else "BUY"),
>                         orderType=self.config["execution"]["sl_scheme"]["stop_order_type"], qty=self.pybit._q(order_qty),
>                         reduceOnly=True, orderLinkId=sl_link, triggerPrice=self.pybit._q(stop_loss),
>                         triggerDirection=(2 if signal == "BUY" else 1), orderFilter="Stop",
>                     )
>                     if self.pybit._ok(sresp): self.logger.info(f"{NEON_GREEN}Conditional stop placed at {stop_loss}.{RESET}")
> 
643c603
<         self.logger.info(f"{NEON_GREEN}[{self.symbol}] Opened {signal} position: {position}{RESET}")
---
>         self.logger.info(f"{NEON_GREEN}Opened {signal} position (simulated): {position}{RESET}")
646,653c606,607
<     def manage_positions(
<         self, current_price: Decimal, performance_tracker: Any
<     ) -> None:
<         """Check and manage all open positions (SL/TP).
< 
<         In a real bot, this would interact with exchange orders.
<         """
<         if not self.trade_management_enabled or not self.open_positions:
---
>     def manage_positions(self, current_price: Decimal, performance_tracker: Any):
>         if self.live or not self.trade_management_enabled or not self.open_positions:
655d608
< 
657,664c610,611
<         for i, position in enumerate(self.open_positions):
<             if position["status"] == "OPEN":
<                 side = position["side"]
<                 entry_price = position["entry_price"]
<                 stop_loss = position["stop_loss"]
<                 take_profit = position["take_profit"]
<                 qty = position["qty"]
< 
---
>         for i, pos in enumerate(self.open_positions):
>             if pos["status"] == "OPEN":
666,682c613,616
<                 close_price = Decimal("0")
< 
<                 if side == "BUY":
<                     if current_price <= stop_loss:
<                         closed_by = "STOP_LOSS"
<                         close_price = current_price
<                     elif current_price >= take_profit:
<                         closed_by = "TAKE_PROFIT"
<                         close_price = current_price
<                 elif side == "SELL":  # Added explicit check for SELL
<                     if current_price >= stop_loss:
<                         closed_by = "STOP_LOSS"
<                         close_price = current_price
<                     elif current_price <= take_profit:
<                         closed_by = "TAKE_PROFIT"
<                         close_price = current_price
< 
---
>                 if pos["side"] == "BUY" and current_price <= pos["stop_loss"]: closed_by = "STOP_LOSS"
>                 elif pos["side"] == "BUY" and current_price >= pos["take_profit"]: closed_by = "TAKE_PROFIT"
>                 elif pos["side"] == "SELL" and current_price >= pos["stop_loss"]: closed_by = "STOP_LOSS"
>                 elif pos["side"] == "SELL" and current_price <= pos["take_profit"]: closed_by = "TAKE_PROFIT"
684,690c618,621
<                     position["status"] = "CLOSED"
<                     position["exit_time"] = datetime.now(TIMEZONE)
<                     position["exit_price"] = close_price.quantize(
<                         Decimal("0." + "0" * (self.price_precision - 1) + "1"),
<                         rounding=ROUND_DOWN,
<                     )
<                     position["closed_by"] = closed_by
---
>                     pos.update({"status": "CLOSED", "exit_time": datetime.now(TIMEZONE), "exit_price": current_price, "closed_by": closed_by})
>                     pnl = ((current_price - pos["entry_price"]) * pos["qty"]) if pos["side"] == "BUY" else ((pos["entry_price"] - current_price) * pos["qty"])
>                     performance_tracker.record_trade(pos, pnl)
>                     self.logger.info(f"{NEON_PURPLE}Closed {pos['side']} by {closed_by}. PnL: {pnl:.2f}{RESET}")
692,708c623
< 
<                     pnl = (
<                         (close_price - entry_price) * qty
<                         if side == "BUY"
<                         else (entry_price - close_price) * qty
<                     )
<                     performance_tracker.record_trade(position, pnl)
<                     self.logger.info(
<                         f"{NEON_PURPLE}[{self.symbol}] Closed {side} position by {closed_by}: {position}. PnL: {pnl.normalize():.2f}{RESET}"
<                     )
< 
<         # Remove closed positions
<         self.open_positions = [
<             pos
<             for i, pos in enumerate(self.open_positions)
<             if i not in positions_to_close
<         ]
---
>         self.open_positions = [p for i, p in enumerate(self.open_positions) if i not in positions_to_close]
711d625
<         """Return a list of currently open positions."""
713a628,677
>     def _compute_stop_loss_price(self, side: Literal["BUY", "SELL"], entry_price: Decimal, atr_value: Decimal) -> Decimal:
>         ex = self.config["execution"]
>         sch = ex["sl_scheme"]
>         price_prec = self.config["trade_management"]["price_precision"]
>         tick_size = Decimal(f"1e-{price_prec}")
>         buffer = tick_size * 5
>         if sch["type"] == "atr_multiple":
>             sl = (entry_price - atr_value * Decimal(str(sch["atr_multiple"]))) if side == "BUY" else (entry_price + atr_value * Decimal(str(sch["atr_multiple"])))
>         else:
>             sl = (entry_price * (1 - Decimal(str(sch["percent"])) / 100)) if side == "BUY" else (entry_price * (1 + Decimal(str(sch["percent"])) / 100))
>         sl_with_buffer = sl - buffer if side == "BUY" else sl + buffer
>         return round_price(sl_with_buffer, price_prec)
> 
>     def _calculate_take_profit_price(self, signal: Literal["BUY", "SELL"], current_price: Decimal, atr_value: Decimal) -> Decimal:
>         tp_mult = Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))
>         tp = (current_price + (atr_value * tp_mult)) if signal == "BUY" else (current_price - (atr_value * tp_mult))
>         return round_price(tp, self.price_precision)
> 
>     def trail_stop(self, pos: dict, current_price: Decimal, atr_value: Decimal):
>         if pos.get('status') != 'OPEN' or self.live: return
>         atr_mult = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
>         side = pos["side"]
>         pos["best_price"] = pos.get("best_price", pos["entry_price"])
>         if side == "BUY":
>             pos["best_price"] = max(pos["best_price"], current_price)
>             new_sl = round_price(pos["best_price"] - atr_mult * atr_value, self.price_precision)
>             if new_sl > pos["stop_loss"]: pos["stop_loss"] = new_sl
>         else: # SELL
>             pos["best_price"] = min(pos["best_price"], current_price)
>             new_sl = round_price(pos["best_price"] + atr_mult * atr_value, self.price_precision)
>             if new_sl < pos["stop_loss"]: pos["stop_loss"] = new_sl
> 
>     def try_pyramid(self, current_price: Decimal, atr_value: Decimal):
>         if not self.trade_management_enabled or not self.open_positions or self.live: return
>         py_cfg = self.config.get("pyramiding", {})
>         if not py_cfg.get("enabled", False): return
>         for pos in self.open_positions:
>             if pos.get("status") != "OPEN": continue
>             adds = pos.get("adds", 0)
>             if adds >= int(py_cfg.get("max_adds", 0)): continue
>             step = Decimal(str(py_cfg.get("step_atr", 0.7))) * atr_value
>             target = pos["entry_price"] + step * (adds + 1) if pos["side"] == "BUY" else pos["entry_price"] - step * (adds + 1)
>             if (pos["side"] == "BUY" and current_price >= target) or (pos["side"] == "SELL" and current_price <= target):
>                 add_qty = round_qty(pos['qty'] * Decimal(str(py_cfg.get("size_pct_of_initial", 0.5))), self.qty_step or Decimal("0.0001"))
>                 if add_qty > 0:
>                     total_cost = (pos['qty'] * pos['entry_price']) + (add_qty * current_price)
>                     pos['qty'] += add_qty
>                     pos['entry_price'] = total_cost / pos['qty']
>                     pos["adds"] = adds + 1
>                     self.logger.info(f"{NEON_GREEN}Pyramiding add #{pos['adds']} qty={add_qty}. New avg price: {pos['entry_price']:.2f}{RESET}")
715c679
< # --- Performance Tracking ---
---
> # --- Performance Tracking & Sync ---
717,718d680
<     """Tracks and reports trading performance."""
< 
720d681
<         """Initializes the PerformanceTracker."""
723a685,686
>         self.gross_profit = Decimal("0")
>         self.gross_loss = Decimal("0")
725a689,690
>         self.peak_pnl = Decimal("0")
>         self.max_drawdown = Decimal("0")
727,740c692,693
<     def record_trade(self, position: dict, pnl: Decimal) -> None:
<         """Record a completed trade."""
<         trade_record = {
<             "entry_time": position["entry_time"],
<             "exit_time": position["exit_time"],
<             "symbol": position["symbol"],
<             "side": position["side"],
<             "entry_price": position["entry_price"],
<             "exit_price": position["exit_price"],
<             "qty": position["qty"],
<             "pnl": pnl,
<             "closed_by": position["closed_by"],
<         }
<         self.trades.append(trade_record)
---
>     def record_trade(self, position: dict, pnl: Decimal):
>         self.trades.append({**position, "pnl": pnl})
743a697
>             self.gross_profit += pnl
746,749c700,714
<         self.logger.info(
<             f"{NEON_CYAN}[{position['symbol']}] Trade recorded. Current Total PnL: {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
<         )
<         self.logger.info("Trade recorded", extra=trade_record)
---
>             self.gross_loss += abs(pnl)
>         if self.total_pnl > self.peak_pnl: self.peak_pnl = self.total_pnl
>         drawdown = self.peak_pnl - self.total_pnl
>         if drawdown > self.max_drawdown: self.max_drawdown = drawdown
>         self.logger.info(f"{NEON_CYAN}Trade recorded. PnL: {pnl:.4f}. Total PnL: {self.total_pnl:.4f}{RESET}")
> 
>     def day_pnl(self) -> Decimal:
>         if not self.trades: return Decimal("0")
>         today = datetime.now(TIMEZONE).date()
>         pnl = Decimal("0")
>         for t in self.trades:
>             et = t.get("exit_time") or t.get("entry_time")
>             if et and et.date() == today:
>                 pnl += Decimal(str(t.get("pnl", "0")))
>         return pnl
752d716
<         """Return a summary of all recorded trades."""
755c719,721
< 
---
>         profit_factor = self.gross_profit / self.gross_loss if self.gross_loss > 0 else Decimal("inf")
>         avg_win = self.gross_profit / self.wins if self.wins > 0 else Decimal("0")
>         avg_loss = self.gross_loss / self.losses if self.losses > 0 else Decimal("0")
757,761c723,727
<             "total_trades": total_trades,
<             "total_pnl": self.total_pnl,
<             "wins": self.wins,
<             "losses": self.losses,
<             "win_rate": f"{win_rate:.2f}%",
---
>             "total_trades": total_trades, "total_pnl": f"{self.total_pnl:.4f}",
>             "gross_profit": f"{self.gross_profit:.4f}", "gross_loss": f"{self.gross_loss:.4f}",
>             "profit_factor": f"{profit_factor:.2f}", "max_drawdown": f"{self.max_drawdown:.4f}",
>             "wins": self.wins, "losses": self.losses, "win_rate": f"{win_rate:.2f}%",
>             "avg_win": f"{avg_win:.4f}", "avg_loss": f"{avg_loss:.4f}",
764,770c730,733
< 
< # --- Alert System ---
< class AlertSystem:
<     """Handles sending alerts for critical events."""
< 
<     def __init__(self, logger: logging.Logger):
<         """Initializes the AlertSystem."""
---
> class ExchangeExecutionSync:
>     def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager, pt: PerformanceTracker):
>         self.symbol = symbol
>         self.pybit = pybit
771a735,754
>         self.cfg = cfg
>         self.pm = pm
>         self.pt = pt
>         self.last_exec_time_ms = int(time.time() * 1000) - 5 * 60 * 1000
> 
>     def _is_ours(self, link_id: str | None) -> bool:
>         if not link_id: return False
>         if not self.cfg["execution"]["live_sync"]["only_track_linked"]: return True
>         return link_id.startswith("wgx_")
> 
>     def _compute_be_price(self, side: str, entry_price: Decimal, atr_value: Decimal) -> Decimal:
>         be_cfg = self.cfg["execution"]["breakeven_after_tp1"]
>         off_type = str(be_cfg.get("offset_type", "atr")).lower()
>         off_val = Decimal(str(be_cfg.get("offset_value", 0)))
>         if off_type == "atr": adj = atr_value * off_val
>         elif off_type == "percent": adj = entry_price * (off_val / Decimal("100"))
>         else: adj = off_val
>         lock_adj = entry_price * (Decimal(str(be_cfg.get("lock_in_min_percent", 0))) / Decimal("100"))
>         be = entry_price + max(adj, lock_adj) if side == "BUY" else entry_price - max(adj, lock_adj)
>         return round_price(be, self.pm.price_precision)
773,781c756,773
<     def send_alert(self, message: str, level: Literal["INFO", "WARNING", "ERROR"]) -> None:
<         """Send an alert (currently logs it)."""
<         if level == "INFO":
<             self.logger.info(f"{NEON_BLUE}ALERT: {message}{RESET}")
<         elif level == "WARNING":
<             self.logger.warning(f"{NEON_YELLOW}ALERT: {message}{RESET}")
<         elif level == "ERROR":
<             self.logger.error(f"{NEON_RED}ALERT: {message}{RESET}")
<         # In a real bot, integrate with Telegram, Discord, Email etc.
---
>     def _move_stop_to_breakeven(self, open_pos: dict, atr_value: Decimal):
>         if not self.cfg["execution"]["breakeven_after_tp1"].get("enabled", False): return
>         try:
>             entry, side = Decimal(str(open_pos["entry_price"])), open_pos["side"]
>             new_sl = self._compute_be_price(side, entry, atr_value)
>             link_prefix = open_pos.get("link_prefix")
>             old_sl_link = f"{link_prefix}_sl" if link_prefix else None
>             if old_sl_link: self.pybit.cancel_by_link_id(self.symbol, old_sl_link)
>             new_sl_link = f"{link_prefix}_sl_be" if link_prefix else f"wgx_{int(time.time()*1000)}_sl_be"
>             sresp = self.pybit.place_order(
>                 category=self.pybit.category, symbol=self.symbol, side=self.pybit._side_to_bybit("SELL" if side == "BUY" else "BUY"),
>                 orderType=self.cfg["execution"]["sl_scheme"]["stop_order_type"], qty=self.pybit._q(open_pos["qty"]),
>                 reduceOnly=True, orderLinkId=new_sl_link, triggerPrice=self.pybit._q(new_sl),
>                 triggerDirection=(2 if side == "BUY" else 1), orderFilter="Stop",
>             )
>             if self.pybit._ok(sresp): self.logger.info(f"{NEON_GREEN}Moved SL to breakeven at {new_sl}.{RESET}")
>         except (pybit.exceptions.FailedRequestError, Exception) as e:
>             self.logger.error(f"{NEON_RED}Breakeven move exception: {e}{RESET}")
782a775,805
>     def poll(self):
>         if not (self.pybit and self.pybit.enabled): return
>         try:
>             resp = self.pybit.get_executions(self.symbol, self.last_exec_time_ms, self.cfg["execution"]["live_sync"]["max_exec_fetch"])
>             if not self.pybit._ok(resp): return
>             rows = resp.get("result", {}).get("list", [])
>             rows.sort(key=lambda r: int(r.get("execTime", 0)))
>             for r in rows:
>                 link = r.get("orderLinkId")
>                 if not self._is_ours(link): continue
>                 ts_ms = int(r.get("execTime", 0))
>                 self.last_exec_time_ms = max(self.last_exec_time_ms, ts_ms + 1)
>                 tag = "ENTRY" if link.endswith("_entry") else ("SL" if "_sl" in link else ("TP" if "_tp" in link else "UNKNOWN"))
>                 open_pos = next((p for p in self.pm.open_positions if p.get("status") == "OPEN"), None)
>                 if tag in ("TP", "SL") and open_pos:
>                     is_reduce = (open_pos["side"] == "BUY" and r.get("side") == "Sell") or (open_pos["side"] == "SELL" and r.get("side") == "Buy")
>                     if is_reduce:
>                         exec_qty, exec_price = Decimal(str(r.get("execQty", "0"))), Decimal(str(r.get("execPrice", "0")))
>                         pnl = ((exec_price - open_pos["entry_price"]) * exec_qty) if open_pos["side"] == "BUY" else ((open_pos["entry_price"] - exec_price) * exec_qty)
>                         self.pt.record_trade({"exit_time": datetime.fromtimestamp(ts_ms / 1000, tz=TIMEZONE), "exit_price": exec_price, "qty": exec_qty, "closed_by": tag, **open_pos}, pnl)
>                         remaining = Decimal(str(open_pos["qty"])) - exec_qty
>                         open_pos["qty"] = max(remaining, Decimal("0"))
>                         if remaining <= 0:
>                             open_pos.update({"status": "CLOSED", "exit_time": datetime.fromtimestamp(ts_ms / 1000, tz=TIMEZONE), "exit_price": exec_price, "closed_by": tag})
>                             self.logger.info(f"{NEON_PURPLE}Position fully closed by {tag}.{RESET}")
>                     if tag == "TP" and link.endswith("_tp1"):
>                         atr_val = Decimal(str(self.cfg.get("_last_atr", "0.1")))
>                         self._move_stop_to_breakeven(open_pos, atr_val)
>             self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"]
>         except (pybit.exceptions.FailedRequestError, Exception) as e:
>             self.logger.error(f"{NEON_RED}Execution sync error: {e}{RESET}")
784,786c807,844
< # --- Trading Analysis (Upgraded with Ehlers SuperTrend and more) ---
< class TradingAnalyzer:
<     """Analyzes trading data and generates signals with MTF, Ehlers SuperTrend, and other new indicators."""
---
> class PositionHeartbeat:
>     def __init__(self, symbol: str, pybit: PybitTradingClient, logger: logging.Logger, cfg: dict, pm: PositionManager):
>         self.symbol = symbol
>         self.pybit = pybit
>         self.logger = logger
>         self.cfg = cfg
>         self.pm = pm
>         self._last_ms = 0
> 
>     def tick(self):
>         hb_cfg = self.cfg["execution"]["live_sync"]["heartbeat"]
>         if not (hb_cfg.get("enabled", True) and self.pybit and self.pybit.enabled): return
>         now_ms = int(time.time() * 1000)
>         if now_ms - self._last_ms < int(hb_cfg.get("interval_ms", 5000)): return
>         self._last_ms = now_ms
>         try:
>             resp = self.pybit.get_positions(self.symbol)
>             if not self.pybit._ok(resp): return
>             lst = (resp.get("result", {}) or {}).get("list", [])
>             net_qty = sum(Decimal(p.get("size", "0")) * (1 if p.get("side") == "Buy" else -1) for p in lst)
>             local = next((p for p in self.pm.open_positions if p.get("status") == "OPEN"), None)
>             if net_qty == 0 and local:
>                 local.update({"status": "CLOSED", "closed_by": "HEARTBEAT_SYNC"})
>                 self.logger.info(f"{NEON_PURPLE}Heartbeat: Closed local position (exchange flat).{RESET}")
>                 self.pm.open_positions = [p for p in self.pm.open_positions if p.get("status") == "OPEN"]
>             elif net_qty != 0 and not local:
>                 avg_price = Decimal(lst[0].get("avgPrice", "0")) if lst else Decimal("0")
>                 side = "BUY" if net_qty > 0 else "SELL"
>                 synt = {
>                     "entry_time": datetime.now(TIMEZONE), "symbol": self.symbol, "side": side,
>                     "entry_price": round_price(avg_price, self.pm.price_precision),
>                     "qty": round_qty(abs(net_qty), self.pm.qty_step), "status": "OPEN",
>                     "link_prefix": f"hb_{int(time.time()*1000)}",
>                 }
>                 self.pm.open_positions.append(synt)
>                 self.logger.info(f"{NEON_YELLOW}Heartbeat: Created synthetic local position.{RESET}")
>         except (pybit.exceptions.FailedRequestError, Exception) as e:
>             self.logger.error(f"{NEON_RED}Heartbeat error: {e}{RESET}")
788,795c846,848
<     def __init__(
<         self,
<         df: pd.DataFrame,
<         config: dict[str, Any],
<         logger: logging.Logger,
<         symbol: str,
<     ):
<         """Initializes the TradingAnalyzer."""
---
> # --- Trading Analysis ---
> class TradingAnalyzer:
>     def __init__(self, df: pd.DataFrame, config: dict[str, Any], logger: logging.Logger, symbol: str):
800,801c853
<         self.indicator_values: dict[str, float | str | Decimal] = {}
<         self.fib_levels: dict[str, Decimal] = {}
---
>         self.indicator_values: dict[str, Any] = {}
804,806d855
<         self._last_signal_ts = 0 # Initialize last signal timestamp
<         self._last_signal_score = 0.0 # Initialize last signal score
< 
808,810c857
<             self.logger.warning(
<                 f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
<             )
---
>             self.logger.warning(f"{NEON_YELLOW}TradingAnalyzer initialized with empty DataFrame.{RESET}")
812d858
< 
814,815d859
<         if self.config["indicators"].get("fibonacci_levels", False):
<             self.calculate_fibonacci_levels()
817,825c861
<     def _safe_calculate(
<         self, func: callable, name: str, min_data_points: int = 0, *args, **kwargs
<     ) -> Any | None:
<         """Safely calculate indicators and log errors, with min_data_points check."""
<         if len(self.df) < min_data_points:
<             self.logger.debug(
<                 f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
<             )
<             return None
---
>     def _safe_calculate(self, func: callable, name: str, *args, **kwargs) -> Any | None:
827,843c863,871
<             result = func(*args, **kwargs)
<             if (
<                 result is None
<                 or (isinstance(result, pd.Series) and result.empty)
<                 or (
<                     isinstance(result, tuple)
<                     and all(
<                         r is None or (isinstance(r, pd.Series) and r.empty)
<                         for r in result
<                     )
<                 )
<             ):
<                 self.logger.warning(
<                     f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
<                 )
<                 return None
<             return result
---
>             if 'df' in func.__code__.co_varnames and func.__code__.co_varnames[0] == 'df':
>                 result = func(self.df, *args, **kwargs)
>             else:
>                 result = func(*args, **kwargs)
>             is_empty = (result is None or (isinstance(result, pd.Series) and result.empty) or
>                         (isinstance(result, tuple) and all(r is None or (isinstance(r, pd.Series) and r.empty) for r in result)))
>             if is_empty:
>                 self.logger.warning(f"{NEON_YELLOW}[{self.symbol}] Indicator '{name}' returned empty.{RESET}")
>             return result if not is_empty else None
845,847c873
<             self.logger.error(
<                 f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}{RESET}"
<             )
---
>             self.logger.error(f"{NEON_RED}[{self.symbol}] Error calculating '{name}': {e}{RESET}")
851,852c877
<         """Calculate all enabled technical indicators, including Ehlers SuperTrend."""
<         self.logger.debug(f"[{self.symbol}] Calculating technical indicators...")
---
>         self.logger.debug(f"[{self.symbol}] Calculating all technical indicators...")
856d880
<         # SMA
858,864c882,883
<             self.df["SMA_10"] = self._safe_calculate(
<                 lambda: self.df["close"].rolling(window=isd["sma_short_period"]).mean(),
<                 "SMA_10",
<                 min_data_points=isd["sma_short_period"],
<             )
<             if self.df["SMA_10"] is not None:
<                 self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
---
>             self.df["SMA_10"] = self._safe_calculate(indicators.calculate_sma, "SMA_10", period=isd["sma_short_period"])
>             if self.df["SMA_10"] is not None and not self.df["SMA_10"].empty: self.indicator_values["SMA_10"] = self.df["SMA_10"].iloc[-1]
866,874c885,886
<             self.df["SMA_Long"] = self._safe_calculate(
<                 lambda: self.df["close"].rolling(window=isd["sma_long_period"]).mean(),
<                 "SMA_Long",
<                 min_data_points=isd["sma_long_period"],
<             )
<             if self.df["SMA_Long"] is not None:
<                 self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]
< 
<         # EMA
---
>             self.df["SMA_Long"] = self._safe_calculate(indicators.calculate_sma, "SMA_Long", period=isd["sma_long_period"])
>             if self.df["SMA_Long"] is not None and not self.df["SMA_Long"].empty: self.indicator_values["SMA_Long"] = self.df["SMA_Long"].iloc[-1]
876,907c888,894
<             self.df["EMA_Short"] = self._safe_calculate(
<                 lambda: self.df["close"]
<                 .ewm(span=isd["ema_short_period"], adjust=False)
<                 .mean(),
<                 "EMA_Short",
<                 min_data_points=isd["ema_short_period"],
<             )
<             self.df["EMA_Long"] = self._safe_calculate(
<                 lambda: self.df["close"]
<                 .ewm(span=isd["ema_long_period"], adjust=False)
<                 .mean(),
<                 "EMA_Long",
<                 min_data_points=isd["ema_long_period"],
<             )
<             if self.df["EMA_Short"] is not None:
<                 self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
<             if self.df["EMA_Long"] is not None:
<                 self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]
< 
<         # ATR
<         self.df["TR"] = self._safe_calculate(
<             self.calculate_true_range, "TR", min_data_points=MIN_DATA_POINTS_TR
<         )
<         self.df["ATR"] = self._safe_calculate(
<             lambda: self.df["TR"].ewm(span=isd["atr_period"], adjust=False).mean(),
<             "ATR",
<             min_data_points=isd["atr_period"],
<         )
<         if self.df["ATR"] is not None:
<             self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]
< 
<         # RSI
---
>             self.df["EMA_Short"] = self._safe_calculate(indicators.calculate_ema, "EMA_Short", period=isd["ema_short_period"])
>             self.df["EMA_Long"] = self._safe_calculate(indicators.calculate_ema, "EMA_Long", period=isd["ema_long_period"])
>             if self.df["EMA_Short"] is not None and not self.df["EMA_Short"].empty: self.indicator_values["EMA_Short"] = self.df["EMA_Short"].iloc[-1]
>             if self.df["EMA_Long"] is not None and not self.df["EMA_Long"].empty: self.indicator_values["EMA_Long"] = self.df["EMA_Long"].iloc[-1]
>         self.df["TR"] = self._safe_calculate(indicators.calculate_true_range, "TR")
>         self.df["ATR"] = self._safe_calculate(indicators.calculate_atr, "ATR", period=isd["atr_period"])
>         if self.df["ATR"] is not None and not self.df["ATR"].empty: self.indicator_values["ATR"] = self.df["ATR"].iloc[-1]
909,918c896,897
<             self.df["RSI"] = self._safe_calculate(
<                 self.calculate_rsi,
<                 "RSI",
<                 min_data_points=isd["rsi_period"] + 1,
<                 period=isd["rsi_period"],
<             )
<             if self.df["RSI"] is not None:
<                 self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
< 
<         # Stochastic RSI
---
>             self.df["RSI"] = self._safe_calculate(indicators.calculate_rsi, "RSI", period=isd["rsi_period"])
>             if self.df["RSI"] is not None and not self.df["RSI"].empty: self.indicator_values["RSI"] = self.df["RSI"].iloc[-1]
920,939c899,901
<             stoch_rsi_k, stoch_rsi_d = self._safe_calculate(
<                 self.calculate_stoch_rsi,
<                 "StochRSI",
<                 min_data_points=isd["stoch_rsi_period"]
<                 + isd["stoch_d_period"]
<                 + isd["stoch_k_period"],
<                 period=isd["stoch_rsi_period"],
<                 k_period=isd["stoch_k_period"],
<                 d_period=isd["stoch_d_period"],
<             )
<             if stoch_rsi_k is not None:
<                 self.df["StochRSI_K"] = stoch_rsi_k
<             if stoch_rsi_d is not None:
<                 self.df["StochRSI_D"] = stoch_rsi_d
<             if stoch_rsi_k is not None:
<                 self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
<             if stoch_rsi_d is not None:
<                 self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]
< 
<         # Bollinger Bands
---
>             stoch_rsi_k, stoch_rsi_d = self._safe_calculate(indicators.calculate_stoch_rsi, "StochRSI", period=isd["stoch_rsi_period"], k_period=isd["stoch_k_period"], d_period=isd["stoch_d_period"])
>             if stoch_rsi_k is not None and not stoch_rsi_k.empty: self.df["StochRSI_K"] = stoch_rsi_k; self.indicator_values["StochRSI_K"] = stoch_rsi_k.iloc[-1]
>             if stoch_rsi_d is not None and not stoch_rsi_d.empty: self.df["StochRSI_D"] = stoch_rsi_d; self.indicator_values["StochRSI_D"] = stoch_rsi_d.iloc[-1]
941,961c903,906
<             bb_upper, bb_middle, bb_lower = self._safe_calculate(
<                 self.calculate_bollinger_bands,
<                 "BollingerBands",
<                 min_data_points=isd["bollinger_bands_period"],
<                 period=isd["bollinger_bands_period"],
<                 std_dev=isd["bollinger_bands_std_dev"],
<             )
<             if bb_upper is not None:
<                 self.df["BB_Upper"] = bb_upper
<             if bb_middle is not None:
<                 self.df["BB_Middle"] = bb_middle
<             if bb_lower is not None:
<                 self.df["BB_Lower"] = bb_lower
<             if bb_upper is not None:
<                 self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
<             if bb_middle is not None:
<                 self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
<             if bb_lower is not None:
<                 self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]
< 
<         # CCI
---
>             bb_upper, bb_middle, bb_lower = self._safe_calculate(indicators.calculate_bollinger_bands, "BollingerBands", period=isd["bollinger_bands_period"], std_dev=isd["bollinger_bands_std_dev"])
>             if bb_upper is not None and not bb_upper.empty: self.df["BB_Upper"] = bb_upper; self.indicator_values["BB_Upper"] = bb_upper.iloc[-1]
>             if bb_middle is not None and not bb_middle.empty: self.df["BB_Middle"] = bb_middle; self.indicator_values["BB_Middle"] = bb_middle.iloc[-1]
>             if bb_lower is not None and not bb_lower.empty: self.df["BB_Lower"] = bb_lower; self.indicator_values["BB_Lower"] = bb_lower.iloc[-1]
963,972c908,909
<             self.df["CCI"] = self._safe_calculate(
<                 self.calculate_cci,
<                 "CCI",
<                 min_data_points=isd["cci_period"],
<                 period=isd["cci_period"],
<             )
<             if self.df["CCI"] is not None:
<                 self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]
< 
<         # Williams %R
---
>             self.df["CCI"] = self._safe_calculate(indicators.calculate_cci, "CCI", period=isd["cci_period"])
>             if self.df["CCI"] is not None and not self.df["CCI"].empty: self.indicator_values["CCI"] = self.df["CCI"].iloc[-1]
974,983c911,912
<             self.df["WR"] = self._safe_calculate(
<                 self.calculate_williams_r,
<                 "WR",
<                 min_data_points=isd["williams_r_period"],
<                 period=isd["williams_r_period"],
<             )
<             if self.df["WR"] is not None:
<                 self.indicator_values["WR"] = self.df["WR"].iloc[-1]
< 
<         # MFI
---
>             self.df["WR"] = self._safe_calculate(indicators.calculate_williams_r, "WR", period=isd["williams_r_period"])
>             if self.df["WR"] is not None and not self.df["WR"].empty: self.indicator_values["WR"] = self.df["WR"].iloc[-1]
985,994c914,915
<             self.df["MFI"] = self._safe_calculate(
<                 self.calculate_mfi,
<                 "MFI",
<                 min_data_points=isd["mfi_period"] + 1,
<                 period=isd["mfi_period"],
<             )
<             if self.df["MFI"] is not None:
<                 self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]
< 
<         # OBV
---
>             self.df["MFI"] = self._safe_calculate(indicators.calculate_mfi, "MFI", period=isd["mfi_period"])
>             if self.df["MFI"] is not None and not self.df["MFI"].empty: self.indicator_values["MFI"] = self.df["MFI"].iloc[-1]
996,1011c917,919
<             obv_val, obv_ema = self._safe_calculate(
<                 self.calculate_obv,
<                 "OBV",
<                 min_data_points=isd["obv_ema_period"],
<                 ema_period=isd["obv_ema_period"],
<             )
<             if obv_val is not None:
<                 self.df["OBV"] = obv_val
<             if obv_ema is not None:
<                 self.df["OBV_EMA"] = obv_ema
<             if obv_val is not None:
<                 self.indicator_values["OBV"] = obv_val.iloc[-1]
<             if obv_ema is not None:
<                 self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]
< 
<         # CMF
---
>             obv_val, obv_ema = self._safe_calculate(indicators.calculate_obv, "OBV", ema_period=isd["obv_ema_period"])
>             if obv_val is not None and not obv_val.empty: self.df["OBV"] = obv_val; self.indicator_values["OBV"] = obv_val.iloc[-1]
>             if obv_ema is not None and not obv_ema.empty: self.df["OBV_EMA"] = obv_ema; self.indicator_values["OBV_EMA"] = obv_ema.iloc[-1]
1013,1024c921,922
<             cmf_val = self._safe_calculate(
<                 self.calculate_cmf,
<                 "CMF",
<                 min_data_points=isd["cmf_period"],
<                 period=isd["cmf_period"],
<             )
<             if cmf_val is not None:
<                 self.df["CMF"] = cmf_val
<             if cmf_val is not None:
<                 self.indicator_values["CMF"] = cmf_val.iloc[-1]
< 
<         # Ichimoku Cloud
---
>             cmf_val = self._safe_calculate(indicators.calculate_cmf, "CMF", period=isd["cmf_period"])
>             if cmf_val is not None and not cmf_val.empty: self.df["CMF"] = cmf_val; self.indicator_values["CMF"] = cmf_val.iloc[-1]
1026,1064c924,929
<             tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = (
<                 self._safe_calculate(
<                     self.calculate_ichimoku_cloud,
<                     "IchimokuCloud",
<                     min_data_points=max(
<                         isd["ichimoku_tenkan_period"],
<                         isd["ichimoku_kijun_period"],
<                         isd["ichimoku_senkou_span_b_period"],
<                     )
<                     + isd["ichimoku_chikou_span_offset"],
<                     tenkan_period=isd["ichimoku_tenkan_period"],
<                     kijun_period=isd["ichimoku_kijun_period"],
<                     senkou_span_b_period=isd["ichimoku_senkou_span_b_period"],
<                     chikou_span_offset=isd["ichimoku_chikou_span_offset"],
<                 )
<             )
<             if tenkan_sen is not None:
<                 self.df["Tenkan_Sen"] = tenkan_sen
<             if kijun_sen is not None:
<                 self.df["Kijun_Sen"] = kijun_sen
<             if senkou_span_a is not None:
<                 self.df["Senkou_Span_A"] = senkou_span_a
<             if senkou_span_b is not None:
<                 self.df["Senkou_Span_B"] = senkou_span_b
<             if chikou_span is not None:
<                 self.df["Chikou_Span"] = chikou_span
< 
<             if tenkan_sen is not None:
<                 self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
<             if kijun_sen is not None:
<                 self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
<             if senkou_span_a is not None:
<                 self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
<             if senkou_span_b is not None:
<                 self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
<             if chikou_span is not None:
<                 self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]
< 
<         # PSAR
---
>             tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span = self._safe_calculate(indicators.calculate_ichimoku_cloud, "IchimokuCloud", tenkan_period=isd["ichimoku_tenkan_period"], kijun_period=isd["ichimoku_kijun_period"], senkou_span_b_period=isd["ichimoku_senkou_span_b_period"], chikou_span_offset=isd["ichimoku_chikou_span_offset"])
>             if tenkan_sen is not None and not tenkan_sen.empty: self.df["Tenkan_Sen"] = tenkan_sen; self.indicator_values["Tenkan_Sen"] = tenkan_sen.iloc[-1]
>             if kijun_sen is not None and not kijun_sen.empty: self.df["Kijun_Sen"] = kijun_sen; self.indicator_values["Kijun_Sen"] = kijun_sen.iloc[-1]
>             if senkou_span_a is not None and not senkou_span_a.empty: self.df["Senkou_Span_A"] = senkou_span_a; self.indicator_values["Senkou_Span_A"] = senkou_span_a.iloc[-1]
>             if senkou_span_b is not None and not senkou_span_b.empty: self.df["Senkou_Span_B"] = senkou_span_b; self.indicator_values["Senkou_Span_B"] = senkou_span_b.iloc[-1]
>             if chikou_span is not None and not chikou_span.empty: self.df["Chikou_Span"] = chikou_span; self.indicator_values["Chikou_Span"] = chikou_span.fillna(0).iloc[-1]
1066,1082c931,933
<             psar_val, psar_dir = self._safe_calculate(
<                 self.calculate_psar,
<                 "PSAR",
<                 min_data_points=MIN_DATA_POINTS_PSAR,
<                 acceleration=isd["psar_acceleration"],
<                 max_acceleration=isd["psar_max_acceleration"],
<             )
<             if psar_val is not None:
<                 self.df["PSAR_Val"] = psar_val
<             if psar_dir is not None:
<                 self.df["PSAR_Dir"] = psar_dir
<             if psar_val is not None:
<                 self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
<             if psar_dir is not None:
<                 self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
< 
<         # VWAP (requires volume and turnover, which are in df)
---
>             psar_val, psar_dir = self._safe_calculate(indicators.calculate_psar, "PSAR", acceleration=isd["psar_acceleration"], max_acceleration=isd["psar_max_acceleration"])
>             if psar_val is not None and not psar_val.empty: self.df["PSAR_Val"] = psar_val; self.indicator_values["PSAR_Val"] = psar_val.iloc[-1]
>             if psar_dir is not None and not psar_dir.empty: self.df["PSAR_Dir"] = psar_dir; self.indicator_values["PSAR_Dir"] = psar_dir.iloc[-1]
1084,1090c935,936
<             self.df["VWAP"] = self._safe_calculate(
<                 self.calculate_vwap, "VWAP", min_data_points=1
<             )
<             if self.df["VWAP"] is not None:
<                 self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]
< 
<         # --- Ehlers SuperTrend Calculation ---
---
>             self.df["VWAP"] = self._safe_calculate(indicators.calculate_vwap, "VWAP")
>             if self.df["VWAP"] is not None and not self.df["VWAP"].empty: self.indicator_values["VWAP"] = self.df["VWAP"].iloc[-1]
1092,1126c938,941
<             st_fast_result = self._safe_calculate(
<                 self.calculate_ehlers_supertrend,
<                 "EhlersSuperTrendFast",
<                 min_data_points=isd["ehlers_fast_period"] * 3,
<                 period=isd["ehlers_fast_period"],
<                 multiplier=isd["ehlers_fast_multiplier"],
<             )
<             if st_fast_result is not None and not st_fast_result.empty:
<                 self.df["st_fast_dir"] = st_fast_result["direction"]
<                 self.df["st_fast_val"] = st_fast_result["supertrend"]
<                 self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[
<                     -1
<                 ]
<                 self.indicator_values["ST_Fast_Val"] = st_fast_result[
<                     "supertrend"
<                 ].iloc[-1]
< 
<             st_slow_result = self._safe_calculate(
<                 self.calculate_ehlers_supertrend,
<                 "EhlersSuperTrendSlow",
<                 min_data_points=isd["ehlers_slow_period"] * 3,
<                 period=isd["ehlers_slow_period"],
<                 multiplier=isd["ehlers_slow_multiplier"],
<             )
<             if st_slow_result is not None and not st_slow_result.empty:
<                 self.df["st_slow_dir"] = st_slow_result["direction"]
<                 self.df["st_slow_val"] = st_slow_result["supertrend"]
<                 self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[
<                     -1
<                 ]
<                 self.indicator_values["ST_Slow_Val"] = st_slow_result[
<                     "supertrend"
<                 ].iloc[-1]
< 
<         # MACD
---
>             st_fast_result = self._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendFast", period=isd["ehlers_fast_period"], multiplier=isd["ehlers_fast_multiplier"])
>             if st_fast_result is not None and not st_fast_result.empty: self.df["st_fast_dir"] = st_fast_result["direction"]; self.df["st_fast_val"] = st_fast_result["supertrend"]; self.indicator_values["ST_Fast_Dir"] = st_fast_result["direction"].iloc[-1]; self.indicator_values["ST_Fast_Val"] = st_fast_result["supertrend"].iloc[-1]
>             st_slow_result = self._safe_calculate(indicators.calculate_ehlers_supertrend, "EhlersSuperTrendSlow", period=isd["ehlers_slow_period"], multiplier=isd["ehlers_slow_multiplier"])
>             if st_slow_result is not None and not st_slow_result.empty: self.df["st_slow_dir"] = st_slow_result["direction"]; self.df["st_slow_val"] = st_slow_result["supertrend"]; self.indicator_values["ST_Slow_Dir"] = st_slow_result["direction"].iloc[-1]; self.indicator_values["ST_Slow_Val"] = st_slow_result["supertrend"].iloc[-1]
1128,1149c943,946
<             macd_line, signal_line, histogram = self._safe_calculate(
<                 self.calculate_macd,
<                 "MACD",
<                 min_data_points=isd["macd_slow_period"] + isd["macd_signal_period"],
<                 fast_period=isd["macd_fast_period"],
<                 slow_period=isd["macd_slow_period"],
<                 signal_period=isd["macd_signal_period"],
<             )
<             if macd_line is not None:
<                 self.df["MACD_Line"] = macd_line
<             if signal_line is not None:
<                 self.df["MACD_Signal"] = signal_line
<             if histogram is not None:
<                 self.df["MACD_Hist"] = histogram
<             if macd_line is not None:
<                 self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
<             if signal_line is not None:
<                 self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
<             if histogram is not None:
<                 self.indicator_values["MACD_Hist"] = histogram.iloc[-1]
< 
<         # ADX
---
>             macd_line, signal_line, histogram = self._safe_calculate(indicators.calculate_macd, "MACD", fast_period=isd["macd_fast_period"], slow_period=isd["macd_slow_period"], signal_period=isd["macd_signal_period"])
>             if macd_line is not None and not macd_line.empty: self.df["MACD_Line"] = macd_line; self.indicator_values["MACD_Line"] = macd_line.iloc[-1]
>             if signal_line is not None and not signal_line.empty: self.df["MACD_Signal"] = signal_line; self.indicator_values["MACD_Signal"] = signal_line.iloc[-1]
>             if histogram is not None and not histogram.empty: self.df["MACD_Hist"] = histogram; self.indicator_values["MACD_Hist"] = histogram.iloc[-1]
1151,1171c948,951
<             adx_val, plus_di, minus_di = self._safe_calculate(
<                 self.calculate_adx,
<                 "ADX",
<                 min_data_points=isd["adx_period"] * 2,
<                 period=isd["adx_period"],
<             )
<             if adx_val is not None:
<                 self.df["ADX"] = adx_val
<             if plus_di is not None:
<                 self.df["PlusDI"] = plus_di
<             if minus_di is not None:
<                 self.df["MinusDI"] = minus_di
<             if adx_val is not None:
<                 self.indicator_values["ADX"] = adx_val.iloc[-1]
<             if plus_di is not None:
<                 self.indicator_values["PlusDI"] = plus_di.iloc[-1]
<             if minus_di is not None:
<                 self.indicator_values["MinusDI"] = minus_di.iloc[-1]
< 
<         # --- New Indicators ---
<         # Volatility Index
---
>             adx_val, plus_di, minus_di = self._safe_calculate(indicators.calculate_adx, "ADX", period=isd["adx_period"])
>             if adx_val is not None and not adx_val.empty: self.df["ADX"] = adx_val; self.indicator_values["ADX"] = adx_val.iloc[-1]
>             if plus_di is not None and not plus_di.empty: self.df["PlusDI"] = plus_di; self.indicator_values["PlusDI"] = plus_di.iloc[-1]
>             if minus_di is not None and not minus_di.empty: self.df["MinusDI"] = minus_di; self.indicator_values["MinusDI"] = minus_di.iloc[-1]
1173,1184c953,954
<             self.df["Volatility_Index"] = self._safe_calculate(
<                 self.calculate_volatility_index,
<                 "Volatility_Index",
<                 min_data_points=isd["volatility_index_period"],
<                 period=isd["volatility_index_period"],
<             )
<             if self.df["Volatility_Index"] is not None:
<                 self.indicator_values["Volatility_Index"] = self.df[
<                     "Volatility_Index"
<                 ].iloc[-1]
< 
<         # VWMA
---
>             self.df["Volatility_Index"] = self._safe_calculate(indicators.calculate_volatility_index, "Volatility_Index", period=isd["volatility_index_period"])
>             if self.df["Volatility_Index"] is not None and not self.df["Volatility_Index"].empty: self.indicator_values["Volatility_Index"] = self.df["Volatility_Index"].iloc[-1]
1186,1195c956,957
<             self.df["VWMA"] = self._safe_calculate(
<                 self.calculate_vwma,
<                 "VWMA",
<                 min_data_points=isd["vwma_period"],
<                 period=isd["vwma_period"],
<             )
<             if self.df["VWMA"] is not None:
<                 self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]
< 
<         # Volume Delta
---
>             self.df["VWMA"] = self._safe_calculate(indicators.calculate_vwma, "VWMA", period=isd["vwma_period"])
>             if self.df["VWMA"] is not None and not self.df["VWMA"].empty: self.indicator_values["VWMA"] = self.df["VWMA"].iloc[-1]
1197,1204c959,960
<             self.df["Volume_Delta"] = self._safe_calculate(
<                 self.calculate_volume_delta,
<                 "Volume_Delta",
<                 min_data_points=isd["volume_delta_period"],
<                 period=isd["volume_delta_period"],
<             )
<             if self.df["Volume_Delta"] is not None:
<                 self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]
---
>             self.df["Volume_Delta"] = self._safe_calculate(indicators.calculate_volume_delta, "Volume_Delta", period=isd["volume_delta_period"])
>             if self.df["Volume_Delta"] is not None and not self.df["Volume_Delta"].empty: self.indicator_values["Volume_Delta"] = self.df["Volume_Delta"].iloc[-1]
1206,1207d961
<         # Final dropna after all indicators are calculated
<         initial_len = len(self.df)
1209,1761c963,964
<         self.df.fillna(0, inplace=True)  # Fill any remaining NaNs in indicator columns
< 
<         if len(self.df) < initial_len:
<             self.logger.debug(
<                 f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
<             )
< 
<         if self.df.empty:
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
<             )
<         else:
<             self.logger.debug(
<                 f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}"
<             )
< 
<     def calculate_true_range(self) -> pd.Series:
<         """Calculate True Range (TR)."""
<         if len(self.df) < MIN_DATA_POINTS_TR:
<             return pd.Series(np.nan, index=self.df.index)
<         high_low = self.df["high"] - self.df["low"]
<         high_prev_close = (self.df["high"] - self.df["close"].shift()).abs()
<         low_prev_close = (self.df["low"] - self.df["close"].shift()).abs()
<         return pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(
<             axis=1
<         )
< 
<     def calculate_super_smoother(self, series: pd.Series, period: int) -> pd.Series:
<         """Apply Ehlers SuperSmoother filter to reduce lag and noise."""
<         if period <= 0 or len(series) < MIN_DATA_POINTS_SMOOTHER:
<             return pd.Series(np.nan, index=series.index)
< 
<         series = pd.to_numeric(series, errors="coerce").dropna()
<         if len(series) < MIN_DATA_POINTS_SMOOTHER:
<             return pd.Series(np.nan, index=series.index)
< 
<         a1 = np.exp(-np.sqrt(2) * np.pi / period)
<         b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / period)
<         c1 = 1 - b1 + a1**2
<         c2 = b1 - 2 * a1**2
<         c3 = a1**2
< 
<         filt = pd.Series(0.0, index=series.index)
<         if len(series) >= 1:
<             filt.iloc[0] = series.iloc[0]
<         if len(series) >= 2:
<             filt.iloc[1] = (series.iloc[0] + series.iloc[1]) / 2
< 
<         for i in range(2, len(series)):
<             filt.iloc[i] = (
<                 (c1 / 2) * (series.iloc[i] + series.iloc[i - 1])
<                 + c2 * filt.iloc[i - 1]
<                 - c3 * filt.iloc[i - 2]
<             )
<         return filt.reindex(self.df.index)
< 
<     def calculate_ehlers_supertrend(
<         self, period: int, multiplier: float
<     ) -> pd.DataFrame | None:
<         """Calculate SuperTrend using Ehlers SuperSmoother for price and volatility."""
<         if len(self.df) < period * 3:
<             self.logger.debug(
<                 f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period*3} bars."
<             )
<             return None
< 
<         df_copy = self.df.copy()
< 
<         hl2 = (df_copy["high"] + df_copy["low"]) / 2
<         smoothed_price = self.calculate_super_smoother(hl2, period)
< 
<         tr = self.calculate_true_range()
<         smoothed_atr = self.calculate_super_smoother(tr, period)
< 
<         df_copy["smoothed_price"] = smoothed_price
<         df_copy["smoothed_atr"] = smoothed_atr
< 
<         if df_copy.empty:
<             self.logger.debug(
<                 f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
<             )
<             return None
< 
<         upper_band = df_copy["smoothed_price"] + multiplier * df_copy["smoothed_atr"]
<         lower_band = df_copy["smoothed_price"] - multiplier * df_copy["smoothed_atr"]
< 
<         direction = pd.Series(0, index=df_copy.index, dtype=int)
<         supertrend = pd.Series(np.nan, index=df_copy.index)
< 
<         # Find the first valid index after smoothing
<         first_valid_idx_val = smoothed_price.first_valid_index()
<         if first_valid_idx_val is None:
<             return None
<         first_valid_idx = df_copy.index.get_loc(first_valid_idx_val)
<         if first_valid_idx >= len(df_copy):
<             return None
< 
<         # Initialize the first valid supertrend value based on the first valid close price relative to bands
<         if df_copy["close"].iloc[first_valid_idx] > upper_band.iloc[first_valid_idx]:
<             direction.iloc[first_valid_idx] = 1
<             supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
<         elif (
<             df_copy["close"].iloc[first_valid_idx] < lower_band.iloc[first_valid_idx]
<         ):
<             direction.iloc[first_valid_idx] = -1
<             supertrend.iloc[first_valid_idx] = upper_band.iloc[first_valid_idx]
<         else:  # Price is within bands, initialize with lower band, neutral direction
<             direction.iloc[first_valid_idx] = 0
<             supertrend.iloc[first_valid_idx] = lower_band.iloc[first_valid_idx]
< 
<         for i in range(first_valid_idx + 1, len(df_copy)):
<             prev_direction = direction.iloc[i - 1]
<             prev_supertrend = supertrend.iloc[i - 1]
<             curr_close = df_copy["close"].iloc[i]
< 
<             if prev_direction == 1:  # Previous was an UP trend
<                 # If current close drops below the prev_supertrend, flip to DOWN
<                 if curr_close < prev_supertrend:
<                     direction.iloc[i] = -1
<                     supertrend.iloc[i] = upper_band.iloc[i]  # New ST is upper band
<                 else:  # Continue UP trend
<                     direction.iloc[i] = 1
<                     # New ST is max of current lower_band and prev_supertrend
<                     supertrend.iloc[i] = max(lower_band.iloc[i], prev_supertrend)
<             elif prev_direction == -1:  # Previous was a DOWN trend
<                 # If current close rises above the prev_supertrend, flip to UP
<                 if curr_close > prev_supertrend:
<                     direction.iloc[i] = 1
<                     supertrend.iloc[i] = lower_band.iloc[i]  # New ST is lower band
<                 else:  # Continue DOWN trend
<                     direction.iloc[i] = -1
<                     # New ST is min of current upper_band and prev_supertrend
<                     supertrend.iloc[i] = min(upper_band.iloc[i], prev_supertrend)
<             else:  # Previous was neutral or initial state (handle explicitly)
<                 if curr_close > upper_band.iloc[i]:
<                     direction.iloc[i] = 1
<                     supertrend.iloc[i] = lower_band.iloc[i]
<                 elif curr_close < lower_band.iloc[i]:
<                     direction.iloc[i] = -1
<                     supertrend.iloc[i] = upper_band.iloc[i]
<                 else:  # Still within bands or undecided, stick to previous or default
<                     direction.iloc[i] = prev_direction  # Maintain previous direction
<                     supertrend.iloc[i] = prev_supertrend  # Maintain previous supertrend
< 
<         result = pd.DataFrame({"supertrend": supertrend, "direction": direction})
<         return result.reindex(self.df.index)
< 
<     def calculate_macd(
<         self, fast_period: int, slow_period: int, signal_period: int
<     ) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Moving Average Convergence Divergence (MACD)."""
<         if len(self.df) < slow_period + signal_period:
<             return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
< 
<         ema_fast = self.df["close"].ewm(span=fast_period, adjust=False).mean()
<         ema_slow = self.df["close"].ewm(span=slow_period, adjust=False).mean()
< 
<         macd_line = ema_fast - ema_slow
<         signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
<         histogram = macd_line - signal_line
< 
<         return macd_line, signal_line, histogram
< 
<     def calculate_rsi(self, period: int) -> pd.Series:
<         """Calculate Relative Strength Index (RSI)."""
<         if len(self.df) <= period:
<             return pd.Series(np.nan, index=self.df.index)
<         delta = self.df["close"].diff()
<         gain = delta.where(delta > 0, 0)
<         loss = -delta.where(delta < 0, 0)
< 
<         avg_gain = gain.ewm(span=period, adjust=False, min_periods=period).mean()
<         avg_loss = loss.ewm(span=period, adjust=False, min_periods=period).mean()
< 
<         # Handle division by zero for rs where avg_loss is 0
<         rs = avg_gain / avg_loss.replace(0, np.nan)
<         rsi = 100 - (100 / (1 + rs))
<         return rsi
< 
<     def calculate_stoch_rsi(
<         self, period: int, k_period: int, d_period: int
<     ) -> tuple[pd.Series, pd.Series]:
<         """Calculate Stochastic RSI."""
<         if len(self.df) <= period:
<             return pd.Series(np.nan, index=self.df.index), pd.Series(
<                 np.nan, index=self.df.index
<             )
<         rsi = self.calculate_rsi(period)
< 
<         lowest_rsi = rsi.rolling(window=period, min_periods=period).min()
<         highest_rsi = rsi.rolling(window=period, min_periods=period).max()
< 
<         # Avoid division by zero if highest_rsi == lowest_rsi
<         denominator = highest_rsi - lowest_rsi
<         denominator[denominator == 0] = np.nan  # Replace 0 with NaN for division
<         stoch_rsi_k_raw = ((rsi - lowest_rsi) / denominator) * 100
<         stoch_rsi_k_raw = stoch_rsi_k_raw.fillna(0).clip(0, 100) # Clip to [0, 100] and fill remaining NaNs with 0
< 
<         stoch_rsi_k = stoch_rsi_k_raw.rolling(
<             window=k_period, min_periods=k_period
<         ).mean().fillna(0)
<         stoch_rsi_d = stoch_rsi_k.rolling(window=d_period, min_periods=d_period).mean().fillna(0)
< 
<         return stoch_rsi_k, stoch_rsi_d
< 
<     def calculate_adx(self, period: int) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Average Directional Index (ADX)."""
<         if len(self.df) < period * 2:
<             return pd.Series(np.nan), pd.Series(np.nan), pd.Series(np.nan)
< 
<         # True Range
<         tr = self.calculate_true_range()
< 
<         # Directional Movement
<         plus_dm = self.df["high"].diff()
<         minus_dm = -self.df["low"].diff()
< 
<         plus_dm_final = pd.Series(0.0, index=self.df.index)
<         minus_dm_final = pd.Series(0.0, index=self.df.index)
< 
<         # Apply +DM and -DM logic
<         for i in range(1, len(self.df)):
<             if plus_dm.iloc[i] > minus_dm.iloc[i] and plus_dm.iloc[i] > 0:
<                 plus_dm_final.iloc[i] = plus_dm.iloc[i]
<             if minus_dm.iloc[i] > plus_dm.iloc[i] and minus_dm.iloc[i] > 0:
<                 minus_dm_final.iloc[i] = minus_dm.iloc[i]
< 
<         # Smoothed True Range, +DM, -DM
<         atr = tr.ewm(span=period, adjust=False).mean()
<         plus_di = (plus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
<         minus_di = (minus_dm_final.ewm(span=period, adjust=False).mean() / atr) * 100
< 
<         # DX
<         di_diff = abs(plus_di - minus_di)
<         di_sum = plus_di + minus_di
<         # Handle division by zero
<         dx = (di_diff / di_sum.replace(0, np.nan)).fillna(0) * 100
< 
<         # ADX
<         adx = dx.ewm(span=period, adjust=False).mean()
< 
<         return adx, plus_di, minus_di
< 
<     def calculate_bollinger_bands(
<         self, period: int, std_dev: float
<     ) -> tuple[pd.Series, pd.Series, pd.Series]:
<         """Calculate Bollinger Bands."""
<         if len(self.df) < period:
<             return (
<                 pd.Series(np.nan, index=self.df.index),
<                 pd.Series(np.nan, index=self.df.index),
<                 pd.Series(np.nan, index=self.df.index),
<             )
<         middle_band = self.df["close"].rolling(window=period, min_periods=period).mean()
<         std = self.df["close"].rolling(window=period, min_periods=period).std()
<         upper_band = middle_band + (std * std_dev)
<         lower_band = middle_band - (std * std_dev)
<         return upper_band, middle_band, lower_band
< 
<     def calculate_vwap(self) -> pd.Series:
<         """Calculate Volume Weighted Average Price (VWAP)."""
<         if self.df.empty:
<             return pd.Series(np.nan, index=self.df.index)
<         typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
<         # Ensure cumulative sum starts from valid data, reindex to original df index
<         cumulative_tp_vol = (typical_price * self.df["volume"]).cumsum()
<         cumulative_vol = self.df["volume"].cumsum()
<         vwap = cumulative_tp_vol / cumulative_vol
<         return vwap.reindex(self.df.index)
< 
<     def calculate_cci(self, period: int) -> pd.Series:
<         """Calculate Commodity Channel Index (CCI)."""
<         if len(self.df) < period:
<             return pd.Series(np.nan, index=self.df.index)
<         tp = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
<         sma_tp = tp.rolling(window=period, min_periods=period).mean()
<         mad = tp.rolling(window=period, min_periods=period).apply(
<             lambda x: np.abs(x - x.mean()).mean(), raw=False
<         )
<         # Handle potential division by zero for mad
<         cci = (tp - sma_tp) / (0.015 * mad.replace(0, np.nan))
<         return cci
< 
<     def calculate_williams_r(self, period: int) -> pd.Series:
<         """Calculate Williams %R."""
<         if len(self.df) < period:
<             return pd.Series(np.nan, index=self.df.index)
<         highest_high = self.df["high"].rolling(window=period, min_periods=period).max()
<         lowest_low = self.df["low"].rolling(window=period, min_periods=period).min()
<         # Handle division by zero
<         denominator = highest_high - lowest_low
<         wr = -100 * ((highest_high - self.df["close"]) / denominator.replace(0, np.nan))
<         return wr
< 
<     def calculate_ichimoku_cloud(
<         self,
<         tenkan_period: int,
<         kijun_period: int,
<         senkou_span_b_period: int,
<         chikou_span_offset: int,
<     ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
<         """Calculate Ichimoku Cloud components."""
<         if (
<             len(self.df)
<             < max(tenkan_period, kijun_period, senkou_span_b_period)
<             + chikou_span_offset
<         ):
<             return (
<                 pd.Series(np.nan),
<                 pd.Series(np.nan),
<                 pd.Series(np.nan),
<                 pd.Series(np.nan),
<                 pd.Series(np.nan),
<             )
< 
<         tenkan_sen = (
<             self.df["high"].rolling(window=tenkan_period).max()
<             + self.df["low"].rolling(window=tenkan_period).min()
<         ) / 2
< 
<         kijun_sen = (
<             self.df["high"].rolling(window=kijun_period).max()
<             + self.df["low"].rolling(window=kijun_period).min()
<         ) / 2
< 
<         senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(kijun_period)
< 
<         senkou_span_b = (
<             (
<                 self.df["high"].rolling(window=senkou_span_b_period).max()
<                 + self.df["low"].rolling(window=senkou_span_b_period).min()
<             )
<             / 2
<         ).shift(kijun_period)
< 
<         chikou_span = self.df["close"].shift(-chikou_span_offset)
< 
<         return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
< 
<     def calculate_mfi(self, period: int) -> pd.Series:
<         """Calculate Money Flow Index (MFI)."""
<         if len(self.df) <= period:
<             return pd.Series(np.nan, index=self.df.index)
<         typical_price = (self.df["high"] + self.df["low"] + self.df["close"]) / 3
<         money_flow = typical_price * self.df["volume"]
< 
<         positive_flow = pd.Series(0.0, index=self.df.index)
<         negative_flow = pd.Series(0.0, index=self.df.index)
< 
<         # Calculate positive and negative money flow
<         # Use vectorized operations where possible
<         price_diff = typical_price.diff()
<         positive_flow = money_flow.where(price_diff > 0, 0)
<         negative_flow = money_flow.where(price_diff < 0, 0)
< 
<         # Rolling sum for period
<         positive_mf_sum = positive_flow.rolling(window=period, min_periods=period).sum()
<         negative_mf_sum = negative_flow.rolling(window=period, min_periods=period).sum()
< 
<         # Avoid division by zero
<         mf_ratio = positive_mf_sum / negative_mf_sum.replace(0, np.nan)
<         mfi = 100 - (100 / (1 + mf_ratio))
<         return mfi
< 
<     def calculate_obv(self, ema_period: int) -> tuple[pd.Series, pd.Series]:
<         """Calculate On-Balance Volume (OBV) and its EMA."""
<         if len(self.df) < MIN_DATA_POINTS_OBV:
<             return pd.Series(np.nan), pd.Series(np.nan)
< 
<         obv = pd.Series(0.0, index=self.df.index)
<         obv_direction = np.sign(self.df["close"].diff().fillna(0))
<         obv = (obv_direction * self.df["volume"]).cumsum()
< 
<         obv_ema = obv.ewm(span=ema_period, adjust=False).mean()
< 
<         return obv, obv_ema
< 
<     def calculate_cmf(self, period: int) -> pd.Series:
<         """Calculate Chaikin Money Flow (CMF)."""
<         if len(self.df) < period:
<             return pd.Series(np.nan)
< 
<         # Money Flow Multiplier (MFM)
<         high_low_range = self.df["high"] - self.df["low"]
<         # Handle division by zero for high_low_range
<         mfm = (
<             (self.df["close"] - self.df["low"]) - (self.df["high"] - self.df["close"])
<         ) / high_low_range.replace(0, np.nan)
<         mfm = mfm.fillna(0)
< 
<         # Money Flow Volume (MFV)
<         mfv = mfm * self.df["volume"]
< 
<         # CMF
<         volume_sum = self.df["volume"].rolling(window=period).sum()
<         # Handle division by zero for volume_sum
<         cmf = mfv.rolling(window=period).sum() / volume_sum.replace(0, np.nan)
<         cmf = cmf.fillna(0)
< 
<         return cmf
< 
<     def calculate_psar(
<         self, acceleration: float, max_acceleration: float
<     ) -> tuple[pd.Series, pd.Series]:
<         """Calculate Parabolic SAR."""
<         if len(self.df) < MIN_DATA_POINTS_PSAR:
<             return pd.Series(np.nan, index=self.df.index), pd.Series(
<                 np.nan, index=self.df.index
<             )
< 
<         psar = self.df["close"].copy()
<         bull = pd.Series(True, index=self.df.index)
<         af = acceleration
<         ep = (
<             self.df["low"].iloc[0]
<             if self.df["close"].iloc[0] < self.df["close"].iloc[1]
<             else self.df["high"].iloc[0]
<         )  # Initial EP depends on first two bars' direction
< 
<         for i in range(1, len(self.df)):
<             prev_bull = bull.iloc[i - 1]
<             prev_psar = psar.iloc[i - 1]
< 
<             # Calculate current PSAR value
<             if prev_bull:  # Bullish trend
<                 psar.iloc[i] = prev_psar + af * (ep - prev_psar)
<             else:  # Bearish trend
<                 psar.iloc[i] = prev_psar - af * (prev_psar - ep)
< 
<             # Check for reversal conditions
<             reverse = False
<             if prev_bull and self.df["low"].iloc[i] < psar.iloc[i]:
<                 bull.iloc[i] = False  # Reverse to bearish
<                 reverse = True
<             elif not prev_bull and self.df["high"].iloc[i] > psar.iloc[i]:
<                 bull.iloc[i] = True  # Reverse to bullish
<                 reverse = True
<             else:
<                 bull.iloc[i] = prev_bull  # Continue previous trend
< 
<             # Update AF and EP
<             if reverse:
<                 af = acceleration
<                 ep = self.df["high"].iloc[i] if bull.iloc[i] else self.df["low"].iloc[i]
<                 # Ensure PSAR does not cross price on reversal
<                 if bull.iloc[i]: # if reversing to bullish, PSAR should be below current low
<                     psar.iloc[i] = min(self.df["low"].iloc[i], self.df["low"].iloc[i-1])
<                 else: # if reversing to bearish, PSAR should be above current high
<                     psar.iloc[i] = max(self.df["high"].iloc[i], self.df["high"].iloc[i-1])
< 
<             elif bull.iloc[i]:  # Continuing bullish
<                 if self.df["high"].iloc[i] > ep:
<                     ep = self.df["high"].iloc[i]
<                     af = min(af + acceleration, max_acceleration)
<                 # Keep PSAR below the lowest low of the last two bars
<                 psar.iloc[i] = min(psar.iloc[i], self.df["low"].iloc[i], self.df["low"].iloc[i-1])
<             else:  # Continuing bearish
<                 if self.df["low"].iloc[i] < ep:
<                     ep = self.df["low"].iloc[i]
<                     af = min(af + acceleration, max_acceleration)
<                 # Keep PSAR above the highest high of the last two bars
<                 psar.iloc[i] = max(psar.iloc[i], self.df["high"].iloc[i], self.df["high"].iloc[i-1])
< 
<         direction = pd.Series(0, index=self.df.index, dtype=int)
<         direction[psar < self.df["close"]] = 1  # Bullish
<         direction[psar > self.df["close"]] = -1  # Bearish
< 
<         return psar, direction
< 
< 
<     def calculate_fibonacci_levels(self) -> None:
<         """Calculate Fibonacci retracement levels based on a recent high-low swing."""
<         window = self.config["indicator_settings"]["fibonacci_window"]
<         if len(self.df) < window:
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}"
<             )
<             return
< 
<         recent_high = self.df["high"].iloc[-window:].max()
<         recent_low = self.df["low"].iloc[-window:].min()
< 
<         diff = recent_high - recent_low
< 
<         if diff <= 0: # Handle cases where high and low are the same or inverted
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}"
<             )
<             return
< 
<         self.fib_levels = {
<             "0.0%": Decimal(str(recent_high)),
<             "23.6%": Decimal(str(recent_high - 0.236 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "38.2%": Decimal(str(recent_high - 0.382 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "50.0%": Decimal(str(recent_high - 0.500 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "61.8%": Decimal(str(recent_high - 0.618 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "78.6%": Decimal(str(recent_high - 0.786 * diff)).quantize(
<                 Decimal("0.00001"), rounding=ROUND_DOWN
<             ),
<             "100.0%": Decimal(str(recent_low)),
<         }
<         self.logger.debug(f"[{self.symbol}] Calculated Fibonacci levels: {self.fib_levels}")
< 
<     def calculate_volatility_index(self, period: int) -> pd.Series:
<         """Calculate a simple Volatility Index based on ATR normalized by price."""
<         if len(self.df) < period or "ATR" not in self.df.columns:
<             return pd.Series(np.nan, index=self.df.index)
< 
<         # ATR is already calculated in _calculate_all_indicators
<         normalized_atr = self.df["ATR"] / self.df["close"]
<         volatility_index = normalized_atr.rolling(window=period).mean()
<         return volatility_index
< 
<     def calculate_vwma(self, period: int) -> pd.Series:
<         """Calculate Volume Weighted Moving Average (VWMA)."""
<         if len(self.df) < period or self.df["volume"].isnull().any():
<             return pd.Series(np.nan, index=self.df.index)
< 
<         # Ensure volume is numeric and not zero
<         valid_volume = self.df["volume"].replace(0, np.nan)
<         pv = self.df["close"] * valid_volume
<         vwma = pv.rolling(window=period).sum() / valid_volume.rolling(
<             window=period
<         ).sum()
<         return vwma
< 
<     def calculate_volume_delta(self, period: int) -> pd.Series:
<         """Calculate Volume Delta, indicating buying vs selling pressure."""
<         if len(self.df) < MIN_DATA_POINTS_VOLATILITY:
<             return pd.Series(np.nan, index=self.df.index)
< 
<         # Approximate buy/sell volume based on close relative to open
<         buy_volume = self.df["volume"].where(self.df["close"] > self.df["open"], 0)
<         sell_volume = self.df["volume"].where(self.df["close"] < self.df["open"], 0)
< 
<         # Rolling sum of buy/sell volume
<         buy_volume_sum = buy_volume.rolling(window=period, min_periods=1).sum()
<         sell_volume_sum = sell_volume.rolling(window=period, min_periods=1).sum()
< 
<         total_volume_sum = buy_volume_sum + sell_volume_sum
<         # Avoid division by zero
<         volume_delta = (buy_volume_sum - sell_volume_sum) / total_volume_sum.replace(
<             0, np.nan
<         )
<         return volume_delta.fillna(0)
---
>         self.df.fillna(0, inplace=True)
>         if self.df.empty: self.logger.warning(f"{NEON_YELLOW}DataFrame empty after indicator calculations.{RESET}")
1764d966
<         """Safely retrieve an indicator value."""
1768d969
<         """Analyze orderbook imbalance."""
1771d971
< 
1774,1777c974
< 
<         if bid_volume + ask_volume == 0:
<             return 0.0
< 
---
>         if bid_volume + ask_volume == 0: return 0.0
1779,1781d975
<         self.logger.debug(
<             f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
<         )
1784,2815c978,997
<     def _get_mtf_trend(self, higher_tf_df: pd.DataFrame, indicator_type: str) -> str:
<         """Determine trend from higher timeframe using specified indicator."""
<         if higher_tf_df.empty:
<             return "UNKNOWN"
< 
<         last_close = higher_tf_df["close"].iloc[-1]
<         period = self.config["mtf_analysis"]["trend_period"]
< 
<         if indicator_type == "sma":
<             if len(higher_tf_df) < period:
<                 self.logger.debug(
<                     f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
<                 )
<                 return "UNKNOWN"
<             sma = (
<                 higher_tf_df["close"]
<                 .rolling(window=period, min_periods=period)
<                 .mean()
<                 .iloc[-1]
<             )
<             if last_close > sma:
<                 return "UP"
<             if last_close < sma:
<                 return "DOWN"
<             return "SIDEWAYS"
<         if indicator_type == "ema":
<             if len(higher_tf_df) < period:
<                 self.logger.debug(
<                     f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
<                 )
<                 return "UNKNOWN"
<             ema = (
<                 higher_tf_df["close"]
<                 .ewm(span=period, adjust=False, min_periods=period)
<                 .mean()
<                 .iloc[-1]
<             )
<             if last_close > ema:
<                 return "UP"
<             if last_close < ema:
<                 return "DOWN"
<             return "SIDEWAYS"
<         if indicator_type == "ehlers_supertrend":
<             temp_analyzer = TradingAnalyzer(
<                 higher_tf_df, self.config, self.logger, self.symbol
<             )
<             st_result = temp_analyzer.calculate_ehlers_supertrend(
<                 period=self.indicator_settings["ehlers_slow_period"],
<                 multiplier=self.indicator_settings["ehlers_slow_multiplier"],
<             )
<             if st_result is not None and not st_result.empty:
<                 st_dir = st_result["direction"].iloc[-1]
<                 if st_dir == 1:
<                     return "UP"
<                 if st_dir == -1:
<                     return "DOWN"
<             return "UNKNOWN"
<         return "UNKNOWN"
< 
<     def generate_trading_signal(
<         self,
<         current_price: Decimal,
<         orderbook_data: dict | None,
<         mtf_trends: dict[str, str],
<     ) -> tuple[str, float, dict]:
<         """Generate a signal using confluence of indicators, including Ehlers SuperTrend.
<         Returns the final signal, the aggregated signal score, and a breakdown of contributions.
<         """
<         signal_score = 0.0
<         signal_breakdown: dict[str, float] = {} # Initialize breakdown dictionary
<         active_indicators = self.config["indicators"]
<         weights = self.weights
<         isd = self.indicator_settings
< 
<         if self.df.empty:
<             self.logger.warning(
<                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
<             )
<             return "HOLD", 0.0, {}
< 
<         current_close = Decimal(str(self.df["close"].iloc[-1]))
<         prev_close = Decimal(
<             str(self.df["close"].iloc[-2]) if len(self.df) > 1 else current_close
<         )
< 
<         # EMA Alignment
<         if active_indicators.get("ema_alignment", False):
<             ema_short = self._get_indicator_value("EMA_Short")
<             ema_long = self._get_indicator_value("EMA_Long")
<             if not pd.isna(ema_short) and not pd.isna(ema_long):
<                 contrib = 0.0
<                 if ema_short > ema_long:
<                     contrib = weights.get("ema_alignment", 0)
<                 elif ema_short < ema_long:
<                     contrib = -weights.get("ema_alignment", 0)
<                 signal_score += contrib
<                 signal_breakdown["EMA_Alignment"] = contrib
< 
<         # SMA Trend Filter
<         if active_indicators.get("sma_trend_filter", False):
<             sma_long = self._get_indicator_value("SMA_Long")
<             if not pd.isna(sma_long):
<                 contrib = 0.0
<                 if current_close > sma_long:
<                     contrib = weights.get("sma_trend_filter", 0)
<                 elif current_close < sma_long:
<                     contrib = -weights.get("sma_trend_filter", 0)
<                 signal_score += contrib
<                 signal_breakdown["SMA_Trend_Filter"] = contrib
< 
<         # Momentum Indicators (RSI, StochRSI, CCI, WR, MFI)
<         if active_indicators.get("momentum", False):
<             momentum_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0)
< 
<             # RSI
<             if active_indicators.get("rsi", False):
<                 rsi = self._get_indicator_value("RSI")
<                 if not pd.isna(rsi):
<                     # Normalize RSI to a -1 to +1 scale
<                     normalized_rsi = (float(rsi) - 50) / 50
<                     contrib = normalized_rsi * momentum_weight * 0.5
<                     signal_score += contrib
<                     signal_breakdown["RSI_Signal"] = contrib
< 
<             # StochRSI Crossover
<             if active_indicators.get("stoch_rsi", False):
<                 stoch_k = self._get_indicator_value("StochRSI_K")
<                 stoch_d = self._get_indicator_value("StochRSI_D")
<                 if not pd.isna(stoch_k) and not pd.isna(stoch_d) and len(self.df) > 1:
<                     prev_stoch_k = self.df["StochRSI_K"].iloc[-2]
<                     prev_stoch_d = self.df["StochRSI_D"].iloc[-2]
<                     contrib = 0.0
<                     if (
<                         stoch_k > stoch_d
<                         and prev_stoch_k <= prev_stoch_d
<                         and stoch_k < isd["stoch_rsi_oversold"]
<                     ):
<                         contrib = momentum_weight * 0.6
<                         self.logger.debug(f"[{self.symbol}] StochRSI: Bullish crossover from oversold.")
<                     elif (
<                         stoch_k < stoch_d
<                         and prev_stoch_k >= prev_stoch_d
<                         and stoch_k > isd["stoch_rsi_overbought"]
<                     ):
<                         contrib = -momentum_weight * 0.6
<                         self.logger.debug(f"[{self.symbol}] StochRSI: Bearish crossover from overbought.")
<                     elif stoch_k > stoch_d and stoch_k < 50: # General bullish momentum
<                         contrib = momentum_weight * 0.2
<                     elif stoch_k < stoch_d and stoch_k > 50: # General bearish momentum
<                         contrib = -momentum_weight * 0.2
<                     signal_score += contrib
<                     signal_breakdown["StochRSI_Signal"] = contrib
< 
<             # CCI
<             if active_indicators.get("cci", False):
<                 cci = self._get_indicator_value("CCI")
<                 if not pd.isna(cci):
<                     # Normalize CCI (e.g., -200 to +200 range, normalize to -1 to +1)
<                     normalized_cci = float(cci) / 200 # Assuming typical range of -200 to 200
<                     contrib = 0.0
<                     if cci < isd["cci_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif cci > isd["cci_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["CCI_Signal"] = contrib
< 
<             # Williams %R
<             if active_indicators.get("wr", False):
<                 wr = self._get_indicator_value("WR")
<                 if not pd.isna(wr):
<                     # Normalize WR to -1 to +1 scale (-100 to 0, so (WR + 50) / 50)
<                     normalized_wr = (float(wr) + 50) / 50 # Assuming typical range of -100 to 0
<                     contrib = 0.0
<                     if wr < isd["williams_r_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif wr > isd["williams_r_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["WR_Signal"] = contrib
< 
<             # MFI
<             if active_indicators.get("mfi", False):
<                 mfi = self._get_indicator_value("MFI")
<                 if not pd.isna(mfi):
<                     # Normalize MFI to -1 to +1 scale (0 to 100, so (MFI - 50) / 50)
<                     normalized_mfi = (float(mfi) - 50) / 50
<                     contrib = 0.0
<                     if mfi < isd["mfi_oversold"]:
<                         contrib = momentum_weight * 0.4
<                     elif mfi > isd["mfi_overbought"]:
<                         contrib = -momentum_weight * 0.4
<                     signal_score += contrib
<                     signal_breakdown["MFI_Signal"] = contrib
< 
<         # Bollinger Bands
<         if active_indicators.get("bollinger_bands", False):
<             bb_upper = self._get_indicator_value("BB_Upper")
<             bb_lower = self._get_indicator_value("BB_Lower")
<             if not pd.isna(bb_upper) and not pd.isna(bb_lower):
<                 contrib = 0.0
<                 if current_close < bb_lower:
<                     contrib = weights.get("bollinger_bands", 0) * 0.5
<                 elif current_close > bb_upper:
<                     contrib = -weights.get("bollinger_bands", 0) * 0.5
<                 signal_score += contrib
<                 signal_breakdown["Bollinger_Bands_Signal"] = contrib
< 
<         # VWAP
<         if active_indicators.get("vwap", False):
<             vwap = self._get_indicator_value("VWAP")
<             if not pd.isna(vwap):
<                 contrib = 0.0
<                 if current_close > vwap:
<                     contrib = weights.get("vwap", 0) * 0.2
<                 elif current_close < vwap:
<                     contrib = -weights.get("vwap", 0) * 0.2
< 
<                 if len(self.df) > 1:
<                     prev_vwap = Decimal(str(self.df["VWAP"].iloc[-2]))
<                     if (current_close > vwap and prev_close <= prev_vwap):
<                         contrib += weights.get("vwap", 0) * 0.3
<                         self.logger.debug(f"[{self.symbol}] VWAP: Bullish crossover detected.")
<                     elif (current_close < vwap and prev_close >= prev_vwap):
<                         contrib -= weights.get("vwap", 0) * 0.3
<                         self.logger.debug(f"[{self.symbol}] VWAP: Bearish crossover detected.")
<                 signal_score += contrib
<                 signal_breakdown["VWAP_Signal"] = contrib
< 
<         # PSAR
<         if active_indicators.get("psar", False):
<             psar_val = self._get_indicator_value("PSAR_Val")
<             psar_dir = self._get_indicator_value("PSAR_Dir")
<             if not pd.isna(psar_val) and not pd.isna(psar_dir):
<                 contrib = 0.0
<                 # PSAR direction change is a strong signal
<                 if psar_dir == 1: # Bullish PSAR
<                     contrib = weights.get("psar", 0) * 0.5
<                 elif psar_dir == -1: # Bearish PSAR
<                     contrib = -weights.get("psar", 0) * 0.5
< 
<                 # PSAR crossover with price
<                 if len(self.df) > 1:
<                     prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
<                     if (current_close > psar_val and prev_close <= prev_psar_val):
<                         contrib += weights.get("psar", 0) * 0.4 # Additional bullish weight on crossover
<                         self.logger.debug("PSAR: Bullish reversal detected.")
<                     elif (current_close < psar_val and prev_close >= prev_psar_val):
<                         contrib -= weights.get("psar", 0) * 0.4 # Additional bearish weight on crossover
<                         self.logger.debug("PSAR: Bearish reversal detected.")
<                 signal_score += contrib
<                 signal_breakdown["PSAR_Signal"] = contrib
< 
<         # SMA_10 (short-term trend confirmation)
<         if active_indicators.get("sma_10", False):
<             sma_10 = self._get_indicator_value("SMA_10")
<             if not pd.isna(sma_10):
<                 contrib = 0.0
<                 if current_close > sma_10:
<                     contrib = weights.get("sma_10", 0) * 0.5
<                 elif current_close < sma_10:
<                     contrib = -weights.get("sma_10", 0) * 0.5
<                 signal_score += contrib
<                 signal_breakdown["SMA_10_Signal"] = contrib
< 
<         # Orderbook Imbalance
<         if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
<             imbalance = self._check_orderbook(current_price, orderbook_data)
<             contrib = imbalance * weights.get("orderbook_imbalance", 0)
<             signal_score += contrib
<             signal_breakdown["Orderbook_Imbalance"] = contrib
< 
<         # Fibonacci Levels (confluence with price action)
<         if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
<             for level_name, level_price in self.fib_levels.items():
<                 # Check if price is near a Fibonacci level
<                 if (level_name not in ["0.0%", "100.0%"] and
<                     abs(current_close - level_price) / current_close < Decimal("0.001")): # Within 0.1% of the level
<                         self.logger.debug(
<                             f"Price near Fibonacci level {level_name}: {level_price}"
<                         )
<                         contrib = 0.0
<                         # If price crosses the level, it can act as support/resistance
<                         if len(self.df) > 1:
<                             if (current_close > prev_close and current_close > level_price): # Bullish breakout
<                                 contrib = weights.get("fibonacci_levels", 0) * 0.1
<                             elif (current_close < prev_close and current_close < level_price): # Bearish breakdown
<                                 contrib = -weights.get("fibonacci_levels", 0) * 0.1
<                         signal_score += contrib
<                         signal_breakdown["Fibonacci_Levels_Signal"] = contrib
< 
<         # --- Ehlers SuperTrend Alignment Scoring ---
<         if active_indicators.get("ehlers_supertrend", False):
<             st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
<             st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
<             prev_st_fast_dir = (
<                 self.df["st_fast_dir"].iloc[-2]
<                 if "st_fast_dir" in self.df.columns and len(self.df) > 1
<                 else np.nan
<             )
<             weight = weights.get("ehlers_supertrend_alignment", 0.0)
< 
<             if (
<                 not pd.isna(st_fast_dir)
<                 and not pd.isna(st_slow_dir)
<                 and not pd.isna(prev_st_fast_dir)
<             ):
<                 contrib = 0.0
<                 # Strong buy signal: fast ST flips up and aligns with slow ST (which is also up)
<                 if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
<                     contrib = weight
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
<                     )
<                 # Strong sell signal: fast ST flips down and aligns with slow ST (which is also down)
<                 elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
<                     contrib = -weight
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
<                     )
<                 # General alignment: both fast and slow ST are in the same direction
<                 elif st_slow_dir == 1 and st_fast_dir == 1:
<                     contrib = weight * 0.3
<                 elif st_slow_dir == -1 and st_fast_dir == -1:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
< 
<         # --- MACD Alignment Scoring ---
<         if active_indicators.get("macd", False):
<             macd_line = self._get_indicator_value("MACD_Line")
<             signal_line = self._get_indicator_value("MACD_Signal")
<             histogram = self._get_indicator_value("MACD_Hist")
<             weight = weights.get("macd_alignment", 0.0)
< 
<             if (
<                 not pd.isna(macd_line)
<                 and not pd.isna(signal_line)
<                 and not pd.isna(histogram)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 # Bullish crossover: MACD line crosses above Signal line
<                 if (
<                     macd_line > signal_line
<                     and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = weight
<                     self.logger.debug(
<                         "MACD: BUY signal (MACD line crossed above Signal line)."
<                     )
<                 # Bearish crossover: MACD line crosses below Signal line
<                 elif (
<                     macd_line < signal_line
<                     and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = -weight
<                     self.logger.debug(
<                         "MACD: SELL signal (MACD line crossed below Signal line)."
<                     )
<                 # Histogram turning positive/negative from zero line
<                 elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
<                     contrib = weight * 0.2
<                 elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
<                     contrib = -weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["MACD_Alignment"] = contrib
< 
<         # --- ADX Alignment Scoring ---
<         if active_indicators.get("adx", False):
<             adx_val = self._get_indicator_value("ADX")
<             plus_di = self._get_indicator_value("PlusDI")
<             minus_di = self._get_indicator_value("MinusDI")
<             weight = weights.get("adx_strength", 0.0)
< 
<             if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
<                 contrib = 0.0
<                 # Strong trend confirmation
<                 if adx_val > ADX_STRONG_TREND_THRESHOLD:
<                     if plus_di > minus_di: # Bullish trend
<                         contrib = weight
<                         self.logger.debug(
<                             "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
<                         )
<                     elif minus_di > plus_di: # Bearish trend
<                         contrib = -weight
<                         self.logger.debug(
<                             "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
<                         )
<                 elif adx_val < ADX_WEAK_TREND_THRESHOLD:
<                     contrib = 0 # Neutral signal, no contribution from ADX
<                     self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")
<                 signal_score += contrib
<                 signal_breakdown["ADX_Strength"] = contrib
< 
<         # --- Ichimoku Cloud Alignment Scoring ---
<         if active_indicators.get("ichimoku_cloud", False):
<             tenkan_sen = self._get_indicator_value("Tenkan_Sen")
<             kijun_sen = self._get_indicator_value("Kijun_Sen")
<             senkou_span_a = self._get_indicator_value("Senkou_Span_A")
<             senkou_span_b = self._get_indicator_value("Senkou_Span_B")
<             chikou_span = self._get_indicator_value("Chikou_Span")
<             weight = weights.get("ichimoku_confluence", 0.0)
< 
<             if (
<                 not pd.isna(tenkan_sen)
<                 and not pd.isna(kijun_sen)
<                 and not pd.isna(senkou_span_a)
<                 and not pd.isna(senkou_span_b)
<                 and not pd.isna(chikou_span)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 # Tenkan-sen / Kijun-sen crossover
<                 if (
<                     tenkan_sen > kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib += weight * 0.5 # Bullish crossover
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
<                     )
<                 elif (
<                     tenkan_sen < kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.5 # Bearish crossover
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
<                     )
< 
<                 # Price breaking above/below Kumo (cloud)
<                 if current_close > max(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] <= max(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib += weight * 0.7 # Strong bullish breakout
<                     self.logger.debug(
<                         "Ichimoku: Price broke above Kumo (strong bullish)."
<                     )
<                 elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] >= min(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.7 # Strong bearish breakdown
<                     self.logger.debug(
<                         "Ichimoku: Price broke below Kumo (strong bearish)."
<                     )
< 
<                 # Chikou Span crossover with price
<                 if (
<                     chikou_span > current_close
<                     and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
<                 ):
<                     contrib += weight * 0.3 # Bullish confirmation
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
<                     )
<                 elif (
<                     chikou_span < current_close
<                     and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.3 # Bearish confirmation
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
<                     )
<                 signal_score += contrib
<                 signal_breakdown["Ichimoku_Confluence"] = contrib
< 
<         # --- OBV Alignment Scoring ---
<         if active_indicators.get("obv", False):
<             obv_val = self._get_indicator_value("OBV")
<             obv_ema = self._get_indicator_value("OBV_EMA")
<             weight = weights.get("obv_momentum", 0.0)
< 
<             if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
<                 contrib = 0.0
<                 # OBV crossing its EMA
<                 if (
<                     obv_val > obv_ema
<                     and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = weight * 0.5 # Bullish crossover
<                     self.logger.debug("OBV: Bullish crossover detected.")
<                 elif (
<                     obv_val < obv_ema
<                     and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = -weight * 0.5 # Bearish crossover
<                     self.logger.debug("OBV: Bearish crossover detected.")
< 
<                 # OBV trend confirmation (e.g., higher highs/lower lows)
<                 if len(self.df) > 2:
<                     if (
<                         obv_val > self.df["OBV"].iloc[-2]
<                         and obv_val > self.df["OBV"].iloc[-3]
<                     ):
<                         contrib += weight * 0.2 # OBV making higher highs
<                     elif (
<                         obv_val < self.df["OBV"].iloc[-2]
<                         and obv_val < self.df["OBV"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.2 # OBV making lower lows
<                 signal_score += contrib
<                 signal_breakdown["OBV_Momentum"] = contrib
< 
<         # --- CMF Alignment Scoring ---
<         if active_indicators.get("cmf", False):
<             cmf_val = self._get_indicator_value("CMF")
<             weight = weights.get("cmf_flow", 0.0)
< 
<             if not pd.isna(cmf_val):
<                 contrib = 0.0
<                 # CMF above/below zero line
<                 if cmf_val > 0:
<                     contrib = weight * 0.5 # Bullish money flow
<                 elif cmf_val < 0:
<                     contrib = -weight * 0.5 # Bearish money flow
< 
<                 # CMF trend confirmation
<                 if len(self.df) > 2:
<                     if (
<                         cmf_val > self.df["CMF"].iloc[-2]
<                         and cmf_val > self.df["CMF"].iloc[-3]
<                     ):
<                         contrib += weight * 0.3 # CMF making higher highs
<                     elif (
<                         cmf_val < self.df["CMF"].iloc[-2]
<                         and cmf_val < self.df["CMF"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.3 # CMF making lower lows
<                 signal_score += contrib
<                 signal_breakdown["CMF_Flow"] = contrib
< 
<         # --- Volatility Index Scoring ---
<         if active_indicators.get("volatility_index", False):
<             vol_idx = self._get_indicator_value("Volatility_Index")
<             weight = weights.get("volatility_index_signal", 0.0)
<             if not pd.isna(vol_idx):
<                 contrib = 0.0
<                 if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
<                     prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
<                     prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
< 
<                     if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
<                         # Increasing volatility can amplify existing signals
<                         if signal_score > 0:
<                             contrib = weight * 0.2
<                         elif signal_score < 0:
<                             contrib = -weight * 0.2
<                         self.logger.debug("Volatility Index: Increasing volatility.")
<                     elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
<                         # Decreasing volatility might reduce confidence in strong signals
<                         if abs(signal_score) > 0: # If there's an existing signal, slightly reduce it
<                              contrib = signal_score * -0.2 # Reduce score by 20% (example)
<                         self.logger.debug("Volatility Index: Decreasing volatility.")
<                 signal_score += contrib
<                 signal_breakdown["Volatility_Index_Signal"] = contrib
< 
<         # --- VWMA Cross Scoring ---
<         if active_indicators.get("vwma", False):
<             vwma = self._get_indicator_value("VWMA")
<             weight = weights.get("vwma_cross", 0.0)
<             if not pd.isna(vwma) and len(self.df) > 1:
<                 prev_vwma = self.df["VWMA"].iloc[-2]
<                 contrib = 0.0
<                 # Price crossing VWMA
<                 if current_close > vwma and prev_close <= prev_vwma:
<                     contrib = weight # Bullish crossover
<                     self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
<                 elif current_close < vwma and prev_close >= prev_vwma:
<                     contrib = -weight # Bearish crossover
<                     self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
<                 signal_score += contrib
<                 signal_breakdown["VWMA_Cross"] = contrib
< 
<         # --- Volume Delta Scoring ---
<         if active_indicators.get("volume_delta", False):
<             volume_delta = self._get_indicator_value("Volume_Delta")
<             volume_delta_threshold = isd["volume_delta_threshold"]
<             weight = weights.get("volume_delta_signal", 0.0)
< 
<             if not pd.isna(volume_delta):
<                 contrib = 0.0
<                 if volume_delta > volume_delta_threshold:  # Strong buying pressure
<                     contrib = weight
<                     self.logger.debug("Volume Delta: Strong buying pressure detected.")
<                 elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
<                     contrib = -weight
<                     self.logger.debug("Volume Delta: Strong selling pressure detected.")
<                 # Weaker signals for moderate delta
<                 elif volume_delta > 0:
<                     contrib = weight * 0.3
<                 elif volume_delta < 0:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Volume_Delta_Signal"] = contrib
< 
< 
<         # --- Multi-Timeframe Trend Confluence Scoring ---
<         if self.config["mtf_analysis"]["enabled"] and mtf_trends:
<             mtf_buy_score = 0
<             mtf_sell_score = 0
<             for _tf_indicator, trend in mtf_trends.items():
<                 if trend == "UP":
<                     mtf_buy_score += 1
<                 elif trend == "DOWN":
<                     mtf_sell_score += 1
< 
<             mtf_weight = weights.get("mtf_trend_confluence", 0.0)
<             contrib = 0.0
<             if mtf_trends:
<                 # Calculate a normalized score based on the balance of buy/sell trends
<                 normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
<                     mtf_trends
<                 )
<                 contrib = mtf_weight * normalized_mtf_score
<                 self.logger.debug(
<                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
<                 )
<             signal_score += contrib
<             signal_breakdown["MTF_Trend_Confluence"] = contrib
< 
<         # --- Final Signal Determination with Hysteresis and Cooldown ---
<         threshold = self.config["signal_score_threshold"]
<         cooldown_sec = self.config["cooldown_sec"]
<         hysteresis_ratio = self.config["hysteresis_ratio"]
< 
<         final_signal = "HOLD"
<         now_ts = int(time.time())
< 
<         is_strong_buy = signal_score >= threshold
<         is_strong_sell = signal_score <= -threshold
< 
<         # Apply hysteresis to prevent immediate flip-flops
<         # If the bot previously issued a BUY signal and the current score is not a strong SELL, and not a strong BUY, it holds the BUY signal.
<         # This prevents it from flipping to HOLD or SELL too quickly if the score dips slightly.
<         if self._last_signal_score > 0 and signal_score > -threshold * hysteresis_ratio and not is_strong_buy:
<             final_signal = "BUY"
<         # If the bot previously issued a SELL signal and the current score is not a strong BUY, and not a strong SELL, it holds the SELL signal.
<         elif self._last_signal_score < 0 and signal_score < threshold * hysteresis_ratio and not is_strong_sell:
<             final_signal = "SELL"
<         elif is_strong_buy:
<             final_signal = "BUY"
<         elif is_strong_sell:
<             final_signal = "SELL"
< 
<         # Apply cooldown period
<         if final_signal != "HOLD":
<             if now_ts - self._last_signal_ts < cooldown_sec:
<                 self.logger.info(f"{NEON_YELLOW}Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
<                 final_signal = "HOLD"
<             else:
<                 self._last_signal_ts = now_ts # Update timestamp only if signal is issued
< 
<         # Update last signal score for next iteration's hysteresis
<         self._last_signal_score = signal_score
< 
<         self.logger.info(
<             f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
<         )
<         return final_signal, signal_score, signal_breakdown
< 
<         # PSAR
<         if active_indicators.get("psar", False):
<             psar_val = self._get_indicator_value("PSAR_Val")
<             psar_dir = self._get_indicator_value("PSAR_Dir")
<             if not pd.isna(psar_val) and not pd.isna(psar_dir):
<                 contrib = 0.0
<                 if psar_dir == 1:
<                     contrib = weights.get("psar", 0) * 0.5
<                 elif psar_dir == -1:
<                     contrib = -weights.get("psar", 0) * 0.5
< 
<                 if len(self.df) > 1:
<                     prev_psar_val = Decimal(str(self.df["PSAR_Val"].iloc[-2]))
<                     if (current_close > psar_val and prev_close <= prev_psar_val):
<                         contrib += weights.get("psar", 0) * 0.4
<                         self.logger.debug("PSAR: Bullish reversal detected.")
<                     elif (current_close < psar_val and prev_close >= prev_psar_val):
<                         contrib -= weights.get("psar", 0) * 0.4
<                         self.logger.debug("PSAR: Bearish reversal detected.")
<                 signal_score += contrib
<                 signal_breakdown["PSAR_Signal"] = contrib
< 
<         # Orderbook Imbalance
<         if active_indicators.get("orderbook_imbalance", False) and orderbook_data:
<             imbalance = self._check_orderbook(current_price, orderbook_data)
<             contrib = imbalance * weights.get("orderbook_imbalance", 0)
<             signal_score += contrib
<             signal_breakdown["Orderbook_Imbalance"] = contrib
< 
<         # Fibonacci Levels (confluence with price action)
<         if active_indicators.get("fibonacci_levels", False) and self.fib_levels:
<             for level_name, level_price in self.fib_levels.items():
<                 if (level_name not in ["0.0%", "100.0%"] and
<                     abs(current_price - level_price) / current_price < Decimal("0.001")):
<                         self.logger.debug(
<                             f"Price near Fibonacci level {level_name}: {level_price}"
<                         )
<                         contrib = 0.0
<                         if len(self.df) > 1:
<                             if (current_close > prev_close and current_close > level_price):
<                                 contrib = weights.get("fibonacci_levels", 0) * 0.1
<                             elif (current_close < prev_close and current_close < level_price):
<                                 contrib = -weights.get("fibonacci_levels", 0) * 0.1
<                         signal_score += contrib
<                         signal_breakdown["Fibonacci_Levels_Signal"] = contrib
< 
<         # --- Ehlers SuperTrend Alignment Scoring ---
<         if active_indicators.get("ehlers_supertrend", False):
<             st_fast_dir = self._get_indicator_value("ST_Fast_Dir")
<             st_slow_dir = self._get_indicator_value("ST_Slow_Dir")
<             prev_st_fast_dir = (
<                 self.df["st_fast_dir"].iloc[-2]
<                 if "st_fast_dir" in self.df.columns and len(self.df) > 1
<                 else np.nan
<             )
<             weight = weights.get("ehlers_supertrend_alignment", 0.0)
< 
<             if (
<                 not pd.isna(st_fast_dir)
<                 and not pd.isna(st_slow_dir)
<                 and not pd.isna(prev_st_fast_dir)
<             ):
<                 contrib = 0.0
<                 if st_slow_dir == 1 and st_fast_dir == 1 and prev_st_fast_dir == -1:
<                     contrib = weight
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
<                     )
<                 elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
<                     contrib = -weight
<                     self.logger.debug(
<                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
<                     )
<                 elif st_slow_dir == 1 and st_fast_dir == 1:
<                     contrib = weight * 0.3
<                 elif st_slow_dir == -1 and st_fast_dir == -1:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Ehlers_SuperTrend_Alignment"] = contrib
< 
<         # --- MACD Alignment Scoring ---
<         if active_indicators.get("macd", False):
<             macd_line = self._get_indicator_value("MACD_Line")
<             signal_line = self._get_indicator_value("MACD_Signal")
<             histogram = self._get_indicator_value("MACD_Hist")
<             weight = weights.get("macd_alignment", 0.0)
< 
<             if (
<                 not pd.isna(macd_line)
<                 and not pd.isna(signal_line)
<                 and not pd.isna(histogram)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 if (
<                     macd_line > signal_line
<                     and self.df["MACD_Line"].iloc[-2] <= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = weight
<                     self.logger.debug(
<                         "MACD: BUY signal (MACD line crossed above Signal line)."
<                     )
<                 elif (
<                     macd_line < signal_line
<                     and self.df["MACD_Line"].iloc[-2] >= self.df["MACD_Signal"].iloc[-2]
<                 ):
<                     contrib = -weight
<                     self.logger.debug(
<                         "MACD: SELL signal (MACD line crossed below Signal line)."
<                     )
<                 elif histogram > 0 and self.df["MACD_Hist"].iloc[-2] < 0:
<                     contrib = weight * 0.2
<                 elif histogram < 0 and self.df["MACD_Hist"].iloc[-2] > 0:
<                     contrib = -weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["MACD_Alignment"] = contrib
< 
<         # --- ADX Alignment Scoring ---
<         if active_indicators.get("adx", False):
<             adx_val = self._get_indicator_value("ADX")
<             plus_di = self._get_indicator_value("PlusDI")
<             minus_di = self._get_indicator_value("MinusDI")
<             weight = weights.get("adx_strength", 0.0)
< 
<             if not pd.isna(adx_val) and not pd.isna(plus_di) and not pd.isna(minus_di):
<                 contrib = 0.0
<                 if adx_val > ADX_STRONG_TREND_THRESHOLD:
<                     if plus_di > minus_di:
<                         contrib = weight
<                         self.logger.debug(
<                             "ADX: Strong BUY trend (ADX > 25, +DI > -DI)."
<                         )
<                     elif minus_di > plus_di:
<                         contrib = -weight
<                         self.logger.debug(
<                             "ADX: Strong SELL trend (ADX > 25, -DI > +DI)."
<                         )
<                 elif adx_val < ADX_WEAK_TREND_THRESHOLD:
<                     contrib = 0 # Neutral signal, no contribution
<                     self.logger.debug("ADX: Weak trend (ADX < 20). Neutral signal.")
<                 signal_score += contrib
<                 signal_breakdown["ADX_Strength"] = contrib
< 
<         # --- Ichimoku Cloud Alignment Scoring ---
<         if active_indicators.get("ichimoku_cloud", False):
<             tenkan_sen = self._get_indicator_value("Tenkan_Sen")
<             kijun_sen = self._get_indicator_value("Kijun_Sen")
<             senkou_span_a = self._get_indicator_value("Senkou_Span_A")
<             senkou_span_b = self._get_indicator_value("Senkou_Span_B")
<             chikou_span = self._get_indicator_value("Chikou_Span")
<             weight = weights.get("ichimoku_confluence", 0.0)
< 
<             if (
<                 not pd.isna(tenkan_sen)
<                 and not pd.isna(kijun_sen)
<                 and not pd.isna(senkou_span_a)
<                 and not pd.isna(senkou_span_b)
<                 and not pd.isna(chikou_span)
<                 and len(self.df) > 1
<             ):
<                 contrib = 0.0
<                 if (
<                     tenkan_sen > kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] <= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib += weight * 0.5
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed above Kijun-sen (bullish)."
<                     )
<                 elif (
<                     tenkan_sen < kijun_sen
<                     and self.df["Tenkan_Sen"].iloc[-2] >= self.df["Kijun_Sen"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.5
<                     self.logger.debug(
<                         "Ichimoku: Tenkan-sen crossed below Kijun-sen (bearish)."
<                     )
< 
<                 if current_close > max(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] <= max(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib += weight * 0.7
<                     self.logger.debug(
<                         "Ichimoku: Price broke above Kumo (strong bullish)."
<                     )
<                 elif current_close < min(senkou_span_a, senkou_span_b) and self.df[
<                     "close"
<                 ].iloc[-2] >= min(
<                     self.df["Senkou_Span_A"].iloc[-2], self.df["Senkou_Span_B"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.7
<                     self.logger.debug(
<                         "Ichimoku: Price broke below Kumo (strong bearish)."
<                     )
< 
<                 if (
<                     chikou_span > current_close
<                     and self.df["Chikou_Span"].iloc[-2] <= self.df["close"].iloc[-2]
<                 ):
<                     contrib += weight * 0.3
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
<                     )
<                 elif (
<                     chikou_span < current_close
<                     and self.df["Chikou_Span"].iloc[-2] >= self.df["close"].iloc[-2]
<                 ):
<                     contrib -= weight * 0.3
<                     self.logger.debug(
<                         "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
<                     )
<                 signal_score += contrib
<                 signal_breakdown["Ichimoku_Confluence"] = contrib
< 
<         # --- OBV Alignment Scoring ---
<         if active_indicators.get("obv", False):
<             obv_val = self._get_indicator_value("OBV")
<             obv_ema = self._get_indicator_value("OBV_EMA")
<             weight = weights.get("obv_momentum", 0.0)
< 
<             if not pd.isna(obv_val) and not pd.isna(obv_ema) and len(self.df) > 1:
<                 contrib = 0.0
<                 if (
<                     obv_val > obv_ema
<                     and self.df["OBV"].iloc[-2] <= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = weight * 0.5
<                     self.logger.debug("OBV: Bullish crossover detected.")
<                 elif (
<                     obv_val < obv_ema
<                     and self.df["OBV"].iloc[-2] >= self.df["OBV_EMA"].iloc[-2]
<                 ):
<                     contrib = -weight * 0.5
<                     self.logger.debug("OBV: Bearish crossover detected.")
< 
<                 if len(self.df) > 2:
<                     if (
<                         obv_val > self.df["OBV"].iloc[-2]
<                         and obv_val > self.df["OBV"].iloc[-3]
<                     ):
<                         contrib += weight * 0.2
<                     elif (
<                         obv_val < self.df["OBV"].iloc[-2]
<                         and obv_val < self.df["OBV"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.2
<                 signal_score += contrib
<                 signal_breakdown["OBV_Momentum"] = contrib
< 
<         # --- CMF Alignment Scoring ---
<         if active_indicators.get("cmf", False):
<             cmf_val = self._get_indicator_value("CMF")
<             weight = weights.get("cmf_flow", 0.0)
< 
<             if not pd.isna(cmf_val):
<                 contrib = 0.0
<                 if cmf_val > 0:
<                     contrib = weight * 0.5
<                 elif cmf_val < 0:
<                     contrib = -weight * 0.5
< 
<                 if len(self.df) > 2:
<                     if (
<                         cmf_val > self.df["CMF"].iloc[-2]
<                         and cmf_val > self.df["CMF"].iloc[-3]
<                     ):
<                         contrib += weight * 0.3
<                     elif (
<                         cmf_val < self.df["CMF"].iloc[-2]
<                         and cmf_val < self.df["CMF"].iloc[-3]
<                     ):
<                         contrib -= weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["CMF_Flow"] = contrib
< 
<         # --- Volatility Index Scoring ---
<         if active_indicators.get("volatility_index", False):
<             vol_idx = self._get_indicator_value("Volatility_Index")
<             weight = weights.get("volatility_index_signal", 0.0)
<             if not pd.isna(vol_idx):
<                 contrib = 0.0
<                 if len(self.df) > 2 and "Volatility_Index" in self.df.columns:
<                     prev_vol_idx = self.df["Volatility_Index"].iloc[-2]
<                     prev_prev_vol_idx = self.df["Volatility_Index"].iloc[-3]
< 
<                     if vol_idx > prev_vol_idx > prev_prev_vol_idx:  # Increasing volatility
<                         if signal_score > 0:
<                             contrib = weight * 0.2
<                         elif signal_score < 0:
<                             contrib = -weight * 0.2
<                         self.logger.debug("Volatility Index: Increasing volatility.")
<                     elif vol_idx < prev_vol_idx < prev_prev_vol_idx: # Decreasing volatility
<                         if abs(signal_score) > 0: # If there's an existing signal, slightly reduce it
<                              contrib = signal_score * -0.2 # Reduce score by 20% (example)
<                         self.logger.debug("Volatility Index: Decreasing volatility.")
<                 signal_score += contrib
<                 signal_breakdown["Volatility_Index_Signal"] = contrib
< 
<         # --- VWMA Cross Scoring ---
<         if active_indicators.get("vwma", False):
<             vwma = self._get_indicator_value("VWMA")
<             weight = weights.get("vwma_cross", 0.0)
<             if not pd.isna(vwma) and len(self.df) > 1:
<                 prev_vwma = self.df["VWMA"].iloc[-2]
<                 contrib = 0.0
<                 if current_close > vwma and prev_close <= prev_vwma:
<                     contrib = weight
<                     self.logger.debug("VWMA: Bullish crossover (price above VWMA).")
<                 elif current_close < vwma and prev_close >= prev_vwma:
<                     contrib = -weight
<                     self.logger.debug("VWMA: Bearish crossover (price below VWMA).")
<                 signal_score += contrib
<                 signal_breakdown["VWMA_Cross"] = contrib
< 
<         # --- Volume Delta Scoring ---
<         if active_indicators.get("volume_delta", False):
<             volume_delta = self._get_indicator_value("Volume_Delta")
<             volume_delta_threshold = isd["volume_delta_threshold"]
<             weight = weights.get("volume_delta_signal", 0.0)
< 
<             if not pd.isna(volume_delta):
<                 contrib = 0.0
<                 if volume_delta > volume_delta_threshold:  # Strong buying pressure
<                     contrib = weight
<                     self.logger.debug("Volume Delta: Strong buying pressure detected.")
<                 elif volume_delta < -volume_delta_threshold:  # Strong selling pressure
<                     contrib = -weight
<                     self.logger.debug("Volume Delta: Strong selling pressure detected.")
<                 # Weaker signals for moderate delta
<                 elif volume_delta > 0:
<                     contrib = weight * 0.3
<                 elif volume_delta < 0:
<                     contrib = -weight * 0.3
<                 signal_score += contrib
<                 signal_breakdown["Volume_Delta_Signal"] = contrib
< 
< 
<         # --- Multi-Timeframe Trend Confluence Scoring ---
<         if self.config["mtf_analysis"]["enabled"] and mtf_trends:
<             mtf_buy_score = 0
<             mtf_sell_score = 0
<             for _tf_indicator, trend in mtf_trends.items():
<                 if trend == "UP":
<                     mtf_buy_score += 1
<                 elif trend == "DOWN":
<                     mtf_sell_score += 1
< 
<             mtf_weight = weights.get("mtf_trend_confluence", 0.0)
<             contrib = 0.0
<             if mtf_trends:
<                 # Calculate a normalized score based on the balance of buy/sell trends
<                 normalized_mtf_score = (mtf_buy_score - mtf_sell_score) / len(
<                     mtf_trends
<                 )
<                 contrib = mtf_weight * normalized_mtf_score
<                 self.logger.debug(
<                     f"MTF Confluence: Score {normalized_mtf_score:.2f} (Buy: {mtf_buy_score}, Sell: {mtf_sell_score}). Total MTF contribution: {mtf_weight * normalized_mtf_score:.2f}"
<                 )
<             signal_score += contrib
<             signal_breakdown["MTF_Trend_Confluence"] = contrib
< 
<         # --- Final Signal Determination with Hysteresis and Cooldown ---
<         threshold = self.config["signal_score_threshold"]
<         cooldown_sec = self.config["cooldown_sec"]
<         hysteresis_ratio = self.config["hysteresis_ratio"]
---
>     def _nz(self, x, default=np.nan):
>         try: return float(x)
>         except Exception: return default
> 
>     def _clip(self, x, lo=-1.0, hi=1.0):
>         return float(np.clip(x, lo, hi))
> 
>     def _safe_prev(self, series_name: str, default=np.nan):
>         s = self.df.get(series_name)
>         if s is None or len(s) < 2: return default, default
>         return float(s.iloc[-1]), float(s.iloc[-2])
> 
>     def _market_regime(self):
>         adx = self._nz(self._get_indicator_value("ADX"))
>         bb_u = self._nz(self._get_indicator_value("BB_Upper"))
>         bb_l = self._nz(self._get_indicator_value("BB_Lower"))
>         bb_m = self._nz(self._get_indicator_value("BB_Middle"))
>         band = (bb_u - bb_l) / bb_m if bb_m and bb_m != 0 else 0
>         if adx >= 23 or band >= 0.03: return "TRENDING"
>         return "RANGING"
2816a999,1147
>     def _volume_confirm(self):
>         try:
>             vol_now = float(self.df["volume"].iloc[-1])
>             vol_ma = float(self.df["volume"].rolling(20).mean().iloc[-1])
>             mult = float(self.config.get("volume_confirmation_multiplier", 1.5))
>             return vol_now > mult * vol_ma if vol_ma > 0 else False
>         except Exception: return False
> 
>     def _orderbook_score(self, orderbook_data, weight):
>         if not orderbook_data: return 0.0, None
>         imb = self._clip(self._check_orderbook(Decimal(str(self.df['close'].iloc[-1])), orderbook_data))
>         if abs(imb) < 0.05: return 0.0, None
>         return weight * imb, f"OB Imbalance {imb:+.2f}"
> 
>     def _mtf_confluence(self, mtf_trends: dict[str, str], weight):
>         if not mtf_trends: return 0.0, None
>         bulls = sum(1 for v in mtf_trends.values() if isinstance(v, str) and v.upper().startswith("BULL"))
>         bears = sum(1 for v in mtf_trends.values() if isinstance(v, str) and v.upper().startswith("BEAR"))
>         total = bulls + bears
>         if total == 0: return 0.0, None
>         net = (bulls - bears) / total
>         return weight * net, f"MTF Confluence {net:+.2f} ({bulls}:{bears})"
> 
>     def _dynamic_threshold(self, base_threshold: float) -> float:
>         atr_now = self._nz(self._get_indicator_value("ATR"), 0.0)
>         if "ATR" not in self.df or self.df["ATR"].rolling(50).mean().empty: return base_threshold
>         atr_ma = float(self.df["ATR"].rolling(50).mean().iloc[-1])
>         if atr_ma <= 0: return base_threshold
>         ratio = float(np.clip(atr_now / atr_ma, 0.9, 1.5))
>         return base_threshold * ratio
> 
>     def generate_trading_signal(self, current_price: Decimal, orderbook_data: dict | None, mtf_trends: dict[str, str]) -> tuple[str, float]:
>         if self.df.empty: return "HOLD", 0.0
>         w, active, isd = self.weights, self.config["indicators"], self.indicator_settings
>         score, notes_buy, notes_sell = 0.0, [], []
>         close = float(self.df["close"].iloc[-1])
>         regime = self._market_regime()
> 
>         if active.get("ema_alignment"):
>             es, el = self._nz(self._get_indicator_value("EMA_Short")), self._nz(self._get_indicator_value("EMA_Long"))
>             if not np.isnan(es) and not np.isnan(el):
>                 if es > el: score += w.get("ema_alignment", 0); notes_buy.append(f"EMA Bull +{w.get('ema_alignment',0):.2f}")
>                 elif es < el: score -= w.get("ema_alignment", 0); notes_sell.append(f"EMA Bear -{w.get('ema_alignment',0):.2f}")
>         if active.get("sma_trend_filter"):
>             sma_long = self._nz(self._get_indicator_value("SMA_Long"))
>             if not np.isnan(sma_long):
>                 if close > sma_long: score += w.get("sma_trend_filter", 0); notes_buy.append(f"SMA Trend Bull +{w.get('sma_trend_filter',0):.2f}")
>                 elif close < sma_long: score -= w.get("sma_trend_filter", 0); notes_sell.append(f"SMA Trend Bear -{w.get('sma_trend_filter',0):.2f}")
>         if active.get("ehlers_supertrend"):
>             st_fast_dir, st_slow_dir = self._get_indicator_value("ST_Fast_Dir"), self._get_indicator_value("ST_Slow_Dir")
>             if st_fast_dir == 1 and st_slow_dir == 1: score += w.get("ehlers_supertrend_alignment", 0); notes_buy.append(f"EhlersST Bull +{w.get('ehlers_supertrend_alignment',0):.2f}")
>             elif st_fast_dir == -1 and st_slow_dir == -1: score -= w.get("ehlers_supertrend_alignment", 0); notes_sell.append(f"EhlersST Bear -{w.get('ehlers_supertrend_alignment',0):.2f}")
>         if active.get("macd"):
>             macd, signal = self._nz(self._get_indicator_value("MACD_Line")), self._nz(self._get_indicator_value("MACD_Signal"))
>             hist, prev_hist = self._safe_prev("MACD_Hist")
>             if not np.isnan(macd) and not np.isnan(signal):
>                 if macd > signal and hist > 0 and prev_hist <= 0: score += w.get("macd_alignment", 0); notes_buy.append(f"MACD Bull Cross +{w.get('macd_alignment',0):.2f}")
>                 elif macd < signal and hist < 0 and prev_hist >= 0: score -= w.get("macd_alignment", 0); notes_sell.append(f"MACD Bear Cross -{w.get('macd_alignment',0):.2f}")
>         if active.get("adx"):
>             adx, pdi, mdi = self._nz(self._get_indicator_value("ADX")), self._nz(self._get_indicator_value("PlusDI")), self._nz(self._get_indicator_value("MinusDI"))
>             if not np.isnan(adx) and adx > 20:
>                 if pdi > mdi: score += w.get("adx_strength", 0) * (adx/50.0); notes_buy.append(f"ADX Bull {adx:.1f} +{w.get('adx_strength',0) * (adx/50.0):.2f}")
>                 else: score -= w.get("adx_strength", 0) * (adx/50.0); notes_sell.append(f"ADX Bear {adx:.1f} -{w.get('adx_strength',0) * (adx/50.0):.2f}")
>         if active.get("ichimoku_cloud"):
>             tenkan, kijun, span_a, span_b, chikou = self._nz(self._get_indicator_value("Tenkan_Sen")), self._nz(self._get_indicator_value("Kijun_Sen")), self._nz(self._get_indicator_value("Senkou_Span_A")), self._nz(self._get_indicator_value("Senkou_Span_B")), self._nz(self._get_indicator_value("Chikou_Span"))
>             if not np.isnan(tenkan) and not np.isnan(kijun) and not np.isnan(span_a) and not np.isnan(span_b) and not np.isnan(chikou):
>                 if close > span_a and close > span_b and tenkan > kijun and chikou > close: score += w.get("ichimoku_confluence", 0); notes_buy.append(f"Ichimoku Bull +{w.get('ichimoku_confluence',0):.2f}")
>                 elif close < span_a and close < span_b and tenkan < kijun and chikou < close: score -= w.get("ichimoku_confluence", 0); notes_sell.append(f"Ichimoku Bear -{w.get('ichimoku_confluence',0):.2f}")
>         if active.get("psar"):
>             if self._get_indicator_value("PSAR_Dir") == 1: score += w.get("psar", 0); notes_buy.append(f"PSAR Bull +{w.get('psar',0):.2f}")
>             elif self._get_indicator_value("PSAR_Dir") == -1: score -= w.get("psar", 0); notes_sell.append(f"PSAR Bear -{w.get('psar',0):.2f}")
>         if active.get("vwap"):
>             vwap = self._nz(self._get_indicator_value("VWAP"))
>             if not np.isnan(vwap):
>                 if close > vwap: score += w.get("vwap", 0); notes_buy.append(f"VWAP Bull +{w.get('vwap',0):.2f}")
>                 elif close < vwap: score -= w.get("vwap", 0); notes_sell.append(f"VWAP Bear -{w.get('vwap',0):.2f}")
>         if active.get("vwma"):
>             vwma, sma = self._nz(self._get_indicator_value("VWMA")), self._nz(self._get_indicator_value("SMA_10"))
>             if not np.isnan(vwma) and not np.isnan(sma):
>                 if vwma > sma: score += w.get("vwma_cross", 0); notes_buy.append(f"VWMA Cross Bull +{w.get('vwma_cross',0):.2f}")
>                 elif vwma < sma: score -= w.get("vwma_cross", 0); notes_sell.append(f"VWMA Cross Bear -{w.get('vwma_cross',0):.2f}")
>         if active.get("sma_10"):
>             sma10 = self._nz(self._get_indicator_value("SMA_10"))
>             if not np.isnan(sma10):
>                 if close > sma10: score += w.get("sma_10", 0); notes_buy.append(f"SMA10 Bull +{w.get('sma_10',0):.2f}")
>                 elif close < sma10: score -= w.get("sma_10", 0); notes_sell.append(f"SMA10 Bear -{w.get('sma_10',0):.2f}")
>         if active.get("momentum"):
>             mom_score = 0.0
>             if not np.isnan(self._get_indicator_value("RSI")) and self._get_indicator_value("RSI") < isd.get("rsi_oversold", 30): mom_score += 1
>             elif not np.isnan(self._get_indicator_value("RSI")) and self._get_indicator_value("RSI") > isd.get("rsi_overbought", 70): mom_score -= 1
>             stoch_k, stoch_d = self._nz(self._get_indicator_value("StochRSI_K")), self._nz(self._get_indicator_value("StochRSI_D"))
>             if not np.isnan(stoch_k) and not np.isnan(stoch_d):
>                 if stoch_k > stoch_d and stoch_k < isd.get("stoch_rsi_oversold", 20): mom_score += 1
>                 elif stoch_k < stoch_d and stoch_k > isd.get("stoch_rsi_overbought", 80): mom_score -= 1
>             if not np.isnan(self._get_indicator_value("CCI")) and self._get_indicator_value("CCI") < isd.get("cci_oversold", -100): mom_score += 1
>             elif not np.isnan(self._get_indicator_value("CCI")) and self._get_indicator_value("CCI") > isd.get("cci_overbought", 100): mom_score -= 1
>             if not np.isnan(self._get_indicator_value("WR")) and self._get_indicator_value("WR") < isd.get("williams_r_oversold", -80): mom_score += 1
>             elif not np.isnan(self._get_indicator_value("WR")) and self._get_indicator_value("WR") > isd.get("williams_r_overbought", -20): mom_score -= 1
>             if not np.isnan(self._get_indicator_value("MFI")) and self._get_indicator_value("MFI") < isd.get("mfi_oversold", 20): mom_score += 1
>             elif not np.isnan(self._get_indicator_value("MFI")) and self._get_indicator_value("MFI") > isd.get("mfi_overbought", 80): mom_score -= 1
>             final_mom_score = w.get("momentum_rsi_stoch_cci_wr_mfi", 0) * self._clip(mom_score / 5.0)
>             score += final_mom_score
>             if final_mom_score > 0: notes_buy.append(f"Momentum Bull +{final_mom_score:.2f}")
>             elif final_mom_score < 0: notes_sell.append(f"Momentum Bear {final_mom_score:.2f}")
>         if active.get("bollinger_bands") and regime == "RANGING":
>             bb_u, bb_l = self._nz(self._get_indicator_value("BB_Upper")), self._nz(self._get_indicator_value("BB_Lower"))
>             if not np.isnan(bb_u) and not np.isnan(bb_l):
>                 if close < bb_l: score += w.get("bollinger_bands", 0); notes_buy.append(f"BB Reversal Bull +{w.get('bollinger_bands',0):.2f}")
>                 elif close > bb_u: score -= w.get("bollinger_bands", 0); notes_sell.append(f"BB Reversal Bear -{w.get('bollinger_bands',0):.2f}")
>         if active.get("volume_confirmation") and self._volume_confirm():
>             score_change = w.get("volume_confirmation", 0)
>             if score > 0: score += score_change; notes_buy.append(f"Vol Confirm +{score_change:.2f}")
>             elif score < 0: score -= score_change; notes_sell.append(f"Vol Confirm -{score_change:.2f}")
>         if active.get("obv"):
>             obv, obv_ema = self._nz(self._get_indicator_value("OBV")), self._nz(self._get_indicator_value("OBV_EMA"))
>             if not np.isnan(obv) and not np.isnan(obv_ema):
>                 if obv > obv_ema: score += w.get("obv_momentum", 0); notes_buy.append(f"OBV Bull +{w.get('obv_momentum',0):.2f}")
>                 elif obv < obv_ema: score -= w.get("obv_momentum", 0); notes_sell.append(f"OBV Bear -{w.get('obv_momentum',0):.2f}")
>         if active.get("cmf"):
>             cmf = self._nz(self._get_indicator_value("CMF"))
>             if not np.isnan(cmf) and cmf > 0.05: score += w.get("cmf_flow", 0); notes_buy.append(f"CMF Bull +{w.get('cmf_flow',0):.2f}")
>             elif not np.isnan(cmf) and cmf < -0.05: score -= w.get("cmf_flow", 0); notes_sell.append(f"CMF Bear -{w.get('cmf_flow',0):.2f}")
>         if active.get("volume_delta"):
>             vol_delta = self._nz(self._get_indicator_value("Volume_Delta"))
>             delta_thresh = self._nz(isd.get("volume_delta_threshold", 0.2))
>             if not np.isnan(vol_delta):
>                 if vol_delta > delta_thresh: score += w.get("volume_delta_signal", 0); notes_buy.append(f"VolDelta Bull +{w.get('volume_delta_signal',0):.2f}")
>                 elif vol_delta < -delta_thresh: score -= w.get("volume_delta_signal", 0); notes_sell.append(f"VolDelta Bear -{w.get('volume_delta_signal',0):.2f}")
>         if active.get("volatility_index"):
>             vol_idx = self._nz(self._get_indicator_value("Volatility_Index"))
>             if not np.isnan(vol_idx) and vol_idx > self.df["Volatility_Index"].rolling(50).mean().iloc[-1] * 1.5:
>                 score *= 0.75; notes_buy.append("High Vol Dampen"); notes_sell.append("High Vol Dampen")
>         if active.get("orderbook_imbalance"):
>             ob_score, ob_note = self._orderbook_score(orderbook_data, w.get("orderbook_imbalance", 0))
>             score += ob_score
>             if ob_note:
>                 if ob_score > 0: notes_buy.append(ob_note)
>                 else: notes_sell.append(ob_note)
>         if active.get("mtf_analysis"):
>             mtf_score, mtf_note = self._mtf_confluence(mtf_trends, w.get("mtf_trend_confluence", 0))
>             score += mtf_score
>             if mtf_note:
>                 if mtf_score > 0: notes_buy.append(mtf_note)
>                 else: notes_sell.append(mtf_note)
> 
>         base_th = max(float(self.config.get("signal_score_threshold", 2.0)), 1.0)
>         dyn_th = self._dynamic_threshold(base_th)
>         last_score = float(self.config.get("_last_score", 0.0))
>         hyster = float(self.config.get("hysteresis_ratio", 0.85))
2818,2907c1149,1150
<         now_ts = int(time.time())
< 
<         is_strong_buy = signal_score >= threshold
<         is_strong_sell = signal_score <= -threshold
< 
<         # Apply hysteresis to prevent immediate flip-flops
<         # If the bot previously issued a BUY signal and the current score is not a strong SELL, and not a strong BUY, it holds the BUY signal.
<         # This prevents it from flipping to HOLD or SELL too quickly if the score dips slightly.
<         if self._last_signal_score > 0 and signal_score > -threshold * hysteresis_ratio and not is_strong_buy:
<             final_signal = "BUY"
<         # If the bot previously issued a SELL signal and the current score is not a strong BUY, and not a strong SELL, it holds the SELL signal.
<         elif self._last_signal_score < 0 and signal_score < threshold * hysteresis_ratio and not is_strong_sell:
<             final_signal = "SELL"
<         elif is_strong_buy:
<             final_signal = "BUY"
<         elif is_strong_sell:
<             final_signal = "SELL"
< 
<         # Apply cooldown period
<         if final_signal != "HOLD":
<             if now_ts - self._last_signal_ts < cooldown_sec:
<                 self.logger.info(f"{NEON_YELLOW}Signal '{final_signal}' ignored due to cooldown ({cooldown_sec - (now_ts - self._last_signal_ts)}s remaining).{RESET}")
<                 final_signal = "HOLD"
<             else:
<                 self._last_signal_ts = now_ts # Update timestamp only if signal is issued
< 
<         # Update last signal score for next iteration's hysteresis
<         self._last_signal_score = signal_score
< 
<         self.logger.info(
<             f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
<         )
<         return final_signal, signal_score, signal_breakdown
< 
<     def calculate_entry_tp_sl(
<         self, current_price: Decimal, atr_value: Decimal, signal: Literal["BUY", "SELL"]
<     ) -> tuple[Decimal, Decimal]:
<         """Calculate Take Profit and Stop Loss levels."""
<         stop_loss_atr_multiple = Decimal(
<             str(self.config["trade_management"]["stop_loss_atr_multiple"])
<         )
<         take_profit_atr_multiple = Decimal(
<             str(self.config["trade_management"]["take_profit_atr_multiple"])
<         )
<         price_precision_str = "0." + "0" * (self.config["trade_management"]["price_precision"] - 1) + "1"
< 
< 
<         if signal == "BUY":
<             stop_loss = current_price - (atr_value * stop_loss_atr_multiple)
<             take_profit = current_price + (atr_value * take_profit_atr_multiple)
<         elif signal == "SELL":
<             stop_loss = current_price + (atr_value * stop_loss_atr_multiple)
<             take_profit = current_price - (atr_value * take_profit_atr_multiple)
<         else:
<             return Decimal("0"), Decimal("0")  # Should not happen for valid signals
< 
<         return take_profit.quantize(
<             Decimal(price_precision_str), rounding=ROUND_DOWN
<         ), stop_loss.quantize(Decimal(price_precision_str), rounding=ROUND_DOWN)
< 
< 
< def display_indicator_values_and_price(
<     config: dict[str, Any],
<     logger: logging.Logger,
<     current_price: Decimal,
<     df: pd.DataFrame,
<     orderbook_data: dict | None,
<     mtf_trends: dict[str, str],
<     signal_breakdown: dict | None = None # New parameter
< ) -> None:
<     """Display current price and calculated indicator values."""
<     logger.info(f"{NEON_BLUE}--- Current Market Data & Indicators ---{RESET}")
<     logger.info(f"{NEON_GREEN}Current Price: {current_price.normalize()}{RESET}")
< 
<     analyzer = TradingAnalyzer(df, config, logger, config["symbol"])
< 
<     if analyzer.df.empty:
<         logger.warning(
<             f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
<         )
<         return
< 
<     logger.info(f"{NEON_CYAN}--- Indicator Values ---{RESET}")
<     for indicator_name, value in analyzer.indicator_values.items():
<         color = INDICATOR_COLORS.get(indicator_name, NEON_YELLOW)
<         # Format Decimal values for consistent display
<         if isinstance(value, Decimal):
<             logger.info(f"  {color}{indicator_name}: {value.normalize()}{RESET}")
<         elif isinstance(value, float):
<             logger.info(f"  {color}{indicator_name}: {value:.8f}{RESET}")
---
>         if np.sign(score) != np.sign(last_score) and abs(score) < abs(last_score) * hyster:
>             final_signal = "HOLD"; self.logger.info(f"{NEON_YELLOW}Signal held by hysteresis. Score {score:.2f} vs last {last_score:.2f}{RESET}")
2909,2931c1152,1163
<             logger.info(f"  {color}{indicator_name}: {value}{RESET}")
< 
<     if analyzer.fib_levels:
<         logger.info(f"{NEON_CYAN}--- Fibonacci Levels ---{RESET}")
<         logger.info("")  # Added newline for spacing
<         for level_name, level_price in analyzer.fib_levels.items():
<             logger.info(f"  {NEON_YELLOW}{level_name}: {level_price.normalize()}{RESET}")
< 
<     if mtf_trends:
<         logger.info(f"{NEON_CYAN}--- Multi-Timeframe Trends ---{RESET}")
<         logger.info("")  # Added newline for spacing
<         for tf_indicator, trend in mtf_trends.items():
<             logger.info(f"  {NEON_YELLOW}{tf_indicator}: {trend}{RESET}")
< 
<     if signal_breakdown:
<         logger.info(f"{NEON_CYAN}--- Signal Score Breakdown ---{RESET}")
<         # Sort by absolute contribution for better readability
<         sorted_breakdown = sorted(signal_breakdown.items(), key=lambda item: abs(item[1]), reverse=True)
<         for indicator, contribution in sorted_breakdown:
<             color = (Fore.GREEN if contribution > 0 else (Fore.RED if contribution < 0 else Fore.YELLOW))
<             logger.info(f"  {color}{indicator:<25}: {contribution: .2f}{RESET}")
< 
<     logger.info(f"{NEON_BLUE}--------------------------------------{RESET}")
---
>             if score >= dyn_th: final_signal = "BUY"
>             elif score <= -dyn_th: final_signal = "SELL"
>         cooldown = int(self.config.get("cooldown_sec", 0))
>         now_ts, last_ts = int(time.time()), int(self.config.get("_last_signal_ts", 0))
>         if cooldown > 0 and now_ts - last_ts < cooldown and final_signal != "HOLD":
>             final_signal = "HOLD"; self.logger.info(f"{NEON_YELLOW}Signal ignored due to cooldown.{RESET}")
>         self.config["_last_score"] = float(score)
>         if final_signal in ("BUY", "SELL"): self.config["_last_signal_ts"] = now_ts
>         if notes_buy: self.logger.info(f"{NEON_GREEN}Buy Factors: {', '.join(notes_buy)}{RESET}")
>         if notes_sell: self.logger.info(f"{NEON_RED}Sell Factors: {', '.join(notes_sell)}{RESET}")
>         self.logger.info(f"{NEON_PURPLE}Regime: {regime} | Score: {score:.2f} | DynThresh: {dyn_th:.2f} | Final: {final_signal}{RESET}")
>         return final_signal, float(score)
2932a1165,1220
> # --- NEW: Helper functions for main loop ---
> def get_spread_bps(orderbook):
>     try:
>         best_ask, best_bid = Decimal(orderbook["a"][0][0]), Decimal(orderbook["b"][0][0])
>         mid = (best_ask + best_bid) / 2
>         return float((best_ask - best_bid) / mid * 10000)
>     except Exception: return 0.0
> 
> def expected_value(perf: PerformanceTracker, n=50, fee_bps=2.0, slip_bps=2.0):
>     trades = perf.trades[-n:]
>     if not trades: return 1.0 # Default to positive if no history
>     wins = [Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) > 0]
>     losses = [-Decimal(str(t["pnl"])) for t in trades if Decimal(str(t["pnl"])) <= 0]
>     win_rate = (len(wins) / len(trades)) if trades else 0.0
>     avg_win = (sum(wins) / len(wins)) if wins else Decimal("0")
>     avg_loss = (sum(losses) / len(losses)) if losses else Decimal("0")
>     cost = Decimal(str((fee_bps + slip_bps) / 10000.0))
>     ev = win_rate * (avg_win * (1 - cost)) - (1 - win_rate) * (avg_loss * (1 + cost))
>     return float(ev)
> 
> def in_allowed_session(cfg) -> bool:
>     sess = cfg.get("session_filter", {})
>     if not sess.get("enabled", False): return True
>     now = datetime.now(TIMEZONE).strftime("%H:%M")
>     for w in sess.get("utc_allowed", []):
>         if w[0] <= now <= w[1]: return True
>     return False
> 
> def adapt_exit_params(pt: PerformanceTracker, cfg: dict) -> tuple[Decimal, Decimal]:
>     tp_mult = Decimal(str(cfg["trade_management"]["take_profit_atr_multiple"]))
>     sl_mult = Decimal(str(cfg["trade_management"]["stop_loss_atr_multiple"]))
>     recent = pt.trades[-100:]
>     if not recent or len(recent) < 20: return tp_mult, sl_mult
>     wins = [t for t in recent if Decimal(str(t.get("pnl","0"))) > 0]
>     losses = [t for t in recent if Decimal(str(t.get("pnl","0"))) <= 0]
>     if wins and losses:
>         avg_win, avg_loss = sum(Decimal(str(t["pnl"])) for t in wins) / len(wins), -sum(Decimal(str(t["pnl"])) for t in losses) / len(losses)
>         rr = (avg_win / avg_loss) if avg_loss > 0 else Decimal("1")
>         tilt = Decimal(min(0.5, max(-0.5, float(rr - 1.0))))
>         return (tp_mult + tilt, max(Decimal("1.0"), sl_mult - tilt/2))
>     return tp_mult, sl_mult
> 
> def random_tune_weights(cfg_path="config.json", k=50, jitter=0.2):
>     print("Running random weight tuning...")
>     with open(cfg_path,encoding="utf-8") as f: cfg=json.load(f)
>     base = cfg["weight_sets"]["default_scalping"]
>     best_cfg, best_score = base, -1e9
>     for _ in range(k):
>         trial = {key: max(0.0, v * (1 + random.uniform(-jitter, jitter))) for key,v in base.items()}
>         proxy = sum(trial.get(x,0) for x in ["ema_alignment","ehlers_supertrend_alignment","macd_alignment","adx_strength"])
>         if proxy > best_score:
>             best_cfg, best_score = trial, proxy
>     cfg["weight_sets"]["default_scalping"] = best_cfg
>     with open(cfg_path,"w",encoding="utf-8") as f: json.dump(cfg,f,indent=4)
>     print(f"New weights saved to {cfg_path}")
>     return best_cfg
2936,2937c1224
<     """Orchestrate the bot's operation."""
<     # The logger is now initialized globally.
---
>     logger = setup_logger("wgwhalex_bot")
2941,2970d1227
<     # Validate interval format at startup
<     valid_bybit_intervals = [
<         "1",
<         "3",
<         "5",
<         "15",
<         "30",
<         "60",
<         "120",
<         "240",
<         "360",
<         "720",
<         "D",
<         "W",
<         "M",
<     ]
< 
<     if config["interval"] not in valid_bybit_intervals:
<         logger.error(
<             f"{NEON_RED}Invalid primary interval '{config['interval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
<         )
<         sys.exit(1)
< 
<     for htf_interval in config["mtf_analysis"]["higher_timeframes"]:
<         if htf_interval not in valid_bybit_intervals:
<             logger.error(
<                 f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
<             )
<             sys.exit(1)
< 
2973d1229
<     logger.info(f"Trade Management Enabled: {config['trade_management']['enabled']}")
2975c1231,1232
<     position_manager = PositionManager(config, logger, config["symbol"])
---
>     pybit_client = PybitTradingClient(config, logger)
>     position_manager = PositionManager(config, logger, config["symbol"], pybit_client)
2976a1234,1235
>     exec_sync = ExchangeExecutionSync(config["symbol"], pybit_client, logger, config, position_manager, performance_tracker) if config["execution"]["live_sync"]["enabled"] else None
>     heartbeat = PositionHeartbeat(config["symbol"], pybit_client, logger, config, position_manager) if config["execution"]["live_sync"]["heartbeat"]["enabled"] else None
2980,3002c1239,1276
<             logger.info(f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
<             current_price = fetch_current_price(config["symbol"], logger)
<             if current_price is None:
<                 alert_system.send_alert(
<                     f"[{config['symbol']}] Failed to fetch current price. Skipping loop.", "WARNING"
<                 )
<                 time.sleep(config["loop_delay"])
<                 continue
< 
<             df = fetch_klines(config["symbol"], config["interval"], 1000, logger)
<             if df is None or df.empty:
<                 alert_system.send_alert(
<                     f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
<                     "WARNING",
<                 )
<                 time.sleep(config["loop_delay"])
<                 continue
< 
<             orderbook_data = None
<             if config["indicators"].get("orderbook_imbalance", False):
<                 orderbook_data = fetch_orderbook(
<                     config["symbol"], config["orderbook_limit"], logger
<                 )
---
>             logger.info(f"{NEON_PURPLE}--- New Loop ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}")
> 
>             guard = config.get("risk_guardrails", {})
>             if guard.get("enabled", False):
>                 equity = Decimal(str(config["trade_management"]["account_balance"])) + performance_tracker.total_pnl
>                 day_loss = performance_tracker.day_pnl()
>                 max_day_loss = (Decimal(str(guard.get("max_day_loss_pct", 3.0))) / 100) * equity
>                 max_dd = (Decimal(str(guard.get("max_drawdown_pct", 8.0))) / 100) * equity
>                 if (max_day_loss > 0 and day_loss <= -max_day_loss) or (performance_tracker.max_drawdown >= max_dd):
>                     logger.error(f"{NEON_RED}KILL SWITCH: Risk limits hit. Cooling down.{RESET}")
>                     time.sleep(int(guard.get("cooldown_after_kill_min", 120)) * 60)
>                     continue
> 
>             if not in_allowed_session(config):
>                 logger.info(f"{NEON_BLUE}Outside allowed session. Holding.{RESET}")
>                 time.sleep(config["loop_delay"]); continue
> 
>             current_price = pybit_client.fetch_current_price(config["symbol"])
>             if current_price is None: time.sleep(config["loop_delay"]); continue
> 
>             df = pybit_client.fetch_klines(config["symbol"], config["interval"], 1000)
>             if df is None or df.empty: time.sleep(config["loop_delay"]); continue
> 
>             orderbook_data = pybit_client.fetch_orderbook(config["symbol"], config["orderbook_limit"]) if config["indicators"].get("orderbook_imbalance") else None
> 
>             if guard.get("enabled", False) and orderbook_data:
>                 spread_bps = get_spread_bps(orderbook_data)
>                 if spread_bps > float(guard.get("spread_filter_bps", 5.0)):
>                     logger.warning(f"{NEON_YELLOW}Spread too high ({spread_bps:.1f} bps). Holding.{RESET}")
>                     time.sleep(config["loop_delay"]); continue
> 
>             if guard.get("ev_filter_enabled", True) and expected_value(performance_tracker) <= 0:
>                 logger.warning(f"{NEON_YELLOW}Negative EV detected. Holding.{RESET}")
>                 time.sleep(config["loop_delay"]); continue
> 
>             tp_mult, sl_mult = adapt_exit_params(performance_tracker, config)
>             config["trade_management"]["take_profit_atr_multiple"] = float(tp_mult)
>             config["trade_management"]["stop_loss_atr_multiple"] = float(sl_mult)
3007,3008c1281
<                     logger.debug(f"Fetching klines for MTF interval: {htf_interval}")
<                     htf_df = fetch_klines(config["symbol"], htf_interval, 1000, logger)
---
>                     htf_df = pybit_client.fetch_klines(config["symbol"], htf_interval, 1000)
3011,3016c1284
<                             temp_htf_analyzer = TradingAnalyzer(
<                                 htf_df, config, logger, config["symbol"]
<                             )
<                             trend = temp_htf_analyzer._get_mtf_trend(
<                                 temp_htf_analyzer.df, trend_ind
<                             )
---
>                             trend = indicators._get_mtf_trend(htf_df, config, logger, config["symbol"], trend_ind)
3018,3031c1286
<                             logger.debug(
<                                 f"MTF Trend ({htf_interval}, {trend_ind}): {trend}"
<                             )
<                     else:
<                         logger.warning(
<                             f"{NEON_YELLOW}Could not fetch klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
<                         )
<                     time.sleep(
<                         config["mtf_analysis"]["mtf_request_delay_seconds"]
<                     )  # Delay between MTF requests
< 
<             display_indicator_values_and_price(
<                 config, logger, current_price, df, orderbook_data, mtf_trends
<             )
---
>                     time.sleep(config["mtf_analysis"]["mtf_request_delay_seconds"])
3033a1289
>             if analyzer.df.empty: time.sleep(config["loop_delay"]); continue
3035,3048c1291,1293
<             if analyzer.df.empty:
<                 alert_system.send_alert(
<                     f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
<                     "WARNING",
<                 )
<                 time.sleep(config["loop_delay"])
<                 continue
< 
<             trading_signal, signal_score, signal_breakdown = analyzer.generate_trading_signal(
<                 current_price, orderbook_data, mtf_trends
<             )
<             atr_value = Decimal(
<                 str(analyzer._get_indicator_value("ATR", Decimal("0.01")))
<             ) # Default to a small positive value if ATR is missing
---
>             atr_value = Decimal(str(analyzer._get_indicator_value("ATR", Decimal("0.1"))))
>             config["_last_atr"] = str(atr_value)
>             trading_signal, signal_score = analyzer.generate_trading_signal(current_price, orderbook_data, mtf_trends)
3049a1295,1296
>             for pos in position_manager.get_open_positions():
>                 position_manager.trail_stop(pos, current_price, atr_value)
3050a1298
>             position_manager.try_pyramid(current_price, atr_value)
3052,3084c1300,1302
<             # Display current state after analysis and signal generation
<             display_indicator_values_and_price(
<                 config, logger, current_price, df, orderbook_data, mtf_trends, signal_breakdown
<             )
< 
<             if (
<                 trading_signal == "BUY"
<                 and signal_score >= config["signal_score_threshold"]
<             ):
<                 logger.info(
<                     f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
<                 )
<                 position_manager.open_position("BUY", current_price, atr_value)
<             elif (
<                 trading_signal == "SELL"
<                 and signal_score <= -config["signal_score_threshold"]
<             ):
<                 logger.info(
<                     f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
<                 )
<                 position_manager.open_position("SELL", current_price, atr_value)
<             else:
<                 logger.info(
<                     f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
<                 )
< 
<             open_positions = position_manager.get_open_positions()
<             if open_positions:
<                 logger.info(f"{NEON_CYAN}Open Positions: {len(open_positions)}{RESET}")
<                 for pos in open_positions:
<                     logger.info(
<                         f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}){RESET}"
<                     )
---
>             if trading_signal in ("BUY", "SELL"):
>                 conviction = float(min(2.0, max(0.0, abs(signal_score) / max(config["signal_score_threshold"], 1.0))))
>                 position_manager.open_position(trading_signal, current_price, atr_value, conviction)
3086c1304
<                 logger.info(f"{NEON_CYAN}No open positions.{RESET}")
---
>                 logger.info(f"{NEON_BLUE}No strong signal. Holding. Score: {signal_score:.2f}{RESET}")
3088,3091c1306,1307
<             perf_summary = performance_tracker.get_summary()
<             logger.info(
<                 f"{NEON_YELLOW}Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
<             )
---
>             config["_last_price"] = str(current_price) # Store last price
>             config["_last_signal"] = trading_signal # Store last signal
3093,3095c1309,1315
<             logger.info(
<                 f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
<             )
---
>             if exec_sync: exec_sync.poll()
>             if heartbeat: heartbeat.tick()
> 
>             logger.info(f"{NEON_YELLOW}Performance: {performance_tracker.get_summary()}{RESET}")
>             logger.info(f"{NEON_PURPLE}--- Loop Finished. Waiting {config['loop_delay']}s ---{RESET}")
>             
>             save_bot_state(config, position_manager, performance_tracker, logger) # Save bot state
3099,3101c1319
<             alert_system.send_alert(
<                 f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}", "ERROR"
<             )
---
>             alert_system.send_alert(f"Unhandled error in main loop: {e}", "ERROR")
3105d1322
< 
3107,3108c1324
<     main()
< 
---
>     # random_tune_weights(CONFIG_FILE)
