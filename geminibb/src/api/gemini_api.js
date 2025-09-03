// src/api/gemini_api.js
import { GoogleGenerativeAI } from '@google/generative-ai';
import { z } from 'zod';
import { config } from '../config.js';
import logger from '../utils/logger.js';
import { ACTIONS, SIDES } from '../core/constants.js';

// NEW: Zod schema for validating the AI's response
const TradeDecisionSchema = z.object({
  functionCall: z.object({
    name: z.nativeEnum(ACTIONS),
    args: z.object({
      side: z.nativeEnum(SIDES).optional(),
      reasoning: z.string().min(10),
    }),
  }),
});

export default class GeminiAPI {
    constructor(apiKey) {
        this.genAI = new GoogleGenerativeAI(apiKey);
    }

    async getTradeDecision(marketContext) {
        try {
            const model = this.genAI.getGenerativeModel({
                model: config.geminiModel,
                generationConfig: { responseMimeType: "application/json" }
            });

            // NEW: Enhanced prompt with multi-timeframe context and clearer instructions
            const prompt = `
                You are a sophisticated crypto trading analyst AI. Your primary goal is to identify high-probability trading opportunities
                for the ${config.symbol} perpetual contract, focusing on maximizing profit while adhering to strict risk management rules.
                
                Analyze the following multi-timeframe market data and the current bot status. The primary trading timeframe is ${config.primaryInterval} minutes.
                Higher timeframe data (${config.multiTimeframeIntervals.join(', ')}) min) is provided for trend context.

                ${marketContext}

                Based *only* on the provided data, decide on one of the following three actions:
                1.  **${ACTIONS.PROPOSE_TRADE}**: If a clear, high-probability entry signal is present on the primary timeframe that aligns with the broader trend.
                2.  **${ACTIONS.PROPOSE_EXIT}**: If the current open position shows signs of reversal, has met its logical target, or the market context has changed unfavorably.
                3.  **${ACTIONS.HOLD}**: If there is no clear signal, the market is choppy, or the risk/reward is unfavorable.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"side": "Buy" or "Sell" (only for proposeTrade), "reasoning": "Detailed analysis..."}}}
                
                Example for entering: {"functionCall": {"name": "${ACTIONS.PROPOSE_TRADE}", "args": {"side": "${SIDES.BUY}", "reasoning": "Price broke above the 50 SMA on the 15m chart, which is in line with the bullish trend on the 4h chart. RSI is showing upward momentum."}}}
                Example for exiting: {"functionCall": {"name": "${ACTIONS.PROPOSE_EXIT}", "args": {"reasoning": "Bearish divergence on the RSI and the price is approaching a major resistance level identified on the 60m chart."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is consolidating within a tight range with conflicting signals from indicators. Waiting for a breakout."}}}
            `;

            const result = await model.generateContent(prompt);
            const responseText = result.response.text();
            const rawDecision = JSON.parse(responseText);
            
            // NEW: Validate the response against the Zod schema
            const validationResult = TradeDecisionSchema.safeParse(rawDecision);
            if (!validationResult.success) {
                throw new Error(`Invalid AI response format: ${validationResult.error.message}`);
            }
            
            const decision = validationResult.data.functionCall;
            logger.info(`AI Decision: ${decision.name} - ${decision.args.reasoning}`);
            return decision;

        } catch (error) {
            logger.error("Failed to get or validate trade decision from Gemini AI.", error);
            return { name: ACTIONS.HOLD, args: { reasoning: 'AI API call or validation failed.' } };
        }
    }
}