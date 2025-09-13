import fs from 'fs-extra';
import chalk from 'chalk';
import { logger, stripAnsi } from './utils.js';

export default class LogParser {
  constructor(tradingSymbol, options = {}) {
    this.tradingSymbol = tradingSymbol;

    this.options = {
      cacheEnabled: options.cacheEnabled !== false,
      cacheTTL: options.cacheTTL || 300000, // 5 minutes
      maxDataPoints: options.maxDataPoints || 1000,
      validateNumbers: options.validateNumbers !== false,
      parseErrorTolerance: options.parseErrorTolerance || 0.1, // 10% error tolerance
      debugMode: options.debugMode || false,
      ...options
    };

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
        tenkan_sen: /Tenkan_Sen:\s*([\d.]+)/,
        kijun_sen: /Kijun_Sen:\s*([\d.]+)/,
        senkou_span_a: /Senkou_Span_A:\s*([\d.]+)/,
        senkou_span_b: /Senkou_Span_B:\s*([\d.]+)/,
        chikou_span: /Chikou_Span:\s*([\d.]+)/,
        psar_val: /PSAR_Val:\s*([\d.]+)/,
        psar_dir: /PSAR_Dir:\s*([-\d]+)/,
        st_fast_dir: /ST_Fast_Dir:\s*([-\d]+)/,
        st_fast_val: /ST_Fast_Val:\s*([\d.]+)/,
        st_slow_dir: /ST_Slow_Dir:\s*([-\d]+)/,
        st_slow_val: /ST_Slow_Val:\s*([\d.]+)/,
        volatilityIndex: /Volatility_Index:\s*([\d.]+)/,
        vwma: /VWMA:\s*([\d.]+|nan)/,
        volumeDelta: /Volume_Delta:\s*([-\d.]+)/,
        kaufmanAMA: /Kaufman_AMA:\s*([\d.]+)/,
        pivot: /Pivot:\s*([\d.]+)/,
        r1: /R1:\s*([\d.]+)/,
        r2: /R2:\s*([\d.]+)/,
        s1: /S1:\s*([\d.]+)/,
        s2: /S2:\s*([\d.]+)/,
        symbol: new RegExp(`(?:Symbol:|\[|for\s+)(${this.tradingSymbol})(?:\]|\s+@|\s+from)?`),
        signal: /Final Signal:\s*(\w+)/,
        score: /Score:\s*([-\d.]+)/,
        rawScore: /Raw Signal Score:\s*([-\d.]+)/
    };

    this.trendPatterns = {
      '3_ema': /3_ema:\s*(\w+)/,
      '3_ehlers_supertrend': /3_ehlers_supertrend:\s*(\w+)/,
      '5_ema': /5_ema:\s*(\w+)/,
      '5_ehlers_supertrend': /5_ehlers_supertrend:\s*(\w+)/,
      '15_ema': /15_ema:\s*(\w+)/,
      '15_ehlers_supertrend': /15_ehlers_supertrend:\s*(\w+)/,
      ema_cross: /EMA Cross\s*:\s*[▲▼]?\s*(\w+)/,
      supertrend: /SuperTrend\s*:\s*[▲▼]?\s*(\w+)/,
      ichimoku: /Ichimoku\s*:\s*(\w+(?:\s+\w+)*)/,
      mtf_confluent: /MTF Confl\.\s*:\s*(.+)$/m
    };

    this.fibonacciPatterns = {
        fib_0: /0\.0%:\s*([\d.]+)/,
        fib_236: /23\.6%:\s*([\d.]+)/,
        fib_382: /38\.2%:\s*([\d.]+)/,
        fib_50: /50\.0%:\s*([\d.]+)/,
        fib_618: /61\.8%:\s*([\d.]+)/,
        fib_786: /78\.6%:\s*([\d.]+)/,
        fib_100: /100\.0%:\s*([\d.]+)/
    };

    this.stats = {
      totalParses: 0,
      successfulParses: 0,
      failedParses: 0,
      cacheHits: 0,
      parseErrors: [],
      lastParseTime: null
    };

    this.cache = new Map();
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
      
      const validationResult = this.validateDataPoints(dataPoints);
      if (!validationResult.isValid) {
        logger.warn(chalk.yellow(`Validation warnings: ${validationResult.warnings.join(', ')}`));
      }

      this.setCache(cacheKey, dataPoints);
      
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
    let parseErrors = 0;

    for (const line of lines) {
        try {
            const logEntry = JSON.parse(line);

            // A log entry with a message containing "Indicator Values" is considered a data point
            if (logEntry.message && (logEntry.message.includes('Indicator Values') || logEntry.message.includes('Current Market Data'))) {
                const dataPoint = {
                    timestamp: logEntry.timestamp,
                    symbol: this.tradingSymbol,
                    currentPrice: this.parseValue(logEntry['Current Price'] || logEntry.currentPrice),
                    sma_10: this.parseValue(logEntry.SMA_10),
                    sma_long: this.parseValue(logEntry.SMA_Long),
                    ema_short: this.parseValue(logEntry.EMA_Short),
                    ema_long: this.parseValue(logEntry.EMA_Long),
                    rsi: this.parseValue(logEntry.RSI),
                    macd_line: this.parseValue(logEntry.MACD_Line),
                    macd_signal: this.parseValue(logEntry.MACD_Signal),
                    macd_hist: this.parseValue(logEntry.MACD_Hist),
                    bb_upper: this.parseValue(logEntry.BB_Upper),
                    bb_middle: this.parseValue(logEntry.BB_Middle),
                    bb_lower: this.parseValue(logEntry.BB_Lower),
                    atr: this.parseValue(logEntry.ATR),
                    adx: this.parseValue(logEntry.ADX),
                    plusDI: this.parseValue(logEntry.PlusDI),
                    minusDI: this.parseValue(logEntry.MinusDI),
                    stochRsi_k: this.parseValue(logEntry.StochRSI_K),
                    stochRsi_d: this.parseValue(logEntry.StochRSI_D),
                    vwap: this.parseValue(logEntry.VWAP),
                    obv: this.parseValue(logEntry.OBV),
                    obv_ema: this.parseValue(logEntry.OBV_EMA),
                    mfi: this.parseValue(logEntry.MFI),
                    cci: this.parseValue(logEntry.CCI),
                    wr: this.parseValue(logEntry.WR),
                    cmf: this.parseValue(logEntry.CMF),
                    tenkan_sen: this.parseValue(logEntry.Tenkan_Sen),
                    kijun_sen: this.parseValue(logEntry.Kijun_Sen),
                    senkou_span_a: this.parseValue(logEntry.Senkou_Span_A),
                    senkou_span_b: this.parseValue(logEntry.Senkou_Span_B),
                    chikou_span: this.parseValue(logEntry.Chikou_Span),
                    psar_val: this.parseValue(logEntry.PSAR_Val),
                    psar_dir: this.parseValue(logEntry.PSAR_Dir),
                    st_fast_dir: this.parseValue(logEntry.ST_Fast_Dir),
                    st_fast_val: this.parseValue(logEntry.ST_Fast_Val),
                    st_slow_dir: this.parseValue(logEntry.ST_Slow_Dir),
                    st_slow_val: this.parseValue(logEntry.ST_Slow_Val),
                    volatilityIndex: this.parseValue(logEntry.Volatility_Index),
                    vwma: this.parseValue(logEntry.VWMA),
                    volumeDelta: this.parseValue(logEntry.Volume_Delta),
                    kaufmanAMA: this.parseValue(logEntry.Kaufman_AMA),
                    pivot: this.parseValue(logEntry.Pivot),
                    r1: this.parseValue(logEntry.R1),
                    r2: this.parseValue(logEntry.R2),
                    s1: this.parseValue(logEntry.S1),
                    s2: this.parseValue(logEntry.S2),
                    '5_ema': logEntry['5_ema'],
                    '5_ehlers_supertrend': logEntry['5_ehlers_supertrend'],
                    '15_ema': logEntry['15_ema'],
                    '15_ehlers_supertrend': logEntry['15_ehlers_supertrend'],
                    fib_0: this.parseValue(logEntry['0.0%']),
                    fib_236: this.parseValue(logEntry['23.6%']),
                    fib_382: this.parseValue(logEntry['38.2%']),
                    fib_50: this.parseValue(logEntry['50.0%']),
                    fib_618: this.parseValue(logEntry['61.8%']),
                    fib_786: this.parseValue(logEntry['78.6%']),
                    fib_100: this.parseValue(logEntry['100.0%']),
                };
                dataPoints.push(this.enrichDataPoint(dataPoint));
            }
        } catch (error) {
            parseErrors++;
            if (this.options.debugMode) {
                logger.debug(chalk.gray(`Skipping non-JSON line: ${line}`));
            }
        }
    }

    const errorRate = lines.length > 0 ? parseErrors / lines.length : 0;
    if (errorRate > this.options.parseErrorTolerance) {
      logger.warn(chalk.yellow(`High JSON parse error rate: ${(errorRate * 100).toFixed(2)}%`));
    }

    const limitedDataPoints = dataPoints.slice(-this.options.maxDataPoints);
    
    logger.info(chalk.green(
      `Extracted ${limitedDataPoints.length} data points for ${this.tradingSymbol}`
    ));
    
    return limitedDataPoints;
  }

  parseValue(value, key) {
    if (value === 'nan' || value === null || value === undefined) {
      return undefined;
    }
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
    if (dataPoint.bb_upper && dataPoint.bb_lower) {
      dataPoint.bb_width = dataPoint.bb_upper - dataPoint.bb_lower;
      dataPoint.bb_percent = dataPoint.currentPrice 
        ? (dataPoint.currentPrice - dataPoint.bb_lower) / dataPoint.bb_width 
        : undefined;
    }
    dataPoint.parsedAt = new Date().toISOString();
    return dataPoint;
  }

  extractTimestamp(line) {
    const patterns = [
      /(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+[+-]\d{2}:\d{2})/,
      /(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/,
      /@ (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})/
    ];
    for (const pattern of patterns) {
      const match = line.match(pattern);
      if (match) {
        return match[1];
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
    const requiredIndicators = ['currentPrice', 'rsi', 'macd_line'];
    for (const point of dataPoints) {
      for (const indicator of requiredIndicators) {
        if (point[indicator] === undefined) {
          warnings.push(`Missing ${indicator} in some data points`);
        }
      }
    }
    return { isValid, warnings };
  }

  getLatestMarketData(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};
    const latest = dataPoints[dataPoints.length - 1];
    const previous = dataPoints.length > 1 ? dataPoints[dataPoints.length - 2] : latest;
    const priceChange = latest.currentPrice && previous.currentPrice 
      ? latest.currentPrice - previous.currentPrice 
      : 0;
    const priceChangePercent = previous.currentPrice 
      ? (priceChange / previous.currentPrice) * 100 
      : 0;
    return {
      ...latest,
      priceChange,
      priceChangePercent,
      historicalData: dataPoints.slice(-10)
    };
  }

  getCached(key) {
    if (!this.options.cacheEnabled) return null;
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp < this.options.cacheTTL) {
      return cached.data;
    }
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
    if (this.cache.size > 10) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
  }

  clearCache() {
    this.cache.clear();
    logger.info(chalk.green('Parser cache cleared'));
  }
}