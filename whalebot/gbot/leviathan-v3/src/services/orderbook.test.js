import { LocalOrderBook } from './orderbook.js';

describe('LocalOrderBook', () => {
  let book;

  beforeEach(() => {
    book = new LocalOrderBook(20); // Use a depth of 20 as in the implementation
  });

  test('should process snapshot correctly', () => {
    const snapshotData = {
      b: [['100', '10'], ['99', '5']],
      a: [['101', '12'], ['102', '6']],
    };
    book.update(snapshotData, 'snapshot');
    expect(book.ready).toBe(true);
    expect(book.bids.get(100)).toBe(10);
    expect(book.asks.get(101)).toBe(12);
  });

  test('should process delta updates correctly', () => {
    book.update({ b: [['100', '10']], a: [['101', '12']] }, 'snapshot');
    const deltaData = {
      b: [['100', '0'], ['99.5', '8']],
      a: [['101', '15']],
    };
    book.update(deltaData, 'delta');
    expect(book.bids.has(100)).toBe(false);
    expect(book.bids.get(99.5)).toBe(8);
    expect(book.asks.get(101)).toBe(15);
  });

  test('getBestBidAsk returns correct values', () => {
    book.update({ b: [['100.5', '10'], ['100.4', '20']], a: [['101.1', '12'], ['101.2', '5']] }, 'snapshot');
    const { bid, ask } = book.getBestBidAsk();
    expect(bid).toBe(100.5);
    expect(ask).toBe(101.1);
  });

  test('calculateMetrics correctly computes WMP, spread, and skew', () => {
    book.update({
      b: [['100.0', '10'], ['99.9', '5']],
      a: [['100.1', '15'], ['100.2', '8']],
    }, 'snapshot');
    
    const metrics = book.getAnalysis();

    // Spread: 100.1 - 100.0 = 0.1
    expect(metrics.spread).toBeCloseTo(0.1);
    
    // WMP: ((bestBid * bestAskSize) + (bestAsk * bestBidSize)) / (bestBidSize + bestAskSize)
    // ((100.0 * 15) + (100.1 * 10)) / (10 + 15) = (1500 + 1001) / 25 = 100.04
    expect(metrics.wmp).toBeCloseTo(100.04);
    
    // Skew: (totalBids - totalAsks) / (totalBids + totalAsks)
    // (10 + 5 - (15 + 8)) / (10 + 5 + 15 + 8) = (15 - 23) / 38 = -8 / 38
    expect(metrics.skew).toBeCloseTo(-8 / 38);
  });

  describe('Wall Status Identification', () => {
    it('should identify BALANCED status', () => {
        book.update({ b: [['100', '10']], a: [['101', '12']] }, 'snapshot');
        expect(book.getAnalysis().wallStatus).toBe('BALANCED');
    });

    it('should identify BID_SUPPORT status', () => {
        book.update({ b: [['100', '20']], a: [['101', '10']] }, 'snapshot');
        expect(book.getAnalysis().wallStatus).toBe('BID_SUPPORT');
    });

    it('should identify ASK_RESISTANCE status', () => {
        book.update({ b: [['100', '10']], a: [['101', '20']] }, 'snapshot');
        expect(book.getAnalysis().wallStatus).toBe('ASK_RESISTANCE');
    });

    it('should identify BID_WALL_BROKEN status', () => {
        // First, establish a wall
        book.update({ b: [['100', '20']], a: [['101', '10']] }, 'snapshot');
        expect(book.getAnalysis().wallStatus).toBe('BID_SUPPORT');
      
        // Then, see it break
        book.update({ b: [['100', '5']] }, 'delta'); // Bid wall at 20 is reduced to 5
        expect(book.getAnalysis().wallStatus).toBe('BID_WALL_BROKEN');
    });

    it('should identify ASK_WALL_BROKEN status', () => {
        // First, establish a wall
        book.update({ b: [['100', '10']], a: [['101', '30']] }, 'snapshot');
        expect(book.getAnalysis().wallStatus).toBe('ASK_RESISTANCE');
      
        // Then, see it break
        book.update({ a: [['101', '5']] }, 'delta'); // Ask wall at 30 is reduced to 5
        expect(book.getAnalysis().wallStatus).toBe('ASK_WALL_BROKEN');
    });
  });
});
