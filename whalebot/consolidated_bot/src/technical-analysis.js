/**
 * 🌊 WHALEWAVE PRO – LEVIATHAN v3.6.2 "SINGULARITY PRIME" (FINAL BUILD)   │
 * │   Self-Contained · Unified Intelligence · Production Grade (v3.6.2)     │
 * └─────────────────────────────────────────────────────────────────────────┘
 *
 * USAGE: node leviathan-v3.6.2.cjs
 */

import fs from 'fs';
import path from 'path';
import dotenv from 'dotenv';
import { Decimal } from 'decimal.js';
import { GoogleGenerativeAI } from '@google/generative-ai';
import { RestClientV5, WebsocketClient } from 'bybit-api';
import winston from 'winston';
import Ajv from 'ajv';
import { fileURLToPath } from 'url'; // Needed for __dirname in ES modules

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// --- 0. CORE SETUP & CONFIGURATION ──────────────────────────────────────────

const VERSION = '3.6.2';

// Logger setup using Winston
const logger = winston.createLogger({
    level: process.env.LOG_LEVEL || 'info',
    format: winston.format.combine(
        winston.format.timestamp({ format: 'YYYY-MM-DD HH:mm:ss' }),
        winston.format.errors({ stack: true }),
        winston.format.splat(),
        winston.format.json(),
    ),
    defaultMeta: { service: 'leviathan-bot', version: VERSION },
    transports: [
        new winston.transports.File({ filename: 'error.log', level: 'error' }),
        new winston.transports.File({ filename: 'leviathan.log' }),
        new winston.transports.Console({
            format: winston.format.combine(winston.format.colorize({ all: true }), winston.format.simple()),
            level: 'info'
        }),
    ],
});
const successTransport = new winston.transports.Console({
    format: winston.format.combine(winston.format.colorize({ all: true }), winston.format.simple())
});
logger.add(successTransport);
winston.addColors({ success: 'green' });
logger.success = (msg) => logger.info(`✅ ${msg}`);

// Loads environment variables from .env file and validates required keys.
function loadEnvSafe() {
    if (fs.existsSync('.env')) Object.assign(process.env, dotenv.parse(fs.readFileSync('.env')));
    const REQUIRED_ENV = ['BYBIT_API_KEY', 'BYBIT_API_SECRET', 'GEMINI_API_KEY'];
    const missing = REQUIRED_ENV.filter(key => !process.env[key]);
    if (missing.length > 0) {
        logger.error(`[FATAL] Missing environment variables: ${missing.join(', ')}`);
        process.exit(1); // Exit if critical variables are missing
    }
}

// Loads configuration from config.json, merging with defaults. Creates default if missing.
function loadConfig() {
    const configPath = path.join(__dirname, 'config.json');
    let defaultConfig = {
        symbol: "BTCUSDT", 
        accountType: "UNIFIED", 
        testnet: process.env.TESTNET === 'true' || true, // Default to testnet true if TESTNET env var is not set
        intervals: { main: "5", scalping: "1" },
        risk: { 
            maxRiskPerTrade: 0.01, // Max risk per trade as fraction of equity
            leverage: 10, 
            rewardRatio: 1.5, // Minimum Risk/Reward ratio target
            trailingStopMultiplier: 2.0, // Multiplier for ATR to set trailing stops
            zombieTimeMs: 300000, // Time after which a position is considered zombie (stuck)
            zombiePnlTolerance: 0.0015, // PnL tolerance for zombie detection
            breakEvenTrigger: 1.0, // Trigger to move SL to BE when profit reaches this multiple of risk
            maxDailyLoss: 10, // Max daily loss %
            minOrderQty: 0.001, // Minimum order quantity
            maxOrderQty: 10.0, // Maximum order quantity
            partialTakeProfitPct: 0.5, // Percentage of position to take profit on
            fundingThreshold: 0.0005, // Funding rate threshold to consider for actions
            icebergOffset: 0.0001, // Offset for iceberg order slices
            fee: 0.0005, // Trading fee
            maxHoldingDuration: 7200000, // Max time a position can be held (in ms)
            kellyFraction: 0.25, // Fraction of Kelly Criterion to apply
            recoveryThreshold: 0.5, // Threshold to exit recovery mode
            atr_tp_limit: 3.5 // Max ATR multiple for TP (volatility clamping)
        },
        ai: { model: "gemini-1.5-pro", minConfidence: 0.85, useGemini: true }, // AI settings
        indicators: { atr: 14, fisher: 9 }, // Indicator periods
        health: { wsLatencyThreshold: 500, apiLatencyThreshold: 2000 } // Health check thresholds
    };
    
    if (fs.existsSync(configPath)) {
        const loaded = JSON.parse(fs.readFileSync(configPath, 'utf-8'));
        // Deep merge logic: prioritize loaded config, merge nested objects carefully
        // This simplified merge might not handle all edge cases but works for common structures.
        // A more robust deep merge function might be needed for complex configs.
        defaultConfig = { ...defaultConfig, ...loaded };
        // Ensure nested objects like risk, ai, indicators, etc., are also merged
        for (const key in loaded) {
            if (loaded[key] && typeof loaded[key] === 'object' && !Array.isArray(loaded[key])) {
                defaultConfig[key] = { ...defaultConfig[key], ...loaded[key] };
            }
        }
        // Specific merge for trading_params if it exists separately
        if (loaded.trading_params) {
            defaultConfig = { ...defaultConfig, ...loaded.trading_params };
        }
        
        // Validate after merging
        TA.validateConfig(defaultConfig); // Assuming TA class has a validateConfig method or similar logic
    } else {
        // Create default config file if it doesn't exist
        fs.writeFileSync(configPath, JSON.stringify(defaultConfig, null, 2));
        logger.warn(`Configuration file not found. Created default ${configPath}. Please review and customize.`);
    }
    
    // Set Decimal precision globally based on config
    Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });
    
    return defaultConfig;
}

loadEnvSafe(); // Load .env variables early
const CONFIG = loadConfig(); // Load configuration

// --- HELPERS & COLORS ---
const C = { // ANSI color codes for terminal output
    reset: "\x1b[0m", dim: "\x1b[2m", bright: "\x1b[1m",
    green: "\x1b[32m", red: "\x1b[31m", cyan: "\x1b[36m",
    yellow: "\x1b[33m", magenta: "\x1b[35m", neonGreen: "\x1b[92m",
    neonRed: "\x1b[91m", neonYellow: "\x1b[93m", neonPurple: "\x1b[95m"
};
// Decimal helpers
const D = (n) => new Decimal(n);
const D0 = () => new Decimal(0);

// --- GLOBAL VALIDATION SCHEMA ---
// Ajv schema for validating AI signal structure
const ajv = new Ajv({ allErrors: true });
const llmSignalSchema = {
    type: "object",
    properties: {
        action: { type: "string", enum: ["BUY", "SELL", "HOLD"] },
        confidence: { type: "number", minimum: 0, maximum: 1 },
        sl: { type: "number" }, 
        tp: { type: "number" },
        reason: { type: "string" }
    },
    required: ["action", "confidence"],
    additionalProperties: false // Disallow extra properties
};

// ─── 1. TECHNICAL ANALYSIS (TA) ──────────────────────────────────────────────
// Contains various technical indicator calculations using Decimal.js for precision.
class TA {
    static sma(src, len) { 
        const res = new Array(src.length).fill(D(0));
        if (src.length < len) return res;
        let sum = D(0);
        for (let i = 0; i < len; i++) sum = sum.plus(src[i]);
        res[len - 1] = sum.div(len);
        for (let i = len; i < src.length; i++) {
            sum = sum.plus(src[i]).minus(src[i - len]);
            res[i] = sum.div(len);
        }
        return res;
    }
    
    static atr(h, l, c, len) {
        const tr = new Array(h.length).fill(D(0));
        for (let i = 1; i < h.length; i++) {
            tr[i] = Decimal.max(h[i].minus(l[i]), h[i].minus(c[i - 1]).abs(), l[i].minus(c[i - 1]).abs());
        }
        return TA.sma(tr, len); // Wilder's Smoothing is implicitly SMA in this implementation based on previous context
    }
    
    static vwap(h, l, c, v) {
        if (!c.length) return D(0);
        let cumPV = D(0), cumV = D(0);
        // VWAP is typically calculated intraday; using last 288 candles as a proxy if daily data is provided
        const start = Math.max(0, c.length - 288); 
        for (let i = start; i < c.length; i++) {
            const tp = h[i].plus(l[i]).plus(c[i]).div(3); // Typical Price
            cumPV = cumPV.plus(tp.mul(v[i])); // Price * Volume
            cumV = cumV.plus(v[i]); // Cumulative Volume
        }
        return cumV.eq(0) ? c[c.length - 1] : cumPV.div(cumV); // Avoid division by zero
    }
    
    static fisher(h, l, len = 9) {
        const res = new Array(h.length).fill(D(0));
        const val = new Array(h.length).fill(D(0));
        if (h.length < len) return res;
        const EPSILON = D('1e-9'); // Small value to avoid division by zero or log(0)
        const MAX_RAW = D('0.999'); 
        const MIN_RAW = D('-0.999');

        for (let i = len; i < h.length; i++) {
            let maxH = h[i], minL = l[i]; // Initialize max/min with current candle data
            for (let j = 0; j < len; j++) { // Find max high and min low over the lookback period
                if (h[i - j].gt(maxH)) maxH = h[i - j];
                if (l[i - j].lt(minL)) minL = l[i - j];
            }
            const range = maxH.minus(minL); // Price range over the period
            let raw = D(0);
            if (range.gt(EPSILON)) { // Ensure range is not zero
                const hl2 = h[i].plus(l[i]).div(2); // (High + Low) / 2
                // Raw Fisher Transform calculation
                raw = hl2.minus(minL).div(range).minus(0.5).mul(2); 
            }
            const prevVal = val[i - 1] && val[i - 1].isFinite() ? val[i - 1] : D(0); // Previous raw value, default to 0
            raw = D('0.33').mul(raw).plus(D('0.67').mul(prevVal)); // Smoothing factor (0.33, 0.67)
            if (raw.gt(MAX_RAW)) raw = MAX_RAW; // Clamp raw value
            else if (raw.lt(MIN_RAW)) raw = MIN_RAW;
            val[i] = raw;

            try { // Calculate smoothed value (often called Fisher Transform)
                const v1 = D(1).plus(raw); 
                const v2 = D(1).minus(raw);
                if (v2.abs().lt(EPSILON) || v1.lte(0) || v2.lte(0)) { // Avoid log(0) or division by zero
                    res[i] = res[i - 1] || D(0); // Use previous result or default to 0
                } else {
                    const logVal = v1.div(v2).ln(); // Natural logarithm
                    const prevRes = res[i - 1] && res[i - 1].isFinite() ? res[i - 1] : D(0); // Previous smoothed value
                    res[i] = D('0.5').mul(logVal).plus(D('0.5').mul(prevRes)); // Smoothing for final result
                }
            } catch (e) { 
                res[i] = res[i - 1] || D(0); // Handle potential math errors
            }
        }
        return res;
    }
    
    static rsi(prices, period = 14) {
        let gains = [], losses = [];
        for (let i = 1; i < prices.length; i++) {
            const diff = prices[i].minus(prices[i - 1]);
            gains.push(diff.gt(0) ? diff : Decimal(0)); // Positive change is a gain
            losses.push(diff.lt(0) ? diff.abs() : Decimal(0)); // Negative change is a loss
        }
        const avgGains = TA.sma(gains, period); // Smoothed average gains
        const avgLosses = TA.sma(losses, period); // Smoothed average losses
        const rsi = [];
        for (let i = 0; i < avgGains.length; i++) {
            const avgG = avgGains[i] || Decimal('1e-9'); // Use small epsilon to avoid division by zero
            const avgL = avgLosses[i] || Decimal('1e-9');
            const rs = avgG.div(avgL); // Relative Strength (RS)
            // RSI formula: 100 - (100 / (1 + RS))
            rsi.push(Decimal(100).minus(Decimal(100).div(Decimal(1).plus(rs))));
        }
        return rsi;
    }

    // Static method to validate config values related to TA parameters
    static validateConfig(config) {
        // Example validation (add more as needed)
        if (config.indicators.atr_period <= 0) {
            throw new Error("ATR period must be positive.");
        }
        // Add more checks for other indicator parameters if necessary
    }
}
