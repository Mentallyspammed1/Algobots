'use client';

import { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { TrendingUp, TrendingDown, BarChart, AlertCircle, Waves } from 'lucide-react';
import type { TickerInfo } from '@/lib/bybit-api';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { useBybitWebSocket } from '@/hooks/use-bybit-websocket';
import { getTicker } from '@/lib/bybit-api';


interface MarketDataProps {
  symbol: string;
}

export function MarketData({ symbol }: MarketDataProps) {
  const [data, setData] = useState<Partial<TickerInfo>>({});
  const [priceChange, setPriceChange] = useState<'up' | 'down' | 'same'>('same');

  const topic = `tickers.${symbol}`;
  const { lastMessage, connectionStatus, reconnect } = useBybitWebSocket(topic);

  // Fetch initial data via REST API
  useEffect(() => {
    let isMounted = true;
    async function fetchInitialData() {
      const initialData = await getTicker(symbol);
      if (isMounted && initialData) {
        setData(initialData);
      }
    }
    fetchInitialData();
    return () => { isMounted = false; };
  }, [symbol]);

  // Update with WebSocket data
  useEffect(() => {
    if (lastMessage && lastMessage.topic === topic && lastMessage.data) {
      setData(prevData => {
        const newData = { ...prevData, ...lastMessage.data };
        if (prevData.lastPrice && newData.lastPrice) {
          const priceDiff = parseFloat(newData.lastPrice) - parseFloat(prevData.lastPrice);
          setPriceChange(priceDiff > 0 ? 'up' : priceDiff < 0 ? 'down' : 'same');
        } else {
          setPriceChange('same');
        }
        return newData;
      });
    }
  }, [lastMessage, topic]);

  const formatNumber = (numStr: string | undefined, precision = 2) => {
    if (!numStr) return '--';
    const num = parseFloat(numStr);
    if (isNaN(num)) return '--';
    return num.toLocaleString(undefined, { maximumFractionDigits: precision, minimumFractionDigits: precision });
  };

  const formatVolume = (numStr: string | undefined) => {
    if (!numStr) return '--';
    const num = parseFloat(numStr);
    if (isNaN(num)) return '--';
    if (num > 1_000_000_000) return `${(num / 1_000_000_000).toFixed(2)}B`;
    if (num > 1_000_000) return `${(num / 1_000_000).toFixed(2)}M`;
    if (num > 1_000) return `${(num / 1_000).toFixed(1)}K`;
    return num.toFixed(2);
  };
  
  const pricePcnt = data?.price24hPcnt ? parseFloat(data.price24hPcnt) : 0;
  const isPositive = pricePcnt >= 0;
  const priceColor = priceChange === 'up' ? 'text-chart-2' : priceChange === 'down' ? 'text-chart-5' : 'text-inherit';
  const isLoading = Object.keys(data).length === 0 && connectionStatus === 'connecting';

  const renderCardContent = (title: string, value: string | undefined, formatter: (val: string | undefined) => string, icon: React.ReactNode, prefix = '', suffix = '', isLoading?: boolean) => {
    return (
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{title}</CardTitle>
                {icon}
            </CardHeader>
            <CardContent>
                {isLoading ? <Skeleton className="h-8 w-3/4" /> : <div className="text-2xl font-bold">{prefix}{formatter(value)}{suffix}</div>}
            </CardContent>
        </Card>
    );
  }

  if (connectionStatus === 'disconnected' && Object.keys(data).length === 0) {
      return (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
              <Card className="md:col-span-2 lg:col-span-5">
                  <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                      <CardTitle className="text-sm font-medium text-red-500">Connection Error</CardTitle>
                      <AlertCircle className="h-4 w-4 text-red-500" />
                  </CardHeader>
                  <CardContent>
                      <p className="text-sm text-red-500">Failed to connect to live market data feed.</p>
                      <button onClick={reconnect} className="text-sm text-blue-500 underline mt-2">Retry</button>
                  </CardContent>
              </Card>
          </div>
      );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Last Price</CardTitle>
                <span className={cn('text-sm font-semibold', isPositive ? 'text-chart-2' : 'text-chart-5')}>
                    {isPositive ? '+' : ''}{(pricePcnt * 100).toFixed(2)}%
                </span>
            </CardHeader>
            <CardContent>
                {isLoading ? <Skeleton className="h-8 w-3/4" /> : (
                    <div className={cn("text-2xl font-bold transition-colors duration-200", priceColor)}>
                        ${formatNumber(data.lastPrice)}
                    </div>
                )}
            </CardContent>
        </Card>
      {renderCardContent('24h High', data.highPrice24h, formatNumber, <TrendingUp className="h-4 w-4 text-muted-foreground" />, '$','', isLoading)}
      {renderCardContent('24h Low', data.lowPrice24h, formatNumber, <TrendingDown className="h-4 w-4 text-muted-foreground" />, '$','', isLoading)}
      {renderCardContent('24h Volume', data.volume24h, formatVolume, <BarChart className="h-4 w-4 text-muted-foreground" />, '', ` ${symbol.replace('USDT', '')}`, isLoading)}
      {renderCardContent('24h Turnover', data.turnover24h, formatVolume, <Waves className="h-4 w-4 text-muted-foreground" />, '$', ' USDT', isLoading)}
    </div>
  );
}
