
import React, { useState, useCallback } from 'react';
import { TickerData } from '../types';
import { useSubscription } from '../hooks/useSubscription';

interface TickerProps {
  symbols: string[];
}

const DirectionIcon: React.FC<{ direction: 'up' | 'down' | 'neutral' }> = ({ direction }) => {
    if (direction === 'up') {
      return <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1 text-green-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M5 15l7-7 7 7" /></svg>;
    }
    if (direction === 'down') {
      return <svg xmlns="http://www.w3.org/2000/svg" className="h-3 w-3 mr-1 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3"><path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" /></svg>;
    }
    return <div className="w-3 mr-1"></div>; // Placeholder for neutral to maintain alignment
  };

const Ticker: React.FC<TickerProps> = ({ symbols }) => {
  const [tickerData, setTickerData] = useState<Record<string, TickerData>>({});

  const topics = symbols.map(s => `tickers.${s}`);

  const handleMessage = useCallback((data: any) => {
    if (data.topic && data.data) {
      const symbol = data.topic.split('.')[1];
      const newPrice = parseFloat(data.data.lastPrice);
      
      setTickerData(prevData => {
          const oldPrice = prevData[symbol]?.price || 0;
          const direction = newPrice > oldPrice ? 'up' : newPrice < oldPrice ? 'down' : prevData[symbol]?.direction || 'neutral';
          return {
              ...prevData,
              [symbol]: { price: newPrice, direction }
          };
      });
    }
  }, []);
  
  useSubscription(topics, handleMessage);

  const getPriceColor = (direction: 'up' | 'down' | 'neutral') => {
    switch(direction) {
        case 'up': return 'text-green-400';
        case 'down': return 'text-red-400';
        default: return 'text-gray-400';
    }
  }

  const tickerContent = symbols.map(symbol => (
    <div key={symbol} className="flex items-center mx-4 flex-shrink-0" role="listitem">
      <span className="text-sm font-bold text-gray-200">{symbol}</span>
      <div className={`ml-2 flex items-center ${getPriceColor(tickerData[symbol]?.direction ?? 'neutral')}`}>
        <DirectionIcon direction={tickerData[symbol]?.direction ?? 'neutral'} />
        <span 
          className="text-sm font-mono"
          aria-live="polite"
        >
          ${tickerData[symbol]?.price ? tickerData[symbol]?.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '...'}
        </span>
      </div>
    </div>
  ));

  return (
    <div className="fixed top-0 left-0 right-0 h-10 bg-gray-900/80 backdrop-blur-sm border-b border-gray-700 z-50 overflow-hidden" aria-label="Live price ticker">
      <div className="flex items-center h-full" role="list">
        <div className="flex items-center animate-scroll whitespace-nowrap">
          {/* Render content twice for seamless loop */}
          {tickerContent}
          {tickerContent}
        </div>
      </div>
    </div>
  );
};

export default Ticker;
