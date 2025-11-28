// enhancedGeminiBrain.js
import { GoogleGenerativeAI } from '@google/generative-ai';
import chalk from 'chalk';
import { config } from './config.js';

export class EnhancedGeminiBrain {
  constructor() {
    const key = process.env.GEMINI_API_KEY;
    if (!key) {
      console.error(chalk.RED('Missing GEMINI_API_KEY in .env'));
      process.exit(1);
    }
    this.model = new GoogleGenerativeAI(key).getGenerativeModel({
      model: config.gemini_model
    });
  }

  async analyze(ctx) {
    const prompt = `
ACT AS: Institutional Scalping Algorithm.
OBJECTIVE: Choose the single best strategy (1-5) or HOLD.

CONSTRAINTS:
- WSS Score: ${ctx.wss} (Bias: ${ctx.wss > 0 ? 'BULLISH' : 'BEARISH'})
- BUY only if WSS >= ${config.indicators.wss_weights.action_threshold}.
- SELL only if WSS <= -${config.indicators.wss_weights.action_threshold}.
- Otherwise, action MUST be "HOLD".

MARKET CONTEXT:
- Price: ${ctx.price}
- Volatility: ${ctx.volatility.toFixed(4)}
- Regime: ${ctx.marketRegime}
- Trend (MTF 15m): ${ctx.trend_mtf}
- Trend (3m LinReg): slope=${ctx.trend_angle.slope.toFixed(4)}, r2=${ctx.trend_angle.r2.toFixed(2)}
- ADX: ${ctx.adx.toFixed(2)}
- Momentum: RSI=${ctx.rsi.toFixed(2)}, StochK=${ctx.stoch_k.toFixed(0)}, MACD_Hist=${ctx.macd_hist.toFixed(4)}
- Structure: VWAP=${ctx.vwap.toFixed(4)}, FVG=${ctx.fvg ? ctx.fvg.type + '@' + ctx.fvg.price.toFixed(2) : 'None'}, Squeeze=${ctx.isSqueeze}
- Divergence: ${ctx.divergence}
- Walls: BUY=${ctx.walls.buy || 'None'}, SELL=${ctx.walls.sell || 'None'}
- Fib Levels: P=${ctx.fibs.P.toFixed(2)}, S1=${ctx.fibs.S1.toFixed(2)}, R1=${ctx.fibs.R1.toFixed(2)}
- Orderbook S/R: ${ctx.sr_levels}

STRATEGIES:
1. TREND_SURFER
2. VOLATILITY_BREAKOUT
3. MEAN_REVERSION
4. LIQUIDITY_GRAB
5. DIVERGENCE_HUNT

REQUIREMENTS:
- Use ATR/FVG/Pivots to set SL/TP.
- Minimum RR: 1:1.5.
- If conditions unclear or conflict, return HOLD.

OUTPUT STRICT JSON ONLY:
{
  "action": "BUY" | "SELL" | "HOLD",
  "strategy": "TREND_SURFER" | "VOLATILITY_BREAKOUT" | "MEAN_REVERSION" | "LIQUIDITY_GRAB" | "DIVERGENCE_HUNT" | "NONE",
  "confidence": number (0 to 1),
  "entry": number,
  "sl": number,
  "tp": number,
  "reason": "short explanation"
}
`;

    try {
      const res = await this.model.generateContent(prompt);
      let text = res.response.text().trim();
      text = text.replace(/```json|```/g, '').trim();

      const start = text.indexOf('{');
      const end = text.lastIndexOf('}');
      if (start === -1 || end === -1) throw new Error('No JSON object found');
      const jsonText = text.substring(start, end + 1);
      const parsed = JSON.parse(jsonText);

      const threshold = config.indicators.wss_weights.action_threshold;
      if (parsed.action === 'BUY' && ctx.wss < threshold) {
        parsed.action = 'HOLD';
        parsed.reason = (parsed.reason || '') + ' | Overruled by WSS BUY threshold';
      }
      if (parsed.action === 'SELL' && ctx.wss > -threshold) {
        parsed.action = 'HOLD';
        parsed.reason = (parsed.reason || '') + ' | Overruled by WSS SELL threshold';
      }

      return parsed;
    } catch (e) {
      console.error(chalk.ORANGE(`AI Parse/Call Error: ${e.message}`));
      return {
        action: 'HOLD',
        strategy: 'NONE',
        confidence: 0,
        entry: ctx.price,
        sl: ctx.price,
        tp: ctx.price,
        reason: `AI failure: ${e.message}`
      };
    }
  }
}
