import winston from 'winston';
import chalk from 'chalk';

// Configure logger
export const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    winston.format.errors({ stack: true }),
    winston.format.splat(),
    winston.format.json()
  ),
  defaultMeta: { service: 'trading-bot' },
  transports: [
    new winston.transports.File({ 
      filename: 'logs/error.log', 
      level: 'error' 
    }),
    new winston.transports.File({ 
      filename: 'logs/combined.log' 
    }),
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Utility functions
export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const formatNumber = (num, decimals = 2) => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(num);
};

export const calculatePercentageChange = (oldValue, newValue) => {
  return ((newValue - oldValue) / oldValue) * 100;
};

export const isMarketOpen = () => {
  // Add your market hours logic here
  // For crypto, markets are always open
  return true;
};

export const validateSignal = (signal) => {
  const required = ['symbol', 'currentPrice', 'action', 'confidence'];
  
  for (const field of required) {
    if (!signal[field]) {
      logger.error(chalk.red(`Invalid signal: missing ${field}`));
      return false;
    }
  }
  
  if (signal.action !== 'HOLD') {
    const tradeFields = ['entry', 'stopLoss', 'takeProfit'];
    for (const field of tradeFields) {
      if (!signal[field]) {
        logger.error(chalk.red(`Invalid trade signal: missing ${field}`));
        return false;
      }
    }
  }
  
  return true;
};