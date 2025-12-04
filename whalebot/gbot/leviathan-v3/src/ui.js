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
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#1C1C1E')(text), // A darker background for contrast
};

/**
 * Renders the main trading HUD to the console.
 * @param {object} state - The current state object.
 */
export function renderHUD(state) {
    const { time, symbol, price, latency, score, rsi, fisher, atr, imbalance, position, aiSignal } = state;

    const latColor = latency > 500 ? COLOR.RED : COLOR.GREEN;
    const scoreColor = score > 0 ? COLOR.GREEN : COLOR.RED;
    const fishColor = fisher > 0 ? COLOR.CYAN : COLOR.PURPLE; // Changed to Cyan/Purple
    const imbColor = imbalance > 0 ? COLOR.GREEN : COLOR.RED;
    const posText = position ? `${position.side}` : 'FLAT';
    
    // Safe retrieval of AI data
    const volText = aiSignal.volatilityForecast ? `Vol: ${aiSignal.volatilityForecast.substring(0,1)}` : 'Vol: M';
    const entryText = aiSignal.aiEntry && aiSignal.aiEntry > 0 ? `E: ${aiSignal.aiEntry.toFixed(2)}` : 'E: N/A';
    const volColor = aiSignal.volatilityForecast === 'HIGH' ? COLOR.ORANGE : COLOR.GRAY;

    const hud = [
        COLOR.GRAY(time),
        `${COLOR.BOLD(symbol)} ${price.toFixed(2)}`,
        `Lat: ${latColor(latency+'ms')}`,
        `Score: ${scoreColor(score.toFixed(1))}`,
        `RSI: ${rsi.toFixed(1)}`,
        `Fish: ${fishColor(fisher.toFixed(2))}`,
        `ATR: ${atr.toFixed(2)}`,
        `Imb: ${imbColor((imbalance*100).toFixed(0)+'%')}`,
        `${COLOR.YELLOW(posText)}`,
        `${volColor(volText)}`,
        `${COLOR.CYAN(entryText)}`
    ].join(' │ '); // Using a different separator for style

    process.stdout.write(`\r${hud}  `);
}