const { execSync } = require('child_process');
const config = require("../config");
const NEON = require('../utils/colors');

function sendSMS(message) {
    try {
        execSync(`termux-sms-send -n "${config.PHONE_NUMBER}" "${message}"`, { stdio: 'ignore' });
        console.log(NEON.GREEN(`SMS Sent (${message.length} chars)`));
    } catch (e) {
        console.log(NEON.RED("SMS failed"));
    }
}

function formatSMS(signal) {
    return `${config.SYMBOL.replace("USDT","")} ${config.TIMEFRAME}m ${signal.direction}
Entry: ${signal.entry}
TP: ${signal.tp} | SL: ${signal.sl}
Conf: ${signal.confidence}
AI: ${signal.reasoning.substring(0,45)}${signal.reasoning.length>45?"...":""}`;
}

module.exports = { sendSMS, formatSMS };
