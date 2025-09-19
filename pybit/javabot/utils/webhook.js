const axios = require('axios');
const chalk = require('chalk').default;
const CONFIG = require('./config');

async function sendWebhookNotification(signal) {
    if (!CONFIG.webhookUrl) {
        return;
    }

    try {
        await axios.post(CONFIG.webhookUrl, {
            content: signal.signal.replace(/\u001b\[[0-9;]*m/g, ''), // Send plain text
            embeds: [{
                title: `${signal.type} - ${CONFIG.symbol}`,
                description: `Confidence: ${signal.confidence}`,
                color: getSignalColor(signal.type),
                fields: [
                    { name: "Entry Price", value: signal.entry, inline: true },
                    { name: "Take Profit", value: signal.tp, inline: true },
                    { name: "Stop Loss", value: signal.sl, inline: true },
                    { name: "Buy Score", value: signal.score.buy.toFixed(2), inline: true },
                    { name: "Sell Score", value: signal.score.sell.toFixed(2), inline: true },
                ]
            }]
        });
        console.log(chalk.gray(`   Webhook notification sent.`));
    } catch (error) {
        console.error(chalk.red(`   (Failed to send webhook notification: ${error.message})`));
    }
}

function getSignalColor(signalType) {
    switch (signalType) {
        case "STRONG BUY":
            return 0x00FF00; // Green
        case "STRONG SELL":
            return 0xFF0000; // Red
        case "BUY":
            return 0x00FFFF; // Cyan
        case "SELL":
            return 0xFF00FF; // Magenta
        default:
            return 0xFFFF00; // Yellow
    }
}

module.exports = { sendWebhookNotification };