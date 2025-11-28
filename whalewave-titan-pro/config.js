// config.js
import fs from 'fs';
import chalk from 'chalk';

export class ConfigManager {
  static CONFIG_FILE = 'config.json';

  static DEFAULTS = {
    symbol: 'BTCUSDT',
    interval: '3',
    trend_interval: '15',
    limit: 300,
    loop_delay: 4,
    gemini_model: 'gemini-1.5-flash',
    min_confidence: 0.75,
    risk: {
      max_drawdown: 10.0,
      daily_loss_limit: 5.0,
      max_positions: 1
    },
    paper_trading: {
      initial_balance: 1000.0,
      risk_percent: 2.0,
      leverage_cap: 10,
      fee: 0.00055,
      slippage: 0.0001
    },
    indicators: {
      rsi: 10,
      stoch_period: 10,
      stoch_k: 3,
      stoch_d: 3,
      cci_period: 10,
      macd_fast: 12,
      macd_slow: 26,
      macd_sig: 9,
      adx_period: 14,
      mfi: 10,
      chop_period: 14,
      linreg_period: 15,
      vwap_period: 20,
      bb_period: 20,
      bb_std: 2.0,
      kc_period: 20,
      kc_mult: 1.5,
      atr_period: 14,
      st_factor: 2.5,
      ce_period: 22,
      ce_mult: 3.0,
      wss_weights: {
        trend_mtf_weight: 2.2,
        trend_scalp_weight: 1.2,
        momentum_normalized_weight: 1.8,
        macd_weight: 1.0,
        regime_weight: 0.8,
        squeeze_vol_weight: 1.0,
        liquidity_grab_weight: 1.5,
        divergence_weight: 2.5,
        volatility_weight: 0.5,
        action_threshold: 2.0
      }
    },
    orderbook: {
      depth: 50,
      wall_threshold: 3.0,
      sr_levels: 5
    },
    api: {
      timeout: 8000,
      retries: 3,
      backoff_factor: 2
    }
  };

  static deepMerge(base, patch) {
    if (Array.isArray(base)) return patch ?? base;
    if (typeof base !== 'object' || base === null) return patch ?? base;
    const out = { ...base };
    if (typeof patch !== 'object' || patch === null) return out;
    for (const key of Object.keys(patch)) out[key] = this.deepMerge(base[key], patch[key]);
    return out;
  }

  static validate(conf) {
    if (!conf.symbol || typeof conf.symbol !== 'string') {
      throw new Error('config.symbol must be a non‑empty string');
    }
    if (conf.paper_trading.initial_balance <= 0) {
      throw new Error('paper_trading.initial_balance must be > 0');
    }
    if (conf.loop_delay < 1) {
      console.warn(chalk.yellow('loop_delay < 1s is aggressive, clamping to 1'));
      conf.loop_delay = 1;
    }
  }

  static load() {
    try {
      const raw = fs.readFileSync(this.CONFIG_FILE, 'utf-8');
      const user = JSON.parse(raw);
      const merged = this.deepMerge(this.DEFAULTS, user);
      this.validate(merged);
      return merged;
    } catch (e) {
      console.error(chalk.red(`Config Load Error: ${e.message}`));
      console.error(chalk.yellow('Falling back to DEFAULT configuration only.'));
      const conf = JSON.parse(JSON.stringify(this.DEFAULTS));
      this.validate(conf);
      return conf;
    }
  }
}
