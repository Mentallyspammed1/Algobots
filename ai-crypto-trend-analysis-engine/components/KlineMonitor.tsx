
import React, { useCallback } from 'react';
import { useSubscription } from '../hooks/useSubscription';

interface KlineMonitorProps {
  symbol: string;
  interval: string;
  onNewCandle: () => void;
}

const KlineMonitor: React.FC<KlineMonitorProps> = ({ symbol, interval, onNewCandle }) => {
  const topic = `kline.${interval}.${symbol}`;

  const handleMessage = useCallback((data: any) => {
    if (data.topic === topic && data.data) {
      const klineData = data.data[0];
      if (klineData && klineData.confirm === true) {
        onNewCandle();
      }
    }
  }, [topic, onNewCandle]);

  useSubscription([topic], handleMessage);

  return null; // This component does not render any UI
};

export default KlineMonitor;
