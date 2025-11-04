
import { Orderbook, OrderbookAnalysis, LiquidityLevel } from '../types';

/**
 * Calculates the mean and standard deviation of a list of numbers.
 * @param numbers - The array of numbers to analyze.
 * @returns An object containing the mean and standard deviation.
 */
const getStats = (numbers: number[]): { mean: number; stdDev: number } => {
    if (numbers.length === 0) {
        return { mean: 0, stdDev: 0 };
    }
    const mean = numbers.reduce((acc, val) => acc + val, 0) / numbers.length;
    const stdDev = Math.sqrt(
        numbers.map(x => Math.pow(x - mean, 2)).reduce((a, b) => a + b) / numbers.length
    );
    return { mean, stdDev };
};

/**
 * Analyzes a deep order book to find significant liquidity levels (buy/sell walls).
 * These are price levels where the volume of orders is statistically significant.
 * @param orderbook - The deep order book data from Bybit.
 * @returns An OrderbookAnalysis object containing lists of support and resistance levels.
 */
export const findLiquidityLevels = (orderbook: Orderbook): OrderbookAnalysis => {
    const bids = orderbook.bids.map(([price, size]) => ({ price: parseFloat(price), size: parseFloat(size) }));
    const asks = orderbook.asks.map(([price, size]) => ({ price: parseFloat(price), size: parseFloat(size) }));

    const bidSizes = bids.map(b => b.size);
    const askSizes = asks.map(a => a.size);

    const bidStats = getStats(bidSizes);
    const askStats = getStats(askSizes);

    // A significant liquidity level is defined as having a volume greater than
    // the mean plus one standard deviation. This finds outliers.
    const bidThreshold = bidStats.mean + (bidStats.stdDev * 1.0);
    const askThreshold = askStats.mean + (askStats.stdDev * 1.0);

    const supportLevels: LiquidityLevel[] = bids
        .filter(bid => bid.size > bidThreshold)
        .map(bid => ({
            price: bid.price,
            volume: bid.size,
            type: 'support',
        }));

    const resistanceLevels: LiquidityLevel[] = asks
        .filter(ask => ask.size > askThreshold)
        .map(ask => ({
            price: ask.price,
            volume: ask.size,
            type: 'resistance',
        }));

    return {
        supportLevels,
        resistanceLevels,
    };
};
