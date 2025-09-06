import fs from 'fs-extra';
import chalk from 'chalk';
import { logger, stripAnsi } from './utils.js';

export default class LogParser {
  constructor(tradingSymbol, options = {}) {
    this.tradingSymbol = tradingSymbol;
    
    // Enhanced configuration with defaults
    this.options = {
      cacheEnabled: options.cacheEnabled !== false,
      cacheTTL: options.cacheTTL || 300000, // 5 minutes
      maxDataPoints: options.maxDataPoints || 1000,
      validateNumbers: options.validateNumbers !== false,
      parseErrorTolerance: options.parseErrorTolerance || 0.1, // 10% error tolerance
      debugMode: options.debugMode || false,
      ...options
    };

    // Comprehensive indicator patterns based on actual log structure
    this.indicatorPatterns = {
      currentPrice: /Current Price:\s*([\d.]+)/,
      sma_10: /SMA_10:\s*([\d.]+)/,
      sma_long: /SMA_Long:\s*([\d.]+)/,
      ema_short: /EMA_Short:\s*([\d.]+)/,
      ema_long: /EMA_Long:\s*([\d.]+)/,
      rsi: /RSI:\s*([\d.]+)/,
      macd_line: /MACD_Line:\s*([-\d.eE]+)/,
      macd_signal: /MACD_Signal:\s*([-\d.eE]+)/,
      macd_hist: /MACD_Hist:\s*([-\d.eE]+)/,
      bb_upper: /BB_Upper:\s*([\d.]+)/,
      bb_middle: /BB_Middle:\s*([\d.]+)/,
      bb_lower: /BB_Lower:\s*([\d.]+)/,
      atr: /ATR:\s*([\d.]+)/,
      adx: /ADX:\s*([\d.]+)/,
      plusDI: /PlusDI:\s*([\d.]+)/,
      minusDI: /MinusDI:\s*([\d.]+)/,
      stochRsi_k: /StochRSI_K:\s*([\d.]+)/,
      stochRsi_d: /StochRSI_D:\s*([\d.]+)/,
      vwap: /VWAP:\s*([\d.]+|nan)/,
      obv: /OBV:\s*([-\d.]+)/,
      obv_ema: /OBV_EMA:\s*([-\d.]+)/,
      mfi: /MFI:\s*([\d.]+)/,
      cci: /CCI:\s*([-\d.]+)/,
      wr: /WR:\s*([-\d.]+)/,
      cmf: /CMF:\s*([-\d.]+)/,
      // Ichimoku Cloud indicators
      tenkan_sen: /Tenkan_Sen:\s*([\d.]+)/,
      kijun_sen: /Kijun_Sen:\s*([\d.]+)/,
      senkou_span_a: /Senkou_Span_A:\s*([\d.]+)/,
      senkou_span_b: /Senkou_Span_B:\s*([\d.]+)/,
      chikou_span: /Chikou_Span:\s*([\d.]+)/,
      // Parabolic SAR
      psar_val: /PSAR_Val:\s*([\d.]+)/,
      psar_dir: /PSAR_Dir:\s*([-\d]+)/,
      // SuperTrend indicators
      st_fast_dir: /ST_Fast_Dir:\s*([-\d]+)/,
      st_fast_val: /ST_Fast_Val:\s*([\d.]+)/,
      st_slow_dir: /ST_Slow_Dir:\s*([-\d]+)/,
      st_slow_val: /ST_Slow_Val:\s*([\d.]+)/,
      // Additional indicators
      volatilityIndex: /Volatility_Index:\s*([\d.]+)/,
      vwma: /VWMA:\s*([\d.]+|nan)/,
      volumeDelta: /Volume_Delta:\s*([-\d.]+)/,
      kaufmanAMA: /Kaufman_AMA:\s*([\d.]+)/,
      // Pivot points
      pivot: /Pivot:\s*([\d.]+)/,
      r1: /R1:\s*([\d.]+)/,
      r2: /R2:\s*([\d.]+)/,
      s1: /S1:\s*([\d.]+)/,
      s2: /S2:\s*([\d.]+)/,
      // Trading signals
      symbol: new RegExp(`(?:Symbol:|\[|for\s+)(${this.tradingSymbol})(?:\]|\s+@|\s+from)?`),
      signal: /Final Signal:\s*(\w+)/,
      score: /Score:\s*([-\d.]+)/,
      rawScore: /Raw Signal Score:\s*([-\d.]+)/
    };

    // Updated trend patterns based on actual logs
    this.trendPatterns = {
      '5_ema': /5_ema:\s*(\w+)/,
      '5_ehlers_supertrend': /5_ehlers_supertrend:\s*(\w+)/,
      '15_ema': /15_ema:\s*(\w+)/,
      '15_ehlers_supertrend': /15_ehlers_supertrend:\s*(\w+)/,
      ema_cross: /EMA Cross\s*:\s*[▲▼]?\s*(\w+)/,
      supertrend: /SuperTrend\s*:\s*[▲▼]?\s*(\w+)/,
      ichimoku: /Ichimoku\s*:\s*(\w+(?:\s+\w+)*)/,
      mtf_confluent: /MTF Confl\.\s*:\s*(.+)$/m
    };

    // Fibonacci patterns
    this.fibonacciPatterns = {
      fib_0: /0\.0%:\s*([\d.]+)/,
      fib_236: /23\.6%:\s*([\d.]+)/,
      fib_382: /38\.2%:\s*([\d.]+)/,
      fib_50: /50\.0%:\s*([\d.]+)/,
      fib_618: /61\.8%:\s*([\d.]+)/,
      fib_786: /78\.6%:\s*([\d.]+)/,
      fib_100: /100\.0%:\s*([\d.]+)/
    };

    // Performance tracking
    this.stats = {
      totalParses: 0,
      successfulParses: 0,
      failedParses: 0,
      cacheHits: 0,
      parseErrors: [],
      lastParseTime: null
    };

    // Cache storage
    this.cache = new Map();
    this.dataBuffer = [];
  }

  async parseLogFile(filePath) {
    const startTime = Date.now();
    this.stats.totalParses++;

    try {
      if (!await fs.pathExists(filePath)) {
        logger.error(chalk.red(`Log file not found: ${filePath}`));
        this.stats.failedParses++;
        return null;
      }

      // Check cache first
      const fileStats = await fs.stat(filePath);
      const cacheKey = `${filePath}_${fileStats.mtime.getTime()}`;
      const cached = this.getCached(cacheKey);
      
      if (cached) {
        this.stats.cacheHits++;
        logger.info(chalk.cyan(`Cache hit for log file: ${filePath}`));
        return cached;
      }

      const content = await fs.readFile(filePath, 'utf-8');
      const lines = content.split('\n');
      
      logger.info(chalk.blue(`Parsing ${lines.length} lines from log file`));
      
      const dataPoints = this.extractMarketData(lines);
      
      // Validate parsing results
      const validationResult = this.validateDataPoints(dataPoints);
      if (!validationResult.isValid) {
        logger.warn(chalk.yellow(`Validation warnings: ${validationResult.warnings.join(', ')}`));
      }

      // Cache the result
      this.setCache(cacheKey, dataPoints);
      
      // Update statistics
      this.stats.successfulParses++;
      this.stats.lastParseTime = Date.now() - startTime;
      
      logger.info(chalk.green(`Parsing completed in ${this.stats.lastParseTime}ms`));
      
      return dataPoints;
      
    } catch (error) {
      this.stats.failedParses++;
      this.stats.parseErrors.push({
        file: filePath,
        error: error.message,
        timestamp: new Date().toISOString()
      });
      logger.error(chalk.red(`Error parsing log file: ${error.message}`));
      return null;
    }
  }

  extractMarketData(lines) {
    const dataPoints = [];
    let currentDataPoint = {};
    let isCapturingIndicators = false;
    let fibonacciSection = false;
    let parseErrors = 0;

    for (let i = 0; i < lines.length; i++) {
      const line = stripAnsi(lines[i]);
      
      try {
        // Check for new data block
        if (line.includes('Current Market Data & Indicators') || 
            line.includes('--- Indicator Values ---')) {
          if (Object.keys(currentDataPoint).length > 0 && 
              currentDataPoint.symbol === this.tradingSymbol) {
            dataPoints.push(this.enrichDataPoint(currentDataPoint));
          }
          currentDataPoint = { 
            timestamp: this.extractTimestamp(line),
            lineNumber: i
          };
          isCapturingIndicators = true;
        }

        // Check for Fibonacci section
        if (line.includes('Fibonacci Levels')) {
          fibonacciSection = true;
        } else if (line.includes('Multi-Timeframe Trends') || 
                   line.includes('Current Trend Summary')) {
          fibonacciSection = false;
        }

        currentDataPoint.symbol = this.tradingSymbol;

        // Skip if wrong symbol (this check is now redundant as symbol is explicitly set)
        // if (currentDataPoint.symbol && 
        //     currentDataPoint.symbol !== this.tradingSymbol) {
        //   continue;
        // }

        // Extract indicators
        if (isCapturingIndicators) {
          // Process indicator patterns
          for (const [key, pattern] of Object.entries(this.indicatorPatterns)) {
            if (key === 'symbol') continue;
            const match = line.match(pattern);
            if (match) {
              const value = this.parseValue(match[1], key);
              if (value !== undefined) {
                currentDataPoint[key] = value;
                if (this.options.debugMode && key === 'currentPrice') {
                  logger.debug(chalk.magenta(`[DEBUG] Line: ${line}`));
                  logger.debug(chalk.magenta(`[DEBUG] Extracted currentPrice: ${value}`));
                  logger.debug(chalk.magenta(`[DEBUG] currentDataPoint after currentPrice: ${JSON.stringify(currentDataPoint)}`));
                }
              }
            }
          }

          // Extract trends
          for (const [key, pattern] of Object.entries(this.trendPatterns)) {
            const match = line.match(pattern);
            if (match) {
              currentDataPoint[key] = match[1].trim();
            }
          }

          // Extract Fibonacci levels if in section
          if (fibonacciSection) {
            for (const [key, pattern] of Object.entries(this.fibonacciPatterns)) {
              const match = line.match(pattern);
              if (match) {
                const value = this.parseValue(match[1], key);
                if (value !== undefined) {
                  currentDataPoint[key] = value;
                }
              }
            }
          }
        }

        // Check for end of indicators section
        if (line.includes('Analysis Loop Finished') || 
            line.includes('New Analysis Loop Started')) {
          isCapturingIndicators = false;
        }
        
      } catch (error) {
        parseErrors++;
        if (this.options.debugMode) {
          logger.debug(chalk.gray(`Parse error at line ${i}: ${error.message}`));
        }
      }
    }

    // Add last data point if valid
    if (Object.keys(currentDataPoint).length > 0 && 
        currentDataPoint.symbol === this.tradingSymbol) {
      dataPoints.push(this.enrichDataPoint(currentDataPoint));
    }

    // Check error tolerance
    const errorRate = parseErrors / lines.length;
    if (errorRate > this.options.parseErrorTolerance) {
      logger.warn(chalk.yellow(`High parse error rate: ${(errorRate * 100).toFixed(2)}%`));
    }

    // Limit to maxDataPoints
    const limitedDataPoints = dataPoints.slice(-this.options.maxDataPoints);
    
    logger.info(chalk.green(
      `Extracted ${limitedDataPoints.length} data points for ${this.tradingSymbol}`
    ));
    
    return limitedDataPoints;
  }

  parseValue(value, key) {
    // Handle special values
    if (value === 'nan' || value === 'null' || value === 'undefined') {
      return undefined;
    }

    // Parse as number
    const parsedValue = parseFloat(value);
    
    if (this.options.validateNumbers && isNaN(parsedValue)) {
      if (this.options.debugMode) {
        logger.debug(chalk.gray(`Invalid number for ${key}: ${value}`));
      }
      return undefined;
    }

    return isNaN(parsedValue) ? value : parsedValue;
  }

  enrichDataPoint(dataPoint) {
    // Calculate derived metrics
    if (dataPoint.bb_upper && dataPoint.bb_lower) {
      dataPoint.bb_width = dataPoint.bb_upper - dataPoint.bb_lower;
      dataPoint.bb_percent = dataPoint.currentPrice 
        ? (dataPoint.currentPrice - dataPoint.bb_lower) / dataPoint.bb_width 
        : undefined;
    }

    // Calculate trend alignment score
    let trendScore = 0;
    let factors = 0;

    // ADX strength
    if (dataPoint.adx !== undefined) {
      factors++;
      if (dataPoint.adx > 40) trendScore += 3;
      else if (dataPoint.adx > 25) trendScore += 2;
      else if (dataPoint.adx > 20) trendScore += 1;
    }

    // MACD alignment
    if (dataPoint.macd_hist !== undefined) {
      factors++;
      if (Math.abs(dataPoint.macd_hist) > 0.001) trendScore += 2;
      else if (Math.abs(dataPoint.macd_hist) > 0.0001) trendScore += 1;
    }

    // RSI momentum
    if (dataPoint.rsi !== undefined) {
      factors++;
      if (dataPoint.rsi > 60 && dataPoint.rsi < 70) trendScore += 2;
      else if (dataPoint.rsi > 50 && dataPoint.rsi < 80) trendScore += 1;
    }

    const score = factors > 0 ? trendScore / (factors * 3) : 0;
    
    if (score > 0.66) return 'STRONG';
    if (score > 0.33) return 'MODERATE';
    return 'WEAK';
  }

  extractTimestamp(line) {
    // Try multiple timestamp formats
    const patterns = [
      /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})/,
      /(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/,
      /@ (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/
    ];

    for (const pattern of patterns) {
      const match = line.match(pattern);
      if (match) {
        return match;
      }
    }

    return new Date().toISOString();
  }

  validateDataPoints(dataPoints) {
    const warnings = [];
    let isValid = true;

    if (!dataPoints || dataPoints.length === 0) {
      warnings.push('No data points extracted');
      isValid = false;
    }

    // Check for required indicators
    const requiredIndicators = ['currentPrice', 'rsi', 'macd_line'];
    for (const point of dataPoints) {
      for (const indicator of requiredIndicators) {
        if (point[indicator] === undefined) {
          warnings.push(`Missing ${indicator} in some data points`);
        }
      }
    }

    // Check for data consistency
    const priceRange = this.calculatePriceRange(dataPoints);
    if (priceRange && priceRange.volatility > 0.5) {
      warnings.push(`High price volatility detected: ${(priceRange.volatility * 100).toFixed(2)}%`);
    }

    return { isValid, warnings };
  }

  calculatePriceRange(dataPoints) {
    const prices = dataPoints
      .map(dp => dp.currentPrice)
      .filter(price => price !== undefined);

    if (prices.length === 0) return null;

    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
    const volatility = (max - min) / avg;

    return { min, max, avg, volatility };
  }

  getLatestMarketData(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};
    
    const latest = dataPoints[dataPoints.length - 1];
    const previous = dataPoints.length > 1 ? dataPoints[dataPoints.length - 2] : latest;
    
    // Calculate additional metrics
    const priceChange = latest.currentPrice && previous.currentPrice 
      ? latest.currentPrice - previous.currentPrice 
      : 0;
    const priceChangePercent = previous.currentPrice 
      ? (priceChange / previous.currentPrice) * 100 
      : 0;

    // Trend strength based on multiple indicators
    const trendStrength = this.calculateTrendStrength(latest);
    
    // Market condition
    const marketCondition = this.determineMarketCondition(latest);

    // Moving average analysis
    const maAnalysis = this.analyzeMAs(latest);

    // Support/Resistance proximity
    const srProximity = this.calculateSRProximity(latest);

    return {
      ...latest,
      priceChange,
      priceChangePercent,
      trendStrength,
      marketCondition,
      maAnalysis,
      srProximity,
      historicalData: dataPoints.slice(-10) // Last 10 data points for trend analysis
    };
  }

  calculateTrendStrength(dataPoint) {
    let strength = 0;
    let factors = 0;

    // ADX strength
    if (dataPoint.adx !== undefined) {
      factors++;
      if (dataPoint.adx > 40) strength += 3;
      else if (dataPoint.adx > 25) strength += 2;
      else if (dataPoint.adx > 20) strength += 1;
    }

    // MACD alignment
    if (dataPoint.macd_hist !== undefined) {
      factors++;
      if (Math.abs(dataPoint.macd_hist) > 0.001) strength += 2;
      else if (Math.abs(dataPoint.macd_hist) > 0.0001) strength += 1;
    }

    // RSI momentum
    if (dataPoint.rsi !== undefined) {
      factors++;
      if (dataPoint.rsi > 60 && dataPoint.rsi < 70) strength += 2;
      else if (dataPoint.rsi > 50 && dataPoint.rsi < 80) strength += 1;
    }

    const score = factors > 0 ? strength / (factors * 3) : 0;
    
    if (score > 0.66) return 'STRONG';
    if (score > 0.33) return 'MODERATE';
    return 'WEAK';
  }

  determineMarketCondition(dataPoint) {
    const conditions = [];

    // RSI conditions
    if (dataPoint.rsi > 70) conditions.push('OVERBOUGHT');
    else if (dataPoint.rsi < 30) conditions.push('OVERSOLD');
    
    // Bollinger Band position
    if (dataPoint.currentPrice && dataPoint.bb_upper && dataPoint.bb_lower) {
      if (dataPoint.currentPrice > dataPoint.bb_upper) {
        conditions.push('ABOVE_BB');
      } else if (dataPoint.currentPrice < dataPoint.bb_lower) {
        conditions.push('BELOW_BB');
      }
    }

    // Volatility
    if (dataPoint.volatilityIndex > 0.01) conditions.push('HIGH_VOLATILITY');
    
    // Trend
    if (dataPoint.st_fast_dir === 1 && dataPoint.st_slow_dir === 1) {
      conditions.push('BULLISH_TREND');
    } else if (dataPoint.st_fast_dir === -1 && dataPoint.st_slow_dir === -1) {
      conditions.push('BEARISH_TREND');
    }

    return conditions.length > 0 ? conditions.join(', ') : 'NEUTRAL';
  }

  analyzeMAs(dataPoint) {
    const analysis = {};

    // EMA relationship
    if (dataPoint.ema_short && dataPoint.ema_long) {
      analysis.emaRelation = dataPoint.ema_short > dataPoint.ema_long 
        ? 'BULLISH' 
        : 'BEARISH';
      analysis.emaDiff = dataPoint.ema_short - dataPoint.ema_long;
      analysis.emaDiffPercent = (analysis.emaDiff / dataPoint.ema_long) * 100;
    }

    // Price vs MAs
    if (dataPoint.currentPrice) {
      if (dataPoint.sma_10) {
        analysis.priceVsSMA10 = dataPoint.currentPrice > dataPoint.sma_10 
          ? 'ABOVE' 
          : 'BELOW';
      }
      if (dataPoint.vwap) {
        analysis.priceVsVWAP = dataPoint.currentPrice > dataPoint.vwap 
          ? 'ABOVE' 
          : 'BELOW';
      }
    }

    return analysis;
  }

  calculateSRProximity(dataPoint) {
    if (!dataPoint.currentPrice) return null;

    const levels = [];
    
    // Add pivot levels
    if (dataPoint.r2) levels.push({ type: 'R2', value: dataPoint.r2 });
    if (dataPoint.r1) levels.push({ type: 'R1', value: dataPoint.r1 });
    if (dataPoint.pivot) levels.push({ type: 'PIVOT', value: dataPoint.pivot });
    if (dataPoint.s1) levels.push({ type: 'S1', value: dataPoint.s1 });
    if (dataPoint.s2) levels.push({ type: 'S2', value: dataPoint.s2 });

    // Find nearest level
    let nearest = null;
    let minDistance = Infinity;

    for (const level of levels) {
      const distance = Math.abs(dataPoint.currentPrice - level.value);
      if (distance < minDistance) {
        minDistance = distance;
        nearest = level;
      }
    }

    if (nearest) {
      return {
        nearestLevel: nearest.type,
        distance: minDistance,
        distancePercent: (minDistance / dataPoint.currentPrice) * 100
      };
    }

    return null;
  }

  // Cache management methods
  getCached(key) {
    if (!this.options.cacheEnabled) return null;
    
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp < this.options.cacheTTL) {
      return cached.data;
    }
    
    // Clean expired entry
    if (cached) {
      this.cache.delete(key);
    }
    
    return null;
  }

  setCache(key, data) {
    if (!this.options.cacheEnabled) return;
    
    this.cache.set(key, {
      data,
      timestamp: Date.now()
    });

    // Limit cache size
    if (this.cache.size > 10) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
  }

  clearCache() {
    this.cache.clear();
    logger.info(chalk.green('Parser cache cleared'));
  }

  // Export and analysis methods
  async exportToJson(dataPoints, outputPath) {
    try {
      const exportData = {
        symbol: this.tradingSymbol,
        exportedAt: new Date().toISOString(),
        dataPoints: dataPoints,
        statistics: this.calculateStatistics(dataPoints),
        metadata: {
          totalPoints: dataPoints.length,
          timeRange: this.getTimeRange(dataPoints),
          parseStats: this.stats
        }
      };

      await fs.ensureDir(require('path').dirname(outputPath));
      await fs.writeJson(outputPath, exportData, { spaces: 2 });
      
      logger.info(chalk.green(`Exported ${dataPoints.length} data points to ${outputPath}`));
      return true;
    } catch (error) {
      logger.error(chalk.red(`Error exporting to JSON: ${error.message}`));
      return false;
    }
  }

  async exportToCSV(dataPoints, outputPath) {
    try {
      if (dataPoints.length === 0) {
        logger.warn(chalk.yellow('No data points to export'));
        return false;
      }

      // Get all unique keys
      const allKeys = new Set();
      dataPoints.forEach(point => {
        Object.keys(point).forEach(key => allKeys.add(key));
      });

      // Create CSV header
      const headers = Array.from(allKeys).sort();
      const csvLines = [headers.join(',')];

      // Add data rows
      for (const point of dataPoints) {
        const row = headers.map(key => {
          const value = point[key];
          if (value === undefined || value === null) return '';
          if (typeof value === 'string' && value.includes(',')) {
            return `"${value}"`;
          }
          return value;
        });
        csvLines.push(row.join(','));
      }

      await fs.ensureDir(require('path').dirname(outputPath));
      await fs.writeFile(outputPath, csvLines.join('\n'));
      
      logger.info(chalk.green(`Exported ${dataPoints.length} data points to CSV: ${outputPath}`));
      return true;
    } catch (error) {
      logger.error(chalk.red(`Error exporting to CSV: ${error.message}`));
      return false;
    }
  }

  calculateStatistics(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};

    const stats = {};

    // Price statistics
    const prices = dataPoints
      .map(dp => dp.currentPrice)
      .filter(p => p !== undefined);
    
    if (prices.length > 0) {
      stats.price = {
        min: Math.min(...prices),
        max: Math.max(...prices),
        avg: prices.reduce((a, b) => a + b, 0) / prices.length,
        last: prices[prices.length - 1]
      };
    }

    // RSI statistics
    const rsiValues = dataPoints
      .map(dp => dp.rsi)
      .filter(r => r !== undefined);
    
    if (rsiValues.length > 0) {
      stats.rsi = {
        min: Math.min(...rsiValues),
        max: Math.max(...rsiValues),
        avg: rsiValues.reduce((a, b) => a + b, 0) / rsiValues.length,
        last: rsiValues[rsiValues.length - 1]
      };
    }

    // Volume statistics
    const volumes = dataPoints
      .map(dp => dp.volumeDelta)
      .filter(v => v !== undefined);
    
    if (volumes.length > 0) {
      stats.volume = {
        min: Math.min(...volumes),
        max: Math.max(...volumes),
        avg: volumes.reduce((a, b) => a + b, 0) / volumes.length,
        totalPositive: volumes.filter(v => v > 0).length,
        totalNegative: volumes.filter(v => v < 0).length
      };
    }

    // Signal statistics
    const signals = dataPoints
      .map(dp => dp.signal)
      .filter(s => s !== undefined);
    
    if (signals.length > 0) {
      const signalCounts = signals.reduce((acc, signal) => {
        acc[signal] = (acc[signal] || 0) + 1;
        return acc;
      }, {});
      
      stats.signals = signalCounts;
    }

    return stats;
  }

  getTimeRange(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return null;

    const timestamps = dataPoints
      .map(dp => dp.timestamp)
      .filter(t => t !== undefined)
      .sort();

    if (timestamps.length === 0) return null;

    return {
      start: timestamps,
      end: timestamps[timestamps.length - 1],
      duration: new Date(timestamps[timestamps.length - 1]) - new Date(timestamps)
    };
  }

  // Utility method to get parse statistics
  getStatistics() {
    return {
      ...this.stats,
      cacheSize: this.cache.size,
      cacheHitRate: this.stats.totalParses > 0 
        ? (this.stats.cacheHits / this.stats.totalParses * 100).toFixed(2) + '%'
        : '0%',
      successRate: this.stats.totalParses > 0
        ? (this.stats.successfulParses / this.stats.totalParses * 100).toFixed(2) + '%'
        : '0%'
    };
  }
}