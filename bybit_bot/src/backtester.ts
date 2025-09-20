import { TradingBot } from './core/bot';
import { config } from './core/config';
import { logger } from './core/logger';
import { LiveBybitService } from './services/live_bybit_service'; // Used to fetch historical data
import { BacktestService } from './services/backtest_service';
import { TrendScoringStrategy } from './strategies/trend_scoring_strategy';

async function runBacktest() {
  logger.system('Initializing backtest...');

  // 1. Fetch historical data using the LiveBybitService (only for data fetching)
  const liveServiceForData = new LiveBybitService(
    config.env.BYBIT_API_KEY,
    config.env.BYBIT_API_SECRET,
    config.env.BYBIT_TESTNET,
    { onCandle: () => {}, onOrderUpdate: () => {}, onExecution: () => {} } // Dummy callbacks
  );

  logger.system(`Fetching ${config.bot.symbol} ${config.bot.interval} historical data...`);
  const historicalKlines = await liveServiceForData.getKlineHistory(config.bot.symbol, config.bot.interval, 1000); // Fetch 1000 candles
  
  if (historicalKlines.length === 0) {
    logger.error('No historical data fetched. Exiting backtest.');
    process.exit(1);
  }
  logger.success(`Fetched ${historicalKlines.length} historical candles.`);

  // 2. Initialize BacktestService with historical data
  const backtestService = new BacktestService(historicalKlines);

  // 3. Initialize Strategy
  if (config.bot.strategy.name !== 'TrendScoring') {
    logger.error(`Strategy ${config.bot.strategy.name} not implemented for backtesting.`);
    process.exit(1);
  }
  const strategy = new TrendScoringStrategy(config.bot.strategy);

  // 4. Initialize the bot with the BacktestService
  const bot = new TradingBot(config.bot, strategy, backtestService);

  // Set the backtest service's callbacks to the bot's handlers
  backtestService.setBotCallbacks(
    (candle) => bot.onCandle(candle),
    (order) => bot.onOrderUpdate(order),
    (exec) => bot.onExecution(exec)
  );

  // 5. Run the backtest
  try {
    await backtestService.runBacktest();
    logger.success('Backtest completed.');
    bot.getTradeMetrics().displaySummary(); // Display final metrics
  } catch (error) {
    logger.error('Backtest failed:', error);
    process.exit(1);
  }
}

runBacktest();
