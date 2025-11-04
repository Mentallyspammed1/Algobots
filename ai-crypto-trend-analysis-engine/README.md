# 🚀 AI Crypto Trend Analysis Engine

An advanced, real-time cryptocurrency dashboard that leverages the Google Gemini API and Bybit's V5 market data to provide sophisticated trend analysis, actionable trading signals, and live market monitoring.

![AI Crypto Trend Analyzer Screenshot](https://storage.googleapis.com/aistudio-o-codegen-public/project_screenshots/ai-crypto-trend-analyzer.png)

## ✨ Core Features

-   **Advanced AI Analysis**: Utilizes the **Gemini 2.5 Flash Lite** model to perform expert-level technical analysis, incorporating multi-timeframe confirmation for higher-quality signals.
-   **Actionable Trading Signals**: Generates clear **BUY/SELL/HOLD** signals complete with confidence scores, entry prices, multiple take-profit targets, and stop-loss levels.
-   **Live, Centralized Data Streams**: Employs a **centralized WebSocket provider** for a highly efficient, single-connection architecture that powers all real-time features.
-   **Event-Driven Auto-Refresh**: Intelligently re-runs analysis the moment a new k-line candle closes, ensuring the most up-to-date insights without redundant API calls.
-   **Rich Data Visualization**: Displays historical price action with dynamic, signal-aware **Area Charts** powered by Recharts.
-   **Live Scrolling Price Ticker**: An always-visible, continuously scrolling ticker provides real-time price updates for key assets.
-   **Customizable Price Alerts**: Set price targets for any symbol and receive instant on-screen **toast notifications** when your target is hit.
-   **Comprehensive Technical Indicators**: Pre-calculates over 15 indicators (RSI, MACD, Bollinger Bands, ADX, VWAP, etc.) on the client-side to feed a richer data set to the AI.
-   **Real-Time Order Book Data**: Each analysis card displays live bid/ask prices with color-coded ticks and a "LIVE" indicator.
-   **Interactive & Responsive UI**: A sleek, modern interface built with **React and Tailwind CSS** allows for easy selection of assets, timeframes, and confidence thresholds.

## 🛠️ Technology Stack

-   **Frontend**: React, TypeScript
-   **Build Tool**: Vite
-   **Styling**: Tailwind CSS
-   **AI Model**: Google Gemini 2.5 Flash Lite (`@google/genai`)
-   **Market Data API**: Bybit V5 API (REST & WebSocket)
-   **Charting**: Recharts
-   **Technical Analysis**: `technicalindicators`

## 📂 Project Structure

The project uses a standard, scalable Vite project structure.

```
/
├── public/                  
├── src/
│   ├── components/          # Reusable React components
│   ├── contexts/            # React Context providers (WebSocketProvider)
│   ├── hooks/               # Custom React hooks (useSubscription)
│   ├── services/            # API interaction and business logic
│   └── utils/               # Shared utility functions (e.g., formatters)
├── .env.example             # Example environment file
├── .gitignore               
├── index.html               
├── package.json             
├── tsconfig.json            
└── vite.config.ts           
```

## 🚀 Getting Started

### Prerequisites

-   Node.js (v18 or higher)
-   npm or a compatible package manager
-   A Google Gemini API key.

### 1. Set Up Your API Key

This project requires a Google Gemini API key to function.

1.  Go to [Google AI Studio](https://aistudio.google.com/apikey) to generate your API key.
2.  Create a new file named `.env` in the root of the project.
3.  Copy the contents of `.env.example` into your new `.env` file.
4.  Paste your API key into the `VITE_API_KEY` variable:
    ```
    VITE_API_KEY="YOUR_GEMINI_API_KEY_HERE"
    ```

### 2. Installation & Running

1.  **Install Dependencies**: Open a terminal in the project root and run:
    ```bash
    npm install
    ```
2.  **Start the Development Server**: Once the installation is complete, run:
    ```bash
    npm start
    ```
3.  Your browser should automatically open to the local development server (usually `http://localhost:5173`).

### 3. How to Use

1.  **Select Asset & Interval**: Use the dropdown menus in the control panel to choose the cryptocurrency and time interval you want to analyze.
2.  **Set Confidence**: Adjust the slider to set your minimum confidence threshold for a signal to be considered "Actionable".
3.  **Run Analysis**: Click the "Run Analysis" button to fetch data and get the AI's insight.
4.  **Enable Auto-Refresh**: Toggle the "Auto-Refresh" switch to get a new analysis every time a new candle closes for your selected asset/interval.
5.  **Set Alerts**: Use the "Price Alerts" panel to monitor specific price levels.
6.  **View Results**: The analysis will appear as a detailed card, including charts, key metrics, and the AI's reasoning.

## ⚠️ Disclaimer

This project is for educational and informational purposes only. It is not financial advice. Cryptocurrency trading involves significant risk, and you should never trade with money you cannot afford to lose. Always do your own research.