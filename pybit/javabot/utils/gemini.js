const { GoogleGenerativeAI } = require('@google/generative-ai');
const chalk = require('chalk').default; // FIX: Correct chalk import
// console.log('Chalk in gemini.js:', chalk); // REMOVE: Debugging line
const { nfmt } = require('./indicators');

const GEMINI_API_KEY = process.env.GEMINI_API_KEY;
const GEMINI_MODEL_NAME = process.env.GEMINI_MODEL || 'gemini-pro';
let geminiAI;
let geminiModel;

if (!GEMINI_API_KEY) {
    console.error(chalk.red.bold("❌ GEMINI_API_KEY not found in .env file. Gemini features will be disabled."));
} else {
    try {
        geminiAI = new GoogleGenerativeAI(GEMINI_API_KEY);
        geminiModel = geminiAI.getGenerativeModel({ model: GEMINI_MODEL_NAME });
        console.log(chalk.green(`✅ Gemini API initialized successfully with model: ${GEMINI_MODEL_NAME}.`));
    } catch (error) {
        console.error(chalk.red.bold(`❌ Error initializing Gemini API: ${error.message}`)); // FIX: Re-add chalk formatting
        if (error.details) console.error(chalk.red(`   Details: ${error.details}`)); // FIX: Re-add chalk formatting
        geminiModel = null;
    }
}

function createGeminiPrompt(data, config, newsSentiment, signalType) {
    const { latestCandle, indicators, reasons = [] } = data;
    if (!latestCandle || !indicators || !Number.isFinite(indicators.atr)) {
        console.warn(chalk.yellow("   (Skipping Gemini prompt generation due to missing critical data.)"));
        return '';
    }

    const closePrice = Number(latestCandle.close);

    let prompt = `Analyze trading data for ${config.symbol} (${config.interval} interval). Current close: ${nfmt(closePrice)}. ATR: ${nfmt(indicators.atr)}.\n\n`;

    prompt += `Key Indicators:\n`;
    prompt += `- EMAs: Short (${config.periods.emaShort}): ${nfmt(indicators.emaShort)}, Long (${config.periods.emaLong}): ${nfmt(indicators.emaLong)}\n`;
    if (Number.isFinite(indicators.rsi)) {
        prompt += `- RSI (${config.periods.rsi}): ${nfmt(indicators.rsi, 2)}\n`;
    }
    if (Number.isFinite(indicators.macdLine)) {
        prompt += `- MACD: Line ${nfmt(indicators.macdLine)}, Signal ${nfmt(indicators.signalLine)}, Hist ${nfmt(indicators.macdHistogram)}\n`;
    }
    if (Number.isFinite(indicators.stochasticK)) {
        prompt += `- Stochastic: %K ${nfmt(indicators.stochasticK, 2)}, %D ${nfmt(indicators.stochasticD, 2)}\n`;
    }
    if (newsSentiment) {
        prompt += `\nNews Sentiment: ${newsSentiment.sentiment} (${newsSentiment.source})\n`;
    }
    prompt += '\n';

    prompt += `Technical Reasoning (Sorted by Influence):\n`;
    if (reasons.length > 0) {
        reasons.forEach(item => {
            const cleanReason = String(item.reason || '').replace(/\u001b\[[0-9;]*m/g, '');
            const w = Number(item.weight);
            prompt += `  - ${cleanReason} (Weight: ${Number.isFinite(w) ? w.toFixed(2) : 'N/A'})\n`;
        });
    } else {
        prompt += `  - No strong technical signals detected.\n`;
    }
    prompt += '\n';

    prompt += `Provide a concise and insightful analysis (max 200 words): trend, opportunity, supporting factors, conflicting signals, sentiment. The current signal type is ${signalType}.\n`;
    prompt += `Respond STRICTLY in JSON format with the following keys: "trend", "opportunity", "reasoning".`; // FIX: Complete template literal
    
    return prompt;
}

async function getGeminiAnalysis(prompt) {
    if (!geminiModel) {
        console.warn(chalk.yellow("   (Gemini model not initialized. Skipping AI analysis.)"));
        return null;
    }
    try {
        const result = await geminiModel.generateContent(prompt);
        const response = await result.response;
        const text = response.text();
        return JSON.parse(text);
    } catch (error) {
        console.error(chalk.red.bold(`❌ Error getting Gemini analysis: ${error.message}`));
        return null;
    }
}

function isGeminiInitialized() {
    return !!geminiModel;
}

module.exports = {
    createGeminiPrompt,
    getGeminiAnalysis,
    isGeminiInitialized,
};