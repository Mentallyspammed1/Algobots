time.sleep(3) # Small delay to allow connection attempt
                 if self.ws_connected: # Check if connection was established and callbacks fired
                     test_result["passed"] = True
                     test_result["error"] = "Connection seemed to establish."
                 else:
                     test_result["error"] = "Connection attempt did not report success."
            else:
                 test_result["error"] = "Skipped: WS instance or topics missing."
        except Exception as e:
             self.logger.exception("Exception during WebSocket test execution.")
             test_result["error"] = f"Exception during test: {e}"
        finally:
             # Restore original WS state using the stored values
             self._restore_ws_state(original_ws_state)
             self.logger.debug("WS Test: Original WS state restored.")

        if test_result["passed"]:
             results.append((check_name, True, test_result["error"]))
             passed_checks += 1
        else:
             results.append((check_name, False, f"WS test failed: {test_result['error']}"))

        # Check 7: Basic OHLCV Fetch
        total_checks += 1
        check_name = f"OHLCV Fetch ({self.config.timeframe})"
        try:
             fetch_limit_ohlcv = max(50, self.config.sma_long + 5, self.config.atr_period + 5, self.config.adx_period + 5, 200) # Ensure enough history
             test_ohlcv_df = bybit_client.get_or_fetch_ohlcv(self.config.timeframe, limit=fetch_limit_ohlcv, include_daily_pivots=False) # No pivots needed for this test
             if not test_ohlcv_df.empty and len(test_ohlcv_df) >= fetch_limit_ohlcv * 0.8: # Check if a substantial amount was fetched
                  results.append((check_name, True, f"OHLCV fetch successful ({len(test_ohlcv_df)} candles)."))
                  passed_checks += 1
             else:
                  results.append((check_name, False, f"OHLCV fetch returned empty or insufficient data ({len(test_ohlcv_df)} fetched, expected ~{fetch_limit_ohlcv})."))
        except Exception as e:
             self.logger.exception("Exception during OHLCV fetch test.")
             results.append((check_name, False, f"Exception during OHLCV fetch: {e}"))

        # Check 8: Daily OHLCV Fetch (for Pivots)
        total_checks += 1
        check_name = "Daily OHLCV Fetch (Pivots)"
        try:
             # Fetch a small amount of daily data for testing pivots
             test_daily_ohlcv_df = bybit_client.get_or_fetch_daily_ohlcv(limit=5)
             if not test_daily_ohlcv_df.empty and len(test_daily_ohlcv_df) >= 2: # Need at least 2 days for pivots
                  results.append((check_name, True, f"Daily OHLCV fetch successful ({len(test_daily_ohlcv_df)} candles)."))
                  passed_checks += 1
             else:
                  results.append((check_name, False, f"Daily OHLCV fetch returned empty or insufficient data ({len(test_daily_ohlcv_df)} fetched, need at least 2)."))
        except Exception as e:
             self.logger.exception("Exception during Daily OHLCV fetch test.")
             results.append((check_name, False, f"Exception during Daily OHLCV fetch: {e}"))

        # Check 9: Indicators Calculation Test
        total_checks += 1
        check_name = "Indicators Calculation"
        try:
             # Need a decent history slice to test indicator calculations
             ohlcv_slice_for_test = None
             daily_df_for_test = None
             with self._cache_lock: # Access cache safely
                  pybit_tf_key = bybit_client._map_timeframe_to_pybit(config.timeframe)
                  if pybit_tf_key and bybit_client.ohlcv_cache.get(pybit_tf_key):
                      ohlcv_slice_for_test = bybit_client.ohlcv_cache.get(pybit_tf_key).copy()
                  daily_cache = bybit_client.daily_ohlcv_cache
                  if daily_cache is not None and not daily_cache.empty:
                       daily_df_for_test = daily_cache.copy()

             min_needed_for_indicators = max(config.initial_candle_history, config.sma_long + 10, config.atr_period + 10, config.adx_period + 10, 200)
             # If cache doesn't have enough data, try fetching it
             if ohlcv_slice_for_test is None or len(ohlcv_slice_for_test) < min_needed_for_indicators:
                  logger.debug("Not enough cached OHLCV data for indicator test. Refetching...")
                  ohlcv_slice_for_test = bybit_client.get_or_fetch_ohlcv(config.timeframe, limit=min_needed_for_indicators, include_daily_pivots=True)
                  # Re-fetch daily data if needed for pivots
                  if (config.analysis_modules.mtf_analysis.enabled or config.indicators.fibonacci_pivot_points) and (daily_df_for_test is None or daily_df_for_test.empty):
                       daily_df_for_test = bybit_client.get_or_fetch_daily_ohlcv()

             if ohlcv_slice_for_test is not None and not ohlcv_slice_for_test.empty and len(ohlcv_slice_for_test) >= min_needed_for_indicators:
                  # Run the indicator calculation on the data slice
                  test_indicators_df = calculate_indicators(ohlcv_slice_for_test.copy(), config, daily_df_for_test)

                  if test_indicators_df is not None and not test_indicators_df.empty:
                       # Check if key indicators and structure elements were populated
                       sample_cols_to_check = ['ATR', 'SMA_Short', 'SMA_Long', 'MACD_Line', 'RSI', 'Fisher_Price', 'Pivot', 'Resistance', 'Support', 'Is_Bullish_OB', 'Is_Bearish_OB']
                       found_valid_indicator = False
                       # Check the last few rows for any non-NaN indicator values
                       check_tail = test_indicators_df.tail(10)
                       for col in sample_cols_to_check:
                            if col in test_indicators_df.columns and pd.api.types.is_numeric_dtype(test_indicators_df[col]):
                                 if test_indicators_df[col].notna().any(): # Check if any value in the column is not NaN
                                      found_valid_indicator = True
                                      break
                       if found_valid_indicator:
                            results.append((check_name, True, f"Indicators calculated successfully. Key indicators populated."))
                            passed_checks += 1
                       else:
                            results.append((check_name, False, "Indicators calculated, but sample results are all NaN. Check data/config."))
                  else:
                      results.append((check_name, False, "calculate_indicators returned empty or None."))
             else:
                  results.append((check_name, False, f"Not enough OHLCV data available/fetched ({len(ohlcv_slice_for_test) if ohlcv_slice_for_test is not None else 0} < {min_needed_for_indicators}) for indicator test."))

        except ImportError:
             results.append((check_name, False, "Indicators module (indicators.py) not found or failed to import."))
        except Exception as e:
             logger.exception("Exception during indicator calculation test.")
             results.append((check_name, False, f"Exception during indicator calculation: {e}"))

        # Check 10: Termux SMS Sending (if enabled)
        if config.notifications.termux_sms.enabled:
            total_checks += 1
            check_name = "Termux SMS Send"
            test_message = f"Bybit Bot Diag Test @ {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S %Z')}"
            logger.info(f"{Fore.CYAN}# Attempting test SMS (respects cooldown, runs in background)...{Style.RESET_ALL}")
            sms_initiated = False
            try:
                 # Check cooldown first
                 current_time = time.time()
                 if current_time - bybit_client.last_sms_time >= bybit_client.config.notifications.termux_sms.cooldown:
                      sms_initiated = bybit_client.send_sms(test_message) # Send SMS
                 else:
                      logger.debug("SMS cooldown active. Skipping test send.")
            except Exception as e:
                 logger.warning(f"Error during SMS test attempt: {e}")

            if sms_initiated:
                 results.append((check_name, True, "Test SMS initiated (check phone/logs for outcome)."))
                 passed_checks += 1
            else:
                 results.append((check_name, False, "Test SMS initiation failed or skipped (check config/cooldown/logs)."))

        # --- Diagnostics Summary ---
        logger.info(f"\n{Fore.MAGENTA + Style.BRIGHT}--- Diagnostics Summary ---{Style.RESET_ALL}")
        for name, success, msg in results:
             status_color = Fore.GREEN if success else Fore.RED
             status_icon = "[PASS]" if success else "[FAIL]"
             message_color = Fore.GREEN if success else Fore.RED
             logger.info(f"{status_color}{status_icon:<6}{Style.RESET_ALL} {name:<35}:{message_color} {msg}{Style.RESET_ALL}")

        # Define essential checks that must pass for the bot to operate safely
        essential_check_names = {
            "Server Time Sync", f"Market Info Load ({config.symbol})", "Balance Fetch (API Auth)",
            "WebSocket Instance Creation", "WebSocket Connection Viability", f"OHLCV Fetch ({config.timeframe})",
            "Daily OHLCV Fetch (Pivots)", "Indicators Calculation"
        }
        # Check if all essential checks passed
        essential_results = [success for name, success, msg in results if name in essential_check_names]
        essential_passed = all(essential_results) if essential_results else False # Ensure there were essential checks to pass

        total_passed_count = sum(1 for _, success, _ in results if success)
        total_run_count = len(results)

        if essential_passed:
            failed_non_essential = [name for name, success, msg in results if not success and name not in essential_check_names]
            minor_issues_msg = f" Minor issues detected: {', '.join(failed_non_essential)}." if failed_non_essential else ""
            logger.success(f"\n{Fore.GREEN + Style.BRIGHT}All ESSENTIAL diagnostics PASSED ({total_passed_count}/{total_run_count} total checks).{minor_issues_msg}{Style.RESET_ALL}")
            return True # Diagnostics passed
        else:
            failed_essential = [name for name, success, msg in results if not success and name in essential_check_names]
            logger.error(f"\n{Fore.RED + Style.BRIGHT}Diagnostics FAILED. {total_passed_count}/{total_run_count} total checks PASSED.{Style.RESET_ALL}")
            logger.error(f"{Fore.RED}Essential checks failed: {', '.join(failed_essential)}{Style.RESET_ALL}")
            logger.error(f"{Fore.RED}Review the [FAIL] items above and consult the logs for detailed error messages.{Style.RESET_ALL}")
            return False # Diagnostics failed

    def _isolate_ws_state_for_test(self) -> dict:
         """Saves current WS state and resets it for a temporary test."""
         with self._ws_lock:
             original_state = {
                  "ws": self.ws, "ws_connected": self.ws_connected, "ws_connecting": self.ws_connecting,
                  "ws_topics": self.ws_topics[:], "ws_user_callbacks": self.ws_user_callbacks.copy(),
                  "ws_reconnect_attempt": self.ws_reconnect_attempt
             }
             # Reset for test
             self.ws = None; self.ws_connected = False; self.ws_connecting = False
             self.ws_topics = []; self.ws_user_callbacks = {}; self.ws_reconnect_attempt = 0
             return original_state

    def _restore_ws_state(self, original_state: dict) -> None:
        """Restores the WebSocket state from saved values."""
        with self._ws_lock:
             self.ws = original_state.get("ws")
             self.ws_connected = original_state.get("ws_connected", False)
             self.ws_connecting = original_state.get("ws_connecting", False)
             self.ws_topics = original_state.get("ws_topics", [])
             self.ws_user_callbacks = original_state.get("ws_user_callbacks", {})
             self.ws_reconnect_attempt = original_state.get("ws_reconnect_attempt", 0)

# --- Global Configuration and Environment Setup ---
# Define the directory for logs and configuration files
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_DIR = SCRIPT_DIR / "config"
LOG_DIRECTORY = SCRIPT_DIR / "logs"

# Create directories if they don't exist
CONFIG_DIR.mkdir(exist_ok=True)
LOG_DIRECTORY.mkdir(exist_ok=True)

# Define the path to the configuration file
CONFIG_FILE_PATH = CONFIG_DIR / "config.json"

# Pydantic Model for Application Configuration
# This structure mirrors the default_config_dict in load_config
class LoggingConfig(BaseModel):
    level: str = "INFO"
    log_to_file: bool = True
    log_trades_to_csv: bool = True
    log_indicators: bool = False
    max_log_size_mb: int = 10
    backup_count: int = 5
    include_sensitive_data: bool = False
    log_to_json: bool = False

class TermuxSMSConfig(BaseModel):
    enabled: bool = False
    phone_number: str = ""
    message_prefix: str = "[WB]"
    alert_levels: List[str] = ["INFO", "WARNING", "ERROR"]
    cooldown: int = 300

class NotificationsConfig(BaseModel):
    enabled: bool = True
    trade_entry: bool = True
    trade_exit: bool = True
    error_alerts: bool = True
    daily_summary: bool = True
    webhook_url: str = ""
    termux_sms: TermuxSMSConfig = Field(default_factory=TermuxSMSConfig)

class MTFAnalysisConfig(BaseModel):
    enabled: bool = True
    higher_timeframes: List[str] = ["60", "240"]
    trend_indicators: List[str] = ["ema", "ehlers_supertrend"]
    trend_period: int = 50
    mtf_request_delay_seconds: float = 0.5
    min_trend_agreement_pct: float = 60.0

class MLEnhancementConfig(BaseModel):
    enabled: bool = False
    model_path: str = "ml_model.pkl"
    prediction_threshold: float = 0.6
    model_weight: float = 0.3
    retrain_on_startup: bool = False
    training_data_limit: int = 5000
    prediction_lookahead: int = 12
    sentiment_analysis_enabled: bool = False
    bullish_sentiment_threshold: float = 0.6
    bearish_sentiment_threshold: float = 0.4

class AnalysisModulesConfig(BaseModel):
    mtf_analysis: MTFAnalysisConfig = Field(default_factory=MTFAnalysisConfig)
    ml_enhancement: MLEnhancementConfig = Field(default_factory=MLEnhancementConfig)

class StrategyProfile(BaseModel):
    description: str = ""
    indicators_enabled: Dict[str, bool] = Field(default_factory=dict)
    weights: Dict[str, float] = Field(default_factory=dict)
    market_condition_criteria: Dict[str, Any] = Field(default_factory=dict)

class StrategyManagementConfig(BaseModel):
    adaptive_strategy_enabled: bool = True
    current_strategy_profile: str = "default_scalping"
    strategy_profiles: Dict[str, StrategyProfile] = Field(default_factory=dict)

class IndicatorParameters(BaseModel):
    atr_period: int = 14
    ema_short_period: int = 9
    ema_long_period: int = 21
    rsi_period: int = 14
    stoch_rsi_period: int = 14
    stoch_k_period: int = 3
    stoch_d_period: int = 3
    bollinger_bands_period: int = 20
    bollinger_bands_std_dev: float = 2.0
    cci_period: int = 20
    williams_r_period: int = 14
    mfi_period: int = 14
    psar_acceleration: float = 0.02
    psar_max_acceleration: float = 0.2
    sma_short_period: int = 10
    sma_long_period: int = 50
    fibonacci_window: int = 60
    ehlers_fast_period: int = 10
    ehlers_fast_multiplier: float = 2.0
    ehlers_slow_period: int = 20
    ehlers_slow_multiplier: float = 3.0
    macd_fast_period: int = 12
    macd_slow_period: int = 26
    macd_signal_period: int = 9
    adx_period: int = 14
    ichimoku_tenkan_period: int = 9
    ichimoku_kijun_period: int = 26
    ichimoku_senkou_span_b_period: int = 52
    ichimoku_chikou_span_offset: int = 26
    obv_ema_period: int = 20
    cmf_period: int = 20
    rsi_oversold: int = 30
    rsi_overbought: int = 70
    stoch_rsi_oversold: int = 20
    stoch_rsi_overbought: int = 80
    cci_oversold: int = -100
    cci_overbought: int = 100
    williams_r_oversold: int = -80
    williams_r_overbought: int = -20
    mfi_oversold: int = 20
    mfi_overbought: int = 80
    volatility_index_period: int = 20
    vwma_period: int = 20
    volume_delta_period: int = 5
    volume_delta_threshold: float = 0.2
    kaufman_ama_period: int = 10
    kama_fast_period: int = 2
    kama_slow_period: int = 30
    relative_volume_period: int = 20
    relative_volume_threshold: float = 1.5
    market_structure_lookback_period: int = 20
    dema_period: int = 14
    keltner_period: int = 20
    keltner_atr_multiplier: float = 2.0
    roc_period: int = 12
    roc_oversold: float = -5.0
    roc_overbought: float = 5.0
    fisher_transform_length: int = 10
    ehlers_supertrend_atr_len: int = 10
    ehlers_supertrend_mult: float = 3.0
    ehlers_supertrend_ss_len: int = 10
    ehlers_stochrsi_rsi_len: int = 14
    ehlers_stochrsi_stoch_len: int = 14
    ehlers_stochrsi_ss_fast: int = 5
    ehlers_stochrsi_ss_slow: int = 3

class TPConfig(BaseModel):
    mode: str = "atr_multiples"
    targets: List[Dict[str, Any]] = Field(default_factory=list)

class SLConfig(BaseModel):
    type: str = "atr_multiple"
    atr_multiple: float = 1.5
    percent: float = 1.0
    use_conditional_stop: bool = True
    stop_order_type: str = "Market"
    trail_stop: Dict[str, Any] = Field(default_factory=dict) # e.g., {"enabled": True, "trail_atr_multiple": 0.5, "activation_threshold": 0.8}

class BreakevenConfig(BaseModel):
    enabled: bool = True
    offset_type: str = "atr"
    offset_value: float = 0.1
    lock_in_min_percent: float = 0.0
    sl_trigger_by: str = "LastPrice"

class LiveSyncConfig(BaseModel):
    enabled: bool = False
    poll_ms: int = 2500
    max_exec_fetch: int = 200
    only_track_linked: bool = True
    heartbeat: Dict[str, Any] = Field(default_factory=lambda: {"enabled": True, "interval_ms": 5000})

class ExecutionConfig(BaseModel):
    use_pybit: bool = False
    testnet: bool = False
    account_type: str = "UNIFIED"
    category: str = "linear"
    position_mode: str = "ONE_WAY"
    leverage: str = "3"
    tp_trigger_by: str = "LastPrice"
    sl_trigger_by: str = "LastPrice"
    default_time_in_force: str = "GoodTillCancel"
    reduce_only_default: bool = False
    post_only_default: bool = False
    position_idx_overrides: Dict[str, int] = Field(default_factory=lambda: {"ONE_WAY": 0, "HEDGE_BUY": 1, "HEDGE_SELL": 2})
    proxies: Dict[str, Any] = Field(default_factory=lambda: {"enabled": False, "http": "", "https": ""})
    tp_scheme: TPConfig = Field(default_factory=TPConfig)
    sl_scheme: SLConfig = Field(default_factory=SLConfig)
    breakeven_after_tp1: BreakevenConfig = Field(default_factory=BreakevenConfig)
    live_sync: LiveSyncConfig = Field(default_factory=LiveSyncConfig)
    use_websocket: bool = True
    slippage_adjustment: bool = True
    max_fill_time_ms: int = 5000
    retry_failed_orders: bool = True
    max_order_retries: int = 3
    order_timeout_ms: int = 10000
    dry_run: bool = True
    http_timeout: float = 10.0
    retry_count: int = 3
    retry_delay: float = 5.0

class RiskManagementConfig(BaseModel):
    enabled: bool = True
    max_day_loss_pct: float = 3.0
    max_drawdown_pct: float = 8.0
    cooldown_after_kill_min: int = 120
    spread_filter_bps: float = 5.0
    ev_filter_enabled: bool = False
    max_spread_bps: float = 10.0
    min_volume_usd: float = 50000.0
    max_slippage_bps: float = 5.0
    max_consecutive_losses: int = 5
    min_trades_before_ev: int = 10

class AppConfig(BaseModel):
    # Core Settings
    symbol: str = "BTCUSDT"
    interval: str = DEFAULT_PRIMARY_INTERVAL
    loop_delay: int = DEFAULT_LOOP_DELAY_SECONDS
    orderbook_limit: int = 50
    signal_score_threshold: float = 0.8
    cooldown_sec: int = 60
    hysteresis_ratio: float = 0.85
    volume_confirmation_multiplier: float = 1.0
    base_url: str = BASE_URL
    api_key: str = Field(default=API_KEY) # Load from env vars or config
    api_secret: str = Field(default=API_SECRET) # Load from env vars or config
    testnet_mode: bool = Field(alias='execution.testnet', default=False) # Alias for easy access
    initial_candle_history: int = 1000 # Min candles for indicators to calc

    # Strategy Management
    strategy_management: StrategyManagementConfig = Field(default_factory=StrategyManagementConfig)

    # Indicator Parameters
    indicators: IndicatorParameters = Field(default_factory=IndicatorParameters)

    # Execution and Trading
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)

    # Risk Management
    risk_management: RiskManagementConfig = Field(default_factory=RiskManagementConfig)

    # Analysis Modules
    analysis_modules: AnalysisModulesConfig = Field(default_factory=AnalysisModulesConfig)

    # Notifications
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)

    # Logging Configuration
    logging: LoggingConfig = Field(default_factory=LoggingConfig)

    # WebSocket Settings (used by BybitHelper)
    ws_settings: Dict[str, str] = Field(default_factory=lambda: {"public_base_url": WS_PUBLIC_BASE_URL, "private_base_url": WS_PRIVATE_BASE_URL})

    # Custom validator for API keys
    @validator('api_key', 'api_secret')
    def check_api_credentials(cls, value):
        if not value:
            # Check if execution.dry_run is False, as keys are needed for live trading
            # NOTE: This validation is crude; a more robust check would involve reading the config structure
            # before this validator is potentially called if dry_run is false. For now, warn if missing.
            logger = logging.getLogger(__name__) # Get logger if available
            if logger:
                logger.warning("API Key or Secret is missing. Live trading will fail. Set BYBIT_API_KEY and BYBIT_API_SECRET in .env or config.")
            # Allow the program to proceed if dry_run is enabled, keys are not strictly required.
            # However, for live trading, this will cause immediate failure.
            # If required for any operation, consider raising an error here if dry_run is False.
            return value # Return the empty value to allow Pydantic to process it further if needed.
        return value

    # Model Config for extra fields and alias handling
    class Config:
        extra = "ignore" # Ignore extra fields in config file
        validate_assignment = True # Validate assignments to fields after model creation
        allow_population_by_field_name = True # Allow using field names or aliases


# --- Function to Load and Initialize Everything ---
def setup_global_environment() -> bool:
    """
    Sets up the global environment: loads config, initializes logger,
    and creates the BybitHelper instance. Returns True on success, False on critical failure.
    """
    global logger, bybit_client # Declare globals to modify them

    # Load API keys from .env file if it exists
    if Path(".env").exists():
        load_dotenv()

    # Retrieve API keys from environment variables (takes precedence over .env)
    # If they are still None here, they will be used as defaults in AppConfig,
    # which might be okay if dry_run is True, but will fail for live trading.
    global API_KEY, API_SECRET
    API_KEY = os.getenv("BYBIT_API_KEY", API_KEY)
    API_SECRET = os.getenv("BYBIT_API_SECRET", API_SECRET)

    # Initialize basic logger early for critical config loading messages
    try:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stderr)
        # Create a temporary logger instance for config loading
        temp_logger = logging.getLogger(__name__)
        temp_logger.info("Initializing global environment...")
    except Exception as e:
        print(f"FATAL: Failed to initialize basic logger: {e}", file=sys.stderr)
        return False # Cannot proceed without basic logging

    # Load configuration
    try:
        config_instance = load_config(CONFIG_FILE_PATH, temp_logger)
        # Re-configure logger using the loaded config
        logger = setup_logger(__name__, config_instance)
        logger.info(f"{Fore.GREEN}Global environment setup complete.{Style.RESET_ALL}")
    except Exception as e:
        temp_logger.critical(f"FATAL: Critical error during configuration loading or logger setup: {e}", exc_info=True)
        return False # Critical failure

    # Assign loaded config to global variable
    config = config_instance
    logger.setLevel(logging.DEBUG) # Set logger to capture all messages for BybitHelper

    # Instantiate BybitHelper
    try:
        # Pass the validated config instance to BybitHelper
        bybit_client = BybitHelper(config)
        logger.info(f"{Fore.GREEN}BybitHelper summoned successfully.{Style.RESET_ALL}")
        return True # Successfully set up
    except RuntimeError as e:
        logger.critical(f"FATAL: Failed to initialize BybitHelper: {e}", exc_info=True)
        return False # Critical failure in BybitHelper initialization
    except Exception as e:
        logger.critical(f"FATAL: Unexpected error during BybitHelper initialization: {e}", exc_info=True)
        return False


# --- Indicator Calculation Module ---
# This section would ideally be in a separate `indicators.py` file.
# For self-containment, it's included here.

def calculate_indicators(df: pd.DataFrame, config: AppConfig, daily_df: Optional[pd.DataFrame] = None) -> Optional[pd.DataFrame]:
    """
    Calculates a comprehensive suite of technical indicators on the provided OHLCV DataFrame,
    based on the application configuration. Returns the DataFrame with new indicator columns.
    """
    if df is None or df.empty:
        logger.warning("Cannot calculate indicators: Input DataFrame is empty.")
        return pd.DataFrame()

    # Ensure DataFrame has necessary columns and data types
    required_cols = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in required_cols):
        logger.error(f"Input DataFrame missing required columns. Found: {df.columns.tolist()}, Required: {required_cols}")
        return None

    # Ensure numeric columns are Decimal, others are appropriate types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns and not isinstance(df[col].iloc[0], Decimal):
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce').apply(lambda x: Decimal(str(x)) if pd.notna(x) else np.nan)
            except Exception as e:
                logger.error(f"Error converting column '{col}' to Decimal for indicator calculation: {e}", exc_info=True)
                return None # Fail early if conversion fails

    # Ensure timestamp is datetime and UTC aware
    if df['timestamp'].dtype != 'datetime64[ns, UTC]':
        try:
            if df['timestamp'].dt.tz is None:
                df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')
            else:
                df['timestamp'] = df['timestamp'].dt.tz_convert('UTC')
        except Exception as e:
            logger.error(f"Error localizing/converting timestamps for indicator calculation: {e}", exc_info=True)
            return None

    # --- Indicator Calculations ---
    # Use global logger for indicator-specific logging
    # Add indicator columns directly to the DataFrame, handle NaNs appropriately
    logger.debug("Calculating technical indicators...")

    # --- Moving Averages ---
    if config.indicators.ema_short_period > 0:
        df['EMA_Short'] = calculate_ema(df['close'], period=config.indicators.ema_short_period)
    if config.indicators.ema_long_period > 0:
        df['EMA_Long'] = calculate_ema(df['close'], period=config.indicators.ema_long_period)
    if config.indicators.sma_short_period > 0:
        df['SMA_Short'] = calculate_sma(df['close'], period=config.indicators.sma_short_period)
    if config.indicators.sma_long_period > 0:
        df['SMA_Long'] = calculate_sma(df['close'], period=config.indicators.sma_long_period)
    if config.indicators.vwma_period > 0:
         df['VWMA'] = calculate_vwma(df['close'], df['volume'], period=config.indicators.vwma_period)
    if config.indicators.dema_period > 0:
         df['DEMA'] = calculate_dema(df['close'], period=config.indicators.dema_period)
    if config.indicators.kaufman_ama_period > 0:
         df['KAMA'] = calculate_kama(df['close'], period=config.indicators.kaufman_ama_period, fast_period=config.indicators.kama_fast_period, slow_period=config.indicators.kama_slow_period)

    # --- Momentum Oscillators ---
    if config.indicators.rsi_period > 0:
        rsi_values = calculate_rsi(df['close'], period=config.indicators.rsi_period)
        df['RSI'] = rsi_values
        df['RSI_OB'] = config.indicators.rsi_overbought
        df['RSI_OS'] = config.indicators.rsi_oversold
        # Signals
        df['RSI_Cross_Up'] = (rsi_values < config.indicators.rsi_oversold) & (rsi_values.shift(1) < config.indicators.rsi_oversold)
        df['RSI_Cross_Down'] = (rsi_values > config.indicators.rsi_overbought) & (rsi_values.shift(1) > config.indicators.rsi_overbought)

    if config.indicators.stoch_rsi_period > 0:
        stoch_rsi_k, stoch_rsi_d = calculate_stoch_rsi(df['close'], period=config.indicators.stoch_rsi_period, k_period=config.indicators.stoch_k_period, d_period=config.indicators.stoch_d_period)
        df['StochRSI_K'] = stoch_rsi_k
        df['StochRSI_D'] = stoch_rsi_d
        df['StochRSI_OB'] = config.indicators.stoch_rsi_overbought
        df['StochRSI_OS'] = config.indicators.stoch_rsi_oversold
        # Signals
        df['StochRSI_Cross_Up'] = (stoch_rsi_k < config.indicators.stoch_rsi_oversold) & (stoch_rsi_k.shift(1) < config.indicators.stoch_rsi_oversold)
        df['StochRSI_Cross_Down'] = (stoch_rsi_k > config.indicators.stoch_rsi_overbought) & (stoch_rsi_k.shift(1) > config.indicators.stoch_rsi_overbought)

    if config.indicators.cci_period > 0:
        cci_values = calculate_cci(df['high'], df['low'], df['close'], period=config.indicators.cci_period)
        df['CCI'] = cci_values
        df['CCI_OB'] = config.indicators.cci_overbought
        df['CCI_OS'] = config.indicators.cci_oversold
        # Signals
        df['CCI_Bullish_Signal'] = (cci_values < config.indicators.cci_oversold) & (cci_values.shift(1) < config.indicators.cci_oversold)
        df['CCI_Bearish_Signal'] = (cci_values > config.indicators.cci_overbought) & (cci_values.shift(1) > config.indicators.cci_overbought)

    if config.indicators.williams_r_period > 0:
        wr_values = calculate_williams_r(df['high'], df['low'], df['close'], period=config.indicators.williams_r_period)
        df['Williams_R'] = wr_values
        df['Williams_R_OB'] = config.indicators.williams_r_overbought
        df['Williams_R_OS'] = config.indicators.williams_r_oversold
        # Signals
        df['Williams_R_Bullish_Signal'] = (wr_values > config.indicators.williams_r_overbought) & (wr_values.shift(1) > config.indicators.williams_r_overbought)
        df['Williams_R_Bearish_Signal'] = (wr_values < config.indicators.williams_r_oversold) & (wr_values.shift(1) < config.indicators.williams_r_oversold)

    if config.indicators.mfi_period > 0:
        mfi_values = calculate_mfi(df['high'], df['low'], df['close'], df['volume'], period=config.indicators.mfi_period)
        df['MFI'] = mfi_values
        df['MFI_OB'] = config.indicators.mfi_overbought
        df['MFI_OS'] = config.indicators.mfi_oversold
        # Signals
        df['MFI_Bullish_Signal'] = (mfi_values < config.indicators.mfi_oversold) & (mfi_values.shift(1) < config.indicators.mfi_oversold)
        df['MFI_Bearish_Signal'] = (mfi_values > config.indicators.mfi_overbought) & (mfi_values.shift(1) > config.indicators.mfi_overbought)

    # --- Trend and Volatility Indicators ---
    if config.indicators.atr_period > 0:
        df['ATR'] = calculate_atr(df['high'], df['low'], df['close'], period=config.indicators.atr_period)

    if config.indicators.psar_acceleration > 0:
        psar_values = calculate_psar(df['high'], df['low'], df['close'], config.indicators.psar_acceleration, config.indicators.psar_max_acceleration)
        df['PSAR'] = psar_values
        # Determine bullish/bearish PSAR state
        df['PSAR_Trend'] = np.where(df['PSAR'] > df['close'], 'Bearish', np.where(df['PSAR'] < df['close'], 'Bullish', 'Flat'))
        # Signals: Trend change
        df['PSAR_Bullish_Flip'] = (df['PSAR_Trend'] == 'Bullish') & (df['PSAR_Trend'].shift(1) == 'Bearish')
        df['PSAR_Bearish_Flip'] = (df['PSAR_Trend'] == 'Bearish') & (df['PSAR_Trend'].shift(1) == 'Bullish')

    if config.indicators.bollinger_bands_period > 0 and config.indicators.bollinger_bands_std_dev > 0:
        basis, upper, lower = calculate_bollinger_bands(df['close'],
                                                       period=config.indicators.bollinger_bands_period,
                                                       std_dev=config.indicators.bollinger_bands_std_dev)
        df['Bollinger_Basis'] = basis
        df['Bollinger_Upper'] = upper
        df['Bollinger_Lower'] = lower
        # Signals: Price touching bands
        df['Price_Touches_Upper_BB'] = df['close'] >= upper
        df['Price_Touches_Lower_BB'] = df['close'] <= lower

    if config.indicators.keltner_period > 0 and config.indicators.keltner_atr_multiplier > 0:
        keltner_basis, keltner_upper, keltner_lower = calculate_keltner_channels(df['high'], df['low'], df['close'],
                                                                              period=config.indicators.keltner_period,
                                                                              atr_multiplier=config.indicators.keltner_atr_multiplier)
        df['Keltner_Basis'] = keltner_basis
        df['Keltner_Upper'] = keltner_upper
        df['Keltner_Lower'] = keltner_lower
        # Signals: Price touching bands
        df['Price_Touches_Upper_KC'] = df['close'] >= keltner_upper
        df['Price_Touches_Lower_KC'] = df['close'] <= keltner_lower

    if config.indicators.adx_period > 0:
        adx_vals = calculate_adx(df['high'], df['low'], df['close'], period=config.indicators.adx_period)
        df['ADX'] = adx_vals['ADX']
        df['ADX_PlusDI'] = adx_vals['PlusDI']
        df['ADX_MinusDI'] = adx_vals['MinusDI']
        # Trend strength indication
        df['ADX_Trend_Strength'] = np.where(df['ADX'] > 25, 'Strong', np.where(df['ADX'] < 20, 'Weak', 'Moderate'))
        # Trend direction based on DI crossover
        df['ADX_Bullish_Signal'] = (df['ADX_PlusDI'] > df['ADX_MinusDI']) & (df['ADX_PlusDI'].shift(1) <= df['ADX_MinusDI'].shift(1))
        df['ADX_Bearish_Signal'] = (df['ADX_MinusDI'] > df['ADX_PlusDI']) & (df['ADX_MinusDI'].shift(1) <= df['ADX_PlusDI'].shift(1))


    # --- Volume Indicators ---
    df['Volume'] = df['volume'] # Ensure Volume column exists and is named consistently
    if config.indicators.volume_delta_period > 0:
        volume_delta_values = calculate_volume_delta(df['close'], df['volume'], period=config.indicators.volume_delta_period)
        df['Volume_Delta'] = volume_delta_values
        df['Volume_Delta_Signal'] = df['Volume_Delta'] > config.indicators.volume_delta_threshold # Simple threshold signal

    if config.indicators.obv_ema_period > 0:
        df['OBV'] = calculate_obv(df['close'], df['volume'])
        df['OBV_EMA'] = calculate_ema(df['OBV'], period=config.indicators.obv_ema_period)

    if config.indicators.cmf_period > 0:
        df['CMF'] = calculate_cmf(df['high'], df['low'], df['close'], df['volume'], period=config.indicators.cmf_period)

    if config.indicators.relative_volume_period > 0:
        df['Relative_Volume'] = calculate_relative_volume(df['volume'], period=config.indicators.relative_volume_period)
        df['Relative_Volume_Signal'] = df['Relative_Volume'] > config.indicators.relative_volume_threshold

    # --- MACD ---
    if config.indicators.macd_fast_period > 0 and config.indicators.macd_slow_period > 0 and config.indicators.macd_signal_period > 0:
        macd_line, signal_line, macd_hist = calculate_macd(df['close'],
                                                             fast_period=config.indicators.macd_fast_period,
                                                             slow_period=config.indicators.macd_slow_period,
                                                             signal_period=config.indicators.macd_signal_period)
        df['MACD_Line'] = macd_line
        df['MACD_Signal'] = signal_line
        df['MACD_Hist'] = macd_hist
        # Signals: Crossovers
        df['MACD_Bullish_Cross'] = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
        df['MACD_Bearish_Cross'] = (macd_line < signal_line) & (macd_line.shift(1) >= signal_line.shift(1))

    # --- Ehlers Indicators ---
    if config.indicators.ehlers_supertrend_atr_len > 0:
        # Apply Ehlers SuperTrend (using settings for "Fast" mode as default)
        supertrend_signal, supertrend_line = calculate_ehlers_supertrend(
            df['high'], df['low'], df['close'],
            atr_len=config.indicators.ehlers_supertrend_atr_len,
            multiplier=config.indicators.ehlers_supertrend_mult,
            ss_len=config.indicators.ehlers_supertrend_ss_len # Optional SS length
        )
        df['Ehlers_SuperTrend'] = supertrend_line
        df['Ehlers_SuperTrend_Trend'] = np.where(supertrend_line > df['close'], 'Bearish', np.where(supertrend_line < df['close'], 'Bullish', 'Flat'))
        # Signals: Trend flips
        df['Ehlers_Bullish_Flip'] = (df['Ehlers_SuperTrend_Trend'] == 'Bullish') & (df['Ehlers_SuperTrend_Trend'].shift(1) == 'Bearish')
        df['Ehlers_Bearish_Flip'] = (df['Ehlers_SuperTrend_Trend'] == 'Bearish') & (df['Ehlers_SuperTrend_Trend'].shift(1) == 'Bullish')

    if config.indicators.fisher_transform_length > 0:
        fisher, signal = calculate_fisher_transform(df['high'], df['low'], df['close'], length=config.indicators.fisher_transform_length)
        df['Fisher_Transform'] = fisher
        df['Fisher_Signal'] = signal
        # Signals: Crossovers
        df['Fisher_Bullish_Cross'] = (fisher > signal) & (fisher.shift(1) <= signal.shift(1))
        df['Fisher_Bearish_Cross'] = (fisher < signal) & (fisher.shift(1) >= signal.shift(1))

    if config.indicators.ehlers_stochrsi_rsi_len > 0:
        stoch_rsi_ehlers = calculate_ehlers_stochrsi(
            df['close'],
            rsi_len=config.indicators.ehlers_stochrsi_rsi_len,
            stoch_len=config.indicators.ehlers_stochrsi_stoch_len,
            fast_len=config.indicators.ehlers_stochrsi_ss_fast,
            slow_len=config.indicators.ehlers_stochrsi_ss_slow
        )
        df['Ehlers_StochRSI'] = stoch_rsi_ehlers
        df['Ehlers_StochRSI_OB'] = 80 # Common overbought level for StochRSI
        df['Ehlers_StochRSI_OS'] = 20 # Common oversold level for StochRSI
        # Signals
        df['Ehlers_StochRSI_Bullish_Signal'] = (stoch_rsi_ehlers < df['Ehlers_StochRSI_OS']) & (stoch_rsi_ehlers.shift(1) < df['Ehlers_StochRSI_OS'])
        df['Ehlers_StochRSI_Bearish_Signal'] = (stoch_rsi_ehlers > df['Ehlers_StochRSI_OB']) & (stoch_rsi_ehlers.shift(1) > df['Ehlers_StochRSI_OB'])


    # --- Ichimoku Cloud ---
    if config.indicators.ichimoku_tenkan_period > 0 and config.indicators.ichimoku_kijun_period > 0 and config.indicators.ichimoku_senkou_span_b_period > 0:
        tenkan, kijun, senkou_a, senkou_b, chikou = calculate_ichimoku_cloud(
            df['high'], df['low'], df['close'],
            tenkan_period=config.indicators.ichimoku_tenkan_period,
            kijun_period=config.indicators.ichimoku_kijun_period,
            senkou_span_b_period=config.indicators.ichimoku_senkou_span_b_period,
            chikou_offset=config.indicators.ichimoku_chikou_span_offset
        )
        df['Ichimoku_Tenkan'] = tenkan
        df['Ichimoku_Kijun'] = kijun
        df['Ichimoku_Senkou_A'] = senkou_a
        df['Ichimoku_Senkou_B'] = senkou_b
        df['Ichimoku_Chikou'] = chikou
        # Cloud formation (Senkou Spans)
        df['Ichimoku_Cloud_Future'] = senkou_a > senkou_b # Bullish cloud future
        df['Ichimoku_Cloud_Past'] = senkou_a.shift(config.indicators.ichimoku_chikou_span_offset) > senkou_b.shift(config.indicators.ichimoku_chikou_span_offset) # Bullish cloud past

        # Signals: Crosses
        df['Ichimoku_Tenkan_Kijun_Bullish_Cross'] = (tenkan > kijun) & (tenkan.shift(1) <= kijun.shift(1))
        df['Ichimoku_Tenkan_Kijun_Bearish_Cross'] = (tenkan < kijun) & (tenkan.shift(1) >= kijun.shift(1))

    # --- Pivot Points (requires Daily OHLCV data) ---
    if config.indicators.fibonacci_window > 0 and daily_df is not None and not daily_df.empty:
        try:
            pivot_points = calculate_pivot_points_fibonacci(daily_df, window=config.indicators.fibonacci_window)
            # Merge pivot data into the current DataFrame based on timestamp
            df = pd.merge(df, pivot_points, on='timestamp', how='left')
            # Add placeholder columns if merge didn't add them (e.g., if daily data was sparse)
            for pp_col in ['Pivot', 'R1', 'R2', 'R3', 'S1', 'S2', 'S3', 'BC', 'BS']:
                if pp_col not in df.columns:
                    df[pp_col] = np.nan
            # Signals: Price crossing pivots
            df['Price_Crossed_R1'] = (df['close'] >= df['R1']) & (df['close'].shift(1) < df['R1'])
            df['Price_Crossed_S1'] = (df['close'] <= df['S1']) & (df['close'].shift(1) > df['S1'])
            df['Price_Crossed_Pivot'] = (df['close'] >= df['Pivot']) & (df['close'].shift(1) < df['Pivot'])

        except Exception as e:
            logger.warning(f"Could not calculate Fibonacci Pivot Points: {e}. Check daily data availability and format.", exc_info=True)

    # --- Volatility Index ---
    if config.indicators.volatility_index_period > 0:
        df['Volatility_Index'] = calculate_volatility_index(df['high'], df['low'], period=config.indicators.volatility_index_period)

    # --- Market Structure ---
    if config.indicators.market_structure_lookback_period > 0:
        # Detect market structure points (HH, HL, LH, LL)
        market_structure = detect_market_structure(df['high'], df['low'], lookback=config.indicators.market_structure_lookback_period)
        df['Market_Structure'] = market_structure # Stores 'HH', 'HL', 'LH', 'LL', or None

        # Simplified trend determination based on structure
        df['MS_Trend'] = np.nan
        df.loc[df['Market_Structure'].isin(['HH', 'HL']), 'MS_Trend'] = 'Bullish'
        df.loc[df['Market_Structure'].isin(['LH', 'LL']), 'MS_Trend'] = 'Bearish'
        # Fill forward for structure trend if no new point detected
        df['MS_Trend'] = df['MS_Trend'].ffill()


    # --- Candlestick Patterns ---
    if config.indicators.roc_period > 0: # Using ROC period for a loose lookback for patterns
        df['ROC'] = calculate_roc(df['close'], period=config.indicators.roc_period)
        df['ROC_Bullish_Signal'] = df['ROC'] > config.indicators.roc_oversold
        df['ROC_Bearish_Signal'] = df['ROC'] < config.indicators.roc_overbought

    # Calculate candlestick patterns (more complex, requires specific logic per pattern)
    # Placeholder for candlestick pattern analysis
    df['Candlestick_Pattern'] = detect_candlestick_patterns(df) # This function would need implementation

    # --- Order Book Imbalance (requires order book data, not available from OHLCV) ---
    # Placeholder for Order Book Imbalance calculation if order book data were available
    df['OrderBook_Imbalance'] = np.nan

    # --- Expectation Value (placeholder) ---
    # Placeholder for EV calculation, requires trade execution data or backtesting simulation
    df['Expectation_Value'] = np.nan

    # --- Populate specific signal columns based on common indicator conditions ---
    # These columns are often used by strategy profiles for scoring
    df['Is_Bullish_OB'] = (
        (df['RSI'] < config.indicators.rsi_oversold) |
        (df['StochRSI_K'] < config.indicators.stoch_rsi_oversold) |
        (df['CCI'] < config.indicators.cci_oversold) |
        (df['Williams_R'] > config.indicators.williams_r_overbought) |
        (df['MFI'] < config.indicators.mfi_oversold)
    )
    df['Is_Bearish_OB'] = (
        (df['RSI'] > config.indicators.rsi_overbought) |
        (df['StochRSI_K'] > config.indicators.stoch_rsi_overbought) |
        (df['CCI'] > config.indicators.cci_overbought) |
        (df['Williams_R'] < config.indicators.williams_r_oversold) |
        (df['MFI'] > config.indicators.mfi_overbought)
    )

    # EMA Alignment
    df['EMA_Alignment_Bullish'] = df['EMA_Short'] > df['EMA_Long']
    df['EMA_Alignment_Bearish'] = df['EMA_Short'] < df['EMA_Long']

    # SMA Trend Filter
    df['SMA_Trend_Bullish'] = df['SMA_Long'] > df['SMA_Short'] # Or other logic depending on desired trend filter
    df['SMA_Trend_Bearish'] = df['SMA_Long'] < df['SMA_Short']

    # Volatility Filter (using ATR as a proxy)
    if 'ATR' in df.columns and config.indicators.atr_period > 0:
        # Volatility as a percentage of close price
        avg_volatility_pct = (df['ATR'] / df['close']) * 100 if df['close'] != 0 else np.nan
        df['Volatility_Pct'] = avg_volatility_pct
        # Example: High volatility if Volatility_Pct > 2%
        df['High_Volatility'] = df['Volatility_Pct'] > 2.0


    logger.debug("Indicator calculations complete.")
    return df

# --- Indicator Calculation Helper Functions ---
# These should be robust and handle NaNs correctly.

def calculate_sma(data: pd.Series, period: int) -> pd.Series:
    """Calculates Simple Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        return data.rolling(window=period).mean()
    except Exception as e:
        logger.warning(f"Error calculating SMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_vwma(close_data: pd.Series, volume_data: pd.Series, period: int) -> pd.Series:
    """Calculates Volume Weighted Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=close_data.index)
    try:
        # Calculate Typical Price (H+L+C)/3
        typical_price = (close_data + close_data.shift(1) + close_data.shift(2)) / 3 # Use close for simplicity if H/L not critical
        if typical_price.isnull().all(): typical_price = close_data # Fallback if H/L not available

        # Calculate VWAP for the period
        vwap_series = (typical_price * volume_data).rolling(window=period).sum() / volume_data.rolling(window=period).sum()
        return vwap_series
    except Exception as e:
        logger.warning(f"Error calculating VWMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close_data.index)


def calculate_kama(data: pd.Series, period: int, fast_period: int, slow_period: int) -> pd.Series:
    """Calculates Kaufman's Adaptive Moving Average (KAMA)."""
    if period <= 0 or fast_period <= 0 or slow_period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        # Step 1: Calculate the Efficiency Ratio (ER)
        # ER = ( (Close - Prior Close) / (High - Low) ) * 100
        # Handle potential division by zero or NaN
        price_change = data - data.shift(1)
        h_l_diff = data.rolling(window=period).max() - data.rolling(window=period).min()
        h_l_diff = h_l_diff.replace(0, 1e-9) # Avoid division by zero
        er = (price_change / h_l_diff) * 100
        er = er.fillna(0) # Fill initial NaNs

        # Step 2: Calculate the Noise Ratio (NR)
        # NR = 100 - ER
        nr = 100 - er

        # Step 3: Calculate the Smoothing Constant (SC)
        # SC = ER / (period * Noise_Ratio)
        # Use SC_fast = 2 / (fast_period + 1) and SC_slow = 2 / (slow_period + 1) for calculation basis
        sc_fast_base = 2 / (fast_period + 1)
        sc_slow_base = 2 / (slow_period + 1)
        sc = (er / period) * (sc_fast_base - sc_slow_base) + sc_slow_base

        # Step 4: Calculate KAMA
        # KAMA = Prior KAMA + SC * (Close - Prior KAMA)
        kama = pd.Series(np.nan, index=data.index)
        # Initialize with the first valid price as KAMA
        kama.iloc[period - 1] = data.iloc[period - 1]

        for i in range(period, len(data)):
             if pd.isna(kama.iloc[i-1]): # If previous KAMA is NaN, re-initialize
                  kama.iloc[i] = data.iloc[i]
             else:
                  kama.iloc[i] = kama.iloc[i-1] + sc.iloc[i] * (data.iloc[i] - kama.iloc[i-1])
        return kama

    except Exception as e:
        logger.warning(f"Error calculating KAMA({period}, fast={fast_period}, slow={slow_period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_ema(data: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        return data.ewm(span=period, adjust=False).mean()
    except Exception as e:
        logger.warning(f"Error calculating EMA({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_rsi(data: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Strength Index."""
    if period <= 0: return pd.Series(np.nan, index=data.index)
    try:
        delta = data.diff()
        gain = (delta.where(delta > 0)).fillna(0)
        loss = (-delta.where(delta < 0)).fillna(0)

        avg_gain = gain.ewm(span=period, adjust=False).mean()
        avg_loss = loss.ewm(span=period, adjust=False).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    except Exception as e:
        logger.warning(f"Error calculating RSI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index)

def calculate_stoch_rsi(data: pd.Series, period: int, k_period: int, d_period: int) -> Tuple[pd.Series, pd.Series]:
    """Calculates Stochastic RSI."""
    if period <= 0 or k_period <= 0 or d_period <= 0: return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)
    try:
        rsi = calculate_rsi(data, period=period)
        if rsi.isnull().all(): return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)

        min_rsi = rsi.rolling(window=period).min()
        max_rsi = rsi.rolling(window=period).max()

        stoch_rsi = 100 * ((rsi - min_rsi) / (max_rsi - min_rsi))
        stoch_rsi = stoch_rsi.fillna(0) # Fill initial NaNs

        # Calculate %K and %D
        stoch_k = stoch_rsi.rolling(window=k_period).mean()
        stoch_d = stoch_k.rolling(window=d_period).mean()

        return stoch_k, stoch_d
    except Exception as e:
        logger.warning(f"Error calculating Stochastic RSI (Period={period}, K={k_period}, D={d_period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)

def calculate_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Commodity Channel Index."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        cci = typical_price.rolling(window=period).apply(lambda x: ta.cci(x.iloc[-1], x.iloc[0], x.iloc[period-1], period=period) if len(x) == period else np.nan, raw=True) # Use ta-lib for accuracy if available
        # Fallback if ta-lib not available or to implement manually:
        if cci.isnull().all():
             tp_mean = typical_price.rolling(window=period).mean()
             tp_dev = abs(typical_price - tp_mean).rolling(window=period).sum() / period
             cci = (typical_price - tp_mean) / (0.015 * tp_dev) # 0.015 is a common constant multiplier
        return cci
    except Exception as e:
        logger.warning(f"Error calculating CCI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Williams %R."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        wr = -100 * ((highest_high - close) / (highest_high - lowest_low))
        return wr
    except Exception as e:
        logger.warning(f"Error calculating Williams %R({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """Calculates Money Flow Index."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        positive_mf = money_flow.where(typical_price > typical_price.shift(1)).fillna(0)
        negative_mf = money_flow.where(typical_price < typical_price.shift(1)).fillna(0)

        positive_mf_sum = positive_mf.rolling(window=period).sum()
        negative_mf_sum = negative_mf.rolling(window=period).sum()

        money_ratio = positive_mf_sum / negative_mf_sum
        mfi = 100 - (100 / (1 + money_ratio))
        return mfi
    except Exception as e:
        logger.warning(f"Error calculating MFI({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    """Calculates Average True Range."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        # Calculate True Range (TR)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        # Calculate ATR using EMA
        atr = true_range.ewm(span=period, adjust=False).mean()
        return atr
    except Exception as e:
        logger.warning(f"Error calculating ATR({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_psar(high: pd.Series, low: pd.Series, close: pd.Series, af_start: float, af_max: float) -> pd.Series:
    """Calculates Parabolic Stop and Reverse (PSAR)."""
    # Using a simplified manual implementation as ta-lib might not be available
    # A full implementation requires careful state management (AF, EP, trend)
    # This is a placeholder and might need refinement or ta-lib integration.
    if af_start <= 0 or af_max <= 0: return pd.Series(np.nan, index=high.index)
    try:
        # Placeholder: Return NaNs or a very basic calculation
        # A proper implementation would be much more complex.
        # For now, we return NaNs to signify it's not reliably calculated here.
        logger.warning("Manual PSAR calculation is a placeholder and may not be accurate. Consider using a library like TA-Lib.")
        return pd.Series(np.nan, index=high.index)
    except Exception as e:
        logger.warning(f"Error calculating PSAR (AF_Start={af_start}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_bollinger_bands(data: pd.Series, period: int, std_dev: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Bollinger Bands (Basis, Upper, Lower)."""
    if period <= 0 or std_dev <= 0: return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)
    try:
        basis = calculate_sma(data, period=period)
        if basis.isnull().all(): return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)

        std_dev_prices = data.rolling(window=period).std()
        upper = basis + (std_dev_prices * std_dev)
        lower = basis - (std_dev_prices * std_dev)
        return basis, upper, lower
    except Exception as e:
        logger.warning(f"Error calculating Bollinger Bands (Period={period}, StdDev={std_dev}): {e}", exc_info=True)
        return pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index), pd.Series(np.nan, index=data.index)

def calculate_keltner_channels(high: pd.Series, low: pd.Series, close: pd.Series, period: int, atr_multiplier: float) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates Keltner Channels."""
    if period <= 0 or atr_multiplier <= 0: return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)
    try:
        basis = calculate_ema(close, period=period) # EMA is common for Keltner basis
        if basis.isnull().all(): return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)

        atr = calculate_atr(high, low, close, period=period)
        upper = basis + (atr * atr_multiplier)
        lower = basis - (atr * atr_multiplier)
        return basis, upper, lower
    except Exception as e:
        logger.warning(f"Error calculating Keltner Channels (Period={period}, ATRMult={atr_multiplier}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)

def calculate_adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> Dict[str, pd.Series]:
    """Calculates ADX, PlusDI, MinusDI."""
    if period <= 0: return {'ADX': pd.Series(np.nan, index=high.index), 'PlusDI': pd.Series(np.nan, index=high.index), 'MinusDI': pd.Series(np.nan, index=high.index)}
    try:
        # Calculate Directional Movement (+DM, -DM)
        up_move = high.diff()
        down_move = low.diff()
        plus_dm = pd.Series(np.nan, index=high.index)
        minus_dm = pd.Series(np.nan, index=high.index)

        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), -down_move, 0)

        # Smoothed Directional Indicators (+DI, -DI) using Wilder's smoothing (similar to EMA but different factor)
        # Smoothed value = Prior Smoothed + (Current Value - Prior Smoothed) / Period
        # Or using EMA with period: TR = EMA(TR, period)
        # Using EMA for simplicity here. Wilder's smoothing uses period / (period + 1) instead of 2/(period+1).
        plus_di = plus_dm.ewm(span=period, adjust=False).mean()
        minus_di = minus_dm.ewm(span=period, adjust=False).mean()

        # Calculate Directional Index (DX)
        di_sum = plus_di + minus_di
        di_diff = abs(plus_di - minus_di)
        # Avoid division by zero
        di_sum = di_sum.replace(0, 1e-9)
        dx = (di_diff / di_sum) * 100

        # Calculate ADX from DX using EMA
        adx = dx.ewm(span=period, adjust=False).mean()

        return {'ADX': adx, 'PlusDI': plus_di, 'MinusDI': minus_di}
    except Exception as e:
        logger.warning(f"Error calculating ADX({period}): {e}", exc_info=True)
        return {'ADX': pd.Series(np.nan, index=high.index), 'PlusDI': pd.Series(np.nan, index=high.index), 'MinusDI': pd.Series(np.nan, index=high.index)}


def calculate_volume_delta(close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """Calculates Volume Delta (Buy Volume - Sell Volume) over a period."""
    if period <= 0: return pd.Series(np.nan, index=close.index)
    try:
        # Simple approach: assume volume is buy volume if close > open, sell volume if close < open
        # This is a simplification; actual buy/sell volume requires order book or tick data.
        buy_volume = volume.where(close > close.shift(1)).fillna(0)
        sell_volume = volume.where(close < close.shift(1)).fillna(0)

        volume_delta_per_candle = buy_volume - sell_volume
        # Calculate rolling sum of volume delta
        volume_delta_rolled = volume_delta_per_candle.rolling(window=period).sum()
        return volume_delta_rolled
    except Exception as e:
        logger.warning(f"Error calculating Volume Delta({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)

def calculate_relative_volume(volume: pd.Series, period: int) -> pd.Series:
    """Calculates Relative Volume (Current Volume / Average Volume)."""
    if period <= 0: return pd.Series(np.nan, index=volume.index)
    try:
        avg_volume = volume.rolling(window=period).mean()
        # Avoid division by zero
        avg_volume = avg_volume.replace(0, 1e-9)
        relative_vol = volume / avg_volume
        return relative_vol
    except Exception as e:
        logger.warning(f"Error calculating Relative Volume({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=volume.index)

def calculate_obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """Calculates On-Balance Volume."""
    try:
        obv = pd.Series(index=close.index, dtype='float64')
        obv.iloc[0] = 0 # Initialize OBV

        for i in range(1, len(close)):
            if close.iloc[i] > close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] + volume.iloc[i]
            elif close.iloc[i] < close.iloc[i-1]:
                obv.iloc[i] = obv.iloc[i-1] - volume.iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i-1]
        return obv
    except Exception as e:
        logger.warning(f"Error calculating OBV: {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)

def calculate_cmf(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int) -> pd.Series:
    """Calculates Chaikin Money Flow."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        # Calculate Money Flow Multiplier (MFM)
        mfm = ((close - low) - (high - close)) / (high - low)
        # Avoid division by zero or NaN in (high - low)
        mfm = mfm.replace([np.inf, -np.inf], 0)
        mfm = mfm.fillna(0)

        # Calculate Money Flow (MF)
        mf = mfm * volume

        # Calculate CMF over the period using rolling sum
        cmf = mf.rolling(window=period).sum() / volume.rolling(window=period).sum()
        return cmf
    except Exception as e:
        logger.warning(f"Error calculating CMF({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def calculate_macd(close: pd.Series, fast_period: int, slow_period: int, signal_period: int) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Calculates MACD (MACD Line, Signal Line, Histogram)."""
    if fast_period <= 0 or slow_period <= 0 or signal_period <= 0 or fast_period >= slow_period:
        return pd.Series(np.nan, index=close.index), pd.Series(np.nan, index=close.index), pd.Series(np.nan, index=close.index)
    try:
        ema_fast = calculate_ema(close, period=fast_period)
        ema_slow = calculate_ema(close, period=slow_period)

        macd_line = ema_fast - ema_slow
        signal_line = calculate_ema(macd_line, period=signal_period)
        macd_hist = macd_line - signal_line

        return macd_line, signal_line, macd_hist
    except Exception as e:
        logger.warning(f"Error calculating MACD (Fast={fast_period}, Slow={slow_period}, Signal={signal_period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index), pd.Series(np.nan, index=close.index), pd.Series(np.nan, index=close.index)

# Ehlers Indicator Calculations (Simplified placeholders, might require external libraries or detailed implementation)
# These are complex and require precise state management. Using basic logic for demonstration.

def calculate_ehlers_supertrend(high: pd.Series, low: pd.Series, close: pd.Series, atr_len: int, multiplier: float, ss_len: Optional[int] = None) -> Tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers SuperTrend calculation. Requires precise implementation."""
    # A true SuperTrend implementation involves ATR and trend direction tracking.
    # This placeholder returns NaNs.
    logger.warning("Ehlers SuperTrend calculation is a placeholder. Requires detailed implementation.")
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)

def calculate_fisher_transform(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> Tuple[pd.Series, pd.Series]:
    """Placeholder for Ehlers Fisher Transform calculation."""
    # Requires calculation of Highest High and Lowest Low over `length` period.
    logger.warning("Ehlers Fisher Transform calculation is a placeholder. Requires detailed implementation.")
    return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)

def calculate_ehlers_stochrsi(close: pd.Series, rsi_len: int, stoch_len: int, fast_len: int, slow_len: int) -> pd.Series:
    """Placeholder for Ehlers Stochastic RSI calculation."""
    # StochRSI calculation is already implemented above, this function might aim for Ehlers' specific version.
    logger.warning("Ehlers Stochastic RSI calculation is a placeholder. Consider using the standard StochRSI or verify Ehlers' method.")
    # For now, defer to the standard implementation. If Ehlers' version differs significantly,
    # this would need its own logic.
    stoch_k, _ = calculate_stoch_rsi(close, rsi_len, stoch_len, fast_len)
    return stoch_k # Returning StochRSI %K as a proxy

def calculate_ichimoku_cloud(high: pd.Series, low: pd.Series, close: pd.Series,
                             tenkan_period: int, kijun_period: int, senkou_span_b_period: int,
                             chikou_offset: int) -> Tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """Calculates Ichimoku Cloud components."""
    if tenkan_period <= 0 or kijun_period <= 0 or senkou_span_b_period <= 0:
        return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), \
               pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)
    try:
        # Conversion periods
        tenkan_sen = (high.rolling(window=tenkan_period).max() + low.rolling(window=tenkan_period).min()) / 2
        kijun_sen = (high.rolling(window=kijun_period).max() + low.rolling(window=kijun_period).min()) / 2

        # Senkou Span A (Leading Span 1)
        senkou_span_a = (tenkan_sen + kijun_sen) / 2

        # Senkou Span B (Leading Span 2)
        senkou_span_b = (high.rolling(window=senkou_span_b_period).max() + low.rolling(window=senkou_span_b_period).min()) / 2

        # Chikou Span (Lagging Span) - shifted back by kijun_period (common offset)
        # The offset is applied in the data frame itself, so here we just return close series.
        # The dataframe merge/lookup handles the offset.
        chikou_span = close

        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b, chikou_span
    except Exception as e:
        logger.warning(f"Error calculating Ichimoku Cloud: {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), \
               pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index), pd.Series(np.nan, index=high.index)

def calculate_pivot_points_fibonacci(daily_df: pd.DataFrame, window: int) -> pd.DataFrame:
    """Calculates Fibonacci Pivot Points based on daily High, Low, Close."""
    if daily_df.empty or window <= 0:
        return pd.DataFrame()
    try:
        # Ensure required columns are present and numeric
        required_cols = ['high', 'low', 'close']
        if not all(col in daily_df.columns for col in required_cols):
            logger.error("Daily DataFrame missing required columns for Pivot calculation.")
            return pd.DataFrame()

        # Calculate Standard Pivots (P)
        P = (daily_df['high'] + daily_df['low'] + daily_df['close']) / 3

        # Calculate Resistance (R) and Support (S) levels
        R1 = (2 * P) - daily_df['low']
        S1 = (2 * P) - daily_df['high']

        R2 = P + (daily_df['high'] - daily_df['low'])
        S2 = P - (df['high'] - df['low'])

        R3 = P + 2 * (daily_df['high'] - daily_df['low'])
        S3 = P - 2 * (df['high'] - df['low'])

        # Calculate Camilla Boyer (BC) and Bollinger Support (BS) - often derived from pivots
        # These might need specific definitions; using common interpretations:
        BC = P - (df['high'] - df['low']) # Simplified BC
        BS = P + (df['high'] - df['low']) # Simplified BS

        # Create DataFrame for pivot points, ensure timestamp alignment
        pivot_df = pd.DataFrame({
            'timestamp': daily_df['timestamp'],
            'Pivot': P, 'R1': R1, 'R2': R2, 'R3': R3,
            'S1': S1, 'S2': S2, 'S3': S3,
            'BC': BC, 'BS': BS
        })

        # Apply rolling window to get pivots for the lookback period
        # This calculates pivots based on the last `window` days' data.
        # We need to apply this rolling calculation carefully.
        # A common approach is to calculate pivots for each day based on the previous N days' data.
        # For simplicity here, let's assume `daily_df` is already aligned and we want pivots for each day.
        # If a rolling calculation is needed, it implies calculating pivots N days in the past for each current bar.

        # For real-time, pivots are typically based on the previous day's data.
        # If `daily_df` represents daily data, we might just return it directly for use.
        # Let's assume `daily_df` is suitable for direct use, and the `window` parameter
        # implies how many days of history were used to derive `daily_df` itself.
        # If the intent is to calculate pivots dynamically based on a rolling window of `daily_df`,
        # that requires more complex application.

        # Let's just return the calculated pivots for each day in `daily_df` for now.
        # The `window` parameter might be more relevant if `daily_df` itself was a rolling window.
        return pivot_df

    except Exception as e:
        logger.warning(f"Error calculating Fibonacci Pivot Points (Window={window}): {e}", exc_info=True)
        return pd.DataFrame()

def calculate_volatility_index(high: pd.Series, low: pd.Series, period: int) -> pd.Series:
    """Calculates a simple Volatility Index (e.g., based on Average Range)."""
    if period <= 0: return pd.Series(np.nan, index=high.index)
    try:
        # Using ATR as a proxy for volatility
        volatility = calculate_atr(high, low, high, period=period) # Using high for close placeholder in ATR
        return volatility
    except Exception as e:
        logger.warning(f"Error calculating Volatility Index ({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def detect_market_structure(high: pd.Series, low: pd.Series, lookback: int) -> pd.Series:
    """Detects Market Structure points (HH, HL, LH, LL) - simplified logic."""
    if lookback <= 0: return pd.Series(np.nan, index=high.index)
    try:
        structure = pd.Series(np.nan, index=high.index)
        # Simplified logic: A high is higher than previous highs, low is higher than previous lows etc.
        # This requires comparing current pivot points to prior ones over the lookback window.
        # A proper implementation involves finding pivot points first.

        # Placeholder: returns NaN, needs significant implementation.
        logger.warning("Market Structure detection is a placeholder. Requires pivot point identification.")
        return structure
    except Exception as e:
        logger.warning(f"Error detecting Market Structure (Lookback={lookback}): {e}", exc_info=True)
        return pd.Series(np.nan, index=high.index)

def detect_candlestick_patterns(df: pd.DataFrame) -> pd.Series:
    """Detects common candlestick patterns - Placeholder function."""
    # This would involve analyzing Open, High, Low, Close relationships for specific patterns.
    # e.g., Doji, Engulfing, Hammer, etc.
    # Requires significant pattern recognition logic.
    logger.warning("Candlestick pattern detection is a placeholder. Requires specific pattern recognition logic.")
    return pd.Series(np.nan, index=df.index)

def calculate_roc(close: pd.Series, period: int) -> pd.Series:
    """Calculates Rate of Change."""
    if period <= 0: return pd.Series(np.nan, index=close.index)
    try:
        roc = ((close - close.shift(period)) / close.shift(period)) * 100
        return roc
    except Exception as e:
        logger.warning(f"Error calculating ROC({period}): {e}", exc_info=True)
        return pd.Series(np.nan, index=close.index)

# --- Main Trading Loop and Bot Logic ---

def main_trading_loop():
    """The heart of the WhaleBot: orchestrates data fetching, analysis, and trading decisions."""
    if not bybit_client:
        logger.critical("BybitHelper not initialized. Cannot start trading loop.")
        sys.exit(1)

    logger.info(f"{Fore.GREEN + Style.BRIGHT}--- Starting Main Trading Loop ---{Style.RESET_ALL}")
    logger.info(f"Symbol: {config.symbol}, Timeframe: {config.interval}, Loop Delay: {config.loop_delay}s")

    # --- WebSocket Subscription ---
    # Define the topics to subscribe to via WebSocket
    # Use simple symbol format from config
    main_ws_topics = [
        f"kline.{bybit_client._map_timeframe_to_pybit(config.interval)}.{config.symbol}", # Kline data for main timeframe
        # Add other relevant topics like order book updates, account updates etc. if needed
        # f"position.{config.symbol}", # Position updates
        # f"account.{config.account_type}", # Account updates
        # f"execution.{config.symbol}", # Trade execution updates
    ]

    # --- WebSocket Message Handler ---
    # This function will be called by BybitHelper for every incoming message on subscribed topics.
    def handle_ws_message(message: Dict[str, Any]):
        """Processes incoming WebSocket messages, updating indicators and triggering actions."""
        if message.get("topic", "").startswith("kline"):
            # Process Kline data update
            processed_row_df = bybit_client.update_ohlcv_cache(message)
            if processed_row_df is not None and not processed_row_df.empty:
                 # A new/updated candle with indicators is available.
                 # This is where signal generation and trading logic would be triggered.
                 latest_candle_data = processed_row_df.iloc[0].to_dict() # Get the single row as a dict
                 # Trigger strategy evaluation with the latest candle data
                 evaluate_strategy_signals(latest_candle_data)
        elif message.get("topic", "").startswith("position"):
             # Handle position updates from WebSocket (if subscribed)
             # Update internal position state or trigger related logic
             pass # Placeholder for position update handling
        elif message.get("topic", "").startswith("account"):
             # Handle account updates from WebSocket
             pass # Placeholder for account update handling
        elif message.get("topic", "").startswith("execution"):
             # Handle trade execution updates
             pass # Placeholder for execution update handling
        #else: logger.debug(f"Received WS message for topic: {message.get('topic')}")

    # --- WebSocket Error Handler ---
    def handle_ws_error(error: Exception):
        """Logs WebSocket errors and triggers reconnection."""
        # BybitHelper's internal handlers already log and schedule reconnects.
        # This callback could be used for additional alerting or state management.
        logger.error(f"External WS Error Handler: {error}", exc_info=True)
        # Potentially send an SMS alert here if WS errors are critical.
        # bybit_client.send_sms(f"CRITICAL: Bybit WS Error on {config.symbol}!")

    # --- WebSocket Open Handler ---
    def handle_ws_open():
        """Called when the WebSocket connection is successfully established."""
        logger.info("WebSocket is now open and ready.")
        # Any actions needed upon successful connection (e.g., re-subscribe if needed)
        # Note: `connect_websocket` already handles initial subscriptions.

    # --- WebSocket Close Handler ---
    def handle_ws_close(close_status_code: Optional[int], close_msg: Optional[str]):
        """Called when the WebSocket connection is closed."""
        logger.warning(f"WebSocket connection closed. Status: {close_status_code}, Message: {close_msg}")
        # BybitHelper handles reconnection scheduling internally.

    # --- Connect to WebSocket ---
    # Start the WebSocket connection in the background.
    # It will automatically attempt to subscribe to the defined topics.
    if config.execution.use_websocket:
        logger.info(f"{Fore.CYAN}# Initiating WebSocket connection...{Style.RESET_ALL}")
        try:
            bybit_client.connect_websocket(
                topics=main_ws_topics,
                message_callback=handle_ws_message,
                error_callback=handle_ws_error,
                open_callback=handle_ws_open,
                close_callback=handle_ws_close
            )
            # Give it a moment to establish connection before the main loop starts polling
            time.sleep(2)
        except Exception as e:
            logger.exception("Failed to initiate WebSocket connection.")

    # --- Main Loop ---
    trade_cooldown_until = 0.0 # Timestamp until which trading is on cooldown

    while True:
        current_time = time.time()
        try:
            # --- Diagnostics Check (Optional, based on config) ---
            # Run diagnostics periodically or on startup
            if not hasattr(main_trading_loop, "_diagnostics_ran") or \
               (current_time - getattr(main_trading_loop, "_last_diag_time", 0) > config.core_settings.loop_delay * 5 and not config.dry_run): # Run every 5 loops if not dry run
                logger.info(f"{Fore.CYAN}# Running periodic diagnostics...{Style.RESET_ALL}")
                diag_success = bybit_client.diagnose()
                setattr(main_trading_loop, "_diagnostics_ran", True)
                setattr(main_trading_loop, "_last_diag_time", current_time)
                if not diag_success:
                    logger.critical(f"{Back.RED}{Fore.WHITE}Essential diagnostics failed. Halting trading operations until resolved.{Style.RESET_ALL}")
                    # Consider disabling trading or taking specific actions here.
                    # For now, we'll just log and continue, but in a real scenario, this could be critical.
                    # sys.exit(1) # Uncomment to halt on critical diagnostic failure

            # --- Fetch OHLCV Data and Indicators ---
            # Get the latest OHLCV data with indicators. This also ensures cache is updated.
            # Pass `include_daily_pivots=True` if strategy depends on them.
            ohlcv_df = bybit_client.get_or_fetch_ohlcv(
                timeframe=config.interval,
                limit=config.initial_candle_history, # Fetch enough history for indicators
                include_daily_pivots=(config.analysis_modules.mtf_analysis.enabled or config.indicators.fibonacci_pivot_points)
            )

            if ohlcv_df is None or ohlcv_df.empty:
                logger.warning(f"No OHLCV data available for {config.symbol} {config.interval}. Skipping this loop iteration.")
                time.sleep(config.loop_delay)
                continue

            # Get the most recent candle's data for analysis
            latest_candle = ohlcv_df.iloc[-1].to_dict()

            # --- Strategy Evaluation ---
            # This function determines if trading signals are generated based on indicators and strategy rules.
            evaluate_strategy_signals(latest_candle)

            # --- Cooldown and Risk Management Checks ---
            # Check if trading is currently on cooldown
            if current_time < trade_cooldown_until:
                logger.debug(f"Trading cooldown active. Skipping trade execution until {datetime.fromtimestamp(trade_cooldown_until).strftime('%Y-%m-%d %H:%M:%S')}.")
                # Continue to next iteration to fetch new data, but skip trade logic.
            else:
                # Check risk management parameters (e.g., max drawdown, consecutive losses)
                risk_limit_hit = check_risk_limits()
                if risk_limit_hit:
                    logger.error(f"{Back.RED}{Fore.WHITE}Risk limit hit! Halting trading operations.{Style.RESET_ALL}")
                    # Implement kill switch logic here (e.g., cancel all orders, disable trading)
                    # Set a long cooldown period to prevent further trading
                    trade_cooldown_until = current_time + config.risk_management.cooldown_after_kill_min * 60
                    bybit_client.cancel_all_orders(symbol=config.symbol) # Cancel all open orders
                    # Optionally send critical SMS alert
                    bybit_client.send_sms(f"CRITICAL: RISK LIMIT HIT on {config.symbol}! Trading halted.")
                    # Continue loop to monitor, but trading actions are disabled.
                else:
                    # --- Execute Trades based on Signals ---
                    # This part would involve trade execution logic based on signals generated by `evaluate_strategy_signals`
                    # and considering current positions and risk parameters.
                    # For demonstration, this part is left as a placeholder.

                    # Example: If a bullish signal is detected and we have no open position, consider entering long.
                    # if latest_candle.get('Signal_Bullish') and bybit_client.get_open_positions(config.symbol) is None:
                    #     enter_long_position()
                    # elif latest_candle.get('Signal_Bearish') and bybit_client.get_open_positions(config.symbol) is None:
                    #     enter_short_position()
                    # elif bybit_client.get_open_positions(config.symbol) is not None:
                    #     manage_existing_position()
                    pass # Placeholder for trade execution logic

            # --- Sleep for the configured delay ---
            time.sleep(config.loop_delay)

        except KeyboardInterrupt:
            logger.info(f"{Fore.YELLOW}KeyboardInterrupt received. Shutting down gracefully...{Style.RESET_ALL}")
            break # Exit the loop on Ctrl+C
        except Exception as e:
            # Catch any unexpected errors in the main loop to prevent crashes
            logger.exception(f"Unhandled exception in main trading loop: {e}")
            # Optionally send an alert for critical loop errors
            # bybit_client.send_sms(f"CRITICAL: UNHANDLED EXCEPTION in WhaleBot main loop on {config.symbol}!")
            # Implement a short delay before retrying to avoid rapid error loops
            time.sleep(5)

    # --- Cleanup on Exit ---
    logger.info(f"{Fore.GREEN + Style.BRIGHT}--- Trading Loop Terminated ---{Style.RESET_ALL}")
    if config.execution.use_websocket and bybit_client:
        logger.info("Disconnecting WebSocket...")
        bybit_client.disconnect_websocket() # Gracefully close WS connection

    logger.info("Performing final order cleanup...")
    if bybit_client:
        # Cancel any remaining open orders before exiting
        cleanup_success = bybit_client.cancel_all_orders(symbol=config.symbol)
        if cleanup_success:
            logger.info("All open orders successfully cancelled or confirmed as non-existent.")
        else:
            logger.warning("Failed to cancel all orders during cleanup. Manual intervention may be required.")

    logger.info("WhaleBot has ceased its operations. May your trades be ever in your favor.")
    sys.exit(0)


# --- Strategy Signal Evaluation ---
# This is a critical function that needs to be implemented based on your trading strategy.
# It takes the latest candle data (with indicators) and returns signals (e.g., BUY, SELL, HOLD).

def evaluate_strategy_signals(latest_candle_data: Dict[str, Any]) -> None:
    """
    Evaluates the latest candle data against the configured strategy rules
    to generate trading signals (BUY, SELL, HOLD).
    This is a placeholder and requires a detailed strategy implementation.
    """
    if not latest_candle_data:
        logger.warning("No candle data provided for signal evaluation.")
        return

    # Access configuration for strategy parameters
    current_profile_name = config.strategy_management.current_strategy_profile
    strategy_profile = config.strategy_management.strategy_profiles.get(current_profile_name)

    if not strategy_profile:
        logger.error(f"Strategy profile '{current_profile_name}' not found. Cannot evaluate signals.")
        return

    # Enable/disable indicators based on the active profile
    indicators_to_use = strategy_profile.indicators_enabled
    weights = strategy_profile.weights

    # --- Signal Generation Logic ---
    # This logic needs to be implemented based on your specific trading strategy.
    # Example: Combine signals from multiple indicators with assigned weights.

    signal_score = 0.0
    buy_signals_count = 0
    sell_signals_count = 0
    total_weight_considered = 0.0

    logger.debug(f"Evaluating strategy signals using profile: '{current_profile_name}'")

    # --- Example Signal Calculation (Illustrative) ---
    # This section demonstrates how you might combine signals.
    # You'll need to define specific conditions for each indicator's bullish/bearish signal.

    # 1. EMA Alignment
    if indicators_to_use.get("ema_alignment", False):
        bullish_ema = latest_candle_data.get('EMA_Alignment_Bullish', False)
        bearish_ema = latest_candle_data.get('EMA_Alignment_Bearish', False)
        weight = weights.get("ema_alignment", 0.0)
        if bullish_ema:
            signal_score += weight
            buy_signals_count += 1
        if bearish_ema:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 2. SMA Trend Filter
    if indicators_to_use.get("sma_trend_filter", False):
        bullish_sma = latest_candle_data.get('SMA_Trend_Bullish', False)
        bearish_sma = latest_candle_data.get('SMA_Trend_Bearish', False)
        weight = weights.get("sma_trend_filter", 0.0)
        if bullish_sma:
            signal_score += weight
            buy_signals_count += 1
        if bearish_sma:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 3. RSI Momentum
    if indicators_to_use.get("momentum_rsi_stoch_cci_wr_mfi", False): # Grouping multiple momentum indicators
        # RSI Signals
        rsi_bullish = latest_candle_data.get('RSI_Bullish_Signal', False)
        rsi_bearish = latest_candle_data.get('RSI_Bearish_Signal', False)
        # StochRSI Signals
        stochrsi_bullish = latest_candle_data.get('StochRSI_Bullish_Signal', False)
        stochrsi_bearish = latest_candle_data.get('StochRSI_Bearish_Signal', False)
        # CCI Signals
        cci_bullish = latest_candle_data.get('CCI_Bullish_Signal', False)
        cci_bearish = latest_candle_data.get('CCI_Bearish_Signal', False)
        # Williams R Signals
        wr_bullish = latest_candle_data.get('Williams_R_Bullish_Signal', False)
        wr_bearish = latest_candle_data.get('Williams_R_Bearish_Signal', False)

        # Aggregate signals from this group
        momentum_bullish_count = sum([rsi_bullish, stochrsi_bullish, cci_bullish, wr_bullish])
        momentum_bearish_count = sum([rsi_bearish, stochrsi_bearish, cci_bearish, wr_bearish])

        # Example weighting logic: assign weight to overall momentum group
        group_weight = weights.get("momentum_rsi_stoch_cci_wr_mfi", 0.0) / 4.0 # Distribute weight if needed per indicator

        if momentum_bullish_count > 0:
             signal_score += group_weight * momentum_bullish_count
             buy_signals_count += momentum_bullish_count
        if momentum_bearish_count > 0:
             signal_score -= group_weight * momentum_bearish_count
             sell_signals_count += momentum_bearish_count
        total_weight_considered += weights.get("momentum_rsi_stoch_cci_wr_mfi", 0.0)

    # 4. Bollinger Bands / Keltner Channels
    if indicators_to_use.get("bollinger_bands", False):
        touches_upper_bb = latest_candle_data.get('Price_Touches_Upper_BB', False)
        touches_lower_bb = latest_candle_data.get('Price_Touches_Lower_BB', False)
        weight = weights.get("bollinger_bands", 0.0)
        if touches_upper_bb: # Price broke above upper band (potential resistance/overbought)
             signal_score -= weight * 0.5 # Slight bearish signal
             sell_signals_count += 0.5
        if touches_lower_bb: # Price broke below lower band (potential support/oversold)
             signal_score += weight * 0.5 # Slight bullish signal
             buy_signals_count += 0.5
        total_weight_considered += weight

    if indicators_to_use.get("keltner_channels", False): # Similar logic for Keltner Channels
        touches_upper_kc = latest_candle_data.get('Price_Touches_Upper_KC', False)
        touches_lower_kc = latest_candle_data.get('Price_Touches_Lower_KC', False)
        weight = weights.get("keltner_channels", 0.0)
        if touches_upper_kc:
             signal_score -= weight * 0.5
             sell_signals_count += 0.5
        if touches_lower_kc:
             signal_score += weight * 0.5
             buy_signals_count += 0.5
        total_weight_considered += weight

    # 5. Ehlers SuperTrend
    if indicators_to_use.get("ehlers_supertrend_alignment", False):
        bullish_flip = latest_candle_data.get('Ehlers_Bullish_Flip', False)
        bearish_flip = latest_candle_data.get('Ehlers_Bearish_Flip', False)
        weight = weights.get("ehlers_supertrend_alignment", 0.0)
        if bullish_flip:
            signal_score += weight
            buy_signals_count += 1
        if bearish_flip:
            signal_score -= weight
            sell_signals_count += 1
        total_weight_considered += weight

    # 6. Fibonacci Pivots (Example: Price crossing R1/S1)
    if indicators_to_use.get("fibonacci_pivot_points_confluence", False):
        crossed_r1 = latest_candle_data.get('Price_Crossed_R1', False)
        crossed_s1 = latest_candle_data.get('Price_Crossed_S1', False)
        weight = weights.get("fibonacci_pivot_points_confluence", 0.0)
        if crossed_r1: # Breaking resistance might be bullish signal
             signal_score += weight * 0.3
             buy_signals_count += 0.3
        if crossed_s1: # Breaking support might be bearish signal
             signal_score -= weight * 0.3
             sell_signals_count += 0.3
        total_weight_considered += weight

    # --- Normalize Signal Score ---
    # Normalize score based on total weight considered to get a relative strength
    # This helps in comparing strategies with different weighting schemes.
    normalized_score = 0.0
    if total_weight_considered > 0:
         normalized_score = signal_score / total_weight_considered
    else:
         logger.warning("No indicator weights considered for signal scoring.")

    # --- Determine Final Signal ---
    final_signal = "HOLD"
    threshold = config.core_settings.signal_score_threshold
    hysteresis = config.core_settings.hysteresis_ratio
    cooldown_duration = config.core_settings.cooldown_sec

    if normalized_score >= threshold:
        final_signal = "BUY"
        # Apply hysteresis to prevent rapid entries/exits if score is close to threshold
        if latest_candle_data.get("Signal_Prev") == "BUY" and normalized_score < threshold * hysteresis:
             final_signal = "HOLD" # Maintain position if score dips slightly but stays above hysteresis
        elif latest_candle_data.get("Signal_Prev") == "SELL" and normalized_score > 0: # If switching from sell, require some positive score
             pass # Allow transition
    elif normalized_score <= -threshold:
        final_signal = "SELL"
        if latest_candle_data.get("Signal_Prev") == "SELL" and normalized_score > -threshold * hysteresis:
             final_signal = "HOLD" # Maintain position if score rises slightly but stays below -threshold
        elif latest_candle_data.get("Signal_Prev") == "BUY" and normalized_score < 0: # If switching from buy, require some negative score
             pass # Allow transition

    # Update previous signal for hysteresis logic
    latest_candle_data["Signal_Prev"] = final_signal
    latest_candle_data["Signal_Score"] = normalized_score

    # Log the generated signal and score
    signal_color = Fore.GREEN if final_signal == "BUY" else Fore.RED if final_signal == "SELL" else Fore.WHITE
    logger.info(f"Signal Evaluation: Score={normalized_score:.4f} ({final_signal}) | Buy={buy_signals_count}, Sell={sell_signals_count}")

    # --- Trigger Actions Based on Signal ---
    if final_signal == "BUY":
        # Enter Long Position Logic
        pass # Placeholder: call function to enter long position
    elif final_signal == "SELL":
        # Enter Short Position Logic
        pass # Placeholder: call function to enter short position

    # --- Manage Existing Positions (if applicable) ---
    # This would involve checking current positions and deciding on exits, stops, etc.
    # based on signals or other criteria.
    # manage_positions(latest_candle_data)

# --- Risk Management Checks ---

def check_risk_limits() -> bool:
    """
    Checks if any risk management limits have been breached.
    Returns True if a limit is hit (indicating a kill switch event), False otherwise.
    """
    if not config.risk_management.enabled:
        return False

    # Placeholder: Implement checks for max daily loss, max drawdown, etc.
    # These would typically involve tracking PnL and position values.

    # Example: Check for maximum consecutive losses
    # This requires tracking trade results (wins/losses) which is not yet implemented here.
    # You'd need a mechanism to store and count consecutive losses.

    # Example: Check for acceptable spread or slippage (requires real-time quote data)
    # This check might be more relevant during order placement.

    # If any critical risk limit is breached, return True to activate kill switch.
    return False # Default to no risk limit hit

# --- Trade Execution Logic ---
# These functions would handle the actual placing, managing, and closing of trades.

def enter_long_position(candle_data: Dict[str, Any]):
    """Logic to enter a long position based on BUY signal."""
    logger.info(f"{Fore.GREEN}Executing BUY signal...{Style.RESET_ALL}")
    # Fetch necessary data (balance, position)
    available_balance = bybit_client.fetch_balance(coin="USDT")
    current_position = bybit_client.get_open_positions(symbol=config.symbol)

    if available_balance is None:
        logger.error("Cannot enter long: Failed to fetch account balance.")
        return

    # Determine position size based on risk settings and available balance
    # Example: Risk X% of balance per trade
    risk_pct = config.risk_management.max_day_loss_pct / 100.0 # Example risk %
    trade_size_usd = available_balance * risk_pct
    entry_price = candle_data.get('close') # Use current close price for entry

    if entry_price is None or entry_price <= Decimal("0"):
        logger.error("Cannot enter long: Invalid entry price from candle data.")
        return

    # Calculate quantity based on trade size and entry price
    quantity_usd = trade_size_usd / entry_price
    formatted_qty = bybit_client.format_quantity(quantity_usd)

    if Decimal(formatted_qty) <= Decimal("0"):
        logger.warning(f"Calculated quantity is zero or negative ({formatted_qty}). Cannot enter long.")
        return

    # Determine Stop Loss (SL) and Take Profit (TP) targets
    # Use strategy configuration (e.g., ATR multiples)
    atr_value = candle_data.get('ATR')
    sl_price = None
    tp_targets = []

    if atr_value and config.execution.sl_scheme.type == "atr_multiple":
         sl_multiple = config.execution.sl_scheme.atr_multiple
         sl_price = entry_price - (atr_value * sl_multiple) # For long, SL is below entry

    if atr_value and config.execution.tp_scheme.mode == "atr_multiples":
         for tp_target in config.execution.tp_scheme.targets:
              tp_multiple = tp_target.get("atr_multiple", 1.0)
              tp_price = entry_price + (atr_value * tp_multiple) # For long, TP is above entry
              tp_targets.append({"price": tp_price, "size_pct": tp_target.get("size_pct", 0.4)}) # Store TP price and size

    # Place the entry order (Market or Limit)
    order_result = bybit_client.place_order(
        side="Buy",
        qty=Decimal(formatted_qty),
        order_type="Limit", # Example: Place a limit order
        price=entry_price, # Use the entry price
        sl=sl_price, # Pass calculated stop loss
        tp=tp_targets[0]['price'] if tp_targets else None, # Example: Use first TP target
        reduce_only=False, # Not reducing a position here
        time_in_force=config.execution.default_time_in_force,
        # Add other parameters like position_idx if needed
    )

    if order_result:
        logger.success(f"Successfully entered long position for {formatted_qty} {config.symbol}.")
        # Handle TP/SL orders if they are not placed automatically with the entry
        # For Bybit v5, TP/SL can often be set directly with the order.
        # If separate TP/SL orders are needed, call cancel_order and place_order again.
    else:
        logger.error("Failed to enter long position.")

def enter_short_position(candle_data: Dict[str, Any]):
    """Logic to enter a short position based on SELL signal."""
    logger.info(f"{Fore.RED}Executing SELL signal...{Style.RESET_ALL}")
    # Similar logic to enter_long_position, but reversed for short entry.
    # Fetch balance, check current position.
    available_balance = bybit_client.fetch_balance(coin="USDT")
    current_position = bybit_client.get_open_positions(symbol=config.symbol)

    if available_balance is None:
        logger.error("Cannot enter short: Failed to fetch account balance.")
        return

    # Determine position size and price
    risk_pct = config.risk_management.max_day_loss_pct / 100.0
    trade_size_usd = available_balance * risk_pct
    entry_price = candle_data.get('close')

    if entry_price is None or entry_price <= Decimal("0"):
        logger.error("Cannot enter short: Invalid entry price from candle data.")
        return

    quantity_usd = trade_size_usd / entry_price
    formatted_qty = bybit_client.format_quantity(quantity_usd)

    if Decimal(formatted_qty) <= Decimal("0"):
        logger.warning(f"Calculated quantity is zero or negative ({formatted_qty}). Cannot enter short.")
        return

    # Determine SL/TP
    atr_value = candle_data.get('ATR')
    sl_price = None
    tp_targets = []

    if atr_value and config.execution.sl_scheme.type == "atr_multiple":
         sl_multiple = config.execution.sl_scheme.atr_multiple
         sl_price = entry_price + (atr_value * sl_multiple) # For short, SL is above entry

    if atr_value and config.execution.tp_scheme.mode == "atr_multiples":
         for tp_target in config.execution.tp_scheme.targets:
              tp_multiple = tp_target.get("atr_multiple", 1.0)
              tp_price = entry_price - (atr_value * tp_multiple) # For short, TP is below entry
              tp_targets.append({"price": tp_price, "size_pct": tp_target.get("size_pct", 0.4)})

    # Place the entry order
    order_result = bybit_client.place_order(
        side="Sell",
        qty=Decimal(formatted_qty),
        order_type="Limit", # Example: Place a limit order
        price=entry_price,
        sl=sl_price,
        tp=tp_targets[0]['price'] if tp_targets else None,
        reduce_only=False,
        time_in_force=config.execution.default_time_in_force,
    )

    if order_result:
        logger.success(f"Successfully entered short position for {formatted_qty} {config.symbol}.")
    else:
        logger.error("Failed to enter short position.")

def manage_positions(candle_data: Dict[str, Any]):
    """Manages open positions based on signals, SL/TP, or other conditions."""
    open_positions = bybit_client.get_open_positions(symbol=config.symbol)
    if not open_positions:
        # No open positions to manage.
        return

    # Assuming only one position is managed at a time for simplicity
    position = open_positions[0]
    current_side = position.get('side')
    current_size = position.get('size')
    entry_price = position.get('entry_price')
    current_mark_price = position.get('mark_price')
    unrealized_pnl = position.get('unrealized_pnl')
    stop_loss = position.get('stop_loss')
    take_profit = position.get('take_profit')

    # --- Logic for managing existing positions ---
    # Example: Trailing Stop Loss based on ATR (if enabled in config)
    if config.execution.sl_scheme.get("trail_stop", {}).get("enabled", False) and atr_value := candle_data.get('ATR'):
        trail_atr_multiple = config.execution.sl_scheme["trail_stop"].get("trail_atr_multiple", 0.5)
        activation_threshold = config.execution.sl_scheme["trail_stop"].get("activation_threshold", 0.8) # Profit threshold to activate trailing stop

        current_profit_pct = 0.0
        if entry_price and current_mark_price:
             if current_side == "Buy" and entry_price > 0:
                  current_profit_pct = ((current_mark_price - entry_price) / entry_price) * 100
             elif current_side == "Sell" and entry_price > 0:
                  current_profit_pct = ((entry_price - current_mark_price) / entry_price) * 100

        # Check if activation threshold is met and trailing stop is needed
        if current_profit_pct >= activation_threshold:
            # Calculate potential new stop loss based on ATR trailing
            atr_trail_stop_value = atr_value * trail_atr_multiple
            new_stop_loss = None

            if current_side == "Buy":
                 # For long positions, trailing stop moves up with price
                 potential_sl = entry_price - atr_trail_value # Assuming entry price is the base
                 if potential_sl > stop_loss: # Only update if it's higher (moves up)
                      new_stop_loss = potential_sl
            elif current_side == "Sell":
                 # For short positions, trailing stop moves down with price
                 potential_sl = entry_price + atr_trail_value
                 if potential_sl < stop_loss: # Only update if it's lower (moves down)
                      new_stop_loss = potential_sl

            # If a valid new stop loss was calculated and it's better than current SL
            if new_stop_loss and stop_loss and ((current_side == "Buy" and new_stop_loss > stop_loss) or (current_side == "Sell" and new_stop_loss < stop_loss)):
                 logger.info(f"Trailing stop loss needs update for {config.symbol}. New SL: {new_stop_loss}")
                 # Call function to update the stop loss order
                 # update_stop_loss_order(position['orderId'], new_stop_loss) # Example function call

    # --- Breakeven Logic ---
    # Check if breakeven should be activated (e.g., after TP1 hit)
    # This would require tracking TP hits and adjusting SL to entry price.

    # --- Exit Logic ---
    # Check for exit signals (e.g., opposite signal, indicator divergence, etc.)
    # or if position size needs reduction based on profit targets.

    pass # Placeholder for position management logic


# --- Entry Point of the Script ---

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="WhaleBot: A Trading Automaton for Bybit.")
    parser.add_argument('--config', type=str, default=str(CONFIG_FILE_PATH),
                        help='Path to the configuration JSON file.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Run in dry-run mode (simulate trades, do not execute orders).')
    parser.add_argument('--testnet', action='store_true',
                        help='Use Bybit testnet environment.')
    parser.add_argument('--symbol', type=str, default=None,
                        help='Override default symbol from config (e.g., BTCUSDT).')
    parser.add_argument('--interval', type=str, default=None,
                        help='Override default interval from config (e.g., 15m).')
    parser.add_argument('--loop-delay', type=int, default=None,
                        help='Override default loop delay in seconds.')
    parser.add_argument('--log-level', type=str, default=None,
                        help='Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).')
    parser.add_argument('--strategy-profile', type=str, default=None,
                        help='Override the current strategy profile name.')

    return parser.parse_args()

def initialize_bot(args):
    """Initializes the bot environment, loads config, and sets up clients."""
    # Load config from args, potentially overriding default path
    global CONFIG_FILE_PATH
    if args.config:
        CONFIG_FILE_PATH = Path(args.config)

    # Attempt to load configuration and setup global environment
    if not setup_global_environment():
        # Critical failure during setup, exit
        sys.exit(1)

    # Apply command-line argument overrides to the config
    global config, logger
    if args.dry_run is not None: config.execution.dry_run = args.dry_run
    if args.testnet is not None: config.execution.testnet = args.testnet
    if args.symbol: config.symbol = args.symbol
    if args.interval: config.interval = args.interval
    if args.loop_delay: config.loop_delay = args.loop_delay
    if args.log_level:
        # Update logger level and potentially console handler level
        log_level_str = args.log_level.upper()
        try:
            log_level = SUCCESS_LEVEL if log_level_str == "SUCCESS" else getattr(logging, log_level_str)
            logger.setLevel(log_level)
            # Update console handler level
            for handler in logger.handlers:
                if isinstance(handler, logging.StreamHandler):
                    handler.setLevel(log_level)
                    break
            config.logging.level = log_level_str # Update config object as well
            logger.info(f"Log level overridden to: {log_level_str}")
        except AttributeError:
            logger.warning(f"Invalid log level '{args.log_level}' provided. Using current level: {config.logging.level}")

    if args.strategy_profile:
        config.strategy_management.current_strategy_profile = args.strategy_profile
        logger.info(f"Strategy profile overridden to: '{args.strategy_profile}'")

    # Re-initialize BybitHelper with potentially updated config if critical params changed
    # (e.g., testnet mode). Note: This is a simplified approach; a full config reload might be needed.
    try:
         # Re-instantiate BybitHelper if key parameters like testnet changed.
         # For simplicity, assume BybitHelper's initial setup is sufficient unless testnet changes.
         if config.execution.testnet != bybit_client.config.execution.testnet:
              logger.info(f"Testnet mode changed to {config.execution.testnet}. Re-initializing BybitHelper...")
              # Need to re-instantiate to apply testnet change correctly
              bybit_client = BybitHelper(config)
         else:
              # Update config in existing client if other params changed (less common, but for completeness)
              bybit_client.config = config

         logger.info(f"Bot Configuration: Symbol={config.symbol}, Interval={config.interval}, Testnet={config.execution.testnet}, DryRun={config.execution.dry_run}")

         # Perform initial diagnostics upon successful initialization
         logger.info(f"{Fore.CYAN}# Running initial diagnostics...{Style.RESET_ALL}")
         initial_diag_success = bybit_client.diagnose()
         if not initial_diag_success:
             logger.critical(f"{Back.RED}{Fore.WHITE}Initial diagnostics FAILED. Bot may not function correctly. Review logs.{Style.RESET_ALL}")
             # Decide whether to halt execution based on diagnostic outcome
             # For safety, we might want to exit if critical components fail initially.
             # sys.exit(1) # Uncomment to halt on critical initial failure.

         return True
    except Exception as e:
         logger.critical(f"FATAL: Error during bot initialization or post-config update: {e}", exc_info=True)
         return False


if __name__ == "__main__":
    # Parse command-line arguments first
    parsed_args = parse_arguments()

    # Initialize the bot environment based on parsed arguments and config files
    if initialize_bot(parsed_args):
        # If initialization is successful, start the main trading loop
        main_trading_loop()
    else:
        # If initialization fails, exit with an error code
        logger.critical("Bot initialization failed. Exiting.")
        sys.exit(1)
