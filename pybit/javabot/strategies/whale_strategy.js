import { Decimal } from 'decimal.js';
import { CONFIG } from '../config.js';
import { logger, neon } from '../logger.js';
import { bybitClient } from '../bybit_api_client.js';
import { round_qty, round_price, np_clip } from '../utils/math_utils.js';
import PerformanceTracker from '../utils/performance_tracker.js';
import AlertSystem from '../utils/alert_system.js';
import * as indicators from '../indicators.js'; // Import all indicator functions
import { setTimeout } from 'timers/promises';

// --- Constants (from original whale.js, now mostly in CONFIG) ---
const SYMBOL = CONFIG.SYMBOL;
const INTERVAL = CONFIG.INTERVAL;
const LOOP_DELAY_SECONDS = CONFIG.LOOP_DELAY_SECONDS;
const ORDERBOOK_LIMIT = CONFIG.ORDERBOOK_LIMIT;
const SIGNAL_SCORE_THRESHOLD = CONFIG.SIGNAL_SCORE_THRESHOLD;
const COOLDOWN_SEC = CONFIG.COOLDOWN_SEC;
const HYSTERESIS_RATIO = CONFIG.HYSTERESIS_RATIO;
const VOLUME_CONFIRMATION_MULTIPLIER = CONFIG.VOLUME_CONFIRMATION_MULTIPLIER;

// --- Position Management ---
/**
 * @class PositionManager
 * @description Manages open trading positions for the Whale strategy, including order sizing,
 * stop loss/take profit calculation, pyramiding, and interaction with the Bybit API.
 */
class PositionManager {
    /**
     * @constructor
     * @param {Object} config - The configuration object for the strategy.
     * @param {string} symbol - The trading symbol this position manager is responsible for.
     * @param {BybitAPIClient} pybit_client - An instance of the BybitAPIClient.
     */
    constructor(config, symbol, pybit_client) {
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.open_positions = [];
        this.trade_management_enabled = config.TRADE_MANAGEMENT.ENABLED;
        this.max_open_positions = config.TRADE_MANAGEMENT.MAX_OPEN_POSITIONS;
        this.order_precision = config.TRADE_MANAGEMENT.ORDER_PRECISION;
        this.price_precision = config.TRADE_MANAGEMENT.PRICE_PRECISION;
        this.slippage_percent = new Decimal(config.TRADE_MANAGEMENT.SLIPPAGE_PERCENT);
        this.pybit = pybit_client;
        this.qty_step = new Decimal("0.000001"); // Default, will be updated from exchange
        this._update_precision_from_exchange();
    }

    /**
     * @async
     * @function _update_precision_from_exchange
     * @description Updates the quantity and price precision (step sizes) based on exchange information.
     * @returns {Promise<void>}
     */
    async _update_precision_from_exchange() {
        const [pricePrec, qtyPrec, minOrderQty] = await this.pybit.getPrecisions(this.symbol);
        this.qty_step = new Decimal(10).pow(-qtyPrec);
        this.order_precision = qtyPrec;
        this.price_precision = pricePrec;
        this.logger.info(neon.blue(`Updated precision for ${this.symbol}: qty_step=${this.qty_step}, order_precision=${this.order_precision}, price_precision=${this.price_precision}`));
    }

    /**
     * @function _get_current_balance
     * @description Retrieves the current account balance (stubbed to use config value for now).
     * In a real bot, this would fetch live balance.
     * @returns {Decimal} The current account balance.
     */
    _get_current_balance() {
        // In a real bot, this would fetch live balance. For now, use config value.
        return new Decimal(this.config.TRADE_MANAGEMENT.ACCOUNT_BALANCE);
    }

    /**
     * @function _calculate_order_size
     * @description Calculates the appropriate order size based on risk percentage, current price, ATR, and conviction.
     * @param {Decimal} current_price - The current market price.
     * @param {Decimal} atr_value - The Average True Range value.
     * @param {number} [conviction=1.0] - The conviction score of the signal (0 to 1).
     * @returns {Decimal} The calculated order quantity.
     */
    _calculate_order_size(current_price, atr_value, conviction = 1.0) {
        if (!this.trade_management_enabled) return new Decimal("0");
        const account_balance = this._get_current_balance();
        const base_risk_pct = new Decimal(this.config.TRADE_MANAGEMENT.RISK_PER_TRADE_PERCENT).dividedBy(100);
        const risk_multiplier = new Decimal(np_clip(0.5 + conviction, 0.5, 1.5));
        const risk_pct = base_risk_pct.times(risk_multiplier);
        const stop_loss_atr_multiple = new Decimal(this.config.TRADE_MANAGEMENT.STOP_LOSS_ATR_MULTIPLE);
        const risk_amount = account_balance.times(risk_pct);
        const stop_loss_distance = atr_value.times(stop_loss_atr_multiple);

        if (stop_loss_distance.lte(0)) {
            this.logger.warning(neon.warn("Stop loss distance invalid. Cannot calculate order size."));
            return new Decimal("0");
        }

        const order_value = risk_amount.dividedBy(stop_loss_distance);
        let order_qty = order_value.dividedBy(current_price);
        return round_qty(order_qty, this.qty_step);
    }

    /**
     * @function _compute_stop_loss_price
     * @description Computes the Stop Loss price based on the configured scheme (ATR multiple or percentage).
     * @param {string} side - The side of the trade ("BUY" or "SELL").
     * @param {Decimal} entry_price - The entry price of the trade.
     * @param {Decimal} atr_value - The Average True Range value.
     * @returns {Decimal} The calculated Stop Loss price.
     */
    _compute_stop_loss_price(side, entry_price, atr_value) {
        const sl_cfg = this.config.EXECUTION.SL_SCHEME;
        let sl;
        if (sl_cfg.TYPE === "atr_multiple") {
            const sl_mult = new Decimal(sl_cfg.ATR_MULTIPLE);
            sl = (side === "BUY") ? entry_price.minus(atr_value.times(sl_mult)) : entry_price.plus(atr_value.times(sl_mult));
        } else {
            const sl_pct = new Decimal(sl_cfg.PERCENT).dividedBy(100);
            sl = (side === "BUY") ? entry_price.times(new Decimal(1).minus(sl_pct)) : entry_price.times(new Decimal(1).plus(sl_pct));
        }
        return round_price(sl, this.price_precision);
    }

    /**
     * @function _calculate_take_profit_price
     * @description Calculates the Take Profit price based on ATR multiple.
     * @param {string} signal - The trading signal ("BUY" or "SELL").
     * @param {Decimal} current_price - The current market price.
     * @param {Decimal} atr_value - The Average True Range value.
     * @returns {Decimal} The calculated Take Profit price.
     */
    _calculate_take_profit_price(signal, current_price, atr_value) {
        const tp_mult = new Decimal(this.config.TRADE_MANAGEMENT.TAKE_PROFIT_ATR_MULTIPLE);
        const tp = (signal === "BUY") ? current_price.plus(atr_value.times(tp_mult)) : current_price.minus(atr_value.times(tp_mult));
        return round_price(tp, this.price_precision);
    }

    /**
     * @async
     * @function open_position
     * @description Opens a new trading position, calculates order size, SL/TP, and places the order via Bybit API.
     * @param {string} signal - The trading signal ("BUY" or "SELL").
     * @param {Decimal} current_price - The current market price.
     * @param {Decimal} atr_value - The Average True Range value.
     * @param {number} conviction - The conviction score of the signal.
     * @returns {Promise<Object|null>} The opened position object if successful, or null on failure.
     */
    async open_position(signal, current_price, atr_value, conviction) {
        if (!this.trade_management_enabled || this.open_positions.length >= this.max_open_positions) {
            this.logger.info(neon.warn("Max positions reached or trade management disabled."));
            return null;
        }

        const order_qty = this._calculate_order_size(current_price, atr_value, conviction);
        if (order_qty.lte(0)) {
            this.logger.warning(neon.warn("Order quantity zero. Skipping position."));
            return null;
        }

        const stop_loss = this._compute_stop_loss_price(signal, current_price, atr_value);
        const take_profit = this._calculate_take_profit_price(signal, current_price, atr_value);

        let adjusted_entry_price_sim = current_price;
        if (signal === "BUY") {
            adjusted_entry_price_sim = current_price.times(new Decimal(1).plus(this.slippage_percent));
        } else {
            adjusted_entry_price_sim = current_price.times(new Decimal(1).minus(this.slippage_percent));
        }

        const position = {
            "entry_time": new Date(), "symbol": this.symbol, "side": signal,
            "entry_price": round_price(adjusted_entry_price_sim, this.price_precision), "qty": order_qty,
            "stop_loss": stop_loss, "take_profit": take_profit,
            "status": "OPEN", "link_prefix": `wgx_${Date.now()}`, "adds": 0,
            "order_id": null, "stop_loss_order_id": null, "take_profit_order_ids": [],
            "best_price": adjusted_entry_price_sim
        };

        if (this.config.EXECUTION.USE_PYBIT && this.pybit) {
            try {
                const resp = await this.pybit.placeMarketOrder(
                    this.symbol, signal, order_qty, take_profit, stop_loss
                );
                if (resp) {
                    position.order_id = resp;
                    this.logger.info(neon.green(`Live order placed: ${JSON.stringify(position)}`));
                }
            } catch (e) {
                this.logger.error(neon.error(`Live order failed: ${e.message}. Simulating.`));
            }
        }

        this.open_positions.push(position);
        this.logger.info(neon.green(`Opened position: ${JSON.stringify(position)}`));
        return position;
    }

    /**
     * @function _check_and_close_position
     * @description Checks if an open position should be closed based on current price hitting SL/TP.
     * @param {Object} position - The position object to check.
     * @param {Decimal} current_price - The current market price.
     * @returns {Object} An object indicating if the position is closed, the adjusted close price, and the reason.
     */
    _check_and_close_position(position, current_price) {
        const side = position.side;
        const stop_loss = position.stop_loss;
        const take_profit = position.take_profit;

        let closed_by = null;
        let close_price = new Decimal("0");

        if (side === "BUY") {
            if (current_price.lte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).minus(this.slippage_percent));
            } else if (current_price.gte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).minus(this.slippage_percent));
            }
        } else {
            if (current_price.gte(stop_loss)) {
                closed_by = "STOP_LOSS";
                close_price = current_price.times(new Decimal(1).plus(this.slippage_percent));
            } else if (current_price.lte(take_profit)) {
                closed_by = "TAKE_PROFIT";
                close_price = current_price.times(new Decimal(1).plus(this.slippage_percent));
            }
        }

        if (closed_by) {
            const adjusted_close_price = round_price(close_price, this.price_precision);
            return { is_closed: true, adjusted_close_price, closed_by };
        }
        return { is_closed: false, adjusted_close_price: new Decimal("0"), closed_by: "" };
    }

    /**
     * @function manage_positions
     * @description Iterates through open positions, checks for closure conditions (SL/TP),
     * records trades, and removes closed positions.
     * @param {Decimal} current_price - The current market price.
     * @param {PerformanceTracker} performance_tracker - An instance of the PerformanceTracker.
     * @returns {void}
     */
    manage_positions(current_price, performance_tracker) {
        if (!this.trade_management_enabled) return;

        const positions_to_remove = [];
        for (let i = 0; i < this.open_positions.length; i++) {
            const pos = this.open_positions[i];
            if (pos.status !== "OPEN") continue;

            const result = this._check_and_close_position(pos, current_price);
            if (result.is_closed) {
                pos.status = "CLOSED";
                pos.exit_time = new Date();
                pos.exit_price = result.adjusted_close_price;
                pos.closed_by = result.closed_by;

                const pnl = pos.side === "BUY"
                    ? (pos.exit_price.minus(pos.entry_price)).times(pos.qty)
                    : (pos.entry_price.minus(pos.exit_price)).times(pos.qty);

                performance_tracker.record_trade(pos, pnl);
                this.logger.info(neon.purple(`Closed position: ${JSON.stringify(pos)}. PnL: ${pnl.toFixed(4)}`));

                positions_to_remove.push(i);

                if (this.config.EXECUTION.USE_PYBIT && this.pybit) {
                    // Assuming bybitClient has a cancelAllOrders or similar for orderLinkId
                    // This part needs to be adapted to bybitClient's capabilities
                    // For now, just log a warning
                    this.logger.warn(neon.warn("Live order cancellation by link_prefix not yet implemented in shared bybitClient."));
                }
            }
        }

        // Remove closed positions
        for (let i = positions_to_remove.length - 1; i >= 0; i--) {
            this.open_positions.splice(positions_to_remove[i], 1);
        }
    }

    /**
     * @function trail_stop
     * @description Trails the stop loss of an open position based on ATR.
     * @param {Object} pos - The position object to trail the stop for.
     * @param {Decimal} current_price - The current market price.
     * @param {Decimal} atr_value - The Average True Range value.
     * @returns {void}
     */
    trail_stop(pos, current_price, atr_value) {
        if (!atr_value || !pos.best_price) return;
        const atr_mult = new Decimal(this.config.TRADE_MANAGEMENT.STOP_LOSS_ATR_MULTIPLE);
        const side = pos.side;

        if (side === "BUY") {
            pos.best_price = Decimal.max(pos.best_price, current_price);
            const new_sl = pos.best_price.minus(atr_mult.times(atr_value));
            if (new_sl.gt(pos.stop_loss)) {
                pos.stop_loss = round_price(new_sl, this.price_precision);
                this.logger.debug(neon.blue(`Trailing BUY SL to ${pos.stop_loss}`));
            }
        } else {
            pos.best_price = Decimal.min(pos.best_price, current_price);
            const new_sl = pos.best_price.plus(atr_mult.times(atr_value));
            if (new_sl.lt(pos.stop_loss)) {
                pos.stop_loss = round_price(new_sl, this.price_precision);
                this.logger.debug(neon.blue(`Trailing SELL SL to ${pos.stop_loss}`));
            }
        }
    }

    /**
     * @async
     * @function try_pyramid
     * @description Attempts to add to an existing position (pyramiding) if conditions are met.
     * @param {Decimal} current_price - The current market price.
     * @param {Decimal} atr_value - The Average True Range value.
     * @returns {Promise<void>}
     */
    async try_pyramid(current_price, atr_value) {
        if (!this.config.PYRAMIDING.ENABLED) return;

        for (const pos of this.open_positions) {
            if (pos.status !== "OPEN" || pos.adds >= this.config.PYRAMIDING.MAX_ADDS) continue;

            const step_atr_mult = new Decimal(this.config.PYRAMIDING.STEP_ATR);
            const step_distance = step_atr_mult.times(atr_value).times(new Decimal(pos.adds + 1));

            let target_price;
            if (pos.side === "BUY") {
                target_price = pos.entry_price.plus(step_distance);
                if (current_price.lt(target_price)) continue;
            } else {
                target_price = pos.entry_price.minus(step_distance);
                if (current_price.gt(target_price)) continue;
            }

            const add_qty = round_qty(pos.qty.times(this.config.PYRAMIDING.SIZE_PCT_OF_INITIAL), this.qty_step);
            if (add_qty.lte(0)) continue;

            const total_cost = pos.entry_price.times(pos.qty).plus(current_price.times(add_qty));
            pos.qty = pos.qty.plus(add_qty);
            pos.entry_price = total_cost.dividedBy(pos.qty);
            pos.adds++;

            this.logger.info(neon.green(`Pyramided: Added ${add_qty} at ${current_price}. New avg: ${pos.entry_price.toFixed(this.price_precision)}`));

            if (this.config.EXECUTION.USE_PYBIT && this.pybit) {
                try {
                    await this.pybit.placeMarketOrder(this.symbol, pos.side, add_qty, pos.take_profit, pos.stop_loss);
                } catch (e) {
                    this.logger.error(neon.error(`Pyramid order failed: ${e.message}`));
                }
            }
        }
    }

    /**
     * @private
     * @function _get_indicator_value
     * @description Placeholder method for getting indicator values. In the main loop, ATR value should be passed from analyzer.
     * @param {string} key - The indicator key.
     * @returns {Decimal} A Decimal.js NaN value.
     */
    _get_indicator_value(key) {
        // This method is a stub. In the main loop, ATR value should be passed from analyzer.
        return new Decimal(NaN);
    }
}

// --- Trading Analyzer ---
/**
 * @class TradingAnalyzer
 * @description Analyzes kline data and calculates various technical indicators.
 * It also computes a signal score based on a weighted combination of these indicators.
 */
class TradingAnalyzer {
    /**
     * @constructor
     * @param {Array<Object>} klines - An array of kline data.
     * @param {Object} config - The configuration object for the strategy.
     * @param {string} symbol - The trading symbol being analyzed.
     */
    constructor(klines, config, symbol) {
        this.df = this._process_dataframe(klines);
        this.config = config;
        this.logger = logger;
        this.symbol = symbol;
        this.indicator_values = {};
        this.fib_levels = {};
        this.weights = config.WEIGHT_SETS.DEFAULT_SCALPING;
        this.indicator_settings = config.INDICATOR_SETTINGS;

        if (this.df.length === 0) {
            this.logger.warning(neon.warn("Empty DataFrame. Skipping indicators."));
            return;
        }

        this._calculate_all_indicators();
        if (config.INDICATORS.FIBONACCI_LEVELS) this.calculate_fibonacci_levels();
        if (config.INDICATORS.FIBONACCI_PIVOT_POINTS) this.calculate_fibonacci_pivot_points();
    }

    /**
     * @private
     * @function _process_dataframe
     * @description Processes raw kline data into a DataFrame-like object with Decimal.js values.
     * @param {Array<Object>} df_raw - Raw kline data array.
     * @returns {Object} A DataFrame-like object with Decimal.js values.
     */
    _process_dataframe(df_raw) {
        const processed = {
            start_time: [], open: [], high: [], low: [], close: [], volume: [], turnover: []
        };
        df_raw.forEach(row => {
            processed.start_time.push(row.start_time);
            processed.open.push(new Decimal(row.open));
            processed.high.push(new Decimal(row.high));
            processed.low.push(new Decimal(row.low));
            processed.close.push(new Decimal(row.close));
            processed.volume.push(new Decimal(row.volume));
            processed.turnover.push(new Decimal(row.turnover));
        });

        const df_like = { ...processed, length: processed.close.length };
        df_like.iloc = (index) => {
            if (index < 0) index += df_like.length;
            const row = {};
            for (const key in df_like) {
                if (Array.isArray(df_like[key])) row[key] = df_like[key][index];
            }
            return row;
        };
        return df_like;
    }

    /**
     * @private
     * @function _safe_calculate
     * @description Safely calculates an indicator, handling insufficient data and errors.
     * @param {Function} func - The indicator calculation function.
     * @param {string} name - The name of the indicator.
     * @param {number} min_data_points - Minimum data points required for calculation.
     * @param {...any} args - Arguments to pass to the indicator function.
     * @returns {any|null} The calculated indicator result, or null if calculation fails or data is insufficient.
     */
    _safe_calculate(func, name, min_data_points, ...args) {
        if (this.df.length < min_data_points) {
            this.logger.debug(neon.blue(`Skipping ${name}: Insufficient data (${this.df.length} < ${min_data_points})`));
            return null;
        }
        try {
            // Pass Decimal.js arrays to indicator functions
            const result = func(this.df, this.indicator_settings, this.logger, this.symbol, ...args);
            if (result === null || (Array.isArray(result) && result.length === 0)) {
                this.logger.warning(neon.warn(`${name} returned empty result.`));
            }
            return result;
        } catch (e) {
            this.logger.error(neon.error(`Error calculating ${name}: ${e.message}`));
            return null;
        }
    }

    /**
     * @private
     * @function _calculate_all_indicators
     * @description Calculates all configured technical indicators and stores their latest values.
     * @returns {void}
     */
    _calculate_all_indicators() {
        const cfg = this.config.INDICATORS;
        const isd = this.indicator_settings;

        // Use the shared indicators module
        const closePrices = this.df.close;
        const highPrices = this.df.high;
        const lowPrices = this.df.low;
        const volumes = this.df.volume;

        if (cfg.SMA_10) {
            const sma = indicators.calculateSMA(closePrices, isd.SMA_SHORT_PERIOD);
            if (sma) this.indicator_values["SMA_10"] = sma[sma.length - 1];
        }

        if (cfg.SMA_TREND_FILTER) {
            const sma = indicators.calculateSMA(closePrices, isd.SMA_LONG_PERIOD);
            if (sma) this.indicator_values["SMA_Long"] = sma[sma.length - 1];
        }

        if (cfg.EMA_ALIGNMENT) {
            const ema_short = indicators.calculateEMA(closePrices, isd.EMA_SHORT_PERIOD);
            const ema_long = indicators.calculateEMA(closePrices, isd.EMA_LONG_PERIOD);
            if (ema_short) this.indicator_values["EMA_Short"] = ema_short[ema_short.length - 1];
            if (ema_long) this.indicator_values["EMA_Long"] = ema_long[ema_long.length - 1];
        }

        if (cfg.ATR) {
            const atr = indicators.calculateATR(highPrices, lowPrices, closePrices, isd.ATR_PERIOD);
            if (atr) this.indicator_values["ATR"] = atr[atr.length - 1];
        }

        if (cfg.RSI) {
            const rsi = indicators.calculateRSI(closePrices, isd.RSI_PERIOD);
            if (rsi) this.indicator_values["RSI"] = rsi[rsi.length - 1];
        }

        if (cfg.STOCH_RSI) {
            const [k, d] = indicators.calculateStochasticOscillator(highPrices, lowPrices, closePrices, isd.STOCH_RSI_PERIOD, isd.STOCH_K_PERIOD, isd.STOCH_D_PERIOD);
            if (k && d) {
                this.indicator_values["StochRSI_K"] = k[k.length - 1];
                this.indicator_values["StochRSI_D"] = d[d.length - 1];
            }
        }

        if (cfg.BOLLINGER_BANDS) {
            const bb = indicators.calculateBollingerBands(closePrices, isd.BOLLINGER_BANDS_PERIOD, isd.BOLLINGER_BANDS_STD_DEV);
            if (bb) {
                this.indicator_values["BB_Upper"] = bb.upper[bb.upper.length - 1];
                this.indicator_values["BB_Middle"] = bb.middle[bb.middle.length - 1];
                this.indicator_values["BB_Lower"] = bb.lower[bb.lower.length - 1];
            }
        }

        if (cfg.CCI) {
            const cci = indicators.calculateCCI(highPrices, lowPrices, closePrices, isd.CCI_PERIOD);
            if (cci) this.indicator_values["CCI"] = cci[cci.length - 1];
        }

        if (cfg.WR) {
            const wr = indicators.calculateWilliamsR(highPrices, lowPrices, closePrices, isd.WILLIAMS_R_PERIOD);
            if (wr) this.indicator_values["WR"] = wr[wr.length - 1];
        }

        if (cfg.MFI) {
            const mfi = indicators.calculateMFI(highPrices, lowPrices, closePrices, volumes, isd.MFI_PERIOD);
            if (mfi) this.indicator_values["MFI"] = mfi[mfi.length - 1];
        }

        if (cfg.OBV) {
            const obv = indicators.calculateOBV(closePrices, volumes);
            const obv_ema = indicators.calculateEMA(obv, isd.OBV_EMA_PERIOD);
            if (obv && obv_ema) {
                this.indicator_values["OBV"] = obv[obv.length - 1];
                this.indicator_values["OBV_EMA"] = obv_ema[obv_ema.length - 1];
            }
        }

        if (cfg.CMF) {
            const cmf = indicators.calculateCMF(highPrices, lowPrices, closePrices, volumes, isd.CMF_PERIOD);
            if (cmf) this.indicator_values["CMF"] = cmf[cmf.length - 1];
        }

        if (cfg.ICHIMOKU_CLOUD) {
            const ichi = indicators.calculateIchimokuCloud(highPrices, lowPrices, closePrices, isd.ICHIMOKU_TENKAN_PERIOD, isd.ICHIMOKU_KIJUN_PERIOD, isd.ICHIMOKU_SENKOU_SPAN_B_PERIOD, isd.ICHIMOKU_CHIKOU_SPAN_OFFSET);
            if (ichi) {
                this.indicator_values["Tenkan_Sen"] = ichi.tenkan_sen[ichi.tenkan_sen.length - 1];
                this.indicator_values["Kijun_Sen"] = ichi.kijun_sen[ichi.kijun_sen.length - 1];
                this.indicator_values["Senkou_Span_A"] = ichi.senkou_span_a[ichi.senkou_span_a.length - 1];
                this.indicator_values["Senkou_Span_B"] = ichi.senkou_span_b[ichi.senkou_span_b.length - 1];
                this.indicator_values["Chikou_Span"] = ichi.chikou_span[ichi.chikou_span.length - 1];
            }
        }

        if (cfg.PSAR) {
            const psar = indicators.calculatePSAR(highPrices, lowPrices, isd.PSAR_ACCELERATION, isd.PSAR_MAX_ACCELERATION);
            if (psar) {
                this.indicator_values["PSAR_Val"] = psar.psar[psar.psar.length - 1];
                this.indicator_values["PSAR_Dir"] = psar.direction[psar.direction.length - 1];
            }
        }

        if (cfg.VWAP) {
            // VWAP needs a DataFrame with 'volume' and 'close' and 'high' and 'low'
            // Assuming df has these columns as Decimal arrays
            const vwap = indicators.calculateVWAP(this.df.high, this.df.low, this.df.close, this.df.volume);
            if (vwap) this.indicator_values["VWAP"] = vwap[vwap.length - 1];
        }

        if (cfg.EHLERS_SUPERTREND) {
            const st_fast = indicators.calculateSupertrend(highPrices, lowPrices, closePrices, isd.EHLERS_FAST_PERIOD, isd.EHLERS_FAST_MULTIPLIER);
            const st_slow = indicators.calculateSupertrend(highPrices, lowPrices, closePrices, isd.EHLERS_SLOW_PERIOD, isd.EHLERS_SLOW_MULTIPLIER);
            if (st_fast) {
                this.indicator_values["ST_Fast_Dir"] = st_fast.direction[st_fast.direction.length - 1];
                this.indicator_values["ST_Fast_Val"] = st_fast.supertrend[st_fast.supertrend.length - 1];
            }
            if (st_slow) {
                this.indicator_values["ST_Slow_Dir"] = st_slow.direction[st_slow.direction.length - 1];
                this.indicator_values["ST_Slow_Val"] = st_slow.supertrend[st_slow.supertrend.length - 1];
            }
        }

        if (cfg.MACD) {
            const macd = indicators.calculateMACD(closePrices, isd.MACD_FAST_PERIOD, isd.MACD_SLOW_PERIOD, isd.MACD_SIGNAL_PERIOD);
            if (macd) {
                this.indicator_values["MACD_Line"] = macd.macd_line[macd.macd_line.length - 1];
                this.indicator_values["MACD_Signal"] = macd.signal_line[macd.signal_line.length - 1];
                this.indicator_values["MACD_Hist"] = macd.histogram[macd.histogram.length - 1];
            }
        }

        if (cfg.ADX) {
            const adx = indicators.calculateADX(highPrices, lowPrices, closePrices, isd.ADX_PERIOD);
            if (adx) {
                this.indicator_values["ADX"] = adx.adx[adx.adx.length - 1];
                this.indicator_values["PlusDI"] = adx.plus_di[adx.plus_di.length - 1];
                this.indicator_values["MinusDI"] = adx.minus_di[adx.minus_di.length - 1];
            }
        }

        if (cfg.VOLATILITY_INDEX) {
            const vi = indicators.calculateVolatilityIndex(highPrices, lowPrices, closePrices, isd.VOLATILITY_INDEX_PERIOD);
            if (vi) this.indicator_values["Volatility_Index"] = vi[vi.length - 1];
        }

        if (cfg.VWMA) {
            const vwma = indicators.calculateVWMA(closePrices, volumes, isd.VWMA_PERIOD);
            if (vwma) this.indicator_values["VWMA"] = vwma[vwma.length - 1];
        }

        if (cfg.VOLUME_DELTA) {
            const vd = indicators.calculateVolumeDelta(closePrices, volumes, isd.VOLUME_DELTA_PERIOD);
            if (vd) this.indicator_values["Volume_Delta"] = vd[vd.length - 1];
        }

        if (cfg.KAUFMAN_AMA) {
            const kama = indicators.calculateKaufmanAMA(closePrices, isd.KAMA_PERIOD, isd.KAMA_FAST_PERIOD, isd.KAMA_SLOW_PERIOD);
            if (kama) this.indicator_values["Kaufman_AMA"] = kama[kama.length - 1];
        }

        if (cfg.RELATIVE_VOLUME) {
            const rv = indicators.calculateRelativeVolume(volumes, isd.RELATIVE_VOLUME_PERIOD);
            if (rv) this.indicator_values["Relative_Volume"] = rv[rv.length - 1];
        }

        if (cfg.MARKET_STRUCTURE) {
            const ms = indicators.calculateMarketStructure(highPrices, lowPrices, isd.MARKET_STRUCTURE_LOOKBACK_PERIOD);
            if (ms) this.indicator_values["Market_Structure_Trend"] = ms[ms.length - 1];
        }

        if (cfg.DEMA) {
            const dema = indicators.calculateDEMA(closePrices, isd.DEMA_PERIOD);
            if (dema) this.indicator_values["DEMA"] = dema[dema.length - 1];
        }

        if (cfg.KELTNER_CHANNELS) {
            const kc = indicators.calculateKeltnerChannels(highPrices, lowPrices, closePrices, isd.KELTNER_PERIOD, isd.KELTNER_ATR_MULTIPLIER);
            if (kc) {
                this.indicator_values["Keltner_Upper"] = kc.upper[kc.upper.length - 1];
                this.indicator_values["Keltner_Middle"] = kc.middle[kc.middle.length - 1];
                this.indicator_values["Keltner_Lower"] = kc.lower[kc.lower.length - 1];
            }
        }

        if (cfg.ROC) {
            const roc = indicators.calculateROC(closePrices, isd.ROC_PERIOD);
            if (roc) this.indicator_values["ROC"] = roc[roc.length - 1];
        }

        if (cfg.CANDLESTICK_PATTERNS) {
            const patterns = indicators.detectCandlestickPatterns(this.df);
            if (patterns) this.indicator_values["Candlestick_Pattern"] = patterns[patterns.length - 1];
        }

        // Clean NaNs
        for (const key in this.indicator_values) {
            const val = this.indicator_values[key];
            if (val instanceof Decimal && val.isNaN()) {
                this.indicator_values[key] = new Decimal(NaN);
            }
        }

        this.logger.debug(neon.blue(`Indicators calculated for ${this.symbol}`));
    }

    /**
     * @function calculate_fibonacci_levels
     * @description Calculates Fibonacci retracement levels based on the provided kline data.
     * Stores the results in `this.fib_levels`.
     * @returns {void}
     */
    calculate_fibonacci_levels() {
        const fib = indicators.calculateFibonacciLevels(this.df, this.config.INDICATOR_SETTINGS.FIBONACCI_WINDOW);
        if (fib) this.fib_levels = fib;
    }

    /**
     * @function calculate_fibonacci_pivot_points
     * @description Calculates Fibonacci Pivot Points based on the provided kline data.
     * Stores the results in `this.indicator_values`.
     * @returns {void}
     */
    calculate_fibonacci_pivot_points() {
        if (this.df.length < 2) return;
        const pivot = indicators.calculateFibonacciPivotPoints(this.df);
        if (pivot) {
            const pp = this.config.TRADE_MANAGEMENT.PRICE_PRECISION;
            this.indicator_values["Pivot"] = pivot.pivot.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["R1"] = pivot.r1.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["R2"] = pivot.r2.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["S1"] = pivot.s1.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
            this.indicator_values["S2"] = pivot.s2.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
        }
    }

    /**
     * @function _get_indicator_value
     * @description Retrieves the latest value of a specified indicator from `indicator_values`.
     * @param {string} key - The key of the indicator.
     * @param {Decimal} [def=new Decimal(NaN)] - The default value to return if the indicator is not found or is NaN.
     * @returns {Decimal} The indicator value or the default value.
     */
    _get_indicator_value(key, def = new Decimal(NaN)) {
        const val = this.indicator_values[key];
        return (val instanceof Decimal && !val.isNaN()) ? val : def;
    }

    /**
     * @private
     * @function _check_orderbook
     * @description Calculates order book imbalance.
     * @param {Object} ob - The order book object with bids (b) and asks (a).
     * @returns {number} The imbalance value.
     */
    _check_orderbook(ob) {
        if (!ob?.b || !ob?.a) return 0;
        const bidVol = ob.b.reduce((sum, b) => sum.plus(new Decimal(b[1])), new Decimal(0));
        const askVol = ob.a.reduce((sum, a) => sum.plus(new Decimal(a[1])), new Decimal(0));
        if (bidVol.plus(askVol).isZero()) return 0;
        return bidVol.minus(askVol).dividedBy(bidVol.plus(askVol)).toNumber();
    }

    /**
     * @function calculate_support_resistance_from_orderbook
     * @description Identifies significant support and resistance levels from the order book.
     * Stores the results in `this.indicator_values`.
     * @param {Object} ob - The order book object with bids (b) and asks (a).
     * @returns {void}
     */
    calculate_support_resistance_from_orderbook(ob) {
        if (!ob?.b || !ob?.a) return;
        let maxBid = new Decimal(0), support = new Decimal(0);
        for (const [p, v] of ob.b) {
            const vol = new Decimal(v);
            if (vol.gt(maxBid)) { maxBid = vol; support = new Decimal(p); }
        }
        let maxAsk = new Decimal(0), resistance = new Decimal(0);
        for (const [p, v] of ob.a) {
            const vol = new Decimal(v);
            if (vol.gt(maxAsk)) { maxAsk = vol; resistance = new Decimal(p); }
        }
        const pp = this.config.TRADE_MANAGEMENT.PRICE_PRECISION;
        if (support.gt(0)) this.indicator_values["Support_Level"] = support.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
        if (resistance.gt(0)) this.indicator_values["Resistance_Level"] = resistance.toDecimalPlaces(pp, Decimal.ROUND_DOWN);
    }

    /**
     * @private
     * @function _get_mtf_trend
     * @description Determines the trend based on a higher timeframe using specified indicator types (SMA, EMA, Ehlers Supertrend).
     * @param {Array<Object>} higher_tf_df_raw - Raw kline data for the higher timeframe.
     * @param {string} indicator_type - The type of indicator to use for trend detection ("sma", "ema", "ehlers_supertrend").
     * @returns {string} The trend direction ("UP", "DOWN", "SIDEWAYS", or "UNKNOWN").
     */
    _get_mtf_trend(higher_tf_df_raw, indicator_type) {
        if (!higher_tf_df_raw || higher_tf_df_raw.length === 0) return "UNKNOWN";
        const df = this._process_dataframe(higher_tf_df_raw);
        const last = df.close[df.close.length - 1];
        const period = this.config.MTF_ANALYSIS.TREND_PERIOD;

        if (indicator_type === "sma" && df.length >= period) {
            const sma = indicators.calculateSMA(df.close, period)[df.close.length - 1];
            return last.gt(sma) ? "UP" : last.lt(sma) ? "DOWN" : "SIDEWAYS";
        }

        if (indicator_type === "ema" && df.length >= period) {
            const ema = indicators.calculateEMA(df.close, period)[df.close.length - 1];
            return last.gt(ema) ? "UP" : last.lt(ema) ? "DOWN" : "SIDEWAYS";
        }

        if (indicator_type === "ehlers_supertrend") {
            const st = indicators.calculateSupertrend(df.high, df.low, df.close, this.indicator_settings.EHLERS_SLOW_PERIOD, this.indicator_settings.EHLERS_SLOW_MULTIPLIER);
            if (st && st.direction.length > 0) {
                const dir = st.direction[st.direction.length - 1];
                return dir === 1 ? "UP" : dir === -1 ? "DOWN" : "UNKNOWN";
            }
        }
        return "UNKNOWN";
    }

    /**
     * @function calculate_signal_score
     * @description Calculates a composite signal score based on a weighted combination of various technical indicators.
     * @param {Object} [orderbook_data=null] - Optional order book data for imbalance calculation.
     * @param {Object} [higher_tf_signals={}] - Optional higher timeframe trend signals.
     * @returns {Object} An object containing the total score, signal ("BUY", "SELL", "NEUTRAL"), conviction, and a breakdown of contributions.
     */
    calculate_signal_score(orderbook_data = null, higher_tf_signals = {}) {
        if (this.df.length === 0) return { total_score: 0, signal: "NEUTRAL", conviction: 0, breakdown: {} };

        const current = this.df.close[this.df.close.length - 1];
        const prev = this.df.length > 1 ? this.df.close[this.df.close.length - 2] : current;

        let score = 0;
        let breakdown = {};
        let trendMult = 1.0;

        // ADX first
        const adx = this._score_adx(trendMult);
        score += adx.adx_contrib;
        trendMult = adx.trend_strength_multiplier_out;
        Object.assign(breakdown, adx.breakdown);

        // Then all others...
        const components = [
            this._score_ema_alignment(current, trendMult),
            this._score_sma_trend_filter(current),
            this._score_momentum_indicators(),
            this._score_bollinger_bands(current),
            this._score_vwap(current, prev),
            this._score_psar(current, prev),
            this._score_obv(),
            this._score_cmf(),
            this._score_volatility_index(),
            this._score_vwma_cross(current, prev),
            this._score_volume_delta(),
            this._score_kaufman_ama_cross(current, prev),
            this._score_relative_volume(),
            this._score_market_structure(),
            this._score_dema_crossover(current, prev),
            this._score_keltner_breakout(current, prev),
            this._score_roc(),
            this._score_candlestick_patterns(),
            this._score_fibonacci_levels(current, prev),
            this._score_fibonacci_pivot_points(current, prev),
            this._score_ehlers_supertrend(trendMult),
            this._score_macd(trendMult),
            this._score_ichimoku_cloud(current, trendMult),
            this._score_orderbook_imbalance(orderbook_data)
        ];

        for (const comp of components) {
            score += comp.contrib || 0;
            Object.assign(breakdown, comp.breakdown);
        }

        // MTF
        if (this.config.MTF_ANALYSIS.ENABLED && Object.keys(higher_tf_signals).length > 0) {
            let mtf = 0;
            const weight = this.weights.mtf_trend_confluence / Object.keys(higher_tf_signals).length;
            for (const tf in higher_tf_signals) {
                if (higher_tf_signals[tf] === "UP") mtf += weight;
                else if (higher_tf_signals[tf] === "DOWN") mtf -= weight;
            }
            score += mtf;
            breakdown["MTF Confluence"] = mtf;
        }

        const threshold = this.config.SIGNAL_SCORE_THRESHOLD;
        const signal = score > threshold ? "BUY" : score < -threshold ? "SELL" : "NEUTRAL";
        const conviction = Math.abs(score);

        return { total_score: score, signal, conviction, breakdown };
    }

    // Placeholder _score_* methods (full implementations would be here)
    /** @private @function _score_adx */
    _score_adx(tm) { return { adx_contrib: 0, trend_strength_multiplier_out: tm, breakdown: {} }; }
    /** @private @function _score_ema_alignment */
    _score_ema_alignment() { return { ema_contrib: 0, breakdown: {} }; }
    /** @private @function _score_sma_trend_filter */
    _score_sma_trend_filter() { return { sma_contrib: 0, breakdown: {} }; }
    /** @private @function _score_momentum_indicators */
    _score_momentum_indicators() { return { momentum_contrib: 0, breakdown: {} }; }
    /** @private @function _score_bollinger_bands */
    _score_bollinger_bands() { return { bb_contrib: 0, breakdown: {} }; }
    /** @private @function _score_vwap */
    _score_vwap() { return { vwap_contrib: 0, breakdown: {} }; }
    /** @private @function _score_psar */
    _score_psar() { return { psar_contrib: 0, breakdown: {} }; }
    /** @private @function _score_obv */
    _score_obv() { return { obv_contrib: 0, breakdown: {} }; }
    /** @private @function _score_cmf */
    _score_cmf() { return { cmf_contrib: 0, breakdown: {} }; }
    /** @private @function _score_volatility_index */
    _score_volatility_index() { return { vi_contrib: 0, breakdown: {} }; }
    /** @private @function _score_vwma_cross */
    _score_vwma_cross() { return { vwma_contrib: 0, breakdown: {} }; }
    /** @private @function _score_volume_delta */
    _score_volume_delta() { return { vd_contrib: 0, breakdown: {} }; }
    /** @private @function _score_kaufman_ama_cross */
    _score_kaufman_ama_cross() { return { kama_contrib: 0, breakdown: {} }; }
    /** @private @function _score_relative_volume */
    _score_relative_volume() { return { rv_contrib: 0, breakdown: {} }; }
    /** @private @function _score_market_structure */
    _score_market_structure() { return { ms_contrib: 0, breakdown: {} }; }
    /** @private @function _score_dema_crossover */
    _score_dema_crossover() { return { dema_contrib: 0, breakdown: {} }; }
    /** @private @function _score_keltner_breakout */
    _score_keltner_breakout() { return { kc_contrib: 0, breakdown: {} }; }
    /** @private @function _score_roc */
    _score_roc() { return { roc_contrib: 0, breakdown: {} }; }
    /** @private @function _score_candlestick_patterns */
    _score_candlestick_patterns() { return { pattern_contrib: 0, breakdown: {} }; }
    /** @private @function _score_fibonacci_levels */
    _score_fibonacci_levels() { return { fib_contrib: 0, breakdown: {} }; }
    /** @private @function _score_fibonacci_pivot_points */
    _score_fibonacci_pivot_points() { return { fib_pivot_contrib: 0, breakdown: {} }; }
    /** @private @function _score_ehlers_supertrend */
    _score_ehlers_supertrend() { return { st_contrib: 0, breakdown: {} }; }
    /** @private @function _score_macd */
    _score_macd() { return { macd_contrib: 0, breakdown: {} }; }
    /** @private @function _score_ichimoku_cloud */
    _score_ichimoku_cloud() { return { ichimoku_contrib: 0, breakdown: {} }; }
    /** @private @function _score_orderbook_imbalance */
    _score_orderbook_imbalance() { return { imbalance_contrib: 0, breakdown: {} }; }
}

// --- Main Bot Loop ---
/**
 * @async
 * @function run_bot
 * @description The main execution loop for the Whale strategy. It initializes alert system,
 * position manager, and performance tracker. Continuously fetches kline data,
 * analyzes it for trading signals, manages positions, and updates performance metrics.
 * @returns {Promise<void>}
 */
async function run_bot() {
    const alertSystem = new AlertSystem();

    logger.info(neon.green(`🚀 WhaleBot Started for ${SYMBOL} @ ${INTERVAL}m interval`));

    const positionMgr = new PositionManager(CONFIG, SYMBOL, bybitClient);
    const perfTracker = new PerformanceTracker(CONFIG);

    let latest_orderbook = null; // This will be updated by WebSocketClient if implemented

    while (true) {
        const loop_start_time = Date.now();
        try {
            const klines = await bybitClient.klines(SYMBOL, INTERVAL, 200); // Fetch more klines for indicators
            if (!klines || klines.length === 0) {
                logger.warn(neon.warn("No kline data. Skipping loop."));
                await setTimeout(LOOP_DELAY_SECONDS * 1000);
                continue;
            }

            const current_price = new Decimal(klines[klines.length - 1].close);

            const analyzer = new TradingAnalyzer(klines, CONFIG, SYMBOL);
            const mtfSignals = {};

            if (CONFIG.MTF_ANALYSIS.ENABLED) {
                for (const tf of CONFIG.MTF_ANALYSIS.HIGHER_TIMEFRAMES) {
                    const tfCandles = await bybitClient.klines(SYMBOL, tf, 100);
                    if (tfCandles) {
                        for (const ind of CONFIG.MTF_ANALYSIS.TREND_INDICATORS) {
                            mtfSignals[`${tf}_${ind}`] = analyzer._get_mtf_trend(tfCandles, ind);
                        }
                    }
                    await setTimeout(CONFIG.MTF_ANALYSIS.MTF_REQUEST_DELAY_SECONDS * 1000);
                }
            }

            const { total_score, signal, conviction, breakdown } = analyzer.calculate_signal_score(latest_orderbook, mtfSignals);

            logger.info(neon.cyan(`[SIGNAL] Score: ${total_score.toFixed(2)} | Signal: ${signal} | Conviction: ${conviction.toFixed(2)}`));

            positionMgr.manage_positions(current_price, perfTracker);
            await positionMgr.try_pyramid(current_price, analyzer._get_indicator_value("ATR"));

            if (signal !== "NEUTRAL" && conviction.gt(0.5)) { // Conviction threshold
                const atr = analyzer._get_indicator_value("ATR");
                if (!atr.isNaN() && atr.gt(0)) {
                    await positionMgr.open_position(signal, current_price, atr, conviction);
                }
            }

            const summary = perfTracker.get_summary();
            logger.info(neon.magenta(`[PERFORMANCE] PnL: ${summary.total_pnl.toFixed(2)} | Win Rate: ${summary.win_rate} | DD: ${summary.max_drawdown.toFixed(2)}`));

        } catch (e) {
            logger.error(neon.error(`Main loop error: ${e.message}`));
            alertSystem.send_alert(`Main loop crashed: ${e.message}`, "ERROR");
        }

        const elapsed_time = Date.now() - loop_start_time;
        const remaining_delay = (LOOP_DELAY_SECONDS * 1000) - elapsed_time;
        if (remaining_delay > 0) {
            await setTimeout(remaining_delay);
        }
    }
}

// Start Bot
/**
 * @description Immediately invoked async function to launch the Whale strategy.
 * Handles top-level unhandled errors during the bot's execution.
 */
(async () => {
    try {
        await run_bot();
    } catch (e) {
        logger.critical(neon.error(`Bot terminated due to unhandled error: ${e.message}`), e);
        process.exit(1);
    }
})();