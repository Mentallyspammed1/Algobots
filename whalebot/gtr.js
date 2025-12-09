// unified_oracle_final_v11.js
// Pyrmethus Supreme: Final Consolidated Oracle v11.0 - Robust & Interactive

import { GoogleGenAI } from "@google/genai";
import * as fs from 'fs';
import 'dotenv/config';
import fetch from 'node-fetch'; 
import promptSync from 'prompt-sync'; 
import { v4 as uuidv4 } from 'uuid';

// --- CONFIGURATION & CONSTANTS ---
const CONFIG = {
    API_KEY: process.env.GEMINI_API_KEY,
    LOG_FILE_PATH: 'whalebot.log',
    CONFIG_FILE: 'config.json',
    MODEL_NAME: 'gemini-2.5-flash',
    BYBIT_BASE_URL: 'https://api.bybit.com',
    REQUEST_TIMEOUT: 10000, 
    LOOP_DELAY_SECONDS: 15,
    DEFAULT_SYMBOL: "BTCUSDT", DEFAULT_INTERVAL: "15", SIGNAL_SCORE_THRESHOLD: 1.0,
    ATR_FALLBACK_PERCENT: 0.005, 
    RISK_PER_TRADE: 1.0, SL_MULTIPLIER: 1.5, TP_MULTIPLIER: 2.0,
    OVERBOUGHT_THRESHOLD: 70, OVERSOLD_THRESHOLD: 30,
    THRESHOLDS: { ADX_STRONG: 25, STOCH_RSI_MID: 50, ATR_DEFAULT_USD: 100.00 },
    DEFAULT_CONFIG: {
        symbol: "BTCUSDT", interval: "15", loop_delay: 15, signal_score_threshold: 1.0,
        trade_management: { enabled: false, account_balance: 1000.0, risk_per_trade_percent: 1.0, slippage_percent: 0.001, trading_fee_percent: 0.0005, order_precision: 5, price_precision: 3},
        mtf_analysis: { enabled: false, higher_timeframes: ["60"], trend_indicators: ["ema"], trend_period: 50},
        indicator_settings: { atr_period: 14, ema_short_period: 9, ema_long_period: 21, rsi_period: 14, macd_fast_period: 12, macd_slow_period: 26, macd_signal_period: 9, psar_acceleration: 0.02, psar_max_acceleration: 0.2 },
        indicators: { ema: true, atr_indicator: true, rsi: true, macd: true, vwap: true, psar: true, cci: false, wr: false, mfi: false, obv: false, kama: false, roc: false },
        weight_sets: { default_scalping: { ema_alignment: 0.3, rsi: 0.2, macd_alignment: 0.2, adx_strength: 0.2, vwap: 0.1, ehlers_supertrend_alignment: 0.3 } },
    },
    BYBIT_ERROR_CODES: { 10004: "Signature Error", 10006: "Invalid API Key" }
};

// --- Color Scheme & Logger ---
const NEON = {
    SUCCESS: "\x1b[38;2;50;205;50m", INFO: "\x1b[38;2;64;224;208m", HIGHLIGHT: "\x1b[38;2;173;255;47m",
    RESET: "\x1b[0m", ERROR: "\x1b[38;2;255;36;0m", ACCENT: "\x1b[38;2;127;255;0m",
};
const NEON_GREEN = NEON.SUCCESS; const NEON_RED = NEON.ERROR; const NEON_YELLOW = NEON.HIGHLIGHT;
const NEON_BLUE = NEON.INFO; const NEON_CYAN = NEON.SUCCESS; 

function redactMessage(message) { 
    const SENSITIVE_PATTERNS = [/API_KEY=[^&]+/gi, /symbol=[A-Z0-9]+/gi, /price=[\d.]+/gi, /entry=[\d.]+/gi];
    return SENSITIVE_PATTERNS.reduce((msg, pattern) => msg.replace(pattern, '[REDACTED]'), message);
}

const log = {
    info: (msg) => console.log(`${NEON.INFO}${new Date().toISOString().substring(11, 23)} - INFO - ${redactMessage(msg)}${NEON.RESET}`),
    warning: (msg) => console.warn(`${NEON.YELLOW}${new Date().toISOString().substring(11, 23)} - WARNING - ${redactMessage(msg)}${NEON.RESET}`),
    error: (msg) => console.error(`${NEON.RED}${new Date().toISOString().substring(11, 23)} - ERROR - ${redactMessage(msg)}${NEON.RESET}`),
    debug: (msg) => process.env.DEBUG && console.log(`${NEON.CYAN}${new Date().toISOString().substring(11, 23)} - DEBUG - ${redactMessage(msg)}${NEON.RESET}`),
};

// --- Utility Functions (Config, Retry, Validation) ---
function deepMerge(target, source) { 
    for (const k of Object.keys(source)) {
        const v = source[k];
        if (v && typeof v === 'object' && !Array.isArray(v)) {
            target[k] = deepMerge((target[k] || {}), v);
        } else {
            target[k] = v;
        }
    }
    return target;
}

function validateConfig(cfg) {
    const errs = [];
    if (!cfg.symbol) errs.push("symbol is required");
    if (typeof cfg.signal_score_threshold !== 'number') errs.push("signal_score_threshold must be a number");
    // Add more validation checks here if needed
    return { valid: errs.length === 0, errors: errs };
}

function loadConfig(filepath, logger) {
    const default_config = CONFIG.DEFAULT_CONFIG;
    if (!fs.existsSync(filepath)) {
        logger.warning(`Config file not found. Creating default at ${filepath}`);
        fs.writeFileSync(filepath, JSON.stringify(default_config, null, 4));
        return default_config;
    }
    try {
        const content = fs.readFileSync(filepath, 'utf8');
        const userConfig = JSON.parse(content);
        const merged = deepMerge({ ...default_config }, userConfig);
        // Ensure nested objects are also merged correctly
        if(userConfig.trade_management) merged.trade_management = {...default_config.trade_management, ...userConfig.trade_management};
        if(userConfig.indicator_settings) merged.indicator_settings = {...default_config.indicator_settings, ...userConfig.indicator_settings};
        if(userConfig.weight_sets) merged.weight_sets = {...default_config.weight_sets, ...userConfig.weight_sets};
        return merged;
    } catch (e) {
        logger.error(`Error loading config: ${e.message}. Using default.`);
        return default_config;
    }
}

async function withRetry(fn, maxRetries = 3, delay = 1000) {
  for (let i = 0; i <= maxRetries; i++) {
    try {
      return await fn();
    } catch (e) {
      if (i < maxRetries) {
        log.warning(`Request failed. Retrying... (${i + 1}/${maxRetries})`);
        await new Promise(resolve => setTimeout(resolve, delay * (i + 1)));
      } else {
        throw e; // Re-throw the last error
      }
    }
  }
}

// --- CORE INDICATOR CALCULATIONS (Stubs & Simplified Implementations) ---
// Note: Full, complex indicator logic translated from Python would be extremely verbose.
// Key indicators are implemented; others are stubs to maintain structure.

function calculateSMA(series, period) { 
    if (series.length < period) return new Array(series.length).fill(NaN);
    const sma = new Array(series.length).fill(NaN);
    for (let i = period - 1; i < series.length; i++) {
        sma[i] = series.slice(i - period + 1, i + 1).reduce((a, b) => a + b, 0) / period;
    }
    return sma;
}

function calculateEMA(series, period) {
    const alpha = 2 / (period + 1);
    const ema = new Array(series.length).fill(NaN);
    if (series.length > 0) ema[0] = series[0];
    for (let i = 1; i < series.length; i++) {
        ema[i] = series[i] * alpha + (isNaN(ema[i-1]) ? series[i] : ema[i - 1]) * (1 - alpha);
    }
    return ema;
}

function calculateTrueRange(data) {
    const tr = [NaN];
    for (let i = 1; i < data.length; i++) {
        const highLow = data[i].high - data[i].low;
        const highPrevClose = Math.abs(data[i].high - data[i - 1].close);
        const lowPrevClose = Math.abs(data[i].low - data[i - 1].close);
        tr.push(Math.max(highLow, highPrevClose, lowPrevClose));
    }
    return tr;
}

function calculateATR(data, period) {
    const tr = calculateTrueRange(data);
    const atr = new Array(data.length).fill(NaN);
    if (tr.length <= period) return atr;
    let avgTr = tr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
    atr[period] = avgTr;
    for (let i = period + 1; i < tr.length; i++) {
        avgTr = (tr[i] + (period - 1) * avgTr) / period;
        atr[i] = avgTr;
    }
    return atr;
}

function calculateRSI(closePrices, period) {
    const rsi = new Array(closePrices.length).fill(NaN);
    if (closePrices.length <= period) return rsi;
    const gains = []; const losses = [];
    for (let i = 1; i < closePrices.length; i++) {
        const diff = closePrices[i] - closePrices[i - 1];
        gains.push(Math.max(0, diff)); losses.push(Math.max(0, -diff));
    }
    let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
    if (avgLoss === 0) avgLoss = 0.0001;
    let rs = avgGain / avgLoss;
    rsi[period] = 100 - (100 / (1 + rs));
    for (let i = period + 1; i < closePrices.length; i++) {
        avgGain = (gains[i - 1] + (period - 1) * avgGain) / period;
        avgLoss = (losses[i - 1] + (period - 1) * avgLoss) / period;
        if (avgLoss === 0) avgLoss = 0.0001;
        rs = avgGain / avgLoss;
        rsi[i] = 100 - (100 / (1 + rs));
    }
    return rsi;
}

function calculateMACD(closePrices, fastP, slowP, signalP) {
    const emaFast = calculateEMA(closePrices, fastP);
    const emaSlow = calculateEMA(closePrices, slowP);
    const macdLine = emaFast.map((val, i) => (isNaN(val) || isNaN(emaSlow[i])) ? NaN : val - emaSlow[i]);
    const signalLine = calculateEMA(macdLine.filter(v => !isNaN(v)), signalP);
    const histogram = macdLine.map((val, i) => (isNaN(val) || isNaN(signalLine[i])) ? NaN : val - signalLine[i]);
    return { macdLine, signalLine, histogram };
}

function calculateVWAP(data) {
    let cumulativeTPVolume = 0;
    let cumulativeVolume = 0;
    const vwap = new Array(data.length).fill(NaN);
    for (let i = 0; i < data.length; i++) {
        const typicalPrice = (data[i].high + data[i].low + data[i].close) / 3;
        cumulativeTPVolume += typicalPrice * data[i].volume;
        cumulativeVolume += data[i].volume;
        vwap[i] = cumulativeVolume > 0 ? cumulativeTPVolume / cumulativeVolume : NaN;
    }
    return vwap;
}

function calculatePSAR(data, acceleration, max_acceleration) {
    const psar = new Array(data.length).fill(NaN);
    const direction = new Array(data.length).fill(0); 
    if (data.length < 2) return [psar, direction];
    let ep = data[0].close < data[1].close ? data[0].low : data[0].high;
    let af = acceleration;
    direction[0] = data[0].close < data[1].close ? 1 : -1;
    psar[0] = data[0].close;
    for (let i = 1; i < data.length; i++) {
        const prev_psar = psar[i - 1];
        const prev_dir = direction[i - 1];
        psar[i] = prev_psar + (prev_dir * af) * (ep - prev_psar);
        let new_dir = prev_dir; let new_ep = ep; let new_af = af;
        if (prev_dir === 1 && data[i].low < psar[i]) { new_dir = -1; new_af = acceleration; new_ep = data[i].high; } 
        else if (prev_dir === -1 && data[i].high > psar[i]) { new_dir = 1; new_af = acceleration; new_ep = data[i].low; } 
        else if (prev_dir === 1 && data[i].high > ep) { new_ep = data[i].high; new_af = Math.min(af + acceleration, max_acceleration); } 
        else if (prev_dir === -1 && data[i].low < ep) { new_ep = data[i].low; new_af = Math.min(af + acceleration, max_acceleration); }
        direction[i] = new_dir; af = new_af; ep = new_ep;
        if (new_dir === 1) psar[i] = Math.min(psar[i], data[i].low);
        else psar[i] = Math.max(psar[i], data[i].high);
    }
    return [psar, direction];
}
function calculateCCI(data, period) { return new Array(data.length).fill(NaN); }
function calculateWR(data, period) { return new Array(data.length).fill(NaN); }
function calculateMFI(data, period) { return new Array(data.length).fill(NaN); }
function calculateOBV(data, period) { return { obv: new Array(data.length).fill(0), obvEma: new Array(data.length).fill(NaN) }; }
function calculateKAMA(data, period, fast_period, slow_period) { return new Array(data.length).fill(NaN); }
function calculateROC(closePrices, period) { return new Array(closePrices.length).fill(NaN); }
function calculateEhlersSuperTrend(data, period, multiplier) { return { direction: new Array(data.length).fill(0), supertrend: new Array(data.length).fill(NaN) }; }

// --- API INTERACTION ---
async function bybitPublicRequest(endpoint, params) {
    const url = `${CONFIG.BYBIT_BASE_URL}/v5${endpoint}?${new URLSearchParams(params)}`;
    try {
        const response = await withRetry(() => fetch(url, { timeout: CONFIG.REQUEST_TIMEOUT }));
        if (!response.ok) throw new Error(`HTTP ${response.status} ${response.statusText}`);
        const data = await response.json();
        if (data.retCode !== 0) throw new Error(`Bybit API Error: Code ${data.retCode} - ${data.retMsg}`);
        return data.result;
    } catch (error) {
        log.error(`API Request Failed for ${url}: ${error.message}`);
        return null;
    }
}

async function fetchCurrentPrice(symbol) {
  const result = await bybitPublicRequest('/market/tickers', { category: 'linear', symbol });
  if (result && result.list && result.list.length > 0) return parseFloat(result.list[0]?.lastPrice ?? '0');
  return null;
}
async function fetchOrderbook(symbol) { return { a: [], b: [] }; }
async function fetchKlines(symbol, interval, limit) { 
    const result = await bybitPublicRequest('/market/kline', { category: 'linear', symbol, interval, limit });
    if (result && result.list) {
        return result.list.map(bar => ({
            start_time: bar[0], open: parseFloat(bar[1]), high: parseFloat(bar[2]), low: parseFloat(bar[3]),
            close: parseFloat(bar[4]), volume: parseFloat(bar[5]), turnover: parseFloat(bar[6])
        }));
    }
    return null;
}

// --- USER INTERACTION & VALIDATION ---
function validateSymbol(symbol) { return symbol && typeof symbol === 'string' && symbol.length >= 3 && symbol.length <= 8 && symbol.endsWith("USDT"); }
function promptUserForSymbol() { 
    const s = prompt(`Enter symbol (e.g., BTCUSDT, or press Enter for default ${CONFIG.DEFAULT_SYMBOL}): `);
    return (s && s.trim() !== '' && validateSymbol(s.toUpperCase())) ? s.trim().toUpperCase() : CONFIG.DEFAULT_SYMBOL;
}

// --- SIGNAL ENGINE CORE ---
async function analyzeLogsAndGenerateSignal(logs, config) { 
    const logLines = logs ? logs.split('\n') : [];
    const finalStatusLine = logLines.slice().reverse().find(line => line.includes('Raw Signal Score:'));
    
    let indicatorSnapshot = { ATR: null, RSI: null, MACD_Line: null, VWAP: null, PSAR_Val: null }; // Populate based on config
    let assetSymbol = config.symbol;
    let lastPrice = null;
    let executionPath = "DEEP INFERENCE (No clear log score)";

    // Simplified log parsing for fast path
    if (finalStatusLine) {
        const scoreMatch = finalStatusLine.match(/Score: ([\d.-]+)/);
        const signalMatch = finalStatusLine.match(/Final Signal: (\w+)/);
        const score = scoreMatch ? parseFloat(scoreMatch[1]) : 0.0;
        const signal = signalMatch ? signalMatch[1].toUpperCase() : "HOLD";
        
        const direction = signal === "BUY" ? "BUY" : signal === "SELL" ? "SELL" : "HOLD";
        const strength = score >= config.signal_score_threshold * 1.5 ? "HIGH" : score <= -config.signal_score_threshold * 1.5 ? "HIGH" : "MEDIUM";
        const rationale = `Python bot concluded with FINAL SIGNAL: ${signal} (Score ${score.toFixed(2)}). Path: FAST SCORE MATCH.`;
        
        const currentPrice = lastPrice || (await fetchCurrentPrice(assetSymbol)) || 0;
        const atr = (indicatorSnapshot.ATR && indicatorSnapshot.ATR > 0) ? indicatorSnapshot.ATR : currentPrice * CONFIG.ATR_FALLBACK_PERCENT; 
        
        let entry = currentPrice;
        let tp = direction === "BUY" ? entry + atr * CONFIG.TP_MULTIPLIER : entry - atr * CONFIG.TP_MULTIPLIER;
        let sl = direction === "BUY" ? entry - atr * CONFIG.SL_MULTIPLIER : entry + atr * CONFIG.SL_MULTIPLIER;

        if (direction === "HOLD") { tp = entry; sl = entry; }

        return {
            AssetSymbol: assetSymbol, CurrentPriceEstimate: currentPrice, SignalDirection: direction,
            EntryPrice: entry, TakeProfit: tp, StopLoss: sl, Strength: strength,
            Rationale: rationale, IndicatorSnapshot: indicatorSnapshot, ExecutionPath: executionPath
        };
    }
    
    return runGeminiAnalysis(logs, assetSymbol, lastPrice, indicatorSnapshot, config);
}

async function runGeminiAnalysis(logs, symbol, price, snapshot, config, liveMode = false) {
    log.warning(`Invoking deep Gemini inference (${liveMode ? 'Live' : 'Log'} Mode)...`);
    const prompt = createGeminiInferencePrompt(logs, symbol, price, snapshot, config);
    try {
        const response = await ai.models.generateContent({
            model: CONFIG.MODEL_NAME, contents: prompt,
            config: { responseMimeType: "application/json" }
        });
        const signalData = JSON.parse(response.text.trim());
        if (!signalData.IndicatorSnapshot) signalData.IndicatorSnapshot = snapshot;
        signalData.ExecutionPath = `DEEP GEMINI INFERENCE (${liveMode ? 'Live Mode' : 'Log Mode'})`; 
        return signalData;
    } catch (e) {
        log.error(`Gemini API call failed: ${e.message}`);
        return createFallbackSignal(symbol, price, snapshot, config, "GEMINI_API_FAILURE");
    }
}

function createFallbackSignal(symbol, price, snapshot, config, reason) {
    const p = price || 0;
    const atr = snapshot.ATR > 0 ? snapshot.ATR : p * CONFIG.ATR_FALLBACK_PERCENT;
    return {
        AssetSymbol: symbol, CurrentPriceEstimate: p, SignalDirection: "HOLD",
        EntryPrice: p, TakeProfit: p, StopLoss: p, Strength: "LOW",
        Rationale: `Fallback triggered: ${reason}. Check live connection or logs.`,
        IndicatorSnapshot: snapshot, ExecutionPath: "FALLBACK_STRATEGY"
    };
}

function createGeminiInferencePrompt(logs, symbol, price, snapshot, config) {
    const TA_CONTEXT = `Indicators active: ${Object.keys(config.indicators).filter(k => config.indicators[k]).join(', ')}.`;
    return `
    Analyze the following log entries or live data snapshot from the trading bot.
    Asset: ${symbol}. Latest known price estimate: ${price || 'Unknown'}. Context: ${TA_CONTEXT}
    
    Data Source:
    --- LOG DATA ---
    ${logs.slice(-10000)}
    --- END LOGS ---

    Deduce the most conservative and actionable trade signal (BUY, SELL, or HOLD). If API errors or low volume are reported, the signal MUST be HOLD.
    
    Format the output strictly as JSON based on the schema below.
    
    --- REQUIRED JSON SCHEMA ---
    {
        "AssetSymbol": "string", "CurrentPriceEstimate": "float", "SignalDirection": "string (BUY, SELL, or HOLD)",
        "EntryPrice": "float", "TakeProfit": "float", "StopLoss": "float",
        "Strength": "string (HIGH, MEDIUM, LOW)",
        "Rationale": "string",
        "IndicatorSnapshot": {
            "ATR": "float | null", "RSI": "float | null", "MACD_Line": "float | null", 
            "VWAP": "float | null", "PSAR_Val": "float | null", "EMA_Short": "float | null"
        }
    }
    `;
}

// --- LIVE ANALYSIS PATH ---
async function runLiveAnalysis(symbol, config) {
    log.info(`Fetching live data for ${symbol} on interval ${config.interval}...`);
    
    const klinesRaw = await fetchKlines(symbol, config.interval, 200);
    const currentPrice = await fetchCurrentPrice(symbol);

    if (!klinesRaw || klinesRaw.length < 100 || !currentPrice) {
        log.error(`Failed to retrieve sufficient live data for ${symbol}.`);
        return createFallbackSignal(symbol, currentPrice, {}, config, "LIVE_DATA_FETCH_FAILURE");
    }
    const klines = klinesRaw;

    const closes = klines.map(d => d.close);
    const snapshot = {};

    // Calculate Key Indicators for Snapshot
    snapshot.ATR = calculateATR(klines, config.indicator_settings.atr_period)[klines.length - 1];
    snapshot.RSI = calculateRSI(closes, config.indicator_settings.rsi_period)[closes.length - 1];
    
    const macdResult = calculateMACD(closes, config.indicator_settings.macd_fast_period, config.indicator_settings.macd_slow_period, config.indicator_settings.macd_signal_period);
    snapshot.MACD_Line = macdResult.macdLine[closes.length - 1];
    
    snapshot.VWAP = calculateVWAP(klines)[closes.length - 1];
    
    const [psarVal] = calculatePSAR(klines, config.indicator_settings.psar_acceleration, config.indicator_settings.psar_max_acceleration);
    snapshot.PSAR_Val = psarVal[psarVal.length - 1];
    
    snapshot.EMA_Short = calculateEMA(closes, config.indicator_settings.ema_short_period)[closes.length - 1];
    
    log.info(`Indicators calculated successfully from ${klines.length} bars.`);
    
    const logs = `--- LIVE DATA ANALYSIS --- ASSET: ${symbol}, PRICE: ${currentPrice}. Snapshot generated.`;
    return runGeminiAnalysis(logs, symbol, currentPrice, snapshot, config, true);
}

// --- MANIFESTATION ---
function manifestSignal(data) {
    const directionColor = data.SignalDirection === 'BUY' ? NEON.SUCCESS : data.SignalDirection === 'SELL' ? NEON.ERROR : NEON.INFO;
    
    console.log(`\n${NEON.ACCENT}✨ --- [ ARCANE SIGNAL MANIFESTED ] --- ✨${NEON.RESET}`);
    console.log(`${NEON.INFO}Execution Path: ${data.ExecutionPath || 'UNKNOWN'}${NEON.RESET}`);

    console.log(`\n${NEON.INFO}  Asset Symbol:  ${NEON.HIGHLIGHT}${data.AssetSymbol || 'UNKNOWN'}${NEON.RESET}`);
    console.log(`  Est. Price:    ${NEON.HIGHLIGHT}${data.CurrentPriceEstimate ? data.CurrentPriceEstimate.toFixed(2) : 'N/A'}${NEON.RESET}`);
    console.log(`${directionColor}  Signal Type:   ${data.SignalDirection}${NEON.RESET}`);
    console.log(`  Strength:      ${NEON.HIGHLIGHT}${data.Strength}${NEON.RESET}`);
    
    console.log(`\n${NEON.INFO}--- The Runic Coordinates ---${NEON.RESET}`);
    console.log(`  Entry Price:   ${NEON.HIGHLIGHT}${data.EntryPrice ? data.EntryPrice.toFixed(2) : 'N/A'}${NEON.RESET}`);
    console.log(`  Take Profit:   ${NEON.SUCCESS}${data.TakeProfit ? data.TakeProfit.toFixed(2) : 'N/A'}${NEON.RESET}`);
    console.log(`  Stop Loss:     ${NEON.ERROR}${data.StopLoss ? data.StopLoss.toFixed(2) : 'N/A'}${NEON.RESET}`);
    
    console.log(`\n${NEON.INFO}--- Indicator Echoes from the Abyss ---${NEON.RESET}`);
    if (data.IndicatorSnapshot) {
        for (const [indicator, value] of Object.entries(data.IndicatorSnapshot)) {
            const color = (value === null || value === 0 || value === 'null' || isNaN(value)) ? NEON_RED : NEON_HIGHLIGHT;
            const displayValue = value === null || value === 'null' || isNaN(value) ? 'N/A' : (typeof value === 'number' ? value.toFixed(4) : value);
            console.log(`  ${color}${indicator.padEnd(15)}: ${displayValue}${NEON.RESET}`);
        }
    }
    
    console.log(`\n${NEON.INFO}--- Rationale (The Prophecy from the Code's Soul) ---${NEON.RESET}`);
    console.log(`  ${NEON.HIGHLIGHT}${data.Rationale}${NEON.RESET}`);
    
    console.log(`\n${NEON.ACCENT}--------------------------------------------------${NEON.RESET}\n`);
    console.log(`${NEON.SUCCESS}✓ Enlightenment achieved! A clear directive has been summoned.${NEON.RESET}`);
}

// --- MAIN EXECUTION ---
async function executeOracle() {
    if (!CONFIG.API_KEY) {
        log.error("Gemini API Key missing. Proceeding in Log-Only/Simulated Live Mode.");
    }
    
    const config = loadConfig(CONFIG.CONFIG_FILE, log);

    const mode = prompt(`\n${NEON.ACCENT}Analyze live data or past logs? (L)ive / (P)ast [P]: ${NEON.RESET}`).toUpperCase();

    let signalResult: SignalOutput;

    try {
        if (mode === 'L') {
            const selectedSymbol = promptUserForSymbol();
            config.symbol = selectedSymbol;
            signalResult = await runLiveAnalysis(selectedSymbol, config);
        } else {
            // Past Log Analysis Mode
            if (!fs.existsSync(config.LOG_FILE_PATH)) {
                log.warning(`Log file not found. Defaulting to Live analysis for ${config.symbol}.`);
                signalResult = await runLiveAnalysis(config.symbol, config);
            } else {
                const logs = fs.readFileSync(config.LOG_FILE_PATH, 'utf8');
                signalResult = await analyzeLogsAndGenerateSignal(logs, config);
            }
        }
        manifestSignal(signalResult); 

    } catch (error) {
        log.error(`Oracle failed during final execution: ${error.message}`);
        log.error(`Check indicator inputs and network connectivity.`);
    }
}

executeOracle();
