import { Decimal } from 'decimal.js';
import PerformanceTracker from '../../utils/performance_tracker.js';

// Mock config for the tracker
const mockConfig = {
  TRADE_MANAGEMENT: {
    TRADING_FEE_PERCENT: '0.001' // 0.1% fee
  }
};

describe('PerformanceTracker', () => {
  let tracker;

  beforeEach(() => {
    tracker = new PerformanceTracker(mockConfig);
  });

  it('should initialize with zero values', () => {
    const summary = tracker.get_summary();
    expect(summary.total_trades).toBe(0);
    expect(summary.total_pnl.toString()).toBe('0');
    expect(summary.wins).toBe(0);
    expect(summary.losses).toBe(0);
    expect(summary.win_rate).toBe('0.00%');
    expect(tracker.peak_pnl.toString()).toBe('0');
    expect(tracker.max_drawdown.toString()).toBe('0');
  });

  it('should correctly record a winning trade', () => {
    const position = {
      entry_price: new Decimal('100'),
      exit_price: new Decimal('110'),
      qty: new Decimal('1'),
    };
    const grossPnl = new Decimal('10'); // 110 - 100

    tracker.record_trade(position, grossPnl);

    const summary = tracker.get_summary();
    const entry_fee = new Decimal('100').times('1').times('0.001'); // 0.1
    const exit_fee = new Decimal('110').times('1').times('0.001'); // 0.11
    const total_fees = entry_fee.plus(exit_fee); // 0.21
    const netPnl = grossPnl.minus(total_fees); // 10 - 0.21 = 9.79

    expect(summary.total_trades).toBe(1);
    expect(summary.wins).toBe(1);
    expect(summary.losses).toBe(0);
    expect(summary.total_pnl.toFixed(2)).toBe(netPnl.toFixed(2));
    expect(summary.gross_profit.toFixed(2)).toBe(netPnl.toFixed(2));
    expect(summary.win_rate).toBe('100.00%');
  });

  it('should correctly record a losing trade', () => {
    const position = {
      entry_price: new Decimal('100'),
      exit_price: new Decimal('90'),
      qty: new Decimal('1'),
    };
    const grossPnl = new Decimal('-10'); // 90 - 100

    tracker.record_trade(position, grossPnl);

    const summary = tracker.get_summary();
    const entry_fee = new Decimal('100').times('1').times('0.001'); // 0.1
    const exit_fee = new Decimal('90').times('1').times('0.001');  // 0.09
    const total_fees = entry_fee.plus(exit_fee); // 0.19
    const netPnl = grossPnl.minus(total_fees); // -10 - 0.19 = -10.19

    expect(summary.total_trades).toBe(1);
    expect(summary.wins).toBe(0);
    expect(summary.losses).toBe(1);
    expect(summary.total_pnl.toFixed(2)).toBe(netPnl.toFixed(2));
    expect(summary.gross_loss.toFixed(2)).toBe(netPnl.abs().toFixed(2));
    expect(summary.win_rate).toBe('0.00%');
  });

  it('should calculate win rate and profit factor correctly', () => {
    // Win
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(110), qty: new Decimal(1) }, new Decimal(10));
    // Win
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(120), qty: new Decimal(1) }, new Decimal(20));
    // Loss
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(95), qty: new Decimal(1) }, new Decimal(-5));

    const summary = tracker.get_summary();
    expect(summary.total_trades).toBe(3);
    expect(summary.wins).toBe(2);
    expect(summary.losses).toBe(1);
    expect(summary.win_rate).toBe('66.67%');
    // Gross Profit and Loss are net of fees
    expect(summary.profit_factor.gt(0)).toBe(true);
  });

  it('should calculate profit factor as Infinity if there are no losses', () => {
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(110), qty: new Decimal(1) }, new Decimal(10));
    const summary = tracker.get_summary();
    expect(summary.profit_factor.toString()).toBe('Infinity');
  });

  it('should track peak PnL and max drawdown correctly', () => {
    // 1. Win: PnL = 9.79, Peak = 9.79, Drawdown = 0
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(110), qty: new Decimal(1) }, new Decimal(10));
    expect(tracker.total_pnl.toFixed(2)).toBe('9.79');
    expect(tracker.peak_pnl.toFixed(2)).toBe('9.79');
    expect(tracker.max_drawdown.toFixed(2)).toBe('0.00');

    // 2. Win: PnL = 9.79 + 19.78 = 29.57, Peak = 29.57, Drawdown = 0
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(120), qty: new Decimal(1) }, new Decimal(20));
    expect(tracker.total_pnl.toFixed(2)).toBe('29.57');
    expect(tracker.peak_pnl.toFixed(2)).toBe('29.57');
    expect(tracker.max_drawdown.toFixed(2)).toBe('0.00');

    // 3. Loss: PnL = 29.57 - 5.195 = 24.375, Peak = 29.57, Drawdown = 29.57 - 24.375 = 5.195
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(95), qty: new Decimal(1) }, new Decimal(-5));
    expect(tracker.total_pnl.toFixed(2)).toBe('24.38');
    expect(tracker.peak_pnl.toFixed(2)).toBe('29.57');
    expect(tracker.max_drawdown.toFixed(2)).toBe('5.20');

    // 4. Bigger Loss: PnL = 24.375 - 15.185 = 9.19, Peak = 29.57, Drawdown = 29.57 - 9.19 = 20.38
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(85), qty: new Decimal(1) }, new Decimal(-15));
    expect(tracker.total_pnl.toFixed(2)).toBe('9.19');
    expect(tracker.peak_pnl.toFixed(2)).toBe('29.57');
    expect(tracker.max_drawdown.toFixed(2)).toBe('20.38');
  });

  it('should calculate day_pnl correctly', () => {
    const today = new Date();
    const yesterday = new Date();
    yesterday.setDate(today.getDate() - 1);

    // Today's trade
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(110), qty: new Decimal(1), exit_time: today }, new Decimal(10));
    // Yesterday's trade
    tracker.record_trade({ entry_price: new Decimal(100), exit_price: new Decimal(120), qty: new Decimal(1), exit_time: yesterday }, new Decimal(20));

    const netPnlToday = new Decimal(10).minus(new Decimal(100 * 0.001)).minus(new Decimal(110 * 0.001)); // 9.79
    
    expect(tracker.day_pnl().toFixed(2)).toBe(netPnlToday.toFixed(2));
  });
});