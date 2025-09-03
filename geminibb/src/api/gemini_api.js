import { GoogleGenerativeAI } from '@google/generative-ai';
import { config } from '../config.js';
import logger from '../utils/logger.js';

class GeminiAPI {
    constructor(apiKey) {
        this.genAI = new GoogleGenerativeAI(apiKey);
    }

    async getTradeDecision(marketContext) {
        const tools = [{
            functionDeclarations: [
                {
                    name: "proposeTrade",
                    description: "Proposes a trade entry (Buy or Sell) based on market analysis. Only use when confidence is high.",
                    parameters: {
                        type: "OBJECT",
                        properties: {
                            side: { type: "STRING", enum: ["Buy", "Sell"] },
                            reasoning: { type: "STRING", description: "Detailed reasoning for the trade proposal." },
                            confidence: { type: "NUMBER", description: "Confidence score from 0.0 to 1.0." }
                        },
                        required: ["side", "reasoning", "confidence"]
                    }
                },
                {
                    name: "proposeExit",
                    description: "Proposes to close the current open position. Use if analysis suggests the trend is reversing or profit target is met.",
                    parameters: {
                        type: "OBJECT",
                        properties: {
                            reasoning: { type: "STRING", description: "Detailed reasoning for closing the position." }
                        },
                        required: ["reasoning"]
                    }
                }
            ]
        }];

        const model = this.genAI.getGenerativeModel({ model: config.ai.model, tools });

        const prompt = `You are an expert trading analyst. Analyze the provided market data.
        - If you are NOT in a position and see a high-probability opportunity, call 'proposeTrade'.
        - If you ARE in a position, analyze the P/L and current data to decide if you should call 'proposeExit' or continue holding.
        - If no action is warranted, simply respond with your analysis on why you are holding.

        Market Data:
        ---
        ${marketContext}
        ---`;

        try {
            const result = await model.generateContent(prompt);
            const functionCalls = result.response.functionCalls();

            if (functionCalls && functionCalls.length > 0) {
                const call = functionCalls[0];
                logger.info(`Gemini proposed function call: ${call.name}`);
                return { name: call.name, args: call.args };
            }
            
            logger.info("Gemini recommends HOLD. Reason: " + result.response.text());
            return null; // Hold
        } catch (error) {
            logger.exception(error);
            return null;
        }
    }
}

export default GeminiAPI;