import chalk from 'chalk';

/**
 * A centralized object for console text styling.
 */
export const COLOR = {
    GREEN: chalk.hex('#00FF41'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#0A84FF'),
    PURPLE: chalk.hex('#BF5AF2'),
    YELLOW: chalk.hex('#FFD60A'),
    CYAN: chalk.hex('#32ADE6'),
    GRAY: chalk.hex('#8E8E93'),
    ORANGE: chalk.hex('#FFA500'),
    BOLD: chalk.bold,
    bg: (text) => chalk.bgHex('#101010')(text),
};

/**
 * Renders the main trading HUD to the console.
 * @param {object} state - The current state object.
 */
export function renderHUD(state) {
    const { time, symbol, price, latency, score, rsi, fisher, atr, imbalance, position, aiSignal } = state;

    const latColor = latency > 500 ? COLOR.RED : COLOR.GREEN;
    const scoreColor = score > 0 ? COLOR.GREEN : COLOR.RED;
    const fishColor = fisher > 0 ? COLOR.BLUE : COLOR.PURPLE;
    const imbColor = imbalance > 0 ? COLOR.GREEN : COLOR.RED;
    const posText = position ? `${position.side}` : 'FLAT';
    
    // Safe retrieval of AI data
    const volText = aiSignal.volatilityForecast ? `Vol: ${aiSignal.volatilityForecast.substring(0,1)}` : 'Vol: M';
    const entryText = aiSignal.aiEntry && aiSignal.aiEntry > 0 ? `E: ${aiSignal.aiEntry.toFixed(2)}` : 'E: N/A';
    const volColor = aiSignal.volatilityForecast === 'HIGH' ? COLOR.RED : COLOR.GREEN;

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
    ].join(' | ');

    process.stdout.write(`\r${hud}  `); // Extra spaces to clear previous line
}
