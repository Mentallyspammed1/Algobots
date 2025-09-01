import dotenv from 'dotenv';
import cron from 'node-cron';
import chalk from 'chalk';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import LogParser from './lib/logParser.js';
import GeminiAnalyzer from './lib/geminiAnalyzer.js';
import SignalGenerator from './lib/signalGenerator.js';
import LiveDataFetcher from './lib/liveDataFetcher.js'; // NEW
import { logger } from './lib/utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config();

// Centralized Configuration Vessel
const config = {
  geminiApiKey: process.env.GEMINI_API_KEY,
  tradingSymbol: process.env.TRADING_SYMBOL || 'TRUMPUSDT', // NEW: Centralized trading symbol
  liveDataMode: process.env.LIVE_DATA_MODE === 'true', // NEW: Enable live data fetching
  bybitApiKey: process.env.BYBIT_API_KEY, // NEW: Bybit API Key
  bybitApiSecret: process.env.BYBIT_API_SECRET, // NEW: Bybit API Secret
  outputPath: process.env.OUTPUT_PATH || './output/signals.json',
  logFilePath: process.env.LOG_FILE_PATH || './logs/wgwhalex_bot.log',
  refreshIntervalMs: parseInt(process.env.REFRESH_INTERVAL_MS || '5000', 10), // Milliseconds
  cronSchedule: process.env.CRON_SCHEDULE || '*/5 * * * *', // Every 5 minutes by default
  signalHistoryLimit: parseInt(process.env.SIGNAL_HISTORY_LIMIT || '100', 10),
};

class TradingBot {
  constructor(logParser, geminiAnalyzer, signalGenerator) {
    this.logParser = logParser;
    this.geminiAnalyzer = geminiAnalyzer;
    this.signalGenerator = signalGenerator;
    this.outputPath = config.outputPath;
    this.logFilePath = config.logFilePath;
    this.isRunning = false;
    this.lastSuccessfulRun = null;
    this.logFileWatcher = null; // To store the watcher instance
  }

  async initialize() {
    try {
      logger.info(chalk.magenta('✨ Invoking the bot initialization ritual...'));

      // Ensure output directory exists
      await fs.ensureDir(path.dirname(this.outputPath));

      // Validate essential configurations
      if (!config.geminiApiKey) {
        logger.error(chalk.red('🚫 GEMINI_API_KEY is not set. Aborting initialization.'));
        return false;
      }

      logger.info(chalk.green('🚀 Trading Bot Initialized successfully!'));
      logger.info(chalk.blue(`📊 Log file path: ${chalk.bold(this.logFilePath)}`));
      logger.info(chalk.blue(`📁 Output path: ${chalk.bold(this.outputPath)}`));
      logger.info(chalk.blue(`⏰ Analysis schedule: ${chalk.bold(config.cronSchedule)} (Cron) or ${chalk.bold(config.refreshIntervalMs / 1000 + 's')} (Interval)`));

      return true;
    } catch (error) {
      logger.error(chalk.red(`Initialization failed: ${error.message}`));
      return false;
    }
  }

  async analyzeAndGenerateSignals() {
    if (this.isRunning) {
      logger.warn(chalk.yellow('⚠️ Analysis already in progress, skipping this cycle.'));
      return;
    }

    this.isRunning = true;
    logger.info(chalk.cyan('📈 Starting a new analysis cycle...'));

    try {
      let latestData;

      if (config.liveDataMode) {
        // Step 1 (Live Data Mode): Fetch live market data
        const liveDataFetcher = new LiveDataFetcher(config.bybitApiKey, config.bybitApiSecret, config.tradingSymbol);
        const fetchedData = await liveDataFetcher.fetchCurrentPrice(); // Only fetching current price for POC

        if (!fetchedData || !fetchedData.currentPrice) {
          logger.warn(chalk.yellow('No live market data available.'));
          return;
        }
        latestData = fetchedData;
      } else {
        // Step 1 (Log File Mode): Parse log file
        const logData = await this.logParser.parseLogFile(this.logFilePath);

        if (!logData || logData.length === 0) {
          logger.warn(chalk.yellow('No valid log data found to analyze.'));
          return;
        }

        // Step 2 (Log File Mode): Get latest market data from logs
        latestData = this.logParser.getLatestMarketData(logData);

        if (!latestData || !latestData.currentPrice) {
          logger.warn(chalk.yellow('No current price data available from logs.'));
          return;
        }
      }

      // Step 3: Analyze with Gemini AI
      logger.info(chalk.blue('🧠 Consulting the Gemini AI oracle for trend analysis...'));
      const aiAnalysis = await this.geminiAnalyzer.analyzeTrends(latestData);

      if (!aiAnalysis) {
        logger.warn(chalk.yellow('Gemini AI did not return a valid analysis.'));
        return;
      }

      // Step 4: Generate trading signals
      logger.info(chalk.blue('✨ Generating trading signals based on market data and AI insights...'));
      const signals = await this.signalGenerator.generateSignals(
        latestData,
        aiAnalysis
      );

      if (!signals || !signals.action) {
        logger.warn(chalk.yellow('Signal generation failed or produced no actionable signal.'));
        return;
      }

      // Step 5: Save signals to JSON
      await this.saveSignals(signals);

      // Log summary
      this.logSignalSummary(signals);
      this.lastSuccessfulRun = new Date().toISOString(); // Update last successful run time
      logger.info(chalk.green('✅ Analysis cycle completed successfully.'));

    } catch (error) {
      logger.error(chalk.red(`❌ Error during analysis cycle: ${error.message}`));
      logger.debug(chalk.red(error.stack)); // For detailed debugging
    } finally {
      this.isRunning = false;
    }
  } // finally block is removed here, it will be added back in the next step

  async saveSignals(newSignal) {
    try {
      let existingSignals = [];
      if (await fs.pathExists(this.outputPath)) {
        try {
          const data = await fs.readJson(this.outputPath);
          existingSignals = data.history || [];
        } catch (readError) {
          logger.warn(chalk.yellow(`Could not read existing signals from ${this.outputPath}: ${readError.message}. Starting with empty history.`));
        }
      }

      // Add timestamp and unique ID to new signal
      const timestampedSignal = {
        ...newSignal,
        timestamp: new Date().toISOString(),
        id: `signal_${Date.now()}`
      };

      // Maintain history (keep last N signals)
      existingSignals.push(timestampedSignal);
      if (existingSignals.length > config.signalHistoryLimit) {
        existingSignals.shift(); // Remove the oldest signal
      }

      // Prepare output structure
      const output = {
        latest: timestampedSignal,
        history: existingSignals,
        statistics: this.calculateStatistics(existingSignals),
        lastUpdated: new Date().toISOString(),
        botStatus: {
          isRunning: this.isRunning,
          lastSuccessfulRun: this.lastSuccessfulRun,
        }
      };

      await fs.writeJson(this.outputPath, output, { spaces: 2 });
      logger.info(chalk.green(`✅ Signals forged and saved to ${chalk.bold(this.outputPath)}`));

    } catch (error) {
      logger.error(chalk.red(`❌ Error saving signals: ${error.message}`));
      logger.debug(chalk.red(error.stack));
    }
  }

  calculateStatistics(signals) {
    const validSignals = signals.filter(s => s.action !== 'HOLD');

    const totalSignals = signals.length;
    const buySignals = validSignals.filter(s => s.action === 'BUY').length;
    const sellSignals = validSignals.filter(s => s.action === 'SELL').length;
    const holdSignals = signals.filter(s => s.action === 'HOLD').length;
    const averageConfidence = validSignals.length > 0
      ? validSignals.reduce((sum, s) => sum + s.confidence, 0) / validSignals.length
      : 0;

    return {
      totalSignals,
      buySignals,
      sellSignals,
      holdSignals,
      averageConfidence: parseFloat(averageConfidence.toFixed(2)),
      lastCalculation: new Date().toISOString()
    };
  }

  logSignalSummary(signal) {
    console.log(chalk.cyan('\n' + '='.repeat(50)));
    console.log(chalk.white.bold('📊 SIGNAL SUMMARY'));
    console.log(chalk.cyan('='.repeat(50)));

    const actionColor = signal.action === 'BUY' ? chalk.green :
                       signal.action === 'SELL' ? chalk.red :
                       chalk.yellow;

    console.log(chalk.white(`Symbol: ${chalk.bold(signal.symbol || 'N/A')}`));
    console.log(chalk.white(`Action: ${actionColor.bold(signal.action || 'N/A')}`));
    console.log(chalk.white(`Current Price: ${chalk.bold(`$${signal.currentPrice ? signal.currentPrice.toFixed(2) : 'N/A'}`)}`));

    if (signal.action !== 'HOLD') {
      console.log(chalk.white(`Entry: ${chalk.bold(`$${signal.entry ? signal.entry.toFixed(2) : 'N/A'}`)}`));
      console.log(chalk.green(`Take Profit: ${chalk.bold(`$${signal.takeProfit ? signal.takeProfit.toFixed(2) : 'N/A'}`)} (${signal.tpPercentage ? signal.tpPercentage.toFixed(2) : 'N/A'}%)`));
      console.log(chalk.red(`Stop Loss: ${chalk.bold(`$${signal.stopLoss ? signal.stopLoss.toFixed(2) : 'N/A'}`)} (${signal.slPercentage ? signal.slPercentage.toFixed(2) : 'N/A'}%)`));
      console.log(chalk.white(`Risk/Reward: ${chalk.bold(signal.riskReward || 'N/A')}`));
    }

    console.log(chalk.white(`Confidence: ${this.getConfidenceBar(signal.confidence || 0)}`));
    console.log(chalk.white(`Reasoning: ${signal.reasoning || 'No specific reasoning provided.'}`));
    console.log(chalk.cyan('='.repeat(50) + '\n'));
  }

  getConfidenceBar(confidence) {
    const filled = Math.round(confidence / 10);
    const empty = 10 - filled;
    const bar = '█'.repeat(Math.max(0, filled)) + '░'.repeat(Math.max(0, empty)); // Ensure non-negative repeats

    const color = confidence >= 80 ? chalk.green :
                  confidence >= 60 ? chalk.yellow :
                  chalk.red;

    return `${color(bar)} ${chalk.bold(confidence + '%')}`;
  }

  async startBot() {
    const initialized = await this.initialize();

    if (!initialized) {
      logger.error(chalk.red('Failed to initialize bot. Exiting.'));
      process.exit(1); // Exit if initialization fails
    }

    // Run initial analysis immediately
    await this.analyzeAndGenerateSignals();

    // Schedule periodic analysis using cron or setInterval
    if (config.cronSchedule) {
      logger.info(chalk.green(`⏰ Scheduling analysis via cron: ${chalk.bold(config.cronSchedule)}`));
      cron.schedule(config.cronSchedule, async () => {
        logger.info(chalk.magenta('🔮 Cron job triggered: Initiating scheduled analysis.'));
        await this.analyzeAndGenerateSignals();
      });
    } else {
      logger.info(chalk.green(`⏰ Scheduling analysis every ${chalk.bold(config.refreshIntervalMs / 1000 + ' seconds')} using setInterval.`));
      setInterval(async () => {
        await this.analyzeAndGenerateSignals();
      }, config.refreshIntervalMs);
    }

    // Watch log file for changes
    this.watchLogFile();
  }

  watchLogFile() {
    if (!fs.existsSync(this.logFilePath)) {
      logger.warn(chalk.yellow(`Log file not found at ${chalk.bold(this.logFilePath)}. Cannot watch for changes.`));
      return;
    }

    // Ensure only one watcher is active
    if (this.logFileWatcher) {
      fs.unwatchFile(this.logFilePath);
    }

    this.logFileWatcher = fs.watchFile(this.logFilePath, async (curr, prev) => {
      if (curr.mtime > prev.mtime) {
        logger.info(chalk.blue('📝 Log file updated! Triggering immediate analysis.'));
        await this.analyzeAndGenerateSignals();
      }
    });

    logger.info(chalk.green(`👁️ Watching log file for changes at ${chalk.bold(this.logFilePath)}`));
  }

  // Graceful shutdown
  async shutdown() {
    logger.info(chalk.yellow('\n👋 Initiating graceful shutdown sequence...'));
    if (this.logFileWatcher) {
      fs.unwatchFile(this.logFilePath);
      logger.info(chalk.yellow('🛑 Log file watcher stopped.'));
    }
    // Any other cleanup like closing connections can go here
    logger.info(chalk.yellow('✨ Shutdown complete. May your digital journey be prosperous!'));
    process.exit(0);
  }
}

// Start the bot with dependency injection
const bot = new TradingBot(
  new LogParser(config.tradingSymbol), // Pass trading symbol to LogParser
  new GeminiAnalyzer(config.geminiApiKey, config.tradingSymbol), // Pass trading symbol to GeminiAnalyzer
  new SignalGenerator()
);

// Handle graceful shutdown
process.on('SIGINT', () => bot.shutdown());
process.on('SIGTERM', () => bot.shutdown()); // Also handle SIGTERM

// Invoke the bot's main incantation
bot.startBot().catch(error => {
  logger.error(chalk.red(`🔥 Fatal disturbance in the code-weave: ${error.message}`));
  logger.error(chalk.red(error.stack));
  process.exit(1);
});
