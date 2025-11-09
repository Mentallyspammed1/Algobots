#!/usr/bin/env node
// Enhanced Trend Analysis Engine (Node.js for Termux)

// --- Dependency Setup ---
let fetch;
let chalk;

try {
  fetch = globalThis.fetch || require('node-fetch');
} catch (e) {
  console.error("Error requiring 'node-fetch'. Please ensure it's installed or use Node.js v18+.");
  process.exit(1);
}

try {
    chalk = require('chalk');
} catch (e) {
    console.warn("Chalk library not found. Output will not be colored. Run 'npm install chalk'.");
    chalk = {
        bold: { magenta: (s) => s, yellow: (s) => s, green: (s) => s, red: (s) => s },
        magenta: (s) => s, yellow: (s) => s, green: (s) => s, red: (s) => s, white: (s) => s,
        hex: () => (s) => s,
    };
}

// Neon Color Palette (Using chalk.hex)
const NEON_MAGENTA = '#FF00FF';
const NEON_CYAN = '#00FFFF';
const NEON_LIME = '#CCFF00';
const NEON_RED = '#FF3333';
const NEON_GREEN = '#39FF14';

// --- Utility Functions ---

async function timeout(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function getKlineData(symbol, interval, limit = 200) {
  const baseUrl = "https://api.bybit.com";
  const endpoint = "/v5/market/kline";
  const params = new URLSearchParams({
    category: "linear",
    symbol: symbol,
    interval: interval,
    limit: limit.toString(),
  });

  try {
    const response = await fetch(`${baseUrl}${endpoint}?${params}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    const data = await response.json();

    if (data.retCode !== 0) {
      console.error(`Bybit API Error: ${data.retMsg} (Code: ${data.retCode})`);
      return null;
    }

    const klines = data.result.list;
    if (!klines || klines.length === 0) {
      console.warn(`No kline data received for ${symbol} with interval ${interval}.`);
      return null;
    }

    const df = klines.map(k => ({
      timestamp: parseInt(k[0]),
      open: parseFloat(k[1]),
      high: parseFloat(k[2]),
      low: parseFloat(k[3]),
      close: parseFloat(k[4]),
      volume: parseFloat(k[5]),
    }));

    return df.sort((a, b) => a.timestamp - b.timestamp);

  } catch (error) {
    console.error(chalk.red.bold(`Error fetching kline data for ${symbol}:`), error.message);
    return null;
  }
}

// --- Indicator Calculation Functions ---

function calculateSMA(data, period) {
  if (data.length < period) return null;
  const slice = data.slice(-period);
  return slice.reduce((sum, row) => sum + row.close, 0) / period;
}

function getEmaSeries(data, period) {
    if (data.length === 0) return [];
    const alpha = 2 / (period + 1);
    const emaSeries = new Array(data.length).fill(null);
    
    if (data.length >= period) {
        const initialSlice = data.slice(0, period);
        let currentEma = initialSlice.reduce((sum, row) => sum + row.close, 0) / period;
        
        for (let i = 0; i < period; i++) {
            emaSeries[i] = currentEma; 
        }
        
        for (let i = period; i < data.length; i++) {
            currentEma = (data[i].close - currentEma) * alpha + currentEma;
            emaSeries[i] = currentEma;
        }
    } else {
        return emaSeries;
    }
    
    return emaSeries;
}

function calculateEMA(data, period) {
    if (data.length < period) return null;
    const series = getEmaSeries(data, period);
    return series[series.length - 1];
}

function calculateMACD(data, fastPeriod = 12, slowPeriod = 26, signalPeriod = 9) {
  if (data.length < slowPeriod) return { macd: null, signal: null, histogram: null };

  const closeValues = data.map(d => d.close);
  
  const emaFastSeries = getEmaSeries(data, fastPeriod);
  const emaSlowSeries = getEmaSeries(data, slowPeriod);
  
  const macdSeries = emaFastSeries.map((fast, i) => {
    if (fast !== null && emaSlowSeries[i] !== null) {
      return fast - emaSlowSeries[i];
    }
    return null;
  }).filter(v => v !== null); 

  const macdDataForSignal = macdSeries.map(m => ({ close: m }));
  const signalSeries = getEmaSeries(macdDataForSignal, signalPeriod).filter(v => v !== null);

  const macd = macdSeries[macdSeries.length - 1] || null;
  const signal = signalSeries[signalSeries.length - 1] || null;
  const histogram = (macd !== null && signal !== null) ? macd - signal : null;

  return { macd, signal, histogram };
}

function calculateRSI(data, period = 14) {
  if (data.length < period + 1) return null;

  let gains = 0;
  let losses = 0;

  for (let i = data.length - period; i < data.length; i++) {
    const change = data[i].close - data[i - 1].close;
    if (change > 0) {
      gains += change;
    } else {
      losses += Math.abs(change);
    }
  }

  const avgGain = gains / period;
  const avgLoss = losses / period;

  if (avgLoss === 0) return 100;
  if (avgGain === 0 && avgLoss > 0) return 0; 

  const rs = avgGain / avgLoss;
  const rsi = 100 - (100 / (1 + rs));

  return rsi;
}

function calculateBollingerBands(data, period = 20, stdDev = 2) {
  if (data.length < period) return { middle: null, upper: null, lower: null };

  const slice = data.slice(-period);
  const sma = slice.reduce((sum, row) => sum + row.close, 0) / period;

  let sumSqDiff = 0;
  for (const row of slice) {
    sumSqDiff += Math.pow(row.close - sma, 2);
  }
  const stdDevValue = Math.sqrt(sumSqDiff / period);

  return {
    middle: sma,
    upper: sma + stdDevValue * stdDev,
    lower: sma - stdDevValue * stdDev,
  };
}

function calculateATR(data, period = 14) {
    if (data.length < period) return null;

    let trSum = 0;
    for (let i = data.length - period; i < data.length; i++) {
        const highLow = data[i].high - data[i].low;
        const closePrev = i > 0 ? data[i-1].close : data[i].open; 
        
        const highClosePrev = Math.abs(data[i].high - closePrev);
        const lowClosePrev = Math.abs(data[i].low - closePrev);
        
        const tr = Math.max(highLow, highClosePrev, lowClosePrev);
        trSum += tr;
    }
    return trSum / period;
}

// --- Main Logic Functions ---

function calculateIndicators(df) {
  const requiredDataPoints = 50;
  if (!df || df.length < requiredDataPoints) {
    return {};
  }

  const indicators = {};
  
  indicators.sma_20 = calculateSMA(df, 20);
  indicators.sma_50 = calculateSMA(df, 50);
  
  indicators.ema_12 = calculateEMA(df, 12);
  indicators.ema_26 = calculateEMA(df, 26);

  const macdData = calculateMACD(df, 12, 26, 9);
  indicators.macd = macdData.macd;
  indicators.macd_signal = macdData.signal;
  indicators.macd_histogram = macdData.histogram;

  indicators.rsi = calculateRSI(df, 14);

  const bb = calculateBollingerBands(df, 20, 2);
  indicators.bb_middle = bb.middle;
  indicators.bb_upper = bb.upper;
  indicators.bb_lower = bb.lower;

  indicators.atr = calculateATR(df, 14);

  if (df.length >= 2 && df[df.length - 2].volume > 0) {
    indicators.volume_change_pct = ((df[df.length - 1].volume - df[df.length - 2].volume) / df[df.length - 2].volume) * 100;
  } else {
    indicators.volume_change_pct = null;
  }

  const latest = df[df.length - 1];
  return {
      ...indicators,
      close: latest.close,
      volume: latest.volume,
      timestamp: latest.timestamp
  };
}

function createGeminiPrompt(symbol, interval, currentPrice, indicators) {
  const prompt = `
Analyze the following cryptocurrency market data for ${symbol} on the ${interval} interval.
Provide a concise trading signal (BUY, SELL, HOLD), a trend assessment (UPTREND, DOWNTREND, SIDEWAYS), a confidence level (0-100), and a brief explanation.
Include key factors that influenced the decision. If applicable, suggest an entry price, target price, and stop-loss price.

Current Price: ${currentPrice.toFixed(4)}

Indicators:
- SMA 20: ${indicators.sma_20 ? indicators.sma_20.toFixed(4) : 'N/A'}
- SMA 50: ${indicators.sma_50 ? indicators.sma_50.toFixed(4) : 'N/A'}
- EMA 12: ${indicators.ema_12 ? indicators.ema_12.toFixed(4) : 'N/A'}
- EMA 26: ${indicators.ema_26 ? indicators.ema_26.toFixed(4) : 'N/A'}
- MACD: ${indicators.macd ? indicators.macd.toFixed(4) : 'N/A'}
- MACD Signal: ${indicators.macd_signal ? indicators.macd_signal.toFixed(4) : 'N/A'}
- MACD Histogram: ${indicators.macd_histogram ? indicators.macd_histogram.toFixed(4) : 'N/A'}
- RSI: ${indicators.rsi ? indicators.rsi.toFixed(2) : 'N/A'}
- Bollinger Bands Middle: ${indicators.bb_middle ? indicators.bb_middle.toFixed(4) : 'N/A'}
- Bollinger Bands Upper: ${indicators.bb_upper ? indicators.bb_upper.toFixed(4) : 'N/A'}
- Bollinger Bands Lower: ${indicators.bb_lower ? indicators.bb_lower.toFixed(4) : 'N/A'}
- Volume Change %: ${indicators.volume_change_pct !== null ? indicators.volume_change_pct.toFixed(2) + '%' : 'N/A'}
- ATR: ${indicators.atr ? indicators.atr.toFixed(4) : 'N/A'}

Consider the interplay of these indicators.
Focus on potential reversals or continuations.
Is the price above/below moving averages? Is RSI overbought/oversold? Is MACD showing a bullish/bearish crossover? Are Bollinger Bands widening/narrowing? Is volume supporting the price action?

Output format:
JSON object with keys: "signal", "trend", "confidence", "explanation", "key_factors", "entry_price", "target_price", "stop_loss_price".
signal must be one of: BUY, SELL, HOLD.
trend must be one of: UPTREND, DOWNTREND, SIDEWAYS.
entry_price, target_price, and stop_loss_price can be null if not applicable.
confidence should be an integer between 0 and 100.
key_factors should be an array of strings.
`;
  return prompt;
}

async function callGeminiApi(prompt) {
  console.log(chalk.hex(NEON_CYAN)("--- Calling Gemini API (Mock) ---"));
  await timeout(1000);
  const mockResponse = {
    signal: Math.random() > 0.6 ? (Math.random() > 0.5 ? "BUY" : "SELL") : "HOLD",
    trend: ["UPTREND", "DOWNTREND", "SIDEWAYS"][Math.floor(Math.random() * 3)],
    confidence: Math.floor(Math.random() * 81) + 10,
    explanation: "Based on the combination of indicators, a potential shift in momentum is observed. RSI indicates near-oversold conditions while MACD shows a potential bullish divergence.",
    key_factors: ["Potential MACD Crossover", "RSI Oversold/Overbought", "Price near Bollinger Band edge"],
    entry_price: Math.random() > 0.3 ? parseFloat((Math.random() * 1000).toFixed(4)) : null,
    target_price: Math.random() > 0.3 ? parseFloat((Math.random() * 1500).toFixed(4)) : null,
    stop_loss_price: Math.random() > 0.3 ? parseFloat((Math.random() * 500).toFixed(4)) : null,
  };
  mockResponse.signal = mockResponse.signal || "HOLD";
  mockResponse.trend = mockResponse.trend || "SIDEWAYS";
  mockResponse.confidence = mockResponse.confidence || 50;
  mockResponse.explanation = mockResponse.explanation || "Default explanation.";
  mockResponse.key_factors = mockResponse.key_factors || [];
  return JSON.stringify(mockResponse);
}

function parseAiResponse(aiResponse) {
  try {
    const parsed = JSON.parse(aiResponse);
    const analysis = {
      signal: parsed.signal ? parsed.signal.toUpperCase() : "HOLD",
      trend: parsed.trend ? parsed.trend.toUpperCase() : "SIDEWAYS",
      confidence: typeof parsed.confidence === 'number' ? Math.max(0, Math.min(100, parsed.confidence)) : 0,
      explanation: parsed.explanation || "AI analysis incomplete.",
      key_factors: Array.isArray(parsed.key_factors) ? parsed.key_factors : [],
      entry_price: typeof parsed.entry_price === 'number' ? parsed.entry_price : null,
      target_price: typeof parsed.target_price === 'number' ? parsed.target_price : null,
      stop_loss_price: typeof parsed.stop_loss_price === 'number' ? parsed.stop_loss_price : null,
    };
    
    // Validate signal and trend values
    const validSignals = ["BUY", "SELL", "HOLD"];
    if (!validSignals.includes(analysis.signal)) analysis.signal = "HOLD";
    
    const validTrends = ["UPTREND", "DOWNTREND", "SIDEWAYS"];
    if (!validTrends.includes(analysis.trend)) analysis.trend = "SIDEWAYS";

    return analysis;
  } catch (error) {
    console.error(chalk.red("Error parsing AI response:"), error.message);
    return {
      signal: "HOLD",
      trend: "SIDEWAYS",
      confidence: 0,
      explanation: "Failed to parse AI response.",
      key_factors: [],
      entry_price: null,
      target_price: null,
      stop_loss_price: null
    };
  }
}

async function analyzeSymbol(symbol, interval, klineLimit) {
  const df = await getKlineData(symbol, interval, klineLimit);

  if (!df) {
    return { symbol, interval, category: "linear", timestamp: new Date().toISOString(), current_price: 0, error: "No market data available." };
  }

  const requiredDataPoints = 50;
  if (df.length < requiredDataPoints) {
      return { symbol, interval, category: "linear", timestamp: new Date().toISOString(), current_price: df[df.length - 1].close, error: `Insufficient data points (${df.length}). Need at least ${requiredDataPoints}.` };
  }

  const currentPrice = df[df.length - 1].close;
  const indicators = calculateIndicators(df);

  if (indicators.sma_20 === null || indicators.macd === null || indicators.rsi === null) {
      return { symbol, interval, category: "linear", timestamp: new Date().toISOString(), current_price: currentPrice, error: "Not enough data for ALL primary indicators (SMA20, MACD, RSI)." };
  }

  const prompt = createGeminiPrompt(symbol, interval, currentPrice, indicators);
  const aiResponse = await callGeminiApi(prompt);
  const analysis = parseAiResponse(aiResponse);

  const price24hPct = ((currentPrice - df[0].open) / df[0].open) * 100; 
  
  const tickerInfo = {
      mark_price: currentPrice,
      price_24h_pct: price24hPct,
      volume_24h: df.reduce((sum, row) => sum + row.volume, 0),
      turnover_24h: 0, 
  };

  return {
    symbol: symbol,
    interval: interval,
    category: "linear",
    timestamp: new Date().toISOString(),
    current_price: currentPrice,
    analysis: analysis,
    indicators: indicators,
    additional_info: tickerInfo,
    error: null
  };
}

async function runAnalysis(symbols, interval, klineLimit, minConfidence) {
  console.log(chalk.bold.hex(NEON_MAGENTA)("\n🚀 Starting Enhanced Trend Analysis Engine"));

  const tasks = symbols.map(symbol => analyzeSymbol(symbol, interval, klineLimit));

  const results = await Promise.all(tasks);

  const successfulResults = results.filter(r => !r.error && r.analysis.confidence >= minConfidence);
  const lowConfidenceResults = results.filter(r => !r.error && r.analysis.confidence < minConfidence);
  const failedResults = results.filter(r => r.error);

  if (successfulResults.length > 0) {
    displayResults(successfulResults.sort((a, b) => b.analysis.confidence - a.analysis.confidence), true);
  } else {
    console.log(chalk.bold.yellow("\nNo high-confidence signals found based on current criteria."));
  }

  if (lowConfidenceResults.length > 0) {
    console.log(chalk.bold.hex(NEON_CYAN)("\nLow Confidence Signals:"));
    displayResults(lowConfidenceResults.sort((a, b) => b.analysis.confidence - a.analysis.confidence), false);
  }

  if (failedResults.length > 0) {
    console.log(chalk.bold.hex(NEON_RED)("\nErrors during analysis:"));
    failedResults.forEach(res => {
      console.log(`  - ${res.symbol}: ${chalk.red(res.error)}`);
    });
  }

  console.log(chalk.bold.hex(NEON_LIME)("\nAnalysis complete."));
}

function displayResults(results, showTitle = true) {
    if (!results || results.length === 0) return;

    let title = "\n📊 Market Analysis Results";
    if (showTitle) {
        title += ` (Conf >= ${results[0].analysis.confidence}%)`;
    }
    console.log(chalk.bold.hex(NEON_CYAN)(title));
    console.log(chalk.hex(NEON_CYAN)("--------------------------------------------------"));

    results.forEach(result => {
        const price24hPct = result.additional_info.price_24h_pct.toFixed(2);
        const trend = result.analysis.trend;
        const signal = result.analysis.signal;
        const confidence = result.analysis.confidence;
        const explanation = result.analysis.explanation;
        const truncatedExplanation = explanation.length > 70 ? explanation.substring(0, 70) + "..." : explanation;

        let symbolColor = chalk.bold.hex(NEON_MAGENTA);
        
        let signalColor = chalk.white;
        if (signal === "BUY") signalColor = chalk.bold.hex(NEON_GREEN);
        if (signal === "SELL") signalColor = chalk.bold.hex(NEON_RED);
        
        let trendColor = chalk.white;
        if (trend === "UPTREND") trendColor = chalk.hex(NEON_GREEN);
        if (trend === "DOWNTREND") trendColor = chalk.hex(NEON_RED);

        console.log(
            `  - ${symbolColor(result.symbol)}: ` +
            `Price: ${chalk.white(`$${result.current_price.toFixed(4)}`)}, ` +
            `24h %: ${price24hPct > 0 ? chalk.green(price24hPct + '%') : price24hPct < 0 ? chalk.red(price24hPct + '%') : chalk.white(price24hPct + '%')}, ` +
            `Trend: ${trendColor(trend)}, ` +
            `Signal: ${signalColor(signal)}, ` +
            `Conf: ${confidence}%, ` +
            `Exp: ${chalk.white(truncatedExplanation)}`
        );

        if (result.analysis.entry_price !== null) {
            console.log(`    - ${chalk.hex(NEON_LIME)("Entry")}: $${result.analysis.entry_price.toFixed(4)}`);
        }
        if (result.analysis.target_price !== null) {
            console.log(`    - ${chalk.hex(NEON_LIME)("Target")}: $${result.analysis.target_price.toFixed(4)}`);
        }
        if (result.analysis.stop_loss_price !== null) {
            console.log(`    - ${chalk.hex(NEON_LIME)("Stop Loss")}: $${result.analysis.stop_loss_price.toFixed(4)}`);
        }
        if (result.analysis.key_factors && result.analysis.key_factors.length > 0) {
            console.log(`    - ${chalk.hex(NEON_CYAN)("Key Factors")}: ${result.analysis.key_factors.join(', ')}`);
        }
    });
    console.log(chalk.hex(NEON_CYAN)("--------------------------------------------------"));
}

async function main() {
  const args = {};
  process.argv.slice(2).forEach((arg, index, arr) => {
    if (arg.startsWith('--')) {
      const key = arg.substring(2);
      if (arr.length > index + 1 && !arr[index + 1].startsWith('--')) {
        args[key] = arr[index + 1];
      } else {
        args[key] = true;
      }
    }
  });

  const symbols = args.symbols ? args.symbols.split(',') : ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
  const interval = args.interval || "15m";
  const klineLimit = parseInt(args.kline_limit) || 200;
  const minConfidence = parseInt(args.min_confidence) || 70;

  try {
    await runAnalysis(symbols, interval, klineLimit, minConfidence);
  } catch (error) {
    console.error(chalk.bold.red("A critical error occurred during script execution:"), error);
  }
}

main();
