
import { useEffect } from 'react';
import { useWebSocket } from '../contexts/WebSocketProvider';

type MessageCallback = (data: any) => void;

export const useSubscription = (topics: string[], onMessage: MessageCallback) => {
  const { subscribe, unsubscribe } = useWebSocket();

  useEffect(() => {
    // Ensure topics array is not empty to avoid unnecessary calls
    if (topics.length > 0) {
      subscribe(topics, onMessage);
    }

    return () => {
      if (topics.length > 0) {
        unsubscribe(topics, onMessage);
      }
    };
  // Re-run the effect if the topics or the message handler change.
  // Using JSON.stringify for topics array to ensure stable dependency checking.
  }, [JSON.stringify(topics), onMessage, subscribe, unsubscribe]);
};
