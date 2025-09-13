import { Decimal } from 'decimal.js';
import { CONFIG } from '../config.js';
import { logger, neon } from '../logger.js';
import { bybitClient } from '../bybit_api_client.js';
import { round_qty, round_price } from '../utils/math_utils.js';
import WebSocketClient from '../utils/websocket_client.js';
import Dashboard from '../utils/dashboard.js';
import PerformanceTracker from '../utils/performance_tracker.js';
import * as indicators from '../indicators.js'; // Import all indicator functions
import { setTimeout } from 'timers/promises';

// --- Constants (from original wb4.0.js, now mostly in CONFIG) ---
const SYMBOL = CONFIG.SYMBOL;
const INTERVAL = CONFIG.INTERVAL;
const LOOP_DELAY_SECONDS = CONFIG.LOOP_DELAY_SECONDS;
const WEBSOCKET_URL = CONFIG.WEBSOCKET_URL;

// --- PositionManager (with Martingale) ---
class PositionManager {
    constructor(config, symbol, bybitClient) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.bybitClient = bybitClient;
        this.open_positions = {}; // { position_id: { entry_price, qty, side, status, ... } }
        this.active_orders = {}; // { order_id: { ... } }
        this.martingale_level = 0;
        this.load_state();
    }

    load_state() {
        // In a real application, you'd load this from a file or database
        this.logger.info('Loading position manager state (stubbed).');
    }

    save_state() {
        // In a real application, you'd save this to a file or database
        this.logger.info('Saving position manager state (stubbed).');
    }

    async manage_positions(current_price, performanceTracker) {
        // Check for open positions and update their status
        // For simplicity, we'll assume positions are managed externally or via order updates
        // In a real scenario, you'd fetch open positions from Bybit API
        
        // Example: If a position is open, check if SL/TP was hit (this logic would be more complex)
        // For now, we just ensure we don't open too many positions
        if (Object.keys(this.open_positions).length >= this.config.TRADE_MANAGEMENT.MAX_OPEN_POSITIONS) {
            // logger.debug('Max open positions reached.');
        }
    }

    async open_position(signal, current_price, atr_value, conviction) {
        if (!this.config.TRADE_MANAGEMENT.ENABLED) {
            this.logger.debug('Trade management is disabled.');
            return;
        }

        if (Object.keys(this.open_positions).length >= this.config.TRADE_MANAGEMENT.MAX_OPEN_POSITIONS) {
            this.logger.debug('Max open positions reached, cannot open new position.');
            return;
        }

        const [price_precision, qty_precision] = await this.bybitClient.getPrecisions(this.symbol);

        let side = signal;
        let order_type = 'Market';
        let qty_step = new Decimal(10).pow(-qty_precision);
        let price_step = new Decimal(10).pow(-price_precision);

        let base_qty = new Decimal(this.config.TRADE_MANAGEMENT.ACCOUNT_BALANCE)
            .times(this.config.TRADE_MANAGEMENT.RISK_PER_TRADE_PERCENT / 100)
            .div(current_price);

        if (this.config.MARTINGALE.ENABLED) {
            this.martingale_level = Math.min(this.martingale_level, this.config.MARTINGALE.MAX_LEVELS);
            base_qty = base_qty.times(Math.pow(this.config.MARTINGALE.MULTIPLIER, this.martingale_level));
        }

        let qty = round_qty(base_qty, qty_step);

        if (qty.isZero() || qty.isNaN()) {
            this.logger.warn(`Calculated quantity is zero or NaN. Cannot open position.`);
            return;
        }

        let stop_loss_price = null;
        let take_profit_price = null;

        if (signal === 'BUY') {
            stop_loss_price = round_price(current_price.minus(atr_value.times(this.config.TRADE_MANAGEMENT.STOP_LOSS_ATR_MULTIPLE)), price_precision);
            take_profit_price = round_price(current_price.plus(atr_value.times(this.config.TRADE_MANAGEMENT.TAKE_PROFIT_ATR_MULTIPLE)), price_precision);
        } else { // SELL
            stop_loss_price = round_price(current_price.plus(atr_value.times(this.config.TRADE_MANAGEMENT.STOP_LOSS_ATR_MULTIPLE)), price_precision);
            take_profit_price = round_price(current_price.minus(atr_value.times(this.config.TRADE_MANAGEMENT.TAKE_PROFIT_ATR_MULTIPLE)), price_precision);
        }

        try {
            const orderId = await this.bybitClient.placeMarketOrder(
                this.symbol,
                side,
                qty,
                take_profit_price,
                stop_loss_price
            );
            
            // Add to open positions (simplified)
            const position_id = `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
            this.open_positions[position_id] = {
                id: position_id,
                entry_price: current_price,
                qty: qty,
                side: side,
                status: 'OPEN',
                order_id: orderId
            };
            this.logger.info(`Opened ${side} position: ${qty} @ ${current_price}. SL: ${stop_loss_price}, TP: ${take_profit_price}`);
            
            if (this.config.MARTINGALE.ENABLED && signal === side) { // If it's a winning trade for this side, reset martingale level
                this.martingale_level = 0;
            } else if (this.config.MARTINGALE.ENABLED && signal !== side) { // If it's a losing trade, increase martingale level
                this.martingale_level++;
            }

            this.save_state();
        } catch (error) {
            this.logger.error(`Failed to open position: ${error.message}`);
            // If order creation failed, do not increment martingale level
        }
    }
}

// --- TradingAnalyzer ---
class TradingAnalyzer {
    constructor(klines, config, symbol) {
        this.klines = klines;
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.calculate_indicators();
    }

    calculate_indicators() {
        if (!this.klines || this.klines.length < 14) { // Need at least 14 periods for StochRSI
            this.logger.warn('Not enough kline data to calculate indicators.');
            return;
        }

        const closes = this.klines.map(k => new Decimal(k.close));
        const highs = this.klines.map(k => new Decimal(k.high));
        const lows = this.klines.map(k => new Decimal(k.low));

        // --- Pivot Points ---
        const last_pivot_kline = this.klines[this.klines.length - 1];
        const prev_pivot_kline = this.klines[this.klines.length - 2];

        const pivot_high = new Decimal(prev_pivot_kline.high);
        const pivot_low = new Decimal(prev_pivot_kline.low);
        const pivot_close = new Decimal(prev_pivot_kline.close);

        const pivot_point = (pivot_high.plus(pivot_low).plus(pivot_close)).div(3);
        const r1 = pivot_point.times(2).minus(pivot_low);
        const s1 = pivot_point.times(2).minus(pivot_high);
        const r2 = pivot_point.plus(pivot_high.minus(pivot_low));
        const s2 = pivot_point.minus(pivot_high.minus(pivot_low));
        const r3 = pivot_point.plus(pivot_high.minus(pivot_low).times(2));
        const s3 = pivot_point.minus(pivot_high.minus(pivot_low).times(2));

        this.indicator_values.pivot = {
            pp: pivot_point,
            r1: r1, s1: s1, r2: r2, s2: s2, r3: r3, s3: s3
        };

        // --- StochRSI ---
        const rsi_period = 14;
        const stoch_k_period = 3;
        const stoch_d_period = 3;

        const rsi_values = indicators.calculateRSI(closes, rsi_period);
        const stoch_rsi_values = indicators.calculateStochRSI(rsi_values, rsi_period);

        this.indicator_values.stoch_rsi = stoch_rsi_values;

        // --- ATR ---
        const atr_period = 14;
        this.indicator_values.ATR = indicators.calculateATR(highs, lows, closes, atr_period);
    }

    _get_indicator_value(indicator_name, default_value) {
        if (this.indicator_values[indicator_name]) {
            if (Array.isArray(this.indicator_values[indicator_name])) {
                return this.indicator_values[indicator_name][this.indicator_values[indicator_name].length - 1];
            } else {
                return this.indicator_values[indicator_name];
            }
        }
        return default_value;
    }

    generate_trading_signal(latest_orderbook) {
        if (!this.klines || this.klines.length < 20) { // Need enough data for indicators
            return ["HOLD", 0, {}];
        }

        const last_kline = this.klines[this.klines.length - 1];
        const prev_kline = this.klines[this.klines.length - 2];

        const current_price = new Decimal(last_kline.close);
        const atr = this._get_indicator_value("ATR", new Decimal("0.01"));

        // --- Pivot Point Analysis ---
        const pivots = this.indicator_values.pivot;
        let pivot_signal = 'HOLD';
        if (current_price.gt(pivots.r1)) pivot_signal = 'BUY';
        if (current_price.lt(pivots.s1)) pivot_signal = 'SELL';

        // --- StochRSI Analysis ---
        const stoch_rsi_values = this.indicator_values.stoch_rsi;
        let stoch_rsi_signal = 'HOLD';
        if (stoch_rsi_values && stoch_rsi_values.length > 0) {
            const last_stoch_rsi = stoch_rsi_values[stoch_rsi_values.length - 1];
            const prev_stoch_rsi = stoch_rsi_values.length > 1 ? stoch_rsi_values[stoch_rsi_values.length - 2] : last_stoch_rsi;

            if (last_stoch_rsi < 20 && prev_stoch_rsi < last_stoch_rsi) {
                stoch_rsi_signal = 'BUY';
            } else if (last_stoch_rsi > 80 && prev_stoch_rsi > last_stoch_rsi) {
                stoch_rsi_signal = 'SELL';
            }
        }

        // --- Combine Signals ---
        let final_signal = 'HOLD';
        let signal_score = 0;
        const signal_breakdown = {};

        const signals = { pivot: pivot_signal, stoch_rsi: stoch_rsi_signal };
        let buy_count = 0;
        let sell_count = 0;

        for (const [indicator, signal] of Object.entries(signals)) {
            signal_breakdown[indicator] = signal;
            if (signal === 'BUY') {
                buy_count++;
            } else if (signal === 'SELL') {
                sell_count++;
            }
        }

        if (buy_count >= 2) {
            final_signal = 'BUY';
            signal_score = buy_count;
        } else if (sell_count >= 2) {
            final_signal = 'SELL';
            signal_score = -sell_count;
        }

        return [final_signal, signal_score, signal_breakdown];
    }
}

// --- Main Execution Logic ---
async function run_bot() {
    const dashboard = new Dashboard(CONFIG, logger);
    dashboard.start();

    const wsClient = new WebSocketClient(WEBSOCKET_URL);
    wsClient.connect();

    const positionManager = new PositionManager(CONFIG, SYMBOL, bybitClient);
    const performanceTracker = new PerformanceTracker(CONFIG);

    let latest_orderbook = null;
    wsClient.subscribe([`orderbook.50.${SYMBOL}`], (data) => {
        const bids = data.b || [];
        const asks = data.a || [];
        if (bids.length > 0 && asks.length > 0) {
            const bidVolume = bids.slice(0, 10).reduce((sum, b) => sum + parseFloat(b[1]), 0);
            const askVolume = asks.slice(0, 10).reduce((sum, a) => sum + parseFloat(a[1]), 0);
            const totalVolume = bidVolume + askVolume;
            latest_orderbook = {
                imbalance: totalVolume > 0 ? (bidVolume - askVolume) / totalVolume : 0,
                liquidity_score: totalVolume > 0 ? Math.min(1, totalVolume / 100) : 0
            };
        }
    });

    while (true) {
        const loop_start_time = Date.now();
        try {
            const klines = await bybitClient.klines(SYMBOL, INTERVAL, 1000);
            if (!klines) {
                logger.warn(neon.warn("No kline data. Skipping loop."));
                await setTimeout(LOOP_DELAY_SECONDS * 1000);
                continue;
            }

            const analyzer = new TradingAnalyzer(klines, CONFIG, SYMBOL);
            const [trading_signal, signal_score, signal_breakdown] = analyzer.generate_trading_signal(latest_orderbook);
            const current_price = new Decimal(klines[klines.length - 1].close);
            const atr_value = analyzer._get_indicator_value("ATR", new Decimal("0.01"));

            positionManager.manage_positions(current_price, performanceTracker);

            if (trading_signal !== "HOLD") {
                const conviction = Math.min(1.0, Math.abs(signal_score) / (CONFIG.SIGNAL_SCORE_THRESHOLD * 2));
                await positionManager.open_position(trading_signal, current_price, atr_value, conviction);
            }

            // Dashboard Update
            dashboard.update({
                marketData: { [SYMBOL]: { price: current_price.toString() } },
                performance: performanceTracker.get_summary(),
                signal: { signal: trading_signal, score: signal_score },
                indicators: analyzer.indicator_values,
                positions: positionManager.open_positions,
                trade_history: performanceTracker.trades.slice(-20)
            });

        } catch (e) {
            logger.error(`Main loop error: ${e.message}`);
        }
        const elapsed_time = Date.now() - loop_start_time;
        const remaining_delay = (LOOP_DELAY_SECONDS * 1000) - elapsed_time;
        if (remaining_delay > 0) {
            await setTimeout(remaining_delay);
        }
    }
}

// Start Bot
(async () => {
    try {
        await run_bot();
    } catch (e) {
        logger.critical(neon.error(`Bot terminated due to unhandled error: ${e.message}`), e);
        process.exit(1);
    }
})();
