import fs from 'fs-extra';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class LogParser {
  constructor(tradingSymbol) { // Accept tradingSymbol
    this.tradingSymbol = tradingSymbol; // Store tradingSymbol
    this.indicatorPatterns = {
      currentPrice: /Current Price:\s*([\d.]+)/,
      ema_short: /EMA_Short:\s*([\d.]+)/,
      ema_long: /EMA_Long:\s*([\d.]+)/,
      rsi: /RSI:\s*([\d.]+)/,
      macd_line: /MACD_Line:\s*([-\d.]+)/,
      macd_signal: /MACD_Signal:\s*([-\d.]+)/,
      macd_hist: /MACD_Hist:\s*([-\d.]+)/,
      bb_upper: /BB_Upper:\s*([\d.]+)/,
      bb_middle: /BB_Middle:\s*([\d.]+)/,
      bb_lower: /BB_Lower:\s*([\d.]+)/,
      atr: /ATR:\s*([\d.]+)/,
      adx: /ADX:\s*([\d.]+)/,
      stochRsi_k: /StochRSI_K:\s*([\d.]+)/,
      stochRsi_d: /StochRSI_D:\s*([\d.]+)/,
      vwap: /VWAP:\s*([\d.]+)/,
      obv: /OBV:\s*([-\d.]+)/,
      mfi: /MFI:\s*([\d.]+)/,
      cci: /CCI:\s*([-\d.]+)/,
      symbol: /(?:Symbol:|\\\[)([A-Z]+USDT)(?:\\\\])?/, // Use tradingSymbol for regex
      signal: /Final Signal:\s*(\w+)/,
      score: /Score:\s*([-\d.]+)/
    };

    this.trendPatterns = {
      '3_ema': /3_ema:\s*(\w+)/,
      '15_ema': /15_ema:\s*(\w+)/,
      '3_supertrend': /3_ehlers_supertrend:\s*(\w+)/,
      '15_supertrend': /15_ehlers_supertrend:\s*(\w+)/
    };
  }

  async parseLogFile(filePath) {
    try {
      if (!await fs.pathExists(filePath)) {
        logger.error(chalk.red(`Log file not found: ${filePath}`));
        return null;
      }

      const content = await fs.readFile(filePath, 'utf-8');
      const lines = content.split('\n');
      
      logger.info(chalk.blue(`Parsing ${lines.length} lines from log file`));
      
      return this.extractMarketData(lines);
      
    } catch (error) {
      logger.error(chalk.red('Error parsing log file:', error));
      return null;
    }
  }

  extractMarketData(lines) {
    const dataPoints = [];
    let currentDataPoint = {};
    let isCapturingIndicators = false;

    for (const line of lines) {
      // Check for new data block
      if (line.includes('Current Market Data & Indicators')) {
        if (Object.keys(currentDataPoint).length > 0) {
          dataPoints.push(currentDataPoint);
        }
        currentDataPoint = { timestamp: this.extractTimestamp(line) };
        isCapturingIndicators = true;
      }

      // Extract symbol (always try to extract symbol)
      const symbolMatch = line.match(this.indicatorPatterns.symbol);
      if (symbolMatch) {
        currentDataPoint.symbol = symbolMatch[1];
      }

      // Extract indicators
      if (isCapturingIndicators) {
        for (const [key, pattern] of Object.entries(this.indicatorPatterns)) {
          // Skip symbol as it's handled separately
          if (key === 'symbol') continue; 
          const match = line.match(pattern);
          if (match) {
            const parsedValue = parseFloat(match[1]);
            currentDataPoint[key] = isNaN(parsedValue) ? undefined : parsedValue;
          }
        }

        // Extract trends
        for (const [key, pattern] of Object.entries(this.trendPatterns)) {
          const match = line.match(pattern);
          if (match) {
            currentDataPoint[key] = match[1];
          }
        }
      }

      // Check for end of indicators section
      if (line.includes('Multi-Timeframe Trends')) {
        isCapturingIndicators = true;
      }
      
      if (line.includes('Analysis Loop Finished')) {
        isCapturingIndicators = false;
      }
    }

    // Add last data point
    if (Object.keys(currentDataPoint).length > 0) {
      dataPoints.push(currentDataPoint);
    }

    logger.info(chalk.green(`Extracted ${dataPoints.length} data points`));
    return dataPoints;
  }

  extractTimestamp(line) {
    const match = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
    return match ? match[1] : new Date().toISOString();
  }

  getLatestMarketData(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};
    
    const latest = dataPoints[dataPoints.length - 1];
    const previous = dataPoints.length > 1 ? dataPoints[dataPoints.length - 2] : latest;
    
    // Calculate additional metrics
    const priceChange = latest.currentPrice - previous.currentPrice;
    const priceChangePercent = (priceChange / previous.currentPrice) * 100;
    
    return {
      ...latest,
      priceChange,
      priceChangePercent,
      dataPoints: dataPoints.slice(-10) // Last 10 data points for trend analysis
    };
  }
}
