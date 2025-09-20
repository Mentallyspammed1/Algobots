import { KlineIntervalV5, OrderV5 } from 'bybit-api';
import { logger } from '../core/logger';
import { Candle, Position } from '../core/types';
import { IExchange } from './exchange_interface';

export class BacktestService implements IExchange {
    private historical_klines: Candle[] = [];
    private current_kline_index = 0;
    private onCandleCallback: ((candle: Candle) => void) | null = null;
    private onOrderUpdateCallback: ((order: OrderV5) => void) | null = null;
    private onExecutionCallback: ((execution: any) => void) | null = null;

    private simulated_position: Position;
    private simulated_orders: Map<string, OrderV5> = new Map();
    private order_id_counter = 0;

    constructor(historicalData: Candle[]) {
        this.historical_klines = historicalData;
        this.simulated_position = this.getEmptyPosition('BTCUSDT'); // Initialize with an empty position
        logger.system(`BacktestService initialized with ${historicalData.length} historical candles.`);
    }

    // This method will be called by the bot to subscribe to data
    subscribeToStreams(symbol: string, interval: KlineIntervalV5) {
        // In backtest, we don't subscribe to live streams. We simulate them.
        // The bot will call onCandleCallback directly.
        logger.system('BacktestService: Simulating kline stream.');
    }

    // This method is used by the bot to get historical data for warm-up
    async getKlineHistory(symbol: string, interval: KlineIntervalV5, limit: number): Promise<Candle[]> {
        // Return a slice of historical data for warm-up
        return this.historical_klines.slice(0, limit);
    }

    async getPosition(symbol: string): Promise<Position> {
        return this.simulated_position;
    }

    async setLeverage(symbol: string, leverage: number): Promise<void> {
        logger.warn(`BACKTEST: Setting leverage for ${symbol} to ${leverage}x (simulated only).`);
    }

    async placeLimitOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, price: number, reduceOnly: boolean = false): Promise<string | undefined> {
        const orderId = `BACKTEST_ORDER_${this.order_id_counter++}`;
        logger.warn(`BACKTEST: Placing limit ${side} order for ${qty} ${symbol} at ${price}. Order ID: ${orderId}`);
        
        const simulatedOrder: OrderV5 = {
            orderId,
            symbol,
            side,
            orderType: 'Limit',
            price: price.toString(),
            qty: qty.toString(),
            orderStatus: 'New',
            avgPrice: '0',
            cumExecQty: '0',
            cumExecValue: '0',
            orderIv: '0',
            blockTradeId: '',
            cancelType: '0',
            createdTime: Date.now().toString(),
            isLeverage: '0',
            lastPrice: '0',
            leavesQty: qty.toString(),
            leavesValue: (qty * price).toString(),
            orderCategory: 'linear',
            orderLinkId: '',
            positionIdx: 0,
            rejectReason: '',
            stopLoss: '0',
            takeProfit: '0',
            tpslMode: 'Full',
            updatedTime: Date.now().toString(),
            userId: 0,
            triggerPrice: '0',
            triggerBy: '',
            triggerDirection: 0,
            closeOnTrigger: false,
            smpType: 'None',
            smpGroup: 0,
            smpOrderId: '',
            placeType: '0',
            bizType: '0',
            tradeMode: 0,
            feeRate: '0',
            bapiErrorCode: 0,
            bapiErrorMessage: '',
            extMap: {},
        };
        this.simulated_orders.set(orderId, simulatedOrder);
        return orderId;
    }

    async placeConditionalOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, triggerPrice: number, orderType: 'Market' | 'Limit' = 'Market'): Promise<string | undefined> {
        const orderId = `BACKTEST_CONDITIONAL_ORDER_${this.order_id_counter++}`;
        logger.warn(`BACKTEST: Placing conditional ${side} order for ${qty} ${symbol} at trigger ${triggerPrice}. Order ID: ${orderId}`);
        
        const simulatedOrder: OrderV5 = {
            orderId,
            symbol,
            side,
            orderType,
            price: '0',
            qty: qty.toString(),
            orderStatus: 'New',
            triggerPrice: triggerPrice.toString(),
            avgPrice: '0',
            cumExecQty: '0',
            cumExecValue: '0',
            orderIv: '0',
            blockTradeId: '',
            cancelType: '0',
            createdTime: Date.now().toString(),
            isLeverage: '0',
            lastPrice: '0',
            leavesQty: qty.toString(),
            leavesValue: '0',
            orderCategory: 'linear',
            orderLinkId: '',
            positionIdx: 0,
            rejectReason: '',
            stopLoss: '0',
            takeProfit: '0',
            tpslMode: 'Full',
            updatedTime: Date.now().toString(),
            userId: 0,
            triggerBy: '',
            triggerDirection: 0,
            closeOnTrigger: false,
            smpType: 'None',
            smpGroup: 0,
            smpOrderId: '',
            placeType: '0',
            bizType: '0',
            tradeMode: 0,
            feeRate: '0',
            bapiErrorCode: 0,
            bapiErrorMessage: '',
            extMap: {},
        };
        this.simulated_orders.set(orderId, simulatedOrder);
        return orderId;
    }

    async cancelAllOrders(symbol: string): Promise<void> {
        logger.warn(`BACKTEST: Cancelling all simulated orders for ${symbol}.`);
        this.simulated_orders.clear();
    }

    // --- Backtest Specific Methods ---

    // This method is called by the backtest runner to set the bot's callbacks
    setBotCallbacks(onCandle: (candle: Candle) => void, onOrderUpdate: (order: OrderV5) => void, onExecution: (execution: any) => void) {
        this.onCandleCallback = onCandle;
        this.onOrderUpdateCallback = onOrderUpdate;
        this.onExecutionCallback = onExecution;
    }

    // This method simulates the passage of time and feeds candles to the bot
    async runBacktest() {
        for (this.current_kline_index = 0; this.current_kline_index < this.historical_klines.length; this.current_kline_index++) {
            const candle = this.historical_klines[this.current_kline_index];
            
            // Simulate order fills for the current candle
            this.simulateOrderFills(candle);

            // Feed the candle to the bot
            if (this.onCandleCallback) {
                this.onCandleCallback(candle);
            }
        }
        logger.system('Backtest finished.');
    }

    private simulateOrderFills(candle: Candle) {
        this.simulated_orders.forEach((order, orderId) => {
            if (order.orderStatus === 'New') {
                // Simulate limit order fill
                if (order.orderType === 'Limit') {
                    const orderPrice = parseFloat(order.price);
                    const filled = (order.side === 'Buy' && candle.low <= orderPrice && candle.high >= orderPrice) ||
                                   (order.side === 'Sell' && candle.high >= orderPrice && candle.low <= orderPrice);
                    if (filled) {
                        order.orderStatus = 'Filled';
                        order.avgPrice = order.price; // Filled at limit price
                        order.cumExecQty = order.qty;
                        order.cumExecValue = (parseFloat(order.qty) * orderPrice).toString();
                        logger.success(`BACKTEST: Simulated limit order ${orderId} filled at ${orderPrice}`);
                        if (this.onOrderUpdateCallback) this.onOrderUpdateCallback(order);
                        this.simulateExecution(order);
                    }
                }
                // Simulate conditional order fill (Market type for simplicity)
                else if (order.triggerPrice && order.orderType === 'Market') {
                    const triggerPrice = parseFloat(order.triggerPrice);
                    const triggered = (order.side === 'Buy' && candle.high >= triggerPrice) ||
                                     (order.side === 'Sell' && candle.low <= triggerPrice);
                    if (triggered) {
                        order.orderStatus = 'Filled';
                        order.avgPrice = candle.close.toString(); // Filled at market price
                        order.cumExecQty = order.qty;
                        order.cumExecValue = (parseFloat(order.qty) * candle.close).toString();
                        logger.success(`BACKTEST: Simulated conditional order ${orderId} triggered and filled at ${candle.close}`);
                        if (this.onOrderUpdateCallback) this.onOrderUpdateCallback(order);
                        this.simulateExecution(order);
                    }
                }
            }
        });
    }

    private simulateExecution(order: OrderV5) {
        const simulatedExec = {
            symbol: order.symbol,
            orderId: order.orderId,
            side: order.side,
            execPrice: order.avgPrice!,
            execQty: order.cumExecQty!,
            execFee: (parseFloat(order.cumExecValue!) * 0.0005).toString(), // Simulate 0.05% fee
            execTime: Date.now().toString(),
        };
        if (this.onExecutionCallback) this.onExecutionCallback(simulatedExec);
    }

    private getEmptyPosition(symbol: string): Position {
        return {
            symbol,
            side: 'None',
            size: 0,
            entry_price: 0,
            unrealised_pnl: 0,
        };
    }
}
