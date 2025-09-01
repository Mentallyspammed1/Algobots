import { GoogleGenerativeAI } from '@google/generative-ai';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class GeminiAnalyzer {
  constructor(apiKey) {
    if (!apiKey) {
      throw new Error('Gemini API key is required');
    }
    
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeTrends(marketData) {
    try {
      logger.info(chalk.blue('🤖 Analyzing with Gemini AI...'));
      
      const prompt = this.buildAnalysisPrompt(marketData);
      const result = await this.model.generateContent(prompt);
      const response = await result.response;
      const analysis = response.text();
      
      return this.parseAIResponse(analysis);
      
    } catch (error) {
      logger.error(chalk.red('Gemini API error:', error));
      return this.getDefaultAnalysis();
    }
  }

  buildAnalysisPrompt(data) {
    return `
    You are an expert cryptocurrency scalping trader. Analyze the following market data and provide a trading signal.
    
    CURRENT MARKET DATA:
    Symbol: ${data.symbol || 'TRUMPUSDT'}
    Current Price: $${data.currentPrice}
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
      "keyFactors": ["factor1", "factor2", "factor3"],
      "riskLevel": "LOW/MEDIUM/HIGH",
      "entryStrategy": "description",
      "exitStrategy": "description",
      "reasoning": "detailed explanation"
    }
    
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
      // Extract JSON from response
      const jsonMatch = response.match(/\{[\s\S]*\}/);
      if (jsonMatch) {
        const analysis = JSON.parse(jsonMatch[0]);
        logger.info(chalk.green('✅ AI analysis completed'));
        return analysis;
      }
    } catch (error) {
      logger.error(chalk.red('Error parsing AI response:', error));
    }
    
    return this.getDefaultAnalysis();
  }

  getDefaultAnalysis() {
    return {
      trend: "NEUTRAL",
      strength: 50,
      action: "HOLD",
      confidence: 40,
      keyFactors: ["Insufficient data", "Manual review recommended"],
      riskLevel: "HIGH",
      entryStrategy: "Wait for clearer signals",
      exitStrategy: "Use tight stop losses",
      reasoning: "Unable to determine clear trend from available data"
    };
  }
}