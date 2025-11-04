
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';

const WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/linear';
const INITIAL_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

type MessageCallback = (data: any) => void;
type ListenerMap = Map<string, Set<MessageCallback>>;

interface WebSocketContextType {
  subscribe: (topics: string[], callback: MessageCallback) => void;
  unsubscribe: (topics: string[], callback: MessageCallback) => void;
  readyState: number;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within a WebSocketProvider');
  }
  return context;
};

export const WebSocketProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const ws = useRef<WebSocket | null>(null);
  const [readyState, setReadyState] = useState<number>(WebSocket.CONNECTING);
  const listeners = useRef<ListenerMap>(new Map());
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelay = useRef<number>(INITIAL_RECONNECT_DELAY);

  const connect = useCallback(() => {
    if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
        console.log("WebSocket connection already open or connecting.");
        return;
    }

    ws.current = new WebSocket(WEBSOCKET_URL);
    setReadyState(WebSocket.CONNECTING);
    console.log("Attempting to connect WebSocket...");

    ws.current.onopen = () => {
      console.log('WebSocket Connected');
      setReadyState(WebSocket.OPEN);
      reconnectDelay.current = INITIAL_RECONNECT_DELAY; // Reset delay on successful connection
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
        reconnectTimeout.current = null;
      }
      const allTopics = Array.from(listeners.current.keys());
      if (allTopics.length > 0) {
        sendMessage({ op: 'subscribe', args: allTopics });
      }
    };

    ws.current.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.topic) {
        const topicListeners = listeners.current.get(data.topic);
        if (topicListeners) {
          topicListeners.forEach(callback => callback(data));
        }
      }
    };

    ws.current.onerror = (event) => {
      console.error('A WebSocket error occurred. The subsequent "close" event will provide more details.', event);
    };

    ws.current.onclose = (event) => {
      console.log(`WebSocket Disconnected. Code: ${event.code}, Reason: ${event.reason}`);
      setReadyState(WebSocket.CLOSED);
      
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      
      console.log(`Attempting to reconnect in ${reconnectDelay.current / 1000}s...`);
      reconnectTimeout.current = setTimeout(() => {
        // Exponentially increase the delay
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY);
        connect();
      }, reconnectDelay.current);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      ws.current?.close(1000, "Component unmounting");
    };
  }, [connect]);
  
  const sendMessage = useCallback((message: object) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.send(JSON.stringify(message));
    } else {
        console.warn('WebSocket is not open. Message not sent:', message);
    }
  }, []);

  const subscribe = useCallback((topics: string[], callback: MessageCallback) => {
    const newTopics: string[] = [];
    topics.forEach(topic => {
      if (!listeners.current.has(topic)) {
        listeners.current.set(topic, new Set());
        newTopics.push(topic);
      }
      listeners.current.get(topic)?.add(callback);
    });

    if (newTopics.length > 0) {
        sendMessage({ op: 'subscribe', args: newTopics });
    }
  }, [sendMessage]);

  const unsubscribe = useCallback((topics: string[], callback: MessageCallback) => {
    const topicsToUnsub: string[] = [];
    topics.forEach(topic => {
      const topicListeners = listeners.current.get(topic);
      if (topicListeners) {
        topicListeners.delete(callback);
        if (topicListeners.size === 0) {
          listeners.current.delete(topic);
          topicsToUnsub.push(topic);
        }
      }
    });

    if (topicsToUnsub.length > 0) {
      sendMessage({ op: 'unsubscribe', args: topicsToUnsub });
    }
  }, [sendMessage]);

  const value = { subscribe, unsubscribe, readyState };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
};