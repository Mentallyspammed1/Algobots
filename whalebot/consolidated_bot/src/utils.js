import fs from 'fs';
import chalk from 'chalk';
import { Decimal } from 'decimal.js';
import { ConfigManager } from './config.js';
import { NEON } from './ui.js';
import { TA } from './technical-analysis.js'; // Import TA module

// --- UTILITIES ---
// General helper functions for the bot.
export const Utils = {
    timestamp: () => new Date().toISOString(), // Returns current ISO timestamp

    // Sums an array of numbers, safely handling non-numeric values by treating them as 0.
    sum: (arr) => arr.reduce((acc, val) => acc + (Number(val) || 0), 0),

    // Safely parses a JSON string, returning null if parsing fails.
    safeJsonParse: (str) => {
        try {
            return JSON.parse(str);
        } catch (e) {
            console.error(chalk.red(`JSON Parse Error: ${e.message}`));
            return null;
        }
    },

    // Formats a number to a fixed decimal place, returning 'N/A' for invalid inputs.
    toFixed: (num, precision = 2) => {
        try {
            return new Decimal(num).toFixed(precision);
        } catch (e) {
            return 'N/A';
        }
    },

    // Calculates Weighted Signal Score (WSS) based on various indicators and configuration weights.
    calculateWSS: (analysis, config) => {
        const w = config.indicators.wss_weights; // Access WSS weights from config
        let score = 0;
        const last = analysis.closes.length - 1; // Index of the latest data point

        // --- 1. Trend Alignment ---
        // Add/subtract weight based on MTF trend direction
        score += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);

        // --- 2. Scalp Trend Confluence ---
        // Add/subtract weight based on SuperTrend and Chandelier Exit trends
        if (analysis.st.trend[last] === 1) score += w.trend_scalp_weight; else score -= w.trend_scalp_weight;
        if (analysis.ce.trend[last] === 1) score += w.trend_scalp_weight; else score -= w.trend_scalp_weight;

        // --- 3. Momentum Extremes (RSI, MFI, Stoch) ---
        // Add/subtract weight for oversold/overbought conditions
        const rsi = analysis.rsi[last];
        const mfi = analysis.mfi[last];
        if (rsi < 30 || mfi < 30) score += w.extreme_rsi_mfi_weight; 
        if (rsi > 70 || mfi > 70) score -= w.extreme_rsi_mfi_weight;
        
        const stoch_k = analysis.stoch.k[last];
        const stoch_d = analysis.stoch.d[last];
        if (stoch_k < 20 && stoch_d < 20) score += w.extreme_stoch_weight; // Oversold Stochastic
        if (stoch_k > 80 && stoch_d > 80) score -= w.extreme_stoch_weight; // Overbought Stochastic

        // --- 4. Regime/Volatility Influence (Chop, ADX, LinReg Slope) ---
        const chop = analysis.chop[last];
        const adx = analysis.adx[last];
        // If in a momentum regime (low chop, high ADX), add weight based on trend direction
        if (chop < 40 && adx > 25) score += (analysis.reg.slope[last] > 0 ? w.momentum_regime_weight : -w.momentum_regime_weight);

        // --- 5. Volatility Squeeze ---
        // Add/subtract weight if a volatility squeeze is detected, aligned with trend
        if (analysis.isSqueeze) score += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight); 
        
        // --- 6. Final Volatility Adjustment ---
        // Modify the final score based on overall market volatility levels
        const volatility = analysis.volatility[analysis.volatility.length - 1] || 0; // Current annualized volatility
        const avgVolatility = analysis.avgVolatility[analysis.avgVolatility.length - 1] || 1; // Average volatility (SMA)
        const volRatio = volatility / avgVolatility; // Ratio of current to average volatility

        if (volRatio > 1.5) score *= (1 - w.volatility_weight); // Reduce conviction in high volatility
        if (volRatio < 0.5) score *= (1 + w.volatility_weight); // Increase conviction in low volatility
        
        return parseFloat(score.toFixed(2)); // Return score rounded to 2 decimal places
    },

    // Builds the context object passed to the AI, summarizing key market data and indicators.
    buildContext: (data, analysis, config) => {
        const atrVal = analysis.atr[analysis.closes.length - 1] || 1; // ATR value for filtering walls
        // Filter out order book walls that are too far from the current price relative to ATR
        const wallFilter = (wallPrice) => wallPrice !== null && Math.abs(data.price - wallPrice) < (atrVal * 3); 

        // Determine Orderbook Support/Resistance levels
        const orderbookLevels = Utils.getOrderbookLevels(data.bids, data.asks, data.price, config.orderbook.support_resistance_levels);
        const srString = `S:[${orderbookLevels.supportLevels.join(', ')}] R:[${orderbookLevels.resistanceLevels.join(', ')}]`;

        const wss = Utils.calculateWSS(analysis, config); // Calculate Weighted Signal Score
        const linRegFinal = TA.getFinalValue(analysis, 'reg', 4); // Get Linear Regression slope/r2

        return {
            symbol: config.symbol,
            price: data.price,
            // Standard Indicators (formatted)
            rsi: TA.getFinalValue(analysis, 'rsi', 2),
            stoch_k: TA.getFinalValue(analysis, 'stoch').k,
            stoch_d: TA.getFinalValue(analysis, 'stoch').d,
            cci: TA.getFinalValue(analysis, 'cci', 2),
            macd_hist: TA.getFinalValue(analysis, 'macd', 4),
            adx: TA.getFinalValue(analysis, 'adx', 2),
            // Advanced Indicators (formatted)
            mfi: TA.getFinalValue(analysis, 'mfi', 2),
            chop: TA.getFinalValue(analysis, 'chop', 2),
            trend_angle: linRegFinal.slope, // Linear Regression Slope
            trend_quality: linRegFinal.r2,  // Linear Regression R-squared
            trend_mtf: analysis.trendMTF,   // Multi-Timeframe Trend
            squeeze: analysis.isSqueeze,    // Volatility Squeeze status
            fvg: analysis.fvg,              // Fair Value Gap object
            superTrend: TA.getFinalValue(analysis, 'st'), // SuperTrend direction
            chandelierExit: TA.getFinalValue(analysis, 'ce'), // Chandelier Exit direction
            // Volatility Metrics
            volatility: analysis.volatility[analysis.volatility.length - 1]?.toFixed(2) || '0.00', // Current annualized volatility
            marketRegime: analysis.marketRegime, // Market regime (HIGH/LOW/NORMAL Volatility)
            // Levels and Walls
            walls: {
                buy: wallFilter(analysis.buyWall) ? analysis.buyWall : null, // Filtered Buy Wall price
                sell: wallFilter(analysis.sellWall) ? analysis.sellWall : null // Filtered Sell Wall price
            },
            fibs: analysis.fibs, // Fibonacci Pivot Points
            sr_levels: srString, // Formatted Support/Resistance string
            wss: wss // Weighted Signal Score
        };
    },

    // Determines Orderbook Support/Resistance levels based on volume distribution.
    getOrderbookLevels: (bids, asks, currentClose, maxLevels) => {
        // Combine all price points from bids and asks
        const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
        // Get unique prices and sort them
        const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
        let potentialSR = []; // Array to store potential Support/Resistance levels

        for (const price of uniquePrices) {
            // Calculate total volume at this price for bids and asks
            let bidVolAtPrice = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
            let askVolAtPrice = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
            
            // Heuristic: If bid volume is significantly higher than ask volume, it might be Support
            if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
            // If ask volume is significantly higher than bid volume, it might be Resistance
            else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
        }
        // Sort potential levels by their distance from the current price (closest first)
        const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));
        
        // Extract top 'maxLevels' Support and Resistance levels below/above current price
        const supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
        const resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
        
        return { supportLevels, resistanceLevels };
    },
    
    // Generates a list of indicator configurations for analysis.
    getIndicatorList: (config) => [
        { name: 'rsi', period: config.indicators.rsi },
        { name: 'stoch', period: config.indicators.stoch_period, kP: config.indicators.stoch_k, dP: config.indicators.stoch_d },
        { name: 'cci', period: config.indicators.cci_period },
        { name: 'macd', period: config.indicators.macd_fast, slow: config.indicators.macd_slow, sig: config.indicators.macd_sig },
        { name: 'adx', period: config.indicators.adx_period },
        { name: 'mfi', period: config.indicators.mfi },
        { name: 'chop', period: config.indicators.chop_period },
        { name: 'linReg', period: config.indicators.linreg_period },
        { name: 'bb', period: config.indicators.bb_period, std: config.indicators.bb_std },
        { name: 'kc', period: config.indicators.kc_period, mult: config.indicators.kc_mult },
        { name: 'atr', period: config.indicators.atr_period },
        { name: 'st', period: config.indicators.atr_period, factor: config.indicators.st_factor }, // Using ATR period for ST factor
        { name: 'ce', period: config.indicators.ce_period, mult: config.indicators.ce_mult },
    ],
};