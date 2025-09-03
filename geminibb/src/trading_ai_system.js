import 'dotenv/config';
import { config } from './config.js';
import BybitAPI from './api/bybit_api.js';
import BybitWebSocket from './api/bybit_websocket.js';
import GeminiAPI from './api/gemini_api.js';
import { loadState, saveState, defaultState } from './utils/state_manager.js';
import { calculateIndicators, formatMarketContext, calculatePositionSize, determineExitPrices } from './core/trading_logic.js';
import { applyRiskPolicy } from './core/risk_policy.js';
import logger from './utils/logger.js';

class TradingAiSystem {
    constructor() {
        this.bybitApi = new BybitAPI(process.env.BYBIT_API_KEY, process.env.BYBIT_API_SECRET);
        this.geminiApi = new GeminiAPI(process.env.GEMINI_API_KEY);
        this.isProcessing = false; // Lock to prevent concurrent runs

        // Execution/risk knobs with safe defaults (overridable via config.js)
        this.hedgeMode = Boolean(config?.hedgeMode ?? false);             // dual-side positions
        this.flipCooldownMs = Number(config?.flipCooldownMs ?? 30_000);   // avoid rapid flip-flops
        this.maxSpreadPct = Number(config?.maxSpreadPct ?? 0.0015);       // 15 bps guard (if spread available)
        this.dryRun = Boolean(config?.dryRun ?? false);                   // if true, skip placing/closing orders

        this._lastFlipAt = 0; // global cooldown; customize per symbol if you trade many
        this._printedBanner = false;
    }

    async handleNewCandle() {
        if (this.isProcessing) {
            logger.warn("Already processing a cycle, skipping new candle trigger.");
            return;
        }
        this.isProcessing = true;

        const tStart = Date.now();
        if (!this._printedBanner) {
            logger.info("Starting Trading AI System with config: " + JSON.stringify({
                symbol: config.symbol,
                interval: config.interval,
                hedgeMode: this.hedgeMode,
                flipCooldownMs: this.flipCooldownMs,
                maxSpreadPct: this.maxSpreadPct,
                dryRun: this.dryRun
            }));
            this._printedBanner = true;
        }

        logger.info("=========================================");
        logger.info("Handling new confirmed candle...");

        let cycleSummary = { decision: 'HOLD', reason: 'init', action: 'HOLD' };

        try {
            // 1) Load State & Fetch Data
            const state = await loadState();
            const klines = await this.bybitApi.getHistoricalMarketData(config.symbol, config.interval);
            if (!klines || !Array.isArray(klines) || klines.length === 0) throw new Error("Failed to fetch market data.");

            // 2) Indicators & Context
            const indicators = calculateIndicators(klines);
            const latest = indicators?.latest;
            if (!latest || typeof latest.price !== 'number') {
                throw new Error("Indicators missing latest price.");
            }

            // Optional market guards (spread/liquidity) if API supports it
            const spreadPct = await this._maybeComputeLiveSpreadPct();
            if (spreadPct != null && spreadPct > this.maxSpreadPct) {
                logger.warn(`Spread too wide (${(spreadPct * 100).toFixed(3)} bps > ${(this.maxSpreadPct * 100).toFixed(3)} bps). Skipping trade.`);
                cycleSummary = { decision: 'HOLD', reason: 'Spread too wide', action: 'HOLD' };
                return;
            }

            // 3) Build AI context and get decision
            const marketContext = formatMarketContext(state, latest);
            const aiDecision = await this.geminiApi.getTradeDecision(marketContext);

            // 4) Apply Risk Policy
            const policyResult = applyRiskPolicy(aiDecision, latest);
            cycleSummary = { decision: policyResult?.decision ?? 'HOLD', reason: policyResult?.reason ?? 'No reason' };

            if (policyResult.decision === 'HOLD') {
                logger.info(`Decision: HOLD. Reason: ${policyResult.reason}`);
                return;
            }

            const trade = policyResult.trade;
            if (!trade || !trade.name || !trade.args) {
                logger.warn("AI policy returned an invalid trade object; holding.");
                cycleSummary = { decision: 'HOLD', reason: 'Invalid policy trade', action: 'HOLD' };
                return;
            }

            // 5) Execute trade intent safely
            if (trade.name === 'proposeTrade') {
                await this._executeProposedEntry(state, trade.args, latest);
                cycleSummary.action = 'ENTRY';
                cycleSummary.side = trade.args?.side;
            } else if (trade.name === 'proposeExit') {
                if (state.inPosition) {
                    await this.executeExit(state, trade.args);
                    cycleSummary.action = 'EXIT';
                } else {
                    logger.warn("Exit proposed but no open position; holding.");
                    cycleSummary.action = 'HOLD';
                }
            } else {
                logger.warn(`AI proposed an unknown action '${trade.name}'; holding.`);
                cycleSummary.action = 'HOLD';
            }

        } catch (error) {
            logger.exception(error);
            cycleSummary = { decision: 'HOLD', reason: 'Exception during cycle', action: 'HOLD' };
        } finally {
            const wallMs = Date.now() - tStart;
            this.isProcessing = false;
            logger.info(`Processing cycle finished. Summary=${JSON.stringify(cycleSummary)} wall=${wallMs}ms`);
            logger.info("=========================================\n");
        }
    }

    // --- Entry flow with conflict resolution and cooldown ---
    async _executeProposedEntry(state, args, indicators) {
        const side = String(args?.side || '').toUpperCase();
        const reasoning = args?.reasoning || 'No reasoning';
        logger.info(`Executing ENTRY proposal: ${side} - ${reasoning}`);

        if (side !== 'BUY' && side !== 'SELL') {
            logger.warn("Invalid side in proposal. Holding.");
            return;
        }

        // Cooldown to avoid rapid flip-flops
        if (Date.now() - this._lastFlipAt < this.flipCooldownMs) {
            const msLeft = this.flipCooldownMs - (Date.now() - this._lastFlipAt);
            logger.warn(`Flip rejected due to cooldown. ${msLeft}ms remaining.`);
            return;
        }

        const price = indicators.price;
        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");

        // Determine exits (SL/TP) and position size
        const { stopLoss, takeProfit } = determineExitPrices(price, side);
        const quantity = calculatePositionSize(balance, price, stopLoss);

        if (!Number.isFinite(quantity) || quantity <= 0) {
            logger.error("Calculated quantity is invalid (<= 0). Aborting trade.");
            return;
        }

        // Hedge vs One-way logic
        if (!this.hedgeMode) {
            // One-way: flatten if opposite side already open
            const current = await this._getLivePositionSideSafe(config.symbol);
            if (current && current !== 'FLAT' && current !== this._desiredSide(side)) {
                logger.info(`Flattening existing ${current} position before opening ${this._desiredSide(side)} (one-way mode).`);
                if (this.dryRun) {
                    logger.info("[DRY-RUN] Would close existing position before flip.");
                } else {
                    const closeId = this._genClientOrderId('CLOSE');
                    const closed = await this.bybitApi.closePosition(config.symbol, current, { clientOrderId: closeId });
                    if (!closed) {
                        logger.error("Close position failed; aborting flip.");
                        return;
                    }
                }
            }
        }

        // Place entry
        await this.executeEntry({ side, reasoning }, indicators, { stopLoss, takeProfit, quantity });
        this._lastFlipAt = Date.now();
    }

    // --- Public entry executor (kept compatible) ---
    async executeEntry(args, indicators, precomputed = undefined) {
        const { side } = args;
        const { price } = indicators;

        const balance = await this.bybitApi.getAccountBalance();
        if (!balance) throw new Error("Could not retrieve account balance.");

        // Use provided SL/TP/qty if passed by caller; otherwise compute
        let stopLoss, takeProfit, quantity;
        if (precomputed) {
            ({ stopLoss, takeProfit, quantity } = precomputed);
        } else {
            const exits = determineExitPrices(price, side);
            stopLoss = exits.stopLoss;
            takeProfit = exits.takeProfit;
            quantity = calculatePositionSize(balance, price, stopLoss);
        }

        if (!Number.isFinite(quantity) || quantity <= 0) {
            logger.error("Calculated quantity is zero or less. Aborting trade.");
            return;
        }

        const clientOrderId = this._genClientOrderId('ENTRY');

        if (this.dryRun) {
            logger.info(`[DRY-RUN] Would place ${side} order: qty=${quantity}, TP=${takeProfit}, SL=${stopLoss}, cid=${clientOrderId}`);
            await saveState({
                inPosition: true,
                positionSide: side,
                entryPrice: price,
                quantity: quantity,
                orderId: `dryrun-${clientOrderId}`,
            });
            logger.info(`(DRY-RUN) Entered ${side} position.`);
            return;
        }

        const orderResult = await this.bybitApi.placeOrder({
            symbol: config.symbol,
            side,
            qty: quantity,
            takeProfit,
            stopLoss,
            clientOrderId,
            hedge: this.hedgeMode === true
        });

        if (orderResult) {
            await saveState({
                inPosition: true,
                positionSide: side,
                entryPrice: price,
                quantity: quantity,
                orderId: orderResult.orderId || clientOrderId,
            });
            logger.info(`Successfully entered ${side} position. Order ID: ${orderResult.orderId || clientOrderId}`);
        }
    }

    // --- Exit flow (compatible) ---
    async executeExit(state, args) {
        const reasoning = args?.reasoning || 'No reasoning';
        logger.info(`Executing EXIT: ${reasoning}`);

        const clientOrderId = this._genClientOrderId('EXIT');

        if (this.dryRun) {
            logger.info(`[DRY-RUN] Would close ${state.positionSide} position. cid=${clientOrderId}`);
            await saveState({ ...defaultState });
            logger.info("(DRY-RUN) Closed position.");
            return;
        }

        const closeResult = await this.bybitApi.closePosition(config.symbol, state.positionSide, { clientOrderId });
        if (closeResult) {
            await saveState({ ...defaultState });
            logger.info(`Successfully closed position. Order ID: ${closeResult.orderId || clientOrderId}`);
        }
    }

    start() {
        logger.info("Starting Trading AI System...");
        const ws = new BybitWebSocket(() => this.handleNewCandle());
        ws.connect();
        // Optional: run once on startup without waiting for the first candle
        setTimeout(() => this.handleNewCandle(), 2000);
    }

    // --- Helpers ---

    _genClientOrderId(tag) {
        const ts = Date.now().toString(36);
        const rnd = Math.random().toString(36).slice(2, 8);
        return `gbb:${config.symbol}:${tag}:${ts}:${rnd}`;
        // This enables idempotency on retries if your Bybit wrapper forwards clientOrderId/orderLinkId
    }

    _desiredSide(buySell) {
        return buySell === 'BUY' ? 'LONG' : 'SHORT';
    }

    async _getLivePositionSideSafe(symbol) {
        try {
            if (typeof this.bybitApi.getPosition === 'function') {
                const pos = await this.bybitApi.getPosition(symbol);
                // Normalize: expect { side: 'LONG'|'SHORT', size: number } or null
                if (pos && pos.size > 0 && (pos.side === 'LONG' || pos.side === 'SHORT')) {
                    return pos.side;
                }
            }
        } catch (e) {
            logger.warn("getPosition failed (non-fatal): " + (e?.message || e));
        }
        return 'FLAT';
    }

    async _maybeComputeLiveSpreadPct() {
        try {
            // If your API exposes a best bid/ask endpoint, use it.
            // Fallbacks are no-ops to preserve compatibility.
            if (typeof this.bybitApi.getTicker === 'function') {
                const t = await this.bybitApi.getTicker(config.symbol);
                const bid = Number(t?.bid);
                const ask = Number(t?.ask);
                if (Number.isFinite(bid) && Number.isFinite(ask) && ask > 0) {
                    return (ask - bid) / ((ask + bid) / 2);
                }
            } else if (typeof this.bybitApi.getOrderBook === 'function') {
                const ob = await this.bybitApi.getOrderBook(config.symbol);
                const bestBid = Number(ob?.bids?.[0]?.price);
                const bestAsk = Number(ob?.asks?.[0]?.price);
                if (Number.isFinite(bestBid) && Number.isFinite(bestAsk) && bestAsk > 0) {
                    return (bestAsk - bestBid) / ((bestAsk + bestBid) / 2);
                }
            }
        } catch (e) {
            logger.warn("Spread check failed (ignored): " + (e?.message || e));
        }
        return undefined;
    }
}

// --- Main Execution ---
const tradingSystem = new TradingAiSystem();
tradingSystem.start();