// src/trading_ai_system.js
import { GeminiAPI } from './api/gemini_api.js';
import { BybitAPI } from './api/bybit_api.js';
import { RiskPolicy } from './core/risk_policy.js';
import { TradingFunctions } from './core/trading_functions.js';
import { AdvancedIndicatorProcessor } from './indicators/advanced_indicator_processor.js';
import { PatternRecognitionProcessor } from './patterns/pattern_recognition_processor.js';
import { Logger } from './utils/logger.js';


import Decimal from 'decimal.js';

const logger = new Logger('AI_SYSTEM');

export class TradingAISystem {
        constructor(geminiApiKey, bybitApiKey, bybitApiSecret, useTestnet = false, appConfig) {
        this.config = appConfig;
        this.bybitAdapter = new BybitAPI(bybitApiKey, bybitApiSecret, useTestnet);
        this.riskPolicy = new RiskPolicy(this.bybitAdapter);
        this.tradingFunctions = new TradingFunctions(this.bybitAdapter, this.riskPolicy);
        this.indicatorProcessor = new AdvancedIndicatorProcessor();
        this.patternProcessor = new PatternRecognitionProcessor();

        // Define tools for Gemini function calling
        this.toolDeclarations = [
            {
                functionDeclarations: [
                    {
                        name: 'getMarketData',
                        description: 'Get current real-time market data for a given symbol.',
                        parameters: {
                            type: 'object',
                            properties: {
                                symbol: { type: 'string', description: 'The trading pair symbol, e.g., "BTCUSDT".' }
                            },
                            required: ['symbol']
                        }
                    },
                    {
                        name: 'getHistoricalData',
                        description: 'Get historical candlestick data for a given symbol and interval.',
                        parameters: {
                            type: 'object',
                            properties: {
                                symbol: { type: 'string', description: 'The trading pair symbol, e.g., "BTCUSDT".' },
                                interval: { type: 'string', description: 'Candlestick interval, e.g., "1h", "1d".' },
                                limit: { type: 'number', description: 'Number of candles to retrieve (max 200).', default: 100 }
                            },
                            required: ['symbol', 'interval']
                        }
                    },
                    {
                        name: 'getPortfolio',
                        description: 'Get the current account portfolio details including balances and positions.',
                        parameters: { type: 'object', properties: {} }
                    },
                    {
                        name: 'marketBuy',
                        description: 'Place a market buy order for a specified quantity of an asset.',
                        parameters: {
                            type: 'object',
                            properties: {
                                symbol: { type: 'string', description: 'The trading pair symbol, e.g., "BTCUSDT".' },
                                quantity: { type: 'string', description: 'The quantity of the base asset to buy (as a string for Decimal).' }
                            },
                            required: ['symbol', 'quantity']
                        }
                    },
                    {
                        name: 'limitSell',
                        description: 'Place a limit sell order for a specified quantity of an asset at a given price.',
                        parameters: {
                            type: 'object',
                            properties: {
                                symbol: { type: 'string', description: 'The trading pair symbol, e.g., "BTCUSDT".' },
                                quantity: { type: 'string', description: 'The quantity of the base asset to sell (as a string for Decimal).' },
                                price: { type: 'string', description: 'The limit price for the sell order (as a string for Decimal).' }
                            },
                            required: ['symbol', 'quantity', 'price']
                        }
                    },
                    {
                        name: 'cancelOrder',
                        description: 'Cancel an open order by its order ID.',
                        parameters: {
                            type: 'object',
                            properties: {
                                symbol: { type: 'string', description: 'The trading pair symbol, e.g., "BTCUSDT".' },
                                orderId: { type: 'string', description: 'The ID of the order to cancel.' }
                            },
                            required: ['symbol', 'orderId']
                        }
                    }
                ]
            }
        ];
        this.geminiAPI = new GeminiAPI(geminiApiKey, this.toolDeclarations);
        logger.info('TradingAISystem initialized.');
    }

    /**
     * Executes a tool call requested by the Gemini AI.
     * @param {object} toolCall - The toolCall object from Gemini's response.
     * @returns {Promise<any>} - The result of the executed function.
     */
    async _executeToolCall(toolCall) {
        const functionName = toolCall.name;
        const args = toolCall.args;

        logger.debug(`Executing tool call: ${functionName} with args:`, args);

        // Convert Decimal string args back to Decimal objects where appropriate
        const processedArgs = {};
        for (const key in args) {
            if (['quantity', 'price'].includes(key) && typeof args[key] === 'string') {
                processedArgs[key] = new Decimal(args[key]);
            } else {
                processedArgs[key] = args[key];
            }
        }

        if (typeof this.tradingFunctions[functionName] === 'function') {
            try {
                const result = await this.tradingFunctions[functionName](...Object.values(processedArgs));
                logger.info(`Tool call ${functionName} executed successfully. Result:`, result);
                return result;
            } catch (error) {
                logger.error(`Error executing tool call ${functionName}:`, error);
                return { error: error.message };
            }
        }
        else {
            logger.error(`Unknown function requested by Gemini: ${functionName}`);
            return { error: `Function ${functionName} not found.` };
        }
    }


    /**
     * Performs a comprehensive quantitative analysis using local indicators and AI insights.
     * @param {string} symbol - Trading pair.
     * @param {string} interval - Candlestick interval.
     * @returns {Promise<object>} - Analysis report.
     */
    async performQuantitativeAnalysis(symbol, interval) {
        logger.info(`Starting quantitative analysis for ${symbol} on ${interval} interval.`);

        // 1. Fetch historical data
        const historicalData = await this.tradingFunctions.getHistoricalData(symbol, interval, 200);
        if (!historicalData || historicalData.length === 0) {
            return { error: 'No historical data available for analysis.' };
        }

        const closes = historicalData.map(d => d.close);

        // 2. Calculate local technical indicators
        const rsi = this.indicatorProcessor.calculateRSI(closes);
        const macd = this.indicatorProcessor.calculateMACD(closes);
        const bbands = this.indicatorProcessor.calculateBBands(closes);
        const atr = this.indicatorProcessor.calculateATR(historicalData); // ATR needs OHLC

        const indicatorResults = {
            closes,
            rsi: rsi.slice(-1)[0], // Last RSI value
            macd: { // Last MACD values
                macd: macd.macd.slice(-1)[0],
                signal: macd.signal.slice(-1)[0],
                hist: macd.hist.slice(-1)[0],
            },
            bbands: { // Last BBands values
                upper: bbands.upper.slice(-1)[0],
                middle: bbands.middle.slice(-1)[0],
                lower: bbands.lower.slice(-1)[0],
            },
            atr: atr.slice(-1)[0], // Last ATR value
        };
        logger.debug('Latest Indicator Results:', indicatorResults);

        const compositeSignal = this.indicatorProcessor.calculateCompositeSignals({
            closes,
            rsi: rsi,
            macd: macd,
            bbands: bbands
        }, { rsi: 0.3, macd: 0.4, bbands: 0.3 }); // Example weights
        logger.debug('Composite Signal:', compositeSignal);

        // 3. Detect local candlestick patterns
        const detectedPatterns = this.patternProcessor.analyzeCandlestickPatterns(historicalData.slice(-2)); // Check last 2 candles
        logger.debug('Detected Candlestick Patterns:', detectedPatterns);

        // 4. Prepare prompt for Gemini AI with local analysis
        let aiPrompt = `Perform a detailed market analysis for ${symbol} on the ${interval} interval.
        Consider the following recent data and technical indicators:

        - Current Price: ${historicalData.slice(-1)[0].close.toFixed(2)}
        - Last Close: ${historicalData.slice(-1)[0].close.toFixed(2)}
        - Last RSI: ${indicatorResults.rsi.isNaN() ? 'N/A' : indicatorResults.rsi.toFixed(2)}
        - Last MACD Line: ${indicatorResults.macd.macd.isNaN() ? 'N/A' : indicatorResults.macd.macd.toFixed(4)}
        - Last MACD Signal Line: ${indicatorResults.macd.signal.isNaN() ? 'N/A' : indicatorResults.macd.signal.toFixed(4)}
        - Last MACD Histogram: ${indicatorResults.macd.hist.isNaN() ? 'N/A' : indicatorResults.macd.hist.toFixed(4)}
        - Last Bollinger Bands (Upper, Middle, Lower): ${indicatorResults.bbands.upper.isNaN() ? 'N/A' : indicatorResults.bbands.upper.toFixed(2)}, ${indicatorResults.bbands.middle.isNaN() ? 'N/A' : indicatorResults.bbands.middle.toFixed(2)}, ${indicatorResults.bbands.lower.isNaN() ? 'N/A' : indicatorResults.bbands.lower.toFixed(2)}
        - Last ATR: ${indicatorResults.atr.isNaN() ? 'N/A' : indicatorResults.atr.toFixed(4)}

        Detected candlestick patterns:
        ${detectedPatterns.length > 0 ? detectedPatterns.map(p => `- ${p.pattern} (Confidence: ${p.confidence * 100}%, Signal: ${p.signal})`).join('\n') : 'None'}

        Composite signal from local analysis: ${compositeSignal.interpretation} (Score: ${compositeSignal.signal.toFixed(2)})
        Details: ${compositeSignal.details}

        Based on this information, provide:
        1. An overall market sentiment (Bullish, Bearish, Neutral, Volatile).
        2. Key price levels (support, resistance).
        3. Potential trade ideas (e.g., "Consider buying if price breaks above X", "Consider selling if price drops below Y").
        4. Any additional insights or risks.
        5. If appropriate, use the available tools to suggest a specific trade action (e.g., marketBuy, limitSell).`;

        this.geminiAPI.updateMarketContext(aiPrompt); // Update context for future AI interactions

        // 5. Get AI's analysis and potential tool calls
        let aiResponse = await this.geminiAPI.getAIResponse(aiPrompt);

        // Handle tool calls if Gemini suggests any
        const functionCalls = JSON.parse(aiResponse).functionCalls; // Assuming AI response is JSON string containing tool calls
        if (functionCalls && functionCalls.length > 0) {
            for (const call of functionCalls) {
                const toolResult = await this._executeToolCall(call);
                // Potentially send toolResult back to Gemini for further refinement
                logger.info('Gemini tool execution result:', toolResult);
            }
            // After executing tools, you might want to ask Gemini for a final summary
            aiResponse = await this.geminiAPI.getAIResponse('Based on the executed actions, provide a final analysis and updated trade recommendation.');
        }

        // 6. Integrate AI's analysis with local insights
        const analysisReport = {
            timestamp: new Date().toISOString(),
            symbol: symbol,
            interval: interval,
            localIndicators: indicatorResults,
            localPatterns: detectedPatterns,
            compositeSignal: compositeSignal,
            aiAnalysis: aiResponse,
        };

        logger.info(`Quantitative analysis complete for ${symbol}.`);
        return analysisReport;
    }

    /**
     * Conceptually starts a live trading session.
     * In a real bot, this would involve a continuous loop fetching data, analyzing, and potentially trading.
     * @param {string} symbol - Trading pair.
     * @param {string} interval - Candlestick interval.
     */
    async startLiveTradingSession(symbol, interval) {
        if (!this.bybitAdapter.bybitEnabled) {
            logger.error('Bybit API is not enabled. Cannot start live trading session.');
            return;
        }

        logger.info(`Starting conceptual live trading session for ${symbol} on ${interval} interval.`);
        // This would be a continuous loop
        setInterval(async () => {
            try {
                logger.info(`[${new Date().toISOString()}] Executing trade cycle...`);
                const analysis = await this.performQuantitativeAnalysis(symbol, interval);
                logger.debug('Current analysis for live session:', analysis);

                // Here, you would parse `analysis.aiAnalysis` and `analysis.compositeSignal`
                // to make actual trading decisions.
                // Example: If AI suggests a 'Strong Bullish' signal AND local RSI is oversold, consider a buy.
                // let tradeDecision = this.makeTradingDecision(analysis);
                // if (tradeDecision.action === 'buy') {
                //     await this.tradingFunctions.marketBuy(symbol, new Decimal(tradeDecision.quantity));
                // } else if (tradeDecision.action === 'sell') {
                //     await this.tradingFunctions.limitSell(symbol, new Decimal(tradeDecision.quantity), new Decimal(tradeDecision.price));
                // }

                logger.log('Trade cycle completed.');

            } catch (error) {
                logger.exception('Error during live trading session cycle:', error);
            }
        }, 60 * 1000); // Run every minute (adjust as needed for interval)

        // For a more robust solution, use WebSockets for real-time updates rather than polling.
        // this.bybitAdapter.connectWebSocket();
    }
}