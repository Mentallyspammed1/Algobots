import { GoogleGenerativeAI } from '@google/generative-ai';
import { COLOR } from '../ui.js'; // Import COLOR for console output

/**
 * Interacts with the Google Generative AI to get trade signals and analysis.
 */
export class AIBrain {
    constructor(config) {
        this.config = config.ai;
        console.log(COLOR.YELLOW(`[AIBrain] Checking GEMINI_API_KEY: ${process.env.GEMINI_API_KEY ? 'Set' : 'Not Set'}`)); // <-- New debug log
        if (!process.env.GEMINI_API_KEY) {
            throw new Error("GEMINI_API_KEY is not set in the environment variables.");
        }
        this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({ 
            model: this.config.model,
            generationConfig: { 
                responseMimeType: "application/json", 
                maxOutputTokens: this.config.maxTokens 
            }
        });

        // New model for deeper analysis
        this.analysisModel = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
            model: this.config.analysis_model,
            generationConfig: {
                responseMimeType: "application/json",
                maxOutputTokens: this.config.analysisMaxTokens
            }
        });
    }

    async analyze(ctx) {
        // Constructing a much richer prompt with all indicators
        const prompt = `
        Act as a high-frequency trading algorithm. Analyze these metrics for ${ctx.symbol}:
        - Current Price: ${ctx.price}
        - Technical Score: ${ctx.score.toFixed(2)} / 10.0
        - Orderbook Imbalance: ${(ctx.imbalance * 100).toFixed(1)}%
        - RSI: ${ctx.rsi.toFixed(2)} (Period: ${this.config.indicators.rsi})
        - Fisher Transform: ${ctx.fisher.toFixed(2)} (Period: ${this.config.indicators.fisher})
        - ATR: ${ctx.atr.toFixed(2)} (Volatility, Period: ${this.config.indicators.atr})
        - Bollinger Bands: Mid=${ctx.bbMid.toFixed(2)}, Upper=${ctx.bbUpper.toFixed(2)}, Lower=${ctx.bbLower.toFixed(2)} (Period: ${this.config.indicators.bb.period}, StdDev: ${this.config.indicators.bb.std})
        - MACD: MACD=${ctx.macd.macdLine.toFixed(2)}, Signal=${ctx.macd.signalLine.toFixed(2)}, Histogram=${ctx.macd.histogram.toFixed(2)} (Fast: ${this.config.indicators.macd.fast}, Slow: ${this.config.indicators.macd.slow}, Signal: ${this.config.indicators.macd.signal})
        - StochRSI: %K=${ctx.stochRsi.k.toFixed(2)}, %D=${ctx.stochRsi.d.toFixed(2)} (RSI Period: ${this.config.indicators.stochRSI.rsi}, Stoch Period: ${this.config.indicators.stochRSI.stoch}, K: ${this.config.indicators.stochRSI.k}, D: ${this.config.indicators.stochRSI.d})
        - ADX: ADX=${ctx.adx.adxLine.toFixed(2)}, +DI=${ctx.adx.pdiLine.toFixed(2)}, -DI=${ctx.adx.ndiLine.toFixed(2)} (Period: ${this.config.indicators.adx})
        - T3 Moving Average: ${ctx.t3.toFixed(2)} (Period: ${this.config.indicators.advanced.t3.period}, VFactor: ${this.config.indicators.advanced.t3.vFactor})
        - SuperTrend: Current Trend=${ctx.superTrend.trend.toFixed(2)}, Direction=${ctx.superTrend.direction} (Period: ${this.config.indicators.advanced.superTrend.period}, Multiplier: ${this.config.indicators.advanced.superTrend.multiplier})
        - VWAP: ${ctx.vwap.toFixed(2)}
        - Hull Moving Average (HMA): ${ctx.hma.toFixed(2)} (Period: ${this.config.indicators.advanced.hma.period})
        - Choppiness Index: ${ctx.choppiness.toFixed(2)} (Period: ${this.config.indicators.advanced.choppiness.period}, Threshold: ${this.config.indicators.advanced.choppiness.threshold})
        - Connors RSI: ${ctx.connorsRsi.toFixed(2)} (RSI: ${this.config.indicators.advanced.connorsRSI.rsiPeriod}, Streak RSI: ${this.config.indicators.advanced.connorsRSI.streakRsiPeriod}, Rank: ${this.config.indicators.advanced.connorsRSI.rankPeriod})
        - Ichimoku Cloud: Tenkan=${ctx.ichimoku.conv.toFixed(2)}, Kijun=${ctx.ichimoku.base.toFixed(2)}, SenkouA=${ctx.ichimoku.spanA.toFixed(2)}, SenkouB=${ctx.ichimoku.spanB.toFixed(2)} (Span1: ${this.config.indicators.advanced.ichimoku.span1}, Span2: ${this.config.indicators.advanced.ichimoku.span2}, Span3: ${this.config.indicators.advanced.ichimoku.span3})
        - Schaff Trend Cycle (STC): ${ctx.schaffTC.toFixed(2)} (Fast: ${this.config.indicators.advanced.schaffTC.fast}, Slow: ${this.config.indicators.advanced.schaffTC.slow}, Cycle: ${this.config.indicators.advanced.schaffTC.cycle})

        Based on all these indicators and current market conditions, provide a trading decision.
        
        Strategy Guidelines:
        1. Fisher Transform indicates market trend and reversal points.
        2. RSI measures the speed and change of price movements.
        3. ATR shows market volatility.
        4. Bollinger Bands indicate price extremes and potential reversals.
        5. MACD reveals changes in the strength, direction, momentum, and duration of a trend.
        6. StochRSI indicates overbought/oversold conditions based on RSI.
        7. ADX measures trend strength.
        8. T3 and HMA are advanced moving averages for smoother trend identification.
        9. SuperTrend gives clear trend direction.
        10. VWAP shows the average price traded against volume.
        11. Choppiness Index identifies if the market is trending or ranging.
        12. Connors RSI combines momentum and overbought/oversold levels.
        13. Ichimoku Cloud provides comprehensive support/resistance, trend, and momentum information.
        14. Schaff Trend Cycle (STC) is a leading indicator for identifying market cycles and reversals.

        Respond ONLY with this JSON structure:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "sl": number,
            "tp": number,
            "reason": "Short string explanation based on key indicators",
            "volatilityForecast": "HIGH" | "MEDIUM" | "LOW",
            "optimalEntry": number
        }`;

        try {
            const result = await this.model.generateContent(prompt);
            let rawText = result.response.text();
            rawText = rawText.replace(/```json|```/g, '').trim();
            
            const signal = JSON.parse(rawText);

            // Add default fields for safety
            return {
                aiEntry: signal.optimalEntry || 0,
                volatilityForecast: ['HIGH', 'MEDIUM', 'LOW'].includes(signal.volatilityForecast) ? signal.volatilityForecast : 'MEDIUM',
                action: signal.action || 'HOLD',
                confidence: signal.confidence || 0,
                sl: signal.sl || 0,
                tp: signal.tp || 0,
                reason: signal.reason || 'AI parse error'
            };
        } catch (e) {
            console.error(COLOR.RED(`[AIBrain] Error parsing AI (real-time) response: ${e.message}`));
            console.error(COLOR.RED(`[AIBrain] AI response that failed to parse: ${rawText}`)); // Log the problematic response
            return { action: "HOLD", confidence: 0, volatilityForecast: 'MEDIUM', aiEntry: 0, reason: 'AI analysis failed' };
        }
    }

    async analyzeTrade(tradeDetails) {
        const prompt = `
        A trade was just closed with the following details:
        - Symbol: ${tradeDetails.symbol}
        - Side: ${tradeDetails.side}
        - Entry Price: ${tradeDetails.entry}
        - Exit Price: ${tradeDetails.exit}
        - PnL (Profit/Loss): ${tradeDetails.pnl.toFixed(2)}
        - Exit Reason: ${tradeDetails.exitReason}
        - Entry AI Decision: ${JSON.stringify(tradeDetails.aiDecision)}
        - Entry Market Context: ${JSON.stringify(tradeDetails.entryContext)}

        Analyze this trade. Provide a concise "Lesson Learned" or "Observation" based on the entry conditions, AI's decision, and the trade outcome. Focus on actionable insights or confirmations of good strategy.

        Respond ONLY with a JSON structure:
        {
            "analysis": "A concise lesson learned or observation from this trade."
        }`;

        try {
            const result = await this.analysisModel.generateContent(prompt);
            let rawText = result.response.text();
            rawText = rawText.replace(/```json|```/g, '').trim();
            
            const analysis = JSON.parse(rawText);
            return analysis.analysis || 'No specific analysis provided by AI.';

        } catch (e) {
            console.error(COLOR.RED(`[AIBrain] Error parsing AI (post-trade) response: ${e.message}`));
            console.error(COLOR.RED(`[AIBrain] AI response that failed to parse: ${rawText}`)); // Log the problematic response
            return `Error in AI post-trade analysis: ${e.message}`;
        }
    }
}