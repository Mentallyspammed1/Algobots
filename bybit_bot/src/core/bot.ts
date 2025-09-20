import { LiveBybitService } from '../services/live_bybit_service';
import { IStrategy } from '../strategies/base_strategy';
import { BotConfig, Candle, Position } from './types';
import { logger } from './logger';
import { OrderV5 } from 'bybit-api';
import { Trade, TradeMetrics } from './trade_metrics';

type TradingState = 'IDLE' | 'PENDING_ENTRY' | 'IN_POSITION';

interface ActiveTrade {
    entry_price: number;
    size: number;
    side: 'Buy' | 'Sell';
    entry_timestamp: number;
}

export class TradingBot {
  private bybit_service: BybitService;
  private strategy: IStrategy;
  private config: BotConfig;
  private metrics: TradeMetrics;

  // State management
  private state: TradingState = 'IDLE';
  private active_entry_order_id: string | null = null;
  private active_tp_order_id: string | null = null;
  private active_sl_order_id: string | null = null;
  private active_trade: ActiveTrade | null = null;

  constructor(config: BotConfig, strategy: IStrategy) {
    this.config = config;
    this.strategy = strategy;
    this.metrics = new TradeMetrics();
    this.bybit_service = new BybitService(
        config.env.BYBIT_API_KEY,
        config.env.BYBIT_API_SECRET,
        config.env.BYBIT_TESTNET,
        {
            onCandle: (candle) => this.onCandle(candle),
            onOrderUpdate: (order) => this.onOrderUpdate(order),
            onExecution: (exec) => this.onExecution(exec),
        }
    );
  }

  public getTradeMetrics(): TradeMetrics {
    return this.metrics;
  }

  async run() {
    logger.system(`Starting bot for ${this.config.symbol} with strategy: ${this.strategy.name}`);
    await this.initialise();
    this.bybit_service.subscribeToStreams(this.config.symbol, this.config.interval);
  }

  private async initialise() {
    await this.bybit_service.cancelAllOrders(this.config.symbol);
    await this.bybit_service.setLeverage(this.config.symbol, this.config.leverage);
    const position = await this.bybit_service.getPosition(this.config.symbol);
    this.state = position.size > 0 ? 'IN_POSITION' : 'IDLE';
    logger.system(`Initial state: ${this.state}. Position size: ${position.size}`);

    const klines = await this.bybit_service.getKlineHistory(this.config.symbol, this.config.interval, 200);
    if (klines.length > 0) {
        klines.forEach(k => this.strategy.update(k));
        logger.success(`Strategy warmed up with ${klines.length} historical candles.`);
    }
  }

  private onCandle(candle: Candle) {
    logger.info('\n--- New Candle Received ---');
    this.strategy.update(candle);

    if (this.state === 'IDLE') {
        this.handleIdleState(candle);
    }
  }

  private onOrderUpdate(order: OrderV5) {
    logger.info(`Order update received: ID=${order.orderId}, Status=${order.orderStatus}`);
    if (this.state === 'PENDING_ENTRY' && order.orderId === this.active_entry_order_id) {
        if (order.orderStatus === 'Filled') {
            this.handleEntryOrderFilled(order);
        } else if (order.orderStatus === 'Cancelled' || order.orderStatus === 'Rejected') {
            logger.warn('Entry order did not fill. Returning to IDLE state.');
            this.resetToIdle();
        }
    }
  }

  private onExecution(exec: any) {
    const isExit = exec.orderId === this.active_sl_order_id || exec.orderId === this.active_tp_order_id;
    if (this.state === 'IN_POSITION' && isExit && this.active_trade) {
        const exit_price = parseFloat(exec.execPrice);
        const fees = parseFloat(exec.execFee);
        const pnl = (this.active_trade.side === 'Buy') 
            ? (exit_price - this.active_trade.entry_price) * this.active_trade.size - fees
            : (this.active_trade.entry_price - exit_price) * this.active_trade.size - fees;

        const trade: Trade = {
            symbol: this.config.symbol,
            side: this.active_trade.side,
            entry_price: this.active_trade.entry_price,
            exit_price,
            size: this.active_trade.size,
            pnl,
            pnl_pct: (pnl / (this.active_trade.entry_price * this.active_trade.size)) * 100,
            fees,
            entry_timestamp: this.active_trade.entry_timestamp,
            exit_timestamp: parseInt(exec.execTime),
        };

        this.metrics.addTrade(trade);
        this.metrics.displaySummary();
        this.resetToIdle();
    }
  }

  private async handleIdleState(candle: Candle) {
    const signal = this.strategy.getSignal();
    logger.info(`State: IDLE. Signal: ${signal}`);

    if (signal === 'hold') return;

    const trade_qty = this.config.position_size_usd / candle.close;
    let entry_price: number;

    if (this.config.entry_order_type === 'Limit') {
        const offset = candle.close * this.config.limit_order_price_offset_pct;
        entry_price = signal === 'long' ? candle.close - offset : candle.close + offset;
    } else {
        entry_price = candle.close; // For market order, price is indicative
    }

    const orderId = await this.bybit_service.placeLimitOrder(this.config.symbol, signal === 'long' ? 'Buy' : 'Sell', trade_qty, entry_price);
    if (orderId) {
        this.active_entry_order_id = orderId;
        this.state = 'PENDING_ENTRY';
        logger.system(`State changed to PENDING_ENTRY. Waiting for order ${orderId} to fill.`);
    }
  }

  private async handleEntryOrderFilled(order: OrderV5) {
    const entry_price = parseFloat(order.avgPrice!);
    const size = parseFloat(order.cumExecQty);

    logger.success(`Entry order ${order.orderId} filled at ${entry_price}!`);
    this.state = 'IN_POSITION';
    this.active_entry_order_id = null;
    this.active_trade = { entry_price, size, side: order.side!, entry_timestamp: parseInt(order.updatedTime!) };

    const { stop_loss_pct, take_profit_pct } = this.config;

    if (order.side === 'Buy') {
        const stopLoss = entry_price * (1 - stop_loss_pct);
        const takeProfit = entry_price * (1 + take_profit_pct);
        this.active_sl_order_id = await this.bybit_service.placeConditionalOrder(this.config.symbol, 'Sell', size, stopLoss);
        this.active_tp_order_id = await this.bybit_service.placeConditionalOrder(this.config.symbol, 'Sell', size, takeProfit);
    } else { // Sell side
        const stopLoss = entry_price * (1 + stop_loss_pct);
        const takeProfit = entry_price * (1 - take_profit_pct);
        this.active_sl_order_id = await this.bybit_service.placeConditionalOrder(this.config.symbol, 'Buy', size, stopLoss);
        this.active_tp_order_id = await this.bybit_service.placeConditionalOrder(this.config.symbol, 'Buy', size, takeProfit);
    }
    logger.system(`State changed to IN_POSITION. SL/TP orders placed.`);
  }

  private async resetToIdle() {
    this.state = 'IDLE';
    this.active_entry_order_id = null;
    this.active_sl_order_id = null;
    this.active_tp_order_id = null;
    this.active_trade = null;
    await this.bybit_service.cancelAllOrders(this.config.symbol);
    logger.system('State reset to IDLE.');
  }
}