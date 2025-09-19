// configLoader.js
import fs from 'fs';
import yaml from 'js-yaml'; // Assuming js-yaml is installed. If not, `npm install js-yaml`

const CONFIG_FILE_PATH = './config.yaml';

function loadConfig() {
  try {
    const yamlContent = fs.readFileSync(CONFIG_FILE_PATH, 'utf8');
    const config = yaml.load(yamlContent);

    // Flatten and merge with environment variables
    const botConfig = {
      // API & General Settings
      TESTNET: config.api.testnet,
      DRY_RUN: config.api.dry_run,
      API_KEY: process.env.BYBIT_API_KEY || null,
      API_SECRET: process.env.BYBIT_API_SECRET || null,

      // Bot Behavior
      LOG_LEVEL: config.bot.log_level,
      LOOP_WAIT_TIME_SECONDS: config.bot.loop_wait_time_seconds,
      TIMEZONE: config.bot.timezone,
      MARKET_OPEN_HOUR: config.bot.market_open_hour,
      MARKET_CLOSE_HOUR: config.bot.market_close_hour,

      // Trading Parameters
      TIMEFRAME: config.trading.timeframe,
      TRADING_SYMBOLS: config.trading.trading_symbols,
      MAX_POSITIONS: config.trading.max_positions,
      MAX_OPEN_ORDERS_PER_SYMBOL: config.trading.max_open_orders_per_symbol,
      MIN_KLINES_FOR_STRATEGY: config.trading.min_klines_for_strategy,
      MAX_HOLDING_CANDLES: config.trading.max_holding_candles,

      // Risk & Position Sizing
      MARGIN_MODE: config.risk_management.margin_mode,
      LEVERAGE: config.risk_management.leverage,
      RISK_PER_TRADE_PCT: config.risk_management.risk_per_trade_pct,
      MAX_NOTIONAL_PER_TRADE_USDT: config.risk_management.order_qty_usdt, // Renamed for clarity

      // Strategy Parameters (Ehlers Supertrend Cross Strategy)
      EST_FAST_LENGTH: config.strategy.est_fast.length,
      EST_FAST_MULTIPLIER: config.strategy.est_fast.multiplier,
      EST_SLOW_LENGTH: config.strategy.est_slow.length,
      EST_SLOW_MULTIPLIER: config.strategy.est_slow.multiplier,
      EHLERS_FISHER_PERIOD: config.strategy.ehlers_fisher.period,
      RSI_PERIOD: config.strategy.rsi.period,
      RSI_OVERBOUGHT: config.strategy.rsi.overbought,
      RSI_OVERSOLD: config.strategy.rsi.oversold,
      RSI_CONFIRM_LONG_THRESHOLD: config.strategy.rsi.confirm_long_threshold,
      RSI_CONFIRM_SHORT_THRESHOLD: config.strategy.rsi.confirm_short_threshold,
      VOLUME_MA_PERIOD: config.strategy.volume.ma_period,
      VOLUME_THRESHOLD_MULTIPLIER: config.strategy.volume.threshold_multiplier,
      ATR_PERIOD: config.strategy.atr.period,

      // Order & Exit Logic
      REWARD_RISK_RATIO: config.order_logic.reward_risk_ratio,
      USE_ATR_FOR_TP_SL: config.order_logic.use_atr_for_tp_sl,
      TP_ATR_MULTIPLIER: config.order_logic.tp_atr_multiplier,
      SL_ATR_MULTIPLIER: config.order_logic.sl_atr_multiplier,
      PRICE_DETECTION_THRESHOLD_PCT: config.order_logic.price_detection_threshold_pct,
      BREAKOUT_TRIGGER_PERCENT: config.order_logic.breakout_trigger_pct,

      // New parameters for filters (default to false if not in config)
      USE_STOCH_FILTER: config.strategy.use_stoch_filter || false,
      STOCH_K_PERIOD: config.strategy.stoch_k_period || 14,
      STOCH_D_PERIOD: config.strategy.stoch_d_period || 3,
      STOCH_SMOOTHING: config.strategy.stoch_smoothing || 3,
      STOCH_OVERBOUGHT: config.strategy.stoch_overbought || 80,
      STOCH_OVERSOLD: config.strategy.stoch_oversold || 20,

      USE_MACD_FILTER: config.strategy.use_macd_filter || false,
      MACD_FAST_PERIOD: config.strategy.macd_fast_period || 12,
      MACD_SLOW_PERIOD: config.strategy.macd_slow_period || 26,
      MACD_SIGNAL_PERIOD: config.strategy.macd_signal_period || 9,

      USE_ADX_FILTER: config.strategy.use_adx_filter || false,
      ADX_PERIOD: config.strategy.adx_period || 14,
      ADX_THRESHOLD: config.strategy.adx_threshold || 25,

      // Add these from the original BOT_CONFIG if they were present and not in config.yaml
      ORDER_RETRY_ATTEMPTS: config.bot.order_retry_attempts || 3, // Default if not in config.yaml
      ORDER_RETRY_DELAY_SECONDS: config.bot.order_retry_delay_seconds || 5, // Default if not in config.yaml
      ORDER_TYPE: config.order_logic.order_type || "Market", // Default if not in config.yaml
      POST_ONLY: config.order_logic.post_only || false, // Default if not in config.yaml
      TRAILING_STOP_ACTIVE: config.order_logic.trailing_stop_active || false, // Default if not in config.yaml
      USE_FISHER_EXIT: config.order_logic.use_fisher_exit || false, // Default if not in config.yaml
      FIXED_PROFIT_TARGET_PCT: config.order_logic.fixed_profit_target_pct || 0, // Default if not in config.yaml
      EMERGENCY_STOP_IF_DOWN_PCT: config.bot.emergency_stop_if_down_pct || 15, // Default if not in config.yaml
      MIN_BARS_BETWEEN_TRADES: config.trading.min_bars_between_trades || 1, // Default if not in config.yaml
      TREND_EMA_PERIOD: config.strategy.trend_ema_period || 50, // Default if not in config.yaml
      EMA_SHORT_PERIOD: config.strategy.ema_short_period || 8, // Default if not in config.yaml
      EMA_LONG_PERIOD: config.strategy.ema_long_period || 21, // Default if not in config.yaml
      H_TF_EMA_SHORT_PERIOD: config.strategy.h_tf_ema_short_period || 8, // Default if not in config.yaml
      H_TF_EMA_LONG_PERIOD: config.strategy.h_tf_ema_long_period || 21, // Default if not in config.yaml
      HIGHER_TF_TIMEFRAME: config.trading.higher_tf_timeframe || 5, // Default if not in config.yaml
      CHANDELIER_MULTIPLIER: config.strategy.chandelier_multiplier || 3.0, // Default if not in config.yaml
      MAX_ATR_MULTIPLIER: config.strategy.max_atr_multiplier || 5.0, // Default if not in config.yaml
      MIN_ATR_MULTIPLIER: config.strategy.min_atr_multiplier || 1.0, // Default if not in config.yaml
      VOLATILITY_LOOKBACK: config.strategy.volatility_lookback || 20, // Default if not in config.yaml
    };

    // Validate essential parameters
    if (!botConfig.API_KEY || !botConfig.API_SECRET) {
      throw new Error("BYBIT_API_KEY and BYBIT_API_SECRET must be set as environment variables.");
    }
    if (!botConfig.TRADING_SYMBOLS || botConfig.TRADING_SYMBOLS.length === 0) {
      throw new Error("TRADING_SYMBOLS must be configured in config.yaml.");
    }

    return botConfig;

  } catch (e) {
    console.error(`Error loading configuration: ${e.message}`);
    process.exit(1); // Exit if config cannot be loaded
  }
}

export const BOT_CONFIG = loadConfig();