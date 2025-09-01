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
      buySignals: validSignals.filter(s => s.action === 'BUY').length,
      sellSignals: validSignals.filter(s => s.action === 'SELL').length,
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
