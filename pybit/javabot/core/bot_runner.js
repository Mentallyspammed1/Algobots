const { UNIFIED_CONFIG } = require('../config/unified_config.js');
const BybitClient = require('../clients/bybit_client.js');
const setupLogger = require('../utils/logger.js');
const { sleep, round_qty, round_price } = require('../utils/utils.js');
const { Decimal } = require('decimal.js');
const EhlersSupertrendStrategy = require('../strategies/ehlers_supertrend_strategy.js');
const ChanExitStrategy = require('../strategies/chanexit_strategy.js');
const SQLiteManager = require('../persistence/sqlite_manager.js');
const { Trade } = require('../models/trade_models.js');
const moment = require('moment-timezone'); // For time handling in chanexit logic
const { v4: uuidv4 } = require('uuid');

/**
 * Orchestrates the trading bot's operations, including strategy execution, position management, and risk control.
 */
class BotRunner {
    /**
     * Creates an instance of BotRunner.
     * Initializes configuration, logger, Bybit client, SQLite manager, and the selected trading strategy.
     */
    constructor() {
        this.config = UNIFIED_CONFIG;
        this.logger = setupLogger('bot_runner', this.config.bot.logLevel, [this.config.api.key, this.config.api.secret]);
        this.bybitClient = new BybitClient(this.config);
        this.sqliteManager = new SQLiteManager('scalper_positions.sqlite', this.logger);
        this.equityReference = null; // For emergency stop
        this.lastReconciliationTime = moment.utc();

        // Select strategy based on config or default
        const selectedStrategy = this.config.bot.activeStrategy || 'ehlersSupertrend';
        switch (selectedStrategy) {
            case 'ehlersSupertrend':
                this.strategy = new EhlersSupertrendStrategy(this.config, this.logger);
                this.logger.info("Active Strategy: Ehlers Supertrend");
                break;
            case 'chanExit':
                this.strategy = new ChanExitStrategy(this.config, this.logger, this.bybitClient, this.sqliteManager);
                this.logger.info("Active Strategy: Chandelier Exit");
                break;
            default:
                this.logger.error(`Unknown strategy: ${selectedStrategy}. Defaulting to Ehlers Supertrend.`);
                this.strategy = new EhlersSupertrendStrategy(this.config, this.logger);
        }
    }

    /**
     * Checks if an emergency stop condition is met based on equity drawdown.
     * If the current equity falls below a configured percentage from the reference equity,
     * the bot will initiate an emergency stop.
     * @returns {Promise<boolean>} True if an emergency stop is triggered, false otherwise.
     */
    async _emergencyStop() {
        const currentEquity = await this.bybitClient.getWalletBalance();

        if (this.equityReference === null) {
            this.equityReference = currentEquity;
            this.logger.info(`Initial equity reference set to ${this.equityReference.toFixed(2)} USDT.`);
            return false;
        }

        if (currentEquity.lte(0)) {
            this.logger.warning("Current equity is zero or negative. Cannot calculate drawdown.");
            return false;
        }

        // No drawdown if current equity is not less than reference
        if (currentEquity.gte(this.equityReference)) {
            return false;
        }

        const drawdown = (this.equityReference.minus(currentEquity)).dividedBy(this.equityReference).times(100);
        if (drawdown.gte(this.config.risk.emergencyStopIfDownPct || 15)) {
            this.logger.critical(`!!! EMERGENCY STOP !!! Equity down ${drawdown.toFixed(1)}%. Shutting down bot.`);
            return true;
        }

        return false;
    }

    /**
     * Reconciles open positions between the exchange and the local database.
     * Marks database trades as closed if not found on the exchange, and adds exchange positions to the database if not found locally.
     * @param {object} exchangePositions - An object containing current open positions from the exchange, keyed by symbol.
     * @param {moment.Moment} utcTime - The current UTC time.
     * @returns {Promise<void>} A promise that resolves when reconciliation is complete.
     */
    async _reconcilePositions(exchangePositions, utcTime) {
        const dbTrades = await this.sqliteManager.getOpenTrades();
        const dbPositions = {};
        dbTrades.forEach(trade => {
            dbPositions[trade.symbol] = trade;
        });

        // 1. Mark DB positions as CLOSED if not found on exchange
        for (const symbol in dbPositions) {
            if (!exchangePositions[symbol]) {
                this.logger.warning(`Position for ${symbol} found in DB (ID: ${dbPositions[symbol].id}) but not on exchange. Marking as CLOSED.`);
                const currentKlines = await this.bybitClient.getKlines(symbol, this.config.trading.timeframe, 1);
                const exitPrice = currentKlines ? currentKlines[0].close : dbPositions[symbol].entry_price; // Fallback to entry price
                const pnl = exitPrice.minus(dbPositions[symbol].entry_price).times(dbPositions[symbol].side === 'Buy' ? 1 : -1);
                await this.sqliteManager.updateTradeStatus(dbPositions[symbol].id, 'CLOSED', utcTime.toISOString(), exitPrice, pnl);
            }
        }

        // 2. Add exchange positions to DB if not found in DB
        for (const symbol in exchangePositions) {
            if (!dbPositions[symbol]) {
                this.logger.warning(`Position for ${symbol} found on exchange but not in DB. Adding as RECONCILED.`);
                const exInfo = exchangePositions[symbol];
                const entryPrice = new Decimal(exInfo.avgPrice).gt(0) ? new Decimal(exInfo.avgPrice) : new Decimal(exInfo.markPrice);
                const trade = new Trade({
                    id: uuidv4(),
                    order_id: exInfo.orderId || 'N/A',
                    symbol: symbol,
                    side: exInfo.side,
                    qty: new Decimal(exInfo.size),
                    entry_time: utcTime.toISOString(),
                    entry_price: entryPrice,
                    sl: new Decimal(exInfo.stopLoss || 0),
                    tp: new Decimal(exInfo.takeProfit || 0),
                    status: 'RECONCILED',
                });
                await this.sqliteManager.addTrade(trade);
            }
        }
    }

    /**
     * Manages the exit of an open trade based on various conditions (fixed profit, trailing stop, Fisher Transform flip, time-based).
     * @param {Trade} trade - The trade object from the local database.
     * @param {object|null} exchangePosition - The corresponding position object from the exchange, or null if not found.
     * @param {moment.Moment} utcTime - The current UTC time.
     * @returns {Promise<void>} A promise that resolves when the trade exit management is complete.
     */
    async _manageTradeExit(trade, exchangePosition, utcTime) {
        if (!exchangePosition) {
            this.logger.info(`Position for ${trade.symbol} not found on exchange while managing trade ${trade.id}. Marking as CLOSED in DB tracker.`);
            const currentKlines = await this.bybitClient.getKlines(trade.symbol, this.config.trading.timeframe, 1);
            const currentPrice = currentKlines ? currentKlines[0].close : trade.entry_price;
            const pnl = currentPrice.minus(trade.entry_price).times(trade.side === 'Buy' ? 1 : -1);
            await this.sqliteManager.updateTradeStatus(trade.id, 'CLOSED', utcTime.toISOString(), currentPrice, pnl);
            return;
        }

        const klines = await this.bybitClient.getKlines(trade.symbol, this.config.trading.timeframe, (this.config.strategies.chanExit.maxHoldingCandles || 50) + 5);
        if (!klines || klines.length < 2) {
            this.logger.warning(`Not enough klines for ${trade.symbol} to manage existing trade. Skipping exit check.`);
            return;
        }

        const dfWithIndicators = this.strategy.buildIndicators(klines);
        const lastRow = dfWithIndicators[dfWithIndicators.length - 1];
        const prevRow = dfWithIndicators[dfWithIndicators.length - 2];
        const currentPrice = lastRow.close;

        let reasonToExit = null;

        // Calculate PNL for fixed profit target
        let currentPnlPercentage = new Decimal(0);
        if (trade.entry_price.gt(0)) {
            if (trade.side === 'Buy') {
                currentPnlPercentage = (currentPrice.minus(trade.entry_price)).dividedBy(trade.entry_price);
            } else { // Sell
                currentPnlPercentage = (trade.entry_price.minus(currentPrice)).dividedBy(trade.entry_price);
            }
        }

        // Fixed Profit Target Exit
        if (this.config.strategies.chanExit.fixedProfitTargetPct.gt(0) && currentPnlPercentage.gte(this.config.strategies.chanExit.fixedProfitTargetPct)) {
            reasonToExit = `Fixed Profit Target (${(this.config.strategies.chanExit.fixedProfitTargetPct.times(100)).toFixed(1)}%) reached (Current PnL: ${(currentPnlPercentage.times(100)).toFixed(1)}%)`;
        }

        // Chandelier Exit (Trailing Stop equivalent, dynamic update if active)
        let newSlPrice = trade.sl; // Start with current SL in DB
        if (this.config.strategies.chanExit.trailingStopActive) {
            let chSl;
            if (trade.side === 'Buy') {
                chSl = lastRow.ch_long;
                if (chSl.gt(newSlPrice)) { // Only trail SL upwards
                    newSlPrice = chSl;
                }
            } else if (trade.side === 'Sell') {
                chSl = lastRow.ch_short;
                if (chSl.lt(newSlPrice)) { // Only trail SL downwards
                    newSlPrice = chSl;
                }
            }

            const instrumentInfo = await this.bybitClient.restClient.getInstrumentsInfo({ category: this.config.api.category, symbol: trade.symbol });
            const pricePrecision = instrumentInfo.result.list[0].priceFilter.tickSize.split('.')[1]?.length || 0;
            newSlPrice = round_price(newSlPrice, pricePrecision);

            // Only modify if SL moved significantly
            if (newSlPrice.minus(trade.sl).abs().dividedBy(trade.sl).gt(0.0001)) {
                await this.bybitClient.setTradingStop(trade.symbol, round_price(trade.tp, pricePrecision), newSlPrice);
                await this.sqliteManager.updateTradeStatus(trade.id, trade.status, null, null, null, newSlPrice); // Update SL in DB
                this.logger.debug(`[${trade.symbol}] Trailing Stop Loss updated to ${newSlPrice.toFixed(4)}.`);
                trade.sl = newSlPrice; // Update for current check
            }

            // Check if price hit the *current* effective stop loss (either initial or trailed)
            if (trade.side === 'Buy' && currentPrice.lte(trade.sl)) {
                reasonToExit = `Stop Loss hit (current price ${currentPrice.toFixed(4)} <= SL ${trade.sl.toFixed(4)})`;
            } else if (trade.side === 'Sell' && currentPrice.gte(trade.sl)) {
                reasonToExit = `Stop Loss hit (current price ${currentPrice.toFixed(4)} >= SL ${trade.sl.toFixed(4)})`;
            }
        }

        // Fisher Transform Flip Early Exit
        if (reasonToExit === null && this.config.strategies.chanExit.useFisherExit) {
            if (trade.side === 'Buy' && lastRow.fisher.lt(0) && prevRow.fisher.gte(0)) {
                reasonToExit = `Fisher Transform (bearish flip: ${lastRow.fisher.toFixed(2)})`;
            } else if (trade.side === 'Sell' && lastRow.fisher.gt(0) && prevRow.fisher.lte(0)) {
                reasonToExit = `Fisher Transform (bullish flip: ${lastRow.fisher.toFixed(2)})`;
            }
        }

        // Time-based Exit
        const entryDt = moment.utc(trade.entry_time);
        const elapsedMinutes = utcTime.diff(entryDt, 'minutes');
        const elapsedCandles = elapsedMinutes / this.config.trading.timeframe;
        if (reasonToExit === null && elapsedCandles >= (this.config.strategies.chanExit.maxHoldingCandles || 50)) {
            reasonToExit = `Max holding candles (${this.config.strategies.chanExit.maxHoldingCandles}) exceeded`;
        }

        if (reasonToExit) {
            this.logger.info(`Closing ${trade.side} position for ${trade.symbol} due to: ${reasonToExit}`);
            await this.bybitClient.cancelAllOpenOrders(trade.symbol);
            await sleep(500); // 0.5 seconds
            await this.bybitClient.closePosition(trade.symbol);

            const pnl = currentPrice.minus(trade.entry_price).times(trade.side === 'Buy' ? 1 : -1);
            await this.sqliteManager.updateTradeStatus(trade.id, 'CLOSED', utcTime.toISOString(), currentPrice, pnl);
            this.logger.info(`Trade ${trade.id} for ${trade.symbol} marked as CLOSED in DB tracker. PNL: ${pnl.toFixed(2)} USDT`);
        }
    }

    /**
     * The main loop of the trading bot.
     * Continuously checks for emergency stop conditions, reconciles positions, manages trade exits, and generates/executes new signals.
     * @returns {Promise<void>} A promise that resolves when the bot stops running (e.g., due to an emergency stop).
     */
    async run() {
        this.logger.info(`Pyrmethus awakens the Trading Bot! Active Strategy: ${this.config.bot.activeStrategy}`);
        await this.sqliteManager.initialize();

        while (true) {
            const localTime = moment().tz(this.config.bot.timezone);
            const utcTime = moment.utc();
            this.logger.info(`Local Time: ${localTime.format('YYYY-MM-DD HH:mm:ss')} | UTC Time: ${utcTime.format('YYYY-MM-DD HH:mm:ss')}`);

            if (await this._emergencyStop()) break; // Emergency stop check

            const balance = await this.bybitClient.getWalletBalance();
            if (balance === null || balance.lte(0)) {
                this.logger.error('Cannot get balance or balance is zero/negative. Retrying...');
                await sleep(this.config.bot.loopWaitTimeSeconds * 1000);
                continue;
            }
            this.logger.info(`Balance: ${balance.toFixed(2)} USDT`);

            const currentPositionsOnExchange = await this.bybitClient.getPositions();
            const currentPositionsSymbolsOnExchange = {};
            currentPositionsOnExchange.forEach(p => {
                currentPositionsSymbolsOnExchange[p.symbol] = p;
            });
            this.logger.info(`You have ${currentPositionsOnExchange.length} open positions on exchange: ${Object.keys(currentPositionsSymbolsOnExchange)}`);

            // --- Position Reconciliation (Exchange vs. DB) ---
            if (utcTime.diff(this.lastReconciliationTime, 'minutes') >= (this.config.strategies.chanExit.positionReconciliationIntervalMinutes || 5)) {
                this.logger.info(`Performing position reconciliation...`);
                await this._reconcilePositions(currentPositionsSymbolsOnExchange, utcTime);
                this.lastReconciliationTime = utcTime;
            }

            // --- Position Exit Manager (Time, Chandelier Exit, Fisher Transform, Fixed Profit, Trailing Stop) ---
            let activeDbTrades = await this.sqliteManager.getOpenTrades();

            const exitTasks = [];
            for (const trade of activeDbTrades) {
                const positionInfo = currentPositionsSymbolsOnExchange[trade.symbol];
                exitTasks.push(this._manageTradeExit(trade, positionInfo, utcTime));
            }
            await Promise.all(exitTasks);

            // Refresh active_db_trades after exits
            activeDbTrades = await this.sqliteManager.getOpenTrades();
            const currentDbPositionsSymbols = activeDbTrades.map(t => t.symbol);

            // --- Signal Search and Order Placement ---
            const signalTasks = [];
            for (const symbol of this.config.trading.symbols) {
                if (currentDbPositionsSymbols.length >= (this.config.trading.maxOpenPositions || 1)) {
                    this.logger.info(`Max positions (${this.config.trading.maxOpenPositions}) reached. Halting signal checks for this cycle.`);
                    break;
                }

                if (currentDbPositionsSymbols.includes(symbol)) {
                    this.logger.debug(`Skipping ${symbol} as there is already an open position in DB tracker.`);
                    continue;
                }

                const openOrdersForSymbol = await this.bybitClient.getOpenOrders(symbol);
                if (openOrdersForSymbol.length >= (this.config.trading.maxOpenOrdersPerSymbol || 1)) {
                    this.logger.debug(`Skipping ${symbol} as there are ${openOrdersForSymbol.length} open orders (max ${this.config.trading.maxOpenOrdersPerSymbol}).`);
                    continue;
                }

                // Process signal for the symbol using the active strategy
                const klines = await this.bybitClient.getKlines(symbol, this.config.trading.timeframe, 200);
                if (!klines || klines.length < this.config.trading.min_klines_for_strategy) {
                    this.logger.warn(`Not enough kline data for ${symbol}. Skipping.`);
                    continue;
                }

                const { signal, sl_price, tp_price, reasoning, currentPrice, df_indicators } = await this.strategy.generateSignals(klines);
                const last = df_indicators[df_indicators.length - 1];

                const log_msg = `[${symbol}] Price: ${last.close.toFixed(4)} | SlowST: ${last.st_slow_line.toFixed(4)} (${last.st_slow_direction.gt(0) ? 'Up' : 'Down'}) | RSI: ${last.rsi.toFixed(2)} | Fisher: ${last.fisher.toFixed(2)}`;
                this.logger.info(log_msg);

                if (signal !== 'none') {
                    this.logger.info(`SIGNAL for ${symbol}: ${signal} | Reason: ${reasoning}`);
                    const instrumentInfo = await this.bybitClient.restClient.getInstrumentsInfo({ category: this.config.api.category, symbol });
                    const pricePrecision = instrumentInfo.result.list[0].priceFilter.tickSize.split('.')[1]?.length || 0;
                    const qtyPrecision = instrumentInfo.result.list[0].lotSizeFilter.qtyStep.split('.')[1]?.length || 0;

                    const riskDistance = last.close.minus(sl_price).abs();
                    const riskAmountUSD = balance.times(this.config.risk.riskPerTradePercent);
                    let orderQty = riskAmountUSD.dividedBy(riskDistance);

                    // Apply max notional per trade
                    const maxNotionalQty = new Decimal(this.config.risk.maxNotionalPerTradeUsdt).dividedBy(last.close);
                    orderQty = Decimal.min(orderQty, maxNotionalQty);

                    const finalQty = round_qty(orderQty, new Decimal(1).dividedBy(new Decimal(10).pow(qtyPrecision)));

                    if (finalQty.gt(0)) {
                        const orderId = await this.bybitClient.placeOrder({
                            category: this.config.api.category,
                            symbol,
                            side: signal,
                            orderType: 'Market',
                            qty: finalQty.toString(),
                            takeProfit: round_price(tp_price, pricePrecision).toString(),
                            stopLoss: round_price(sl_price, pricePrecision).toString(),
                        });

                        if (orderId) {
                            const trade = new Trade({
                                id: uuidv4(),
                                order_id: orderId,
                                symbol: symbol,
                                side: signal,
                                qty: finalQty,
                                entry_time: utcTime.toISOString(),
                                entry_price: currentPrice,
                                sl: sl_price,
                                tp: tp_price,
                                status: 'OPEN',
                            });
                            await this.sqliteManager.addTrade(trade);
                            this.logger.info(`New trade logged for ${symbol} (${signal} ${finalQty}). Order ID: ${orderId}`);
                        }
                    }
                }
            }

            this.logger.info(`--- Cycle finished. Waiting ${this.config.bot.loopWaitTimeSeconds} seconds. ---`);
            await sleep(this.config.bot.loopWaitTimeSeconds * 1000);
        }
    }
}

module.exports = BotRunner;