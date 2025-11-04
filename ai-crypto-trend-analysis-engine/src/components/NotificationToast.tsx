
import React from 'react';
import { PriceAlert } from '../types';
import { formatPrice } from '../utils/formatters';

interface NotificationToastProps {
  alert: PriceAlert;
  onClose: () => void;
}

const NotificationToast: React.FC<NotificationToastProps> = ({ alert, onClose }) => {
  return (
    <div className="fixed top-24 right-8 bg-sky-600 text-white p-4 rounded-lg shadow-2xl z-50 animate-pulse">
      <div className="flex items-center">
        <div className="flex-shrink-0">
          <svg className="h-6 w-6 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        </div>
        <div className="ml-3">
          <p className="font-bold">Price Alert Triggered!</p>
          <p className="text-sm">
            {alert.symbol} has gone {alert.condition} {formatPrice(alert.price)}
          </p>
        </div>
        <div className="ml-4 flex-shrink-0">
          <button onClick={onClose} className="inline-flex rounded-md p-1.5 text-sky-100 hover:bg-sky-700 focus:outline-none focus:ring-2 focus:ring-white">
            <span className="sr-only">Dismiss</span>
            <svg className="h-5 w-5" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
};

export default NotificationToast;
