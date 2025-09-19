const axios = require('axios');
const chalk = require('chalk').default;
const CONFIG = require('./config');

async function fetchWithRetry(url, params, retries = CONFIG.retryAttempts, delay = CONFIG.retryDelay) {
    for (let i = 0; i < retries; i++) {
        try {
            const response = await axios.get(url, { params });
            if (response.data.retCode === 0) {
                return response.data;
            }
            console.warn(chalk.yellow(`Attempt ${i + 1} failed with retCode ${response.data.retCode}: ${response.data.retMsg}`))
        } catch (error) {
            console.warn(chalk.yellow(`Attempt ${i + 1} failed with error: ${error.message}`))
        }
        await new Promise(resolve => setTimeout(resolve, delay * (i + 1)));
    }
    throw new Error(`Failed to fetch data from ${url} after ${retries} attempts`);
}

async function fetchAndCalculateIndicators(config, symbol) {
    const { interval, baseFetchLimit, fetchBuffer, bybitApiUrl, apiCategory, periods } = config;

    const longestPeriodRequired = Math.max(
        periods.smaShort, periods.smaLong, periods.emaShort, periods.emaLong,
        periods.macd.slow + periods.macd.signal, periods.rsi, periods.stochastic.k,
        periods.atr, periods.bollinger.period, periods.williamsR, periods.cmf,
        periods.elderRay, periods.keltner.period, periods.aroon
    );
    const fetchLimit = Math.max(baseFetchLimit, Math.ceil(longestPeriodRequired * fetchBuffer));

    console.log(chalk.cyan(`\n✨ Channeling ${fetchLimit} candles from Bybit for ${symbol} (${interval})...`));

    try {
        const response = await fetchWithRetry(bybitApiUrl, {
            category: apiCategory,
            symbol,
            interval: interval,
            limit: fetchLimit
        });

        const candleData = response.result?.list;

        if (!candleData || candleData.length === 0) {
            console.error(chalk.red.bold("❌ No candle data received from Bybit."));
            return null;
        }

        const reversedCandleData = candleData.reverse();

        const formattedCandles = reversedCandleData.map(candle => ({
            timestamp: candle[0],
            open: Number(candle[1]),
            high: Number(candle[2]),
            low: Number(candle[3]),
            close: Number(candle[4]),
            volume: Number(candle[5]),
            turnover: Number(candle[6])
        }));

        console.log(chalk.green(`✅ Successfully fetched ${formattedCandles.length} candles.`));

        if (formattedCandles.length < longestPeriodRequired) {
            console.warn(chalk.yellow(`⚠️ Insufficient data (${formattedCandles.length} candles) to reliably calculate all indicators requiring up to ${longestPeriodRequired} periods.`));
        }

        return formattedCandles;

    } catch (error) {
        console.error(chalk.red.bold(`❌ Error fetching data from Bybit.`));
        if (error.response) {
            console.error(chalk.red(`   Status: ${error.response.status}`));
            console.error(chalk.red(`   Message: ${error.message}`));
            console.error(chalk.red(`   Data: ${JSON.stringify(error.response.data)}`));
        } else {
            console.error(chalk.red(`   Message: ${error.message}`));
        }
        return null;
    }
}

async function getAccountBalance() {
    // This is a placeholder. In a real application, you would use the Bybit API
    // with authentication to fetch the account balance.
    console.log(chalk.yellow("Fetching account balance (placeholder)..."));
    return 10000; // Placeholder balance
}


module.exports = { fetchAndCalculateIndicators, getAccountBalance };