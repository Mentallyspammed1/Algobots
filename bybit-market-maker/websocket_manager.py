import json
import logging
import threading
import time
from collections.abc import Callable

import websocket


class WebSocketManager:
    """Handles Bybit WebSocket connections and subscriptions."""

    def __init__(self, api_key: str, api_secret: str, on_message: Callable):
        self.logger = logging.getLogger(__name__)
        self.api_key = api_key
        self.api_secret = api_secret
        self.channel = "wss://stream.bybit.com/v5/private"
        self.on_message = on_message
        self.ws = None
        self.wst = None
        self.is_connected = False

    def connect(self):
        """Connect to the WebSocket."""
        self.ws = websocket.WebSocketApp(
            self.channel,
            on_message=self._on_message,
            on_close=self._on_close,
            on_open=self._on_open,
            on_error=self._on_error,
        )
        self.wst = threading.Thread(target=lambda: self.ws.run_forever())
        self.wst.daemon = True
        self.wst.start()

    def _on_message(self, ws, message):
        """Handle incoming messages."""
        try:
            data = json.loads(message)
            if "topic" in data:
                self.on_message(data)
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode WebSocket message: {e}")

    def _on_open(self, ws):
        """Handle WebSocket connection open."""
        self.logger.info("WebSocket connection opened.")
        self.is_connected = True
        self._subscribe()

    def _on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close."""
        self.logger.warning(
            f"WebSocket connection closed with status {close_status_code}: {close_msg}",
        )
        self.is_connected = False

    def _on_error(self, ws, error):
        """Handle WebSocket errors."""
        self.logger.error(f"WebSocket error: {error}")

    def _subscribe(self):
        """Subscribe to WebSocket topics."""
        # Bybit WebSocket v5 authentication and subscription
        expires = int((time.time() + 1) * 1000)
        signature = self._generate_signature(f"GET/realtime{expires}")

        self.ws.send(
            json.dumps(
                {
                    "op": "auth",
                    "args": [self.api_key, expires, signature],
                },
            ),
        )
        time.sleep(1)  # Allow time for authentication

        # Subscribe to topics
        self.ws.send(
            json.dumps(
                {
                    "op": "subscribe",
                    "args": [
                        "order",
                        "position",
                        "tickers.BTCUSDT",
                    ],
                },
            ),
        )

    def _generate_signature(self, data: str) -> str:
        """Generate API signature."""
        import hashlib
        import hmac

        return hmac.new(
            self.api_secret.encode("utf-8"), data.encode("utf-8"), hashlib.sha256,
        ).hexdigest()

    def disconnect(self):
        """Disconnect from the WebSocket."""
        if self.ws:
            self.ws.close()
