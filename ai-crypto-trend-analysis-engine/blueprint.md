
# 🏗️ Technical Blueprint: AI Crypto Trend Analysis Engine

## 1. High-Level Architecture

This application is a **Client-Side Single Page Application (SPA)** built with **React** and **TypeScript**. Its architecture has been refactored for performance and scalability, centered around a **centralized WebSocket provider**.

The core design principles are:
-   **Component-Based UI**: The interface is built from a collection of reusable React components.
-   **Service Layer Abstraction**: All external API communications (Bybit, Gemini) are handled by dedicated services.
-   **Centralized State Orchestration**: The main `App.tsx` component manages the application's primary state (analysis results, alerts) and orchestrates the data flow.
-   **Centralized Real-Time Data**: A single, persistent WebSocket connection is managed by the `WebSocketProvider`. Components subscribe to the data they need through a custom `useSubscription` hook, eliminating redundant connections and simplifying component logic.

## 2. Core Data Flow (On "Run Analysis")

1.  **User Interaction**: The user selects an asset and interval in the `ControlPanel` and clicks "Run Analysis".
2.  **Orchestration**: The `handleRunAnalysis` function in `App.tsx` is triggered.
3.  **Multi-Timeframe Data Fetching**: `App.tsx` calls the `bybitService`.
    -   `getKlines()` is called concurrently for the primary, secondary, and tertiary timeframes using `Promise.all()`.
    -   `getOrderbook()` is also called to get a static snapshot for the initial analysis.
4.  **Client-Side Indicator Calculation**:
    -   The primary k-line data is passed to `indicatorService.calculateAllIndicators()` to compute a comprehensive set of indicators.
    -   The higher timeframe k-line data is passed to `indicatorService.determineTrendFromKlines()` to establish the broader market trend.
5.  **AI Analysis Request**: `App.tsx` calls `geminiService.performTrendAnalysis()`.
    -   The service constructs a detailed prompt containing the market context, all pre-calculated indicators, and the crucial multi-timeframe trend confirmation.
    -   It sends this prompt to the Gemini API with a required JSON schema for a structured, predictable response.
6.  **State Update**: `App.tsx` assembles the final `AnalysisResult` object and adds it to the `results` state array.
7.  **UI Re-render**: React renders a new `SignalCard` component with the complete analysis.

## 3. Real-Time Data Architecture (WebSockets)

The application uses a highly efficient, centralized WebSocket architecture.

1.  **`WebSocketProvider.tsx`**:
    -   On application load, this provider establishes and maintains a **single, persistent WebSocket connection** to the Bybit public stream.
    -   It manages a map of subscribed `topics` and the `callbacks` that need to be notified for each topic.
    -   It handles all connection lifecycle events, including automatic reconnection logic.

2.  **`hooks/useSubscription.ts`**:
    -   This custom hook provides a simple, declarative API for components to access the WebSocket data.
    -   A component calls `useSubscription(['topic1', 'topic2'], handleMessage)`.
    -   The hook registers the `handleMessage` callback with the `WebSocketProvider` for the specified topics.
    -   It automatically handles cleanup, unsubscribing the component when it unmounts.

3.  **Data Consumers (Components)**:
    -   **`Ticker.tsx`**: Subscribes to `tickers.{symbol}` topics for all assets.
    -   **`PriceMonitor.tsx`**: Dynamically subscribes to `tickers.{symbol}` topics based on active user alerts.
    -   **`KlineMonitor.tsx`**: Subscribes to a single `kline.{interval}.{symbol}` topic to power the event-driven auto-refresh.
    -   **`SignalCard.tsx`**: Each card subscribes to its `orderbook.1.{symbol}` topic to display live bid/ask data.

This architecture ensures that even with many components needing real-time data, only one network connection is ever used, and data is subscribed to efficiently.

## 4. Component & Service Breakdown

| Name                      | Type      | Description                                                                                                                                                             |
| ------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`App.tsx`**             | Component | **The Core Orchestrator.** Manages primary state and renders the main layout. Wraps the app in the `WebSocketProvider`.                                                  |
| **`WebSocketProvider.tsx`** | Context   | **The Heart of Real-Time.** Manages the single, persistent WebSocket connection and distributes data to subscribers.                                                       |
| **`useSubscription.ts`**  | Hook      | **The Data Connector.** Provides a clean API for components to subscribe to WebSocket data from the provider.                                                          |
| **`bybitService.ts`**     | Service   | **Bybit REST Gateway.** Handles all initial HTTP requests to Bybit for historical k-line data and order book snapshots.                                                 |
| **`geminiService.ts`**    | Service   | **AI Brain.** Constructs the expert-level prompt and manages the request/response cycle with the Google Gemini API.                                                    |
| **`indicatorService.ts`** | Service   | **Calculation Engine.** Computes all technical indicators on the client-side from raw k-line data.                                                                      |
| **`ControlPanel.tsx`**    | Component | **User Input Hub.** The main form for running an analysis.                                                                                                              |
| **`SignalCard.tsx`**      | Component | **The Main UI Card.** Displays a single analysis result, including live order book data subscribed via `useSubscription`.                                               |
| **`Ticker.tsx`**          | Component | **Live Price Ticker.** Subscribes to ticker data via `useSubscription` to display a scrolling price marquee.                                                            |
| **`PriceMonitor.tsx`**    | Component | **Headless Alert Engine.** Dynamically subscribes to ticker topics via `useSubscription` based on active alerts.                                                       |
| **`KlineMonitor.tsx`**    | Component | **Headless Refresh Engine.** Subscribes to the k-line topic via `useSubscription` to trigger event-driven refreshes.                                                   |
| ...other components       | Component | Standard presentational components for charts, alerts panel, etc.                                                                                                       |
