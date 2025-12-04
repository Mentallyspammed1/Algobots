import fs from 'fs/promises';

/**
 * Manages loading and merging of the bot's configuration from a JSON file.
 */
export class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        live_trading: process.env.LIVE_MODE === 'true',
        intervals: { scalping: '1', main: '5', trend: '15' },
        limits: { kline: 300, orderbook: 20 },
        delays: { loop: 3000, retry: 2000, wsReconnect: 1000 },
        ai: { 
            model: 'gemini-1.5-flash', 
            minConfidence: 0.86,
            maxTokens: 300
        },
        risk: {
            maxDailyLoss: 5.0,
            maxRiskPerTrade: 1.0,
            leverage: 5,
            fee: 0.00055,
            slippage: 0.0001,
            rewardRatio: 1.5,
            initialBalance: 10000
        },
        indicators: {
            rsi: 14,
            fisher: 10,
            atr: 14,
            bb: { period: 20, std: 2 },
            macd: { fast: 12, slow: 26, signal: 9 },
            stochRSI: { rsi: 14, stoch: 14, k: 3, d: 3 },
            adx: 14,

            scoring: {
                fisher_weight: 2.2,
                rsi_weight: 1.0,
                imbalance_weight: 1.0,
                bb_weight: 1.0,
                macd_weight: 1.5,
                stoch_rsi_weight: 0.8,
                adx_weight: 0.5
            },
            
            // --- Integrated Advanced Indicators Config ---
            advanced: {
                t3: { enabled: true, period: 10, vFactor: 0.7, weight: 0.8 },
                superTrend: { enabled: true, period: 10, multiplier: 3, weight: 1.8 },
                vwap: { enabled: true, weight: 0.5 },
                hma: { enabled: true, period: 16, weight: 0.7 },
                choppiness: { enabled: true, period: 14, threshold: 61.8, weight: -1.0 },
                connorsRSI: { enabled: true, rsiPeriod: 3, streakRsiPeriod: 2, rankPeriod: 100, oversold: 10, overbought: 90, weight: 1.2 },
                kaufmanER: { enabled: false, period: 10, efficiency_threshold: 0.6, weight: 0.5 },
                ichimoku: { enabled: true, span1: 9, span2: 26, span3: 52, weight: 1.5 },
                schaffTC: { enabled: true, fast: 23, slow: 50, cycle: 10, oversold: 25, overbought: 75, weight: 1.0 },
                dpo: { enabled: false, period: 21, weight: 0.5 }
            },

            thresholds: {
                adx_trend_threshold: 25,
                imbalance_threshold: 0.2
            }
        }
    });

    static async load() {
        let config = { ...this.DEFAULTS };
        try {
            const data = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.mergeDeep(config, JSON.parse(data));
        } catch {
            console.log(`[ConfigManager] No '${this.CONFIG_FILE}' found, using default settings.`);
        }
        return config;
    }

    static mergeDeep(target, source) {
        const output = { ...target };
        for (const key in source) {
            if (Object.prototype.hasOwnProperty.call(source, key)) {
                if (source[key] instanceof Object && key in target && target[key] instanceof Object) {
                    output[key] = this.mergeDeep(target[key], source[key]);
                } else {
                    output[key] = source[key];
                }
            }
        }
        return output;
    }
}