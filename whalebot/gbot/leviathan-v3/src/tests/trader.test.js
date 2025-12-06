import { Trader } from '../trader.js';
import { Decimal } from 'decimal.js';

// Mock dependencies
const mockExchange = {
    placeOrder: jest.fn(),
    getFundingRate: jest.fn(),
    getPos: jest.fn(),
    // Add other methods if needed by Trader, e.g., getSymbol()
    getSymbol: jest.fn().mockReturnValue('BTCUSDT'),
};

const mockCircuitBreaker = {
    isOpen: jest.fn(),
    trip: jest.fn(),
};

const mockConfig = {
    symbol: 'BTCUSDT',
    risk: {
        maxRiskPerTrade: 1.0,
        leverage: 5,
        fee: 0.00055,
        slippage: 0.0001,
        rewardRatio: 1.5,
        iceberg: { enabled: false, slices: 3 },
        loss_streak_threshold: 3,
    },
    ai: {
        minConfidence: 0.7,
    }
};

describe('Trader', () => {
    let trader;

    beforeEach(() => {
        // Reset mocks before each test
        jest.clearAllMocks();
        trader = new Trader(mockExchange, mockCircuitBreaker, mockConfig);
    });

    describe('_calculateRiskSize', () => {
        it('should return 0 if balance is zero or negative', () => {
            expect(trader._calculateRiskSize({ sl: 100, confidence: 0.9 }, 1000, 0)).toBe(0);
            expect(trader._calculateRiskSize({ sl: 100, confidence: 0.9 }, 1000, -100)).toBe(0);
        });

        it('should return 0 if stop loss is invalid', () => {
            expect(trader._calculateRiskSize({ sl: 0, confidence: 0.9 }, 1000, 1000)).toBe(0);
            expect(trader._calculateRiskSize({ sl: -10, confidence: 0.9 }, 1000, 1000)).toBe(0);
            expect(trader._calculateRiskSize({ sl: undefined, confidence: 0.9 }, 1000, 1000)).toBe(0);
        });

        it('should return 0 if confidence is invalid', () => {
            expect(trader._calculateRiskSize({ sl: 100, confidence: 0 }, 1000, 1000)).toBe(0);
            expect(trader._calculateRiskSize({ sl: 100, confidence: -0.5 }, 1000, 1000)).toBe(0);
        });

        it('should calculate size correctly for a valid trade', () => {
            // Balance: 10000, Risk: 1% (100), Entry: 1000, SL: 990 (distance 10)
            // Qty = 100 / 10 = 10
            const size = trader._calculateRiskSize({ sl: 990, confidence: 0.9 }, 1000, 10000);
            expect(size).toBe(10.000); // Expecting 3 decimal places rounded down
        });

        it('should cap size by leverage', () => {
            // Balance: 10000, Risk: 1% (100), Entry: 1000, SL: 999 (distance 1) -> Qty calc = 100
            // Leverage: 5 -> Max Qty = (10000 * 5) / 1000 = 50
            // Should return 50
            const size = trader._calculateRiskSize({ sl: 999, confidence: 0.9 }, 1000, 10000);
            expect(size).toBe(50.000);
        });

        it('should handle zero risk amount correctly', () => {
             // If risk amount is effectively zero due to balance or riskPct
            const size = trader._calculateRiskSize({ sl: 990, confidence: 0.9 }, 1000, 0.01); // Very small balance
            expect(size).toBe(0);
        });
    });

    describe('_checkFundingSafe', () => {
        it('should return true for BUY with low positive funding rate', async () => {
            mockExchange.getFundingRate.mockResolvedValue(0.0001); // 0.01%
            expect(await trader._checkFundingSafe('BUY')).toBe(true);
        });

        it('should return false for BUY with high positive funding rate', async () => {
            mockExchange.getFundingRate.mockResolvedValue(0.0006); // 0.06%
            expect(await trader._checkFundingSafe('BUY')).toBe(false);
        });

        it('should return true for SELL with low negative funding rate', async () => {
            mockExchange.getFundingRate.mockResolvedValue(-0.0001); // -0.01%
            expect(await trader._checkFundingSafe('SELL')).toBe(true);
        });

        it('should return false for SELL with high negative funding rate', async () => {
            mockExchange.getFundingRate.mockResolvedValue(-0.0006); // -0.06%
            expect(await trader._checkFundingSafe('SELL')).toBe(false);
        });

        it('should return true for BUY/SELL with zero funding rate', async () => {
            mockExchange.getFundingRate.mockResolvedValue(0);
            expect(await trader._checkFundingSafe('BUY')).toBe(true);
            expect(await trader._checkFundingSafe('SELL')).toBe(true);
        });
        
        it('should handle errors from getFundingRate gracefully', async () => {
            mockExchange.getFundingRate.mockRejectedValue(new Error('API Error'));
            // Should default to true (allow trade) if error occurs, as it's a warning/filter, not a hard block.
            // Or, it could default to false if we want to be overly cautious. Current logic returns true.
            expect(await trader._checkFundingSafe('BUY')).toBe(true); 
        });
    });

    describe('_placeIcebergOrder', () => {
        const mockSignal = { sl: 990, tp: 1010, aiDecision: { decision: 'BUY' } };
        const entryPrice = 1000;
        const totalQty = 10;

        it('should place a single limit order if iceberg is disabled', async () => {
            mockConfig.risk.iceberg.enabled = false;
            mockConfig.risk.iceberg.slices = 3; // Ensure slices doesn't affect when disabled
            mockExchange.placeOrder.mockResolvedValue({ orderId: 'single-order-123' });

            await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
            expect(mockExchange.placeOrder).toHaveBeenCalledWith(
                'BTCUSDT', 'Buy', totalQty, entryPrice,
                expect.objectContaining({ type: 'Limit', timeInForce: 'PostOnly', sl: 990, tp: 1010 })
            );
        });

        it('should place a single limit order if slices is 1', async () => {
            mockConfig.risk.iceberg.enabled = true;
            mockConfig.risk.iceberg.slices = 1;
            mockExchange.placeOrder.mockResolvedValue({ orderId: 'single-order-124' });

            await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
            expect(mockExchange.placeOrder).toHaveBeenCalledWith(
                'BTCUSDT', 'Buy', totalQty, entryPrice,
                expect.objectContaining({ type: 'Limit', timeInForce: 'PostOnly', sl: 990, tp: 1010 })
            );
        });

        it('should place multiple limit orders if iceberg is enabled with slices > 1', async () => {
            mockConfig.risk.iceberg.enabled = true;
            mockConfig.risk.iceberg.slices = 3;
            mockExchange.placeOrder.mockResolvedValue({ orderId: 'iceberg-slice-order' });

            await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            // Expect 3 calls to placeOrder
            expect(mockExchange.placeOrder).toHaveBeenCalledTimes(3);
            
            // Check parameters for the first slice (price slightly lower)
            const firstCallArgs = mockExchange.placeOrder.mock.calls[0];
            expect(firstCallArgs[0]).toBe('BTCUSDT'); // Symbol
            expect(firstCallArgs[1]).toBe('Buy'); // Side
            expect(firstCallArgs[2]).toBe('3.333'); // Qty (totalQty / slices, rounded down)
            expect(firstCallArgs[3]).toBeCloseTo(1000 - (0 * 0.1 * 0.5)); // Price for slice 0
            expect(firstCallArgs[4]).toEqual(expect.objectContaining({ type: 'Limit', timeInForce: 'PostOnly', sl: 990, tp: 1010 }));

             // Check parameters for the second slice (price slightly lower)
            const secondCallArgs = mockExchange.placeOrder.mock.calls[1];
            expect(secondCallArgs[3]).toBeCloseTo(1000 - (1 * 0.1 * 0.5)); // Price for slice 1

            // Check parameters for the third slice (price slightly lower)
            const thirdCallArgs = mockExchange.placeOrder.mock.calls[2];
            expect(thirdCallArgs[3]).toBeCloseTo(1000 - (2 * 0.1 * 0.5)); // Price for slice 2
        });

        it('should return the first order result', async () => {
            mockConfig.risk.iceberg.enabled = true;
            mockConfig.risk.iceberg.slices = 2;
            const firstOrder = { orderId: 'iceberg-first' };
            mockExchange.placeOrder.mockResolvedValueOnce(firstOrder).mockResolvedValue({ orderId: 'iceberg-second' });

            const result = await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            expect(result).toBe(firstOrder);
        });

        it('should return null if all slices fail', async () => {
            mockConfig.risk.iceberg.enabled = true;
            mockConfig.risk.iceberg.slices = 2;
            mockExchange.placeOrder.mockResolvedValue(null).mockResolvedValue(null);

            const result = await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            expect(result).toBeNull();
        });

        it('should handle errors during order placement gracefully', async () => {
            mockConfig.risk.iceberg.enabled = true;
            mockConfig.risk.iceberg.slices = 2;
            mockExchange.placeOrder.mockRejectedValueOnce(new Error('API Error')).mockResolvedValue({ orderId: 'second-order' });

            const result = await trader._placeIcebergOrder(mockSignal, entryPrice, totalQty);
            expect(mockExchange.placeOrder).toHaveBeenCalledTimes(2);
            expect(result).toEqual({ orderId: 'second-order' }); // Should return the successful one
        });
    });

    describe('execute', () => {
        const mockAIState = {
            currentPrice: 1000,
            position: 'none',
            balance: 10000,
            consecutiveLosses: 0,
            entryPrice: null,
            signal: 'HOLD',
            aiDecision: { decision: 'HOLD', confidence: 0, sl: 0, tp: 0, aiEntry: 0 }
        };
        const mockAIStateLong = { ...mockAIState, position: 'long', entryPrice: 995, balance: 9950, consecutiveLosses: 1, aiDecision: { decision: 'SELL', confidence: 0.9, sl: 990, tp: 1010, aiEntry: 995 } };
        const mockAIStateBuy = { ...mockAIState, aiDecision: { decision: 'BUY', confidence: 0.9, sl: 990, tp: 1010, aiEntry: 995 } };

        it('should do nothing if circuit breaker is open', async () => {
            mockCircuitBreaker.isOpen.mockReturnValue(true);
            const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);
            expect(mockExchange.placeOrder).not.toHaveBeenCalled();
            expect(result.newPosition).toBe('none');
        });

        it('should do nothing if consecutive losses exceed threshold', async () => {
            mockCircuitBreaker.isOpen.mockReturnValue(false);
            const stateWithHighLosses = { ...mockAIState, consecutiveLosses: 3 }; // Threshold is 3
            const result = await trader.execute(mockAIStateBuy.aiDecision, stateWithHighLosses);
            expect(mockExchange.placeOrder).not.toHaveBeenCalled();
            expect(result.newPosition).toBe('none');
        });

        it('should do nothing if currentPrice is invalid', async () => {
            mockCircuitBreaker.isOpen.mockReturnValue(false);
            const stateWithInvalidPrice = { ...mockAIState, currentPrice: NaN };
            const result = await trader.execute(mockAIStateBuy.aiDecision, stateWithInvalidPrice);
            expect(mockExchange.placeOrder).not.toHaveBeenCalled();
            expect(result.newPosition).toBe('none');
        });

        describe('BUY signal execution', () => {
            beforeEach(() => {
                mockCircuitBreaker.isOpen.mockReturnValue(false);
                mockConfig.risk.iceberg.enabled = false; // Default to single order for most tests
            });

            it('should do nothing if AI confidence is too low', async () => {
                const lowConfidenceAI = { ...mockAIStateBuy.aiDecision, confidence: 0.5 };
                const result = await trader.execute(lowConfidenceAI, mockAIStateBuy);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('none');
            });

            it('should do nothing if calculated BUY quantity is zero', async () => {
                jest.spyOn(trader, '_calculateRiskSize').mockReturnValue(0);
                const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('none');
            });

            it('should skip BUY if funding is unsafe', async () => {
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(false);
                const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('none');
            });

            it('should place a BUY order if conditions are met', async () => {
                jest.spyOn(trader, '_calculateRiskSize').mockReturnValue(10);
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(true);
                mockExchange.placeOrder.mockResolvedValue({ orderId: 'buy-order-1' });

                const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);

                expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
                expect(mockExchange.placeOrder).toHaveBeenCalledWith(
                    'BTCUSDT', 'Buy', 10, mockAIStateBuy.aiDecision.aiEntry,
                    expect.objectContaining({ type: 'Limit', timeInForce: 'GTC', sl: 990, tp: 1010 })
                );
                expect(result.orderResult).toEqual({ orderId: 'buy-order-1' });
                expect(result.newPosition).toBe('long');
                expect(result.newEntryPrice).toBe(mockAIStateBuy.aiDecision.aiEntry);
            });

            it('should use iceberg order if enabled', async () => {
                jest.spyOn(trader, '_calculateRiskSize').mockReturnValue(10);
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(true);
                jest.spyOn(trader, '_placeIcebergOrder').mockResolvedValue({ orderId: 'iceberg-buy-order' });
                mockConfig.risk.iceberg.enabled = true;

                const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);

                expect(trader._placeIcebergOrder).toHaveBeenCalledTimes(1);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled(); // Ensure single placeOrder isn't called
                expect(result.orderResult).toEqual({ orderId: 'iceberg-buy-order' });
                expect(result.newPosition).toBe('long');
            });
            
             it('should handle BUY order placement failure', async () => {
                jest.spyOn(trader, '_calculateRiskSize').mockReturnValue(10);
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(true);
                mockExchange.placeOrder.mockResolvedValue(null); // Simulate failed order

                const result = await trader.execute(mockAIStateBuy.aiDecision, mockAIStateBuy);

                expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
                expect(result.orderResult).toBeNull();
                expect(result.newPosition).toBe('none'); // Position should not change
                expect(result.newEntryPrice).toBeNull(); // Entry price should reset
            });
        });

        describe('SELL signal execution', () => {
            beforeEach(() => {
                mockCircuitBreaker.isOpen.mockReturnValue(false);
                // Setup a long position for sell tests
                mockExchange.getPos.mockResolvedValue({ qty: 10, side: 'long', entry: 995 });
            });

            it('should do nothing if AI confidence is too low', async () => {
                const lowConfidenceAI = { ...mockAIStateLong.aiDecision, confidence: 0.5 };
                const result = await trader.execute(lowConfidenceAI, mockAIStateLong);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('long'); // Position remains unchanged
            });

            it('should do nothing if quantity to close is zero', async () => {
                jest.spyOn(mockExchange, 'getPos').mockResolvedValue({ qty: 0, side: 'long' }); // Zero quantity
                const result = await trader.execute(mockAIStateLong.aiDecision, mockAIStateLong);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('long');
            });
            
             it('should do nothing if position side is not "long" when selling', async () => {
                mockExchange.getPos.mockResolvedValue({ qty: 10, side: 'short', entry: 1005 }); // Incorrect side
                const result = await trader.execute(mockAIStateLong.aiDecision, mockAIStateLong);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('long'); // Position remains unchanged
            });

            it('should skip SELL if funding is unsafe', async () => {
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(false);
                const result = await trader.execute(mockAIStateLong.aiDecision, mockAIStateLong);
                expect(mockExchange.placeOrder).not.toHaveBeenCalled();
                expect(result.newPosition).toBe('long');
            });

            it('should place a SELL order to close position if conditions are met', async () => {
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(true);
                mockExchange.placeOrder.mockResolvedValue({ orderId: 'sell-order-1' });

                const result = await trader.execute(mockAIStateLong.aiDecision, mockAIStateLong);

                expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
                expect(mockExchange.placeOrder).toHaveBeenCalledWith(
                    'BTCUSDT', 'Sell', 10, mockAIStateLong.currentPrice,
                    expect.objectContaining({ type: 'Market', timeInForce: 'GTC' })
                );
                expect(result.orderResult).toEqual({ orderId: 'sell-order-1' });
                expect(result.newPosition).toBe('none');
                expect(result.newEntryPrice).toBeNull();
            });
            
            it('should handle SELL order placement failure', async () => {
                jest.spyOn(trader, '_checkFundingSafe').mockResolvedValue(true);
                mockExchange.placeOrder.mockResolvedValue(null); // Simulate failed order

                const result = await trader.execute(mockAIStateLong.aiDecision, mockAIStateLong);

                expect(mockExchange.placeOrder).toHaveBeenCalledTimes(1);
                expect(result.orderResult).toBeNull();
                expect(result.newPosition).toBe('long'); // Position should remain unchanged
                expect(result.newEntryPrice).toBe(mockAIStateLong.entryPrice);
            });
        });

        it('should do nothing if AI decision is HOLD', async () => {
            const holdAI = { decision: 'HOLD', confidence: 0.5, sl: 0, tp: 0, aiEntry: 0 };
            const result = await trader.execute(holdAI, mockAIState);
            expect(mockExchange.placeOrder).not.toHaveBeenCalled();
            expect(result.newPosition).toBe('none');
        });
    });
});
