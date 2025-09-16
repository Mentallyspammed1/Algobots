'use client';

import { useEffect, useRef } from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { TRADINGVIEW_TIMEFRAME_MAP } from '@/lib/constants';

interface TradingViewChartProps {
  symbol: string;
  timeframe: string;
}

declare const TradingView: any;

export function TradingViewChart({ symbol, timeframe }: TradingViewChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<any>(null);

  useEffect(() => {
    const createWidget = () => {
      if (containerRef.current && typeof TradingView !== 'undefined') {
        if (widgetRef.current) {
          widgetRef.current.remove();
          widgetRef.current = null;
        }

        const widget = new TradingView.widget({
          autosize: true,
          symbol: `BYBIT:${symbol}`,
          interval: TRADINGVIEW_TIMEFRAME_MAP[timeframe],
          timezone: 'Etc/UTC',
          theme: 'dark',
          style: '1',
          locale: 'en',
          enable_publishing: false,
          hide_side_toolbar: true,
          allow_symbol_change: false,
          studies: [
            "Supertrend@tv-basicstudies",
            "ChandelierExit@tv-basicstudies"
          ],
          container_id: containerRef.current.id,
        });
        widgetRef.current = widget;
      }
    };

    if (typeof TradingView === 'undefined') {
      const script = document.querySelector('script[src="https://s3.tradingview.com/tv.js"]');
      if (script) {
        script.addEventListener('load', createWidget);
        return () => script.removeEventListener('load', createWidget);
      }
    } else {
      createWidget();
    }
    
    return () => {
        if (widgetRef.current) {
            try {
                widgetRef.current.remove();
            } catch (error) {
                // Ignore errors on cleanup
            }
            widgetRef.current = null;
        }
    }

  }, [symbol, timeframe]);

  return (
    <Card className="h-[500px] w-full">
      <CardContent className="p-0 h-full">
        <div ref={containerRef} id={`tradingview_widget_${symbol}_${timeframe}`} className="h-full w-full" />
      </CardContent>
    </Card>
  );
}
