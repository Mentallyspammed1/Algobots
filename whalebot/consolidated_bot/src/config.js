import fs from 'fs';
import dotenv from 'dotenv';
import chalk from 'chalk';
import { Decimal } from 'decimal.js';

dotenv.config();

// --- ⚙️ CONFIGURATION MANAGER ---
// Manages loading, validation, and merging of bot configuration from a JSON file.
export class ConfigManager {
    static CONFIG_FILE = 'config.json';
    static DEFAULTS = {
        // General Bot Settings
        symbol: 'BTCUSDT', // Default trading symbol
        interval: '3',     // Main candle interval (e.g., '1', '3', '5', '15', '60' minutes)
        trend_interval: '15', // Interval for trend analysis (higher timeframe)
        limit: 300,        // Number of candles to fetch for analysis
        loop_delay: 15,    // Delay between main loop cycles in seconds

        // AI / Gemini Settings
        gemini_model: 'gemini-1.5-flash-latest', // Default AI model for signals
        ai: {
            minConfidence: 0.60, // Minimum confidence for AI to issue a trade signal
            model: 'gemini-1.5-flash-latest' // Alias for gemini_model
        },

        // Paper Trading Configuration
        paper_trading: {
            initial_balance: 1000.00, // Starting balance for paper trading simulation
            risk_percent: 1.0,       // Risk per trade as a percentage of balance
            leverage_cap: 10,        // Maximum leverage allowed for position sizing
            fee: 0.00055,            // Trading fee rate (e.g., 0.055%)
            slippage: 0.0001         // Simulated slippage for order execution
        },
        
        // Indicator Settings - All commonly used indicators
        indicators: {
            // Standard Indicators
            rsi: 14, 
            stoch_period: 14, stoch_k: 3, stoch_d: 3, // Stochastic Oscillator
            cci_period: 14, // Commodity Channel Index
            macd_fast: 12, macd_slow: 26, macd_sig: 9, // MACD
            adx_period: 14, // Average Directional Index

            // Advanced Indicators
            mfi: 14, // Money Flow Index
            chop_period: 14, // Choppiness Index
            linreg_period: 20, // Linear Regression period
            bb_period: 20, bb_std: 2.0, // Bollinger Bands (Period, Std Dev)
            kc_period: 20, kc_mult: 1.5, // Keltner Channels (Period, Multiplier)
            atr_period: 14, // Average True Range
            st_factor: 3.0, ce_period: 22, ce_mult: 3.0, // SuperTrend (Factor), Chandelier Exit (Period, Multiplier)
            
            // Weighted Signal Scoring (WSS) Configuration - Weights for different indicators
            wss_weights: {
                trend_mtf_weight: 2.0,          // Weight for Multi-Timeframe Trend alignment
                trend_scalp_weight: 1.5,        // Weight for Scalp Trend alignment (ST, CE)
                extreme_rsi_mfi_weight: 1.0,    // Weight for RSI/MFI being in extreme zones (oversold/overbought)
                extreme_stoch_weight: 0.5,      // Weight for Stochastic extremes
                momentum_regime_weight: 1.0,    // Weight for momentum indicators (ADX, Chop, LinReg Slope)
                squeeze_vol_weight: 0.5,        // Weight for volatility squeeze detection
                volatility_weight: 0.4,         // Factor to adjust WSS based on overall volatility levels
                action_threshold: 1.0           // Minimum WSS score required to consider a BUY/SELL action
            }
        },
        
        // Orderbook Analysis Settings
        orderbook: {
            depth: 50,             // Number of order book levels to fetch
            wall_threshold: 5.0,   // Threshold to detect significant volume walls
            support_resistance_levels: 5 // Number of key S/R levels to identify
        },
        
        // API Client Settings (for Bybit)
        api: {
            timeout: 8000,         // Request timeout in milliseconds
            retries: 3,            // Number of retries for failed API requests
            backoff_factor: 2      // Exponential backoff factor for retries
        },

        // Risk Management Settings
        risk: {
            max_drawdown: 10.0,    // Maximum allowed drawdown percentage from start balance
            daily_loss_limit: 5.0, // Maximum allowed daily loss percentage from start balance
            max_positions: 1       // Maximum number of concurrent open positions
        },

        // Simulation / Optimization Settings
        simulation: {
            mock_data: false,      // Whether to use mock data (e.g., for optimization runs)
            iterations: 100        // Number of iterations for simulations
        },

        // Delays and Thresholds
        delays: {
            loop: 15,              // Delay between main loop cycles in seconds
            ai_query: 60           // Minimum delay between AI queries in seconds to avoid rate limits/spam
        }
    };

    // Loads configuration: Merges defaults with user settings from config.json.
    static async load() {
        let config = JSON.parse(JSON.stringify(this.DEFAULTS)); // Deep copy defaults to avoid mutation
        
        if (fs.existsSync(this.CONFIG_FILE)) {
            try {
                const userConfig = JSON.parse(fs.readFileSync(this.CONFIG_FILE, 'utf-8'));
                // Deep merge user config over defaults
                config = this.deepMerge(config, userConfig);
                this.validate(config); // Validate merged configuration
            } catch (e) {
                console.error(chalk.red(`Configuration Error: Could not load or validate ${this.CONFIG_FILE}. Using defaults. Error: ${e.message}`));
            }
        } else {
            // Create default config file if it doesn't exist
            fs.writeFileSync(this.CONFIG_FILE, JSON.stringify(this.DEFAULTS, null, 2));
            console.log(chalk.yellow(`Created default ${this.CONFIG_FILE}. Please review and customize.`));
        }
        
        // Set global Decimal precision based on loaded config
        Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });
        
        return config;
    }

    // Deep merges two objects, handling nested objects recursively.
    static deepMerge(target, source) {
        const result = { ...target };
        for (const key in source) {
            if (source.hasOwnProperty(key)) {
                // If property is a non-array object and exists in target, recurse
                if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key]) && !['buffer'].includes(key)) { 
                    result[key] = this.deepMerge(result[key] || {}, source[key]);
                } else { // Otherwise, overwrite or add the property
                    result[key] = source[key];
                }
            }
        }
        return result;
    }

    // Validates critical configuration parameters.
    static validate(config) {
        const errors = [];
        if (config.min_confidence < 0 || config.min_confidence > 1) errors.push('ai.minConfidence must be between 0 and 1');
        if (config.risk.max_drawdown < 0 || config.risk.max_drawdown > 100) errors.push('risk.max_drawdown must be between 0 and 100');
        if (config.risk.daily_loss_limit < 0 || config.risk.daily_loss_limit > 100) errors.push('risk.daily_loss_limit must be between 0 and 100');
        if (errors.length > 0) throw new Error(`Configuration validation failed: ${errors.join(', ')}`);
    }
}