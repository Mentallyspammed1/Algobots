// src/patterns/pattern_recognition_processor.js
import Decimal from 'decimal.js';
import { Logger } from '../utils/logger.js';

const logger = new Logger('PATTERN_PROCESSOR');

export class PatternRecognitionProcessor {
    constructor() {
        logger.info('PatternRecognitionProcessor initialized.');
    }

    /**
     * Detects if the last candle is a Doji.
     * A Doji indicates indecision, with open and close prices very close.
     * @param {object} candle - The candlestick object {open, high, low, close}.
     * @returns {object|null} - { pattern: 'Doji', confidence: number, signal: 'Neutral' } or null.
     */
    isDoji(candle) {
        const body = candle.close.minus(candle.open).abs();
        const range = candle.high.minus(candle.low);
        if (range.isZero()) return null; // Avoid division by zero
        const bodyRatio = body.dividedBy(range);

        // If body is less than a small percentage of the total range (e.g., 5-10%)
        if (bodyRatio.lessThan(new Decimal(0.1))) { // Adjust threshold as needed
            return { pattern: 'Doji', confidence: 0.6, signal: 'Neutral' };
        }
        return null;
    }

    /**
     * Detects if the last candle is a Hammer or Hanging Man.
     * Hammer (bullish): small body at top, long lower shadow.
     * Hanging Man (bearish): small body at top, long lower shadow, occurs after an uptrend.
     * @param {object} candle - The candlestick object {open, high, low, close}.
     * @returns {object|null} - Pattern details or null.
     */
    isHammerOrHangingMan(candle) {
        const body = candle.close.minus(candle.open).abs();
        const lowerShadow = Decimal.min(candle.open, candle.close).minus(candle.low);
        const upperShadow = candle.high.minus(Decimal.max(candle.open, candle.close));

        // Conditions: Small body, little to no upper shadow, long lower shadow
        if (body.lessThan(new Decimal(candle.high.minus(candle.low).times(0.2))) && // Body < 20% of range
            upperShadow.lessThan(new Decimal(candle.high.minus(candle.low).times(0.1))) && // Small upper shadow
            lowerShadow.greaterThan(body.times(2))) { // Lower shadow at least twice the body
            // We need trend context to differentiate Hammer (bullish reversal after downtrend)
            // from Hanging Man (bearish reversal after uptrend).
            return { pattern: 'Hammer/Hanging Man', confidence: 0.7, signal: 'Context Dependent' };
        }
        return null;
    }

    /**
     * Detects an Engulfing pattern (Bullish or Bearish).
     * Bullish: Small bearish candle followed by large bullish candle that engulfs previous.
     * Bearish: Small bullish candle followed by large bearish candle that engulfs previous.
     * @param {Array<object>} candles - Array of at least two candlestick objects.
     * @returns {object|null} - Pattern details or null.
     */
    isEngulfing(candles) {
        if (candles.length < 2) return null;
        const prev = candles[candles.length - 2];
        const curr = candles[candles.length - 1];

        // Check if previous candle is bearish and current is bullish
        if (prev.close.lessThan(prev.open) && curr.close.greaterThan(curr.open)) { // Previous red, current green
            // Current body engulfs previous body (low of current <= low of prev AND high of current >= high of prev)
            if (curr.low.lessThanOrEqualTo(prev.low) && curr.high.greaterThanOrEqualTo(prev.high)) {
                 return { pattern: 'Bullish Engulfing', confidence: 0.8, signal: 'Bullish' };
            }
        }
        // Check if previous candle is bullish and current is bearish
        else if (prev.close.greaterThan(prev.open) && curr.close.lessThan(curr.open)) { // Previous green, current red
            // Current body engulfs previous body
            if (curr.low.lessThanOrEqualTo(prev.low) && curr.high.greaterThanOrEqualTo(prev.high)) {
                return { pattern: 'Bearish Engulfing', confidence: 0.8, signal: 'Bearish' };
            }
        }
        return null;
    }

    /**
     * Analyzes candlestick data for common patterns.
     * @param {Array<object>} candles - Array of candlestick data {open, high, low, close, volume}.
     * @returns {Array<object>} - Array of detected patterns.
     */
    analyzeCandlestickPatterns(candles) {
        if (candles.length < 1) {
            return [];
        }

        const detectedPatterns = [];
        const lastCandle = candles[candles.length - 1];

        // Check for Doji
        const doji = this.isDoji(lastCandle);
        if (doji) detectedPatterns.push(doji);

        // Check for Hammer/Hanging Man (requires trend context which we don't have here)
        // For simplicity, just detect the shape
        const hammerOrHangingMan = this.isHammerOrHangingMan(lastCandle);
        if (hammerOrHangingMan) detectedPatterns.push(hammerOrHangingMan);

        // Check for Engulfing (requires at least 2 candles)
        const engulfing = this.isEngulfing(candles);
        if (engulfing) detectedPatterns.push(engulfing);

        // Add more patterns here (e.g., Harami, Morning Star, Evening Star, Three White Soldiers, Three Black Crows)

        logger.debug(`Detected ${detectedPatterns.length} candlestick patterns.`);
        return detectedPatterns;
    }

    /**
     * Delegates complex chart pattern analysis (e.g., head and shoulders, double top/bottom) to Gemini AI.
     * This would typically involve sending a textual description or image of the chart to the AI.
     * @param {string} chartDescription - Textual description of the chart.
     * @returns {Promise<object>} - AI's pattern analysis.
     */
    async analyzeComplexChartPatternsWithAI(/* chartDescription */) {
        logger.warn('Complex chart pattern analysis is delegated to Gemini AI. This method would send ' +
                    'chartDescription to Gemini and interpret its response.');
        // In a real scenario, this would involve a call to GeminiAPI.getAIResponse or analyzeMarketCharts.
        // For now, it's a conceptual placeholder.
        const mockAIResponse = {
            patterns: [
                { name: 'Potential Head and Shoulders', signal: 'Bearish', confidence: 0.75, description: 'Slightly complex pattern often indicating a reversal.' },
                { name: 'Double Bottom', signal: 'Bullish', confidence: 0.6, description: 'Possible double bottom pattern.' }
            ],
            overallInterpretation: 'The market shows signs of a complex bearish reversal pattern with underlying bullish consolidation.'
        };
        return Promise.resolve(mockAIResponse);
    }
}