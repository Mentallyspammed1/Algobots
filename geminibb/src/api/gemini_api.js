// src/api/gemini_api.js
import pkg from '@google/genai';
const { GoogleGenAI } = pkg;
import { Logger } from '../utils/logger.js';
import { withRetry } from '../utils/retry_handler.js';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const config = require('../../config.json');

const logger = new Logger('GEMINI_API');

export class GeminiAPI {
    constructor(apiKey, toolDeclarations) {
        if (!apiKey) {
            throw new Error('Gemini API Key is required.');
        }
        this.genAI = new GoogleGenAI(apiKey);
        
        this.model = genAIInstance.getGenerativeModel({
            model: config.ai.modelName,
            systemInstruction: config.ai.systemInstruction,
            tools: toolDeclarations // Dynamic tool declarations
        });
        this.generationConfig = {
            temperature: config.ai.temperature,
            topP: config.ai.topP,
            topK: config.ai.topK,
            maxOutputTokens: config.ai.maxOutputTokens
        };
        this.marketContext = null; // Stores market context for prompt
        this.cacheMarketContext = config.ai.cacheMarketContext;

        this.chatSession = this.model.startChat({
            generationConfig: this.generationConfig,
            history: [], // Initialize with empty history for a fresh session
        });
    }

    /**
     * Sends a prompt to the Gemini model and returns the response.
     * @param {string} prompt - The user prompt.
     * @param {Array<object>} [history] - Optional chat history.
     * @returns {Promise<object>} - The Gemini AI response.
     */
    async getAIResponse(prompt) {
        const parts = [{ text: prompt }];
        if (this.marketContext && this.cacheMarketContext) {
            parts.unshift({ text: `Current market data context:
${this.marketContext}
` });
        }

        const runPrompt = async () => {
            logger.debug('Sending prompt to Gemini...', { prompt: prompt.substring(0, 100) + '...' });
            const result = await this.chatSession.sendMessage(parts); // Use chat session for turn-by-turn interaction
            const response = await result.response;
            const text = response.text();
            logger.debug('Gemini raw response:', text);

            const functionCalls = response.functionCalls();
            if (functionCalls && functionCalls.length > 0) {
                logger.info('Gemini requested function calls:', functionCalls);
                // In a real scenario, you would execute these calls and send the results back to Gemini.
                // For now, we'll just log them.
                // Example: const toolResults = await this._executeToolCalls(functionCalls);
                // const finalResponse = await this.chatSession.sendMessage({ toolResults: toolResults });
                // return finalResponse.response;
            }

            return { text, functionCalls };
        };
        return withRetry(runPrompt, { maxAttempts: 3 })();
    }

    /**
     * Conceptually analyzes market charts/images using Gemini's multimodal capabilities.
     * Requires the `gemini-pro-vision` model or similar.
     * @param {string} imageBase64 - Base64 encoded image data.
     * @param {string} prompt - Accompanying text prompt.
     * @returns {Promise<string>} - Analysis from Gemini.
     */
    async analyzeMarketCharts(/* imageBase64, prompt */) { // Commented out unused parameters
        // This feature would require a different model instance (e.g., gemini-pro-vision)
        // and handling of image parts. For brevity, this is a conceptual placeholder.
        logger.warn('analyzeMarketCharts is a conceptual method. Requires a vision model and image processing.');
        // const visionModel = this.genAI.getGenerativeModel({ model: 'gemini-pro-vision' }); // Commented out unused variable
        // Example structure for image input:
        // const imagePart = {
        //     inlineData: {
        //         mimeType: 'image/jpeg', // Or appropriate mime type
        //         data: imageBase64
        //     }
        // };
        // const result = await visionModel.generateContent([prompt, imagePart]);
        // const response = await result.response;
        // return response.text();
        return Promise.resolve("Conceptual chart analysis output.");
    }

    /**
     * Updates the internal market context.
     * @param {string} context - New market data context string.
     */
    updateMarketContext(context) {
        this.marketContext = context;
        logger.debug('Market context updated.');
    }
}
