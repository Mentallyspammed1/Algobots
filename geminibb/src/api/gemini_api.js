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
        // IMPROVEMENT 10: Simple Rate Limiting for Gemini
        this.lastRequestTime = 0;
        this.requestIntervalMs = config.gemini.requestIntervalMs; // Configurable interval
    }

    async getTradeDecision(marketContext, isInPosition, positionSide) { // IMPROVEMENT 14: Pass current position state
        try {
            const model = this.genAI.getGenerativeModel({
                model: config.geminiModel,
                // IMPROVEMENT 13: Configurable AI generation parameters
                generationConfig: { 
                    responseMimeType: "application/json",
                    temperature: config.gemini.temperature,
                    topP: config.gemini.topP,
                    maxOutputTokens: config.gemini.maxOutputTokens, // IMPROVEMENT 9: Max output tokens
                }
            });

            // IMPROVEMENT 14: Dynamic prompt based on position status
            let actionInstructions = '';
            if (isInPosition) {
                actionInstructions = `You are currently in a ${positionSide} position. Your primary goal is now to manage this open position.
                Based *only* on the provided data, decide on one of the following two actions:
                1.  **${ACTIONS.PROPOSE_EXIT}**: If the current open position shows signs of reversal, has met its logical target, or the market context has changed unfavorably.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal to exit, the position is still valid, or waiting for further confirmation.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"reasoning": "Detailed analysis..."}}}
                
                Example for exiting: {"functionCall": {"name": "${ACTIONS.PROPOSE_EXIT}", "args": {"reasoning": "Bearish divergence on the RSI and the price is approaching a major resistance level identified on the 60m chart."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is still trending favorably, and the position is performing as expected. No immediate exit signal."}}}
                `;
            } else {
                actionInstructions = `Your primary goal is to identify high-probability trading opportunities
                for the ${config.symbol} perpetual contract, focusing on maximizing profit while adhering to strict risk management rules.
                
                Based *only* on the provided data, decide on one of the following three actions:
                1.  **${ACTIONS.PROPOSE_TRADE}**: If a clear, high-probability entry signal is present on the primary timeframe that aligns with the broader trend.
                2.  **${ACTIONS.HOLD}**: If there is no clear signal, the market is choppy, or the risk/reward is unfavorable.

                Your response MUST be a valid JSON object matching this structure:
                {"functionCall": {"name": "action_name", "args": {"side": "Buy" or "Sell" (only for proposeTrade), "reasoning": "Detailed analysis..."}}}
                
                Example for entering: {"functionCall": {"name": "${ACTIONS.PROPOSE_TRADE}", "args": {"side": "${SIDES.BUY}", "reasoning": "Price broke above the 50 SMA on the 15m chart, which is in line with the bullish trend on the 4h chart. RSI is showing upward momentum."}}}
                Example for holding: {"functionCall": {"name": "${ACTIONS.HOLD}", "args": {"reasoning": "The market is consolidating within a tight range with conflicting signals from indicators. Waiting for a breakout."}}}
                `;
            }

            const prompt = `
                You are a sophisticated crypto trading analyst AI.
                Analyze the following multi-timeframe market data and the current bot status. The primary trading timeframe is ${config.primaryInterval} minutes.
                Higher timeframe data (${config.multiTimeframeIntervals.join(', ')}) min) is provided for trend context.

                ${marketContext}

                ${actionInstructions}
            `;

            // IMPROVEMENT 10: Simple Rate Limiting for Gemini
            const now = Date.now();
            if (now - this.lastRequestTime < this.requestIntervalMs) {
                const delay = this.requestIntervalMs - (now - this.lastRequestTime);
                logger.debug(`Delaying Gemini API call by ${delay}ms to respect rate limit.`);
                await sleep(delay); // Ensure `sleep` is imported/available (e.g., from bybit_api.js)
            }
            this.lastRequestTime = Date.now(); // Update after potential sleep

            const result = await this.model.generateContent(prompt);
            const responseText = result.response.text();
            
            // IMPROVEMENT 19: Add robust JSON parsing with error handling
            let rawDecision;
            try {
                rawDecision = JSON.parse(responseText);
            } catch (jsonError) {
                logger.error(`AI response not valid JSON: ${responseText}`, jsonError);
                throw new Error("AI returned invalid JSON.");
            }
            
            const validationResult = TradeDecisionSchema.safeParse(rawDecision);
            if (!validationResult.success) {
                logger.error(`Invalid AI response format: ${validationResult.error.message}\nRaw AI response: ${responseText}`);
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