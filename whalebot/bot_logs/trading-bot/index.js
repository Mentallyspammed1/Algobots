import dotenv from 'dotenv';
import cron from 'node-cron';
import chalk from 'chalk';
import fs from 'fs-extra';
import path from 'path';
import { fileURLToPath } from 'url';
import LogParser from './lib/logParser.js';
import GeminiAnalyzer from './lib/geminiAnalyzer.js';
import SignalGenerator from './lib/signalGenerator.js';
import LiveDataFetcher from './lib/liveDataFetcher.js';
import { logger } from './lib/utils.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

dotenv.config({ path: path.join(__dirname, '..', '.env') });

const config = {
  geminiApiKey: process.env.GEMINI_API_KEY,
  tradingSymbol: process.env.TRADING_SYMBOL || 'BCHUSDT',
  liveDataMode: true,
  bybitApiKey: process.env.BYBIT_API_KEY,
  bybitApiSecret: process.env.BYBIT_API_SECRET,
  outputPath: process.env.OUTPUT_PATH || path.join(__dirname, 'output/signals.json'),
  logFilePath: process.env.LOG_FILE_PATH || path.join(__dirname, '..', 'unanimous.log'),
  refreshIntervalMs: parseInt(process.env.REFRESH_INTERVAL_MS || '5000', 10),
  cronSchedule: process.env.CRON_SCHEDULE || '*/5 * * * *',
  signalHistoryLimit: parseInt(process.env.SIGNAL_HISTORY_LIMIT || '100', 10),
  indicatorSettings: {
    atr_period: 12,
    ema_short_period: 8,
    ema_long_period: 22,
    rsi_period: 12,
    stoch_rsi_period: 14,
    stoch_k_period: 3,
    stoch_d_period: 3,
    bollinger_bands_period: 40,
    bollinger_bands_std_dev: 2.0,
    cci_period: 22,
    williams_r_period: 12,
    mfi_period: 14,
    psar_acceleration: 0.02,
    psar_max_acceleration: 0.2,
    sma_short_period: 10,
    sma_long_period: 50,
    fibonacci_window: 60,
    ehlers_fast_period: 10,
    ehlers_fast_multiplier: 2.0,
    ehlers_slow_period: 20,
    ehlers_slow_multiplier: 3.0,
    macd_fast_period: 3,
    macd_slow_period: 40,
    macd_signal_period: 89,
    adx_period: 14,
    ichimoku_tenkan_period: 9,
    ichimoku_kijun_period: 26,
    ichimoku_senkou_span_b_period: 52,
    ichimoku_chikou_span_offset: 26,
    obv_ema_period: 20,
    cmf_period: 20,
    rsi_oversold: 33,
    rsi_overbought: 66,
    stoch_rsi_oversold: 20,
    stoch_rsi_overbought: 80,
    cci_oversold: -100,
    cci_overbought: 100,
    williams_r_oversold: -80,
    williams_r_overbought: -20,
    mfi_oversold: 20,
    mfi_overbought: 80,
    volatility_index_period: 12,
    vwma_period: 20,
    volume_delta_period: 5,
    volume_delta_threshold: 0.2,
    kama_period: 10,
    kama_fast_period: 2,
    kama_slow_period: 12,
  },
  klineInterval: process.env.KLINE_INTERVAL || '15',
  klineLimit: parseInt(process.env.KLINE_LIMIT || '200', 10),
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
    this.logFileWatcher = null;
  }

  async initialize() {
    try {
      logger.info(chalk.magenta('✨ Invoking the bot initialization ritual...'));

      await fs.ensureDir(path.dirname(this.outputPath));

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
      let latestData = {};

      if (config.liveDataMode) {
        const liveDataFetcher = new LiveDataFetcher(config.bybitApiKey, config.bybitApiSecret, config.tradingSymbol);
        const fetchedPriceData = await liveDataFetcher.fetchCurrentPrice();
        const fetchedKlineData = await liveDataFetcher.fetchKlineData(config.klineInterval, config.klineLimit);

        if (!fetchedPriceData || !fetchedPriceData.currentPrice) {
          logger.warn(chalk.yellow('No live market price data available.'));
          return;
        }
        if (!fetchedKlineData || fetchedKlineData.length === 0) {
          logger.warn(chalk.yellow('No live kline data available.'));
          return;
        }

        latestData = {
          currentPrice: fetchedPriceData.currentPrice,
          symbol: fetchedPriceData.symbol,
          klines: fetchedKlineData,
          indicatorSettings: config.indicatorSettings,
        };

      } else {
        const logData = await this.logParser.parseLogFile(this.logFilePath);

        if (!logData || logData.length === 0) {
          logger.warn(chalk.yellow('No valid log data found to analyze.'));
          return;
        }

        latestData = this.logParser.getLatestMarketData(logData);

        if (!latestData || !latestData.currentPrice) {
          logger.warn(chalk.yellow('No current price data available from logs.'));
          return;
        }
        latestData.indicatorSettings = config.indicatorSettings;
      }

      logger.info(chalk.blue('🧠 Consulting the Gemini AI oracle for trend analysis...'));
      const aiAnalysis = await this.geminiAnalyzer.analyzeTrends(latestData);

      if (!aiAnalysis) {
        logger.warn(chalk.yellow('Gemini AI did not return a valid analysis.'));
        return;
      }

      logger.info(chalk.blue('✨ Generating trading signals based on market data and AI insights...'));
      const signals = await this.signalGenerator.generateSignals(
        latestData,
        aiAnalysis
      );

      if (!signals || !signals.action) {
        logger.warn(chalk.yellow('Signal generation failed or produced no actionable signal.'));
        return;
      }

      await this.saveSignals(signals);

      this.logSignalSummary(signals);
      this.lastSuccessfulRun = new Date().toISOString();
      logger.info(chalk.green('✅ Analysis cycle completed successfully.'));

    } catch (error) {
      logger.error(chalk.red(`❌ Error during analysis cycle: ${error.message}`));
      logger.debug(chalk.red(error.stack));
    } finally {
      this.isRunning = false;
    }
  }

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

      const timestampedSignal = {
        ...newSignal,
        timestamp: new Date().toISOString(),
        id: `signal_${Date.now()}`
      };

      existingSignals.push(timestampedSignal);
      if (existingSignals.length > config.signalHistoryLimit) {
        existingSignals.shift();
      }

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
    const bar = '█'.repeat(Math.max(0, filled)) + '░'.repeat(Math.max(0, empty));

    const color = confidence >= 80 ? chalk.green :
                  confidence >= 60 ? chalk.yellow :
                  chalk.red;

    return `${color(bar)} ${chalk.bold(confidence + '%')}`;
  }

  async startBot() {
    const initialized = await this.initialize();

    if (!initialized) {
      logger.error(chalk.red('Failed to initialize bot. Exiting.'));
      process.exit(1);
    }

    await this.analyzeAndGenerateSignals();

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

    this.watchLogFile();
  }

  watchLogFile() {
    if (!fs.existsSync(this.logFilePath)) {
      logger.warn(chalk.yellow(`Log file not found at ${chalk.bold(this.logFilePath)}. Cannot watch for changes.`));
      return;
    }

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

  async shutdown() {
    logger.info(chalk.yellow('\n👋 Initiating graceful shutdown sequence...'));
    if (this.logFileWatcher) {
      fs.unwatchFile(this.logFilePath);
      logger.info(chalk.yellow('🛑 Log file watcher stopped.'));
    }
    logger.info(chalk.yellow('✨ Shutdown complete. May your digital journey be prosperous!'));
    process.exit(0);
  }
}

const bot = new TradingBot(
  new LogParser(config.tradingSymbol),
  new GeminiAnalyzer(config.geminiApiKey, config.tradingSymbol, {
    model: "gemini-2.5-flash-lite",
    retryDelay: 5000 // 5 seconds
  }),
  new SignalGenerator(config.tradingSymbol)
);

process.on('SIGINT', () => bot.shutdown());
process.on('SIGTERM', () => bot.shutdown());

bot.startBot().catch(error => {
  logger.error(chalk.red(`🔥 Fatal disturbance in the code-weave: ${error.message}`));
  logger.error(chalk.red(error.stack));
  process.exit(1);
});
