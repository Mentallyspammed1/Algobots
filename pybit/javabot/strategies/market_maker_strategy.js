const { Decimal } = require('decimal.js');
const { sleep, round_qty, round_price } = require('../utils/utils.js');

class MarketMakerStrategy {
    constructor(config, logger, bybitClient) {
        this.config = config;
        this.logger = logger;
        this.bybitClient = bybitClient;
        this.botState = {
            lastPrice: null,
            priceHistory: [],
            netPosition: new Decimal(0),
            averageEntryPrice: new Decimal(0),
            activeOrders: new Set(),
            isPaused: false,
            realizedPnL: new Decimal(0),
            unrealizedPnL: new Decimal(0),
            totalPnL: new Decimal(0),
            tradeCount: 0,
        };
        this.pnlCsvWriter = null; // Placeholder for CSV writer
    }

    // --- Market Data --- (Adapted from market-maker.js)
    async getOrderBook() {
        try {
            const res = await this.bybitClient.restClient.getOrderbook({
                category: 'linear',
                symbol: this.config.trading.symbols[0],
                limit: 5
            });

            if (res.retCode !== 0) {
                throw new Error(res.retMsg || 'Bybit error');
            }
            if (!res.result || typeof res.result !== 'object') {
                throw new Error('Invalid response structure');
            }
            const rawBids = res.result.b || [];
            const rawAsks = res.result.a || [];

            if (rawBids.length === 0 && rawAsks.length === 0) {
                this.logger.warn('Received an empty order book from Bybit API.');
                // Fallback simulation
                const mid = this.botState.lastPrice || new Decimal(70000);
                const bid = { price: mid.times(0.999), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) };
                const ask = { price: mid.times(1.001), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) };
                return {
                    bids: [bid], asks: [ask],
                    midPrice: mid,
                    imbalance: new Decimal(0),
                };
            }

            const bids = rawBids.map(b => ({ price: new Decimal(b[0]), size: new Decimal(b[1]) }))
                .filter(b => b.price.isFinite() && b.size.isFinite() && b.price.gt(0) && b.size.gt(0));
            const asks = rawAsks.map(a => ({ price: new Decimal(a[0]), size: new Decimal(a[1]) }))
                .filter(a => a.price.isFinite() && a.size.isFinite() && a.price.gt(0) && a.size.gt(0));

            if (bids.length === 0 || asks.length === 0) {
                this.logger.warn(`One side empty. Simulating for continuity. Bids: ${bids.length}, Asks: ${asks.length}`);
                const mid = this.botState.lastPrice || new Decimal(70000);
                if (bids.length === 0) bids.push({ price: mid.times(0.999), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) });
                if (asks.length === 0) asks.push({ price: mid.times(1.001), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) });
            }

            const midPrice = (bids[0].price.plus(asks[0].price)).dividedBy(2);
            const imbalance = (bids[0].size.minus(asks[0].size)).dividedBy(bids[0].size.plus(asks[0].size));
            return { bids, asks, midPrice, imbalance };
        } catch (err) {
            this.logger.error(`Order book fetch failed: ${err.message}`);
            if (!this.botState.lastPrice) throw err; // If no fallback price, rethrow
            this.logger.warn('Using fallback book due to failure.');
            const midPrice = this.botState.lastPrice;
            return {
                bids: [{ price: midPrice.times(0.999), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) }],
                asks: [{ price: midPrice.times(1.001), size: new Decimal(this.config.strategies.marketMaker.minOrderSize) }],
                midPrice,
                imbalance: new Decimal(0),
            };
        }
    }

    getVolatility() {
        if (this.botState.priceHistory.length < this.config.strategies.marketMaker.volatilityWindow) return new Decimal(0.001);
        const recent = this.botState.priceHistory.slice(-this.config.strategies.marketMaker.volatilityWindow);
        const changes = recent.map((p, i) => i > 0 ? p.minus(recent[i - 1]).abs().dividedBy(recent[i - 1]) : new Decimal(0));
        const avgChange = changes.reduce((a, b) => a.plus(b), new Decimal(0)).dividedBy(Math.max(1, changes.length - 1));
        return Decimal.max(0, avgChange);
    }

    // --- PNL & Fill Simulation --- (Adapted from market-maker.js)
    updatePnL(side, qty, price) {
        const oldPos = this.botState.netPosition;
        const tradeDelta = side === 'buy' ? qty : qty.negated();
        const newPos = oldPos.plus(tradeDelta);

        if (!oldPos.isZero() && oldPos.s !== newPos.s) { // Sign change
            const closeQty = Decimal.min(oldPos.abs(), tradeDelta.abs());
            const closePnl = (price.minus(this.botState.averageEntryPrice)).times(oldPos.negated());
            this.botState.realizedPnL = this.botState.realizedPnL.plus(closePnl);
            this.botState.tradeCount += 1;
            this.logger.info(`[PnL] Realized ${closePnl.toFixed(6)}`);
        }

        if (newPos.isZero()) {
            this.botState.averageEntryPrice = new Decimal(0);
        } else if (oldPos.s === newPos.s || oldPos.isZero()) {
            this.botState.averageEntryPrice = (this.botState.averageEntryPrice.times(oldPos)).plus(price.times(tradeDelta)).dividedBy(newPos);
        } else {
            this.botState.averageEntryPrice = price;
        }
        this.botState.netPosition = newPos;
        if (!this.botState.netPosition.isZero() && this.botState.lastPrice) {
            this.botState.unrealizedPnL = (this.botState.lastPrice.minus(this.botState.averageEntryPrice)).times(this.botState.netPosition);
        } else {
            this.botState.unrealizedPnL = new Decimal(0);
        }
        this.botState.totalPnL = this.botState.realizedPnL.plus(this.botState.unrealizedPnL);
        // pnlCsvWriter.writeRecords - integrate with PerformanceTracker
    }

    simulateFillEvent(orderSize) {
        if (this.config.api.dryRun) {
            if (Math.random() > this.config.strategies.marketMaker.fillProbability) return;
            const side = Math.random() > 0.5 ? 'buy' : 'sell';
            const qty = orderSize;
            const last = this.botState.lastPrice || new Decimal(0);
            const price = last.times(new Decimal(1).plus(new Decimal(Math.random() - 0.5).times(2).times(this.config.strategies.marketMaker.slippageFactor)));
            this.logger.info(`[DRY RUN] Simulated ${side.toUpperCase()} fill`);
            this.updatePnL(side, qty, price);
        }
    }

    // --- Order & Risk Management --- (Adapted from market-maker.js)
    async placeOrder(side, price, qty) {
        const displayPrice = price.toFixed(this.config.trade_management.price_precision);
        const displayQty = qty.toFixed(this.config.trade_management.order_precision);
        if (this.config.api.dryRun) {
            const orderId = `DRY_${Date.now()}_${Math.floor(Math.random() * 10000)}`;
            this.logger.info(`[DRY RUN] Would place ${side.toUpperCase()} order`);
            this.botState.activeOrders.add(orderId);
            return orderId;
        }
        // Use bybitClient.placeOrder
        try {
            const res = await this.bybitClient.placeOrder({
                category: 'linear',
                symbol: this.config.trading.symbols[0],
                side: side.toUpperCase(),
                orderType: 'Limit',
                qty: qty.toString(),
                price: price.toString(),
                timeInForce: 'GTC',
                reduceOnly: false,
                closeOnTrigger: false,
            });
            if (res) {
                const orderId = res.orderId;
                this.botState.activeOrders.add(orderId);
                this.logger.info(`Placed ${side} order`);
                return orderId;
            } else {
                this.logger.error(`Failed to place ${side} order`);
                return null;
            }
        } catch (err) {
            this.logger.error(`Exception placing ${side} order: ${err.message}`);
            return null;
        }
    }

    async cancelAllOrders() {
        if (this.config.api.dryRun) {
            this.logger.info(`[DRY RUN] Would cancel ${this.botState.activeOrders.size} orders`);
            this.botState.activeOrders.clear();
            return true;
        }
        try {
            const res = await this.bybitClient.cancelAllOpenOrders(this.config.trading.symbols[0]);
            if (res) {
                this.logger.info('All orders canceled');
                this.botState.activeOrders.clear();
                return true;
            } else {
                this.logger.error('Failed to cancel all orders');
                return false;
            }
        } catch (err) {
            this.logger.error(`Exception during cancel-all: ${err.message}`);
            return false;
        }
    }

    checkRiskLimits() {
        const maxNetPosition = new Decimal(this.config.strategies.marketMaker.maxNetPosition);
        if (this.config.strategies.marketMaker.stopOnLargePos && this.botState.netPosition.abs().gte(maxNetPosition)) {
            if (!this.botState.isPaused) {
                this.botState.isPaused = true;
                this.logger.warn(`⚠️ POSITION RISK TRIGGERED: Net ${this.botState.netPosition.toFixed(6)} ≥ ${maxNetPosition} → PAUSED`);
                // sendTermuxSMS - integrate with AlertSystem
            }
            return false;
        }
        if (this.botState.isPaused && this.botState.netPosition.abs().lt(maxNetPosition.times(0.8))) {
            this.botState.isPaused = false;
            this.logger.info(`✅ RISK CLEARED: Net ${this.botState.netPosition.toFixed(6)} < ${maxNetPosition.times(0.8)} → RESUMED`);
            // sendTermuxSMS - integrate with AlertSystem
        }
        return true;
    }

    // --- Refresh Cycle --- (Adapted from market-maker.js)
    async refreshOrders() {
        if (this.botState.isShuttingDown || this.botState.isPaused) {
            this.logger.info('Market maker paused or shutting down. Skipping refresh.');
            return;
        }
        try {
            const { bids, asks, midPrice, imbalance } = await this.getOrderBook();
            this.botState.lastPrice = midPrice;
            // const analysis = analyzeOrderBook(bids, asks, midPrice); // Integrate with Dashboard/UI
            // displayOrderBook(bids, asks, midPrice, analysis); // Integrate with Dashboard/UI

            const vol = this.getVolatility();
            const volatilitySpread = vol.times(this.config.strategies.marketMaker.volatilitySpreadFactor);
            const positionSkew = (this.botState.netPosition.dividedBy(this.config.strategies.marketMaker.maxNetPosition)).times(this.config.strategies.marketMaker.positionSkewFactor);
            const imbalanceSpread = imbalance.times(this.config.strategies.marketMaker.imbalanceSpreadFactor);
            
            const bidSpreadBase = new Decimal(this.config.strategies.marketMaker.bidSpreadBase);
            const askSpreadBase = new Decimal(this.config.strategies.marketMaker.askSpreadBase);

            const bidSpread = Decimal.max(0.00005, bidSpreadBase.plus(volatilitySpread).plus(Decimal.max(0, positionSkew)).plus(imbalanceSpread));
            const askSpread = Decimal.max(0.00005, askSpreadBase.plus(volatilitySpread).minus(Decimal.min(0, positionSkew)).minus(imbalanceSpread));
            
            const baseBidPrice = midPrice.times(new Decimal(1).minus(bidSpread));
            const baseAskPrice = midPrice.times(new Decimal(1).plus(askSpread));

            let orderSize = new Decimal(this.config.strategies.marketMaker.minOrderSize);
            if (!this.config.strategies.marketMaker.orderSizeFixed) {
                orderSize = orderSize.times(new Decimal(1).plus(vol.times(this.config.strategies.marketMaker.volatilityFactor)));
                orderSize = orderSize.times(new Decimal(1).plus(imbalance.abs().times(this.config.strategies.marketMaker.imbalanceOrderSizeFactor)));
            }
            orderSize = Decimal.max(this.config.strategies.marketMaker.minOrderSize, Decimal.min(orderSize, new Decimal(0.01)));

            this.logger.info(`📊 Refreshing orders`);

            await this.cancelAllOrders();
            const tasks = [];
            const gridSpacing = new Decimal(this.config.strategies.marketMaker.gridSpacingBase).times(new Decimal(1).plus(vol.times(0.5)));
            for (let i = 0; i < this.config.strategies.marketMaker.maxOrdersPerSide; i++) {
                tasks.push(this.placeOrder('buy', baseBidPrice.times(new Decimal(1).minus(new Decimal(i).times(gridSpacing))), orderSize));
                tasks.push(this.placeOrder('sell', baseAskPrice.times(new Decimal(1).plus(new Decimal(i).times(gridSpacing))), orderSize));
            }
            await Promise.all(tasks);
            this.simulateFillEvent(orderSize);
            this.checkRiskLimits();
            this.logger.debug('Order refresh completed');
        } catch (err) {
            this.logger.error(`❌ Refresh failed: ${err.message}`);
            // sendTermuxSMS - integrate with AlertSystem
        }
    }
}

module.exports = MarketMakerStrategy;
