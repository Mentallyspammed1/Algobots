'use client';

import { useState, useEffect } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { getKline, calculateIndicators, type IndicatorData, type IndicatorSettings } from '@/lib/indicators';
import {
  Gauge,
  TrendingUp,
  TrendingDown,
  Waves,
  Percent,
  BarChart2,
  GitCommitHorizontal,
  MoveHorizontal,
  Orbit,
  Cloud,
  Sigma,
  ChevronsUpDown,
  Zap,
  Settings,
  LineChart,
  Fish,
} from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Button } from '@/components/ui/button';
import { IndicatorSettingsDialog } from './indicator-settings';

interface IndicatorSuiteProps {
  symbol: string;
  timeframe: string;
  settings: IndicatorSettings;
  onSettingsChange: (settings: IndicatorSettings) => void;
}

const getSentiment = (value: number | undefined, upper: number, lower: number) => {
  if (value === undefined || value === null || isNaN(value)) return { text: 'N/A', color: 'text-muted-foreground' };
  if (value > upper) return { text: 'Overbought', color: 'text-chart-5' };
  if (value < lower) return { text: 'Oversold', color: 'text-chart-2' };
  return { text: 'Neutral', color: 'text-muted-foreground' };
};

const getBullishBearish = (value1: number | undefined | null, value2: number | undefined | null) => {
  if (value1 === undefined || value2 === undefined || value1 === null || value2 === null || isNaN(value1) || isNaN(value2)) return { text: 'N/A', color: 'text-muted-foreground', icon: <ChevronsUpDown className="h-4 w-4" /> };
  if (value1 > value2) return { text: 'Bullish', color: 'text-chart-2', icon: <TrendingUp className="h-4 w-4" /> };
  return { text: 'Bearish', color: 'text-chart-5', icon: <TrendingDown className="h-4 w-4" /> };
};

const getSupertrendSentiment = (direction: 'buy' | 'sell' | undefined) => {
    if (direction === 'buy') return { text: 'Buy Signal', color: 'text-chart-2', icon: <TrendingUp className="h-4 w-4" /> };
    if (direction === 'sell') return { text: 'Sell Signal', color: 'text-chart-5', icon: <TrendingDown className="h-4 w-4" /> };
    return { text: 'Neutral', color: 'text-muted-foreground', icon: <ChevronsUpDown className="h-4 w-4" /> };
}

export function IndicatorSuite({ symbol, timeframe, settings, onSettingsChange }: IndicatorSuiteProps) {
  const [data, setData] = useState<IndicatorData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      setIsLoading(true);
      const klineData = await getKline(symbol, timeframe);
      if(klineData) {
        const indicatorData = calculateIndicators(klineData, settings);
        setData(indicatorData);
      } else {
        setData(null);
      }
      setIsLoading(false);
    };

    fetchData();
  }, [symbol, timeframe, settings]);
  
  const rsiSentiment = getSentiment(data?.rsi?.rsi, settings.rsi.overbought, settings.rsi.oversold);
  const macdSentiment = getBullishBearish(data?.macd?.macd, data?.macd?.signal);
  const stochasticSentiment = getSentiment(data?.stochastic?.k, settings.stochastic.overbought, settings.stochastic.oversold);
  const williamsRSentiment = getSentiment(data?.williamsR?.williamsR, settings.williamsR.overbought, settings.williamsR.oversold);
  const cciSentiment = getSentiment(data?.cci?.cci, settings.cci.overbought, settings.cci.oversold);
  const mfiSentiment = getSentiment(data?.mfi?.mfi, settings.mfi.overbought, settings.mfi.oversold);
  const aoSentiment = data?.awesomeOscillator?.ao !== undefined && data.awesomeOscillator.ao !== null
    ? (data.awesomeOscillator.ao > 0 
        ? { text: 'Bullish', color: 'text-chart-2', icon: <TrendingUp className="h-4 w-4" /> }
        : { text: 'Bearish', color: 'text-chart-5', icon: <TrendingDown className="h-4 w-4" /> })
    : { text: 'N/A', color: 'text-muted-foreground', icon: <ChevronsUpDown className="h-4 w-4" /> };

  const supertrendFastSentiment = getSupertrendSentiment(data?.supertrendFast?.direction);
  const supertrendSlowSentiment = getSupertrendSentiment(data?.supertrendSlow?.direction);
  const fisherSentiment = getBullishBearish(data?.fisher?.fisher, data?.fisher?.trigger);


  const renderIndicator = (
    icon: React.ReactNode,
    name: string,
    value: string | number | undefined | null,
    sentiment?: { text: string; color: string } | null,
    details?: React.ReactNode
  ) => (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2">
        {icon}
        <span className="font-semibold">{name}</span>
      </div>
      <div className="text-right">
        {(value !== undefined && value !== null && !isNaN(value as number))
            ? <p className="font-bold">{typeof value === 'number' ? value.toFixed(2) : value}</p>
            : !details ? <p className="font-bold text-muted-foreground">-</p> : null}
        {sentiment && <p className={`text-xs ${sentiment.color}`}>{sentiment.text}</p>}
        {details}
      </div>
    </div>
  );

  const renderBB = (bb: typeof data.bollingerBands) => {
    if (!bb || bb.upper === undefined || bb.middle === undefined || bb.lower === undefined) return <p className="font-mono text-xs text-muted-foreground">Unavailable</p>;
    return (
        <div className="font-mono text-xs">
            <p>U: {bb.upper.toFixed(2)}</p>
            <p>M: {bb.middle.toFixed(2)}</p>
            <p>L: {bb.lower.toFixed(2)}</p>
        </div>
    )
  }
  
  const renderFisher = (fisher: typeof data.fisher) => {
    if (!fisher || fisher.fisher === null || fisher.trigger === null) return <p className="font-mono text-xs text-muted-foreground">Unavailable</p>;
    return (
        <div className="font-mono text-xs">
            <p>F: {fisher.fisher.toFixed(2)}</p>
            <p>T: {fisher.trigger.toFixed(2)}</p>
        </div>
    )
  }

  const renderIchimoku = (ic: typeof data.ichimokuCloud) => {
    if (!ic) return <p className="font-mono text-xs text-muted-foreground">Unavailable</p>;
     return (
        <div className="font-mono text-xs">
            <p>Tenkan: {ic.tenkanSen?.toFixed(2) || '-'}</p>
            <p>Kijun: {ic.kijunSen?.toFixed(2) || '-'}</p>
            <p>Span A: {ic.senkouSpanA?.toFixed(2) || '-'}</p>
            <p>Span B: {ic.senkouSpanB?.toFixed(2) || '-'}</p>
        </div>
     )
  }

  return (
    <>
      <IndicatorSettingsDialog 
        isOpen={isSettingsOpen}
        onOpenChange={setIsSettingsOpen}
        settings={settings}
        onSettingsChange={onSettingsChange}
      />
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Indicator Suite</CardTitle>
          <Button variant="ghost" size="icon" onClick={() => setIsSettingsOpen(true)}>
            <Settings className="h-5 w-5" />
          </Button>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[400px] p-4">
            {isLoading ? (
              <div className="space-y-4">
                {Array.from({ length: 14 }).map((_, i) => (
                  <Skeleton key={i} className="h-8 w-full" />
                ))}
              </div>
            ) : data ? (
              <div className="space-y-4">
                {renderIndicator(supertrendFastSentiment.icon, `Supertrend (${settings.supertrendFast.atrPeriod}, ${settings.supertrendFast.multiplier})`, data.supertrendFast?.supertrend, supertrendFastSentiment)}
                <Separator />
                {renderIndicator(supertrendSlowSentiment.icon, `Supertrend (${settings.supertrendSlow.atrPeriod}, ${settings.supertrendSlow.multiplier})`, data.supertrendSlow?.supertrend, supertrendSlowSentiment)}
                <Separator />
                {renderIndicator(<Gauge className="h-5 w-5 text-muted-foreground" />, `RSI (${settings.rsi.period})`, data.rsi?.rsi, rsiSentiment)}
                <Separator />
                {renderIndicator(macdSentiment?.icon || <ChevronsUpDown className="h-5 w-5 text-muted-foreground" />, `MACD (${settings.macd.fast}, ${settings.macd.slow}, ${settings.macd.signal})`, data.macd?.macd, macdSentiment)}
                <Separator />
                {renderIndicator(<Waves className="h-5 w-5 text-muted-foreground" />, `Bollinger (${settings.bollingerBands.period}, ${settings.bollingerBands.stdDev})`, null, null, renderBB(data.bollingerBands))}
                <Separator />
                {renderIndicator(<Percent className="h-5 w-5 text-muted-foreground" />, `Stochastic (${settings.stochastic.period}, ${settings.stochastic.slowing})`, data.stochastic?.k, stochasticSentiment)}
                <Separator />
                {renderIndicator(<BarChart2 className="h-5 w-5 text-muted-foreground" />, `ATR (${settings.atr.period})`, data.atr?.atr)}
                <Separator />
                {renderIndicator(<GitCommitHorizontal className="h-5 w-5 text-muted-foreground" />, 'OBV', data.obv?.obv?.toExponential(2))}
                <Separator />
                {renderIndicator(<MoveHorizontal className="h-5 w-5 text-muted-foreground" />, `Williams %R (${settings.williamsR.period})`, data.williamsR?.williamsR, williamsRSentiment)}
                <Separator />
                {renderIndicator(<Orbit className="h-5 w-5 text-muted-foreground" />, `CCI (${settings.cci.period})`, data.cci?.cci, cciSentiment)}
                <Separator />
                {renderIndicator(<TrendingUp className="h-5 w-5 text-muted-foreground" />, `ROC (${settings.roc.period})`, data.roc?.roc)}
                 <Separator />
                {renderIndicator(<Sigma className="h-5 w-5 text-muted-foreground" />, `MFI (${settings.mfi.period})`, data.mfi?.mfi, mfiSentiment)}
                 <Separator />
                {renderIndicator(aoSentiment?.icon || <ChevronsUpDown className="h-5 w-5 text-muted-foreground" />, 'Awesome Oscillator', data.awesomeOscillator?.ao, aoSentiment)}
                <Separator />
                 {renderIndicator(<Cloud className="h-5 w-5 text-muted-foreground" />, 'Ichimoku Cloud', null, null, renderIchimoku(data.ichimokuCloud))}
                <Separator />
                {renderIndicator(<TrendingUp className="h-5 w-5 text-muted-foreground" />, `SMA (${settings.sma.period})`, data.sma?.sma)}
                <Separator />
                {renderIndicator(fisherSentiment.icon, `Fisher (${settings.fisher.period})`, null, fisherSentiment, renderFisher(data.fisher))}
                <Separator />
                {renderIndicator(<LineChart className="h-5 w-5 text-muted-foreground" />, `Ehlers Trend (${settings.ehlers.period})`, data.ehlers?.trendline)}

              </div>
            ) : (
              <p className="text-muted-foreground text-center">Could not load indicator data.</p>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
    </>
  );
}
