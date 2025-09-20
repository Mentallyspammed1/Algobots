import chalk from 'chalk';
let termux;
try {
    termux = await import('termux-api');
    } catch (e) { // eslint-disable-line no-unused-vars
        console.log(chalk.gray("Termux API not found. Notifications will be disabled."));
    }
function sendTermuxNotification(message, type) {
    if (!termux) return;

    let title = "Bybit Signal";
    let color = "#FF0000";
    let vibratePattern = [];

    switch (type) {
        case "STRONG BUY":
            title = "🔥 STRONG BUY SIGNAL 🔥";
            color = "#00FF00";
            vibratePattern = [100, 50, 100, 50, 100];
            break;
        case "STRONG SELL":
            title = "🚨 STRONG SELL SIGNAL 🚨";
            color = "#FF0000";
            vibratePattern = [100, 50, 100, 50, 100];
            break;
        case "BUY":
            title = "👍 BUY SIGNAL 👍";
            color = "#00FFFF";
            vibratePattern = [50, 50];
            break;
        case "SELL":
            title = "👎 SELL SIGNAL 👎";
            color = "#FF00FF";
            vibratePattern = [50, 50];
            break;
        default:
            title = "-- NEUTRAL --";
            color = "#FFFF00";
            break;
    }

    const signalText = message.split('\n')[0];

    try {
        termux.notification({ title: title, content: signalText, color: color, vibrate: vibratePattern });
        console.log(chalk.gray(`   (Termux notification sent: ${title})`));
    } catch (error) {
        console.error(chalk.red(`   (Failed to send Termux notification: ${error.message})`));
    }
}

export { sendTermuxNotification };