
import React, { useState } from 'react';
import { PriceAlert } from '../types';
import { formatPrice } from '../utils/formatters';

interface AlertsPanelProps {
  symbols: string[];
  alerts: PriceAlert[];
  onAddAlert: (alert: Omit<PriceAlert, 'id' | 'triggered'>) => void;
  onRemoveAlert: (id: number) => void;
}

const AlertsPanel: React.FC<AlertsPanelProps> = ({ symbols, alerts, onAddAlert, onRemoveAlert }) => {
  const [symbol, setSymbol] = useState(symbols[0]);
  const [price, setPrice] = useState('');
  const [condition, setCondition] = useState<'above' | 'below'>('above');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const priceNum = parseFloat(price);
    if (!priceNum || priceNum <= 0) return;
    onAddAlert({ symbol, price: priceNum, condition });
    setPrice('');
  };

  return (
    <div className="bg-gray-800/50 border border-gray-700 p-6 rounded-xl shadow-lg h-full">
      <h2 className="text-2xl font-bold mb-4 text-gray-300">Price Alerts</h2>
      
      <form onSubmit={handleSubmit} className="space-y-4 mb-6">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label htmlFor="alert-symbol" className="block text-sm font-medium text-gray-400 mb-1">Asset</label>
            <select id="alert-symbol" value={symbol} onChange={e => setSymbol(e.target.value)} className="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 focus:ring-sky-500 focus:border-sky-500 transition">
              {symbols.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
             <label htmlFor="alert-condition" className="block text-sm font-medium text-gray-400 mb-1">Condition</label>
            <select id="alert-condition" value={condition} onChange={e => setCondition(e.target.value as any)} className="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 focus:ring-sky-500 focus:border-sky-500 transition">
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
          </div>
        </div>
        <div>
          <label htmlFor="alert-price" className="block text-sm font-medium text-gray-400 mb-1">Target Price</label>
          <input type="number" step="any" id="alert-price" value={price} onChange={e => setPrice(e.target.value)} placeholder="e.g., 65000" className="w-full bg-gray-900 border border-gray-600 rounded-lg p-2 focus:ring-sky-500 focus:border-sky-500 transition" />
        </div>
        <button type="submit" className="w-full bg-sky-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-sky-500 disabled:bg-gray-600 transition">
          Set Alert
        </button>
      </form>
      
      <h3 className="text-lg font-semibold text-gray-400 mb-3 border-t border-gray-700 pt-4">Active Alerts</h3>
      <div className="space-y-2 max-h-96 overflow-y-auto">
        {alerts.length > 0 ? alerts.map(alert => (
          <div key={alert.id} className={`flex justify-between items-center p-3 rounded-lg ${alert.triggered ? 'bg-green-900/50' : 'bg-gray-900/50'}`}>
            <div className="text-sm">
              <span className="font-bold">{alert.symbol}</span>
              <span className="text-gray-400"> {alert.condition === 'above' ? '>' : '<'} </span>
              <span className="font-mono">{formatPrice(alert.price)}</span>
              {alert.triggered && <span className="ml-2 text-xs font-bold text-green-400">TRIGGERED</span>}
            </div>
            <button onClick={() => onRemoveAlert(alert.id)} className="text-red-500 hover:text-red-400">&times;</button>
          </div>
        )) : (
          <p className="text-sm text-gray-500 text-center py-4">No active alerts.</p>
        )}
      </div>
    </div>
  );
};

export default AlertsPanel;
