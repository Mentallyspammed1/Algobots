import winston from 'winston';
import chalk from 'chalk';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import DailyRotateFile from 'winston-daily-rotate-file';

// Get current directory for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Ensure logs directory exists
fs.ensureDirSync(path.join(__dirname, '../logs'));

// Custom log levels with colors
const customLevels = {
  levels: {
    critical: 0,
    error: 1,
    warn: 2,
    info: 3,
    debug: 4,
    trace: 5,
    profit: 3,
    loss: 3,
    signal: 3
  },
  colors: {
    critical: 'magenta',
    error: 'red',
    warn: 'yellow',
    info: 'cyan',
    debug: 'blue',
    trace: 'gray',
    profit: 'green',
    loss: 'red',
    signal: 'cyan'
  }
};

// Add colors to Winston
winston.addColors(customLevels.colors);

// Custom format for console output
const consoleFormat = winston.format.printf(({ level, message, timestamp, ...metadata }) => {
  let msg = `${timestamp} [${level}]: ${message}`;
  if (Object.keys(metadata).length > 0 && metadata.service !== 'trading-bot') {
    msg += ` ${JSON.stringify(metadata)}`;
  }
  return msg;
});

// Create performance monitoring transport
class PerformanceTransport extends winston.transports.File {
  constructor(opts) {
    super(opts);
    this.performanceMetrics = [];
  }

  log(info, callback) {
    if (info.performance) {
      this.performanceMetrics.push(info.performance);
      // Keep only last 1000 metrics
      if (this.performanceMetrics.length > 1000) {
        this.performanceMetrics.shift();
      }
    }
    super.log(info, callback);
  }

  getMetrics() {
    return this.performanceMetrics;
  }
}

// Configure enhanced logger

// Strips ANSI escape codes from a string
export const stripAnsi = (str) => {
  if (typeof str !== 'string' || str.length === 0) {
    return '';
  }
  return str.replace(/[\u001b\u009b][[()#;?]*.?[0-9;]*[0-9A-ORZcf-nqry=><]/g, '');
};

export const logger = winston.createLogger({
  levels: customLevels.levels,
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss.SSS'
    }),
    winston.format.errors({ stack: true }),
    winston.format.splat(),
    winston.format.json(),
    winston.format.metadata({ fillExcept: ['message', 'level', 'timestamp', 'label'] })
  ),
  defaultMeta: { service: 'trading-bot' },
  transports: [
    // Rotating file for errors
    new DailyRotateFile({
      filename: 'logs/error-%DATE%.log',
      datePattern: 'YYYY-MM-DD',
      level: 'error',
      maxSize: '20m',
      maxFiles: '14d',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
      )
    }),
    // Rotating file for all logs
    new DailyRotateFile({
      filename: 'logs/combined-%DATE%.log',
      datePattern: 'YYYY-MM-DD',
      maxSize: '50m',
      maxFiles: '30d',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
      )
    }),
    // Separate file for trading signals
    new winston.transports.File({
      filename: 'logs/signals.log',
      level: 'info',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json(),
        winston.format.printf(info => {
          if (info.level === 'signal' || info.signal) {
            return JSON.stringify(info);
          }
          return '';
        })
      )
    }),
    // Separate file for profits/losses
    new winston.transports.File({
      filename: 'logs/pnl.log',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json(),
        winston.format.printf(info => {
          if (info.level === 'profit' || info.level === 'loss' || info.pnl) {
            return JSON.stringify(info);
          }
          return '';
        })
      )
    }),
    // Performance metrics transport
    new PerformanceTransport({
      filename: 'logs/performance.log',
      format: winston.format.combine(
        winston.format.timestamp(),
        winston.format.json()
      )
    }),
    // Enhanced console transport
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize({ all: true }),
        winston.format.timestamp({
          format: 'YYYY-MM-DD HH:mm:ss'
        }),
        consoleFormat
      ),
      handleExceptions: true,
      handleRejections: true
    })
  ],
  exitOnError: false
});

// Add custom logging methods for backward compatibility and enhancement
logger.profit = function(message, meta) {
  this.log('profit', message, meta);
};

logger.loss = function(message, meta) {
  this.log('loss', message, meta);
};

logger.signal = function(message, meta) {
  this.log('signal', message, meta);
};

logger.critical = function(message, meta) {
  this.log('critical', message, meta);
};

logger.trace = function(message, meta) {
  this.log('trace', message, meta);
};

// Performance tracking wrapper
export const trackPerformance = async (operation, func) => {
  const startTime = Date.now();
  const startMemory = process.memoryUsage().heapUsed;
  
  try {
    const result = await func();
    const endTime = Date.now();
    const endMemory = process.memoryUsage().heapUsed;
    
    logger.log('info', `Performance: ${operation}`, {
      performance: {
        operation,
        duration: endTime - startTime,
        memoryDelta: endMemory - startMemory,
        timestamp: new Date().toISOString(),
        success: true
      }
    });
    
    return result;
  } catch (error) {
    const endTime = Date.now();
    
    logger.log('error', `Performance Error: ${operation}`, {
      performance: {
        operation,
        duration: endTime - startTime,
        timestamp: new Date().toISOString(),
        success: false,
        error: error.message
      }
    });
    
    throw error;
  }
};

// Enhanced utility functions
export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const formatNumber = (num, decimals = 2) => {
  if (typeof num !== 'number' || isNaN(num)) return 'N/A';
  
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(num);
};

export const formatCurrency = (amount, currency = 'USD') => {
  if (typeof amount !== 'number' || isNaN(amount)) return 'N/A';
  
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(amount);
};

export const formatPercentage = (value, decimals = 2) => {
  if (typeof value !== 'number' || isNaN(value)) return 'N/A';
  
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
};

export const formatLargeNumber = (num) => {
  if (typeof num !== 'number' || isNaN(num)) return 'N/A';
  
  const abs = Math.abs(num);
  const sign = num < 0 ? '-' : '';
  
  if (abs >= 1e9) return `${sign}${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}${(abs / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(2)}K`;
  
  return `${sign}${abs.toFixed(2)}`;
};

export const calculatePercentageChange = (oldValue, newValue) => {
  if (oldValue === 0) return newValue === 0 ? 0 : 100;
  return ((newValue - oldValue) / Math.abs(oldValue)) * 100;
};

// Time utilities
export const isMarketOpen = (market = 'crypto') => {
  const now = new Date();
  const dayOfWeek = now.getUTCDay();
  const hour = now.getUTCHours();
  const minute = now.getUTCMinutes();
  const currentTime = hour * 60 + minute;
  
  switch (market.toLowerCase()) {
    case 'crypto':
      return true; // 24/7
      
    case 'forex':
      // Forex market: Sunday 5 PM EST to Friday 5 PM EST
      if (dayOfWeek === 0 && currentTime < 22 * 60) return false; // Sunday before 10 PM UTC
      if (dayOfWeek === 5 && currentTime > 22 * 60) return false; // Friday after 10 PM UTC
      if (dayOfWeek === 6) return false; // Saturday
      return true;
      
    case 'stock':
    case 'nyse':
      // NYSE: 9:30 AM - 4:00 PM EST (14:30 - 21:00 UTC)
      if (dayOfWeek === 0 || dayOfWeek === 6) return false; // Weekend
      if (currentTime < 14 * 60 + 30 || currentTime > 21 * 60) return false;
      return true;
      
    default:
      return true;
  }
};

export const getMarketSession = () => {
  const now = new Date();
  const hour = now.getUTCHours();
  
  if (hour >= 0 && hour < 8) return 'ASIAN';
  if (hour >= 8 && hour < 16) return 'EUROPEAN';
  if (hour >= 16 && hour < 24) return 'AMERICAN';
  
  return 'UNKNOWN';
};

export const formatTimestamp = (date = new Date(), includeMs = false) => {
  const format = includeMs 
    ? 'YYYY-MM-DD HH:mm:ss.SSS'
    : 'YYYY-MM-DD HH:mm:ss';
  
  return date.toISOString().replace('T', ' ').slice(0, includeMs ? 23 : 19);
};

export const getTimeDiff = (startTime, endTime = Date.now()) => {
  const diff = endTime - startTime;
  
  if (diff < 1000) return `${diff}ms`;
  if (diff < 60000) return `${(diff / 1000).toFixed(1)}s`;
  if (diff < 3600000) return `${(diff / 60000).toFixed(1)}m`;
  
  return `${(diff / 3600000).toFixed(1)}h`;
};

// Enhanced validation with detailed error reporting
export const validateSignal = (signal, strict = false) => {
  const errors = [];
  const warnings = [];
  
  // Required fields
  const required = ['symbol', 'currentPrice', 'action', 'confidence'];
  
  for (const field of required) {
    if (!signal[field] && signal[field] !== 0) {
      errors.push(`Missing required field: ${field}`);
    }
  }
  
  // Validate field types and ranges
  if (signal.currentPrice !== undefined) {
    if (typeof signal.currentPrice !== 'number' || signal.currentPrice <= 0) {
      errors.push(`Invalid currentPrice: ${signal.currentPrice}`);
    }
  }
  
  if (signal.confidence !== undefined) {
    if (typeof signal.confidence !== 'number' || signal.confidence < 0 || signal.confidence > 100) {
      errors.push(`Invalid confidence: ${signal.confidence} (must be 0-100)`);
    }
  }
  
  if (signal.action !== undefined) {
    const validActions = ['BUY', 'SELL', 'HOLD'];
    if (!validActions.includes(signal.action)) {
      errors.push(`Invalid action: ${signal.action} (must be ${validActions.join(', ')})`);
    }
  }
  
  // Validate trade-specific fields
  if (signal.action && signal.action !== 'HOLD') {
    const tradeFields = ['entry', 'stopLoss', 'takeProfit'];
    
    for (const field of tradeFields) {
      if (!signal[field] && signal[field] !== 0) {
        errors.push(`Missing trade field: ${field}`);
      } else if (typeof signal[field] !== 'number' || signal[field] <= 0) {
        errors.push(`Invalid ${field}: ${signal[field]}`);
      }
    }
    
    // Logical validation
    if (signal.entry && signal.stopLoss && signal.takeProfit) {
      if (signal.action === 'BUY') {
        if (signal.stopLoss >= signal.entry) {
          warnings.push(`BUY signal: stopLoss (${signal.stopLoss}) should be below entry (${signal.entry})`);
        }
        if (signal.takeProfit <= signal.entry) {
          warnings.push(`BUY signal: takeProfit (${signal.takeProfit}) should be above entry (${signal.entry})`);
        }
      } else if (signal.action === 'SELL') {
        if (signal.stopLoss <= signal.entry) {
          warnings.push(`SELL signal: stopLoss (${signal.stopLoss}) should be above entry (${signal.entry})`);
        }
        if (signal.takeProfit >= signal.entry) {
          warnings.push(`SELL signal: takeProfit (${signal.takeProfit}) should be below entry (${signal.entry})`);
        }
      }
    }
  }
  
  // Strict mode additional checks
  if (strict) {
    const additionalFields = ['reasoning', 'keyFactors', 'riskLevel', 'trend'];
    for (const field of additionalFields) {
      if (!signal[field]) {
        warnings.push(`Missing optional field: ${field}`);
      }
    }
  }
  
  // Log results
  if (errors.length > 0) {
    logger.error(chalk.red('Signal validation failed:'), { errors, signal });
    return false;
  }
  
  if (warnings.length > 0) {
    logger.warn(chalk.yellow('Signal validation warnings:'), { warnings, signal });
  }
  
  return true;
};

// Risk calculation utilities
export const calculatePositionSize = (capital, riskPercentage, entryPrice, stopLossPrice) => {
  const riskAmount = capital * (riskPercentage / 100);
  const priceRisk = Math.abs(entryPrice - stopLossPrice);
  
  if (priceRisk === 0) return 0;
  
  return riskAmount / priceRisk;
};

export const calculateRiskRewardRatio = (entryPrice, stopLossPrice, takeProfitPrice) => {
  const risk = Math.abs(entryPrice - stopLossPrice);
  const reward = Math.abs(takeProfitPrice - entryPrice);
  
  if (risk === 0) return 0;
  
  return reward / risk;
};

export const calculatePnL = (entryPrice, exitPrice, quantity, isBuy = true) => {
  const priceDiff = isBuy ? exitPrice - entryPrice : entryPrice - exitPrice;
  return priceDiff * quantity;
};

export const calculatePnLPercentage = (entryPrice, exitPrice, isBuy = true) => {
  const pnl = isBuy ? exitPrice - entryPrice : entryPrice - exitPrice;
  return (pnl / entryPrice) * 100;
};

// Network retry utility
export const retryWithBackoff = async (fn, options = {}) => {
  const { 
    maxRetries = 3,
    initialDelay = 1000,
    maxDelay = 10000,
    backoffMultiplier = 2,
    shouldRetry = (error) => true,
    onRetry = (error, attempt) => {}
  } = options;
  
  let lastError;
  
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      
      if (!shouldRetry(error) || attempt === maxRetries) {
        throw error;
      }
      
      const delay = Math.min(
        initialDelay * Math.pow(backoffMultiplier, attempt - 1),
        maxDelay
      );
      
      onRetry(error, attempt);
      logger.warn(`Retry attempt ${attempt}/${maxRetries} after ${delay}ms`, {
        error: error.message
      });
      
      await sleep(delay);
    }
  }
  
  throw lastError;
};

// Data transformation utilities
export const normalizePrice = (price, decimals = 8) => {
  if (typeof price !== 'number' || isNaN(price)) return 0;
  return Math.round(price * Math.pow(10, decimals)) / Math.pow(10, decimals);
};

export const aggregateKlines = (klines, targetInterval) => {
  if (!Array.isArray(klines) || klines.length === 0) return [];
  
  const aggregated = [];
  let currentGroup = [];
  
  for (const kline of klines) {
    currentGroup.push(kline);
    
    if (currentGroup.length === targetInterval) {
      aggregated.push({
        timestamp: currentGroup.timestamp,
        open: currentGroup.open,
        high: Math.max(...currentGroup.map(k => k.high)),
        low: Math.min(...currentGroup.map(k => k.low)),
        close: currentGroup[currentGroup.length - 1].close,
        volume: currentGroup.reduce((sum, k) => sum + k.volume, 0)
      });
      currentGroup = [];
    }
  }
  
  return aggregated;
};

// Statistical utilities
export const calculateStats = (values) => {
  if (!Array.isArray(values) || values.length === 0) {
    return { min: 0, max: 0, mean: 0, median: 0, stdDev: 0 };
  }
  
  const sorted = [...values].sort((a, b) => a - b);
  const sum = values.reduce((a, b) => a + b, 0);
  const mean = sum / values.length;
  
  const median = values.length % 2 === 0
    ? (sorted[values.length / 2 - 1] + sorted[values.length / 2]) / 2
    : sorted[Math.floor(values.length / 2)];
  
  const variance = values.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / values.length;
  const stdDev = Math.sqrt(variance);
  
  return {
    min: Math.min(...values),
    max: Math.max(...values),
    mean,
    median,
    stdDev,
    count: values.length
  };
};

// Moving average utilities
export const simpleMovingAverage = (values, period) => {
  if (values.length < period) return null;
  
  const slice = values.slice(-period);
  return slice.reduce((a, b) => a + b, 0) / period;
};

export const exponentialMovingAverage = (values, period) => {
  if (values.length < period) return null;
  
  const multiplier = 2 / (period + 1);
  let ema = simpleMovingAverage(values.slice(0, period), period);
  
  for (let i = period; i < values.length; i++) {
    ema = (values[i] - ema) * multiplier + ema;
  }
  
  return ema;
};

// Configuration management
export const loadConfig = async (configPath = './config.json') => {
  try {
    const config = await fs.readJson(configPath);
    logger.info('Configuration loaded successfully');
    return config;
  } catch (error) {
    logger.error('Failed to load configuration:', error);
    return null;
  }
};

export const saveConfig = async (config, configPath = './config.json') => {
  try {
    await fs.writeJson(configPath, config, { spaces: 2 });
    logger.info('Configuration saved successfully');
    return true;
  } catch (error) {
    logger.error('Failed to save configuration:', error);
    return false;
  }
};

// Error handling utilities
export class TradingError extends Error {
  constructor(message, code, details = {}) {
    super(message);
    this.name = 'TradingError';
    this.code = code;
    this.details = details;
    this.timestamp = new Date().toISOString();
  }
}

export const handleError = (error, context = '') => {
  const errorInfo = {
    message: error.message,
    stack: error.stack,
    context,
    timestamp: new Date().toISOString()
  };
  
  if (error instanceof TradingError) {
    errorInfo.code = error.code;
    errorInfo.details = error.details;
  }
  
  logger.error('Error occurred:', errorInfo);
  
  // Send alert if critical
  if (error.code === 'CRITICAL' || error.message.includes('CRITICAL')) {
    logger.critical('CRITICAL ERROR - Immediate attention required', errorInfo);
  }
  
  return errorInfo;
};

// Health check utilities
export const systemHealthCheck = () => {
  const memoryUsage = process.memoryUsage();
  const uptime = process.uptime();
  
  return {
    status: 'healthy',
    uptime: formatTimeDuration(uptime * 1000),
    memory: {
      rss: formatBytes(memoryUsage.rss),
      heapTotal: formatBytes(memoryUsage.heapTotal),
      heapUsed: formatBytes(memoryUsage.heapUsed),
      external: formatBytes(memoryUsage.external)
    },
    timestamp: new Date().toISOString()
  };
};

export const formatBytes = (bytes) => {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

export const formatTimeDuration = (ms) => {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);
  
  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  
  return `${seconds}s`;
};

// Data sanitization
export const sanitizeInput = (input) => {
  if (typeof input === 'string') {
    return input.replace(/[<>]/g, '').trim();
  }
  return input;
};

export const validateApiKey = (apiKey) => {
  if (!apiKey || typeof apiKey !== 'string') return false;
  
  // Basic validation - adjust pattern based on your API key format
  const pattern = /^[A-Za-z0-9\-_]{20,}$/;
  return pattern.test(apiKey);
};

// Export all utilities as a namespace for convenience
export const utils = {
  sleep,
  formatNumber,
  formatCurrency,
  formatPercentage,
  formatLargeNumber,
  calculatePercentageChange,
  isMarketOpen,
  getMarketSession,
  formatTimestamp,
  getTimeDiff,
  validateSignal,
  calculatePositionSize,
  calculateRiskRewardRatio,
  calculatePnL,
  calculatePnLPercentage,
  retryWithBackoff,
  normalizePrice,
  aggregateKlines,
  calculateStats,
  simpleMovingAverage,
  exponentialMovingAverage,
  loadConfig,
  saveConfig,
  handleError,
  systemHealthCheck,
  formatBytes,
  formatTimeDuration,
  sanitizeInput,
  validateApiKey,
  trackPerformance
};

// Log startup message
logger.info(chalk.green('Utils module initialized'), {
  logLevel: logger.level,
  timestamp: new Date().toISOString()
});
