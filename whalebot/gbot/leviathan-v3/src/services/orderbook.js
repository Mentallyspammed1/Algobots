/**
 * Manages a local copy of the order book, processing updates and calculating liquidity metrics.
 * Ported from Leviathan v2.9.
 */
export class LocalOrderBook {
    /**
     * @param {number} [depth=20] - The maximum number of levels to consider for metrics calculation.
     */
    constructor(depth = 20) {
        this.bids = new Map();
        this.asks = new Map();
        this.ready = false;
        this.depth = depth;
        this.metrics = {
            wmp: 0, // Weighted Mid-Price
            spread: 0,
            bidWall: 0,
            askWall: 0,
            skew: 0,
            prevBidWall: 0,
            prevAskWall: 0,
            wallStatus: 'Stable' // 'Stable', 'BID_WALL_BROKEN', 'ASK_WALL_BROKEN', 'BID_SUPPORT', 'ASK_RESISTANCE', 'BALANCED'
        };
    }

    _processLevels(levels, map) {
        if (!levels) return;
        for (const [priceStr, sizeStr] of levels) {
            const p = parseFloat(priceStr);
            const s = parseFloat(sizeStr);
            if (s === 0) {
                map.delete(p);
            } else {
                map.set(p, s);
            }
        }
    }

    /**
     * Updates the order book with new data. Can be a snapshot or a delta update.
     * @param {object} data - The incoming order book data. Expected to have 'b' (bids) and 'a' (asks) properties.
     * @param {string} type - The type of update, 'snapshot' or 'delta'.
     */
    update(data, type) {
        const isSnapshot = type === 'snapshot';
        if (isSnapshot) {
            this.bids.clear();
            this.asks.clear();
        }
        
        if (!this.ready && !isSnapshot) return;

        this._processLevels(data.b, this.bids);
        this._processLevels(data.a, this.asks);
        
        if (isSnapshot) {
            this.ready = true;
        }

        this.calculateMetrics();
    }

    getBestBidAsk() {
        if (!this.ready || this.bids.size === 0 || this.asks.size === 0) {
            return { bid: 0, ask: 0 };
        }
        return {
            bid: Math.max(...this.bids.keys()),
            ask: Math.min(...this.asks.keys())
        };
    }

    calculateMetrics() {
        if (!this.ready || this.bids.size < 1 || this.asks.size < 1) return;

        const bids = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, this.depth);
        const asks = Array.from(this.asks.entries()).sort((a, b) => a[0] - b[0]).slice(0, this.depth);

        if (bids.length === 0 || asks.length === 0) return;

        const bestBid = bids[0][0];
        const bestBidSize = bids[0][1];
        const bestAsk = asks[0][0];
        const bestAskSize = asks[0][1];

        // Weighted Mid-Price
        const totalTopLevelVolume = bestBidSize + bestAskSize;
        this.metrics.wmp = totalTopLevelVolume > 0
            ? ((bestBid * bestAskSize) + (bestAsk * bestBidSize)) / totalTopLevelVolume
            : (bestBid + bestAsk) / 2;

        this.metrics.spread = bestAsk - bestBid;

        const currentBidWall = Math.max(0, ...bids.map(b => b[1]));
        const currentAskWall = Math.max(0, ...asks.map(a => a[1]));

        // Wall Exhaustion Logic
        if (this.metrics.prevBidWall > 0 && currentBidWall < this.metrics.prevBidWall * 0.7) {
            this.metrics.wallStatus = 'BID_WALL_BROKEN';
        } else if (this.metrics.prevAskWall > 0 && currentAskWall < this.metrics.prevAskWall * 0.7) {
            this.metrics.wallStatus = 'ASK_WALL_BROKEN';
        } else {
            this.metrics.wallStatus = currentBidWall > currentAskWall * 1.5 ? 'BID_SUPPORT' :
                                   (currentAskWall > currentBidWall * 1.5 ? 'ASK_RESISTANCE' : 'BALANCED');
        }

        this.metrics.prevBidWall = currentBidWall;
        this.metrics.prevAskWall = currentAskWall;
        this.metrics.bidWall = currentBidWall;
        this.metrics.askWall = currentAskWall;

        const totalBidVol = bids.reduce((acc, val) => acc + val[1], 0);
        const totalAskVol = asks.reduce((acc, val) => acc + val[1], 0);
        const totalVol = totalBidVol + totalAskVol;
        this.metrics.skew = totalVol === 0 ? 0 : (totalBidVol - totalAskVol) / totalVol;
    }

    getAnalysis() {
        return this.metrics;
    }
}
