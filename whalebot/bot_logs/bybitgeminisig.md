

Building a Node.js bot that leverages the Google Gemini API for trend analysis and scalping signal generation requires integrating multiple components: log file parsing, technical indicator analysis, AI-powered decision making, and signal generation. Here's a comprehensive implementation that processes your trading log data and generates actionable scalping signals.

## Setting Up the Project

First, initialize your Node.js project and install the necessary dependencies:

```bash
npm init -y
npm install @google/generativeai fs-extra chalk dotenv moment
```

Create a `.env` file to store your Gemini API key securely:

```env
GEMINI_API_KEY=your_gemini_api_key_here
```

## Main Bot Implementation

```javascript
// tradingBot.js
import { GoogleGenerativeAI } from "@google/generativeai";
import fs from 'fs-extra';
import chalk from 'chalk';
import dotenv from 'dotenv';
import moment from 'moment';
import { promisify } from 'util';
import readline from 'readline';

dotenv.config();

class GeminiTradingBot {
    constructor() {
        // Initialize Gemini API with your API key
        this.genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
        this.model = this.genAI.getGenerativeModel({ model: "gemini-2.0-flash-exp" });
        
        // Configuration
        this.config = {
            logFilePath: './trading_logs.txt',
            outputPath: './trading_signals.json',
            updateInterval: 30000, // 30 seconds
            riskPerTrade: 0.02, // 2% risk per trade
            confidenceThreshold: 0.65
        };
        
        // State management
        this.lastProcessedLine = 0;
        this.tradingSignals = [];
        this.indicatorHistory = [];
    }

    // Parse log file and extract indicator data
    async parseLogFile() {
        try {
            const fileContent = await fs.readFile(this.config.logFilePath, 'utf-8');
            const lines = fileContent.split('\n');
            
            const indicatorData = {
                timestamp: null,
                price: null,
                indicators: {},
                fibLevels: {},
                trends: {}
            };
            
            for (let i = this.lastProcessedLine; i < lines.length; i++) {
                const line = lines[i];
                
                // Extract timestamp
                const timestampMatch = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
                if (timestampMatch) {
                    indicatorData.timestamp = timestampMatch;
                }
                
                // Extract current price
                const priceMatch = line.match(/Current Price: ([\d.]+)/);
                if (priceMatch) {
                    indicatorData.price = parseFloat(priceMatch);
                }
                
                // Extract indicators
                const indicatorPatterns = {
                    'RSI': /RSI: ([\d.]+)/,
                    'MACD_Line': /MACD_Line: ([-\d.]+)/,
                    'MACD_Signal': /MACD_Signal: ([-\d.]+)/,
                    'MACD_Hist': /MACD_Hist: ([-\d.]+)/,
                    'ATR': /ATR: ([\d.]+)/,
                    'BB_Upper': /BB_Upper: ([\d.]+)/,
                    'BB_Middle': /BB_Middle: ([\d.]+)/,
                    'BB_Lower': /BB_Lower: ([\d.]+)/,
                    'VWAP': /VWAP: ([\d.]+)/,
                    'StochRSI_K': /StochRSI_K: ([\d.]+)/,
                    'StochRSI_D': /StochRSI_D: ([\d.]+)/,
                    'ADX': /ADX: ([\d.]+)/,
                    'CCI': /CCI: ([-\d.]+)/,
                    'MFI': /MFI: ([\d.]+)/,
                    'CMF': /CMF: ([-\d.]+)/,
                    'EMA_Short': /EMA_Short: ([\d.]+)/,
                    'EMA_Long': /EMA_Long: ([\d.]+)/,
                    'SMA_10': /SMA_10: ([\d.]+)/,
                    'OBV': /OBV: ([-\d.]+)/
                };
                
                for (const [key, pattern] of Object.entries(indicatorPatterns)) {
                    const match = line.match(pattern);
                    if (match) {
                        indicatorData.indicators[key] = parseFloat(match);
                    }
                }
                
                // Extract Fibonacci levels
                const fibMatch = line.match(/([\d.]+)%: ([\d.]+)/);
                if (fibMatch) {
                    indicatorData.fibLevels[fibMatch] = parseFloat(fibMatch);
                }
                
                // Extract multi-timeframe trends
                const trendMatch = line.match(/(\d+)_(\w+): (\w+)/);
                if (trendMatch) {
                    const key = `${trendMatch}_${trendMatch}`;
                    indicatorData.trends[key] = trendMatch;
                }
            }
            
            this.lastProcessedLine = lines.length;
            return indicatorData;
            
        } catch (error) {
            console.error(chalk.red('Error parsing log file:'), error);
            return null;
        }
    }

    // Prepare data for Gemini analysis
    prepareAnalysisPrompt(indicatorData) {
        return `
        Analyze the following cryptocurrency trading data for scalping opportunities:
        
        Current Market Data:
        - Price: ${indicatorData.price}
        - Timestamp: ${indicatorData.timestamp}
        
        Technical Indicators:
        ${JSON.stringify(indicatorData.indicators, null, 2)}
        
        Fibonacci Retracement Levels:
        ${JSON.stringify(indicatorData.fibLevels, null, 2)}
        
        Multi-Timeframe Trends:
        ${JSON.stringify(indicatorData.trends, null, 2)}
        
        Historical Context (Last 5 readings):
        ${JSON.stringify(this.indicatorHistory.slice(-5), null, 2)}
        
        Based on this data, provide a scalping trading signal with the following:
        1. Direction (BUY/SELL/HOLD)
        2. Entry price
        3. Stop loss (tight for scalping, considering ATR)
        4. Take profit targets (at least 2 targets)
        5. Confidence level (0-100%)
        6. Detailed reasoning for the signal
        7. Risk assessment
        8. Key levels to watch
        
        Consider:
        - Momentum indicators alignment
        - Support/resistance from Fibonacci levels
        - Volume confirmation (OBV, CMF)
        - Trend alignment across timeframes
        - Overbought/oversold conditions
        - Volatility (ATR) for position sizing
        
        Respond in JSON format only, no additional text.
        `;
    }

    // Generate trading signal using Gemini API
    async generateTradingSignal(indicatorData) {
        try {
            console.log(chalk.cyan('🤖 Analyzing market conditions with Gemini AI...'));
            
            const prompt = this.prepareAnalysisPrompt(indicatorData);
            
            // Send request to Gemini API
            const result = await this.model.generateContent(prompt);
            const response = result.response;
            const text = response.text();
            
            // Parse JSON response from Gemini
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            if (!jsonMatch) {
                throw new Error('Invalid response format from Gemini');
            }
            
            const signal = JSON.parse(jsonMatch);
            
            // Enhance signal with additional data
            const enhancedSignal = {
                ...signal,
                timestamp: indicatorData.timestamp,
                currentPrice: indicatorData.price,
                generatedAt: moment().format('YYYY-MM-DD HH:mm:ss'),
                indicators: {
                    rsi: indicatorData.indicators.RSI,
                    macd: indicatorData.indicators.MACD_Hist,
                    stochRsi: indicatorData.indicators.StochRSI_K,
                    adx: indicatorData.indicators.ADX,
                    mfi: indicatorData.indicators.MFI
                }
            };
            
            return enhancedSignal;
            
        } catch (error) {
            console.error(chalk.red('Error generating trading signal:'), error);
            return this.generateFallbackSignal(indicatorData);
        }
    }

    // Fallback signal generation using rule-based logic
    generateFallbackSignal(indicatorData) {
        const { price, indicators } = indicatorData;
        const { RSI, MACD_Hist, StochRSI_K, BB_Upper, BB_Lower, ATR, ADX, MFI } = indicators;
        
        let signal = {
            direction: 'HOLD',
            entry: price,
            stopLoss: null,
            takeProfit: [],
            confidence: 0,
            reasoning: [],
            riskAssessment: 'MEDIUM'
        };
        
        // Bullish signals
        const bullishConditions = [];
        if (RSI < 30) bullishConditions.push('RSI oversold');
        if (StochRSI_K < 20) bullishConditions.push('StochRSI oversold');
        if (price <= BB_Lower) bullishConditions.push('Price at lower Bollinger Band');
        if (MACD_Hist > 0) bullishConditions.push('MACD histogram positive');
        if (MFI < 30) bullishConditions.push('MFI oversold');
        
        // Bearish signals
        const bearishConditions = [];
        if (RSI > 70) bearishConditions.push('RSI overbought');
        if (StochRSI_K > 80) bearishConditions.push('StochRSI overbought');
        if (price >= BB_Upper) bearishConditions.push('Price at upper Bollinger Band');
        if (MACD_Hist < 0) bearishConditions.push('MACD histogram negative');
        if (MFI > 70) bearishConditions.push('MFI overbought');
        
        // Calculate confidence and determine direction
        const bullishScore = bullishConditions.length;
        const bearishScore = bearishConditions.length;
        
        if (bullishScore >= 3 && ADX > 25) {
            signal.direction = 'BUY';
            signal.stopLoss = price - (ATR * 1.5);
            signal.takeProfit = [
                price + (ATR * 1),
                price + (ATR * 2),
                price + (ATR * 3)
            ];
            signal.confidence = Math.min(95, 50 + (bullishScore * 10));
            signal.reasoning = bullishConditions;
        } else if (bearishScore >= 3 && ADX > 25) {
            signal.direction = 'SELL';
            signal.stopLoss = price + (ATR * 1.5);
            signal.takeProfit = [
                price - (ATR * 1),
                price - (ATR * 2),
                price - (ATR * 3)
            ];
            signal.confidence = Math.min(95, 50 + (bearishScore * 10));
            signal.reasoning = bearishConditions;
        }
        
        return {
            ...signal,
            timestamp: indicatorData.timestamp,
            currentPrice: price,
            generatedAt: moment().format('YYYY-MM-DD HH:mm:ss')
        };
    }

    // Save signals to JSON file
    async saveSignals() {
        try {
            const outputData = {
                lastUpdate: moment().format('YYYY-MM-DD HH:mm:ss'),
                signals: this.tradingSignals.slice(-50), // Keep last 50 signals
                statistics: this.calculateStatistics()
            };
            
            await fs.writeJson(this.config.outputPath, outputData, { spaces: 2 });
            console.log(chalk.green(`✅ Signals saved to ${this.config.outputPath}`));
            
        } catch (error) {
            console.error(chalk.red('Error saving signals:'), error);
        }
    }

    // Calculate trading statistics
    calculateStatistics() {
        const totalSignals = this.tradingSignals.length;
        const buySignals = this.tradingSignals.filter(s => s.direction === 'BUY').length;
        const sellSignals = this.tradingSignals.filter(s => s.direction === 'SELL').length;
        const avgConfidence = this.tradingSignals.reduce((sum, s) => sum + (s.confidence || 0), 0) / totalSignals || 0;
        
        return {
            totalSignals,
            buySignals,
            sellSignals,
            holdSignals: totalSignals - buySignals - sellSignals,
            averageConfidence: avgConfidence.toFixed(2)
        };
    }

    // Main execution loop
    async run() {
        console.log(chalk.blue('🚀 Gemini Trading Bot Started'));
        console.log(chalk.yellow(`📊 Monitoring: ${this.config.logFilePath}`));
        console.log(chalk.yellow(`💾 Output: ${this.config.outputPath}`));
        
        setInterval(async () => {
            try {
                // Parse latest log data
                const indicatorData = await this.parseLogFile();
                
                if (indicatorData && indicatorData.price) {
                    // Store in history
                    this.indicatorHistory.push(indicatorData);
                    if (this.indicatorHistory.length > 100) {
                        this.indicatorHistory.shift();
                    }
                    
                    // Generate trading signal
                    const signal = await this.generateTradingSignal(indicatorData);
                    
                    if (signal) {
                        this.tradingSignals.push(signal);
                        
                        // Display signal
                        this.displaySignal(signal);
                        
                        // Save to file
                        await this.saveSignals();
                    }
                }
                
            } catch (error) {
                console.error(chalk.red('Error in main loop:'), error);
            }
        }, this.config.updateInterval);
    }

    // Display signal in console
    displaySignal(signal) {
        console.log(chalk.cyan('\n' + '='.repeat(50)));
        console.log(chalk.white('📈 NEW TRADING SIGNAL'));
        console.log(chalk.cyan('='.repeat(50)));
        
        const colorMap = {
            'BUY': chalk.green,
            'SELL': chalk.red,
            'HOLD': chalk.yellow
        };
        
        const color = colorMap[signal.direction] || chalk.white;
        
        console.log(color(`Direction: ${signal.direction}`));
        console.log(chalk.white(`Entry: ${signal.entry}`));
        console.log(chalk.red(`Stop Loss: ${signal.stopLoss}`));
        console.log(chalk.green(`Take Profit: ${signal.takeProfit?.join(', ')}`));
        console.log(chalk.magenta(`Confidence: ${signal.confidence}%`));
        console.log(chalk.blue(`Reasoning: ${signal.reasoning}`));
        console.log(chalk.cyan('='.repeat(50) + '\n'));
    }
}

// Initialize and run the bot
const bot = new GeminiTradingBot();
bot.run();
```

## Enhanced Signal Generator Module

```javascript
// signalGenerator.js
export class SignalGenerator {
    constructor(geminiModel) {
        this.model = geminiModel;
        this.signalHistory = [];
    }

    async analyzeMarketStructure(data) {
        const prompt = `
        Analyze the market structure and identify key levels:
        
        Price Data: ${JSON.stringify(data)}
        
        Identify:
        1. Support and resistance levels
        2. Trend direction (primary, secondary)
        3. Market phase (accumulation, distribution, markup, markdown)
        4. Volume profile analysis
        5. Liquidity zones
        
        Return analysis in JSON format.
        `;

        const result = await this.model.generateContent(prompt);
        return this.parseGeminiResponse(result.response.text());
    }

    async generateScalpingStrategy(marketData, marketStructure) {
        const prompt = `
        Generate a detailed scalping strategy based on:
        
        Market Data: ${JSON.stringify(marketData)}
        Market Structure: ${JSON.stringify(marketStructure)}
        
        Provide:
        1. Entry criteria (specific conditions)
        2. Exit criteria
        3. Position sizing recommendation
        4. Risk/reward ratio
        5. Time frame for trade execution
        6. Alternative scenarios
        
        Format as actionable JSON trading plan.
        `;

        const result = await this.model.generateContent(prompt);
        return this.parseGeminiResponse(result.response.text());
    }

    parseGeminiResponse(text) {
        try {
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            return jsonMatch ? JSON.parse(jsonMatch) : null;
        } catch (error) {
            console.error('Error parsing Gemini response:', error);
            return null;
        }
    }

    validateSignal(signal) {
        // Implement signal validation logic
        const requiredFields = ['direction', 'entry', 'stopLoss', 'takeProfit', 'confidence'];
        const isValid = requiredFields.every(field => signal.hasOwnProperty(field));
        
        if (!isValid) {
            console.warn('Invalid signal structure detected');
            return false;
        }

        // Validate confidence threshold
        if (signal.confidence < 60) {
            console.warn('Signal confidence below threshold');
            return false;
        }

        return true;
    }
}
```

## Risk Management Module

```javascript
// riskManager.js
export class RiskManager {
    constructor(config) {
        this.maxRiskPerTrade = config.maxRiskPerTrade || 0.02;
        this.maxDailyLoss = config.maxDailyLoss || 0.06;
        this.maxOpenPositions = config.maxOpenPositions || 3;
        this.dailyStats = {
            trades: 0,
            profit: 0,
            loss: 0
        };
    }

    calculatePositionSize(accountBalance, entryPrice, stopLoss) {
        const riskAmount = accountBalance * this.maxRiskPerTrade;
        const stopDistance = Math.abs(entryPrice - stopLoss);
        const positionSize = riskAmount / stopDistance;
        
        return {
            size: positionSize.toFixed(4),
            riskAmount: riskAmount.toFixed(2),
            stopDistance: stopDistance.toFixed(4)
        };
    }

    evaluateRisk(signal, currentPositions) {
        const riskScore = {
            acceptable: true,
            reasons: [],
            adjustments: {}
        };

        // Check daily loss limit
        if (Math.abs(this.dailyStats.loss) >= this.maxDailyLoss) {
            riskScore.acceptable = false;
            riskScore.reasons.push('Daily loss limit reached');
        }

        // Check open positions limit
        if (currentPositions.length >= this.maxOpenPositions) {
            riskScore.acceptable = false;
            riskScore.reasons.push('Maximum open positions reached');
        }

        // Adjust stop loss if too wide
        const atrMultiplier = 1.5;
        if (signal.stopDistance > signal.atr * atrMultiplier) {
            riskScore.adjustments.stopLoss = signal.entry - (signal.atr * atrMultiplier);
        }

        return riskScore;
    }

    updateDailyStats(trade) {
        this.dailyStats.trades++;
        if (trade.profit > 0) {
            this.dailyStats.profit += trade.profit;
        } else {
            this.dailyStats.loss += Math.abs(trade.profit);
        }
    }
}
```

## Configuration File

```javascript
// config.js
export const config = {
    gemini: {
        model: 'gemini-2.0-flash-exp',
        temperature: 0.7,
        maxTokens: 2048
    },
    trading: {
        symbols: ['TRUMPUSDT', 'XRPUSDT', 'LINKUSDT'],
        timeframes: ['1m', '3m', '15m'],
        indicators: {
            ema: [9, 21],
            sma: [10, 50],
            rsi: { period: 14, overbought: 70, oversold: 30 },
            macd: { fast: 12, slow: 26, signal: 9 },
            bollinger: { period: 20, stdDev: 2 },
            atr: { period: 14 }
        }
    },
    risk: {
        maxRiskPerTrade: 0.02,
        maxDailyLoss: 0.06,
        maxOpenPositions: 3,
        minConfidence: 65,
        trailingStop: true
    },
    logging: {
        level: 'info',
        file: './logs/trading_bot.log',
        maxFiles: 7
    }
};
```

## Running the Bot

```javascript
// index.js
import { GeminiTradingBot } from './tradingBot.js';
import { config } from './config.js';
import chalk from 'chalk';

async function main() {
    try {
        console.log(chalk.cyan('═══════════════════════════════════════'));
        console.log(chalk.yellow('   🤖 GEMINI TRADING BOT v1.0   '));
        console.log(chalk.cyan('═══════════════════════════════════════'));
        
        const bot = new GeminiTradingBot(config);
        
        // Initialize bot
        await bot.initialize();
        
        // Start monitoring
        await bot.run();
        
        // Graceful shutdown
        process.on('SIGINT', async () => {
            console.log(chalk.yellow('\n📊 Shutting down bot...'));
            await bot.shutdown();
            process.exit(0);
        });
        
    } catch (error) {
        console.error(chalk.red('Fatal error:'), error);
        process.exit(1);
    }
}

main();
```

The bot integrates the Google Gemini API to analyze complex market conditions from your log files, generating sophisticated scalping signals with entry points, stop losses, take profits, confidence levels, and detailed reasoning. It continuously monitors the log file, processes new data every 30 seconds, and outputs actionable trading signals in JSON format.

The system uses Gemini's advanced language model capabilities to interpret technical indicators, identify market patterns, and provide context-aware trading decisions that go beyond simple rule-based strategies. The risk management module ensures proper position sizing and adherence to trading limits, while the signal generator validates all outputs before execution.
I'll create a comprehensive Node.js bot that leverages Google's Gemini API for trend analysis and generates scalping signals based on log data. Here's the complete implementation:

## Project Structure

```
trading-bot/
├── package.json
├── .env
├── index.js
├── lib/
│   ├── logParser.js
│   ├── geminiAnalyzer.js
│   ├── signalGenerator.js
│   └── utils.js
└── output/
    └── signals.json
```

## 1. Package.json

```json
{
  "name": "gemini-scalping-bot",
  "version": "1.0.0",
  "description": "Trading bot using Gemini API for trend analysis",
  "main": "index.js",
  "type": "module",
  "scripts": {
    "start": "node index.js",
    "dev": "nodemon index.js"
  },
  "dependencies": {
    "@google/generative-ai": "^0.17.0",
    "dotenv": "^16.3.1",
    "fs-extra": "^11.2.0",
    "chalk": "^5.3.0",
    "winston": "^3.11.0",
    "node-cron": "^3.0.3",
    "axios": "^1.6.2"
  },
  "devDependencies": {
    "nodemon": "^3.0.2"
  }
}
```

## 2. Environment Variables (.env)

```env
GEMINI_API_KEY=your_gemini_api_key_here
LOG_FILE_PATH=./logs/trading.log
OUTPUT_PATH=./output/signals.json
REFRESH_INTERVAL=5000
RISK_PERCENTAGE=1
```

## 3. Main Bot (index.js)

```javascript
import dotenv from 'dotenv';
import cron from 'node-cron';
import chalk from 'chalk';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import LogParser from './lib/logParser.js';
import GeminiAnalyzer from './lib/geminiAnalyzer.js';
import SignalGenerator from './lib/signalGenerator.js';
import { logger } from './lib/utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

class TradingBot {
  constructor() {
    this.logParser = new LogParser();
    this.geminiAnalyzer = new GeminiAnalyzer(process.env.GEMINI_API_KEY);
    this.signalGenerator = new SignalGenerator();
    this.outputPath = process.env.OUTPUT_PATH || './output/signals.json';
    this.logFilePath = process.env.LOG_FILE_PATH || './logs/trading.log';
    this.isRunning = false;
  }

  async initialize() {
    try {
      // Ensure output directory exists
      await fs.ensureDir(path.dirname(this.outputPath));
      
      logger.info(chalk.green('🚀 Trading Bot Initialized'));
      logger.info(chalk.blue(`📊 Log file: ${this.logFilePath}`));
      logger.info(chalk.blue(`📁 Output: ${this.outputPath}`));
      
      return true;
    } catch (error) {
      logger.error(chalk.red('Initialization failed:', error));
      return false;
    }
  }

  async analyzeAndGenerateSignals() {
    if (this.isRunning) {
      logger.warn(chalk.yellow('Analysis already in progress, skipping...'));
      return;
    }

    this.isRunning = true;
    
    try {
      logger.info(chalk.cyan('📈 Starting analysis cycle...'));
      
      // Step 1: Parse log file
      const logData = await this.logParser.parseLogFile(this.logFilePath);
      
      if (!logData || logData.length === 0) {
        logger.warn(chalk.yellow('No valid log data found'));
        return;
      }

      // Step 2: Get latest market data
      const latestData = this.logParser.getLatestMarketData(logData);
      
      if (!latestData.currentPrice) {
        logger.warn(chalk.yellow('No current price data available'));
        return;
      }

      // Step 3: Analyze with Gemini AI
      const aiAnalysis = await this.geminiAnalyzer.analyzeTrends(latestData);
      
      // Step 4: Generate trading signals
      const signals = await this.signalGenerator.generateSignals(
        latestData,
        aiAnalysis
      );

      // Step 5: Save signals to JSON
      await this.saveSignals(signals);
      
      // Log summary
      this.logSignalSummary(signals);
      
    } catch (error) {
      logger.error(chalk.red('Error during analysis:', error));
    } finally {
      this.isRunning = false;
    }
  }

  async saveSignals(signals) {
    try {
      const existingSignals = await this.loadExistingSignals();
      
      // Add timestamp to new signals
      const timestampedSignals = {
        ...signals,
        timestamp: new Date().toISOString(),
        id: `signal_${Date.now()}`
      };

      // Maintain history (keep last 100 signals)
      existingSignals.push(timestampedSignals);
      if (existingSignals.length > 100) {
        existingSignals.shift();
      }

      // Save to file
      const output = {
        latest: timestampedSignals,
        history: existingSignals,
        statistics: this.calculateStatistics(existingSignals)
      };

      await fs.writeJson(this.outputPath, output, { spaces: 2 });
      logger.info(chalk.green(`✅ Signals saved to ${this.outputPath}`));
      
    } catch (error) {
      logger.error(chalk.red('Error saving signals:', error));
    }
  }

  async loadExistingSignals() {
    try {
      if (await fs.pathExists(this.outputPath)) {
        const data = await fs.readJson(this.outputPath);
        return data.history || [];
      }
    } catch (error) {
      logger.warn(chalk.yellow('Could not load existing signals'));
    }
    return [];
  }

  calculateStatistics(signals) {
    const validSignals = signals.filter(s => s.action !== 'HOLD');
    
    return {
      totalSignals: signals.length,
      buySignals: signals.filter(s => s.action === 'BUY').length,
      sellSignals: signals.filter(s => s.action === 'SELL').length,
      holdSignals: signals.filter(s => s.action === 'HOLD').length,
      averageConfidence: validSignals.length > 0
        ? validSignals.reduce((sum, s) => sum + s.confidence, 0) / validSignals.length
        : 0,
      lastUpdate: new Date().toISOString()
    };
  }

  logSignalSummary(signal) {
    console.log(chalk.cyan('\n' + '='.repeat(50)));
    console.log(chalk.white.bold('📊 SIGNAL SUMMARY'));
    console.log(chalk.cyan('='.repeat(50)));
    
    const actionColor = signal.action === 'BUY' ? chalk.green :
                       signal.action === 'SELL' ? chalk.red :
                       chalk.yellow;
    
    console.log(chalk.white(`Symbol: ${chalk.bold(signal.symbol)}`));
    console.log(chalk.white(`Action: ${actionColor.bold(signal.action)}`));
    console.log(chalk.white(`Current Price: ${chalk.bold(`$${signal.currentPrice}`)}`));
    
    if (signal.action !== 'HOLD') {
      console.log(chalk.white(`Entry: ${chalk.bold(`$${signal.entry}`)}`));
      console.log(chalk.green(`Take Profit: ${chalk.bold(`$${signal.takeProfit}`)} (${signal.tpPercentage}%)`));
      console.log(chalk.red(`Stop Loss: ${chalk.bold(`$${signal.stopLoss}`)} (${signal.slPercentage}%)`));
      console.log(chalk.white(`Risk/Reward: ${chalk.bold(signal.riskReward)}`));
    }
    
    console.log(chalk.white(`Confidence: ${this.getConfidenceBar(signal.confidence)}`));
    console.log(chalk.white(`Reasoning: ${signal.reasoning}`));
    console.log(chalk.cyan('='.repeat(50) + '\n'));
  }

  getConfidenceBar(confidence) {
    const filled = Math.round(confidence / 10);
    const empty = 10 - filled;
    const bar = '█'.repeat(filled) + '░'.repeat(empty);
    
    const color = confidence >= 80 ? chalk.green :
                  confidence >= 60 ? chalk.yellow :
                  chalk.red;
    
    return `${color(bar)} ${chalk.bold(confidence + '%')}`;
  }

  async startBot() {
    const initialized = await this.initialize();
    
    if (!initialized) {
      logger.error(chalk.red('Failed to initialize bot'));
      return;
    }

    // Run initial analysis
    await this.analyzeAndGenerateSignals();

    // Schedule periodic analysis
    const interval = parseInt(process.env.REFRESH_INTERVAL) || 5000;
    
    logger.info(chalk.green(`⏰ Scheduling analysis every ${interval/1000} seconds`));
    
    setInterval(async () => {
      await this.analyzeAndGenerateSignals();
    }, interval);

    // Watch log file for changes (optional)
    this.watchLogFile();
  }

  watchLogFile() {
    if (!fs.existsSync(this.logFilePath)) {
      logger.warn(chalk.yellow(`Log file not found: ${this.logFilePath}`));
      return;
    }

    fs.watchFile(this.logFilePath, async (curr, prev) => {
      if (curr.mtime > prev.mtime) {
        logger.info(chalk.blue('📝 Log file updated, triggering analysis...'));
        await this.analyzeAndGenerateSignals();
      }
    });

    logger.info(chalk.green('👁️ Watching log file for changes'));
  }
}

// Start the bot
const bot = new TradingBot();

// Handle graceful shutdown
process.on('SIGINT', () => {
  logger.info(chalk.yellow('\n👋 Shutting down gracefully...'));
  process.exit(0);
});

// Start
bot.startBot().catch(error => {
  logger.error(chalk.red('Fatal error:', error));
  process.exit(1);
});
```

## 4. Log Parser (lib/logParser.js)

```javascript
import fs from 'fs-extra';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class LogParser {
  constructor() {
    this.indicatorPatterns = {
      currentPrice: /Current Price:\s*([\d.]+)/,
      ema_short: /EMA_Short:\s*([\d.]+)/,
      ema_long: /EMA_Long:\s*([\d.]+)/,
      rsi: /RSI:\s*([\d.]+)/,
      macd_line: /MACD_Line:\s*([-\d.]+)/,
      macd_signal: /MACD_Signal:\s*([-\d.]+)/,
      macd_hist: /MACD_Hist:\s*([-\d.]+)/,
      bb_upper: /BB_Upper:\s*([\d.]+)/,
      bb_middle: /BB_Middle:\s*([\d.]+)/,
      bb_lower: /BB_Lower:\s*([\d.]+)/,
      atr: /ATR:\s*([\d.]+)/,
      adx: /ADX:\s*([\d.]+)/,
      stochRsi_k: /StochRSI_K:\s*([\d.]+)/,
      stochRsi_d: /StochRSI_D:\s*([\d.]+)/,
      vwap: /VWAP:\s*([\d.]+)/,
      obv: /OBV:\s*([-\d.]+)/,
      mfi: /MFI:\s*([\d.]+)/,
      cci: /CCI:\s*([-\d.]+)/,
      symbol: /Symbol:\s*([A-Z]+USDT)/,
      signal: /Final Signal:\s*(\w+)/,
      score: /Score:\s*([-\d.]+)/
    };

    this.trendPatterns = {
      '3_ema': /3_ema:\s*(\w+)/,
      '15_ema': /15_ema:\s*(\w+)/,
      '3_supertrend': /3_ehlers_supertrend:\s*(\w+)/,
      '15_supertrend': /15_ehlers_supertrend:\s*(\w+)/
    };
  }

  async parseLogFile(filePath) {
    try {
      if (!await fs.pathExists(filePath)) {
        logger.error(chalk.red(`Log file not found: ${filePath}`));
        return null;
      }

      const content = await fs.readFile(filePath, 'utf-8');
      const lines = content.split('\n');
      
      logger.info(chalk.blue(`Parsing ${lines.length} lines from log file`));
      
      return this.extractMarketData(lines);
      
    } catch (error) {
      logger.error(chalk.red('Error parsing log file:', error));
      return null;
    }
  }

  extractMarketData(lines) {
    const dataPoints = [];
    let currentDataPoint = {};
    let isCapturingIndicators = false;

    for (const line of lines) {
      // Check for new data block
      if (line.includes('Current Market Data & Indicators')) {
        if (Object.keys(currentDataPoint).length > 0) {
          dataPoints.push(currentDataPoint);
        }
        currentDataPoint = { timestamp: this.extractTimestamp(line) };
        isCapturingIndicators = true;
      }

      // Extract indicators
      if (isCapturingIndicators) {
        for (const [key, pattern] of Object.entries(this.indicatorPatterns)) {
          const match = line.match(pattern);
          if (match) {
            currentDataPoint[key] = parseFloat(match[1]) || match[1];
          }
        }

        // Extract trends
        for (const [key, pattern] of Object.entries(this.trendPatterns)) {
          const match = line.match(pattern);
          if (match) {
            currentDataPoint[key] = match[1];
          }
        }
      }

      // Check for end of indicators section
      if (line.includes('Multi-Timeframe Trends')) {
        isCapturingIndicators = true;
      }
      
      if (line.includes('Analysis Loop Finished')) {
        isCapturingIndicators = false;
      }
    }

    // Add last data point
    if (Object.keys(currentDataPoint).length > 0) {
      dataPoints.push(currentDataPoint);
    }

    logger.info(chalk.green(`Extracted ${dataPoints.length} data points`));
    return dataPoints;
  }

  extractTimestamp(line) {
    const match = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
    return match ? match[1] : new Date().toISOString();
  }

  getLatestMarketData(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};
    
    const latest = dataPoints[dataPoints.length - 1];
    const previous = dataPoints.length > 1 ? dataPoints[dataPoints.length - 2] : latest;
    
    // Calculate additional metrics
    const priceChange = latest.currentPrice - previous.currentPrice;
    const priceChangePercent = (priceChange / previous.currentPrice) * 100;
    
    return {
      ...latest,
      priceChange,
      priceChangePercent,
      dataPoints: dataPoints.slice(-10) // Last 10 data points for trend analysis
    };
  }
}
```

## 5. Gemini Analyzer (lib/geminiAnalyzer.js)

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class GeminiAnalyzer {
  constructor(apiKey) {
    if (!apiKey) {
      throw new Error('Gemini API key is required');
    }
    
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-pro" });
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
```

## 6. Signal Generator (lib/signalGenerator.js)

```javascript
import chalk from 'chalk';
import { logger } from './utils.js';

export default class SignalGenerator {
  constructor() {
    this.riskPercentage = parseFloat(process.env.RISK_PERCENTAGE) || 1;
    this.minConfidence = 60;
    this.defaultRiskReward = 2;
  }

  async generateSignals(marketData, aiAnalysis) {
    try {
      const symbol = marketData.symbol || 'TRUMPUSDT';
      const currentPrice = marketData.currentPrice;
      
      logger.info(chalk.blue('🎯 Generating trading signals...'));
      
      // Determine action based on AI analysis and confidence
      let action = aiAnalysis.action;
      const confidence = aiAnalysis.confidence;
      
      // Override to HOLD if confidence is too low
      if (confidence < this.minConfidence && action !== 'HOLD') {
        logger.warn(chalk.yellow(`Confidence too low (${confidence}%), changing to HOLD`));
        action = 'HOLD';
      }

      // Generate signal based on action
      let signal = {
        symbol,
        currentPrice,
        action,
        confidence,
        reasoning: aiAnalysis.reasoning,
        keyFactors: aiAnalysis.keyFactors,
        riskLevel: aiAnalysis.riskLevel,
        trend: aiAnalysis.trend,
        trendStrength: aiAnalysis.strength
      };

      // Add entry, SL, TP for BUY/SELL signals
      if (action === 'BUY' || action === 'SELL') {
        const tradeSetup = this.calculateTradeSetup(
          currentPrice,
          action,
          marketData,
          aiAnalysis
        );
        signal = { ...signal, ...tradeSetup };
      }

      return signal;
      
    } catch (error) {
      logger.error(chalk.red('Error generating signals:', error));
      return this.getDefaultSignal(marketData);
    }
  }

  calculateTradeSetup(currentPrice, action, marketData, aiAnalysis) {
    const atr = marketData.atr || currentPrice * 0.002; // Default 0.2% if no ATR
    const riskReward = this.calculateRiskReward(aiAnalysis.confidence);
    
    let entry, stopLoss, takeProfit;
    
    if (action === 'BUY') {
      // For BUY signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'BUY', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'BUY');
      
    } else if (action === 'SELL') {
      // For SELL signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'SELL', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'SELL');
    }

    // Calculate percentages
    const slPercentage = Math.abs((stopLoss - entry) / entry * 100);
    const tpPercentage = Math.abs((takeProfit - entry) / entry * 100);
    
    return {
      entry: this.roundPrice(entry),
      stopLoss: this.roundPrice(stopLoss),
      takeProfit: this.roundPrice(takeProfit),
      riskReward: riskReward.toFixed(2),
      slPercentage: slPercentage.toFixed(2),
      tpPercentage: tpPercentage.toFixed(2),
      positionSize: this.calculatePositionSize(entry, stopLoss),
      entryStrategy: aiAnalysis.entryStrategy,
      exitStrategy: aiAnalysis.exitStrategy
    };
  }

  calculateStopLoss(entry, atr, action, marketData) {
    // Use multiple factors for stop loss
    let stopDistance = atr * 1.5; // 1.5x ATR as base
    
    // Adjust based on volatility
    if (marketData.adx > 40) {
      stopDistance *= 1.2; // Wider stop for strong trends
    }
    
    // Consider Bollinger Bands
    if (action === 'BUY' && marketData.bb_lower) {
      const bbStop = entry - (entry - marketData.bb_lower) * 0.5;
      return Math.min(entry - stopDistance, bbStop);
    } else if (action === 'SELL' && marketData.bb_upper) {
      const bbStop = entry + (marketData.bb_upper - entry) * 0.5;
      return Math.max(entry + stopDistance, bbStop);
    }
    
    return action === 'BUY' ? entry - stopDistance : entry + stopDistance;
  }

  calculateTakeProfit(entry, stopLoss, riskReward, action) {
    const risk = Math.abs(entry - stopLoss);
    const reward = risk * riskReward;
    
    return action === 'BUY' ? entry + reward : entry - reward;
  }

  calculateRiskReward(confidence) {
    // Higher confidence = higher risk/reward ratio
    if (confidence >= 80) return 3;
    if (confidence >= 70) return 2.5;
    if (confidence >= 60) return 2;
    return 1.5;
  }

  calculatePositionSize(entry, stopLoss) {
    // Calculate position size based on risk percentage
    const accountBalance = 1000; // Default account balance
    const riskAmount = accountBalance * (this.riskPercentage / 100);
    const stopLossDistance = Math.abs(entry - stopLoss);
    const positionSize = riskAmount / stopLossDistance;
    
    return {
      units: this.roundSize(positionSize),
      riskAmount: riskAmount.toFixed(2),
      notionalValue: (positionSize * entry).toFixed(2)
    };
  }

  roundPrice(price) {
    // Round to appropriate decimal places based on price level
    if (price < 1) return parseFloat(price.toFixed(4));
    if (price < 10) return parseFloat(price.toFixed(3));
    if (price < 100) return parseFloat(price.toFixed(2));
    return parseFloat(price.toFixed(1));
  }

  roundSize(size) {
    if (size < 1) return parseFloat(size.toFixed(4));
    if (size < 10) return parseFloat(size.toFixed(2));
    return Math.round(size);
  }

  getDefaultSignal(marketData) {
    return {
      symbol: marketData.symbol || 'UNKNOWN',
      currentPrice: marketData.currentPrice || 0,
      action: 'HOLD',
      confidence: 0,
      reasoning: 'Unable to generate signal due to insufficient data',
      keyFactors: ['Error in signal generation'],
      riskLevel: 'HIGH',
      trend: 'UNKNOWN',
      trendStrength: 0
    };
  }
}
```

## 7. Utilities (lib/utils.js)

```javascript
import winston from 'winston';
import chalk from 'chalk';

// Configure logger
export const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    winston.format.errors({ stack: true }),
    winston.format.splat(),
    winston.format.json()
  ),
  defaultMeta: { service: 'trading-bot' },
  transports: [
    new winston.transports.File({ 
      filename: 'logs/error.log', 
      level: 'error' 
    }),
    new winston.transports.File({ 
      filename: 'logs/combined.log' 
    }),
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Utility functions
export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const formatNumber = (num, decimals = 2) => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(num);
};

export const calculatePercentageChange = (oldValue, newValue) => {
  return ((newValue - oldValue) / oldValue) * 100;
};

export const isMarketOpen = () => {
  // Add your market hours logic here
  // For crypto, markets are always open
  return true;
};

export const validateSignal = (signal) => {
  const required = ['symbol', 'currentPrice', 'action', 'confidence'];
  
  for (const field of required) {
    if (!signal[field]) {
      logger.error(chalk.red(`Invalid signal: missing ${field}`));
      return false;
    }
  }
  
  if (signal.action !== 'HOLD') {
    const tradeFields = ['entry', 'stopLoss', 'takeProfit'];
    for (const field of tradeFields) {
      if (!signal[field]) {
        logger.error(chalk.red(`Invalid trade signal: missing ${field}`));
        return false;
      }
    }
  }
  
  return true;
};
```

## 8. Sample Output (signals.json)

```json
{
  "latest": {
    "symbol": "TRUMPUSDT",
    "currentPrice": 8.626,
    "action": "BUY",
    "confidence": 75,
    "reasoning": "Strong bullish momentum detected with RSI showing oversold recovery, MACD turning positive, and price bouncing off lower Bollinger Band. Multi-timeframe alignment suggests upward movement.",
    "keyFactors": [
      "RSI bouncing from oversold",
      "MACD bullish crossover",
      "Price at Bollinger Band support"
    ],
    "riskLevel": "MEDIUM",
    "trend": "BULLISH",
    "trendStrength": 72,
    "entry": 8.626,
    "stopLoss": 8.595,
    "takeProfit": 8.704,
    "riskReward": "2.50",
    "slPercentage": "0.36",
    "tpPercentage": "0.90",
    "positionSize": {
      "units": 32.26,
      "riskAmount": "10.00",
      "notionalValue": "278.27"
    },
    "entryStrategy": "Enter on confirmation of support bounce with increasing volume",
    "exitStrategy": "Take partial profits at first resistance, trail stop for remaining position",
    "timestamp": "2024-08-31T19:15:30.123Z",
    "id": "signal_1693594530123"
  },
  "history": [
    {
      "symbol": "TRUMPUSDT",
      "currentPrice": 8.607,
      "action": "HOLD",
      "confidence": 45,
      "reasoning": "Mixed signals with no clear directional bias",
      "timestamp": "2024-08-31T19:10:25.456Z"
    }
  ],
  "statistics": {
    "totalSignals": 2,
    "buySignals": 1,
    "sellSignals": 0,
    "holdSignals": 1,
    "averageConfidence": 75,
    "lastUpdate": "2024-08-31T19:15:30.123Z"
  }
}
```

## How to Run:

1. **Install dependencies:**
```bash
npm install
```

2. **Set up your Gemini API key in .env file**

3. **Place your log file in the specified path**

4. **Run the bot:**
```bash
npm start
```

## Features:

- **Real-time log parsing** with indicator extraction
- **AI-powered trend analysis** using Google Gemini
- **Smart signal generation** with risk management
- **Automatic position sizing** based on risk percentage
- **Multi-timeframe analysis** support
- **Comprehensive JSON output** with all trading parameters
- **Signal history tracking** and statistics
- **Color-coded console output** for easy monitoring
- **File watching** for automatic updates when logs change

The bot continuously monitors the log file, analyzes market data using Gemini AI, and generates actionable scalping signals with proper risk management parameters.

I'll create a comprehensive Node.js bot that leverages Google's Gemini API for trend analysis and generates scalping signals based on log data. Here's the complete implementation:

## Project Structure

```
trading-bot/
├── package.json
├── .env
├── index.js
├── lib/
│   ├── logParser.js
│   ├── geminiAnalyzer.js
│   ├── signalGenerator.js
│   └── utils.js
└── output/
    └── signals.json
```

## 1. Package.json

```json
{
  "name": "gemini-scalping-bot",
  "version": "1.0.0",
  "description": "Trading bot using Gemini API for trend analysis",
  "main": "index.js",
  "type": "module",
  "scripts": {
    "start": "node index.js",
    "dev": "nodemon index.js"
  },
  "dependencies": {
    "@google/generative-ai": "^0.17.0",
    "dotenv": "^16.3.1",
    "fs-extra": "^11.2.0",
    "chalk": "^5.3.0",
    "winston": "^3.11.0",
    "node-cron": "^3.0.3",
    "axios": "^1.6.2"
  },
  "devDependencies": {
    "nodemon": "^3.0.2"
  }
}
```

## 2. Environment Variables (.env)

```env
GEMINI_API_KEY=your_gemini_api_key_here
LOG_FILE_PATH=./logs/trading.log
OUTPUT_PATH=./output/signals.json
REFRESH_INTERVAL=5000
RISK_PERCENTAGE=1
```

## 3. Main Bot (index.js)

```javascript
import dotenv from 'dotenv';
import cron from 'node-cron';
import chalk from 'chalk';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import LogParser from './lib/logParser.js';
import GeminiAnalyzer from './lib/geminiAnalyzer.js';
import SignalGenerator from './lib/signalGenerator.js';
import { logger } from './lib/utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

class TradingBot {
  constructor() {
    this.logParser = new LogParser();
    this.geminiAnalyzer = new GeminiAnalyzer(process.env.GEMINI_API_KEY);
    this.signalGenerator = new SignalGenerator();
    this.outputPath = process.env.OUTPUT_PATH || './output/signals.json';
    this.logFilePath = process.env.LOG_FILE_PATH || './logs/trading.log';
    this.isRunning = false;
  }

  async initialize() {
    try {
      // Ensure output directory exists
      await fs.ensureDir(path.dirname(this.outputPath));
      
      logger.info(chalk.green('🚀 Trading Bot Initialized'));
      logger.info(chalk.blue(`📊 Log file: ${this.logFilePath}`));
      logger.info(chalk.blue(`📁 Output: ${this.outputPath}`));
      
      return true;
    } catch (error) {
      logger.error(chalk.red('Initialization failed:', error));
      return false;
    }
  }

  async analyzeAndGenerateSignals() {
    if (this.isRunning) {
      logger.warn(chalk.yellow('Analysis already in progress, skipping...'));
      return;
    }

    this.isRunning = true;
    
    try {
      logger.info(chalk.cyan('📈 Starting analysis cycle...'));
      
      // Step 1: Parse log file
      const logData = await this.logParser.parseLogFile(this.logFilePath);
      
      if (!logData || logData.length === 0) {
        logger.warn(chalk.yellow('No valid log data found'));
        return;
      }

      // Step 2: Get latest market data
      const latestData = this.logParser.getLatestMarketData(logData);
      
      if (!latestData.currentPrice) {
        logger.warn(chalk.yellow('No current price data available'));
        return;
      }

      // Step 3: Analyze with Gemini AI
      const aiAnalysis = await this.geminiAnalyzer.analyzeTrends(latestData);
      
      // Step 4: Generate trading signals
      const signals = await this.signalGenerator.generateSignals(
        latestData,
        aiAnalysis
      );

      // Step 5: Save signals to JSON
      await this.saveSignals(signals);
      
      // Log summary
      this.logSignalSummary(signals);
      
    } catch (error) {
      logger.error(chalk.red('Error during analysis:', error));
    } finally {
      this.isRunning = false;
    }
  }

  async saveSignals(signals) {
    try {
      const existingSignals = await this.loadExistingSignals();
      
      // Add timestamp to new signals
      const timestampedSignals = {
        ...signals,
        timestamp: new Date().toISOString(),
        id: `signal_${Date.now()}`
      };

      // Maintain history (keep last 100 signals)
      existingSignals.push(timestampedSignals);
      if (existingSignals.length > 100) {
        existingSignals.shift();
      }

      // Save to file
      const output = {
        latest: timestampedSignals,
        history: existingSignals,
        statistics: this.calculateStatistics(existingSignals)
      };

      await fs.writeJson(this.outputPath, output, { spaces: 2 });
      logger.info(chalk.green(`✅ Signals saved to ${this.outputPath}`));
      
    } catch (error) {
      logger.error(chalk.red('Error saving signals:', error));
    }
  }

  async loadExistingSignals() {
    try {
      if (await fs.pathExists(this.outputPath)) {
        const data = await fs.readJson(this.outputPath);
        return data.history || [];
      }
    } catch (error) {
      logger.warn(chalk.yellow('Could not load existing signals'));
    }
    return [];
  }

  calculateStatistics(signals) {
    const validSignals = signals.filter(s => s.action !== 'HOLD');
    
    return {
      totalSignals: signals.length,
      buySignals: signals.filter(s => s.action === 'BUY').length,
      sellSignals: signals.filter(s => s.action === 'SELL').length,
      holdSignals: signals.filter(s => s.action === 'HOLD').length,
      averageConfidence: validSignals.length > 0
        ? validSignals.reduce((sum, s) => sum + s.confidence, 0) / validSignals.length
        : 0,
      lastUpdate: new Date().toISOString()
    };
  }

  logSignalSummary(signal) {
    console.log(chalk.cyan('\n' + '='.repeat(50)));
    console.log(chalk.white.bold('📊 SIGNAL SUMMARY'));
    console.log(chalk.cyan('='.repeat(50)));
    
    const actionColor = signal.action === 'BUY' ? chalk.green :
                       signal.action === 'SELL' ? chalk.red :
                       chalk.yellow;
    
    console.log(chalk.white(`Symbol: ${chalk.bold(signal.symbol)}`));
    console.log(chalk.white(`Action: ${actionColor.bold(signal.action)}`));
    console.log(chalk.white(`Current Price: ${chalk.bold(`$${signal.currentPrice}`)}`));
    
    if (signal.action !== 'HOLD') {
      console.log(chalk.white(`Entry: ${chalk.bold(`$${signal.entry}`)}`));
      console.log(chalk.green(`Take Profit: ${chalk.bold(`$${signal.takeProfit}`)} (${signal.tpPercentage}%)`));
      console.log(chalk.red(`Stop Loss: ${chalk.bold(`$${signal.stopLoss}`)} (${signal.slPercentage}%)`));
      console.log(chalk.white(`Risk/Reward: ${chalk.bold(signal.riskReward)}`));
    }
    
    console.log(chalk.white(`Confidence: ${this.getConfidenceBar(signal.confidence)}`));
    console.log(chalk.white(`Reasoning: ${signal.reasoning}`));
    console.log(chalk.cyan('='.repeat(50) + '\n'));
  }

  getConfidenceBar(confidence) {
    const filled = Math.round(confidence / 10);
    const empty = 10 - filled;
    const bar = '█'.repeat(filled) + '░'.repeat(empty);
    
    const color = confidence >= 80 ? chalk.green :
                  confidence >= 60 ? chalk.yellow :
                  chalk.red;
    
    return `${color(bar)} ${chalk.bold(confidence + '%')}`;
  }

  async startBot() {
    const initialized = await this.initialize();
    
    if (!initialized) {
      logger.error(chalk.red('Failed to initialize bot'));
      return;
    }

    // Run initial analysis
    await this.analyzeAndGenerateSignals();

    // Schedule periodic analysis
    const interval = parseInt(process.env.REFRESH_INTERVAL) || 5000;
    
    logger.info(chalk.green(`⏰ Scheduling analysis every ${interval/1000} seconds`));
    
    setInterval(async () => {
      await this.analyzeAndGenerateSignals();
    }, interval);

    // Watch log file for changes (optional)
    this.watchLogFile();
  }

  watchLogFile() {
    if (!fs.existsSync(this.logFilePath)) {
      logger.warn(chalk.yellow(`Log file not found: ${this.logFilePath}`));
      return;
    }

    fs.watchFile(this.logFilePath, async (curr, prev) => {
      if (curr.mtime > prev.mtime) {
        logger.info(chalk.blue('📝 Log file updated, triggering analysis...'));
        await this.analyzeAndGenerateSignals();
      }
    });

    logger.info(chalk.green('👁️ Watching log file for changes'));
  }
}

// Start the bot
const bot = new TradingBot();

// Handle graceful shutdown
process.on('SIGINT', () => {
  logger.info(chalk.yellow('\n👋 Shutting down gracefully...'));
  process.exit(0);
});

// Start
bot.startBot().catch(error => {
  logger.error(chalk.red('Fatal error:', error));
  process.exit(1);
});
```

## 4. Log Parser (lib/logParser.js)

The log parser extracts trading data from log files and prepares it for analysis:

```javascript
import fs from 'fs-extra';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class LogParser {
  constructor() {
    this.indicatorPatterns = {
      currentPrice: /Current Price:\s*([\d.]+)/,
      ema_short: /EMA_Short:\s*([\d.]+)/,
      ema_long: /EMA_Long:\s*([\d.]+)/,
      rsi: /RSI:\s*([\d.]+)/,
      macd_line: /MACD_Line:\s*([-\d.]+)/,
      macd_signal: /MACD_Signal:\s*([-\d.]+)/,
      macd_hist: /MACD_Hist:\s*([-\d.]+)/,
      bb_upper: /BB_Upper:\s*([\d.]+)/,
      bb_middle: /BB_Middle:\s*([\d.]+)/,
      bb_lower: /BB_Lower:\s*([\d.]+)/,
      atr: /ATR:\s*([\d.]+)/,
      adx: /ADX:\s*([\d.]+)/,
      stochRsi_k: /StochRSI_K:\s*([\d.]+)/,
      stochRsi_d: /StochRSI_D:\s*([\d.]+)/,
      vwap: /VWAP:\s*([\d.]+)/,
      obv: /OBV:\s*([-\d.]+)/,
      mfi: /MFI:\s*([\d.]+)/,
      cci: /CCI:\s*([-\d.]+)/,
      symbol: /Symbol:\s*([A-Z]+USDT)/,
      signal: /Final Signal:\s*(\w+)/,
      score: /Score:\s*([-\d.]+)/
    };

    this.trendPatterns = {
      '3_ema': /3_ema:\s*(\w+)/,
      '15_ema': /15_ema:\s*(\w+)/,
      '3_supertrend': /3_ehlers_supertrend:\s*(\w+)/,
      '15_supertrend': /15_ehlers_supertrend:\s*(\w+)/
    };
  }

  async parseLogFile(filePath) {
    try {
      if (!await fs.pathExists(filePath)) {
        logger.error(chalk.red(`Log file not found: ${filePath}`));
        return null;
      }

      const content = await fs.readFile(filePath, 'utf-8');
      const lines = content.split('\n');
      
      logger.info(chalk.blue(`Parsing ${lines.length} lines from log file`));
      
      return this.extractMarketData(lines);
      
    } catch (error) {
      logger.error(chalk.red('Error parsing log file:', error));
      return null;
    }
  }

  extractMarketData(lines) {
    const dataPoints = [];
    let currentDataPoint = {};
    let isCapturingIndicators = false;

    for (const line of lines) {
      // Check for new data block
      if (line.includes('Current Market Data & Indicators')) {
        if (Object.keys(currentDataPoint).length > 0) {
          dataPoints.push(currentDataPoint);
        }
        currentDataPoint = { timestamp: this.extractTimestamp(line) };
        isCapturingIndicators = true;
      }

      // Extract indicators
      if (isCapturingIndicators) {
        for (const [key, pattern] of Object.entries(this.indicatorPatterns)) {
          const match = line.match(pattern);
          if (match) {
            currentDataPoint[key] = parseFloat(match) || match;
          }
        }

        // Extract trends
        for (const [key, pattern] of Object.entries(this.trendPatterns)) {
          const match = line.match(pattern);
          if (match) {
            currentDataPoint[key] = match;
          }
        }
      }

      // Check for end of indicators section
      if (line.includes('Multi-Timeframe Trends')) {
        isCapturingIndicators = true;
      }
      
      if (line.includes('Analysis Loop Finished')) {
        isCapturingIndicators = false;
      }
    }

    // Add last data point
    if (Object.keys(currentDataPoint).length > 0) {
      dataPoints.push(currentDataPoint);
    }

    logger.info(chalk.green(`Extracted ${dataPoints.length} data points`));
    return dataPoints;
  }

  extractTimestamp(line) {
    const match = line.match(/(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})/);
    return match ? match : new Date().toISOString();
  }

  getLatestMarketData(dataPoints) {
    if (!dataPoints || dataPoints.length === 0) return {};
    
    const latest = dataPoints[dataPoints.length - 1];
    const previous = dataPoints.length > 1 ? dataPoints[dataPoints.length - 2] : latest;
    
    // Calculate additional metrics
    const priceChange = latest.currentPrice - previous.currentPrice;
    const priceChangePercent = (priceChange / previous.currentPrice) * 100;
    
    return {
      ...latest,
      priceChange,
      priceChangePercent,
      dataPoints: dataPoints.slice(-10) // Last 10 data points for trend analysis
    };
  }
}
```

## 5. Gemini Analyzer (lib/geminiAnalyzer.js)

This module integrates with Google's Gemini API to analyze market trends using AI:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';
import chalk from 'chalk';
import { logger } from './utils.js';

export default class GeminiAnalyzer {
  constructor(apiKey) {
    if (!apiKey) {
      throw new Error('Gemini API key is required');
    }
    
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-pro" });
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
        const analysis = JSON.parse(jsonMatch);
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
```

## 6. Signal Generator (lib/signalGenerator.js)

This module generates actionable trading signals based on the AI analysis:

```javascript
import chalk from 'chalk';
import { logger } from './utils.js';

export default class SignalGenerator {
  constructor() {
    this.riskPercentage = parseFloat(process.env.RISK_PERCENTAGE) || 1;
    this.minConfidence = 60;
    this.defaultRiskReward = 2;
  }

  async generateSignals(marketData, aiAnalysis) {
    try {
      const symbol = marketData.symbol || 'TRUMPUSDT';
      const currentPrice = marketData.currentPrice;
      
      logger.info(chalk.blue('🎯 Generating trading signals...'));
      
      // Determine action based on AI analysis and confidence
      let action = aiAnalysis.action;
      const confidence = aiAnalysis.confidence;
      
      // Override to HOLD if confidence is too low
      if (confidence < this.minConfidence && action !== 'HOLD') {
        logger.warn(chalk.yellow(`Confidence too low (${confidence}%), changing to HOLD`));
        action = 'HOLD';
      }

      // Generate signal based on action
      let signal = {
        symbol,
        currentPrice,
        action,
        confidence,
        reasoning: aiAnalysis.reasoning,
        keyFactors: aiAnalysis.keyFactors,
        riskLevel: aiAnalysis.riskLevel,
        trend: aiAnalysis.trend,
        trendStrength: aiAnalysis.strength
      };

      // Add entry, SL, TP for BUY/SELL signals
      if (action === 'BUY' || action === 'SELL') {
        const tradeSetup = this.calculateTradeSetup(
          currentPrice,
          action,
          marketData,
          aiAnalysis
        );
        signal = { ...signal, ...tradeSetup };
      }

      return signal;
      
    } catch (error) {
      logger.error(chalk.red('Error generating signals:', error));
      return this.getDefaultSignal(marketData);
    }
  }

  calculateTradeSetup(currentPrice, action, marketData, aiAnalysis) {
    const atr = marketData.atr || currentPrice * 0.002; // Default 0.2% if no ATR
    const riskReward = this.calculateRiskReward(aiAnalysis.confidence);
    
    let entry, stopLoss, takeProfit;
    
    if (action === 'BUY') {
      // For BUY signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'BUY', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'BUY');
      
    } else if (action === 'SELL') {
      // For SELL signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'SELL', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'SELL');
    }

    // Calculate percentages
    const slPercentage = Math.abs((stopLoss - entry) / entry * 100);
    const tpPercentage = Math.abs((takeProfit - entry) / entry * 100);
    
    return {
      entry: this.roundPrice(entry),
      stopLoss: this.roundPrice(stopLoss),
      takeProfit: this.roundPrice(takeProfit),
      riskReward: riskReward.toFixed(2),
      slPercentage: slPercentage.toFixed(2),
      tpPercentage: tpPercentage.toFixed(2),
      positionSize: this.calculatePositionSize(entry, stopLoss),
      entryStrategy: aiAnalysis.entryStrategy,
      exitStrategy: aiAnalysis.exitStrategy
    };
  }

  calculateStopLoss(entry, atr, action, marketData) {
    // Use multiple factors for stop loss
    let stopDistance = atr * 1.5; // 1.5x ATR as base
    
    // Adjust based on volatility
    if (marketData.adx > 40) {
      stopDistance *= 1.2; // Wider stop for strong trends
    }
    
    // Consider Bollinger Bands
    if (action === 'BUY' && marketData.bb_lower) {
      const bbStop = entry - (entry - marketData.bb_lower) * 0.5;
      return Math.min(entry - stopDistance, bbStop);
    } else if (action === 'SELL' && marketData.bb_upper) {
      const bbStop = entry + (marketData.bb_upper - entry) * 0.5;
      return Math.max(entry + stopDistance, bbStop);
    }
    
    return action === 'BUY' ? entry - stopDistance : entry + stopDistance;
  }

  calculateTakeProfit(entry, stopLoss, riskReward, action) {
    const risk = Math.abs(entry - stopLoss);
    const reward = risk * riskReward;
    
    return action === 'BUY' ? entry + reward : entry - reward;
  }

  calculateRiskReward(confidence) {
    // Higher confidence = higher risk/reward ratio
    if (confidence >= 80) return 3;
    if (confidence >= 70) return 2.5;
    if (confidence >= 60) return 2;
    return 1.5;
  }

  calculatePositionSize(entry, stopLoss) {
    // Calculate position size based on risk percentage
    const accountBalance = 1000; // Default account balance
    const riskAmount = accountBalance * (this.riskPercentage / 100);
    const stopLossDistance = Math.abs(entry - stopLoss);
    const positionSize = riskAmount / stopLossDistance;
    
    return {
      units: this.roundSize(positionSize),
      riskAmount: riskAmount.toFixed(2),
      notionalValue: (positionSize * entry).toFixed(2)
    };
  }

  roundPrice(price) {
    // Round to appropriate decimal places based on price level
    if (price < 1) return parseFloat(price.toFixed(4));
    if (price < 10) return parseFloat(price.toFixed(3));
    if (price < 100) return parseFloat(price.toFixed(2));
    return parseFloat(price.toFixed(1));
  }

  roundSize(size) {
    if (size < 1) return parseFloat(size.toFixed(4));
    if (size < 10) return parseFloat(size.toFixed(2));
    return Math.round(size);
  }

  getDefaultSignal(marketData) {
    return {
      symbol: marketData.symbol || 'UNKNOWN',
      currentPrice: marketData.currentPrice || 0,
      action: 'HOLD',
      confidence: 0,
      reasoning: 'Unable to generate signal due to insufficient data',
      keyFactors: ['Error in signal generation'],
      riskLevel: 'HIGH',
      trend: 'UNKNOWN',
      trendStrength: 0
    };
  }
}
```

## 7. Utilities (lib/utils.js)

```javascript
import winston from 'winston';
import chalk from 'chalk';

// Configure logger
export const logger = winston.createLogger({
  level: 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    winston.format.errors({ stack: true }),
    winston.format.splat(),
    winston.format.json()
  ),
  defaultMeta: { service: 'trading-bot' },
  transports: [
    new winston.transports.File({ 
      filename: 'logs/error.log', 
      level: 'error' 
    }),
    new winston.transports.File({ 
      filename: 'logs/combined.log' 
    }),
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple()
      )
    })
  ]
});

// Utility functions
export const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

export const formatNumber = (num, decimals = 2) => {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  }).format(num);
};

export const calculatePercentageChange = (oldValue, newValue) => {
  return ((newValue - oldValue) / oldValue) * 100;
};

export const isMarketOpen = () => {
  // Add your market hours logic here
  // For crypto, markets are always open
  return true;
};

export const validateSignal = (signal) => {
  const required = ['symbol', 'currentPrice', 'action', 'confidence'];
  
  for (const field of required) {
    if (!signal[field]) {
      logger.error(chalk.red(`Invalid signal: missing ${field}`));
      return false;
    }
  }
  
  if (signal.action !== 'HOLD') {
    const tradeFields = ['entry', 'stopLoss', 'takeProfit'];
    for (const field of tradeFields) {
      if (!signal[field]) {
        logger.error(chalk.red(`Invalid trade signal: missing ${field}`));
        return false;
      }
    }
  }
  
  return true;
};
```

## 8. Sample Output (signals.json)

```json
{
  "latest": {
    "symbol": "TRUMPUSDT",
    "currentPrice": 8.626,
    "action": "BUY",
    "confidence": 75,
    "reasoning": "Strong bullish momentum detected with RSI showing oversold recovery, MACD turning positive, and price bouncing off lower Bollinger Band. Multi-timeframe alignment suggests upward movement.",
    "keyFactors": [
      "RSI bouncing from oversold",
      "MACD bullish crossover",
      "Price at Bollinger Band support"
    ],
    "riskLevel": "MEDIUM",
    "trend": "BULLISH",
    "trendStrength": 72,
    "entry": 8.626,
    "stopLoss": 8.595,
    "takeProfit": 8.704,
    "riskReward": "2.50",
    "slPercentage": "0.36",
    "tpPercentage": "0.90",
    "positionSize": {
      "units": 32.26,
      "riskAmount": "10.00",
      "notionalValue": "278.27"
    },
    "entryStrategy": "Enter on confirmation of support bounce with increasing volume",
    "exitStrategy": "Take partial profits at first resistance, trail stop for remaining position",
    "timestamp": "2024-08-31T19:15:30.123Z",
    "id": "signal_1693594530123"
  },
  "history": [
    {
      "symbol": "TRUMPUSDT",
      "currentPrice": 8.607,
      "action": "HOLD",
      "confidence": 45,
      "reasoning": "Mixed signals with no clear directional bias",
      "timestamp": "2024-08-31T19:10:25.456Z"
    }
  ],
  "statistics": {
    "totalSignals": 2,
    "buySignals": 1,
    "sellSignals": 0,
    "holdSignals": 1,
    "averageConfidence": 75,
    "lastUpdate": "2024-08-31T19:15:30.123Z"
  }
}
```

## How to Run

**1. Install dependencies:**
```bash
npm install
```

**2. Get your Gemini API key from Google AI Studio:**
- Visit https://aistudio.google.com/app/apikey
- Create a new API key
- Add it to your `.env` file

**3. Place your trading log file in the specified path**

**4. Run the bot:**
```bash
npm start
```

## Key Features

- **Real-time log parsing** with comprehensive indicator extraction
- **AI-powered trend analysis** using Google's Gemini Pro model
- **Smart signal generation** with advanced risk management
- **Automatic position sizing** based on configurable risk percentage
- **Multi-timeframe analysis** support for better signal accuracy
- **Comprehensive JSON output** with all trading parameters
- **Signal history tracking** with performance statistics
- **Color-coded console output** for easy monitoring using chalk
- **File watching** for automatic updates when logs change
- **Error handling and retry logic** for reliability

The bot continuously monitors your trading log file, analyzes market data using the Gemini AI API, and generates actionable scalping signals with proper entry points, stop losses, and take profit targets. The AI analysis considers multiple technical indicators, trend alignments across timeframes, and market conditions to provide high-confidence trading signals.


# 10 Upgrades for Trading Bot with Code Snippets

Here are 10 code upgrades to enhance your trading bot with modern AI integration, improved data processing, and better observability:

## 1. Upgrade to Google Generative AI SDK

Replace the legacy `@google/generative-ai` with the new official **Google Generative AI SDK**:

```javascript
// Before (deprecated)
import { GoogleGenerativeAI } from '@google/generative-ai';

// After (recommended)
import { GoogleGenerativeAI } from '@google/generative-ai';

// Initialize with the new SDK structure
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
```

> "The Google Gen AI SDK provides a unified interface to Gemini 2.5 Pro and Gemini 2.0 models through both the Gemini Developer API and the Gemini API on Vertex." 

## 2. Implement AI-Powered Market Analysis with RAG

Enhance trend analysis with Retrieval-Augmented Generation:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';

export class AdvancedGeminiAnalyzer {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeMarketWithRAG(marketData, historicalContext) {
    const prompt = `
      You are an expert cryptocurrency trader with access to both current market data and historical context.
      
      Current Market Data:
      ${JSON.stringify(marketData)}
      
      Historical Context:
      ${JSON.stringify(historicalContext)}
      
      Provide a scalping signal with:
      1. Short-term trend prediction (1-5 minutes)
      2. Entry/Exit points with price targets
      3. Risk assessment based on current volatility
      4. Confirmatory indicators needed before execution
      
      Format as JSON with fields: trend, entry, stopLoss, takeProfit, confidence, keyFactors
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 3. Add Real-time Performance Monitoring

Integrate **N|Solid** for deep Node.js observability with AI-powered insights:

```javascript
// Install: npm install nssolid
import nssolid from 'nssolid';

// Initialize with your N|Solid license
nssolid.start({
  license: process.env.N_SOLID_LICENSE,
  app: 'trading-bot',
  autoInstrument: true
});

// Add AI-powered anomaly detection
nssolid.on('error', (err) => {
  // Send alerts with AI analysis of the error context
  analyzeErrorWithContext(err, getCurrentMarketState());
});

function getCurrentMarketState() {
  // Return current bot state for context in error analysis
  return {
    activeSignals: signalGenerator.getActiveSignals(),
    riskExposure: riskManager.getExposure(),
    lastUpdate: new Date().toISOString()
  };
}
```

> "N|Solid offers AI-powered insights: Heap and CPU profile analysis with AI + RAG (Retrieval-Augmented Generation)." 

## 4. Implement Streaming Data Processing

Upgrade log parsing to handle streaming data with backpressure handling:

```javascript
import fs from 'fs';
import { Transform } from 'stream';

export class StreamingLogParser {
  constructor(logPath) {
    this.logPath = logPath;
    this.parser = this.createParser();
  }

  createParser() {
    return new Transform({
      // Handle chunks of data as they arrive
      transform(chunk, encoding, callback) {
        // Process each line incrementally
        const lines = chunk.toString().split('\n');
        lines.forEach(line => {
          if (line.trim()) {
            this.push(JSON.parse(line));
          }
        });
        callback();
      }
    });
  }

  startProcessing() {
    const logStream = fs.createReadStream(this.logPath, { 
      encoding: 'utf8',
      autoClose: true
    });
    
    // Pipe with backpressure handling
    logStream
      .pipe(this.parser)
      .on('data', this.processData.bind(this))
      .on('error', this.handleError.bind(this));
  }

  processData(data) {
    // Process each log entry as it arrives
    this.extractIndicators(data);
    this.updateAnalytics(data.timestamp);
  }
}
```

## 5. Add Financial Data Validation Layer

Implement AI-powered data validation for trading signals:

```javascript
export class FinancialValidator {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async validateTradingSignal(signal, marketContext) {
    const prompt = `
      You are a financial compliance officer reviewing a trading signal for cryptocurrency scalping.
      
      Trading Signal:
      ${JSON.stringify(signal)}
      
      Market Context:
      ${JSON.stringify(marketContext)}
      
      Evaluate this signal for:
      1. Risk appropriateness given current volatility
      2. Technical validity of the entry/exit points
      3. Market conditions supporting the predicted move
      4. Potential red flags or overconfidence indicators
      
      Respond with JSON: {isValid: boolean, confidence: 0-100, concerns: [string], recommendation: "accept/modify/reject"}
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "AI-extracted metrics and insights can be exported in structured formats, such as JSON, compatible with financial modeling tools." ([An Introduction to Financial Statement Analysis With AI [2025]](https://www.v7labs.com/blog/financial-statement-analysis-with-ai-guide#:~:text=AI-extracted%20metrics%20and%20insights%20can%20be%20exported%20in%20structured%20formats%2C%20such%20as%20JSON%2C%20compatible%20with%20financial%20modeling%20tools))

## 6. Implement Predictive Risk Management

Add machine learning-based risk prediction:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';

export class PredictiveRiskManager {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
    
    this.riskPatterns = {
      high_volatility: ["large price swings", "increasing ATR", "spread expansion"],
      low_liquidity: ["small volume", "large bid-ask spread", "few trades"],
      trend_reversal: ["overbought/oversold", "MACD divergence", "RSI divergence"]
    };
  }

  async predictRisk(signal, marketData) {
    const prompt = `
      Analyze the following market conditions for potential risks to the trading signal:
      
      Trading Signal:
      ${JSON.stringify(signal)}
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Identify any risk patterns from this set:
      ${JSON.stringify(this.riskPatterns)}
      
      For each identified risk pattern:
      1. Rate severity (1-5)
      2. Suggest mitigation strategy
      3. Update risk percentage accordingly
      
      Return JSON with: riskFactors, adjustedRiskPercentage, mitigationStrategies
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 7. Add Multi-Model Ensemble Analysis

Combine multiple AI models for more robust signals:

```javascript
export class EnsembleAnalyzer {
  constructor() {
    // Initialize multiple models with different strengths
    this.models = {
      speed: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-flash" }),
      accuracy: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-pro" }),
      creativity: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-pro-002" })
    };
  }

  async generateEnsembleSignal(marketData) {
    const analysisPromises = Object.entries(this.models).map(([name, model]) => {
      return this.analyzeWithModel(marketData, model, name);
    });
    
    const analyses = await Promise.all(analysisPromises);
    
    // Combine results with weighted scoring
    return this.combineAnalyses(analyses);
  }

  analyzeWithModel(marketData, model, modelType) {
    const prompt = `
      You are ${modelType} model analyzing cryptocurrency market data.
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Provide analysis in JSON format with:
      {
        "model": "${modelType}",
        "trend": "bullish/bearish/neutral",
        "confidence": 0-100,
        "keyFactors": ["factor1", "factor2"],
        "riskLevel": "low/medium/high"
      }
    `;
    
    return model.generateContent(prompt);
  }

  combineAnalyses(analyses) {
    // Implement weighted averaging based on model strengths
    const combined = {
      trend: this.calculateWeightedTrend(analyses),
      confidence: this.calculateAverageConfidence(analyses),
      riskLevel: this.determineRiskLevel(analyses),
      keyFactors: this.extractKeyFactors(analyses)
    };
    
    return combined;
  }
}
```

> "The Google Gen AI SDK provides a unified interface to Gemini 2.5 Pro and Gemini 2.0 models through both the Gemini Developer API and the Gemini API on Vertex." 

## 8. Implement Automated Backtesting

Add AI-powered backtesting with adaptive parameters:

```javascript
export class Backtester {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async autoBacktest(signalGenerator, historicalData) {
    const prompt = `
      You are an expert quantitative researcher optimizing a scalping trading strategy.
      
      Current Strategy Parameters:
      ${JSON.stringify(signalGenerator.getParameters())}
      
      Historical Data Period: ${historicalData.period}
      Asset: ${historicalData.asset}
      
      Analyze the strategy performance and recommend optimizations:
      1. Identify parameter combinations that improve risk-adjusted returns
      2. Detect overfitting patterns in the current strategy
      3. Suggest adaptive parameters for different market conditions
      4. Provide statistical validation of recommended changes
      
      Return JSON with: optimalParameters, performanceMetrics, implementationSteps
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 9. Add Real-time Market Sentiment Analysis

Incorporate social media and news sentiment into trading signals:

```javascript
export class SentimentAnalyzer {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeMarketSentiment(asset) {
    // In a real implementation, this would fetch from news APIs and social media
    const marketData = await this.getMarketData(asset);
    const newsData = await this.getRecentNews(asset);
    const socialData = await this.getSocialMediaSentiment(asset);
    
    const prompt = `
      Analyze market sentiment for ${asset} based on:
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Recent News (last 24h):
      ${JSON.stringify(newsData)}
      
      Social Media Sentiment:
      ${JSON.stringify(socialData)}
      
      Provide sentiment score (1-10) and categorization:
      - Bullish/Neutral/Bearish bias
      - Key drivers of sentiment
      - Contrast between technicals and sentiment
      - Potential impact on short-term price
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 10. Implement Automated Documentation

Add AI-powered documentation generation:

```javascript
export class DocumentationGenerator {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async generateSystemDocumentation(botComponents) {
    const prompt = `
      You are a technical documentation specialist creating comprehensive documentation for a cryptocurrency trading bot.
      
      Bot Components:
      ${JSON.stringify(botComponents)}
      
      Generate documentation with these sections:
      1. System architecture diagram description
      2. Component interaction flowchart
      3. Error handling strategy explanation
      4. Maintenance procedures
      5. Upgrade path for AI models
      
      Format as JSON with markdown content in each field.
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "The ideal AI solution for financial statement analysis should address 


# 10 Upgrades for Trading Bot with Code Snippets

Here are 10 code upgrades to enhance your trading bot with modern AI integration, improved data processing, and better observability:

## 1. Upgrade to Google Generative AI SDK

Replace the legacy `@google/generative-ai` with the new official **Google Generative AI SDK**:

```javascript
// Before (deprecated)
import { GoogleGenerativeAI } from '@google/generative-ai';

// After (recommended)
import { GoogleGenerativeAI } from '@google/generative-ai';

// Initialize with the new SDK structure
const genAI = new GoogleGenerativeAI(process.env.GEMINI_API_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
```

> "The Google Gen AI SDK provides a unified interface to Gemini 2.5 Pro and Gemini 2.0 models through both the Gemini Developer API and the Gemini API on Vertex." 

## 2. Implement AI-Powered Market Analysis with RAG

Enhance trend analysis with Retrieval-Augmented Generation:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';

export class AdvancedGeminiAnalyzer {
  constructor(apiKey) {
    this.genAI = new GoogleGenerativeAI(apiKey);
    this.model = this.genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeMarketWithRAG(marketData, historicalContext) {
    const prompt = `
      You are an expert cryptocurrency trader with access to both current market data and historical context.
      
      Current Market Data:
      ${JSON.stringify(marketData)}
      
      Historical Context:
      ${JSON.stringify(historicalContext)}
      
      Provide a scalping signal with:
      1. Short-term trend prediction (1-5 minutes)
      2. Entry/Exit points with price targets
      3. Risk assessment based on current volatility
      4. Confirmatory indicators needed before execution
      
      Format as JSON with fields: trend, entry, stopLoss, takeProfit, confidence, keyFactors
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 3. Add Real-time Performance Monitoring

Integrate **N|Solid** for deep Node.js observability with AI-powered insights:

```javascript
// Install: npm install nssolid
import nssolid from 'nssolid';

// Initialize with your N|Solid license
nssolid.start({
  license: process.env.N_SOLID_LICENSE,
  app: 'trading-bot',
  autoInstrument: true
});

// Add AI-powered anomaly detection
nssolid.on('error', (err) => {
  // Send alerts with AI analysis of the error context
  analyzeErrorWithContext(err, getCurrentMarketState());
});

function getCurrentMarketState() {
  // Return current bot state for context in error analysis
  return {
    activeSignals: signalGenerator.getActiveSignals(),
    riskExposure: riskManager.getExposure(),
    lastUpdate: new Date().toISOString()
  };
}
```

> "N|Solid offers AI-powered insights: Heap and CPU profile analysis with AI + RAG (Retrieval-Augmented Generation)." 

## 4. Implement Streaming Data Processing

Upgrade log parsing to handle streaming data with backpressure handling:

```javascript
import fs from 'fs';
import { Transform } from 'stream';

export class StreamingLogParser {
  constructor(logPath) {
    this.logPath = logPath;
    this.parser = this.createParser();
  }

  createParser() {
    return new Transform({
      // Handle chunks of data as they arrive
      transform(chunk, encoding, callback) {
        // Process each line incrementally
        const lines = chunk.toString().split('\n');
        lines.forEach(line => {
          if (line.trim()) {
            this.push(JSON.parse(line));
          }
        });
        callback();
      }
    });
  }

  startProcessing() {
    const logStream = fs.createReadStream(this.logPath, { 
      encoding: 'utf8',
      autoClose: true
    });
    
    // Pipe with backpressure handling
    logStream
      .pipe(this.parser)
      .on('data', this.processData.bind(this))
      .on('error', this.handleError.bind(this));
  }

  processData(data) {
    // Process each log entry as it arrives
    this.extractIndicators(data);
    this.updateAnalytics(data.timestamp);
  }
}
```

## 5. Add Financial Data Validation Layer

Implement AI-powered data validation for trading signals:

```javascript
export class FinancialValidator {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async validateTradingSignal(signal, marketContext) {
    const prompt = `
      You are a financial compliance officer reviewing a trading signal for cryptocurrency scalping.
      
      Trading Signal:
      ${JSON.stringify(signal)}
      
      Market Context:
      ${JSON.stringify(marketContext)}
      
      Evaluate this signal for:
      1. Risk appropriateness given current volatility
      2. Technical validity of the entry/exit points
      3. Market conditions supporting the predicted move
      4. Potential red flags or overconfidence indicators
      
      Respond with JSON: {isValid: boolean, confidence: 0-100, concerns: [string], recommendation: "accept/modify/reject"}
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "AI-extracted metrics and insights can be exported in structured formats, such as JSON, compatible with financial modeling tools." ([An Introduction to Financial Statement Analysis With AI [2025]](https://www.v7labs.com/blog/financial-statement-analysis-with-ai-guide#:~:text=AI-extracted%20metrics%20and%20insights%20can%20be%20exported%20in%20structured%20formats%2C%20such%20as%20JSON%2C%20compatible%20with%20financial%20modeling%20tools))

## 6. Implement Predictive Risk Management

Add machine learning-based risk prediction:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';

export class PredictiveRiskManager {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
    
    this.riskPatterns = {
      high_volatility: ["large price swings", "increasing ATR", "spread expansion"],
      low_liquidity: ["small volume", "large bid-ask spread", "few trades"],
      trend_reversal: ["overbought/oversold", "MACD divergence", "RSI divergence"]
    };
  }

  async predictRisk(signal, marketData) {
    const prompt = `
      Analyze the following market conditions for potential risks to the trading signal:
      
      Trading Signal:
      ${JSON.stringify(signal)}
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Identify any risk patterns from this set:
      ${JSON.stringify(this.riskPatterns)}
      
      For each identified risk pattern:
      1. Rate severity (1-5)
      2. Suggest mitigation strategy
      3. Update risk percentage accordingly
      
      Return JSON with: riskFactors, adjustedRiskPercentage, mitigationStrategies
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 7. Add Multi-Model Ensemble Analysis

Combine multiple AI models for more robust signals:

```javascript
export class EnsembleAnalyzer {
  constructor() {
    // Initialize multiple models with different strengths
    this.models = {
      speed: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-flash" }),
      accuracy: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-pro" }),
      creativity: new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
        .getGenerativeModel({ model: "gemini-2.5-pro-002" })
    };
  }

  async generateEnsembleSignal(marketData) {
    const analysisPromises = Object.entries(this.models).map(([name, model]) => {
      return this.analyzeWithModel(marketData, model, name);
    });
    
    const analyses = await Promise.all(analysisPromises);
    
    // Combine results with weighted scoring
    return this.combineAnalyses(analyses);
  }

  analyzeWithModel(marketData, model, modelType) {
    const prompt = `
      You are ${modelType} model analyzing cryptocurrency market data.
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Provide analysis in JSON format with:
      {
        "model": "${modelType}",
        "trend": "bullish/bearish/neutral",
        "confidence": 0-100,
        "keyFactors": ["factor1", "factor2"],
        "riskLevel": "low/medium/high"
      }
    `;
    
    return model.generateContent(prompt);
  }

  combineAnalyses(analyses) {
    // Implement weighted averaging based on model strengths
    const combined = {
      trend: this.calculateWeightedTrend(analyses),
      confidence: this.calculateAverageConfidence(analyses),
      riskLevel: this.determineRiskLevel(analyses),
      keyFactors: this.extractKeyFactors(analyses)
    };
    
    return combined;
  }
}
```

> "The Google Gen AI SDK provides a unified interface to Gemini 2.5 Pro and Gemini 2.0 models through both the Gemini Developer API and the Gemini API on Vertex." 

## 8. Implement Automated Backtesting

Add AI-powered backtesting with adaptive parameters:

```javascript
export class Backtester {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async autoBacktest(signalGenerator, historicalData) {
    const prompt = `
      You are an expert quantitative researcher optimizing a scalping trading strategy.
      
      Current Strategy Parameters:
      ${JSON.stringify(signalGenerator.getParameters())}
      
      Historical Data Period: ${historicalData.period}
      Asset: ${historicalData.asset}
      
      Analyze the strategy performance and recommend optimizations:
      1. Identify parameter combinations that improve risk-adjusted returns
      2. Detect overfitting patterns in the current strategy
      3. Suggest adaptive parameters for different market conditions
      4. Provide statistical validation of recommended changes
      
      Return JSON with: optimalParameters, performanceMetrics, implementationSteps
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 9. Add Real-time Market Sentiment Analysis

Incorporate social media and news sentiment into trading signals:

```javascript
export class SentimentAnalyzer {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeMarketSentiment(asset) {
    // In a real implementation, this would fetch from news APIs and social media
    const marketData = await this.getMarketData(asset);
    const newsData = await this.getRecentNews(asset);
    const socialData = await this.getSocialMediaSentiment(asset);
    
    const prompt = `
      Analyze market sentiment for ${asset} based on:
      
      Market Data:
      ${JSON.stringify(marketData)}
      
      Recent News (last 24h):
      ${JSON.stringify(newsData)}
      
      Social Media Sentiment:
      ${JSON.stringify(socialData)}
      
      Provide sentiment score (1-10) and categorization:
      - Bullish/Neutral/Bearish bias
      - Key drivers of sentiment
      - Contrast between technicals and sentiment
      - Potential impact on short-term price
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 10. Implement Automated Documentation

Add AI-powered documentation generation:

```javascript
export class DocumentationGenerator {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async generateSystemDocumentation(botComponents) {
    const prompt = `
      You are a technical documentation specialist creating comprehensive documentation for a cryptocurrency trading bot.
      
      Bot Components:
      ${JSON.stringify(botComponents)}
      
      Generate documentation with these sections:
      1. System architecture diagram description
      2. Component interaction flowchart
      3. Error handling strategy explanation
      4. Maintenance procedures
      5. Upgrade path for AI models
      
      Format as JSON with markdown content in each field.
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "The ideal AI solution for financial statement analysis should address 
> "AI-extracted metrics and insights can be exported in structured formats, such as JSON, compatible with financial modeling tools." 

## 11. Add Time-Series Forecasting Layer

Integrate **Google Forecast** for price movement predictions:

```javascript
import { GoogleGenerativeAI } from '@google/generative-ai';

export class PriceForecaster {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async predictPriceMovement(historicalData, timeHorizon = '5min') {
    const prompt = `
      You are a quantitative analyst predicting short-term cryptocurrency price movements.
      
      Historical Data (last 24h):
      ${JSON.stringify(historicalData.slice(-100))} // Last 100 data points
      
      Analyze for:
      1. Trend direction and strength
      2. Volatility clustering patterns
      3. Mean reversion opportunities
      4. Momentum continuation signals
      
      For ${timeHorizon} predictions, provide:
      - Probability of upward movement (%)
      - Potential price targets
      - Key support/resistance levels
      - Confidence score (1-100)
      
      Return JSON with fields: probability, targets, supportResistance, confidence
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 12. Implement Dynamic Position Sizing 2.0

Enhance risk management with volatility-adjusted position sizing:

```javascript
// In signalGenerator.js, replace calculatePositionSize with:
calculateDynamicPositionSize(entry, stopLoss, volatility) {
  // Base risk amount as percentage of account
  const accountBalance = 1000;
  const baseRiskAmount = accountBalance * (this.riskPercentage / 100);
  
  // Volatility adjustment factor
  const volatilityFactor = Math.min(1.0 + (volatility - 0.02) * 10, 2.0); // 2x sizing in low volatility
  const riskAmount = baseRiskAmount / volatilityFactor;
  
  // Calculate position size
  const stopLossDistance = Math.abs(entry - stopLoss);
  const positionSize = riskAmount / stopLossDistance;
  
  return {
    units: this.roundSize(positionSize),
    riskAmount: riskAmount.toFixed(2),
    notionalValue: (positionSize * entry).toFixed(2),
    volatilityFactor: volatilityFactor.toFixed(2),
    recommendedRiskPercentage: ((riskAmount / accountBalance) * 100).toFixed(1)
  };
}
```

## 13. Add Circuit Breaker with AI Analysis

Implement intelligent trading halts based on market conditions:

```javascript
export class CircuitBreaker {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async evaluateTradingContinuity(marketConditions) {
    const prompt = `
      You are a market stability officer assessing whether trading should continue or be suspended.
      
      Current Market Conditions:
      ${JSON.stringify(marketConditions)}
      
      Evaluate the need for a circuit breaker using these criteria:
      1. Extreme volatility (ATR > 3%)
      2. Liquidity crunch (bid-ask spread > 2%)
      3. Trend exhaustion signals
      4. Systemic risk indicators
      
      For each criterion:
      - Rate severity (1-5)
      - Provide evidence
      - Recommend action (continue/tradeWithCaution/suspend)
      
      Return JSON with overall recommendation and justification.
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "The Google Gen AI SDK provides a unified interface to Gemini 2.5 Pro and Gemini 2.0 models through both the Gemini Developer API and the Gemini API on Vertex." 

## 14. Implement Adaptive Signal Filtering

Create AI-powered signal validation with dynamic thresholds:

```javascript
export class AdaptiveSignalFilter {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async filterSignal(signal, marketContext, historicalPerformance) {
    const prompt = `
      You are a trading strategy validator analyzing signal reliability.
      
      Signal to Evaluate:
      ${JSON.stringify(signal)}
      
      Current Market Context:
      ${JSON.stringify(marketContext)}
      
      Historical Performance (last 30 days):
      ${JSON.stringify(historicalPerformance)}
      
      Evaluate based on:
      1. Consistency with prevailing market regime
      2. Edge over random walk hypothesis
      3. Win rate and risk-reward expectations
      4. Potential overfitting indicators
      
      Assign reliability score (1-100) and provide recommendations.
      
      Return JSON with: reliabilityScore, confidence, recommendations
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 15. Add Order Book Imbalance Detection

Monitor market structure for hidden liquidity imbalances:

```javascript
export class OrderBookAnalyzer {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async detectOrderBookImbalance(bookData) {
    const prompt = `
      You are a market microstructure analyst detecting hidden order book imbalances.
      
      Order Book Snapshot:
      ${JSON.stringify(bookData)}
      
      Analyze for:
      1. Hidden liquidity pools (iceberg orders)
      2. Spoofing attempts (large orders that disappear)
      3. Liquidity droughts in critical price levels
      4. Market maker behavior patterns
      
      Identify at least 3 significant patterns with:
      - Description
      - Confidence score (1-100)
      - Recommended trading strategy
      
      Return JSON with array of findings.
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

> "AI-extracted metrics and insights can be exported in structured formats, such as JSON, compatible with financial modeling tools." 

## 16. Implement Sentiment-Adjusted Risk Management

Balance technical signals with market sentiment:

```javascript
export class SentimentRiskManager {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async adjustRiskParameters(technicalSignal, sentimentScore, volatility) {
    const prompt = `
      You are a risk manager adjusting position sizing based on market sentiment.
      
      Technical Signal:
      ${JSON.stringify(technicalSignal)}
      
      Sentiment Score (1-10): ${sentimentScore}
      
      Volatility Level: ${volatility.toFixed(2)}
      
      Sentiment categories:
      - 1-3: Bearish
      - 4-7: Neutral
      - 8-10: Bullish
      
      Rules:
      1. Bullish sentiment → increase position size by 25-50%
      2. Bearish sentiment → decrease position size by 25-50%
      3. High volatility → reduce position size proportionally
      4. Contradictory signals → apply 50% risk factor
      
      Calculate adjusted risk parameters and return JSON with:
      - baseRiskPercentage
      - sentimentAdjustment
      - volatilityAdjustment
      - finalRiskPercentage
      - positionSizeMultiplier
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
```

## 17. Add Cross-Asset Correlation Analysis

Monitor relationships between different trading pairs:

```javascript
export class CorrelationAnalyzer {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async analyzeCorrelations(marketData) {
    const prompt = `
      You are a quantitative analyst examining correlations between cryptocurrency assets.
      
      Market Data Structure:
      {
        "timeframe": "1h",
        "assets": 

        import { Transform } from 'stream';

export class StreamingLogProcessor {
  constructor() {
    this.lineParser = new Transform({
      transform(chunk, encoding, callback) {
        // Process each line as it arrives
        const lines = chunk.toString().split('\n');
        lines.forEach(line => {
          if (line.trim()) {
            try {
              this.push(JSON.parse(line));
            } catch (e) {
              console.error('Error parsing log line:', line);
            }
          }
        });
        callback();
      }
    });
  }

  processStream(logStream) {
    return logStream.pipe(this.lineParser);
  }
}

// Usage with file watching
import fs from 'fs';

const processor = new StreamingLogProcessor();
const logStream = fs.createReadStream('trading.log', { encoding: 'utf8' });

processor.processStream(logStream)
  .on('data', (data) => {
    // Process each JSON log entry
    analyzeMarketData(data);
  })
  .on('error', (err) => {
    console.error('Stream processing error:', err);
  });

  ////
  export class DocumentationGenerator {
  constructor() {
    this.model = new GoogleGenerativeAI(process.env.GEMINI_API_KEY)
      .getGenerativeModel({ model: "gemini-2.5-flash" });
  }

  async generateSystemDocumentation(botComponents) {
    const prompt = `
      You are a technical documentation specialist creating comprehensive documentation for a cryptocurrency trading bot.
      
      Bot Components:
      ${JSON.stringify(botComponents)}
      
      Generate documentation with these sections:
      1. System architecture diagram description
      2. Component interaction flowchart
      3. Error handling strategy explanation
      4. Maintenance procedures
      5. Upgrade path for AI models
      
      Format as JSON with markdown content in each field.
    `;
    
    const result = await this.model.generateContent(prompt);
    return JSON.parse(result.response.text());
  }
}
////

