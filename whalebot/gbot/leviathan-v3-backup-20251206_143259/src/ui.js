import chalk from 'chalk';

/**
 * A centralized object for console text styling.
 * Updated with a more vibrant, "neon" color palette.
 */
export const COLOR = {
    GREEN: chalk.hex('#39FF14'),   // Neon Green
    RED: chalk.hex('#FF073A'),     // Neon Red/Pink
    BLUE: chalk.hex('#0A84FF'),   // Standard Blue (already quite vibrant)
    PURPLE: chalk.hex('#BC13FE'), // Neon Purple
    YELLOW: chalk.hex('#FAED27'), // Neon Yellow
    CYAN: chalk.hex('#00FFFF'),   // Aqua/Cyan
    GRAY: chalk.hex('#8E8E93'),   // A slightly lighter gray for readability
    ORANGE: chalk.hex('#FF9F00'), // Bright Orange
    MAGENTA: chalk.hex('#FF00FF'), // Magenta
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#1C1C1E')(text), // A darker background for contrast
};

/**
 * Renders the main trading HUD to the console.
 * @param {object} state - The current state object.
 */
export function renderHUD(state) {
    const { 
        time, symbol, price, latency, score, orderbook, position, aiSignal, consecutiveLosses,
        rsi, fisher, atr, williamsR,
        macd, bollingerBands, stochRSI, adx,
        supertrend, ichimoku, vwap, hma, choppiness, t3
    } = state;

    const latColor = latency > 500 ? COLOR.RED : COLOR.GREEN;
    const scoreColor = score > 0 ? COLOR.GREEN : COLOR.RED;
    const fishColor = fisher > 0 ? COLOR.CYAN : COLOR.PURPLE;
    const skew = orderbook.skew || 0;
    const skewColor = skew > 0 ? COLOR.GREEN : COLOR.RED;
    const posText = position ? `${position.side}` : 'FLAT';
    
    const volText = aiSignal.volatilityForecast ? `Vol: ${aiSignal.volatilityForecast.substring(0,1)}` : 'Vol: M';
    const entryText = aiSignal.aiEntry && aiSignal.aiEntry > 0 ? `E: ${aiSignal.aiEntry.toFixed(2)}` : 'E: N/A';
    const volColor = aiSignal.volatilityForecast === 'HIGH' ? COLOR.ORANGE : COLOR.GRAY;
    const lossColor = consecutiveLosses > 0 ? COLOR.RED : COLOR.GRAY;

    const hudLines = [
        // Line 1: Basic Info & Price
        `${COLOR.GRAY(time)} │ ${COLOR.BOLD(symbol)} ${price.toFixed(2)} │ Lat: ${latColor(latency+'ms')} │ Score: ${scoreColor(score.toFixed(1))}`,
        
        // Line 2: Core Indicators
        `RSI: ${rsi.toFixed(1)} │ Fish: ${fishColor(fisher.toFixed(2))} │ ATR: ${atr.toFixed(2)} │ W%R: ${williamsR.toFixed(1)}`,

        // Line 3: MACD & Bollinger Bands
        `MACD(H): ${macd.histogram.toFixed(2)} │ BB(M/U/L): ${bollingerBands.mid.toFixed(2)}/${bollingerBands.upper.toFixed(2)}/${bollingerBands.lower.toFixed(2)}`,

        // Line 4: StochRSI & ADX
        `Stoch(K/D): ${stochRSI.k.toFixed(1)}/${stochRSI.d.toFixed(1)} │ ADX(ADX/PDI/NDI): ${adx.adx.toFixed(1)}/${adx.pdi.toFixed(1)}/${adx.ndi.toFixed(1)}`,
        
        // Line 5: Advanced Indicators 1
        `SuperTrend: ${supertrend.trend.toFixed(2)} (${supertrend.direction === 1 ? 'UP' : 'DN'}) │ VWAP: ${vwap.toFixed(2)} │ HMA: ${hma.toFixed(2)}`,
        
        // Line 6: Advanced Indicators 2
        `Chop: ${choppiness.toFixed(2)} │ T3: ${t3.toFixed(2)}`,

        // Line 7: Orderbook & Position
        `Skew: ${skewColor(skew.toFixed(2))} │ Wall: ${COLOR.YELLOW(orderbook.wallStatus || 'N/A')} │ ${COLOR.YELLOW(posText)} │ Losses: ${lossColor(consecutiveLosses || 0)}`,

        // Line 8: AI & Entry Info
        `AI: ${aiSignal.decision} (${(aiSignal.confidence * 100).toFixed(0)}%) │ ${volColor(volText)} │ ${COLOR.CYAN(entryText)}`
    ];

    process.stdout.write(hudLines.join('\n') + '\n');
}