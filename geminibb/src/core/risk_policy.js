// src/core/risk_policy.js
import Decimal from 'decimal.js';
import { Logger } from '../utils/logger.js';

const logger = new Logger('RISK_POLICY');

export class RiskPolicy {
    constructor(bybitAdapter) {
        this.bybitAdapter = bybitAdapter;
        this.maxRiskPerTradePercent = new Decimal(0.01); // Example: 1% risk per trade
        this.maxExposurePercent = new Decimal(0.10);    // Example: 10% max total exposure
        this.slippageTolerance = new Decimal(0.001);    // Example: 0.1% slippage tolerance
    }

    /**
     * Validates a proposed trade against risk parameters and available balance.
     * @param {string} symbol - Trading pair (e.g., 'BTCUSDT').
     * @param {string} side - 'Buy' or 'Sell'.
     * @param {Decimal} quantity - Proposed quantity.
     * @param {Decimal} price - Expected execution price.
     * @param {Decimal} [stopLossPrice] - Optional stop loss price.
     * @returns {Promise<object>} - { isValid: boolean, message: string }.
     */
    async validateTradeProposal(symbol, side, quantity, price, stopLossPrice = null) {
        logger.debug(`Validating trade proposal for ${side} ${quantity} ${symbol} at ${price}`);

        if (quantity.isZero() || price.isZero()) {
            return { isValid: false, message: 'Quantity and price must be greater than zero.' };
        }

        try {
            const accountInfo = await this.bybitAdapter.getAccountInfo();
            if (!accountInfo) {
                return { isValid: false, message: 'Could not retrieve account information.' };
            }

            const availableUSDT = accountInfo.balances['USDT'] ? accountInfo.balances['USDT'].available : new Decimal(0);
            const availableCrypto = accountInfo.balances[symbol.replace('USDT', '')] ? accountInfo.balances[symbol.replace('USDT', '')].available : new Decimal(0);
            const totalEquity = accountInfo.totalBalance;

            const tradeValue = quantity.times(price);
            const maxTradeValue = totalEquity.times(this.maxExposurePercent);

            if (tradeValue.greaterThan(maxTradeValue)) {
                return { isValid: false, message: `Trade value (${tradeValue}) exceeds maximum allowed exposure (${maxTradeValue}).` };
            }

            if (side === 'Buy') {
                if (tradeValue.greaterThan(availableUSDT)) {
                    return { isValid: false, message: `Insufficient USDT. Required: ${tradeValue}, Available: ${availableUSDT}.` };
                }
            } else if (side === 'Sell') {
                // For selling, ensure we have enough of the base asset (e.g., BTC for BTCUSDT)
                if (quantity.greaterThan(availableCrypto)) {
                    return { isValid: false, message: `Insufficient ${symbol.replace('USDT', '')}. Required: ${quantity}, Available: ${availableCrypto}.` };
                }
            }

            // If a stop-loss is provided, calculate potential risk
            if (stopLossPrice && stopLossPrice.isPositive()) {
                let potentialLoss = new Decimal(0);
                if (side === 'Buy') {
                    if (stopLossPrice.greaterThanOrEqualTo(price)) {
                        return { isValid: false, message: 'Stop loss price for a buy order must be below the entry price.' };
                    }
                    potentialLoss = price.minus(stopLossPrice).times(quantity);
                } else if (side === 'Sell') {
                    if (stopLossPrice.lessThanOrEqualTo(price)) {
                        return { isValid: false, message: 'Stop loss price for a sell order must be above the entry price.' };
                    }
                    potentialLoss = stopLossPrice.minus(price).times(quantity);
                }

                const maxRiskAmount = totalEquity.times(this.maxRiskPerTradePercent);
                if (potentialLoss.greaterThan(maxRiskAmount)) {
                    return { isValid: false, message: `Potential loss (${potentialLoss}) exceeds maximum allowed risk per trade (${maxRiskAmount}).` };
                }
            }

            logger.info(`Trade proposal for ${side} ${quantity} ${symbol} at ${price} is valid.`);
            return { isValid: true, message: 'Trade proposal is valid.' };

        } catch (error) {
            logger.exception('Error during trade proposal validation:', error);
            return { isValid: false, message: `Error validating trade: ${error.message}` };
        }
    }
}