
import React, { useState, useCallback } from 'react';
import { AnalysisResult, TrendDirection, TimeframeAlignmentEntry } from '../types';
import PriceChart from './PriceChart';
import { useSubscription } from '../hooks/useSubscription';
import { TIME_INTERVALS } from '../constants';
import { formatPrice } from '../utils/formatters';

interface SignalCardProps {
  result: AnalysisResult;
  onReanalyze: (symbol: string, interval: string) => void;
  isLoading: boolean;
}

const getSignalClasses = (signal: 'BUY' | 'SELL' | 'HOLD') => {
  switch (signal) {
    case 'BUY':
      return 'bg-green-500/10 text-green-400 border-green-500/30';
    case 'SELL':
      return 'bg-red-500/10 text-red-400 border-red-500/30';
    case 'HOLD':
      return 'bg-gray-500/10 text-gray-400 border-gray-500/30';
  }
};

const getSignalBorderClasses = (signal: 'BUY' | 'SELL' | 'HOLD') => {
    switch (signal) {
      case 'BUY':
        return 'border-green-500/70 hover:border-green-400';
      case 'SELL':
        return 'border-red-500/70 hover:border-red-400';
      case 'HOLD':
        return 'border-gray-700 hover:border-gray-500';
    }
  };

const getTrendColor = (trend: TrendDirection) => {
    switch(trend) {
        case 'Uptrend': return 'text-green-400';
        case 'Downtrend': return 'text-red-400';
        default: return 'text-gray-400';
    }
}

const getUrgencyClasses = (urgency: 'Immediate' | 'Monitor' | 'Low') => {
    switch(urgency) {
        case 'Immediate': return 'bg-red-600/20 text-red-400 animate-pulse';
        case 'Monitor': return 'bg-sky-600/20 text-sky-400';
        default: return 'bg-gray-600/20 text-gray-400';
    }
}

const SignalIcon: React.FC<{ signal: 'BUY' | 'SELL' | 'HOLD' }> = ({ signal }) => {
    switch (signal) {
      case 'BUY':
        return <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M5 10l7-7m0 0l7 7m-7-7v18" /></svg>;
      case 'SELL':
        return <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M19 14l-7 7m0 0l-7-7m7 7V3" /></svg>;
      case 'HOLD':
        return <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-1.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2.5"><path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>;
      default:
        return null;
    }
  };

const LiveOrderbookData: React.FC<{ symbol: string }> = ({ symbol }) => {
    const [orderbookData, setOrderbookData] = useState({
      bid: null as string | null,
      ask: null as string | null,
      bidDirection: 'neutral' as 'up' | 'down' | 'neutral',
      askDirection: 'neutral' as 'up' | 'down' | 'neutral',
    });

    const topic = `orderbook.1.${symbol}`;

    const handleMessage = useCallback((data: any) => {
        if (data.topic === topic && data.data) {
            const newBid = data.data.b[0]?.[0];
            const newAsk = data.data.a[0]?.[0];
            
            setOrderbookData(prevData => {
                const nextBid = newBid || prevData.bid;
                const nextAsk = newAsk || prevData.ask;
                
                let nextBidDirection: 'up' | 'down' | 'neutral' = 'neutral';
                if (prevData.bid && nextBid) {
                    if (parseFloat(nextBid) > parseFloat(prevData.bid)) nextBidDirection = 'up';
                    else if (parseFloat(nextBid) < parseFloat(prevData.bid)) nextBidDirection = 'down';
                }

                let nextAskDirection: 'up' | 'down' | 'neutral' = 'neutral';
                if (prevData.ask && nextAsk) {
                    if (parseFloat(nextAsk) > parseFloat(prevData.ask)) nextAskDirection = 'up';
                    else if (parseFloat(nextAsk) < parseFloat(prevData.ask)) nextAskDirection = 'down';
                }

                return {
                    bid: nextBid,
                    ask: nextAsk,
                    bidDirection: nextBidDirection,
                    askDirection: nextAskDirection
                };
            });
        }
    }, [topic]);

    useSubscription([topic], handleMessage);

    const getPriceColor = (direction: 'up' | 'down' | 'neutral') => {
        if (direction === 'up') return 'text-green-400';
        if (direction === 'down') return 'text-red-400';
        return 'text-white';
    };

    const spread = orderbookData.bid && orderbookData.ask ? (parseFloat(orderbookData.ask) - parseFloat(orderbookData.bid)) : null;

    return (
        <>
            <div className="flex justify-between pt-2 border-t border-gray-700/50">
                <div className="flex items-center">
                    <span>Best Bid:</span>
                    <span className="ml-2 text-xs font-bold text-sky-400 bg-sky-900/50 px-1.5 py-0.5 rounded animate-pulse">LIVE</span>
                </div>
                 <span className={`font-mono transition-colors duration-300 ${getPriceColor(orderbookData.bidDirection)}`}>{formatPrice(orderbookData.bid)}</span>
            </div>
            <div className="flex justify-between">
                <span>Best Ask:</span> 
                <span className={`font-mono transition-colors duration-300 ${getPriceColor(orderbookData.askDirection)}`}>{formatPrice(orderbookData.ask)}</span>
            </div>
            {spread !== null && <div className="flex justify-between"><span>Spread:</span> <span className="font-mono text-white">{formatPrice(spread)}</span></div>}
        </>
    );
};

const TimeframeAlignment: React.FC<{ alignment?: TimeframeAlignmentEntry[] }> = ({ alignment }) => {
    if (!alignment || alignment.length === 0) {
        return null;
    }

    return (
        <div className="pt-2 border-t border-gray-700/50">
            <h5 className="font-semibold text-gray-400 text-xs mb-1">Higher Timeframe Confirmation</h5>
            <div className="flex gap-2">
                {alignment.map(({ interval, trend }) => (
                    <div key={interval} className="flex-1 text-center bg-gray-900 rounded p-1">
                        <div className="text-xs text-gray-500">{TIME_INTERVALS.find(i => i.value === interval)?.label || interval}</div>
                        <div className={`text-xs font-bold ${getTrendColor(trend)}`}>{trend}</div>
                    </div>
                ))}
            </div>
        </div>
    );
};


const SignalCard: React.FC<SignalCardProps> = ({ result, onReanalyze, isLoading }) => {
  const { symbol, interval, analysis, current_price, timestamp, klines, meets_confidence, indicators } = result;
  
  const rsi = indicators.momentum?.rsi;
  const adx = indicators.trend?.adx;
  const vwap = indicators.volume?.vwap;


  return (
    <div className={`bg-gray-800/50 border-2 rounded-xl overflow-hidden shadow-lg transition-all duration-300 ${getSignalBorderClasses(analysis.signal)}`}>
      <div className="p-5">
        {/* Header */}
        <div className="flex flex-col sm:flex-row justify-between sm:items-center gap-2 mb-4">
          <div>
            <h3 className="text-2xl font-bold text-white">{symbol}</h3>
            <div className="flex items-center gap-2">
                <p className="text-sm text-gray-400">
                {new Date(timestamp).toLocaleString()} - {TIME_INTERVALS.find(i => i.value === interval)?.label || `${interval} Interval`}
                </p>
                <button
                    onClick={() => onReanalyze(symbol, interval)}
                    disabled={isLoading}
                    className="p-1.5 rounded-full text-gray-400 hover:bg-gray-700 hover:text-sky-400 disabled:cursor-not-allowed disabled:opacity-50 transition-colors"
                    aria-label="Re-analyze"
                    title="Re-analyze"
                >
                    {isLoading ? (
                        <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                    ) : (
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 110 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                        </svg>
                    )}
                </button>
            </div>
          </div>
          <div className="flex items-center gap-4">
             <span className={`text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full ${getUrgencyClasses(analysis.tradeUrgency)}`}>
                {analysis.tradeUrgency}
            </span>
            {meets_confidence && (
                <span className="text-xs font-semibold inline-block py-1 px-2 uppercase rounded-full bg-sky-600/20 text-sky-400">
                ACTIONABLE
                </span>
            )}
            <div className={`px-4 py-2 text-lg font-extrabold rounded-lg flex items-center ${getSignalClasses(analysis.signal)}`}>
              <SignalIcon signal={analysis.signal} />
              {analysis.signal}
            </div>
          </div>
        </div>

        {/* Chart */}
        <div className="h-60 w-full mb-4">
          <PriceChart data={klines} signal={analysis.signal}/>
        </div>

        {/* Analysis Details */}
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 text-sm">
          <div className="lg:col-span-1 md:col-span-2 bg-gray-900/50 p-4 rounded-lg">
            <h4 className="font-bold text-gray-200 mb-3 text-base">Key Metrics</h4>
            <div className="space-y-2">
                <div className="flex justify-between"><span>Last Price:</span> <span className="font-mono text-white">{formatPrice(current_price)}</span></div>
                <div className="flex justify-between"><span>Entry Price:</span> <span className="font-mono text-white">{formatPrice(analysis.entryPrice)}</span></div>
                {analysis.takeProfitLevels.map((tp, index) => (
                    <div className="flex justify-between" key={index}>
                        <span>Take Profit {index + 1}:</span> <span className="font-mono text-green-400">{formatPrice(tp)}</span>
                    </div>
                ))}
                <div className="flex justify-between"><span>Stop Loss:</span> <span className="font-mono text-red-400">{formatPrice(analysis.stopLossLevel)}</span></div>
                
                <LiveOrderbookData symbol={symbol} />
                
                {vwap !== undefined && <div className="flex justify-between pt-2 border-t border-gray-700/50"><span>VWAP (20-p):</span> <span className="font-mono text-white">{formatPrice(vwap)}</span></div>}
                
                <div className="flex justify-between pt-2 border-t border-gray-700/50"><span>Trend ({TIME_INTERVALS.find(i => i.value === interval)?.label}):</span> <span className={`font-semibold ${getTrendColor(analysis.trend)}`}>{analysis.trend}</span></div>
                
                <TimeframeAlignment alignment={analysis.timeframe_alignment} />

                <div className="flex justify-between items-center pt-2 border-t border-gray-700/50">
                  <span>Confidence:</span>
                  <div className="w-1/2 bg-gray-700 rounded-full h-2.5">
                    <div className="bg-sky-500 h-2.5 rounded-full" style={{ width: `${analysis.confidence}%` }}></div>
                  </div>
                  <span className="font-mono text-white">{analysis.confidence}%</span>
                </div>
                {rsi !== undefined && <div className="flex justify-between"><span>RSI (14):</span> <span className="font-mono text-white">{rsi.toFixed(2)}</span></div>}
                {adx !== undefined && <div className="flex justify-between"><span>ADX (14):</span> <span className="font-mono text-white">{adx.toFixed(2)}</span></div>}
                <div className="flex justify-between"><span>Support:</span> <span className="font-mono text-green-400">{formatPrice(analysis.supportLevel)}</span></div>
                <div className="flex justify-between"><span>Resistance:</span> <span className="font-mono text-red-400">{formatPrice(analysis.resistanceLevel)}</span></div>
            </div>
          </div>

          <div className="lg:col-span-2 md:col-span-2 bg-gray-900/50 p-4 rounded-lg">
            <h4 className="font-bold text-gray-200 mb-2 text-base">AI Scalping Analysis</h4>
            <p className="italic text-gray-400 mb-4">"{analysis.scalpingThesis}"</p>
            
            <div className="mb-4">
                <h5 className="font-semibold text-gray-300 mb-2 text-sm">Scalping Strategy:</h5>
                <span className="bg-gray-700 text-amber-300 text-xs font-medium px-2.5 py-1 rounded-full border border-gray-600">
                    {analysis.scalpingStrategy}
                </span>
            </div>

            <div className="mb-4">
                <h5 className="font-semibold text-gray-300 mb-2 text-sm">Key Factors Identified:</h5>
                <div className="flex flex-wrap gap-2">
                    {analysis.key_factors.map((factor, index) => (
                        <span key={index} className="bg-gray-700 text-sky-300 text-xs font-medium px-2.5 py-1 rounded-full border border-gray-600">
                            {factor}
                        </span>
                    ))}
                </div>
            </div>

            <div className="border-t border-gray-700/50 pt-3">
                <h5 className="font-semibold text-gray-300 mb-1 text-sm">Detailed Reasoning:</h5>
                <p className="text-gray-300 text-sm">{analysis.reasoning}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignalCard;
