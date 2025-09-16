# Bybit Edge - AI Trading Dashboard

Bybit Edge is a sophisticated, AI-powered cryptocurrency trading dashboard built with Next.js and Genkit. It provides traders with real-time market data, advanced charting, and AI-generated trading signals to make informed decisions.

![Bybit Edge Screenshot](https://storage.googleapis.com/aifirebase.appspot.com/stark-tours-387313/gen_41b11e737c35e389.png)

## Key Features

- **Real-Time Market Data:** Live price updates, 24-hour high/low, volume, and turnover.
- **Advanced Charting:** Integrates TradingView charts for detailed technical analysis.
- **AI Trading Signal Generation:** Uses a Genkit AI agent to analyze market data and provide 'Buy', 'Sell', or 'Hold' signals with entry, take-profit, and stop-loss levels.
- **Comprehensive Indicator Suite:** A full panel of configurable technical indicators like RSI, MACD, Bollinger Bands, Supertrend, and more.
- **Live Order Book:** Real-time visualization of market depth with bids and asks.
- **Recent Trades Feed:** A live feed of the latest public trades for the selected symbol.
- **Volume Pressure Analysis:** A custom widget that calculates and displays the buy vs. sell volume pressure in real-time.
- **Customizable & Modern UI:** Built with ShadCN UI and Tailwind CSS, featuring a sleek dark/light mode theme.
- **Robust & Performant:** Leverages Next.js App Router, Server Actions, and real-time WebSocket connections.

## Tech Stack

- **Framework:** [Next.js](https://nextjs.org/) (App Router)
- **Language:** [TypeScript](https://www.typescriptlang.org/)
- **AI:** [Genkit](https://firebase.google.com/docs/genkit)
- **UI:** [React](https://react.dev/), [ShadCN UI](https://ui.shadcn.com/), [Tailwind CSS](https://tailwindcss.com/)
- **Charting:** [TradingView Lightweight Charts](https://www.tradingview.com/lightweight-charts/)
- **Market Data:** [Bybit API](https://bybit-exchange.github.io/docs/v5/intro) (via REST and WebSockets)

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Node.js (v18 or later)
- npm or yarn

### Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-name>
    ```

2.  **Install dependencies:**
    ```bash
    npm install
    ```

3.  **Set up environment variables:**
    Create a `.env` file in the root of the project and add your Gemini API key. You can get one from [Google AI Studio](https://aistudio.google.com/app/apikey).

    ```
    GEMINI_API_KEY=your_gemini_api_key_here
    ```

### Running the Application

This project requires two separate development servers to run concurrently: one for the Next.js frontend and one for the Genkit AI backend.

1.  **Run the Next.js development server:**
    This server handles the web application.

    ```bash
    npm run dev
    ```
    The application will be available at [http://localhost:9002](http://localhost:9002).

2.  **Run the Genkit development server:**
    This server runs the AI flows and provides the Genkit Dev UI for debugging.

    ```bash
    npm run genkit:dev
    ```
    The Genkit Dev UI will be available at [http://localhost:4000](http://localhost:4000).

## Project Structure

- **`src/app/`**: Contains the main application pages and API routes, following the Next.js App Router structure.
- **`src/ai/`**: Houses all AI-related code, including Genkit flows and tool definitions.
  - **`flows/`**: Defines the main AI agent logic for generating trading signals.
  - **`genkit.ts`**: The core Genkit configuration file.
- **`src/components/`**: All React components used in the application.
  - **`dashboard/`**: Components specific to the trading dashboard (e.g., `OrderBook`, `AiSignal`).
  - **`ui/`**: Reusable UI components from ShadCN.
- **`src/lib/`**: Core libraries, helper functions, and API integrations.
  - **`actions.ts`**: Next.js Server Actions for interacting with the backend.
  - **`bybit-api.ts`**: A wrapper for fetching data from the Bybit REST API and WebSockets.
  - **`indicators.ts`**: All logic for calculating technical indicators.
  - **`constants.ts`**: Shared constants like trading symbols and timeframes.
- **`src/hooks/`**: Custom React hooks.