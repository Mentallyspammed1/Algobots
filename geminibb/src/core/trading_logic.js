import { ta } from '../indicators/ta.js';
import { config } from '../config.js';

export function calculateIndicators(klines) {
    // Bybit sends klines with newest first, reverse it for calculations
    const reversedKlines = [...klines].reverse();

    const formattedKlines = reversedKlines.map(k => ({
        timestamp: parseInt(k[0]),
        open: parseFloat(k[1]),
        high: parseFloat(k[2]),
        low: parseFloat(k[3]),
        close: parseFloat(k[4]),
        volume: parseFloat(k[5]),
    }));

    const close = formattedKlines.map(k => k.close);

    const rsi = ta.RSI(close, config.indicators.rsiPeriod);
    const smaShort = ta.SMA(close, config.indicators.smaShortPeriod);
    const smaLong = ta.SMA(close, config.indicators.smaLongPeriod);
    const macdResult = ta.MACD(
        close,
        config.indicators.macd.fastPeriod,
        config.indicators.macd.slowPeriod,
        config.indicators.macd.signalPeriod
    );
    const atr = ta.ATR(formattedKlines, config.indicators.atrPeriod);

    const latestIndex = formattedKlines.length - 1;

    return {
        // dataframe is no longer used, but we can keep a similar structure
        klines: formattedKlines,
        latest: {
            price: close[latestIndex],
            rsi: rsi[latestIndex],
            smaShort: smaShort[latestIndex],
            smaLong: smaLong[latestIndex],
            macd: macdResult.macd[latestIndex] ? {
                MACD: macdResult.macd[latestIndex],
                signal: macdResult.signal[latestIndex],
                histogram: macdResult.histogram[latestIndex],
            } : null,
            atr: atr[latestIndex],
        }
    };
}

export function formatMarketContext(state, indicators) {
    const { price, rsi, smaShort, smaLong, macd, atr } = indicators;
    let context = `Current Price: ${price.toFixed(2)}
`;
    context += `RSI(${config.indicators.rsiPeriod}): ${rsi.toFixed(2)}
`;
    context += `SMA(${config.indicators.smaShortPeriod}): ${smaShort.toFixed(2)}
`;
    context += `SMA(${config.indicators.smaLongPeriod}): ${smaLong.toFixed(2)}
`;
    context += `ATR(${config.indicators.atrPeriod}): ${atr.toFixed(4)} (Volatility Measure)
`;

    if (state.inPosition) {
        const pnl = (price - state.entryPrice) * state.quantity * (state.positionSide === 'Buy' ? 1 : -1);
        context += `
CURRENTLY IN POSITION:
        - Side: ${state.positionSide}
        - Entry Price: ${state.entryPrice}
        - Quantity: ${state.quantity}
        - Unrealized P/L: ${pnl.toFixed(2)} USDT`;
    } else {
        context += "\nCURRENTLY FLAT (No open position).";
    }
    return context;
}

export function calculatePositionSize(balance, currentPrice, stopLossPrice) {
    const riskAmount = balance * (config.riskPercentage / 100);
    const riskPerShare = Math.abs(currentPrice - stopLossPrice);
    if (riskPerShare === 0) return 0;
    const quantity = riskAmount / riskPerShare;
    return parseFloat(quantity.toFixed(3)); // Adjust precision for BTC
}

export function determineExitPrices(entryPrice, side) {
    const slDistance = entryPrice * (config.stopLossPercentage / 100);
    const tpDistance = slDistance * config.riskToRewardRatio;

    let stopLoss, takeProfit;
    if (side === 'Buy') {
        stopLoss = entryPrice - slDistance;
        takeProfit = entryPrice + tpDistance;
    } else { // Sell
        stopLoss = entryPrice + slDistance;
        takeProfit = entryPrice - tpDistance;
    }
    return { stopLoss: parseFloat(stopLoss.toFixed(2)), takeProfit: parseFloat(takeProfit.toFixed(2)) };
}
