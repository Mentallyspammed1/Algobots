import { KlineIntervalV5, OrderV5 } from 'bybit-api';
import { logger } from '../core/logger';
import { Candle, Position } from '../core/types';
import { LiveBybitService } from './live_bybit_service';

export class DryRunBybitService extends LiveBybitService {
    private simulated_position: Position;
    private simulated_orders: Map<string, OrderV5> = new Map();
    private order_id_counter = 0;

    constructor(apiKey: string, apiSecret: string, testnet: boolean, callbacks: { onCandle: (candle: Candle) => void; onOrderUpdate: (order: OrderV5) => void; onExecution: (execution: any) => void; }) {
        super(apiKey, apiSecret, testnet, callbacks);
        this.simulated_position = this.getEmptyPosition('BTCUSDT'); // Initialize with an empty position
        logger.system('DryRunBybitService initialized. All trades will be simulated.');
    }

    // Override order placement methods to simulate
    async placeLimitOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, price: number, reduceOnly: boolean = false): Promise<string | undefined> {
        const orderId = `DRY_RUN_ORDER_${this.order_id_counter++}`;
        logger.warn(`DRY RUN: Placing limit ${side} order for ${qty} ${symbol} at ${price}. Order ID: ${orderId}`);
        
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
            // Add other required fields if any
        };
        this.simulated_orders.set(orderId, simulatedOrder);
        return orderId;
    }

    async placeConditionalOrder(symbol: string, side: 'Buy' | 'Sell', qty: number, triggerPrice: number, orderType: 'Market' | 'Limit' = 'Market'): Promise<string | undefined> {
        const orderId = `DRY_RUN_CONDITIONAL_ORDER_${this.order_id_counter++}`;
        logger.warn(`DRY RUN: Placing conditional ${side} order for ${qty} ${symbol} at trigger ${triggerPrice}. Order ID: ${orderId}`);
        
        const simulatedOrder: OrderV5 = {
            orderId,
            symbol,
            side,
            orderType,
            price: '0',
            qty: qty.toString(),
            orderStatus: 'New',
            triggerPrice: triggerPrice.toString(),
            // Add other required fields
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
        logger.warn(`DRY RUN: Cancelling all simulated orders for ${symbol}.`);
        this.simulated_orders.clear();
    }

    // Simulate order fills based on incoming candles
    subscribeToStreams(symbol: string, interval: KlineIntervalV5) {
        super.subscribeToStreams(symbol, interval); // Still get live data
        
        // Override the onCandle callback to simulate fills
        const originalOnCandle = this.callbacks.onCandle;
        this.callbacks.onCandle = (candle: Candle) => {
            originalOnCandle(candle);
            this.simulateOrderFills(candle);
        };
    }

    private simulateOrderFills(candle: Candle) {
        this.simulated_orders.forEach((order, orderId) => {
            if (order.orderStatus === 'New') {
                // Simulate limit order fill
                if (order.orderType === 'Limit') {
                    const orderPrice = parseFloat(order.price);
                    const filled = (order.side === 'Buy' && candle.low <= orderPrice) ||
                                   (order.side === 'Sell' && candle.high >= orderPrice);
                    if (filled) {
                        order.orderStatus = 'Filled';
                        order.avgPrice = order.price; // Filled at limit price
                        order.cumExecQty = order.qty;
                        order.cumExecValue = (parseFloat(order.qty) * orderPrice).toString();
                        logger.success(`DRY RUN: Simulated limit order ${orderId} filled at ${orderPrice}`);
                        this.callbacks.onOrderUpdate(order);
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
                        logger.success(`DRY RUN: Simulated conditional order ${orderId} triggered and filled at ${candle.close}`);
                        this.callbacks.onOrderUpdate(order);
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
        this.callbacks.onExecution(simulatedExec);
    }

    // Override getPosition to return simulated position
    async getPosition(symbol: string): Promise<Position> {
        // In a real dry run, you'd update this based on simulated fills
        // For simplicity, we'll just return the last known simulated position
        return this.simulated_position;
    }

    // Override setLeverage (no actual action needed in dry run)
    async setLeverage(symbol: string, leverage: number): Promise<void> {
        logger.warn(`DRY RUN: Setting leverage for ${symbol} to ${leverage}x (simulated only).`);
    }

    // Override getKlineHistory (still uses live service for historical data)
    async getKlineHistory(symbol: string, interval: KlineIntervalV5, limit: number): Promise<Candle[]> {
        return super.getKlineHistory(symbol, interval, limit);
    }
}
