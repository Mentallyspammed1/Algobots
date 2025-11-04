import { GoogleGenAI, Type } from "@google/genai";
import { Analysis, Kline, IndicatorData, HigherTimeframeTrends, OrderbookAnalysis } from '../types';

// Fix: Adhere to Gemini API coding guidelines for API key initialization.
// The API key must be read from process.env.API_KEY and passed directly to the constructor.
// This assumes the environment variable is pre-configured and accessible.
const ai = new GoogleGenAI({ apiKey: process.env.API_KEY! });

// FIX: Complete the analysis schema and add required fields.
const analysisSchema = {
  type: Type.OBJECT,
  properties: {
    trend: { 
      type: Type.STRING,
      enum: ['Uptrend', 'Downtrend', 'Sideways'],
      description: 'The overall short-term market trend.'
    },
    signal: { 
      type: Type.STRING,
      enum: ['BUY', 'SELL', 'HOLD'],
      description: 'A clear trading signal based on the scalping analysis.'
    },
    confidence: { 
      type: Type.INTEGER,
      description: 'Confidence score for the signal from 0 (very low) to 100 (very high).'
    },
    scalpingThesis: { 
      type: Type.STRING,
      description: 'A concise, one-sentence thesis for the scalping opportunity.'
    },
    scalpingStrategy: {
      type: Type.STRING,
      description: 'The specific scalping strategy identified, e.g., "Momentum Scalp", "Mean Reversion", "Breakout Scalp", "Ichimoku Cloud Bounce".'
    },
    tradeUrgency: {
        type: Type.STRING,
        enum: ['Immediate', 'Monitor', 'Low'],
        description: 'The urgency of the trade signal. "Immediate" for time-sensitive opportunities.'
    },
    reasoning: { 
      type: Type.STRING,
      description: 'Detailed reasoning for the analysis, mentioning key patterns or indicators observed in the data.'
    },
    key_factors: {
      type: Type.ARRAY,
      items: {
        type: Type.STRING,
      },
      description: 'A list of key technical factors that support the scalping signal (e.g., "Price rejected from VWAP", "Approaching major buy wall").'
    },
    supportLevel: {
      type: Type.NUMBER,
      description: 'The estimated key short-term support price level.'
    },
    resistanceLevel: {
      type: Type.NUMBER,
      description: 'The estimated key short-term resistance price level.'
    },
    entryPrice: {
      type: Type.NUMBER,
      description: 'The suggested entry price for the trade, close to the current price.'
    },
    takeProfitLevels: {
      type: Type.ARRAY,
      items: { type: Type.NUMBER },
      description: 'An array of two tight take-profit levels suitable for scalping. TP1 should be conservative, TP2 more optimistic.'
    },
    stopLossLevel: {
      type: Type.NUMBER,
      description: 'A tight stop-loss level suitable for scalping, based on immediate support/resistance.'
    },
    timeframe_alignment: {
        type: Type.ARRAY,
        description: 'An array of objects showing the confirmed trend direction on higher timeframes, e.g., [{"interval": "60", "trend": "Uptrend"}]',
        items: {
            type: Type.OBJECT,
            properties: {
                interval: { 
                    type: Type.STRING, 
                    description: "The timeframe interval (e.g., '60', '240', 'D')." 
                },
                trend: { 
                    type: Type.STRING, 
                    enum: ['Uptrend', 'Downtrend', 'Sideways'], 
                    description: "The trend on that interval." 
                }
            },
            required: ['interval', 'trend']
        }
    }
  },
  required: ['trend', 'signal', 'confidence', 'scalpingThesis', 'scalpingStrategy', 'tradeUrgency', 'reasoning', 'key_factors', 'supportLevel', 'resistanceLevel', 'entryPrice', 'takeProfitLevels', 'stopLossLevel']
};

const formatIndicatorDataForPrompt = (indicators: IndicatorData): string => {
  let prompt = 'Key calculated indicator values are:\n';
  if (indicators.momentum) {
    prompt += `\n**Momentum:**\n`;
    prompt += `- RSI(14): ${indicators.momentum.rsi?.toFixed(2)}\n`;
    prompt += `- Stochastic(14,3,3): K=${indicators.momentum.stochastic_k?.toFixed(2)}, D=${indicators.momentum.stochastic_d?.toFixed(2)}\n`;
    prompt += `- Williams %R(14): ${indicators.momentum.williamsr?.toFixed(2)}\n`;
    prompt += `- MACD(12,26,9): MACD=${indicators.momentum.macd?.toFixed(4)}, Signal=${indicators.momentum.macd_signal?.toFixed(4)}, Hist=${indicators.momentum.macd_histogram?.toFixed(4)}\n`;
  }
  if (indicators.trend) {
    prompt += `\n**Trend & Volatility:**\n`;
    prompt += `- ADX(14): ${indicators.trend.adx?.toFixed(2)} (+DI: ${indicators.trend.plus_di?.toFixed(2)}, -DI: ${indicators.trend.minus_di?.toFixed(2)})\n`;
    prompt += `- Ichimoku Cloud(9,26,52,26): Conversion=${indicators.trend.ichimoku_conversion?.toFixed(2)}, Base=${indicators.trend.ichimoku_base?.toFixed(2)}, Span A=${indicators.trend.ichimoku_span_a?.toFixed(2)}, Span B=${indicators.trend.ichimoku_span_b?.toFixed(2)}\n`;
  }
  if (indicators.volatility) {
    prompt += `- Bollinger Bands(20,2): Upper=${indicators.volatility.bb_upper?.toFixed(2)}, Middle=${indicators.volatility.bb_middle?.toFixed(2)}, Lower=${indicators.volatility.bb_lower?.toFixed(2)}\n`;
  }
  if (indicators.volume) {
    prompt += `\n**Volume:**\n`;
    prompt += `- 20-Period VWAP: ${indicators.volume.vwap?.toFixed(2)}\n`;
  }
  if (indicators.ehlers) {
    prompt += `\n**Advanced Oscillators:**\n`;
    prompt += `- Fisher Transform(9): Fisher=${indicators.ehlers.fisher_transform?.toFixed(2)}, Trigger=${indicators.ehlers.fisher_trigger?.toFixed(2)}\n`;
    prompt += `- Stochastic RSI(14,14,3,3): K=${indicators.ehlers.stoch_rsi_k?.toFixed(2)}, D=${indicators.ehlers.stoch_rsi_d?.toFixed(2)}\n`;
  }
  return prompt;
};

const formatHigherTimeframeTrendsForPrompt = (trends: HigherTimeframeTrends): string => {
    let prompt = 'Higher timeframe context is as follows:\n';
    for (const [interval, trend] of Object.entries(trends)) {
        prompt += `- The trend on the ${interval} interval is currently an **${trend}**.\n`;
    }
    return prompt;
};

const formatLiquidityForPrompt = (analysis: OrderbookAnalysis): string => {
    let prompt = 'Significant Order Book Liquidity Walls:\n';
    if (analysis.supportLevels.length > 0) {
        analysis.supportLevels.forEach(level => {
            prompt += `- Strong Support (Buy Wall) identified at: $${level.price.toFixed(2)} (Volume: ${level.volume.toLocaleString()})\n`;
        });
    } else {
        prompt += '- No significant support walls detected.\n';
    }
    if (analysis.resistanceLevels.length > 0) {
        analysis.resistanceLevels.forEach(level => {
            prompt += `- Strong Resistance (Sell Wall) identified at: $${level.price.toFixed(2)} (Volume: ${level.volume.toLocaleString()})\n`;
        });
    } else {
        prompt += '- No significant resistance walls detected.\n';
    }
    return prompt;
};


export const performTrendAnalysis = async (symbol: string, interval: string, klines: Kline[], indicators: IndicatorData, higherTimeframeTrends: HigherTimeframeTrends, orderbookAnalysis: OrderbookAnalysis): Promise<Analysis> => {
  const prompt = `
    Act as an expert cryptocurrency scalper with a focus on high-probability, short-term trades.
    Your task is to analyze the market data for ${symbol} on the ${interval} timeframe and provide a complete SCALPING signal in the required JSON format.

    ${formatHigherTimeframeTrendsForPrompt(higherTimeframeTrends)}

    ${formatLiquidityForPrompt(orderbookAnalysis)}

    Here is a summary of the latest pre-calculated technical indicators for the primary ${interval} timeframe:
    ${formatIndicatorDataForPrompt(indicators)}

    Your scalping analysis MUST strictly adhere to these interpretation rules:
    1.  **Primary Goal**: Identify quick entry/exit opportunities. Trade duration is expected to be very short. Risk management is paramount.
    2.  **Key Indicators**: Your primary focus should be on the **20-period VWAP**, Bollinger Bands, **Ichimoku Cloud (Kumo)**, and the identified Order Book **Liquidity Walls**. These provide the most immediate levels for scalping.
    3.  **VWAP Rule**: For a BUY signal, the price should ideally be bouncing off or reclaiming the **20-period VWAP** from below. For a SELL signal, it should be rejecting from the **20-period VWAP** from above.
    4.  **Ichimoku Cloud Rule**: The Cloud (Kumo) is a primary dynamic support/resistance zone. A strong BUY signal occurs when price is *above* the cloud and retests the top of it (Senkou Span A). A strong SELL occurs when price is *below* the cloud and rejects from the bottom (Senkou Span B).
    5.  **Mean Reversion Rule**: Use Bollinger Bands and Oscillators (RSI, Stochastic, Williams %R) for mean reversion. A price touching the lower band while oscillators are oversold (<20-30) is a BUY scalp opportunity. A price touching the upper band while oscillators are overbought (>70-80) is a SELL scalp opportunity.
    6.  **Liquidity Rule**: The 'Liquidity Walls' from the order book are your most important levels for setting Take Profit and Stop Loss. A BUY signal should have a Stop Loss just below a major buy wall, and a Take Profit just before a major sell wall.
    7.  **Signal Confirmation**: A high-confidence signal occurs when at least THREE of the above rules align (e.g., price bounces off VWAP which is also the top of the Ichimoku Cloud, with Stochastics moving out of oversold). Confidence is even higher if it aligns with the higher timeframe trend.
    8.  **Urgency**: If a clear setup is present right now (e.g., price is currently touching a key level), urgency is 'Immediate'. If the price is approaching a key level, urgency is 'Monitor'. Otherwise, it is 'Low'.

    Output Requirements:
    -   **scalpingStrategy**: Name the pattern you see (e.g., "VWAP Bounce", "Ichimoku Cloud Support", "BB Mean Reversion", "Liquidity Wall Fade").
    -   **takeProfitLevels**: Provide an array of **TWO** take-profit levels. TP1 should be a conservative, quick scalp target (e.g., the BB middle line or a minor resistance). TP2 should be at the next significant resistance/support level.
    -   **confidence**: Base this on how many rules are in alignment.
    -   **key_factors**: List the specific scalping rules that were met (e.g., "Price testing VWAP from above", "Stochastic oversold (<20)", "Bouncing from Senkou Span A").
    -   **Trade Parameters**: Must be VERY TIGHT. The Stop Loss should be close to the entry, suitable for a quick scalp.

    Latest Candlestick Data (last 50 periods for context):
    ${JSON.stringify(klines.slice(-50))}
  `;

  try {
    const response = await ai.models.generateContent({
      model: "gemini-flash-lite-latest",
      contents: prompt,
      config: {
        responseMimeType: "application/json",
        responseSchema: analysisSchema,
        temperature: 0.2, // Lower temperature for more deterministic, rule-based output
      },
    });

    const jsonText = response.text.trim();
    const parsedJson = JSON.parse(jsonText);
    
    // Ensure numeric fields are correctly typed
    parsedJson.confidence = Number(parsedJson.confidence);
    parsedJson.supportLevel = Number(parsedJson.supportLevel);
    parsedJson.resistanceLevel = Number(parsedJson.resistanceLevel);
    parsedJson.entryPrice = Number(parsedJson.entryPrice);
    parsedJson.takeProfitLevels = Array.isArray(parsedJson.takeProfitLevels) ? parsedJson.takeProfitLevels.map(Number) : [];
    parsedJson.stopLossLevel = Number(parsedJson.stopLossLevel);

    return parsedJson as Analysis;

  } catch (error) {
    console.error("Error performing trend analysis with Gemini:", error);
    throw new Error("Failed to get analysis from AI. The model may have returned an invalid response.");
  }
};