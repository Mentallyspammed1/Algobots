// File: src/config-manager.js

import fs from 'fs/promises';

export class ConfigManager {
    static CONFIG_FILE = 'config.json';

    static DEFAULTS = Object.freeze({
        symbol: 'BTCUSDT',
        intervals: { scalp: '1', quick: '3', trend: '5', macro: '15' },
        limits: { kline: 200, orderbook: 50, ticks: 1000 },
        delays: { loop: 500, retry: 500, ai: 1000 },
        ai: {
            model: 'gemini-1.5-pro',
            minConfidence: 0.88,
            temperature: 0.03,
            rateLimitMs: 1000,
            maxRetries: 3
        },
        risk: {
            initialBalance: 1000.00,
            maxDrawdown: 6.0,
            dailyLossLimit: 3.0,
            riskPercent: 1.0,
            leverageCap: 20,
            fee: 0.00045,
            slippage: 0.00005,
            volatilityAdjustment: true,
            maxPositionSize: 0.25,
            minRR: 1.8,
            dynamicSizing: true,
            atr_tp_limit: 3.5,
            trailing_ratchet_dist: 2.0,
            zombie_time_ms: 300000,
            zombie_pnl_threshold: 0.0015,
            break_even_trigger: 1.0
        },
        indicators: {
            periods: {
                rsi: 5, fisher: 7, stoch: 3, cci: 10, adx: 6, mfi: 5, chop: 10, atr: 6, ema_fast: 5, ema_slow: 13, williams: 7, roc: 8, momentum: 9,
                microTrendLength: 8
            },
            scalping: {
                volumeSpikeThreshold: 2.2, priceAcceleration: 0.00015, orderFlowImbalance: 0.35, liquidityThreshold: 1000000
            },
            weights: {
                microTrend: 4.0, momentum: 3.2, volume: 3.0, orderFlow: 2.8, acceleration: 2.5, structure: 2.0, divergence: 1.8, neural: 2.5, actionThreshold: 2.8
            },
            neural: { enabled: true, modelPath: './models/scalping_model.json', confidence: 0.85, features: ['price_change', 'volume_change', 'rsi', 'fisher', 'stoch', 'momentum'] }
        },
        scalping: {
            minProfitTarget: 0.0018, maxHoldingTime: 450000, quickExitThreshold: 0.00075, timeBasedExit: 180000,
            partialClose: 0.0009, breakEvenStop: 0.0006
        },
        websocket: { enabled: true, reconnectInterval: 2000, tickData: true, heartbeat: true }
    });

    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS));
        try {
            await fs.access(this.CONFIG_FILE);
            const fileContent = await fs.readFile(this.CONFIG_FILE, 'utf-8');
            config = this.deepMerge(config, JSON.parse(fileContent));
        } catch (error) {
            await fs.writeFile(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        this.validate(config);
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

    static validate(config) {
        if (config.risk.minRR < 1.0) {
            console.warn(COLORS.RED('Invalid config: minRR must be >= 1.0'));
            config.risk.minRR = 1.0;
        }
        if (config.ai.minConfidence > 1.0 || config.ai.minConfidence < 0.0) {
            console.warn(COLORS.RED('Invalid config: minConfidence must be between 0 and 1'));
            config.ai.minConfidence = 0.88;
        }
    }
}