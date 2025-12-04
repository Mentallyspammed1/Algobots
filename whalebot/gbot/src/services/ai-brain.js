import { GoogleGenerativeAI } from '@google/generative-ai';

/**
 * Interacts with the Google Generative AI to get trade signals.
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
    }

    async analyze(ctx) {
        const prompt = `
        Act as a high-frequency trading algorithm. Analyze these metrics for ${ctx.symbol}:
        - Price: ${ctx.price}
        - Fisher Transform: ${ctx.fisher.toFixed(2)} (Trend Strength)
        - RSI: ${ctx.rsi.toFixed(2)}
        - ATR: ${ctx.atr.toFixed(2)} (Volatility)
        - Orderbook Imbalance: ${(ctx.imbalance * 100).toFixed(1)}%
        - Technical Score: ${ctx.score.toFixed(2)} / 10.0
        
        Strategy:
        1. Fisher > 2.0 is Bullish, < -2.0 is Bearish.
        2. Imbalance > 0 supports Buy, < 0 supports Sell.
        3. RSI > 70 Overbought, < 30 Oversold.
        
        Respond ONLY with this JSON structure:
        {
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": 0.0 to 1.0,
            "sl": number,
            "tp": number,
            "reason": "Short string explanation",
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
            console.error(`[AIBrain] Error parsing AI response: ${e.message}`);
            return { action: "HOLD", confidence: 0, volatilityForecast: 'MEDIUM', aiEntry: 0, reason: 'AI analysis failed' };
        }
    }
}
