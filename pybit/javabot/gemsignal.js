// Forge the ultimate scalping signal with Gemini AI reasoning - Refactored Edition
// By Pyrmethus, Termux Coding Wizard

const chalk = require('chalk').default;
const fs = require('fs');
const yargs = require('yargs/yargs');
const { hideBin } = require('yargs/helpers');
const argv = yargs(hideBin(process.argv)).argv;

const CONFIG = require('./utils/config');
const { fetchAndCalculateIndicators, getAccountBalance } = require('./utils/bybit');
const { createGeminiPrompt, getGeminiAnalysis, isGeminiInitialized } = require('./utils/gemini');
const { sendTermuxNotification } = require('./utils/termux');
const { sendWebhookNotification } = require('./utils/webhook');
const { getNewsSentiment } = require('./utils/news');
const Indicators = require('./utils/indicators');

// --- Main Signal Generation Logic ---
async function generateComprehensiveSignal(data, config, newsSentiment) {
    if (!data || !data.latestCandle || !data.indicators || !Number.isFinite(data.indicators.atr)) {
        console.error(chalk.red.bold("❌ Critical data missing for signal generation. Cannot proceed."));
        return { signal: chalk.red.bold("Error: Insufficient data for signal generation."), reasons: [], score: { buy: 0, sell: 0 }, type: "ERROR", entry: null, tp: null, sl: null, confidence: "N/A", geminiReasoning: null };
    }

    const { latestCandle, indicators } = data;
    const { signalThresholds, weights } = config;
    const { close } = latestCandle;
    const closePrice = Number(close);
    const currentATR = indicators.atr;

    let weightedBuyScore = 0;
    let weightedSellScore = 0;
    let signalReasons = [];

    const addWeightedScore = (side, reason, weight) => {
        if (weight == null) return;
        const w = Math.abs(weight);
        if (side === 'buy') {
            weightedBuyScore += w;
            signalReasons.push({ reason: chalk.green(`+ ${reason}`), type: 'buy', weight: w });
        } else if (side === 'sell') {
            weightedSellScore += w;
            signalReasons.push({ reason: chalk.red(`- ${reason}`), type: 'sell', weight: w });
        }
    };

    // --- Weighted Scoring Logic ---

    // RSI Analysis
    if (indicators.rsi) {
        if (indicators.rsi <= signalThresholds.rsi.oversold) {
            addWeightedScore('buy', `RSI is oversold (${indicators.rsi.toFixed(2)})`, weights.rsi);
        } else if (indicators.rsi >= signalThresholds.rsi.overbought) {
            addWeightedScore('sell', `RSI is overbought (${indicators.rsi.toFixed(2)})`, weights.rsi);
        }
    }

    // Stochastic Analysis
    if (indicators.stochasticK && indicators.stochasticD) {
        if (indicators.stochasticK <= signalThresholds.stochastic.oversold && indicators.stochasticD <= signalThresholds.stochastic.oversold && indicators.stochasticK > indicators.stochasticD) {
            addWeightedScore('buy', `Stochastic is oversold and crossing up (K:${indicators.stochasticK.toFixed(2)}, D:${indicators.stochasticD.toFixed(2)})`, weights.stochastic);
        } else if (indicators.stochasticK >= signalThresholds.stochastic.overbought && indicators.stochasticD >= signalThresholds.stochastic.overbought && indicators.stochasticK < indicators.stochasticD) {
            addWeightedScore('sell', `Stochastic is overbought and crossing down (K:${indicators.stochasticK.toFixed(2)}, D:${indicators.stochasticD.toFixed(2)})`, weights.stochastic);
        }
    }

    // MACD Analysis
    if (indicators.macdLine && indicators.signalLine && indicators.macdHistogram) {
        if (indicators.macdLine > indicators.signalLine && indicators.macdHistogram > 0) {
            addWeightedScore('buy', `MACD bullish crossover (Histogram: ${indicators.macdHistogram.toFixed(4)})`, weights.macd);
        } else if (indicators.macdLine < indicators.signalLine && indicators.macdHistogram < 0) {
            addWeightedScore('sell', `MACD bearish crossover (Histogram: ${indicators.macdHistogram.toFixed(4)})`, weights.macd);
        }
    }

    // Moving Average Crossover Analysis (EMA)
    if (indicators.emaShort && indicators.emaLong) {
        if (indicators.emaShort > indicators.emaLong) {
            addWeightedScore('buy', 'EMA bullish crossover (Short > Long)', weights.emaCrossover);
        } else {
            addWeightedScore('sell', 'EMA bearish crossover (Short < Long)', weights.emaCrossover);
        }
    }

    // News Sentiment Analysis
    if (newsSentiment && newsSentiment.sentimentScore && weights.news) {
        if (newsSentiment.sentimentScore > 0) {
            addWeightedScore('buy', `Positive news sentiment (${newsSentiment.sentimentScore.toFixed(2)})`, weights.news * newsSentiment.sentimentScore);
        } else if (newsSentiment.sentimentScore < 0) {
            addWeightedScore('sell', `Negative news sentiment (${newsSentiment.sentimentScore.toFixed(2)})`, weights.news * Math.abs(newsSentiment.sentimentScore));
        }
    }

    let finalSignal = "-- NEUTRAL --";
    let signalColor = chalk.yellow.bold;
    let signalType = "NEUTRAL";
    let entryPrice = closePrice;
    let tpPrice = null;
    let slPrice = null;
    let confidenceLevel = "N/A";

    const totalScore = weightedBuyScore + weightedSellScore;
    if (totalScore > 0) {
        const buyPercentage = (weightedBuyScore / totalScore) * 100;
        if (buyPercentage >= 65) confidenceLevel = `High (${buyPercentage.toFixed(0)}%)`;
        else if (buyPercentage >= 55) confidenceLevel = `Medium (${buyPercentage.toFixed(0)}%)`;
        else if (buyPercentage >= 45) confidenceLevel = `Low (${buyPercentage.toFixed(0)}%)`;
        else confidenceLevel = `Very Low (${buyPercentage.toFixed(0)}%)`;
    }

    const scoreDifference = weightedBuyScore - weightedSellScore;

    if (scoreDifference >= signalThresholds.strength) {
        signalType = "STRONG BUY";
        signalColor = chalk.green.bold;
        finalSignal = "🔥 STRONG BUY SIGNAL 🔥";
    } else if (scoreDifference > 0) {
        signalType = "BUY";
        signalColor = chalk.green;
        finalSignal = "📈 BUY SIGNAL 📈";
    } else if (scoreDifference <= -signalThresholds.strength) {
        signalType = "STRONG SELL";
        signalColor = chalk.red.bold;
        finalSignal = "🚨 STRONG SELL SIGNAL 🚨";
    } else if (scoreDifference < 0) {
        signalType = "SELL";
        signalColor = chalk.red;
        finalSignal = "📉 SELL SIGNAL 📉";
    }

    if (Number.isFinite(currentATR) && currentATR > 0) {
        const tpMultiplier = config.tradeManagement.atrMultiplierTP;
        const slMultiplier = config.tradeManagement.atrMultiplierSL;

        if (signalType.includes("BUY")) {
            tpPrice = entryPrice + (currentATR * tpMultiplier);
            slPrice = entryPrice - (currentATR * slMultiplier);
        } else if (signalType.includes("SELL")) {
            tpPrice = entryPrice - (currentATR * tpMultiplier);
            slPrice = entryPrice + (currentATR * slMultiplier);
        }
    }

    signalReasons.sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight));

    let geminiReasoning = null;
    if (isGeminiInitialized() && (signalType.includes('BUY') || signalType.includes('SELL'))) {
        const prompt = createGeminiPrompt(data, config, newsSentiment, signalType);
        if (prompt) {
            geminiReasoning = await getGeminiAnalysis(prompt);
        }
    }

    const accountBalance = await getAccountBalance();
    let positionSize = 0;
    if (slPrice !== null && entryPrice !== slPrice) {
        positionSize = (accountBalance * config.tradeManagement.riskPerTrade) / Math.abs(entryPrice - slPrice);
    }

    let message = `${finalSignal}\n`;
    message += `  Symbol: ${config.symbol}\n`;
    message += `  Entry Price: ${Indicators.nfmt(entryPrice)}\n`;
    message += `  Take Profit (TP): ${tpPrice !== null ? Indicators.nfmt(tpPrice) : 'N/A'}\n`;
    message += `  Stop Loss (SL): ${slPrice !== null ? Indicators.nfmt(slPrice) : 'N/A'}\n`;
    message += `  Position Size: ${positionSize > 0 ? positionSize.toFixed(4) : 'N/A'}\n`;
    message += `  Confidence: ${signalColor(confidenceLevel)}\n`;
    message += `  Weighted Score: ${signalColor(`Buy: ${weightedBuyScore.toFixed(2)}, Sell: ${weightedSellScore.toFixed(2)}`)}\n`;

    if (geminiReasoning) {
        message += `\n  ${chalk.magenta.bold('🔮 Gemini AI Analysis:')}\n`;
        message += `    ${chalk.cyan('Trend:')} ${geminiReasoning.trend ? signalColor(geminiReasoning.trend) : chalk.gray('N/A')}\n`;
        message += `    ${chalk.cyan('Opportunity:')} ${geminiReasoning.opportunity ? chalk.yellow(geminiReasoning.opportunity) : chalk.gray('N/A')}\n`;
        message += `    ${chalk.cyan('Rationale:')} ${geminiReasoning.reasoning || chalk.gray('N/A')}\n`;
    }

    const result = { signal: signalColor(message), reasons: signalReasons, score: { buy: weightedBuyScore, sell: weightedSellScore }, type: signalType, entry: entryPrice, tp: tpPrice, sl: slPrice, confidence: confidenceLevel, geminiReasoning: geminiReasoning };

    sendWebhookNotification(result);
    return result;
}

// --- Main Execution Loop ---
async function runContinuousLoop() {
    console.log(chalk.cyan(`Entering continuous monitoring mode. Interval: ${CONFIG.interval}, Loop Delay: ${CONFIG.loopInterval}ms`));
    while (true) {
        for (const symbol of CONFIG.symbols) {
            const formattedCandles = await fetchAndCalculateIndicators(CONFIG, symbol);

            if (!formattedCandles) {
                console.log(chalk.yellow(`\nSkipping signal generation for ${symbol} due to data issues.`));
                continue;
            }

            const indicators = calculateAllIndicators(formattedCandles, CONFIG.periods);
            const newsSentiment = await getNewsSentiment(symbol);

            const data = {
                candles: formattedCandles,
                latestCandle: formattedCandles[formattedCandles.length - 1],
                indicators,
            };

            const { signal, type } = await generateComprehensiveSignal(data, { ...CONFIG, symbol }, newsSentiment);
            console.log(signal);

            logSignal(signal.replace(/\x1b\[[0-9;]*m/g, ''), symbol); // Log plain text without ANSI codes

            if (type.includes("BUY") || type.includes("SELL")) {
                sendTermuxNotification(signal, type);
            }
        }
        await new Promise(resolve => setTimeout(resolve, CONFIG.loopInterval));
    }
}

function calculateAllIndicators(candles, periods) {
    const indicators = {};
    indicators.smaShort = Indicators.calculateSMA(candles, periods.smaShort);
    indicators.smaLong = Indicators.calculateSMA(candles, periods.smaLong);
    indicators.emaShort = Indicators.calculateEMA(candles, periods.emaShort);
    indicators.emaLong = Indicators.calculateEMA(candles, periods.emaLong);
    const macdResult = Indicators.calculateMACD(candles, periods.macd.fast, periods.macd.slow, periods.macd.signal);
    if (macdResult) {
        indicators.macdLine = macdResult.macdLine;
        indicators.signalLine = macdResult.signalLine;
        indicators.macdHistogram = macdResult.histogram;
    }
    indicators.rsi = Indicators.calculateRSI(candles, periods.rsi);
    const stochasticResult = Indicators.calculateStochastic(candles, periods.stochastic.k, periods.stochastic.d);
    if (stochasticResult) {
        indicators.stochasticK = stochasticResult.k;
        indicators.stochasticD = stochasticResult.d;
    }
    indicators.atr = Indicators.calculateATR(candles, periods.atr);
    return indicators;
}

function logSignal(signalText, symbol) {
    try {
        const logEntry = `${new Date().toISOString()} - ${symbol}: ${signalText.split('\n')[0]}\n`;
        fs.appendFileSync(CONFIG.logFile, logEntry, 'utf8');
        console.log(chalk.gray(`   Signal logged to ${CONFIG.logFile}.`));
    } catch (error) {
        console.error(chalk.red(`   (Failed to log signal: ${error.message})`));
    }
}

async function runBacktest(filePath) {
    console.log(chalk.cyan(`Entering backtesting mode. Loading data from ${filePath}...`));
    let historicalData;
    try {
        const fileContent = fs.readFileSync(filePath, 'utf8');
        historicalData = JSON.parse(fileContent);
    } catch (error) {
        console.error(chalk.red(`Failed to read or parse backtest data file: ${error.message}`));
        return;
    }

    if (!Array.isArray(historicalData) || historicalData.length === 0) {
        console.error(chalk.red("Backtest data is not a valid array or is empty."));
        return;
    }

    let balance = 10000; // Starting balance
    let trades = 0;
    let wins = 0;
    let totalPnl = 0;

    for (let i = 1; i < historicalData.length - 1; i++) { // Iterate up to the second to last element
        const candleSlice = historicalData.slice(0, i + 1);
        const indicators = calculateAllIndicators(candleSlice, CONFIG.periods);
        const data = {
            candles: candleSlice,
            latestCandle: candleSlice[candleSlice.length - 1],
            indicators,
        };

        const { type, entry, tp, sl } = await generateComprehensiveSignal(data, CONFIG, null);

        if ((type.includes("BUY") || type.includes("SELL")) && entry && tp && sl) {
            trades++;
            const nextCandle = historicalData[i + 1];
            let pnl = 0;
            let outcome = "INCONCLUSIVE";

            if (type.includes("BUY")) {
                if (nextCandle.low <= sl) {
                    outcome = "LOSS";
                    pnl = sl - entry;
                } else if (nextCandle.high >= tp) {
                    outcome = "WIN";
                    pnl = tp - entry;
                }
            } else if (type.includes("SELL")) {
                if (nextCandle.high >= sl) {
                    outcome = "LOSS";
                    pnl = entry - sl;
                } else if (nextCandle.low <= tp) {
                    outcome = "WIN";
                    pnl = entry - tp;
                }
            }

            if (outcome === "WIN") {
                wins++;
                totalPnl += pnl;
            } else if (outcome === "LOSS") {
                totalPnl += pnl;
            }
        }
    }
    
    const finalBalance = balance + totalPnl;

    console.log(chalk.blue.bold("\n--- Backtest Results ---"));
    console.log(`  Total Trades: ${trades}`);
    console.log(`  Wins: ${wins}`);
    console.log(`  Losses: ${trades - wins}`);
    console.log(`  Win Rate: ${trades > 0 ? ((wins / trades) * 100).toFixed(2) : 'N/A'}%`);
    console.log(`  Total PnL: ${totalPnl.toFixed(2)}`);
    console.log(`  Starting Balance: ${balance.toFixed(2)}`);
    console.log(`  Final Balance: ${finalBalance.toFixed(2)}`);
    console.log(chalk.blue.bold("------------------------"));
}


// --- Entry Point ---
async function main() {
    if (argv.backtest) {
        await runBacktest(argv.backtest);
    } else if (CONFIG.continuousMode) {
        await runContinuousLoop();
    } else {
        // Original single-run logic can be placed here if needed
        console.log(chalk.yellow("Running in single-shot mode is deprecated. Please use --continuous or --backtest."));
    }
}

main();