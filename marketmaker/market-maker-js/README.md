# Bybit Market Maker Bot (JavaScript)

A simple market maker bot for the Bybit exchange, built with Node.js. This bot places buy and sell orders around the mid-price of a given trading symbol.

**DISCLAIMER: This is a simple example bot. Trading cryptocurrencies involves significant risk. Use this bot at your own risk. It is highly recommended to run it on the Bybit testnet before using real funds.**

## Features

- Connects to Bybit's v5 WebSocket API for real-time order book data.
- Places and cancels orders using the v5 REST API.
- Configurable symbol, spread, and order quantity via an `.env` file.
- Supports both testnet and mainnet.

## Prerequisites

- Node.js (v16 or higher)
- A Bybit account (either testnet or mainnet)
- API Key and Secret from your Bybit account

## Setup

1.  **Navigate into the project directory:**
    ```bash
    cd market-maker-js
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Review the `.env` file:**
    The project comes with a pre-configured `.env` file. You can modify the `SYMBOL`, `SPREAD`, and `ORDER_QTY` to your liking. The API keys have been pre-filled from your environment.

4.  **Set to Mainnet (Optional):**
    To run on the mainnet, change `BYBIT_TESTNET=true` to `BYBIT_TESTNET=false` in the `.env` file.

## Running the Bot

To start the bot, run the following command from within the `market-maker-js` directory:

```bash
npm start
```

The bot will connect to the Bybit API and start placing orders based on your configuration. You will see log output in your console.

To stop the bot, press `Ctrl + C`.
