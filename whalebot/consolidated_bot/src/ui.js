import chalk from 'chalk';
import { Decimal } from 'decimal.js';

// --- UI UTILITIES ---
// Provides color constants and functions for console output.
export const NEON = {
    GREEN: chalk.hex('#39FF14'),
    RED: chalk.hex('#FF073A'),
    BLUE: chalk.hex('#00FFFF'),
    PURPLE: chalk.hex('#BC13FE'),
    YELLOW: chalk.hex('#FAED27'),
    ORANGE: chalk.hex('#FF9F00'),
    GRAY: chalk.hex('#666666'),
    BOLD: chalk.bold,
    CYAN: chalk.hex('#00FFFF')
};

// Helper for applying background color.
NEON.bg = (text) => chalk.bgHex('#222')(text);

// Renders a styled box for displaying information in the console.
export function renderBox(title, lines, width = 60) {
    const border = NEON.GRAY('─'.repeat(width));
    console.log(border);
    console.log(NEON.bg(NEON.PURPLE.bold(` ${title} `.padEnd(width)))); // Title with background and bold purple
    console.log(border);
    lines.forEach(l => console.log(l)); // Print each line of content
    console.log(border);
}

// Renders the Heads-Up Display (HUD) for the trading bot state.
export function renderHUD(state) {
    console.clear(); // Clear console for clean display
    
    // Determine colors and text for regime based on Chop value
    const regimeColor = state.chop > 60 ? NEON.BLUE : state.chop < 40 ? NEON.GREEN : NEON.GRAY;
    const regimeTxt = state.chop > 60 ? "MEAN REVERSION" : state.chop < 40 ? "MOMENTUM" : "NOISE/HOLD";
    
    // Determine Squeeze text color
    const sqzTxt = state.squeeze ? NEON.RED("🔥 ACTIVE") : NEON.GRAY("Inactive");
    
    // Determine Volatility Regime color
    const volColor = state.marketRegime === 'HIGH_VOLATILITY' ? NEON.RED : 
                    state.marketRegime === 'LOW_VOLATILITY' ? NEON.GREEN : NEON.YELLOW;

    // Render the main info box
    renderBox(`WHALEWAVE TITAN | ${state.price.toFixed(4)}`, [
        `Regime: ${regimeColor(regimeTxt)} | Vol Regime: ${volColor(state.marketRegime)} | Vol: ${state.volatility}`,
        `MTF: ${state.trend_mtf === 'BULLISH' ? NEON.GREEN(state.trend_mtf) : NEON.RED(state.trend_mtf)} | WSS: ${state.wss}`,
        `RSI: ${state.rsi} | MFI: ${state.mfi} | Chop: ${state.chop} | ADX: ${state.adx}`,
        `Stoch: ${state.stoch_k}/${state.stoch_d} | CCI: ${state.cci} | MACD Hist: ${state.macd_hist}`,
        `ST: ${state.superTrend} | CE: ${state.chandelierExit} | Squeeze: ${sqzTxt}`,
        `FVG: ${state.fvg ? NEON.YELLOW(state.fvg.type + ' @ ' + state.fvg.price.toFixed(4)) : 'None'}`,
        `Key Levels: P=${state.fibs.P.toFixed(4)} | S1=${state.fibs.S1.toFixed(4)} | R1=${state.fibs.R1.toFixed(4)}`,
        `S/R: ${state.sr_levels}`
    ]);
    
    // Display AI Signal
    const col = state.aiSignal.action === 'BUY' ? NEON.GREEN : state.aiSignal.action === 'SELL' ? NEON.RED : NEON.GRAY;
    console.log(`SIGNAL: ${col(state.aiSignal.action)} (${(state.aiSignal.confidence * 100).toFixed(0)}%)`);
    console.log(chalk.dim(state.aiSignal.reason)); // Reason for the signal

    // Display position details or balance
    if(state.position) {
        const curPnl = state.position.side==='BUY' ? new Decimal(state.price).sub(state.position.entry) : new Decimal(state.position.entry).sub(new Decimal(state.price));
        const pnlVal = curPnl.mul(state.position.qty);
        const pnlCol = pnlVal.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`${NEON.BLUE('POS:')} ${state.position.side} @ ${state.position.entry.toFixed(4)} | SL: ${state.position.sl.toFixed(4)} | TP: ${state.position.tp.toFixed(4)} | PnL: ${pnlCol(pnlVal.toFixed(2))}`);
    } else {
        console.log(`Balance: $${state.balance.toFixed(2)}`); // Display balance if no position is open
    }
    // Display performance metrics
    console.log(`Latency: ${state.latency}ms | Benchmark: ${state.benchmarkMs.toFixed(2)}ms`);
}