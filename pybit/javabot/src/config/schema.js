const Joi = require('joi');

const configSchema = Joi.object({
  // Basic config from market-maker.js
  apiKey: Joi.string().required(),
  secret: Joi.string().required(),
  symbol: Joi.string().required(),
  isTestnet: Joi.boolean().default(false),
  dryRun: Joi.boolean().default(false),
  bidSpreadBase: Joi.number().min(0).default(0.00025),
  askSpreadBase: Joi.number().min(0).default(0.00025),
  maxOrdersPerSide: Joi.number().integer().min(1).default(3),
  minOrderSize: Joi.number().min(0).default(0.002),
  orderSizeFixed: Joi.boolean().default(false),
  volatilityWindow: Joi.number().integer().min(1).default(20),
  volatilityFactor: Joi.number().min(0).default(2.0),
  refreshInterval: Joi.number().integer().min(100).default(5000),
  heartbeatInterval: Joi.number().integer().min(1000).default(30000),
  retryDelayBase: Joi.number().integer().min(100).default(1000),
  maxNetPosition: Joi.number().min(0).default(0.01),
  stopOnLargePos: Joi.boolean().default(true),
  inventorySizeFactor: Joi.number().min(0).default(1.0),
  logToFile: Joi.boolean().default(false),
  logLevel: Joi.string().valid('error', 'warn', 'info', 'debug').default('info'),
  pnlCsvPath: Joi.string().default('./logs/pnl.csv'),
  useTermuxSms: Joi.boolean().default(false),
  smsPhoneNumber: Joi.string().allow('').default(''),
  positionSkewFactor: Joi.number().min(0).default(0.15),
  volatilitySpreadFactor: Joi.number().min(0).default(0.75),
  stateFilePath: Joi.string().default('./logs/state.json'),
  fillProbability: Joi.number().min(0).max(1).default(0.15),
  slippageFactor: Joi.number().min(0).default(0.0001),
  gridSpacingBase: Joi.number().min(0).default(0.00015),
  imbalanceSpreadFactor: Joi.number().min(0).default(0.2),
  imbalanceOrderSizeFactor: Joi.number().min(0).default(0.5),
  priceDisplayPrecision: Joi.number().integer().min(0).default(4),
  qtyDisplayPrecision: Joi.number().integer().min(0).default(8),
  riskClearedThresholdFactor: Joi.number().min(0).max(1).default(0.8),
  maxPriceHistoryLength: Joi.number().integer().min(1).default(200),
  // New parameters from the feature request will be added here later
  // For now, just the basic structure
}).unknown(true); // Allow unknown keys for now, will be tightened later

module.exports = configSchema;