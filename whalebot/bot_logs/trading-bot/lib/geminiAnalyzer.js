import { GoogleGenerativeAI } from '@google/generative-ai';
import chalk from 'chalk';
import { logger } from './utils.js';
import {
  calculateVolatilityIndex,
  calculateVWMA,
  calculateVolumeDelta,
  calculateKaufmanAMA,
  calculateFibonacciPivotPoints,
} from './indicators.js';

export default class GeminiAnalyzer {
  constructor(apiKey, tradingSymbol) { // Accept tradingSymbol
    if (!apiKey) {
      throw new Error('Gemini API key is required');
    }
    
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
    this.tradingSymbol = tradingSymbol; // Store tradingSymbol
  }

  async analyzeTrends(marketData) {
    try {
      logger.info(chalk.hex('#00FFFF').bold('🤖 Analyzing with Gemini AI...'));
      
      let indicators = {};
      if (marketData.klines && marketData.klines.length > 0) {
        // Calculate new indicators
        const klines = marketData.klines;
        const indicatorSettings = marketData.indicatorSettings; // Assuming indicator settings are passed

        indicators.volatilityIndex = calculateVolatilityIndex(klines, indicatorSettings.volatility_index_period).slice(-1)[0];
        indicators.vwma = calculateVWMA(klines, indicatorSettings.vwma_period).slice(-1)[0];
        indicators.volumeDelta = calculateVolumeDelta(klines, indicatorSettings.volume_delta_period).slice(-1)[0];
        indicators.kaufmanAMA = calculateKaufmanAMA(klines, indicatorSettings.kama_period, indicatorSettings.kama_fast_period, indicatorSettings.kama_slow_period).slice(-1)[0];
        indicators.fibonacciPivotPoints = calculateFibonacciPivotPoints(klines);
      }

      const prompt = this.buildAnalysisPrompt(marketData, indicators);
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const analysis = response.text();
      
      return this.parseAIResponse(analysis);
      
    } catch (error) {
      logger.error(chalk.hex('#FF00FF').bold('Gemini API error:'), error);
      return this.getDefaultAnalysis();
    }
  }

  buildAnalysisPrompt(data, indicators) {
    return `
    You are an expert cryptocurrency scalping trader. Analyze the following market data and provide a trading signal.
    
    CURRENT MARKET DATA:
    Symbol: ${this.tradingSymbol}
    Current Price: ${data.currentPrice}
    Price Change: ${data.priceChangePercent?.toFixed(2)}%
    
    TECHNICAL INDICATORS:
    - RSI: ${data.rsi} (Overbought >70, Oversold <30)
    - MACD Line: ${data.macd_line}
    - MACD Signal: ${data.macd_signal}
    - MACD Histogram: ${data.macd_hist}
    - EMA Short: ${data.ema_short}
    - EMA Long: ${data.ema_long}
    - Bollinger Bands: Upper=${data.bb_upper}, Middle=${data.bb_middle}, Lower=${data.bb_lower}
    - ATR: ${data.atr}
    - ADX: ${data.adx} (Trend strength)
    - Stochastic RSI: K=${data.stochRsi_k}, D=${data.stochRsi_d}
    - MFI: ${data.mfi}
    - CCI: ${data.cci}
    - VWAP: ${data.vwap}
    - Volatility Index: ${indicators.volatilityIndex?.toFixed(4)}
    - VWMA: ${indicators.vwma?.toFixed(4)}
    - Volume Delta: ${indicators.volumeDelta?.toFixed(4)}
    - Kaufman AMA: ${indicators.kaufmanAMA?.toFixed(4)}
    - Fibonacci Pivot Points: Pivot=${indicators.fibonacciPivotPoints?.pivot?.toFixed(4)}, R1=${indicators.fibonacciPivotPoints?.r1?.toFixed(4)}, R2=${indicators.fibonacciPivotPoints?.r2?.toFixed(4)}, S1=${indicators.fibonacciPivotPoints?.s1?.toFixed(4)}, S2=${indicators.fibonacciPivotPoints?.s2?.toFixed(4)}
    
    MULTI-TIMEFRAME TRENDS:
    - 3min EMA Trend: ${data['3_ema']}
    - 3min Supertrend: ${data['3_supertrend']}
    - 15min EMA Trend: ${data['15_ema']}
    - 15min Supertrend: ${data['15_supertrend']}
    
    Based on this data, provide a scalping signal with the following JSON format:
    {
      "trend": "BULLISH/BEARISH/NEUTRAL",
      "strength": 1-100,
      "action": "BUY/SELL/HOLD",
      "confidence": 1-100,
      "confidenceReasoning": "detailed explanation for the confidence score", // NEW FIELD
      "keyFactors": ["factor1", "factor2", "factor3"],
      "riskLevel": "LOW/MEDIUM/HIGH",
      "entryStrategy": "description",
      "exitStrategy": "description",
      "reasoning": "detailed explanation for the trading signal"
    }

    When determining the 'confidence' score, provide a detailed explanation in 'confidenceReasoning' justifying your assessment based on the confluence or divergence of indicators, market context, and risk factors.
    
    Focus on:
    1. Momentum and trend alignment across timeframes
    2. Overbought/oversold conditions
    3. Volume and money flow
    4. Support/resistance levels from Bollinger Bands
    5. Risk/reward ratio for scalping
    
    Respond ONLY with valid JSON.
    `;
  }

  parseAIResponse(response) {
    try {
      // Find the first and last curly braces to extract the JSON content
      const firstCurly = response.indexOf('{');
      const lastCurly = response.lastIndexOf('}');

      if (firstCurly !== -1 && lastCurly !== -1 && lastCurly > firstCurly) {
        const jsonString = response.substring(firstCurly, lastCurly + 1);
        const analysis = JSON.parse(jsonString);

        // Validate essential fields
        if (typeof analysis.reasoning !== 'string' || analysis.reasoning.trim() === '') {
          analysis.reasoning = 'AI did not provide specific reasoning.';
        }
        if (typeof analysis.confidenceReasoning !== 'string' || analysis.confidenceReasoning.trim() === '') {
          analysis.confidenceReasoning = 'AI did not provide specific confidence reasoning.';
        }

        logger.info(chalk.hex('#00FF00').bold('✅ AI analysis completed'));
        return analysis;
      } else {
        logger.error(chalk.hex('#FF00FF').bold('AI response did not contain a valid JSON object.'));
        logger.debug(chalk.hex('#FF00FF')(`Raw AI response: ${response}`)); // Log raw response for debugging
      }
    } catch (error) {
      logger.error(chalk.hex('#FF00FF').bold('Error parsing AI response:'), error);
      logger.debug(chalk.hex('#FF00FF')(`Raw AI response that caused error: ${response}`)); // Log raw response for debugging
    }
    
    return this.getDefaultAnalysis();
  }

  getDefaultAnalysis() {
    return {
      trend: "NEUTRAL",
      strength: 50,
      action: "HOLD",
      confidence: 40,
      confidenceReasoning: "Default reasoning: Insufficient data or error during AI analysis.", // NEW FIELD
      keyFactors: ["Insufficient data", "Manual review recommended"],
      riskLevel: "HIGH",
      entryStrategy: "Wait for clearer signals",
      exitStrategy: "Use tight stop losses",
      reasoning: "Unable to determine clear trend from available data"
    };
  }
}