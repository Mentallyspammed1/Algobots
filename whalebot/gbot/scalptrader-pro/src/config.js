const fs = require('fs');
const chalk = require('chalk');
require('dotenv').config();

class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        symbol: 'BTCUSDT', interval: '3', trend_interval: '15', limit: 300,
        loop_delay: 4, gemini_model: 'gemini-1.5-flash', min_confidence: 0.75, 
        risk: { max_drawdown: 10.0, daily_loss_limit: 5.0, max_positions: 1, },
        paper_trading: { initial_balance: 1000.00, risk_percent: 2.0, leverage_cap: 10, fee: 0.00055, slippage: 0.0001 },
        indicators: {
            rsi: 10, stoch_period: 10, stoch_k: 3, stoch_d: 3, cci_period: 10, 
            macd_fast: 12, macd_slow: 26, macd_sig: 9, adx_period: 14,
            mfi: 10, chop_period: 14, linreg_period: 15, vwap_period: 20,
            bb_period: 20, bb_std: 2.0, kc_period: 20, kc_mult: 1.5,
            atr_period: 14, st_factor: 2.5, ce_period: 22, ce_mult: 3.0,
            wss_weights: {
                trend_mtf_weight: 2.2, trend_scalp_weight: 1.2,
                momentum_normalized_weight: 1.8, macd_weight: 1.0,
                regime_weight: 0.8, squeeze_vol_weight: 1.0,
                liquidity_grab_weight: 1.5, divergence_weight: 2.5,
                volatility_weight: 0.5, action_threshold: 2.0
            }
        },
        orderbook: { depth: 50, wall_threshold: 3.0, sr_levels: 5 },
        api: { timeout: 8000, retries: 3, backoff_factor: 2 }
    };

    static load() {
        let config = { ...this.DEFAULTS };
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                config = this.deepMerge(config, userConfig);
            } catch (e) { console.error(chalk.red(`Config Error: ${e.message}`)); }
        } else {
            fs.writeFileSync(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
        }
        return config;
    }

    static deepMerge(target, source) {
        const result = { ...target };
        for (const key in source) {
            if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
                result[key] = this.deepMerge(result[key] || {}, source[key]);
            } else { result[key] = source[key]; }
        }
        return result;
    }
}

const config = ConfigManager.load();
config.GEMINI_API_KEY = process.env.GEMINI_API_KEY;
config.PHONE_NUMBER = process.env.PHONE_NUMBER;

module.exports = config;