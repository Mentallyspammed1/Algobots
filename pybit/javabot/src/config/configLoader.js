const Joi = require('joi');
const dotenv = require('dotenv');
const path = require('path');
const fs = require('fs');
const configSchema = require('./schema'); // Assuming schema.js is in the same directory

dotenv.config(); // Load .env variables

function loadConfig() {
  // Load config from process.env
  const envConfig = {
    apiKey: process.env.BYBIT_API_KEY,
    secret: process.env.BYBIT_SECRET,
    symbol: process.env.SYMBOL,
    isTestnet: process.env.TESTNET !== undefined ? process.env.TESTNET === 'true' : undefined,
    dryRun: process.env.DRY_RUN !== undefined ? process.env.DRY_RUN === 'true' : undefined,
    bidSpreadBase: process.env.BID_SPREAD_BASE !== undefined ? parseFloat(process.env.BID_SPREAD_BASE) : undefined,
    askSpreadBase: process.env.ASK_SPREAD_BASE !== undefined ? parseFloat(process.env.ASK_SPREAD_BASE) : undefined,
    maxOrdersPerSide: process.env.MAX_ORDERS_PER_SIDE !== undefined ? parseInt(process.env.MAX_ORDERS_PER_SIDE, 10) : undefined,
    minOrderSize: process.env.MIN_ORDER_SIZE !== undefined ? parseFloat(process.env.MIN_ORDER_SIZE) : undefined,
    orderSizeFixed: process.env.ORDER_SIZE_FIXED !== undefined ? process.env.ORDER_SIZE_FIXED === 'true' : undefined,
    volatilityWindow: process.env.VOLATILITY_WINDOW !== undefined ? parseInt(process.env.VOLATILITY_WINDOW, 10) : undefined,
    volatilityFactor: process.env.VOLATILITY_FACTOR !== undefined ? parseFloat(process.env.VOLATILITY_FACTOR) : undefined,
    refreshInterval: process.env.REFRESH_INTERVAL !== undefined ? parseInt(process.env.REFRESH_INTERVAL, 10) : undefined,
    heartbeatInterval: process.env.HEARTBEAT_INTERVAL !== undefined ? parseInt(process.env.HEARTBEAT_INTERVAL, 10) : undefined,
    retryDelayBase: process.env.RETRY_DELAY_BASE !== undefined ? parseInt(process.env.RETRY_DELAY_BASE, 10) : undefined,
    maxNetPosition: process.env.MAX_NET_POSITION !== undefined ? parseFloat(process.env.MAX_NET_POSITION) : undefined,
    stopOnLargePos: process.env.STOP_ON_LARGE_POS !== undefined ? process.env.STOP_ON_LARGE_POS === 'true' : undefined,
    inventorySizeFactor: process.env.INVENTORY_SIZE_FACTOR !== undefined ? parseFloat(process.env.INVENTORY_SIZE_FACTOR) : undefined,
    logToFile: process.env.LOG_TO_FILE !== undefined ? process.env.LOG_TO_FILE === 'true' : undefined,
    logLevel: process.env.LOG_LEVEL,
    pnlCsvPath: process.env.PNL_CSV_PATH,
    useTermuxSms: process.env.USE_TERMUX_SMS !== undefined ? process.env.USE_TERMUX_SMS === 'true' : undefined,
    smsPhoneNumber: process.env.SMS_PHONE_NUMBER,
    positionSkewFactor: process.env.POSITION_SKEW_FACTOR !== undefined ? parseFloat(process.env.POSITION_SKEW_FACTOR) : undefined,
    volatilitySpreadFactor: process.env.VOLATILITY_SPREAD_FACTOR !== undefined ? parseFloat(process.env.VOLATILITY_SPREAD_FACTOR) : undefined,
    stateFilePath: process.env.STATE_FILE_PATH,
    fillProbability: process.env.FILL_PROBABILITY !== undefined ? parseFloat(process.env.FILL_PROBABILITY) : undefined,
    slippageFactor: process.env.SLIPPAGE_FACTOR !== undefined ? parseFloat(process.env.SLIPPAGE_FACTOR) : undefined,
    gridSpacingBase: process.env.GRID_SPACING_BASE !== undefined ? parseFloat(process.env.GRID_SPACING_BASE) : undefined,
    imbalanceSpreadFactor: process.env.IMBALANCE_SPREAD_FACTOR !== undefined ? parseFloat(process.env.IMBALANCE_SPREAD_FACTOR) : undefined,
    imbalanceOrderSizeFactor: process.env.IMBALANCE_ORDER_SIZE_FACTOR !== undefined ? parseFloat(process.env.IMBALANCE_ORDER_SIZE_FACTOR) : undefined,
    priceDisplayPrecision: process.env.PRICE_DISPLAY_PRECISION !== undefined ? parseInt(process.env.PRICE_DISPLAY_PRECISION, 10) : undefined,
    qtyDisplayPrecision: process.env.QTY_DISPLAY_PRECISION !== undefined ? parseInt(process.env.QTY_DISPLAY_PRECISION, 10) : undefined,
    riskClearedThresholdFactor: process.env.RISK_CLEARED_THRESHOLD_FACTOR !== undefined ? parseFloat(process.env.RISK_CLEARED_THRESHOLD_FACTOR) : undefined,
    maxPriceHistoryLength: process.env.MAX_PRICE_HISTORY_LENGTH !== undefined ? parseInt(process.env.MAX_PRICE_HISTORY_LENGTH, 10) : undefined,
  };

  // Validate config against schema
  const { error, value } = configSchema.validate(envConfig, {
    abortEarly: false, // Report all errors, not just the first one
    stripUnknown: true, // Remove unknown keys
  });

  if (error) {
    console.error('❌ FATAL: Configuration validation error:');
    error.details.forEach(err => console.error(`   - ${err.message}`));
    process.exit(1);
  }

  // Add derived properties
  value.baseUrl = value.isTestnet ? 'https://api-testnet.bybit.com' : 'https://api.bybit.com';
  value.baseCurrency = (value.symbol || '').replace('USDT', '');

  return value;
}

module.exports = loadConfig(); // Export the loaded and validated config directly