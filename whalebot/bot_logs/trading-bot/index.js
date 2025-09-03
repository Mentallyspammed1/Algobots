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

dotenv.config();

// Centralized Configuration Vessel
const config = {
  geminiApiKey: process.env.GEMINI_API_KEY,
  tradingSymbol: process.env.TRADING_SYMBOL || 'POPCATUSDT',
  liveDataMode: process.env.LIVE_DATA_MODE === 'true',
  bybitApiKey: process.env.BYBIT_API_KEY,
  bybitApiSecret: process.env.BYBIT_API_SECRET,
  outputPath: process.env.OUTPUT_PATH || './output/signals.json',
  logFilePath: process.env.LOG_FILE_PATH || './logs/wgwhalex_bot.log',
  refreshIntervalMs: parseInt(process.env.REFRESH_INTERVAL_MS || '5000', 10),
  cronSchedule: process.env.CRON_SCHEDULE || '*/5 * * * *',
  signalHistoryLimit: parseInt(process.env.SIGNAL_HISTORY_LIMIT || '100', 10),
  // New indicator settings from whalebot.py config.json
  indicatorSettings: {
    atr_period: parseInt(process.env.ATR_PERIOD || '14', 10),
    ema_short_period: parseInt(process.env.EMA_SHORT_PERIOD || '9', 10),
    ema_long_period: parseInt(process.env.EMA_LONG_PERIOD || '21', 10),
    rsi_period: parseInt(process.env.RSI_PERIOD || '14', 10),
    stoch_rsi_period: parseInt(process.env.STOCH_RSI_PERIOD || '14', 10),
    stoch_k_period: parseInt(process.env.STOCH_K_PERIOD || '3', 10),
    stoch_d_period: parseInt(process.env.STOCH_D_PERIOD || '3', 10),
    bollinger_bands_period: parseInt(process.env.BOLLINGER_BANDS_PERIOD || '20', 10),
    bollinger_bands_std_dev: parseFloat(process.env.BOLLINGER_BANDS_STD_DEV || '2.0'),
    cci_period: parseInt(process.env.CCI_PERIOD || '20', 10),
    williams_r_period: parseInt(process.env.WILLIAMS_R_PERIOD || '14', 10),
    mfi_period: parseInt(process.env.MFI_PERIOD || '14', 10),
    psar_acceleration: parseFloat(process.env.PSAR_ACCELERATION || '0.02'),
    psar_max_acceleration: parseFloat(process.env.PSAR_MAX_ACCELERATION || '0.2'),
    sma_short_period: parseInt(process.env.SMA_SHORT_PERIOD || '10', 10),
    sma_long_period: parseInt(process.env.SMA_LONG_PERIOD || '50', 10),
    fibonacci_window: parseInt(process.env.FIBONACCI_WINDOW || '60', 10),
    ehlers_fast_period: parseInt(process.env.EHLERS_FAST_PERIOD || '10', 10),
    ehlers_fast_multiplier: parseFloat(process.env.EHLERS_FAST_MULTIPLIER || '2.0'),
    ehlers_slow_period: parseInt(process.env.EHLERS_SLOW_PERIOD || '20', 10),
    ehlers_slow_multiplier: parseFloat(process.env.EHLERS_SLOW_MULTIPLIER || '3.0'),
    macd_fast_period: parseInt(process.env.MACD_FAST_PERIOD || '12', 10),
    macd_slow_period: parseInt(process.env.MACD_SLOW_PERIOD || '26', 10),
    macd_signal_period: parseInt(process.env.MACD_SIGNAL_PERIOD || '9', 10),
    adx_period: parseInt(process.env.ADX_PERIOD || '14', 10),
    ichimoku_tenkan_period: parseInt(process.env.ICHIMOKU_TENKAN_PERIOD || '9', 10),
    ichimoku_kijun_period: parseInt(process.env.ICHIMOKU_KIJUN_PERIOD || '26', 10),
    ichimoku_senkou_span_b_period: parseInt(process.env.ICHIMOKU_SENKOU_SPAN_B_PERIOD || '52', 10),
    ichimoku_chikou_span_offset: parseInt(process.env.ICHIMOKU_CHIKOU_SPAN_OFFSET || '26', 10),
    obv_ema_period: parseInt(process.env.OBV_EMA_PERIOD || '20', 10),
    cmf_period: parseInt(process.env.CMF_PERIOD || '20', 10),
    rsi_oversold: parseInt(process.env.RSI_OVERSOLD || '30', 10),
    rsi_overbought: parseInt(process.env.RSI_OVERBOUGHT || '70', 10),
    stoch_rsi_oversold: parseInt(process.env.STOCH_RSI_OVERSOLD || '20', 10),
    stoch_rsi_overbought: parseInt(process.env.STOCH_RSI_OVERBOUGHT || '80', 10),
    cci_oversold: parseInt(process.env.CCI_OVERSOLD || '-100', 10),
    cci_overbought: parseInt(process.env.CCI_OVERBOUGHT || '100', 10),
    williams_r_oversold: parseInt(process.env.WILLIAMS_R_OVERSOLD || '-80', 10),
    williams_r_overbought: parseInt(process.env.WILLIAMS_R_OVERBOUGHT || '-20', 10),
    mfi_oversold: parseInt(process.env.MFI_OVERSOLD || '20', 10),
    mfi_overbought: parseInt(process.env.MFI_OVERBOUGHT || '80', 10),
    volatility_index_period: parseInt(process.env.VOLATILITY_INDEX_PERIOD || '20', 10),
    vwma_period: parseInt(process.env.VWMA_PERIOD || '20', 10),
    volume_delta_period: parseInt(process.env.VOLUME_DELTA_PERIOD || '5', 10),
    volume_delta_threshold: parseFloat(process.env.VOLUME_DELTA_THRESHOLD || '0.2'),
    kama_period: parseInt(process.env.KAMA_PERIOD || '10', 10),
    kama_fast_period: parseInt(process.env.KAMA_FAST_PERIOD || '2', 10),
    kama_slow_period: parseInt(process.env.KAMA_SLOW_PERIOD || '30', 10),
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
          indicatorSettings: config.indicatorSettings, // Pass indicator settings
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
        // In log mode, klines and indicator settings are assumed to be part of the parsed log data if needed by GeminiAnalyzer
        // For now, we'll just pass the existing latestData structure.
        latestData.indicatorSettings = config.indicatorSettings; // Ensure settings are passed even in log mode
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
  new GeminiAnalyzer(config.geminiApiKey, config.tradingSymbol),
  new SignalGenerator()
);

process.on('SIGINT', () => bot.shutdown());
process.on('SIGTERM', () => bot.shutdown());

bot.startBot().catch(error => {
  logger.error(chalk.red(`🔥 Fatal disturbance in the code-weave: ${error.message}`));
  logger.error(chalk.red(error.stack));
  process.exit(1);
});