'use client';
import { useState, useEffect, useMemo } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { TrendingUp, TrendingDown, Scale } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { RecentTrade } from '@/lib/bybit-api';

interface VolumePressureData {
    buyVolume: number;
    sellVolume: number;
    totalVolume: number;
    buyPercentage: number;
    sellPercentage: number;
}

const calculateVolumePressure = (trades: RecentTrade[]): VolumePressureData => {
    const emptyState = { buyVolume: 0, sellVolume: 0, totalVolume: 0, buyPercentage: 50, sellPercentage: 50 };
    if (!trades || trades.length === 0) {
        return emptyState;
    }

    let buyVolume = 0;
    let sellVolume = 0;

    trades.forEach((trade) => {
        const volume = parseFloat(trade.qty);
        if (isNaN(volume)) return;

        if (trade.side === 'Buy') {
            buyVolume += volume;
        } else {
            sellVolume += volume;
        }
    });

    const totalVolume = buyVolume + sellVolume;
    if (totalVolume === 0) {
        return emptyState;
    }

    return {
        buyVolume,
        sellVolume,
        totalVolume,
        buyPercentage: (buyVolume / totalVolume) * 100,
        sellPercentage: (sellVolume / totalVolume) * 100,
    };
};


interface VolumePressureProps {
  symbol: string;
  trades: RecentTrade[];
}

const formatVolume = (num: number | undefined, symbol: string): string => {
  if (num === undefined || isNaN(num)) return '0';
  
  const baseSymbol = symbol.replace('USDT', '');
  
  if (num >= 1_000_000_000) {
    return `${(num / 1_000_000_000).toFixed(2)}B ${baseSymbol}`;
  }
  if (num >= 1_000_000) {
    return `${(num / 1_000_000).toFixed(2)}M ${baseSymbol}`;
  }
  if (num >= 1_000) {
    return `${(num / 1_000).toFixed(1)}K ${baseSymbol}`;
  }
  if (num < 0.01 && num > 0) {
    return `${num.toFixed(5)} ${baseSymbol}`;
  }
  return `${num.toFixed(2)} ${baseSymbol}`;
};

export function VolumePressure({ symbol, trades }: VolumePressureProps) {
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const data = useMemo(() => {
    if (trades.length > 0) {
        setLastUpdated(new Date());
    }
    return calculateVolumePressure(trades)
  }, [trades]);

  const formatLastUpdated = (date: Date | null): string => {
    if (!date) return '';
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  };

  const renderContent = () => {
    if (trades.length === 0) {
      return (
        <div className="space-y-4">
          <Skeleton className="h-6 w-3/4 mx-auto" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-6 w-1/2 mx-auto" />
        </div>
      );
    }
    
    if (data) {
      const buyPressureHigher = data.buyPercentage > data.sellPercentage;
      
      return (
        <div className="space-y-3">
          <div className="flex justify-between items-center text-sm font-medium">
            <div className={cn("flex items-center gap-2", buyPressureHigher ? "text-chart-2 font-semibold" : "text-muted-foreground")}>
              <TrendingUp />
              <span>Buy Pressure</span>
            </div>
            <div className={cn("flex items-center gap-2", !buyPressureHigher ? "text-chart-5 font-semibold" : "text-muted-foreground")}>
              <span>Sell Pressure</span>
              <TrendingDown />
            </div>
          </div>
          
          <div className="relative flex h-4 w-full rounded-full overflow-hidden bg-muted">
            <div className={cn("h-full transition-all duration-500 ease-out", buyPressureHigher ? "bg-chart-2" : "bg-chart-2/70")} style={{ width: `${data.buyPercentage}%` }}/>
            <div className={cn("h-full transition-all duration-500 ease-out", !buyPressureHigher ? "bg-chart-5" : "bg-chart-5/70")} style={{ width: `${data.sellPercentage}%` }} />
            <div className="absolute top-0 left-1/2 transform -translate-x-1/2 w-0.5 h-full bg-background/50" />
          </div>
          
          <div className="flex justify-between items-center text-xs font-mono">
            <span className={cn(buyPressureHigher && "font-semibold")}>
              {data.buyPercentage.toFixed(2)}%
            </span>
            <span className={cn(!buyPressureHigher && "font-semibold text-chart-5")}>
              {data.sellPercentage.toFixed(2)}%
            </span>
          </div>
          
          <div className="text-center pt-2 border-t border-border">
            <div className="flex items-center justify-center gap-2 mb-1">
              <Scale className="h-4 w-4 text-muted-foreground" />
              <p className="text-sm font-semibold text-muted-foreground">
                Total Volume (from feed)
              </p>
            </div>
            <p className="text-lg font-bold font-mono">
              {formatVolume(data.totalVolume, symbol)}
            </p>
            {lastUpdated && (
              <p className="text-xs text-muted-foreground mt-1">
                Updated: {formatLastUpdated(lastUpdated)}
              </p>
            )}
          </div>
        </div>
      );
    }
    
    return (
      <div className="text-center text-muted-foreground space-y-3">
        <p>Waiting for trade data...</p>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span>Volume Pressure</span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {renderContent()}
      </CardContent>
    </Card>
  );
}
