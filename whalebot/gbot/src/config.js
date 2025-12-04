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
            minConfidence: 0.85,
            maxTokens: 300
        },
        risk: {
            maxDailyLoss: 5.0, // % of balance
            maxRiskPerTrade: 1.0, // % of balance
            leverage: 5,
            fee: 0.00055,
            slippage: 0.0001,
            rewardRatio: 1.5,
            initialBalance: 10000 // Added for paper trading
        },
        indicators: {
            rsi: 14,
            fisher: 10,
            atr: 14,
            bb: { period: 20, std: 2 },
            threshold: 1.8 // Minimum score to trigger AI check
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
