'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { BYBIT_WEBSOCKET_URL } from '@/lib/bybit-api';

type ConnectionStatus = 'connecting' | 'connected' | 'reconnecting' | 'disconnected' | 'closed';
type MessageHandler = (message: any) => void;

const MAX_RETRIES = 5;
const RETRY_DELAY_BASE = 1000;

// #region Singleton WebSocket Manager
// This manager lives outside the component lifecycle to ensure a single WebSocket instance.
let ws: WebSocket | null = null;
let status: ConnectionStatus = 'closed';
let retryCount = 0;
let reconnectTimeout: NodeJS.Timeout | null = null;
const subscribers = new Map<string, Set<MessageHandler>>();
const statusListeners = new Set<(status: ConnectionStatus) => void>();

const setStatus = (newStatus: ConnectionStatus) => {
  if (status === newStatus) return;
  status = newStatus;
  statusListeners.forEach(listener => listener(newStatus));
};

const connect = () => {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }
  
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }

  setStatus(retryCount > 0 ? 'reconnecting' : 'connecting');
  ws = new WebSocket(BYBIT_WEBSOCKET_URL);

  ws.onopen = () => {
    console.log('Bybit WebSocket connected.');
    setStatus('connected');
    retryCount = 0;
    // Resubscribe to all topics now that the connection is open
    subscribers.forEach((_, topic) => {
      ws?.send(JSON.stringify({ op: 'subscribe', args: [topic] }));
    });
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.topic) {
      subscribers.get(message.topic)?.forEach(handler => handler(message));
    }
  };

  ws.onclose = () => {
    console.log('Bybit WebSocket disconnected.');
    if (status === 'closed') { // Deliberate close
      return;
    }
    if (retryCount < MAX_RETRIES) {
      const delay = RETRY_DELAY_BASE * Math.pow(2, retryCount);
      retryCount++;
      setStatus('reconnecting');
      console.log(`Attempting to reconnect in ${delay}ms...`);
      reconnectTimeout = setTimeout(connect, delay);
    } else {
      setStatus('disconnected');
      console.error('Failed to reconnect to Bybit WebSocket after max retries.');
    }
  };

  ws.onerror = (err) => {
    console.error('Bybit WebSocket error:', err);
    ws?.close(); // This will trigger the onclose handler for reconnection logic
  };
};

const disconnect = () => {
  if (reconnectTimeout) {
    clearTimeout(reconnectTimeout);
    reconnectTimeout = null;
  }
  if (ws) {
    setStatus('closed');
    ws.close();
    ws = null;
  }
  subscribers.clear();
};

const subscribe = (topic: string, handler: MessageHandler) => {
  if (!subscribers.has(topic)) {
    subscribers.set(topic, new Set());
    // Only send subscribe message if connection is already open.
    // Otherwise, the onopen handler will take care of it.
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ op: 'subscribe', args: [topic] }));
    }
  }
  subscribers.get(topic)?.add(handler);
};

const unsubscribe = (topic: string, handler: MessageHandler) => {
  const topicSubscribers = subscribers.get(topic);
  if (topicSubscribers) {
    topicSubscribers.delete(handler);
    if (topicSubscribers.size === 0) {
      subscribers.delete(topic);
      // Only send unsubscribe if connection is open
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ op: 'unsubscribe', args: [topic] }));
      }
    }
  }
};
// #endregion

/**
 * A custom hook to subscribe to a Bybit WebSocket topic.
 * It manages a single, shared WebSocket connection for the entire application.
 *
 * @param topic The WebSocket topic to subscribe to (e.g., 'tickers.BTCUSDT').
 * @returns An object containing the latest message for the topic and the current connection status.
 */
export function useBybitWebSocket(topic: string | null) {
  const [lastMessage, setLastMessage] = useState<any | null>(null);
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>(status);

  useEffect(() => {
    if (!topic) return;
    
    // Connect if not already connected/connecting
    if (!ws || ws.readyState === WebSocket.CLOSED) {
      connect();
    }
    
    const messageHandler: MessageHandler = (message) => {
      setLastMessage(message);
    };

    const statusHandler = (newStatus: ConnectionStatus) => {
      setConnectionStatus(newStatus);
    };

    subscribe(topic, messageHandler);
    statusListeners.add(statusHandler);
    setConnectionStatus(status); // Set initial status

    return () => {
      unsubscribe(topic, messageHandler);
      statusListeners.delete(statusHandler);
      
      // If this is the last subscriber, consider closing the connection
      if (subscribers.size === 0) {
        // Optional: Add a delay before disconnecting in case of quick navigation
        // setTimeout(() => {
        //   if (subscribers.size === 0) disconnect();
        // }, 5000);
      }
    };
  }, [topic]);

  const reconnect = useCallback(() => {
    if (status === 'disconnected' || status === 'closed') {
        retryCount = 0;
        connect();
    }
  }, []);

  return { lastMessage, connectionStatus, reconnect };
}
