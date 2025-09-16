'use client';

import { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { useBybitWebSocket } from '@/hooks/use-bybit-websocket';

const ORDER_BOOK_DEPTH = 50; // Bybit supports 1, 50, 200, 500
const MAX_DISPLAY_ROWS = 20;

interface OrderBookProps {
  symbol: string;
  className?: string;
}

export function OrderBook({ symbol, className }: OrderBookProps) {
  const [bids, setBids] = useState<[string, string][]>([]);
  const [asks, setAsks] = useState<[string, string][]>([]);
  const [lastPrice, setLastPrice] = useState<string | null>(null);
  const [priceChange, setPriceChange] = useState<'up' | 'down' | 'same'>('same');

  const orderbookTopic = `orderbook.${ORDER_BOOK_DEPTH}.${symbol}`;
  const tickerTopic = `tickers.${symbol}`;
  
  const { lastMessage: orderbookMessage, connectionStatus } = useBybitWebSocket(orderbookTopic);
  const { lastMessage: tickerMessage } = useBybitWebSocket(tickerTopic);
  
  // Reset state on symbol change
  useEffect(() => {
    setBids([]);
    setAsks([]);
    setLastPrice(null);
  }, [symbol]);

  useEffect(() => {
    if (orderbookMessage && orderbookMessage.topic === orderbookTopic) {
        const { type, data: orderData } = orderbookMessage;
        if (type === 'snapshot') {
            setBids(orderData.b);
            setAsks(orderData.a);
        } else if (type === 'delta') {
            const update = (current: [string, string][], delta: [string, string][]) => {
                const newMap = new Map(current);
                delta.forEach(([price, size]) => {
                    if (size === '0') {
                        newMap.delete(price);
                    } else {
                        newMap.set(price, size);
                    }
                });
                return Array.from(newMap.entries());
            };
            setBids(prev => update(prev, orderData.b).sort((a,b) => parseFloat(b[0]) - parseFloat(a[0])));
            setAsks(prev => update(prev, orderData.a).sort((a,b) => parseFloat(a[0]) - parseFloat(b[0])));
        }
    }
  }, [orderbookMessage, orderbookTopic]);

  useEffect(() => {
    if (tickerMessage && tickerMessage.topic === tickerTopic) {
        const newPrice = tickerMessage.data.lastPrice;
        if (newPrice) {
            setLastPrice(prev => {
                if(prev) {
                    const priceDiff = parseFloat(newPrice) - parseFloat(prev);
                    setPriceChange(priceDiff > 0 ? 'up' : priceDiff < 0 ? 'down' : 'same');
                }
                return newPrice;
            });
        }
    }
  }, [tickerMessage, tickerTopic]);

  const renderRows = useMemo(() => {
    let cumulativeBids = 0;
    const processedBids = bids.slice(0, MAX_DISPLAY_ROWS).map(([price, size]) => {
      cumulativeBids += parseFloat(size);
      return { price, size, total: cumulativeBids };
    });

    let cumulativeAsks = 0;
    const processedAsks = asks.slice(0, MAX_DISPLAY_ROWS).map(([price, size]) => {
      cumulativeAsks += parseFloat(size);
      return { price, size, total: cumulativeAsks };
    }).reverse();

    const maxTotal = Math.max(cumulativeBids, cumulativeAsks);

    const createRow = (d: { price: string; size: string; total: number; }, type: 'bid' | 'ask') => {
        const depth = maxTotal > 0 ? (d.total / maxTotal) * 100 : 0;
        return (
            <TableRow key={`${type}-${d.price}`} className="text-xs">
                <TableCell className={cn("p-1 text-left font-mono", type === 'bid' ? 'text-chart-2' : 'text-chart-5')}>{parseFloat(d.price).toFixed(2)}</TableCell>
                <TableCell className="p-1 text-right font-mono">{parseFloat(d.size).toFixed(4)}</TableCell>
                <TableCell className="p-1 text-right font-mono relative">
                    {d.total.toFixed(4)}
                    <div 
                        className={cn("absolute inset-y-0 -z-10", type === 'bid' ? "right-0 bg-chart-2/20" : "left-0 bg-chart-5/20")} 
                        style={{
                            width: `calc(${depth}% + 1rem)`, // Cover padding
                            left: type === 'ask' ? '-0.5rem' : 'auto',
                            right: type === 'bid' ? '-0.5rem' : 'auto'
                        }}
                    ></div>
                </TableCell>
            </TableRow>
        );
    }

    return {
        asks: processedAsks.map(d => createRow(d, 'ask')),
        bids: processedBids.map(d => createRow(d, 'bid')),
    }
  }, [bids, asks]);

  const isLoading = connectionStatus === 'connecting' && bids.length === 0 && asks.length === 0;

  return (
    <Card className={cn(className)}>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Order Book</CardTitle>
        <div className="flex items-center gap-2">
            { connectionStatus === 'connected' && <Wifi className="h-4 w-4 text-green-500" /> }
            { connectionStatus === 'connecting' && <RefreshCw className="h-4 w-4 animate-spin text-yellow-500" /> }
            { connectionStatus === 'reconnecting' && <RefreshCw className="h-4 w-4 animate-spin text-yellow-500" /> }
            { connectionStatus === 'disconnected' && <WifiOff className="h-4 w-4 text-red-500" /> }
        </div>
      </CardHeader>
      <CardContent className="p-0">
        <div className="grid grid-cols-1">
          <div className="h-[250px]">
            <ScrollArea className="h-full">
              <Table className="relative">
                <TableHeader>
                    <TableRow className="text-xs">
                        <TableHead className="p-1 w-1/3 text-left">Price (USDT)</TableHead>
                        <TableHead className="p-1 w-1/3 text-right">Size ({symbol.replace('USDT', '')})</TableHead>
                        <TableHead className="p-1 w-1/3 text-right">Total</TableHead>
                    </TableRow>
                </TableHeader>
                <TableBody>
                    {isLoading ? Array.from({length: 10}).map((_, i) => <TableRow key={i}><TableCell colSpan={3}><Skeleton className="h-4 w-full" /></TableCell></TableRow>) : renderRows.asks}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>
          <div className={cn("text-lg font-bold text-center py-1 border-y transition-colors", priceChange === 'up' ? 'text-chart-2' : priceChange === 'down' ? 'text-chart-5' : '')}>
            {lastPrice ? parseFloat(lastPrice).toFixed(2) : <Skeleton className="h-6 w-1/3 mx-auto" />}
          </div>
          <div className="h-[250px]">
            <ScrollArea className="h-full">
              <Table className="relative">
                <TableBody>
                    {isLoading ? Array.from({length: 10}).map((_, i) => <TableRow key={i}><TableCell colSpan={3}><Skeleton className="h-4 w-full" /></TableCell></TableRow>) : renderRows.bids}
                </TableBody>
              </Table>
            </ScrollArea>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
