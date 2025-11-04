
import React, { useState, useCallback } from 'react';
import { SYMBOLS, TIME_INTERVALS, getHigherTimeframes } from './constants';
import { AnalysisResult, PriceAlert, HigherTimeframeTrends } from './types';
import { getKlines, getOrderbook } from './services/bybitService';
import { performTrendAnalysis } from './services/geminiService';
import { calculateAllIndicators, determineTrendFromKlines } from './services/indicatorService';
import { findLiquidityLevels } from './services/orderbookService';
import { WebSocketProvider } from './contexts/WebSocketProvider';
import ControlPanel from './components/ControlPanel';
import ResultsDisplay from './components/ResultsDisplay';
import AlertsPanel from './components/AlertsPanel';
import PriceMonitor from './components/PriceMonitor';
import NotificationToast from './components/NotificationToast';
import Ticker from './components/Ticker';
import KlineMonitor from './components/KlineMonitor';

interface AnalysisParams {
  symbol: string;
  interval: string;
  minConfidence: number;
}

const App: React.FC = () => {
  const [results, setResults] = useState<AnalysisResult[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [isAutoRefreshEnabled, setIsAutoRefreshEnabled] = useState<boolean>(false);
  const [lastAnalysisParams, setLastAnalysisParams] = useState<AnalysisParams | null>(null);

  // Lifted state from ControlPanel
  const [symbol, setSymbol] = useState<string>('BTCUSDT');
  const [interval, setInterval] = useState<string>(TIME_INTERVALS[2].value);
  const [minConfidence, setMinConfidence] = useState<number>(70);

  // State for Price Alerts
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [triggeredAlert, setTriggeredAlert] = useState<PriceAlert | null>(null);

  const handleRunAnalysis = useCallback(async (symbol: string, interval: string, minConfidence: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const { secondary, tertiary } = getHigherTimeframes(interval);
      
      const klinePromises = [
        getKlines(symbol, interval, 200), // Primary
        secondary ? getKlines(symbol, secondary, 100) : Promise.resolve(null),
        tertiary ? getKlines(symbol, tertiary, 100) : Promise.resolve(null)
      ];
      
      const [primaryKlines, secondaryKlines, tertiaryKlines, orderbook] = await Promise.all([
        ...klinePromises,
        getOrderbook(symbol, 50), // Fetch deeper order book
      ]);

      if (!primaryKlines || primaryKlines.length < 52) { // Updated for Ichimoku
        throw new Error('Not enough market data for the primary interval to perform analysis.');
      }

      // Analyze order book for liquidity walls
      const liquidityAnalysis = findLiquidityLevels(orderbook);

      // Determine trends on higher timeframes
      const higherTimeframeTrends: HigherTimeframeTrends = {};
      if (secondaryKlines && secondary) {
        higherTimeframeTrends[secondary] = determineTrendFromKlines(secondaryKlines);
      }
      if (tertiaryKlines && tertiary) {
        higherTimeframeTrends[tertiary] = determineTrendFromKlines(tertiaryKlines);
      }
      
      const indicators = calculateAllIndicators(primaryKlines);
      const analysis = await performTrendAnalysis(symbol, interval, primaryKlines, indicators, higherTimeframeTrends, liquidityAnalysis);
      
      const newResult: AnalysisResult = {
        id: `${symbol}-${interval}-${Date.now()}`,
        symbol,
        interval,
        analysis,
        klines: primaryKlines,
        indicators,
        orderbook,
        orderbookAnalysis: liquidityAnalysis,
        current_price: primaryKlines[primaryKlines.length - 1].close,
        timestamp: new Date(),
        confidence: analysis.confidence,
        meets_confidence: analysis.confidence >= minConfidence,
      };

      setResults(prevResults => [newResult, ...prevResults]);

    } catch (err: any) {
      console.error(err);
      setError(err.message || 'An unexpected error occurred during analysis.');
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  const runNewAnalysis = useCallback(() => {
    setLastAnalysisParams({ symbol, interval, minConfidence });
    handleRunAnalysis(symbol, interval, minConfidence);
  }, [symbol, interval, minConfidence, handleRunAnalysis]);

  const handleNewCandle = useCallback(() => {
    if (isAutoRefreshEnabled && lastAnalysisParams && !isLoading) {
      // Check if control panel selection matches the auto-refresh target
      if (symbol === lastAnalysisParams.symbol && interval === lastAnalysisParams.interval) {
        console.log(`New candle detected for ${lastAnalysisParams.symbol}. Triggering auto-refresh.`);
        handleRunAnalysis(lastAnalysisParams.symbol, lastAnalysisParams.interval, lastAnalysisParams.minConfidence);
      } else {
        // Selections do not match, prompt the user
        const intervalLabel = TIME_INTERVALS.find(i => i.value === lastAnalysisParams.interval)?.label || `${lastAnalysisParams.interval} interval`;
        const confirmed = window.confirm(
          `A new candle for ${lastAnalysisParams.symbol} (${intervalLabel}) is ready for auto-refresh.\n\nYour current selection is ${symbol}.\n\nDo you want to switch to ${lastAnalysisParams.symbol} and run the analysis?`
        );

        if (confirmed) {
          // User wants to switch. Update controls and run analysis.
          setSymbol(lastAnalysisParams.symbol);
          setInterval(lastAnalysisParams.interval);
          console.log(`Switching to ${lastAnalysisParams.symbol} and running analysis.`);
          handleRunAnalysis(lastAnalysisParams.symbol, lastAnalysisParams.interval, lastAnalysisParams.minConfidence);
        } else {
          console.log(`Auto-refresh for ${lastAnalysisParams.symbol} skipped by user.`);
        }
      }
    }
  }, [isAutoRefreshEnabled, lastAnalysisParams, isLoading, handleRunAnalysis, symbol, interval]);

  // Alert handlers
  const handleAddAlert = (alert: Omit<PriceAlert, 'id' | 'triggered'>) => {
    setAlerts(prev => [...prev, { ...alert, id: Date.now(), triggered: false }]);
  };

  const handleRemoveAlert = (id: number) => {
    setAlerts(prev => prev.filter(a => a.id !== id));
  };

  const handleAlertTriggered = (triggered: PriceAlert) => {
    setTriggeredAlert(triggered);
    setAlerts(prev => prev.map(a => a.id === triggered.id ? { ...a, triggered: true } : a));
  };

  const handleCloseToast = () => {
    setTriggeredAlert(null);
  };

  return (
    <WebSocketProvider>
      <Ticker symbols={SYMBOLS} />
      <div className="min-h-screen bg-gray-900 text-gray-100 p-4 sm:p-6 lg:p-8 pt-20">
        {isAutoRefreshEnabled && lastAnalysisParams && (
            <KlineMonitor 
                symbol={lastAnalysisParams.symbol}
                interval={lastAnalysisParams.interval}
                onNewCandle={handleNewCandle}
            />
        )}
        <PriceMonitor alerts={alerts} onAlertTriggered={handleAlertTriggered} />
        {triggeredAlert && <NotificationToast alert={triggeredAlert} onClose={handleCloseToast} />}

        <div className="max-w-7xl mx-auto">
          <header className="text-center mb-8">
            <h1 className="text-4xl sm:text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-sky-400 to-emerald-400">
              AI Trend Analysis Engine
            </h1>
            <p className="mt-2 text-lg text-gray-400">
              Leveraging Gemini for Real-Time Crypto Market Insights
            </p>
          </header>

          <main>
            <ControlPanel
              symbols={SYMBOLS}
              intervals={TIME_INTERVALS}
              onRunAnalysis={runNewAnalysis}
              isLoading={isLoading}
              isAutoRefreshEnabled={isAutoRefreshEnabled}
              onToggleAutoRefresh={setIsAutoRefreshEnabled}
              symbol={symbol}
              onSymbolChange={setSymbol}
              interval={interval}
              onIntervalChange={setInterval}
              minConfidence={minConfidence}
              onMinConfidenceChange={setMinConfidence}
            />

            {error && (
              <div className="mt-6 p-4 bg-red-900/50 border border-red-600 text-red-300 rounded-lg text-center">
                <p className="font-semibold">Analysis Failed</p>
                <p>{error}</p>
              </div>
            )}
            
            <div className="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-8">
              <div className="lg:col-span-2">
                <ResultsDisplay results={results} isLoading={isLoading} />
              </div>
              <div className="lg:col-span-1">
                <AlertsPanel
                  symbols={SYMBOLS}
                  alerts={alerts}
                  onAddAlert={handleAddAlert}
                  onRemoveAlert={handleRemoveAlert}
                />
              </div>
            </div>
          </main>
        </div>
      </div>
    </WebSocketProvider>
  );
};

export default App;