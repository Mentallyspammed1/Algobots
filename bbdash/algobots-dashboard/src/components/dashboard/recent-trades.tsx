'use client';
import { useMemo, useRef } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { RecentTrade } from '@/lib/bybit-api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { RefreshCw, Wifi, WifiOff, AlertCircle } from 'lucide-react';

const LOADING_ROW_COUNT = 15;

const formatTime = (timestamp: string | number | undefined): string => {
  if (timestamp === undefined || timestamp === null) return '...';
  try {
    const numericTimestamp = Number(timestamp);
    if (isNaN(numericTimestamp) || !isFinite(numericTimestamp) || numericTimestamp <= 0) return 'Invalid Time';
    return format(new Date(numericTimestamp), 'HH:mm:ss');
  } catch (e) {
    console.error("Error formatting time:", e);
    return 'Invalid Time';
  }
};

const formatAmount = (amountStr: string | undefined): string => {
    if (!amountStr) return '0.000';
    const amount = parseFloat(amountStr);
    if (isNaN(amount)) return '0.000';
    if (amount >= 1_000_000) return `${(amount / 1_000_000).toFixed(2)}M`;
    if (amount >= 1000) return `${(amount / 1000).toFixed(2)}K`;
    if (amount < 0.01 && amount > 0) return amount.toFixed(5);
    if (amount < 0.0001 && amount > 0) return amount.toFixed(6);
    return amount.toFixed(3);
};

const LoadingRows = ({ count = LOADING_ROW_COUNT }) => (
  Array.from({ length: count }).map((_, i) => (
      <TableRow key={i} className="text-xs" aria-hidden="true">
          <TableCell className="p-2"><Skeleton className="h-4 w-full" /></TableCell>
          <TableCell className="p-2"><Skeleton className="h-4 w-full" /></TableCell>
          <TableCell className="p-2"><Skeleton className="h-4 w-full" /></TableCell>
      </TableRow>
  ))
);

interface RecentTradesProps {
  trades: RecentTrade[];
  newTradeIds: Set<string>;
  wsStatus: 'connecting' | 'connected' | 'reconnecting' | 'disconnected';
  onReconnect: () => void;
  className?: string;
}

export function RecentTrades({ trades, newTradeIds, wsStatus, onReconnect, className }: RecentTradesProps) {
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  
  const isLoading = wsStatus === 'connecting' && trades.length === 0;

  const renderContent = useMemo(() => {
    if (isLoading) {
      return <LoadingRows />;
    }

    if (wsStatus === 'disconnected' && trades.length === 0) {
      return (
        <TableRow>
          <TableCell colSpan={3} className="text-center p-4" role="alert">
            <div className="flex flex-col items-center space-y-2">
              <AlertCircle className="h-5 w-5 text-red-500" />
              <p className="text-sm text-red-500">Connection failed. Please try to reconnect.</p>
              <Button onClick={onReconnect} variant="outline" size="sm">
                <RefreshCw className="h-4 w-4 mr-1" />
                Reconnect
              </Button>
            </div>
          </TableCell>
        </TableRow>
      );
    }
    
    if (trades.length > 0) {
      return trades.map((trade) => {
        const isNew = newTradeIds.has(trade.execId);
        return (
            <TableRow 
                key={trade.execId} 
                className={cn(
                    "text-xs font-mono transition-all duration-1000",
                    isNew && trade.side === 'Buy' && 'bg-green-500/30',
                    isNew && trade.side === 'Sell' && 'bg-red-500/30'
                )}
            >
                <TableCell className="p-2">{formatTime(trade.execTime)}</TableCell>
                <TableCell className={`p-2 font-medium ${trade.side === 'Buy' ? 'text-chart-2' : 'text-chart-5'}`}>
                  {parseFloat(trade.price).toFixed(2)}
                </TableCell>
                <TableCell className="p-2 text-right">{formatAmount(trade.qty)}</TableCell>
            </TableRow>
        );
      });
    }

    return (
        <TableRow>
          <TableCell colSpan={3} className="text-center text-muted-foreground p-4">Waiting for trades...</TableCell>
        </TableRow>
    );
  }, [isLoading, wsStatus, trades, newTradeIds, onReconnect]);

  const WsStatusIndicator = () => {
    switch (wsStatus) {
        case 'connected': return <Wifi className="h-4 w-4 text-green-500" title="Connected" />;
        case 'connecting':
        case 'reconnecting': return <RefreshCw className="h-4 w-4 text-yellow-500 animate-spin" title={wsStatus === 'connecting' ? 'Connecting...': 'Reconnecting...'} />;
        case 'disconnected':
        default: return <WifiOff className="h-4 w-4 text-red-500" title="Disconnected" />;
    }
  }

  return (
    <Card className={cn("", className)}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span>Recent Trades</span>
          </div>
          <div className="flex items-center space-x-2">
            {wsStatus === 'disconnected' && (
                <Button variant="ghost" size="sm" onClick={onReconnect} className="h-8 w-8 p-0" title="Reconnect">
                    <RefreshCw className="h-4 w-4"/>
                </Button>
            )}
            <WsStatusIndicator />
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ScrollArea className="h-[200px]" ref={scrollAreaRef}>
          <Table>
            <TableHeader className="sticky top-0 bg-background">
              <TableRow className="text-xs">
                <TableHead className="p-2 w-[33%]">Time</TableHead>
                <TableHead className="p-2 w-[33%]">Price (USDT)</TableHead>
                <TableHead className="p-2 text-right w-[33%]">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {renderContent}
            </TableBody>
          </Table>
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
