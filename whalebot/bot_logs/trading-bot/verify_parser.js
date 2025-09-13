import LogParser from './lib/logParser.js';
import chalk from 'chalk';
import { logger } from './lib/utils.js';

const verify = async () => {
  logger.info(chalk.magenta('--- Parser Verification Ritual ---'));

  // Change this to the symbol you want to test from the log
  const symbolToTest = 'POPCATUSDT'; 

  const logParser = new LogParser(symbolToTest, { debugMode: true });
  const logFilePath = '../logs/wgwhalex_bot.log';

  logger.info(`Parsing log for symbol: ${chalk.cyan(symbolToTest)}`);

  const dataPoints = await logParser.parseLogFile(logFilePath);

  if (!dataPoints || dataPoints.length === 0) {
    logger.error(chalk.red('Verification failed: No data points were extracted.'));
    logger.warn(chalk.yellow('Ensure the log file contains entries for the specified symbol and the parser logic is correct.'));
    return;
  }

  const latestData = logParser.getLatestMarketData(dataPoints);

  logger.info(chalk.green('\n--- Latest Parsed Data Point ---'));
  console.log(JSON.stringify(latestData, null, 2));

  const requiredKeys = ['currentPrice', 'rsi', 'macd_hist', '3_ema', '15_ema'];
  let allKeysFound = true;

  logger.info(chalk.magenta('\n--- Key Indicator Verification ---'));
  for (const key of requiredKeys) {
    if (latestData[key] !== undefined) {
      logger.info(chalk.green(`✅ ${key}: ${latestData[key]}`));
    } else {
      logger.error(chalk.red(`❌ ${key}: Not found!`));
      allKeysFound = false;
    }
  }

  if (allKeysFound) {
    logger.info(chalk.green.bold('\n✨ Verification successful! The parser is correctly extracting key data. ✨'));
  } else {
    logger.error(chalk.red.bold('\n🔥 Verification failed! Some key indicators were not parsed. Review the patterns and log format. 🔥'));
  }
};

verify();
