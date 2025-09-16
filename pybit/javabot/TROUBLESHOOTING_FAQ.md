# Troubleshooting and FAQ

This document provides solutions to common issues, answers to frequently asked questions, and explanations for common error messages you might encounter while using the trading bot.

## Common Issues and Solutions

### 1. `API Key and Secret must be provided` error

**Cause:** The bot cannot find your Bybit API Key or API Secret.
**Solution:**
*   Ensure you have created a `.env` file in the project root.
*   Verify that `BYBIT_API_KEY` and `BYBIT_API_SECRET` are correctly defined in your `.env` file.
*   Double-check for typos or extra spaces in the key/secret values.

### 2. Bot not placing trades

**Cause:** The bot is in dry-run mode, or your API keys do not have trading permissions.
**Solution:**
*   **Check `DRY_RUN` flag:** In `config.js` (for Node.js bots) or `config.py` (for Python bots), ensure `DRY_RUN` is set to `false` to enable live trading.
*   **API Key Permissions:** Log in to your Bybit account and verify that the API key you are using has "Trade" permissions enabled.

### 3. Strategy not starting or not generating signals

**Cause:** The strategy is disabled in the configuration, or there's an issue with the strategy file itself.
**Solution:**
*   **Enable Strategy:** In `config.js` (Node.js) or `config.py` (Python), ensure the `enabled` flag for your desired strategy is set to `true`.
*   **Correct File Path:** Verify that the strategy file exists in the correct `strategies/` directory and that its name matches the configuration.
*   **Sufficient Data:** Ensure the bot has received enough historical kline data for the strategy to calculate indicators (e.g., `MIN_KLINES_FOR_STRATEGY` in `config.js`).
*   **Strategy Logic:** Review your strategy's `generateSignals` (Node.js) or `generate_signals` (Python) method for any logical errors or issues that might prevent it from returning a signal.

### 4. `Bybit API Error 10001: accountType only support UNIFIED`

**Cause:** Your Bybit account is not configured as a Unified Trading Account (UTA). The bot is designed to work with UTA.
**Solution:**
*   **Upgrade Account:** Log in to your Bybit account and upgrade your account to a Unified Trading Account (UTA). This option is usually found in your account settings or profile.

### 5. `TypeError: chalk.purple is not a function` (Node.js specific)

**Cause:** You are trying to use a `chalk` color method that does not exist.
**Solution:**
*   The `chalk` library has specific color methods. Use valid methods like `chalk.magenta`, `chalk.rgb(R,G,B)`, or `chalk.hex('#RRGGBB')` for custom colors. Refer to the `chalk` documentation for available colors.

## Frequently Asked Questions (FAQ)

### Q1: Can I run multiple strategies simultaneously?
**A1:** Yes, the Node.js `bot_orchestrator.js` is designed to run multiple enabled strategies concurrently. For Python, you would need to modify `main.py` to load and run multiple `BybitTrader` instances, each with a different strategy.

### Q2: How can I test my strategy without risking real money?
**A2:** Set the `DRY_RUN` flag to `true` in your `config.js` (Node.js) or `config.py` (Python) file. This will simulate all trades without sending them to the exchange.

### Q3: How do I change the trading pair or interval?
**A3:** You can configure the `SYMBOL` and `INTERVAL` parameters in your `config.js` (Node.js) or `config.py` (Python) file. Ensure your chosen strategy supports the new symbol and interval.

### Q4: What is the cooldown period for placing orders?
**A4:** The `cooldown_period` (Python) or `ORDER_RETRY_DELAY_SECONDS` (Node.js) in the configuration prevents the bot from placing orders too frequently. This is to avoid rate limit issues and unintended rapid trades.

### Q5: How can I get more detailed logs for debugging?
**A5:** Change the `LOG_LEVEL` in your `config.js` (Node.js) or `config.py` (Python) to `DEBUG`. This will enable more verbose logging output.

## Common Error Messages

### `Error: connect ECONNREFUSED 127.0.0.1:80`

**Cause:** The bot is trying to connect to a local server that is not running or is blocked by a firewall. This often happens if you have a proxy configured incorrectly or a service the bot depends on is down.
**Solution:**
*   Check your network connection.
*   Verify any proxy settings in your configuration.
*   Ensure any local services the bot might be trying to connect to are running.

### `Max retries reached`

**Cause:** The bot attempted to make an API call multiple times but failed to get a successful response after all retries. This could be due to persistent network issues, incorrect API keys, or Bybit API downtime.
**Solution:**
*   Check your internet connection.
*   Verify your API keys and secret.
*   Check Bybit's API status page for any ongoing issues.
*   Increase `ORDER_RETRY_ATTEMPTS` or `ORDER_RETRY_DELAY_SECONDS` in your configuration if you suspect temporary network instability.
