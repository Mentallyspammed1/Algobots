# --- Bybit API Client (using pybit) ---
# Make sure to install pybit: pip install pybit
from pybit.unified_trading import HTTP

class BybitApiClient:
    """A real Bybit API client using pybit."""
    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
        )
        self.testnet = testnet
        logger.info(f"Initializing Bybit API Client. Testnet: {self.testnet}")

    def get_server_time(self) -> int:
        """Returns the current server time in milliseconds."""
        try:
            response = self.session.get_time()
            return int(response['time']) # pybit returns time in seconds, convert to ms
        except Exception as e:
            logger.error(f"Error getting server time: {e}", exc_info=True)
            raise

    def get_candlesticks(self, symbol: str, interval: str, limit: int = 200) -> List[List[Any]]:
        """
        Fetches candlestick data.
        Returns a list of lists, where each inner list represents a candle:
        [timestamp, open, high, low, close, volume]
        """
        logger.info(f"Fetching {interval} candlesticks for {symbol} (limit: {limit})")
        try:
            response = self.session.get_kline(
                symbol=symbol,
                interval=interval,
                limit=limit,
            )
            # pybit returns data in a different format, need to adapt
            # Example format: {'list': [['1678886400000', '20000.0', '20500.0', '19800.0', '20200.0', '1000.0', '100000.0']]}
            # We need: [timestamp, open, high, low, close, volume]
            candlesticks = []
            if 'list' in response:
                for candle in response['list']:
                    # Convert prices and volume to float, timestamp is already ms
                    candlesticks.append([
                        int(candle[0]), # timestamp (ms)
                        float(candle[1]), # open
                        float(candle[2]), # high
                        float(candle[3]), # low
                        float(candle[4]), # close
                        float(candle[5])  # volume
                    ])
            return candlesticks
        except Exception as e:
            logger.error(f"Error fetching candlesticks for {symbol}: {e}", exc_info=True)
            raise

    def get_position_info(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches current position information for a symbol.
        Returns a dictionary with 'side' ('Buy', 'Sell', or None) and 'size'.
        """
        logger.info(f"Fetching position info for {symbol}")
        try:
            response = self.session.get_positions(
                symbol=symbol,
                accountType="UNIFIED", # Or "CONTRACT" depending on your account type
            )
            # Example response: {'list': [{'side': 'Buy', 'size': '0.001', ...}]}
            positions = response.get('list', [])
            for pos in positions:
                if pos.get('symbol') == symbol and float(pos.get('size', 0.0)) > 0:
                    return {"side": pos.get('side'), "size": float(pos.get('size'))}
            return {"side": None, "size": 0.0} # No open position for this symbol
        except Exception as e:
            logger.error(f"Error fetching position info for {symbol}: {e}", exc_info=True)
            raise

    def place_order(self, symbol: str, side: str, order_type: str, qty: float, price: Optional[float] = None, time_in_force: str = "GTC") -> Dict[str, Any]:
        """Places an order."""
        logger.info(f"Placing order: {side} {qty} {symbol} @ {price if price else 'Market'} ({order_type}, TIF: {time_in_force})")
        try:
            # pybit's place_order expects 'Buy'/'Sell', 'Market'/'Limit'
            order_params = {
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": time_in_force,
                "accountType": "UNIFIED", # Or "CONTRACT"
            }
            if order_type == "Limit":
                order_params["price"] = str(price)

            response = self.session.place_order(**order_params)

            # Check response for success and return relevant info
            if response and response.get('retMsg') == 'OK':
                order_info = response.get('result', {})
                return {
                    "orderId": order_info.get('orderId'),
                    "symbol": symbol,
                    "side": side,
                    "type": order_type,
                    "qty": qty,
                    "price": price,
                    "status": "Filled" if order_type == "Market" else order_info.get('orderStatus') # Simplified status
                }
            else:
                logger.error(f"Order placement failed: {response}")
                return {"status": "Failed", "message": response.get('retMsg')}

        except Exception as e:
            logger.error(f"Error placing order for {symbol}: {e}", exc_info=True)
            raise

    def close_position(self, symbol: str, side: str, qty: float) -> Dict[str, Any]:
        """Closes the current position."""
        logger.info(f"Closing position: {side} {qty} {symbol}")
        try:
            # Use the unified trading endpoint for closing positions
            response = self.session.close_position(
                symbol=symbol,
                accountType="UNIFIED", # Or "CONTRACT"
                # Note: pybit's close_position might not directly take side and qty.
                # You might need to use place_order with the opposite side and qty.
                # Example using place_order for closing:
                side="Buy" if side == "Sell" else "Sell",
                orderType="Market",
                qty=str(qty),
                timeInForce="GTC", # Or "PostOnly" if preferred
            )
            if response and response.get('retMsg') == 'OK':
                 order_info = response.get('result', {})
                 return {"orderId": order_info.get('orderId'), "status": "Filled"}
            else:
                 logger.error(f"Close position failed: {response}")
                 return {"status": "Failed", "message": response.get('retMsg')}
        except Exception as e:
            logger.error(f"Error closing position for {symbol}: {e}", exc_info=True)
            raise
