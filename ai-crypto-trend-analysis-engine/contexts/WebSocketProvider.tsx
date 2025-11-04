
import React, { createContext, useContext, useEffect, useRef, useState, useCallback } from 'react';

const WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/linear';

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
  const reconnectInterval = useRef<ReturnType<typeof setInterval> | null>(null);

  const connect = useCallback(() => {
    if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
        return;
    }

    ws.current = new WebSocket(WEBSOCKET_URL);
    setReadyState(WebSocket.CONNECTING);

    ws.current.onopen = () => {
      console.log('WebSocket Connected');
      setReadyState(WebSocket.OPEN);
      if (reconnectInterval.current) {
        clearInterval(reconnectInterval.current);
        reconnectInterval.current = null;
      }
      // Resubscribe to all topics on reconnect
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
      console.error('WebSocket Error:', event);
      setReadyState(WebSocket.CLOSED);
    };

    ws.current.onclose = (event) => {
      console.log(`WebSocket Disconnected. Code: ${event.code}, Reason: ${event.reason}`);
      setReadyState(WebSocket.CLOSED);
      // Attempt to reconnect
      if (!reconnectInterval.current) {
        reconnectInterval.current = setInterval(() => {
            console.log("Attempting to reconnect WebSocket...");
            connect();
        }, 5000); // Reconnect every 5 seconds
      }
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectInterval.current) clearInterval(reconnectInterval.current);
      ws.current?.close();
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
