import { TradingBot } from './core/bot';
import { config } from './core/config';
import { logger } from './core/logger';
import { LiveBybitService } from './services/live_bybit_service';
import { DryRunBybitService } from './services/dry_run_bybit_service';
import { IExchange } from './services/exchange_interface';
import { TrendScoringStrategy } from './strategies/trend_scoring_strategy';

async function main() {
  logger.system('Initializing trading bot...');

  // 1. Initialize Services based on RUN_MODE
  let bybitService: IExchange;
  if (config.bot.run_mode === 'LIVE') {
    bybitService = new LiveBybitService(
      config.env.BYBIT_API_KEY,
      config.env.BYBIT_API_SECRET,
      config.env.BYBIT_TESTNET,
      {
        onCandle: (candle) => bot.onCandle(candle),
        onOrderUpdate: (order) => bot.onOrderUpdate(order),
        onExecution: (exec) => bot.onExecution(exec),
      }
    );
    logger.system('Running in LIVE mode.');
  } else if (config.bot.run_mode === 'DRY_RUN') {
    bybitService = new DryRunBybitService(
      config.env.BYBIT_API_KEY,
      config.env.BYBIT_API_SECRET,
      config.env.BYBIT_TESTNET,
      {
        onCandle: (candle) => bot.onCandle(candle),
        onOrderUpdate: (order) => bot.onOrderUpdate(order),
        onExecution: (exec) => bot.onExecution(exec),
      }
    );
    logger.system('Running in DRY_RUN mode.');
  } else if (config.bot.run_mode === 'BACKTEST') {
    logger.error('BACKTEST mode is not yet implemented.');
    process.exit(1);
  } else {
    logger.error(`Invalid RUN_MODE: ${config.bot.run_mode}`);
    process.exit(1);
  }

  // 2. Initialize Strategy
  if (config.bot.strategy.name !== 'TrendScoring') {
    logger.error(`Strategy ${config.bot.strategy.name} not implemented.`);
    process.exit(1);
  }
  const strategy = new TrendScoringStrategy(config.bot.strategy);

  // 3. Initialize and run the bot
  const bot = new TradingBot(config.bot, strategy, bybitService);
  
  try {
    await bot.run();
    logger.success('Trading bot is running.');
  } catch (error) {
    logger.error('Failed to start the trading bot:', error);
    process.exit(1);
  }
}

main();