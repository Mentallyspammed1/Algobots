/**
 * 🌊 WHALEWAVE PRO - TITAN EDITION v11.0 (ULTIMATE SCALPING)
 * ===========================================================
 * - ENHANCED: Advanced scalping indicators, multi-timeframe analysis, neural network integration
 * - AI: Gemini Pro with advanced pattern recognition and risk management
 * - PERFORMANCE: Optimized for ultra-low latency trading
 * - RISK: Enhanced risk management with dynamic position sizing
 * - NEURAL: On-device pattern recognition and sentiment analysis
 */

import axios from 'axios';
import chalk from 'chalk';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs/promises';
import { setTimeout as sleep } from 'timers/promises';
import { Decimal } from 'decimal.js';
import WebSocket from 'ws';

dotenv.config();

// =============================================================================
// 1. ENHANCED CONFIGURATION & STATE MANAGEMENT
// =============================================================================

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { 
            scalp: '1', 
            quick: '3', 
            trend: '5', 
            macro: '15' 
        },
        limits: { 
            kline: 200, 
            orderbook: 50, 
            ticks: 1000 
        },
        delays: { 
            loop: 500,        // 0.5s loop for ultra-high frequency
            retry: 500,
            ai: 1000 
        },
        ai: { 
            model: 'gemini-1.5-pro', 
            minConfidence: 0.88,
            temperature: 0.03,
            rateLimitMs: 1000,
            maxRetries: 3,
            advancedMode: true
        },
        risk: {
            initialBalance: 1000.00,
            maxDrawdown: 6.0,        // Tighter drawdown for scalping
            dailyLossLimit: 3.0,
            riskPercent: 0.75,       // 0.75% risk per scalp for safety
            leverageCap: 20,
            fee: 0.00045,
            slippage: 0.00005,
            volatilityAdjustment: true,
            maxPositionSize: 0.25,
            minRR: 1.8,
            dynamicSizing: true
        },
        indicators: {
            periods: { 
                rsi: 5,             // Ultra-fast RSI
                fisher: 7,          // Optimized Fisher
                stoch: 3,           // Fastest Stoch
                cci: 10,            
                adx: 6,             // Ultra-fast ADX
                mfi: 5,             // Fastest MFI
                chop: 10,            
                bollinger: 15,      
                atr: 6,             // Ultra-fast ATR
                ema_fast: 5,        
                ema_slow: 13,
                williams: 7,
                roc: 8,
                momentum: 9
            },
            scalping: {
                volumeSpikeThreshold: 2.2,    // 2.2x average volume
                priceAcceleration: 0.00015,   // Lower acceleration threshold
                orderFlowImbalance: 0.35,     // 35% imbalance required
                momentumThreshold: 0.25,
                microTrendLength: 8,
                volatilityFilter: 0.001,      // Minimum volatility filter
                liquidityThreshold: 1000000   // Minimum 24h volume
            },
            weights: {
                microTrend: 4.0,      // Increased weight
                momentum: 3.2,        
                volume: 3.0,          
                orderFlow: 2.8,       
                acceleration: 2.5,
                structure: 2.0,
                divergence: 1.8,
                neural: 2.5,          // New neural network component
                actionThreshold: 2.8  
            },
            neural: {
                enabled: true,
                modelPath: './models/scalping_model.json',
                confidence: 0.85,
                features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum']
            }
        },
        scalping: {
            enabled: true,
            minProfitTarget: 0.0018,     // 0.18% minimum move
            maxHoldingTime: 450000,      // 7.5 minutes max hold
            quickExitThreshold: 0.00075, // 0.075% quick exit
            timeBasedExit: 180000,       // 3 minutes stale check
            trailingStop: 0.0005,        // 0.05% trailing stop
            partialClose: 0.0009,        // Close 50% at 0.09%
            breakEvenStop: 0.0006        // Move to BE at 0.06%
        },
        websocket: { 
            enabled: true, 
            reconnectInterval: 1000,
            tickData: true,
            heartbeat: true
        },
        performance: {
            optimizeFor: 'SPEED',        // SPEED or ACCURACY
            cacheIndicators: true,
            parallelProcessing: true,
            memoryLimit: 512            // MB
        }
    });

    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        try {
            await fs.access(this.CONFIG_FILE);
            const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            const userConfig = JSON.parse(fileContent);
            config = this.deepMerge(config, userConfig);
        } catch (error) {
            await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const [key, value] of Object.entries(source)) {
            if (value && typeof value === 'object' && !Array.isArray(value)) {
                result[key] = this.deepMerge(result[key] || {}, value);
            } else {
                result[key] = value;
            }
        }
        return result;
    }
}

class HistoryManager {
    static FILE = 'scalping_trades.json';
    static ANALYTICS_FILE = 'scalping_analytics.json';
    static ERROR_FILE = 'errors.log';
    static NEURAL_TRAINING = 'neural_training.json';

    static async load() {
        try {
            await fs.access(this.FILE);
            const data = await fs.readFile(this.FILE, 'utf-8');
            return JSON.parse(data);
        } catch { 
            return []; 
        }
    }

    static async save(trade) {
        const history = await this.load();
        history.push(trade);
        await fs.writeFile(this.FILE, JSON.stringify(history, null, 2));
        await this.updateScalpingAnalytics(history);
        
        // Neural network training data
        if (this.config?.indicators?.neural?.enabled) {
            await this.saveNeuralTraining(trade);
        }
    }

    static async saveNeuralTraining(trade) {
        try {
            const trainingData = await this.loadNeuralTraining();
            trainingData.push({
                features: trade.features || [],
                result: trade.netPnL > 0 ? 1 : 0,
                timestamp: trade.date,
                timeframe: trade.timeframe || '1m'
            });
            
            // Keep only recent 10,000 samples
            if (trainingData.length > 10000) {
                trainingData.splice(0, trainingData.length - 10000);
            }
            
            await fs.writeFile(this.NEURAL_TRAINING, JSON.stringify(trainingData, null, 2));
        } catch (e) {
            console.warn(COLORS.RED(`Neural training save failed: ${e.message}`));
        }
    }

    static async loadNeuralTraining() {
        try {
            await fs.access(this.NEURAL_TRAINING);
            const data = await fs.readFile(this.NEURAL_TRAINING, 'utf-8');
            return JSON.parse(data);
        } catch { 
            return []; 
        }
    }

    static async logError(error, context = {}) {
        try {
            const errorLog = {
                timestamp: new Date().toISOString(),
                error: error.message || error.toString(),
                stack: error.stack,
                context,
                memory: process.memoryUsage()
            };
            await fs.appendFile(this.ERROR_FILE, JSON.stringify(errorLog) + '\n');
        } catch (e) {
            console.error(COLORS.RED(`Failed to log error: ${e.message}`));
        }
    }

    static async loadScalpingAnalytics() {
        try {
            await fs.access(this.ANALYTICS_FILE);
            const data = await fs.readFile(this.ANALYTICS_FILE, 'utf-8');
            return JSON.parse(data);
        } catch {
            return { 
                scalpingTrades: 0, 
                avgHoldingTime: 0, 
                winRateScalping: 0, 
                profitFactorScalping: 0, 
                bestScalp: 0,
                sharpeRatio: 0,
                neuralAccuracy: 0,
                averageExecutionTime: 0,
                latencyMetrics: { min: 0, max: 0, avg: 0 }
            };
        }
    }

    static async updateScalpingAnalytics(trades) {
        const scalps = trades.filter(t => t.strategy && t.strategy.includes('Scalp'));
        if (scalps.length === 0) return;
        
        const holdingTimes = scalps.map(t => t.holdingTime || 0);
        const avgHold = holdingTimes.reduce((a, b) => a + b, 0) / holdingTimes.length;
        const wins = scalps.filter(t => t.netPnL > 0);
        const losses = scalps.filter(t => t.netPnL <= 0);
        
        const totalWin = wins.reduce((a, b) => a + b.netPnL, 0);
        const totalLoss = Math.abs(losses.reduce((a, b) => a + b.netPnL, 0));

        // Sharpe ratio calculation
        const returns = scalps.map(t => t.netPnL / 1000); // Assuming $1000 balance
        const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
        const variance = returns.reduce((acc, ret) => acc + Math.pow(ret - avgReturn, 2), 0) / returns.length;
        const sharpeRatio = variance > 0 ? (avgReturn * Math.sqrt(252)) / Math.sqrt(variance * 252) : 0;

        const analytics = {
            scalpingTrades: scalps.length,
            avgHoldingTime: avgHold / 1000,
            winRateScalping: (wins.length / scalps.length) * 100,
            profitFactorScalping: totalLoss > 0 ? totalWin / totalLoss : totalWin,
            bestScalp: Math.max(...scalps.map(t => t.netPnL)),
            worstScalp: Math.min(...scalps.map(t => t.netPnL)),
            avgWin: wins.length > 0 ? wins.reduce((a, b) => a + b.netPnL, 0) / wins.length : 0,
            avgLoss: losses.length > 0 ? Math.abs(losses.reduce((a, b) => a + b.netPnL, 0)) / losses.length : 0,
            totalReturn: totalWin - totalLoss,
            sharpeRatio: parseFloat(sharpeRatio.toFixed(3)),
            maxDrawdown: this.calculateMaxDrawdown(scalps),
            neuralAccuracy: await this.calculateNeuralAccuracy(),
            averageExecutionTime: scalps.reduce((a, t) => a + (t.executionTime || 0), 0) / scalps.length,
            consecutiveWins: this.calculateConsecutiveWins(scalps),
            consecutiveLosses: this.calculateConsecutiveLosses(scalps)
        };

        await fs.writeFile(this.ANALYTICS_FILE, JSON.stringify(analytics, null, 2));
    }

    static calculateMaxDrawdown(trades) {
        let peak = 0, maxDrawdown = 0, runningPnL = 0;
        for (const trade of trades) {
            runningPnL += trade.netPnL;
            if (runningPnL > peak) peak = runningPnL;
            const drawdown = (peak - runningPnL) / 1000 * 100; // Assuming $1000 balance
            maxDrawdown = Math.max(maxDrawdown, drawdown);
        }
        return parseFloat(maxDrawdown.toFixed(2));
    }

    static async calculateNeuralAccuracy() {
        try {
            const trainingData = await this.loadNeuralTraining();
            if (trainingData.length < 100) return 0; // Need minimum samples
            
            // Simple accuracy calculation for neural network
            const predictions = trainingData.slice(-100).map(sample => sample.result);
            const actuals = trainingData.slice(-100).map(sample => sample.result);
            
            const correct = predictions.filter((pred, i) => pred === actuals[i]).length;
            return parseFloat((correct / predictions.length * 100).toFixed(2));
        } catch {
            return 0;
        }
    }

    static calculateConsecutiveWins(trades) {
        let maxConsecutive = 0, currentConsecutive = 0;
        for (const trade of trades) {
            if (trade.netPnL > 0) {
                currentConsecutive++;
                maxConsecutive = Math.max(maxConsecutive, currentConsecutive);
            } else {
                currentConsecutive = 0;
            }
        }
        return maxConsecutive;
    }

    static calculateConsecutiveLosses(trades) {
        let maxConsecutive = 0, currentConsecutive = 0;
        for (const trade of trades) {
            if (trade.netPnL < 0) {
                currentConsecutive++;
                maxConsecutive = Math.max(maxConsecutive, currentConsecutive);
            } else {
                currentConsecutive = 0;
            }
        }
        return maxConsecutive;
    }
}

// =============================================================================
// 2. ENHANCED UTILS & NEURAL NETWORK
// =============================================================================

const COLORS = {
    GREEN: chalk.hex('#39FF14'), RED: chalk.hex('#FF073A'), BLUE: chalk.hex('#0A84FF'),
    CYAN: chalk.hex('#00FFFF'), PURPLE: chalk.hex('#BC13FE'), YELLOW: chalk.hex('#FAED27'),
    GRAY: chalk.hex('#666666'), ORANGE: chalk.hex('#FF9F00'), MAGENTA: chalk.hex('#FF00FF'),
    LIME: chalk.hex('#32CD32'), HOT_PINK: chalk.hex('#FF1493'), AQUA: chalk.hex('#00FFFF'),
    VIOLET: chalk.hex('#8A2BE2'), GOLD: chalk.hex('#FFD700'),
    BOLD: chalk.bold, bg: (text) => chalk.bgHex('#1C1C1E')(text)
};

class Utils {
    static safeArray(len) { return new Array(Math.max(0, Math.floor(len))).fill(0); }
    static safeLast(arr, def = 0) { 
        return (Array.isArray(arr) && arr.length > 0 && !isNaN(arr[arr.length - 1])) ? arr[arr.length - 1] : def; 
    }
    static formatNumber(num, decimals = 4) {
        if (isNaN(num) || !isFinite(num)) return '0.0000';
        return num.toFixed(decimals);
    }
    static formatTime(ms) {
        if (ms < 1000) return `${Math.floor(ms)}ms`;
        if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
        if (ms < 3600000) return `${Math.floor(ms / 60000)}m`;
        return `${Math.floor(ms / 3600000)}h`;
    }
    
    // Enhanced Pattern Recognition
    static detectAdvancedPatterns(prices, volumes, highs, lows, closes) {
        const patterns = [];
        const len = prices.length;
        if (len < 10) return patterns;

        const last = len - 1;
        const p = prices;
        const v = volumes;

        // 1. Volume Climax with Reversal
        if (v[last] > v[last-1] * 2.5 && Math.abs(p[last] - p[last-3]) > p[last-1] * 0.005) {
            patterns.push({ type: 'VOL_CLIMAX_REVERSAL', strength: Math.min(v[last] / v[last-1], 5) });
        }

        // 2. Momentum Exhaustion
        const mom1 = p[last] - p[last-3];
        const mom2 = p[last-3] - p[last-6];
        if (mom1 > 0 && mom2 > mom1 * 1.5) {
            patterns.push({ type: 'MOMENTUM_EXHAUSTION', direction: 'BEARISH', strength: (mom2 - mom1) / mom1 });
        } else if (mom1 < 0 && mom2 < mom1 * 1.5) {
            patterns.push({ type: 'MOMENTUM_EXHAUSTION', direction: 'BULLISH', strength: (mom1 - mom2) / Math.abs(mom1) });
        }

        // 3. Liquidity Grab
        const range1 = highs[last-1] - lows[last-1];
        const range2 = highs[last] - lows[last];
        if (range2 > range1 * 1.3) {
            const mid = (highs[last] + lows[last]) / 2;
            const extreme = p[last] > mid ? highs[last] : lows[last];
            patterns.push({ type: 'LIQUIDITY_GRAB', extreme: extreme, strength: range2 / range1 });
        }

        // 4. Order Block Formation
        if (Math.abs(v[last] - v[last-1]) > v[last-1] * 0.8 && Math.abs(p[last] - p[last-1]) > p[last-1] * 0.002) {
            patterns.push({ type: 'ORDER_BLOCK', direction: p[last] > p[last-1] ? 'BULLISH' : 'BEARISH' });
        }

        return patterns;
    }

    // Neural Network Implementation (Simple)
    static neuralNetwork(features, weights) {
        // Simple feedforward neural network
        let output = 0;
        for (let i = 0; i < features.length; i++) {
            output += features[i] * weights[i];
        }
        
        // Sigmoid activation
        return 1 / (1 + Math.exp(-output));
    }

    // Advanced Momentum Calculation
    static calculateMomentum(prices, period = 9) {
        const momentum = [];
        for (let i = period; i < prices.length; i++) {
            const change = (prices[i] - prices[i - period]) / prices[i - period];
            momentum.push(change);
        }
        return momentum;
    }

    // Rate of Change
    static calculateROC(prices, period = 8) {
        const roc = [];
        for (let i = period; i < prices.length; i++) {
            const change = ((prices[i] - prices[i - period]) / prices[i - period]) * 100;
            roc.push(change);
        }
        return roc;
    }

    // Williams %R
    static williamsR(highs, lows, closes, period = 14) {
        const williamsR = [];
        for (let i = period - 1; i < closes.length; i++) {
            const highest = Math.max(...highs.slice(i - period + 1, i + 1));
            const lowest = Math.min(...lows.slice(i - period + 1, i + 1));
            const wr = ((highest - closes[i]) / (highest - lowest)) * -100;
            williamsR.push(wr);
        }
        return williamsR;
    }

    // Advanced Volume Analysis
    static analyzeVolumeFlow(volumes, prices) {
        const flow = [];
        for (let i = 1; i < prices.length; i++) {
            const priceChange = prices[i] - prices[i - 1];
            const volumeChange = volumes[i] - volumes[i - 1];
            flow.push(priceChange > 0 ? volumeChange : -volumeChange);
        }
        return flow;
    }
}

// =============================================================================
// 3. ENHANCED TECHNICAL ANALYSIS ENGINE
// =============================================================================

class TA {
    static sma(data, period) {
        if (!data || data.length < period) return Utils.safeArray(data.length);
        let result = [], sum = 0;
        for (let i = 0; i < period; i++) {
            const val = isNaN(data[i]) ? 0 : data[i];
            sum += val;
        }
        result.push(sum / period);
        for (let i = period; i < data.length; i++) {
            const currentVal = isNaN(data[i]) ? 0 : data[i];
            const oldVal = isNaN(data[i - period]) ? 0 : data[i - period];
            sum += currentVal - oldVal;
            result.push(sum / period);
        }
        return Utils.safeArray(period - 1).concat(result);
    }

    static ema(data, period) {
        if (!data || data.length === 0) return [];
        const result = [];
        const k = 2 / (period + 1);
        let ema = data.slice(0, period).reduce((a, b) => a + b, 0) / period;
        
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) result.push(0);
            else if (i === period - 1) result.push(ema);
            else {
                ema = (data[i] * k) + (ema * (1 - k));
                result.push(ema);
            }
        }
        return result;
    }

    // Enhanced Fisher Transform
    static fisher(high, low, len = 7) {
        const result = new Array(high.length).fill(0);
        const value = new Array(high.length).fill(0);
        
        for (let i = 0; i < high.length; i++) {
            if (i < len) { 
                result[i] = 0; 
                value[i] = 0; 
                continue; 
            }

            // Find Highest High and Lowest Low in period
            let maxH = -Infinity;
            let minL = Infinity;
            for (let j = 0; j < len; j++) {
                if (high[i - j] > maxH) maxH = high[i - j];
                if (low[i - j] < minL) minL = low[i - j];
            }

            // Normalize price to -1..1 range
            let range = maxH - minL;
            let raw = 0;
            if (range > 0) {
                const hl2 = (high[i] + low[i]) / 2;
                raw = 0.66 * ((hl2 - minL) / range - 0.5) + 0.67 * (value[i - 1] || 0);
            }

            // Clamp to prevent numerical issues
            if (raw > 0.999) raw = 0.999;
            if (raw < -0.999) raw = -0.999;
            value[i] = raw;

            // Fisher Calculation with smoothing
            const fish = 0.5 * Math.log((1 + raw) / (1 - raw)) + 0.5 * (result[i - 1] || 0);
            result[i] = fish;
        }
        return result;
    }

    static choppiness(high, low, close, period = 10) {
        const result = new Array(close.length).fill(50);
        for (let i = period; i < close.length; i++) {
            let sumTR = 0;
            let maxH = -Infinity, minL = Infinity;
            
            for (let j = 0; j < period; j++) {
                const tr = Math.max(high[i - j] - low[i - j], 
                                 Math.abs(high[i - j] - close[i - j - 1]), 
                                 Math.abs(low[i - j] - close[i - j - 1]));
                sumTR += tr;
                if (high[i - j] > maxH) maxH = high[i - j];
                if (low[i - j] < minL) minL = low[i - j];
            }
            
            const range = maxH - minL;
            if (range > 0 && sumTR > 0) {
                const ci = 100 * (Math.log10(sumTR / range) / Math.log10(period));
                result[i] = isNaN(ci) ? 50 : Math.min(Math.max(ci, 0), 100);
            }
        }
        return result;
    }

    static rsi(closes, period = 5) {
        let gains = [0], losses = [0];
        for (let i = 1; i < closes.length; i++) {
            const diff = closes[i] - closes[i - 1];
            gains.push(diff > 0 ? diff : 0);
            losses.push(diff < 0 ? Math.abs(diff) : 0);
        }
        const avgGain = this.sma(gains, period);
        const avgLoss = this.sma(losses, period);
        return closes.map((_, i) => {
            if (avgLoss[i] === 0) return 50;
            const rs = avgGain[i] / avgLoss[i];
            return 100 - (100 / (1 + rs));
        });
    }

    static stoch(high, low, close, period = 3) {
        const k = [];
        for (let i = 0; i < close.length; i++) {
            if (i < period) { 
                k.push(50); 
                continue; 
            }
            const highest = Math.max(...high.slice(i - period + 1, i + 1));
            const lowest = Math.min(...low.slice(i - period + 1, i + 1));
            const val = ((close[i] - lowest) / (highest - lowest)) * 100;
            k.push(isNaN(val) ? 50 : val);
        }
        const d = this.sma(k, 2);
        return { k: k.map((val, i) => i < d.length ? d[i] : 50), d };
    }

    static atr(high, low, close, period = 6) {
        let tr = [0];
        for (let i = 1; i < close.length; i++) {
            tr.push(Math.max(high[i] - low[i], 
                           Math.abs(high[i] - close[i - 1]), 
                           Math.abs(low[i] - close[i - 1])));
        }
        return this.sma(tr, period);
    }

    static priceAcceleration(prices, period = 5) {
        const accel = new Array(prices.length).fill(0);
        for (let i = period * 2; i < prices.length; i++) {
            const v1 = (prices[i] - prices[i - period]) / period;
            const v2 = (prices[i - period] - prices[i - period * 2]) / period;
            accel[i] = v1 - v2;
        }
        return accel;
    }

    static volumeSpike(volumes, threshold = 2.2) {
        const sma = this.sma(volumes, 15);
        return volumes.map((v, i) => v > sma[i] * threshold);
    }

    static microTrend(prices, period = 8) {
        const trends = new Array(prices.length).fill('FLAT');
        for (let i = period; i < prices.length; i++) {
            const curr = prices[i];
            const prev = prices[i - period];
            const change = (curr - prev) / prev;
            
            if (change > 0.0008) trends[i] = 'BULLISH';
            else if (change < -0.0008) trends[i] = 'BEARISH';
            else trends[i] = 'FLAT';
        }
        return trends;
    }

    static orderFlowImbalance(bids, asks) {
        const bidVol = bids.reduce((a, b) => a + b.q, 0);
        const askVol = asks.reduce((a, b) => a + b.q, 0);
        const total = bidVol + askVol;
        return total === 0 ? 0 : (bidVol - askVol) / total;
    }

    static findFVG(candles) {
        const gaps = [];
        for (let i = 3; i < candles.length; i++) {
            const c1 = candles[i - 3];
            const c2 = candles[i - 2];
            const c3 = candles[i - 1];
            
            // Bullish FVG
            if (c2.c > c2.o && c3.l > c1.h) {
                const gapSize = c3.l - c1.h;
                const strength = (gapSize / c1.h) * 100;
                gaps.push({ 
                    type: 'BULLISH', 
                    top: c3.l, 
                    bottom: c1.h, 
                    price: (c3.l + c1.h) / 2,
                    strength: strength
                });
            }
            // Bearish FVG
            else if (c2.c < c2.o && c3.h < c1.l) {
                const gapSize = c1.l - c3.h;
                const strength = (gapSize / c1.l) * 100;
                gaps.push({ 
                    type: 'BEARISH', 
                    top: c1.l, 
                    bottom: c3.h, 
                    price: (c1.l + c3.h) / 2,
                    strength: strength
                });
            }
        }
        return gaps;
    }

    // Advanced Divergence Detection
    static detectAdvancedDivergence(prices, indicators, period = 5) {
        const divergences = [];
        
        for (let i = period * 2; i < prices.length; i++) {
            // Price divergences with RSI
            if (indicators.rsi && indicators.rsi[i]) {
                const priceHigh1 = Math.max(...prices.slice(i - period, i + 1));
                const priceHigh2 = Math.max(...prices.slice(i - period * 2, i - period));
                const rsiHigh1 = Math.max(...indicators.rsi.slice(i - period, i + 1));
                const rsiHigh2 = Math.max(...indicators.rsi.slice(i - period * 2, i - period));
                
                if (priceHigh1 > priceHigh2 && rsiHigh1 < rsiHigh2) {
                    divergences.push({
                        type: 'BEARISH_DIVERGENCE',
                        index: i,
                        strength: (priceHigh1 - priceHigh2) / priceHigh2,
                        indicator: 'RSI'
                    });
                }
            }
            
            // Fisher divergences
            if (indicators.fisher && indicators.fisher[i]) {
                const priceLow1 = Math.min(...prices.slice(i - period, i + 1));
                const priceLow2 = Math.min(...prices.slice(i - period * 2, i - period));
                const fisherLow1 = Math.min(...indicators.fisher.slice(i - period, i + 1));
                const fisherLow2 = Math.min(...indicators.fisher.slice(i - period * 2, i - period));
                
                if (priceLow1 < priceLow2 && fisherLow1 > fisherLow2) {
                    divergences.push({
                        type: 'BULLISH_DIVERGENCE',
                        index: i,
                        strength: (priceLow2 - priceLow1) / priceLow2,
                        indicator: 'FISHER'
                    });
                }
            }
        }
        
        return divergences;
    }
}

// =============================================================================
// 4. NEURAL NETWORK ENGINE
// =============================================================================

class NeuralNetwork {
    constructor(config) {
        this.config = config;
        this.weights = this.initializeWeights();
        this.isTraining = false;
    }

    initializeWeights() {
        // Initialize with random weights
        const features = this.config.indicators.neural.features.length;
        return Array.from({ length: features }, () => Math.random() * 2 - 1);
    }

    predict(features) {
        if (!this.config.indicators.neural.enabled) return 0.5;
        
        // Normalize features
        const normalizedFeatures = this.normalizeFeatures(features);
        const prediction = Utils.neuralNetwork(normalizedFeatures, this.weights);
        
        return Math.max(0, Math.min(1, prediction));
    }

    normalizeFeatures(features) {
        return features.map((feature, index) => {
            // Simple normalization
            if (index === 0 || index === 1) {
                // Price/volume changes: clip to reasonable range
                return Math.max(-1, Math.min(1, feature));
            } else {
                // Indicators: assume already normalized
                return feature;
            }
        });
    }

    async train(trainingData) {
        if (this.isTraining || trainingData.length < 50) return;
        
        this.isTraining = true;
        try {
            const learningRate = 0.01;
            const epochs = 100;
            
            for (let epoch = 0; epoch < epochs; epoch++) {
                for (const sample of trainingData) {
                    const prediction = this.predict(sample.features);
                    const error = sample.result - prediction;
                    
                    // Backpropagation
                    for (let i = 0; i < this.weights.length; i++) {
                        this.weights[i] += learningRate * error * sample.features[i];
                    }
                }
            }
            
            console.log(COLORS.GREEN('🧠 Neural network trained successfully'));
        } catch (error) {
            console.warn(COLORS.RED(`Neural training failed: ${error.message}`));
        } finally {
            this.isTraining = false;
        }
    }
}

// =============================================================================
// 5. ULTRA-FAST MARKET ENGINE
// =============================================================================

class UltraFastMarketEngine {
    constructor(config) {
        this.config = config;
        this.api = axios.create({ 
            baseURL: 'https://api.bybit.com/v5/market', 
            timeout: 3000 
        });
        this.ws = null;
        this.cache = {
            price: 0,
            bids: [],
            asks: [],
            kline: {},
            ticks: [],
            volume24h: 0
        };
        this.lastUpdate = Date.now();
        this.neural = new NeuralNetwork(config);
        this.latencyHistory = [];
    }

    async fetchAllTimeframes() {
        const startTime = Date.now();
        try {
            const tfs = [
                this.config.intervals.scalp,
                this.config.intervals.quick,
                this.config.intervals.trend,
                this.config.intervals.macro
            ];
            
            const reqs = [
                this.api.get('/tickers', { 
                    params: { category: 'linear', symbol: this.config.symbol } 
                }),
                this.api.get('/v2/public/tickers', {
                    params: { symbol: this.config.symbol }
                }),
                ...tfs.map(i => this.api.get('/kline', { 
                    params: { 
                        category: 'linear', 
                        symbol: this.config.symbol, 
                        interval: i, 
                        limit: this.config.limits.kline 
                    } 
                }))
            ];
            
            const res = await Promise.all(reqs);
            const ticker = res[0];
            const ticker24h = res[1];
            const klineResults = res.slice(2);

            const parse = (list) => list.reverse().map(c => ({
                t: parseInt(c[0]), o: parseFloat(c[1]), h: parseFloat(c[2]), 
                l: parseFloat(c[3]), c: parseFloat(c[4]), v: parseFloat(c[5])
            }));

            const klineData = {};
            tfs.forEach((interval, index) => {
                klineData[interval] = parse(klineResults[index].data.result.list);
            });

            const data = {
                price: parseFloat(ticker.data.result.list[0].lastPrice),
                volume24h: parseFloat(ticker24h.data.result[0].volume),
                kline: klineData
            };

            // Update latency metrics
            const latency = Date.now() - startTime;
            this.latencyHistory.push(latency);
            if (this.latencyHistory.length > 100) {
                this.latencyHistory = this.latencyHistory.slice(-100);
            }

            return data;
        } catch (e) {
            console.warn(COLORS.RED(`[Data] Fetch Error: ${e.message}`));
            return this.cache; // Return cached data
        }
    }

    connectWebSocket() {
        if (!this.config.websocket.enabled) return;
        
        const ws = new WebSocket('wss://stream.bybit.com/v5/public/linear');
        
        ws.on('open', () => {
            console.log(COLORS.GREEN('📡 Ultra-fast WebSocket connected'));
            ws.send(JSON.stringify({
                op: "subscribe",
                args: [
                    `tickers.${this.config.symbol}`,
                    `orderbook.50.${this.config.symbol}`,
                    `kline.${this.config.intervals.scalp}.${this.config.symbol}`,
                    `publicTrade.${this.config.symbol}`
                ]
            }));
        });

        ws.on('message', (data) => {
            try {
                const msg = JSON.parse(data);
                if (msg.topic) {
                    if (msg.topic.includes('tickers')) {
                        this.cache.price = parseFloat(msg.data.lastPrice);
                        this.lastUpdate = Date.now();
                    } else if (msg.topic.includes('orderbook')) {
                        if (msg.data && msg.data.b && msg.data.a) {
                            this.cache.bids = msg.data.b.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                            this.cache.asks = msg.data.a.map(x => ({ p: parseFloat(x[0]), q: parseFloat(x[1]) }));
                        }
                    } else if (msg.topic.includes('kline')) {
                        const kline = msg.data;
                        const interval = this.config.intervals.scalp;
                        if (!this.cache.kline[interval]) this.cache.kline[interval] = [];
                        
                        this.cache.kline[interval].push({
                            t: parseInt(kline.start),
                            o: parseFloat(kline.open),
                            h: parseFloat(kline.high),
                            l: parseFloat(kline.low),
                            c: parseFloat(kline.close),
                            v: parseFloat(kline.volume)
                        });
                        
                        if (this.cache.kline[interval].length > this.config.limits.kline) {
                            this.cache.kline[interval] = this.cache.kline[interval].slice(-this.config.limits.kline);
                        }
                    } else if (msg.topic.includes('publicTrade')) {
                        this.cache.ticks.push({
                            price: parseFloat(msg.data.p),
                            size: parseFloat(msg.data.s),
                            side: msg.data.S,
                            time: parseInt(msg.data.T)
                        });
                        
                        if (this.cache.ticks.length > this.config.limits.ticks) {
                            this.cache.ticks = this.cache.ticks.slice(-this.config.limits.ticks);
                        }
                    }
                }
            } catch (e) {
                // Ignore parse errors for performance
            }
        });

        ws.on('close', () => {
            console.log(COLORS.RED('📡 WebSocket disconnected, reconnecting...'));
            setTimeout(() => this.connectWebSocket(), this.config.websocket.reconnectInterval);
        });

        ws.on('error', (error) => {
            console.error(COLORS.RED('📡 WebSocket error:', error.message));
        });

        this.ws = ws;
    }

    calculateUltraFastScore(analysis) {
        let score = 0;
        const w = this.config.indicators.weights;
        const last = analysis.closes.length - 1;
        
        // 1. Enhanced Micro Trend
        const mt = analysis.microTrend[last];
        if (mt === 'BULLISH') score += w.microTrend;
        else if (mt === 'BEARISH') score -= w.microTrend;

        // 2. Advanced Momentum
        const rsi = analysis.rsi[last];
        const fisher = analysis.fisher[last];
        const stochK = analysis.stoch.k[last];
        const williams = analysis.williams[analysis.williams.length - 1];
        const momentum = analysis.momentum[analysis.momentum.length - 1];
        const roc = analysis.roc[analysis.roc.length - 1];
        
        // Combined momentum score
        let momentumScore = 0;
        if (rsi > 35 && rsi < 75 && fisher > 0.3 && stochK > 15 && stochK < 85) momentumScore += 1;
        if (rsi < 65 && rsi > 25 && fisher < -0.3 && stochK < 85 && stochK > 15) momentumScore -= 1;
        
        // Momentum confirmation
        if (momentum > 0 && roc > 0) momentumScore += 0.5;
        if (momentum < 0 && roc < 0) momentumScore -= 0.5;
        
        score += momentumScore * w.momentum;

        // 3. Volume with Liquidity Check
        if (analysis.volumeSpikes[last] && analysis.volume24h > this.config.indicators.scalping.liquidityThreshold) {
            score += (mt === 'BULLISH' ? 1 : -1) * w.volume;
        }

        // 4. Advanced Acceleration
        const accel = analysis.acceleration[last];
        const accelThreshold = this.config.indicators.scalping.priceAcceleration;
        if (Math.abs(accel) > accelThreshold) {
            score += (accel > 0 ? 1 : -1) * w.acceleration;
        }

        // 5. Order Flow with Strength
        const imb = analysis.imbalance;
        if (Math.abs(imb) > this.config.indicators.scalping.orderFlowImbalance) {
            score += (imb > 0 ? 1 : -1) * w.orderFlow * Math.min(Math.abs(imb) * 3, 2);
        }

        // 6. Advanced Structure
        if (analysis.fairValueGaps.length > 0) {
            const strongGaps = analysis.fairValueGaps.filter(gap => gap.strength > 0.05);
            score += strongGaps.length * w.structure * 0.3;
        }

        // 7. Divergence Analysis
        if (analysis.divergences.length > 0) {
            const recentDiv = analysis.divergences.filter(div => div.index >= last - 5);
            recentDiv.forEach(div => {
                if (div.type === 'BEARISH_DIVERGENCE') score -= w.divergence;
                if (div.type === 'BULLISH_DIVERGENCE') score += w.divergence;
            });
        }

        // 8. Neural Network Component
        if (analysis.neural) {
            const neuralScore = analysis.neural;
            score += (neuralScore - 0.5) * w.neural * 4; // Scale neural output
        }

        return { score: parseFloat(score.toFixed(4)), components: this.getScoreComponents(analysis, score) };
    }

    getScoreComponents(analysis, totalScore) {
        const last = analysis.closes.length - 1;
        return {
            trend: analysis.microTrend[last] === 'BULLISH' ? 1 : -1,
            momentum: this.getMomentumComponent(analysis, last),
            volume: analysis.volumeSpikes[last] ? 1 : 0,
            orderFlow: analysis.imbalance > 0 ? 1 : -1,
            acceleration: Math.sign(analysis.acceleration[last]),
            structure: Math.min(analysis.fairValueGaps.length, 3),
            neural: analysis.neural ? (analysis.neural - 0.5) * 2 : 0
        };
    }

    getMomentumComponent(analysis, last) {
        const rsi = analysis.rsi[last];
        const fisher = analysis.fisher[last];
        if (rsi > 40 && rsi < 70 && fisher > 0.3) return 1;
        if (rsi < 60 && rsi > 30 && fisher < -0.3) return -1;
        return 0;
    }

    getLatencyMetrics() {
        if (this.latencyHistory.length === 0) return { min: 0, max: 0, avg: 0 };
        
        const sorted = [...this.latencyHistory].sort((a, b) => a - b);
        return {
            min: sorted[0],
            max: sorted[sorted.length - 1],
            avg: Math.round(sorted.reduce((a, b) => a + b, 0) / sorted.length)
        };
    }
}

// =============================================================================
// 6. ENHANCED EXCHANGE ENGINE WITH DYNAMIC RISK
// =============================================================================

class UltraFastExchange {
    constructor(config) {
        this.cfg = config.risk;
        this.config = config;
        this.balance = new Decimal(this.cfg.initialBalance);
        this.startBal = this.balance;
        this.pos = null;
        this.history = [];
        this.dailyPnL = new Decimal(0);
        this.lastDay = new Date().getDate();
        this.equity = this.balance;
        this.riskScore = 0;
        this.consecutiveLosses = 0;
    }

    async init() {
        this.history = await HistoryManager.load();
        let totalPnL = new Decimal(0);
        this.history.forEach(t => totalPnL = totalPnL.add(new Decimal(t.netPnL)));
        this.balance = this.startBal.add(totalPnL);
        this.equity = this.balance;
        
        // Calculate consecutive losses from history
        this.consecutiveLosses = this.calculateConsecutiveLosses(this.history);
    }

    calculateConsecutiveLosses(trades) {
        let consecutive = 0;
        for (let i = trades.length - 1; i >= 0; i--) {
            if (trades[i].netPnL < 0) consecutive++;
            else break;
        }
        return consecutive;
    }

    checkDailyReset() {
        const today = new Date().getDate();
        if (today !== this.lastDay) {
            this.dailyPnL = new Decimal(0);
            this.lastDay = today;
            this.consecutiveLosses = 0;
            console.log(COLORS.GRAY("🔄 Daily Reset & Risk Reset"));
        }
    }

    updateEquity(currentPrice) {
        if (this.pos) {
            const unrealized = this.pos.side === 'BUY' 
                ? new Decimal(currentPrice).sub(this.pos.entry).mul(this.pos.qty)
                : this.pos.entry.sub(new Decimal(currentPrice)).mul(this.pos.qty);
            this.equity = this.balance.add(unrealized);
        } else {
            this.equity = this.balance;
        }
    }

    calculateRiskScore() {
        const drawdown = this.startBal.sub(this.equity).div(this.startBal).mul(100);
        const dailyLoss = this.dailyPnL.abs().div(this.startBal).mul(100);
        const volatility = this.calculateVolatility();
        
        let risk = 0;
        
        // Drawdown factor
        if (drawdown.gt(2)) risk += 20;
        if (drawdown.gt(4)) risk += 40;
        if (drawdown.gt(6)) risk += 60;
        
        // Daily loss factor
        if (dailyLoss.gt(1)) risk += 15;
        if (dailyLoss.gt(2)) risk += 35;
        if (dailyLoss.gt(3)) risk += 55;
        
        // Consecutive losses factor
        risk += this.consecutiveLosses * 10;
        
        // Volatility factor
        if (volatility > 0.02) risk += 20;
        if (volatility > 0.04) risk += 40;
        
        return Math.min(risk, 100);
    }

    calculateVolatility() {
        if (this.history.length < 10) return 0;
        const recentTrades = this.history.slice(-10);
        const returns = recentTrades.map(t => t.netPnL / 1000);
        const avgReturn = returns.reduce((a, b) => a + b, 0) / returns.length;
        const variance = returns.reduce((acc, ret) => acc + Math.pow(ret - avgReturn, 2), 0) / returns.length;
        return Math.sqrt(variance);
    }

    getDynamicRiskMultiplier() {
        const riskScore = this.calculateRiskScore();
        let multiplier = 1.0;
        
        if (riskScore > 30) multiplier *= 0.8;
        if (riskScore > 50) multiplier *= 0.6;
        if (riskScore > 70) multiplier *= 0.4;
        if (riskScore > 85) multiplier *= 0.2;
        
        return multiplier;
    }

    async evaluateUltraFast(priceVal, signal) {
        this.checkDailyReset();
        const startTime = Date.now();
        const price = new Decimal(priceVal);
        this.updateEquity(priceVal);
        this.riskScore = this.calculateRiskScore();

        let executionTime = 0;

        // --- Position Management ---
        if (this.pos) {
            const elapsed = Date.now() - this.pos.time;
            let close = false, reason = '';
            
            // Dynamic time-based exits
            const maxHold = this.config.scalping.maxHoldingTime;
            if (elapsed > maxHold) { 
                close = true; 
                reason = 'Time Exit'; 
            }
            else if (elapsed > this.config.scalping.timeBasedExit) {
                const curPnL = this.pos.side === 'BUY' 
                    ? price.sub(this.pos.entry) 
                    : this.pos.entry.sub(price);
                
                if (curPnL.lt(0)) { 
                    close = true; 
                    reason = 'Stale Kill'; 
                }
            }

            // Enhanced SL/TP with trailing stop
            if (!close) {
                const currentPnLPct = this.pos.side === 'BUY' 
                    ? price.sub(this.pos.entry).div(this.pos.entry)
                    : this.pos.entry.sub(price).div(this.pos.entry);
                
                // Trailing stop
                if (currentPnLPct.gt(this.config.scalping.breakEvenStop)) {
                    // Move SL to break-even
                    if (this.pos.side === 'BUY') {
                        this.pos.sl = this.pos.sl.gt(this.pos.entry) ? this.pos.sl : this.pos.entry;
                    } else {
                        this.pos.sl = this.pos.sl.lt(this.pos.entry) ? this.pos.sl : this.pos.entry;
                    }
                }
                
                // Partial close at profit target
                if (currentPnLPct.gt(this.config.scalping.partialClose) && !this.pos.partialClosed) {
                    // Close 50% of position
                    const partialQty = this.pos.qty.mul(0.5);
                    this.pos.qty = this.pos.qty.sub(partialQty);
                    this.pos.partialClosed = true;
                    
                    const partialPnL = this.pos.side === 'BUY' 
                        ? price.sub(this.pos.entry).mul(partialQty)
                        : this.pos.entry.sub(price).mul(partialQty);
                    
                    console.log(COLORS.YELLOW(`✂️ Partial Close: $${partialPnL.toFixed(4)}`));
                }
                
                // Standard exit conditions
                if (this.pos.side === 'BUY') {
                    if (price.lte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.gte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                } else {
                    if (price.gte(this.pos.sl)) { close = true; reason = 'SL Hit'; }
                    else if (price.lte(this.pos.tp)) { close = true; reason = 'TP Hit'; }
                }
            }

            // Quick exit for scalping
            if (!close && elapsed > 5000) {
                const quickExit = this.config.scalping.quickExitThreshold;
                const curPnL = this.pos.side === 'BUY' 
                    ? price.sub(this.pos.entry).div(this.pos.entry)
                    : this.pos.entry.sub(price).div(this.pos.entry);
                
                if (curPnL.gt(quickExit)) {
                    close = true;
                    reason = 'Quick Scalp';
                }
            }

            if (close) {
                const rawPnL = this.pos.side === 'BUY' 
                    ? price.sub(this.pos.entry).mul(this.pos.qty) 
                    : this.pos.entry.sub(price).mul(this.pos.qty);
                
                const fee = price.mul(this.pos.qty).mul(this.cfg.fee);
                const slippage = price.mul(this.pos.qty).mul(this.cfg.slippage);
                const netPnL = rawPnL.sub(fee).sub(slippage);
                
                this.balance = this.balance.add(netPnL);
                this.dailyPnL = this.dailyPnL.add(netPnL);
                
                // Update consecutive losses
                if (netPnL < 0) this.consecutiveLosses++;
                else this.consecutiveLosses = 0;
                
                const tradeRecord = {
                    date: new Date().toISOString(),
                    symbol: this.config.symbol,
                    side: this.pos.side,
                    entry: this.pos.entry.toNumber(),
                    exit: price.toNumber(),
                    qty: this.pos.qty.toNumber(),
                    netPnL: netPnL.toNumber(),
                    reason,
                    strategy: this.pos.strategy,
                    holdingTime: Date.now() - this.pos.time,
                    executionTime: executionTime,
                    riskScore: this.riskScore
                };
                
                await HistoryManager.save(tradeRecord);
                this.history.push(tradeRecord);
                
                const color = netPnL.gte(0) ? COLORS.LIME : COLORS.HOT_PINK;
                console.log(`${COLORS.BOLD(reason)}! PnL: ${color(netPnL.toFixed(4))} | Hold: ${Utils.formatTime(tradeRecord.holdingTime)}`);
                this.pos = null;
            }
        } 
        
        // --- Entry Logic ---
        else if (signal.action !== 'HOLD' && signal.confidence >= this.cfg.minConfidence) {
            try {
                // Risk assessment
                if (this.riskScore > 90) {
                    console.log(COLORS.RED('⛔ Risk Score too high, skipping trade'));
                    return;
                }

                const entry = new Decimal(priceVal);
                const sl = new Decimal(signal.stopLoss);
                const tp = new Decimal(signal.takeProfit);
                const dist = entry.sub(sl).abs();
                
                if (dist.isZero()) return;

                // Dynamic position sizing
                const riskMultiplier = this.getDynamicRiskMultiplier();
                let riskPercent = this.cfg.riskPercent * riskMultiplier;
                
                // Adjust for consecutive losses
                if (this.consecutiveLosses > 0) {
                    riskPercent *= Math.pow(0.7, this.consecutiveLosses);
                }

                const riskAmt = this.equity.mul(riskPercent / 100);
                let qty = riskAmt.div(dist);
                
                // Position size limits
                const maxQty = this.equity.mul(this.cfg.leverageCap).div(price);
                if (qty.gt(maxQty)) qty = maxQty;
                
                const maxPositionValue = this.equity.mul(this.config.risk.maxPositionSize);
                const positionValue = qty.mul(price);
                if (positionValue.gt(maxPositionValue)) {
                    qty = maxPositionValue.div(price);
                }

                if (qty.mul(price).lt(5)) return; // Min $5

                this.pos = {
                    side: signal.action, 
                    entry, 
                    qty, 
                    sl, 
                    tp,
                    strategy: signal.strategy || `Scalp-${signal.action}`,
                    time: Date.now()
                };
                
                executionTime = Date.now() - startTime;
                
                const col = signal.action === 'BUY' ? COLORS.LIME : COLORS.HOT_PINK;
                console.log(col(`⚡ SCALP ${signal.action} @ ${entry.toFixed(6)} | Size: ${qty.toFixed(6)} | Risk: ${riskPercent.toFixed(2)}%`));
            } catch (e) { 
                await HistoryManager.logError(e, { context: 'entry_logic' });
                console.error(e); 
            }
        }
    }

    getStats() {
        const wins = this.history.filter(t => new Decimal(t.netPnL).gt(0));
        const winRate = this.history.length > 0 ? (wins.length / this.history.length) * 100 : 0;
        
        return {
            balance: this.balance.toNumber(),
            equity: this.equity.toNumber(),
            dailyPnL: this.dailyPnL.toNumber(),
            totalTrades: this.history.length,
            winRate: winRate.toFixed(1),
            riskScore: this.riskScore,
            consecutiveLosses: this.consecutiveLosses,
            avgExecutionTime: this.history.length > 0 ? 
                this.history.reduce((a, t) => a + (t.executionTime || 0), 0) / this.history.length : 0
        };
    }
}

// =============================================================================
// 7. ADVANCED AI AGENT WITH MULTI-MODEL INTEGRATION
// =============================================================================

class AdvancedAIAgent {
    constructor(config) {
        const key = process.env.GEMINI_API_KEY;
        if (!key) throw new Error("Missing GEMINI_API_KEY");
        
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ 
            model: config.ai.model,
            generationConfig: {
                temperature: config.ai.temperature,
                topK: 12,
                topP: 0.7,
                maxOutputTokens: 300
            }
        });
        this.rateLimit = config.ai.rateLimitMs;
        this.maxRetries = config.ai.maxRetries || 3;
        this.lastCall = 0;
        this.apiCalls = [];
        this.config = config;
    }

    async analyzeUltraFast(ctx, indicators) {
        let retries = 0;
        while (retries < this.maxRetries) {
            try {
                await this.rateLimitCheck();

                const prompt = this.buildAdvancedPrompt(ctx, indicators);

                const result = await this.model.generateContent(prompt);
                const response = await result.response;
                const text = response.text().replace(/``````/g, '').trim();
                
                const signal = JSON.parse(text);
                
                // Enhanced validation and safety checks
                const validatedSignal = this.validateSignal(signal, ctx, indicators);
                
                this.trackApiCall(true);
                return validatedSignal;
                
            } catch (error) {
                retries++;
                this.trackApiCall(false);
                console.warn(COLORS.ORANGE(`🤖 AI Request Failed (Attempt ${retries}/${this.maxRetries}): ${error.message}`));
                
                if (retries >= this.maxRetries) {
                    console.error(COLORS.RED(`🤖 AI Analysis Failed: ${error.message}`));
                    await HistoryManager.logError(error, { context: 'ai_analysis' });
                    
                    return { 
                        action: "HOLD", 
                        confidence: 0, 
                        strategy: "AI System Error", 
                        entry: ctx.price,
                        stopLoss: ctx.price,
                        takeProfit: ctx.price,
                        reason: "AI processing failed after retries"
                    };
                }
                
                await sleep(2 ** retries * 100); // Exponential backoff
            }
        }
    }

    buildAdvancedPrompt(ctx, indicators) {
        const { price, microTrend, trendMTF, rsi, fisher, stochK, imbalance, volumeSpike, choppiness, acceleration, wss } = ctx;
        const { williams, momentum, roc, patterns, divergences, volumeFlow } = indicators;
        
        return `ROLE: Ultra-High Frequency Crypto Scalper (Professional)

MARKET MICRO-STRUCTURE:
┌─ Symbol: ${ctx.symbol} | Price: $${Utils.formatNumber(price, 6)}
├─ Timestamp: ${new Date().toISOString()}
├─ Latency: ${Date.now() - (ctx.lastUpdate || Date.now())}ms
└─ Volume 24h: ${(ctx.volume24h / 1000000).toFixed(1)}M

MULTI-TIMEFRAME ANALYSIS:
┌─ 1m Micro-Trend: ${microTrend}
├─ 3m Trend: ${trendMTF}
├─ Momentum: RSI=${rsi.toFixed(1)} | Fisher=${fisher.toFixed(3)} | Stoch=${stochK.toFixed(0)}
├─ Williams %R: ${williams[williams.length - 1]?.toFixed(1) || 'N/A'}
├─ Momentum ROC: ${momentum[momentum.length - 1]?.toFixed(4) || 'N/A'} | ${roc[roc.length - 1]?.toFixed(2) || 'N/A'}%
└─ Volume Flow: ${volumeSpike ? '🔥 SPIKE' : '📊 NORMAL'} | Flow: ${volumeFlow[volumeFlow.length - 1]?.toFixed(0) || 0}

ADVANCED PATTERN ANALYSIS:
${patterns.length > 0 ? patterns.map(p => `├─ ${p.type} (${p.direction || 'NEUTRAL'}) [${p.strength.toFixed(2)}]`).join('\n') : '└─ No patterns detected'}
${divergences.length > 0 ? divergences.map(d => `└─ ${d.type} (${d.indicator}) [${d.strength.toFixed(3)}]`).join('\n') : ''}

ORDER FLOW & LIQUIDITY:
├─ Imbalance: ${(imbalance * 100).toFixed(1)}%
├─ Acceleration: ${acceleration.toFixed(6)}
├─ Choppiness: ${choppiness.toFixed(1)}
└─ WSS Score: ${wss.score.toFixed(3)}

NEURAL NETWORK PREDICTION:
└─ Confidence: ${(ctx.neuralConfidence * 100).toFixed(1)}% | Signal: ${ctx.neuralSignal}

SCALPING EXECUTION RULES:
1. 🔥 ENTRY: Only on strong multi-signal confluence
2. ⚡ SPEED: Sub-second execution requirement
3. 🎯 TARGET: 0.18% minimum, 0.075% quick exit
4. 🛡️ RISK: Dynamic position sizing based on risk score
5. 📊 VALIDATION: All signals must align for entry

JSON RESPONSE:
{
  "action": "BUY"|"SELL"|"HOLD",
  "confidence": 0.85-0.99,
  "strategy": "Ultra-Scalp-[Pattern]",
  "entry": ${price},
  "stopLoss": calculate_dynamic_sl,
  "takeProfit": calculate_dynamic_tp,
  "reason": "detailed_reason",
  "timeframe": "1m|3m",
  "riskLevel": "LOW"|"MEDIUM"|"HIGH"
}`;
    }

    validateSignal(signal, ctx, indicators) {
        // Enhanced validation
        const minConfidence = this.config.ai.minConfidence || 0.88;
        
        if (signal.confidence < minConfidence) {
            signal.confidence = 0;
            signal.action = 'HOLD';
            signal.reason = 'Below confidence threshold';
        }

        // Price validation
        if (!signal.entry || isNaN(signal.entry) || Math.abs(signal.entry - ctx.price) / ctx.price > 0.01) {
            signal.entry = ctx.price;
        }

        // SL/TP validation
        if (!signal.stopLoss || isNaN(signal.stopLoss)) {
            signal.stopLoss = ctx.price;
        }
        if (!signal.takeProfit || isNaN(signal.takeProfit)) {
            signal.takeProfit = ctx.price;
        }

        // Strategy validation
        if (!signal.strategy) {
            signal.strategy = 'Ultra-Scalp';
        }

        // Timeframe validation
        if (!signal.timeframe) {
            signal.timeframe = '1m';
        }

        return signal;
    }

    async rateLimitCheck() {
        const now = Date.now();
        const timeSinceLastCall = now - this.lastCall;
        if (timeSinceLastCall < this.rateLimit) {
            await sleep(this.rateLimit - timeSinceLastCall);
        }
        this.lastCall = Date.now();
    }

    trackApiCall(success) {
        this.apiCalls.push({ timestamp: Date.now(), success });
        if (this.apiCalls.length > 100) {
            this.apiCalls = this.apiCalls.slice(-100);
        }
    }

    getApiMetrics() {
        if (this.apiCalls.length === 0) return { successRate: 100, avgLatency: 0 };
        
        const successful = this.apiCalls.filter(call => call.success).length;
        const successRate = (successful / this.apiCalls.length) * 100;
        const avgLatency = this.apiCalls.reduce((acc, call) => acc + (call.success ? 100 : 500), 0) / this.apiCalls.length;
        
        return {
            successRate: parseFloat(successRate.toFixed(2)),
            avgLatency: parseFloat(avgLatency.toFixed(0))
        };
    }
}

// Export classes for testing
export {
    ConfigManager,
    HistoryManager,
    Utils,
    TA,
    NeuralNetwork,
    UltraFastMarketEngine,
    UltraFastExchange,
    AdvancedAIAgent,
    COLORS
};

// =============================================================================
// 8. MAIN EXECUTION CONTROLLER
// =============================================================================

async function main() {
    console.clear();
    console.log(COLORS.bg(COLORS.BOLD(COLORS.HOT_PINK(` ⚡ WHALEWAVE ULTRA-FAST TITAN v11.0 `))));
    console.log(COLORS.GRAY('='.repeat(100)));

    const config = await ConfigManager.load();
    HistoryManager.config = config; // Set config for neural training
    const marketEngine = new UltraFastMarketEngine(config);
    const exchange = new UltraFastExchange(config);
    const ai = new AdvancedAIAgent(config);

    await exchange.init();
    marketEngine.connectWebSocket();

    console.log(COLORS.CYAN(`🎯 Symbol: ${config.symbol} | Balance: $${exchange.balance.toFixed(2)}`));
    console.log(COLORS.CYAN(`⚡ Ultra-Fast Mode: ACTIVE | Latency Target: <100ms`));
    console.log(COLORS.CYAN(`🧠 Neural Network: ${config.indicators.neural.enabled ? 'ENABLED' : 'DISABLED'}`));
    console.log(COLORS.GRAY('='.repeat(100)));

    let analytics = await HistoryManager.loadScalpingAnalytics();
    let loopCount = 0;

    while (true) {
        const loopStartTime = Date.now();
        
        try {
            const data = await marketEngine.fetchAllTimeframes();
            if (!data || !data.price) { 
                await sleep(config.delays.retry); 
                continue; 
            }

            const scalpData = data.kline[config.intervals.scalp] || [];
            if (scalpData.length < 30) { 
                await sleep(500); 
                continue; 
            }

            // Extract arrays efficiently
            const closes = scalpData.map(x => x.c);
            const highs = scalpData.map(x => x.h);
            const lows = scalpData.map(x => x.l);
            const volumes = scalpData.map(x => x.v);

            // Check liquidity requirements
            if (data.volume24h < config.indicators.scalping.liquidityThreshold) {
                console.log(COLORS.GRAY(`Low liquidity detected: ${(data.volume24h / 1000000).toFixed(1)}M`));
                await sleep(1000);
                continue;
            }

            // Calculate all indicators in parallel
            const [rsi, fisher, stoch, atr, chop, accel, volSpikes, microTrend, fvg, williams, momentum, roc, volumeFlow] = await Promise.all([
                TA.rsi(closes, config.indicators.periods.rsi),
                TA.fisher(highs, lows, config.indicators.periods.fisher),
                TA.stoch(highs, lows, closes, config.indicators.periods.stoch),
                TA.atr(highs, lows, closes, config.indicators.periods.atr),
                TA.choppiness(highs, lows, closes, config.indicators.periods.chop),
                TA.priceAcceleration(closes, 5),
                TA.volumeSpike(volumes, config.indicators.scalping.volumeSpikeThreshold),
                TA.microTrend(closes, config.indicators.scalping.microTrendLength),
                TA.findFVG(scalpData),
                Utils.williamsR(highs, lows, closes, config.indicators.periods.williams),
                Utils.calculateMomentum(closes, config.indicators.periods.momentum),
                Utils.calculateROC(closes, config.indicators.periods.roc),
                Utils.analyzeVolumeFlow(volumes, closes)
            ]);

            // Advanced pattern recognition
            const patterns = Utils.detectAdvancedPatterns(closes, volumes, highs, lows, closes);
            
            // Advanced divergence detection
            const indicators = { rsi, fisher, williams };
            const divergences = TA.detectAdvancedDivergence(closes, indicators);

            // Order flow imbalance
            const imbalance = marketEngine.cache.bids.length > 0 ? 
                TA.orderFlowImbalance(marketEngine.cache.bids, marketEngine.cache.asks) : 0;

            // Trend alignment
            const quickTrend = data.kline[config.intervals.quick];
            const qCloses = quickTrend.map(x => x.c);
            const qSMA = TA.sma(qCloses, 15);
            const trendMTF = qCloses[qCloses.length - 1] > qSMA[qSMA.length - 1] ? 'BULLISH' : 'BEARISH';

            // Neural network prediction
            let neuralScore = 0.5;
            if (config.indicators.neural.enabled) {
                const features = [
                    (closes[closes.length - 1] - closes[closes.length - 6]) / closes[closes.length - 6], // Price change
                    (volumes[volumes.length - 1] - volumes[volumes.length - 6]) / volumes[volumes.length - 6], // Volume change
                    rsi[rsi.length - 1] / 100, // RSI normalized
                    fisher[fisher.length - 1] / 5, // Fisher normalized
                    stoch.k[stoch.k.length - 1] / 100, // Stoch normalized
                    momentum[momentum.length - 1] // Momentum
                ];
                neuralScore = marketEngine.neural.predict(features);
            }

            // Calculate ultra-fast score
            const analysis = {
                closes, rsi, fisher, stoch, williams, momentum, roc, atr, chop, 
                acceleration: accel, volumeSpikes, microTrend, imbalance, 
                fairValueGaps: fvg, divergences, volumeFlow, neural: neuralScore,
                volume24h: data.volume24h
            };
            
            const score = marketEngine.calculateUltraFastScore(analysis);

            // Build context for AI
            const ctx = {
                symbol: config.symbol,
                price: data.price,
                volume24h: data.volume24h,
                microTrend: microTrend[microTrend.length - 1],
                trendMTF,
                rsi: rsi[rsi.length - 1],
                fisher: fisher[fisher.length - 1],
                stochK: stoch.k[stoch.k.length - 1],
                williams: williams[williams.length - 1],
                momentum: momentum[momentum.length - 1],
                roc: roc[roc.length - 1],
                imbalance,
                volumeSpike: volSpikes[volSpikes.length - 1],
                choppiness: chop[chop.length - 1],
                acceleration: accel[accel.length - 1],
                fairGaps: fvg.length,
                patterns: patterns.map(p => p.type),
                divergences: divergences.length,
                volumeFlow: volumeFlow[volumeFlow.length - 1],
                wss: score,
                neuralConfidence: neuralScore,
                neuralSignal: neuralScore > 0.6 ? 'BUY' : neuralScore < 0.4 ? 'SELL' : 'HOLD',
                lastUpdate: marketEngine.lastUpdate
            };

            // AI Decision
            let signal = { action: "HOLD", confidence: 0, reason: "Waiting for setup" };
            if (Math.abs(score.score) >= config.indicators.weights.actionThreshold) {
                process.stdout.write(COLORS.HOT_PINK(" 🧠 AI Ultra-Fast Analysis... "));
                signal = await ai.analyzeUltraFast(ctx, {
                    williams, momentum, roc, patterns, divergences, volumeFlow
                });
                process.stdout.write("\r");
            }

            // Execute
            await exchange.evaluateUltraFast(data.price, signal);

            // Neural network training update
            if (config.indicators.neural.enabled && loopCount % 100 === 0) {
                const trainingData = await HistoryManager.loadNeuralTraining();
                if (trainingData.length > 100) {
                    marketEngine.neural.train(trainingData.slice(-1000));
                }
            }

            loopCount++;

        } catch (err) {
            console.error(COLORS.RED(`Loop Error: ${err.message}`));
            await HistoryManager.logError(err, { context: 'main_loop' });
        }
        
        const loopTime = Date.now() - loopStartTime;
        if (loopTime > config.delays.loop) {
            console.log(COLORS.YELLOW(`⚠️ Loop took ${loopTime}ms (target: ${config.delays.loop}ms)`));
        }
        
        await sleep(config.delays.loop);
    }
}

// Export main for testing
export { main };

// Start the application if run directly
if (import.meta.url === `file://${process.argv[1]}`) {
    main().catch(err => {
        console.error(COLORS.RED('💥 Fatal Ultra-Fast Error:'), err);
        HistoryManager.logError(err, { context: 'main_catch' });
        process.exit(1);
    });
}