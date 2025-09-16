'use client';

import { useState, useEffect, useCallback } from 'react';
import { DashboardHeader } from '@/components/dashboard/header';
import { MarketData } from '@/components/dashboard/market-data';
import { TradingViewChart } from '@/components/dashboard/tradingview-chart';
import { OrderBook } from '@/components/dashboard/order-book';
import { RecentTrades } from '@/components/dashboard/recent-trades';
import { AiSignal } from '@/components/dashboard/ai-signal';
import { IndicatorSuite } from '@/components/dashboard/indicator-suite';
import { SYMBOLS, TIME_FRAMES } from '@/lib/constants';
import type { IndicatorSettings as IndicatorSettingsType } from '@/lib/indicators';
import { defaultIndicatorSettings } from '@/lib/indicators';
import { VolumePressure } from '@/components/dashboard/volume-pressure';
import { type RecentTrade } from '@/lib/bybit-api';
import { useBybitWebSocket } from '@/hooks/use-bybit-websocket';

const MAX_VISIBLE_TRADES = 50;

export default function Home() {
  const [symbol, setSymbol] = useState(SYMBOLS[0]);
  const [timeframe, setTimeframe] = useState(TIME_FRAMES[3]);
  const [indicatorSettings, setIndicatorSettings] = useState<IndicatorSettingsType>(defaultIndicatorSettings);

  const [trades, setTrades] = useState<RecentTrade[]>([]);
  const [newTradeIds, setNewTradeIds] = useState<Set<string>>(new Set());

  const tradeTopic = `publicTrade.${symbol}`;
  const { lastMessage, connectionStatus, reconnect } = useBybitWebSocket(tradeTopic);

  useEffect(() => {
    // Clear trades when symbol changes
    setTrades([]);
  }, [symbol]);

  useEffect(() => {
    if (lastMessage && lastMessage.topic === tradeTopic && Array.isArray(lastMessage.data)) {
        const newTrades = lastMessage.data.map(t => ({
            execId: t.i,
            price: t.p,
            qty: t.v,
            side: t.S,
            execTime: t.T,
            isBlockTrade: t.m,
        })) as RecentTrade[];
        
        setTrades(prev => [ ...newTrades, ...prev].slice(0, MAX_VISIBLE_TRADES));
        
        const newIds = new Set(newTrades.map(t => t.execId));
        setNewTradeIds(newIds);

        const highlightTimeout = setTimeout(() => {
            setNewTradeIds(current => {
                const updated = new Set(current);
                newIds.forEach(id => updated.delete(id));
                return updated;
            });
        }, 1500);

        return () => clearTimeout(highlightTimeout);
    }
  }, [lastMessage, tradeTopic]);

  return (
    <div className="flex flex-col min-h-screen bg-background text-foreground">
      <DashboardHeader
        symbol={symbol}
        setSymbol={setSymbol}
        timeframe={timeframe}
        setTimeframe={setTimeframe}
      />
      <main className="flex-1 p-4 md:p-6 lg:p-8">
        <div className="grid gap-6">
          <MarketData symbol={symbol} />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 flex flex-col gap-6">
              <TradingViewChart symbol={symbol} timeframe={timeframe} />
              <AiSignal symbol={symbol} timeframe={timeframe} indicatorSettings={indicatorSettings} />
            </div>
            <div className="flex flex-col gap-6">
              <OrderBook symbol={symbol} />
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-6">
                <RecentTrades 
                  trades={trades}
                  newTradeIds={newTradeIds}
                  wsStatus={connectionStatus}
                  onReconnect={reconnect}
                />
                <VolumePressure trades={trades} symbol={symbol} />
              </div>
              <IndicatorSuite 
                symbol={symbol} 
                timeframe={timeframe}
                settings={indicatorSettings}
                onSettingsChange={setIndicatorSettings}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
