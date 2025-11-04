import React, { useMemo, useCallback } from 'react';
import { PriceAlert } from '../types';
import { useSubscription } from '../hooks/useSubscription';

interface PriceMonitorProps {
  alerts: PriceAlert[];
  onAlertTriggered: (alert: PriceAlert) => void;
}

const PriceMonitor: React.FC<PriceMonitorProps> = ({ alerts, onAlertTriggered }) => {
  const activeAlerts = useMemo(() => alerts.filter(a => !a.triggered), [alerts]);
  const topics = useMemo(() => [...new Set(activeAlerts.map(a => `tickers.${a.symbol}`))], [activeAlerts]);

  const handleMessage = useCallback((data: any) => {
    if (data.topic && data.data) {
      const symbol = data.topic.split('.')[1];
      const currentPrice = parseFloat(data.data.lastPrice);
      
      activeAlerts.forEach(alert => {
        if (alert.symbol === symbol) {
          const conditionMet = 
            (alert.condition === 'above' && currentPrice >= alert.price) ||
            (alert.condition === 'below' && currentPrice <= alert.price);
          
          if (conditionMet) {
            onAlertTriggered(alert);
          }
        }
      });
    }
  }, [activeAlerts, onAlertTriggered]);

  useSubscription(topics, handleMessage);

  return null; // This component does not render anything
};

export default PriceMonitor;