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
    isTestnet: process.env.TESTNET === 'true',
    dryRun: process.env.DRY_RUN === 'true',
    bidSpreadBase: parseFloat(process.env.BID_SPREAD_BASE),
    askSpreadBase: parseFloat(process.env.ASK_SPREAD_BASE),
    maxOrdersPerSide: parseInt(process.env.MAX_ORDERS_PER_SIDE, 10),
    minOrderSize: parseFloat(process.env.MIN_ORDER_SIZE),
    orderSizeFixed: process.env.ORDER_SIZE_FIXED === 'true',
    volatilityWindow: parseInt(process.env.VOLATILITY_WINDOW, 10),
    volatilityFactor: parseFloat(process.env.VOLATILITY_FACTOR),
    refreshInterval: parseInt(process.env.REFRESH_INTERVAL, 10),
    heartbeatInterval: parseInt(process.env.HEARTBEAT_INTERVAL, 10),
    retryDelayBase: parseInt(process.env.RETRY_DELAY_BASE, 10),
    maxNetPosition: parseFloat(process.env.MAX_NET_POSITION),
    stopOnLargePos: process.env.STOP_ON_LARGE_POS === 'true',
    inventorySizeFactor: parseFloat(process.env.INVENTORY_SIZE_FACTOR),
    logToFile: process.env.LOG_TO_FILE === 'true',
    logLevel: process.env.LOG_LEVEL,
    pnlCsvPath: process.env.PNL_CSV_PATH,
    useTermuxSms: process.env.USE_TERMUX_SMS === 'true',
    smsPhoneNumber: process.env.SMS_PHONE_NUMBER,
    positionSkewFactor: parseFloat(process.env.POSITION_SKEW_FACTOR),
    volatilitySpreadFactor: parseFloat(process.env.VOLATILITY_SPREAD_FACTOR),
    stateFilePath: process.env.STATE_FILE_PATH,
    fillProbability: parseFloat(process.env.FILL_PROBABILITY),
    slippageFactor: parseFloat(process.env.SLIPPAGE_FACTOR),
    gridSpacingBase: parseFloat(process.env.GRID_SPACING_BASE),
    imbalanceSpreadFactor: parseFloat(process.env.IMBALANCE_SPREAD_FACTOR),
    imbalanceOrderSizeFactor: parseFloat(process.env.IMBALANCE_ORDER_SIZE_FACTOR),
    priceDisplayPrecision: parseInt(process.env.PRICE_DISPLAY_PRECISION, 10),
    qtyDisplayPrecision: parseInt(process.env.QTY_DISPLAY_PRECISION, 10),
    riskClearedThresholdFactor: parseFloat(process.env.RISK_CLEARED_THRESHOLD_FACTOR),
    maxPriceHistoryLength: parseInt(process.env.MAX_PRICE_HISTORY_LENGTH, 10),
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