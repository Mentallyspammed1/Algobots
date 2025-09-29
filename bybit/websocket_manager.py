"""This module contains the BybitWebSocket class, which manages the WebSocket
connection to the Bybit exchange. It handles subscribing to topics,
receiving messages, and processing real-time data.
"""

import json
import logging
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import websocket
from scalper_core.constants import NB, NG, NR, NY, RST


class BybitWebSocket:
    """Manages the WebSocket connection to the Bybit exchange."""

    def __init__(
        self,
        logger: logging.Logger,
        config: dict[str, Any],
        trade_tracker: "TradeManager",
        market_infos: dict[str, dict],
        message_handler: Callable[[dict], None],
    ):
        self.lg = logger
        self.cfg = config
        self.tt = trade_tracker
        self.mi = market_infos
        self.ws = None
        self.wst = None
        self.message_handler = message_handler
        self.current_prices: dict[str, Decimal | None] = {}
        self.is_connected = False

    def connect(self) -> None:
        """Connects to the Bybit WebSocket."""
        if self.cfg["use_sandbox"]:
            url = "wss://stream-testnet.bybit.com/v5/public/linear"
        else:
            url = "wss://stream.bybit.com/v5/public/linear"

        self.lg.info(f"Connecting to Bybit WebSocket at {url}...")
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self.wst = threading.Thread(target=lambda: self.ws.run_forever())
        self.wst.daemon = True
        self.wst.start()

    def _on_open(self, ws) -> None:
        """Handles the WebSocket connection opening."""
        self.lg.info(f"{NG}Bybit WebSocket connection opened.{RST}")
        self.is_connected = True
        self._subscribe_to_topics()

    def _on_message(self, ws, message: str) -> None:
        """Handles incoming WebSocket messages."""
        try:
            data = json.loads(message)
            if "topic" in data:
                self.message_handler(data)
        except json.JSONDecodeError:
            self.lg.error(f"{NR}Failed to decode WebSocket message: {message}{RST}")

    def _on_error(self, ws, error: Any) -> None:
        """Handles WebSocket errors."""
        self.lg.error(f"{NR}Bybit WebSocket error: {error}{RST}")
        self.is_connected = False

    def _on_close(self, ws, close_status_code, close_msg) -> None:
        """Handles the WebSocket connection closing."""
        self.lg.warning(f"{NY}Bybit WebSocket connection closed.{RST}")
        self.is_connected = False

    def _subscribe_to_topics(self) -> None:
        """Subscribes to the required WebSocket topics."""
        if not self.ws:
            return

        symbols = [
            self.mi[s]["id"]
            for s in self.cfg["symbols_to_trade"]
            if s in self.mi and "id" in self.mi[s]
        ]
        topics = [f"tickers.{symbol}" for symbol in symbols]
        sub_message = {"op": "subscribe", "args": topics}
        self.ws.send(json.dumps(sub_message))
        self.lg.info(f"{NB}Subscribed to WebSocket topics: {topics}{RST}")

    def close(self) -> None:
        """Closes the WebSocket connection."""
        if self.ws:
            self.ws.close()
