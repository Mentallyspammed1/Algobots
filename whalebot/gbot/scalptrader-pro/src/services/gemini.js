const { GoogleGenerativeAI } = require("@google/generative-ai");
const config = require("../config");
const NEON = require('../utils/colors');

// Helper for retry
async function retry(fn, maxAttempts = 3, delay = 1000) {
    let attempts = 0;
    while (attempts < maxAttempts) {
        try {
            return await fn();
        } catch (error) {
            attempts++;
            if (attempts >= maxAttempts) {
                console.error(NEON.RED("Gemini API call failed after multiple retries:"), error);
                throw error;
            }
            console.log(NEON.YELLOW(`Gemini call failed, retrying in ${delay}ms... (Attempt ${attempts}/${maxAttempts})`));
            await new Promise(res => setTimeout(res, delay));
            delay *= 2; // Exponential backoff
        }
    }
}

class EnhancedGeminiBrain {
    constructor() {
        const key = config.GEMINI_API_KEY;
        if (!key) { console.error(NEON.RED("Missing GEMINI_API_KEY")); process.exit(1); }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: config.gemini_model });
    }

    async analyze(ctx) {
        const prompt = `
        ACT AS: Institutional Scalping Algorithm.
        OBJECTIVE: Select the single best strategy (1-5) and provide a precise trade plan, or HOLD.

        QUANTITATIVE BIAS:
        - **WSS Score (Crucial Filter):** ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
        - CRITICAL RULE: Action must align with WSS. BUY requires WSS >= ${config.indicators.wss_weights.action_threshold}. SELL requires WSS <= -${config.indicators.wss_weights.action_threshold}.

        MARKET CONTEXT:
        - Price: ${ctx.price} | Volatility: ${ctx.volatility} | Regime: ${ctx.marketRegime}
        - Trend (15m): ${ctx.trend_mtf} | Trend (3m): ${ctx.trend_angle} (Slope) | ADX: ${ctx.adx}
        - Momentum: RSI=${ctx.rsi.toFixed(2)}, Stoch=${ctx.stoch_k.toFixed(0)}, MACD=${ctx.macd_hist.toFixed(4)}
        - Structure: VWAP=${ctx.vwap.toFixed(4)}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze: ${ctx.isSqueeze}
        - Divergence: ${ctx.divergence}
        - Key Levels: Fib P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
        - Support/Resistance: ${ctx.sr_levels}

        STRATEGY ARCHETYPES:
        1. TREND_SURFER (WSS Trend > 1.0): Pullback to VWAP/EMA, anticipate continuation.
        2. VOLATILITY_BREAKOUT (Squeeze=YES): Trade in direction of MTF trend on volatility expansion.
        3. MEAN_REVERSION (WSS Momentum < -1.0 or > 1.0, Chop > 60): Fade extreme RSI/Stoch.
        4. LIQUIDITY_GRAB (Price Near FVG/Wall): Fade or trade the retest/bounce of a liquidity zone.
        5. DIVERGENCE_HUNT (Divergence != NONE): High conviction reversal trade using swing high/low for SL.

        INSTRUCTIONS:
        - If the WSS does not meet the threshold, or if no strategy is clear, return "HOLD".
        - Calculate precise entry, SL, and TP (1:1.5 RR minimum, use ATR/Pivot/FVG for targets).

        OUTPUT JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "strategy": "STRATEGY_NAME", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;

        try {
            const res = await retry(() => this.model.generateContent(prompt));
            const text = res.response.text().replace(/```json|```/g, '').trim();
            const start = text.indexOf('{');
            const end = text.lastIndexOf('}');
            if (start === -1 || end === -1) throw new Error("Invalid JSON: AI response error");
            return JSON.parse(text.substring(start, end + 1));
        } catch (e) {
            console.error(NEON.RED("Failed to get analysis from Gemini:"), e);
            // Return default values on failure
            return { action: "HOLD", confidence: 0, reason: `AI Comms Failure: ${e.message}` };
        }
    }
}

module.exports = { EnhancedGeminiBrain };
