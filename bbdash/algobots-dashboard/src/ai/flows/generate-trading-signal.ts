
'use server';
/**
 * @fileOverview An AI agent that generates trading signals and market analysis using a direct, data-first approach.
 *
 * This version simplifies the AI interaction by gathering all necessary market data upfront
 * and passing it to the AI in a single, comprehensive prompt. This approach enhances
 * reliability and simplifies debugging compared to a multi-tool agentic system.
 *
 * - generateTradingSignal: The main function to generate a trading signal.
 * - GenerateTradingSignalInput: The Zod schema for the input.
 * - GenerateTradingSignalOutput: The Zod schema for the output.
 */

import { ai } from '@/ai/genkit';
import { z } from 'zod';
import { 
  getKline,
  getOrderBook,
  getTicker,
  getRecentTrades
} from '@/lib/bybit-api';
import { 
  IndicatorSettings,
  calculateIndicators,
  type IndicatorData
} from '@/lib/indicators';

// #region Schemas
const GenerateTradingSignalInputSchema = z.object({
  symbol: z.string().describe('The trading symbol (e.g., BTCUSDT).'),
  timeframe: z.string().describe('Primary timeframe for analysis.'),
  indicatorSettings: IndicatorSettings.optional().describe('Technical indicator settings.'),
  riskProfile: z.enum(['conservative', 'moderate', 'aggressive']).default('moderate').describe('User\'s risk tolerance level.'),
  accountBalance: z.number().optional().describe('User\'s account balance for position sizing calculations.'),
  maxRiskPercentage: z.number().min(0.1).max(10).default(2).describe('Maximum risk per trade as a percentage of account balance.'),
});
export type GenerateTradingSignalInput = z.infer<typeof GenerateTradingSignalInputSchema>;

const GenerateTradingSignalOutputSchema = z.object({
  currentPrice: z.number().describe('Current market price at the time of analysis.'),
  entryPrice: z.number().describe('Recommended entry price for the trade.'),
  takeProfit: z.array(z.number()).min(1).describe('An array of multiple take-profit levels (e.g., TP1, TP2).'),
  stopLoss: z.number().describe('The recommended stop-loss price level for risk management.'),
  signal: z.enum(['Buy', 'Sell', 'Hold']).describe('The final trading signal.'),
  
  signalStrength: z.number().min(0).max(100).describe('A data-driven signal strength score from 0 to 100.'),
  reasoning: z.string().describe('A detailed, step-by-step analysis explaining the rationale behind the signal, referencing specific data points.'),
  confidenceLevel: z.enum(['High', 'Medium', 'Low']).describe('The AI\'s confidence in the signal.'),
  
  positionSize: z.number().optional().describe('Recommended position size in the base currency (e.g., BTC amount).'),
  riskRewardRatio: z.number().optional().describe('The calculated risk/reward ratio for the first take-profit level.'),
  
  marketRegime: z.enum(['Trending Up', 'Trending Down', 'Ranging', 'Volatile']).describe('The AI\'s assessment of the current market regime.'),
  volatilityLevel: z.enum(['Low', 'Medium', 'High', 'Extreme']).describe('The AI\'s assessment of current market volatility.'),
  
  keyLevels: z.object({
    support: z.array(z.number()).describe('Key support levels identified.'),
    resistance: z.array(z.number()).describe('Key resistance levels identified.'),
  }).describe('Key price levels.'),
  
  patterns: z.array(z.object({
    name: z.string().describe('e.g., "Bullish Flag", "Head and Shoulders"'),
    reliability: z.number().min(0).max(100).describe('Estimated reliability of the pattern.'),
  })).optional().describe('Detected chart patterns.'),

  divergences: z.array(z.object({
    type: z.enum(['Bullish', 'Bearish']).describe('Type of divergence.'),
    indicator: z.string().describe('Indicator showing divergence (e.g., "RSI", "MACD").'),
  })).optional().describe('Detected indicator divergences.'),

  warnings: z.array(z.string()).optional().describe('Important risk warnings or caveats (e.g., "High volatility expected", "Low liquidity").'),
  analysisTimestamp: z.string().describe('ISO timestamp of when the analysis was performed.'),
});
export type GenerateTradingSignalOutput = z.infer<typeof GenerateTradingSignalOutputSchema>;
// #endregion

/**
 * Main exported function to be called by server actions.
 */
export async function generateTradingSignal(input: GenerateTradingSignalInput): Promise<GenerateTradingSignalOutput> {
  return generateTradingSignalFlow(input);
}

/**
 * Gathers all necessary market data in parallel.
 * @param symbol The trading symbol.
 * @param timeframe The analysis timeframe.
 * @param settings Technical indicator settings.
 * @returns An object containing all fetched market data.
 */
async function gatherMarketData(symbol: string, timeframe: string, settings?: IndicatorSettings) {
  const [tickerResult, klineResult, orderBookResult, tradesResult] = await Promise.allSettled([
    getTicker(symbol),
    getKline(symbol, timeframe, 300),
    getOrderBook(symbol),
    getRecentTrades(symbol, 50),
  ]);

  const ticker = tickerResult.status === 'fulfilled' ? tickerResult.value : null;
  const klineData = klineResult.status === 'fulfilled' ? klineResult.value : null;
  const orderBook = orderBookResult.status === 'fulfilled' ? orderBookResult.value : null;
  const recentTrades = tradesResult.status === 'fulfilled' ? tradesResult.value : null;

  let indicators: IndicatorData | null = null;
  if (klineData) {
    indicators = calculateIndicators(klineData, settings || {});
  }

  return { ticker, indicators, orderBook, recentTrades };
}

// #region AI Prompt
const tradingSignalPrompt = ai.definePrompt({
  name: 'directTradingSignalPrompt',
  input: { schema: z.any() }, // Input is a stringified context
  output: { format: 'json', schema: GenerateTradingSignalOutputSchema },
  system: `You are an elite quantitative trading analyst AI. Your mission is to generate a comprehensive, actionable trading signal by performing a multi-dimensional analysis of the provided market data context.

**Analysis Framework & Logic:**

1.  **Analyze Context:** The user will provide a JSON string containing all available market data. Your first step is to parse and understand this data. Note any fields that are 'null', as this indicates a data fetching failure which should lower your confidence.

2.  **Market Assessment (Fill these fields):**
    *   **Market Regime:** Analyze indicator trends (e.g., ADX, moving averages) to determine if the market is 'Trending Up', 'Trending Down', 'Ranging', or 'Volatile'.
    *   **Volatility Level:** Use the ATR (Average True Range) from the indicator data to classify volatility as 'Low', 'Medium', 'High', or 'Extreme'.

3.  **Signal Generation (Determine 'signal'):**
    *   **Buy Signal:** Strong bullish indicator alignment (e.g., RSI < 40, MACD crossover), price bouncing from key support, bullish patterns confirmed, positive order flow.
    *   **Sell Signal:** Strong bearish indicator alignment (e.g., RSI > 60, MACD crossunder), price rejecting key resistance, bearish patterns confirmed, negative order flow.
    *   **Hold Signal:** Conflicting indicators, price is in a tight range between strong support/resistance, market is highly volatile with no clear direction, or critical data is missing.

4.  **Trade Parameters & Risk Management:**
    *   Set the \`entryPrice\` near the \`currentPrice\`.
    *   Set the \`stopLoss\` below a key support level for a Buy, or above key resistance for a Sell. Use the ATR to give it some buffer.
    *   Define at least two \`takeProfit\` levels based on upcoming resistance (for Buys) or support (for Sells).
    *   If \`accountBalance\` is available in the input, calculate a \`positionSize\` based on the \`maxRiskPercentage\`, \`entryPrice\`, and \`stopLoss\`.
    *   Calculate the \`riskRewardRatio\` for the first TP. It **must be at least 1.5** for a Buy/Sell signal. If not, downgrade to Hold and state this in the reasoning.

5.  **Scoring & Reasoning:**
    *   **Signal Strength (0-100):** Calculate this score based on the confluence of evidence. Start at 50. Add points for: each confirming indicator (+10), pattern confirmation (+15), strong order book support/resistance (+15), trend alignment (+10). Subtract points for: conflicting indicators (-10), low liquidity (-10), extreme volatility (-10), missing data (-15 per missing source).
    *   **Confidence Level:** Set to 'High' if strength > 70, 'Medium' if 40-70, 'Low' if < 40.
    *   **Reasoning:** Write a detailed, step-by-step narrative. Start with the market assessment, discuss the key indicator and pattern findings, mention the identified support/resistance levels, and conclude with how this all justifies the final signal and trade parameters. You must mention any missing data.

6.  **Final Output:**
    *   Populate all fields in the output schema. Add any \`warnings\` for risks like low liquidity or high volatility.
    *   Set \`analysisTimestamp\` to the current UTC ISO string. Your entire output must be a single, valid JSON object.`,
});
// #endregion

// #region Genkit Flow
const generateTradingSignalFlow = ai.defineFlow(
    { name: 'generateTradingSignalFlow', inputSchema: GenerateTradingSignalInputSchema, outputSchema: GenerateTradingSignalOutputSchema }, 
    async (input) => {
        console.log(`[Flow] Starting direct signal generation for ${input.symbol} on ${input.timeframe}.`);

        const { ticker, indicators, orderBook, recentTrades } = await gatherMarketData(input.symbol, input.timeframe, input.indicatorSettings);
        
        if (!ticker) {
            throw new Error(`Critical failure: Could not fetch market ticker for ${input.symbol}. Cannot proceed.`);
        }

        // Construct a detailed context for the AI
        const context = {
            input,
            data: {
                ticker,
                indicators,
                orderBook,
                recentTrades
            }
        };

        const llmResponse = await tradingSignalPrompt(JSON.stringify(context, null, 2));
        const output = llmResponse.output;

        if (!output) {
            throw new Error("AI failed to produce a valid JSON response. The model may have returned an empty or malformed output.");
        }

        // Final validation and sanitization
        const requiredNumericFields: (keyof Pick<GenerateTradingSignalOutput, 'currentPrice' | 'entryPrice' | 'stopLoss' | 'signalStrength'>)[] = ['currentPrice', 'entryPrice', 'stopLoss', 'signalStrength'];

        for (const field of requiredNumericFields) {
            const value = output[field];
            if (value === null || typeof value !== 'number' || !isFinite(value) || value < 0) {
                throw new Error(`AI generated an invalid or non-positive numeric value for '${field}'. Received: ${value}`);
            }
        }
        if (!output.takeProfit || output.takeProfit.length === 0 || output.takeProfit.some(tp => typeof tp !== 'number' || tp <= 0)) {
            throw new Error(`AI generated invalid takeProfit levels. Received: ${JSON.stringify(output.takeProfit)}`);
        }

        console.log(`[Flow] Successfully generated signal for ${input.symbol}: ${output.signal} (Strength: ${output.signalStrength})`);
        return output;
    }
);
// #endregion
