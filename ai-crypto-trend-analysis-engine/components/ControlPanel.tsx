
import React, { useState } from 'react';

interface ControlPanelProps {
  symbols: string[];
  intervals: { value: string; label: string }[];
  onRunAnalysis: (symbol: string, interval: string, minConfidence: number) => void;
  isLoading: boolean;
  isAutoRefreshEnabled: boolean;
  onToggleAutoRefresh: (enabled: boolean) => void;
}

const ControlPanel: React.FC<ControlPanelProps> = ({ 
  symbols, 
  intervals, 
  onRunAnalysis, 
  isLoading,
  isAutoRefreshEnabled,
  onToggleAutoRefresh
}) => {
  const [symbol, setSymbol] = useState<string>(symbols[0]);
  const [interval, setInterval] = useState<string>(intervals[2].value);
  const [minConfidence, setMinConfidence] = useState<number>(70);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onRunAnalysis(symbol, interval, minConfidence);
  };

  const toggleClasses = isAutoRefreshEnabled ? 'bg-sky-600' : 'bg-gray-600';
  const knobClasses = isAutoRefreshEnabled ? 'translate-x-5' : 'translate-x-0';

  return (
    <div className="bg-gray-800/50 backdrop-blur-sm border border-gray-700 p-6 rounded-xl shadow-lg mb-8">
      <form onSubmit={handleSubmit} className="grid grid-cols-1 md:grid-cols-5 gap-4 items-end">
        
        <div className="flex flex-col">
          <label htmlFor="symbol" className="mb-2 text-sm font-medium text-gray-400">Asset</label>
          <select id="symbol" value={symbol} onChange={(e) => setSymbol(e.target.value)} className="bg-gray-900 border border-gray-600 rounded-lg p-2.5 focus:ring-sky-500 focus:border-sky-500 transition">
            {symbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>

        <div className="flex flex-col">
          <label htmlFor="interval" className="mb-2 text-sm font-medium text-gray-400">Time Interval</label>
          <select id="interval" value={interval} onChange={(e) => setInterval(e.target.value)} className="bg-gray-900 border border-gray-600 rounded-lg p-2.5 focus:ring-sky-500 focus:border-sky-500 transition">
            {intervals.map(i => <option key={i.value} value={i.value}>{i.label}</option>)}
          </select>
        </div>

        <div className="flex flex-col">
          <label htmlFor="confidence" className="mb-2 text-sm font-medium text-gray-400">Min. Confidence ({minConfidence}%)</label>
          <input 
            id="confidence" 
            type="range" 
            min="0" 
            max="100" 
            step="5"
            value={minConfidence} 
            onChange={(e) => setMinConfidence(parseInt(e.target.value))} 
            className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer"
          />
        </div>

        <div className="flex flex-col items-center">
            <label htmlFor="auto-refresh" className="mb-2 text-sm font-medium text-gray-400">Auto-Refresh</label>
            <button
                type="button"
                id="auto-refresh"
                onClick={() => onToggleAutoRefresh(!isAutoRefreshEnabled)}
                className={`${toggleClasses} relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-800 focus:ring-sky-500`}
                disabled={isLoading}
            >
                <span className={`${knobClasses} inline-block w-4 h-4 transform bg-white rounded-full transition-transform`}/>
            </button>
        </div>

        <button type="submit" disabled={isLoading} className="w-full bg-sky-600 text-white font-bold py-2.5 px-4 rounded-lg hover:bg-sky-500 disabled:bg-gray-600 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center">
          {isLoading ? (
            <>
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Analyzing...
            </>
          ) : 'Run Analysis'}
        </button>
      </form>
    </div>
  );
};

export default ControlPanel;
