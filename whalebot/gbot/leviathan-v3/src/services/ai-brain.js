import { GoogleGenerativeAI } from '@google/generative-ai';
import { COLOR } from '../ui.js';

/**
 * Interacts with the Google Generative AI to get trade signals and analysis.
 */
export class AIBrain {
    constructor(config) {
        this.config = config.ai;
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
        this.analysisModel = new GoogleGenerativeAI(process.env.GEMINI_API_KEY).getGenerativeModel({
            model: this.config.analysis_model,
            generationConfig: {
                responseMimeType: "application/json",
                maxOutputTokens: this.config.analysisMaxTokens
            }
        });
    }

    async getTradingDecision(ctx) {
        const prompt = `
        Act as a high-frequency trading algorithm. Analyze these metrics for ${ctx.symbol}:
        - Current Price: ${ctx.price}
        - Technical Score: ${ctx.score.toFixed(2)} / 100.0
        - RSI: ${ctx.indicators.rsi.toFixed(2)}
        - Fisher Transform: ${ctx.indicators.fisher.toFixed(2)}
        - ATR: ${ctx.indicators.atr.toFixed(2)} (Volatility)
        - Bollinger Bands: Mid=${ctx.indicators.bollingerBands.mid.toFixed(2)}, Upper=${ctx.indicators.bollingerBands.upper.toFixed(2)}, Lower=${ctx.indicators.bollingerBands.lower.toFixed(2)}
        - MACD Histogram: ${ctx.indicators.macd.histogram.toFixed(2)}
        - StochRSI K: ${ctx.indicators.stochRSI.k.toFixed(2)}
        - ADX: ${ctx.indicators.adx.adx.toFixed(2)}
        - SuperTrend Direction: ${ctx.indicators.supertrend.direction}
        - VWAP: ${ctx.indicators.vwap.toFixed(2)}
        - Hull MA: ${ctx.indicators.hma.toFixed(2)}
        - Choppiness: ${ctx.indicators.choppiness.toFixed(2)}
        - Ichimoku Span A: ${ctx.indicators.ichimoku.spanA.toFixed(2)}
        - Ichimoku Span B: ${ctx.indicators.ichimoku.spanB.toFixed(2)}

        Based on all these indicators and current market conditions, provide a trading decision.
        
        Strategy Guidelines:
        - The Technical Score is a weighted summary of all indicators (0-100 for buy, 0 to -100 for sell).
        - Use Fisher Transform and SuperTrend for primary trend direction.
        - Use RSI, StochRSI, and Williams %R for overbought/oversold conditions.
        - Use ADX and Choppiness to determine trend strength vs. ranging market.
        - Use Bollinger Bands and VWAP for dynamic support/resistance.

        Respond ONLY with this JSON structure:
        {
            "decision": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "reason": "Short string explanation based on key indicators.",
            "volatilityForecast": "LOW" | "MEDIUM" | "HIGH",
            "aiEntry": "A suggested entry price based on your analysis, or 0 if HOLD."
        }`;

        try {
            const result = await this.model.generateContent(prompt);
            let rawText = result.response.text();
            rawText = rawText.replace(/```json|```/g, '').trim();
            
            const signal = JSON.parse(rawText);

            return {
                decision: signal.decision || 'HOLD',
                confidence: signal.confidence || 0,
                reason: signal.reason || 'AI parse error',
                volatilityForecast: signal.volatilityForecast || 'MEDIUM',
                aiEntry: signal.aiEntry || 0
            };
        } catch (e) {
            console.error(COLOR.RED(`[AIBrain] Error parsing AI response: ${e.message}`));
            console.error(COLOR.RED(`[AIBrain] AI response that failed to parse: ${rawText}`));
            return { decision: "HOLD", confidence: 0, reason: 'AI analysis failed', volatilityForecast: 'MEDIUM', aiEntry: 0 };
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
            console.error(COLOR.RED(`[AIBrain] AI response that failed to parse: ${rawText}`));
            return `Error in AI post-trade analysis: ${e.message}`;
        }
    }
}
