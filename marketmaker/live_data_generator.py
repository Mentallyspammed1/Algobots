
import logging
import queue
from typing import Iterator
from pybit.unified_trading import WebSocket
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LiveDataGenerator:
    def __init__(self, symbol: str):
        self.config = Config()
        self.symbol = symbol
        self.ws = None
        self.queue = queue.Queue()

    def start_websocket(self) -> None:
        """Initializes and starts the WebSocket connection."""
        self.ws = WebSocket(
            testnet=self.config.TESTNET,
            channel_type="linear",
            api_key=self.config.API_KEY,
            api_secret=self.config.API_SECRET
        )
        self.ws.orderbook_stream(depth=50, symbol=self.symbol, callback=self.handle_message)
        self.ws.trade_stream(symbol=self.symbol, callback=self.handle_message)
        logger.info("WebSocket connection started.")

    def handle_message(self, message: dict) -> None:
        """Callback function to handle incoming WebSocket messages."""
        self.queue.put(message)

    def data_generator(self) -> Iterator[dict]:
        """Yields live market data."""
        if not self.ws:
            self.start_websocket()
        
        while True:
            try:
                data = self.queue.get(timeout=1)  # Wait for 1 second
                yield data
            except queue.Empty:
                # logger.info("No new data in the last second.")
                pass

if __name__ == '__main__':
    generator = LiveDataGenerator(symbol='TRUMPUSDT')
    for data in generator.data_generator():
        logger.info(f"Received data: {data}")
