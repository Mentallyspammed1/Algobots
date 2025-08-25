# trade_metrics.py
import logging
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Initialize logging for trade_metrics
trade_metrics_logger = logging.getLogger('trade_metrics')
trade_metrics_logger.setLevel(logging.INFO)
# Ensure handlers are not duplicated if setup_logging is called elsewhere
if not trade_metrics_logger.handlers:
    # This assumes bot_logger.setup_logging() has been called and configured the root logger
    # If not, you might need to add a basic handler here or ensure it's handled by the main setup
    pass

class TradeMetrics:
    """
    Calculates fees and tracks various trade metrics such as PnL, win rate, etc.
    """
    def __init__(self, maker_fee: float = 0.0002, taker_fee: float = 0.0007):
        self.maker_fee = Decimal(str(maker_fee))
        self.taker_fee = Decimal(str(taker_fee))
        self.total_realized_pnl = Decimal('0')
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.trade_history = [] # Stores details of each closed trade
        trade_metrics_logger.info(f"TradeMetrics initialized with Maker Fee: {self.maker_fee}, Taker Fee: {self.taker_fee}")

    def calculate_fee(self, quantity: Decimal, price: Decimal, is_maker: bool) -> Decimal:
        """
        Calculates the trading fee for a given trade.

        Args:
            quantity (Decimal): The quantity of the asset traded.
            price (Decimal): The price at which the asset was traded.
            is_maker (bool): True if the order was a maker order, False for taker.

        Returns:
            Decimal: The calculated fee.
        """
        trade_value = quantity * price
        fee_rate = self.maker_fee if is_maker else self.taker_fee
        fee = trade_value * fee_rate
        trade_metrics_logger.debug(f"Calculated fee: {fee} for trade value {trade_value} (Maker: {is_maker})")
        return fee.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP)

    def record_trade(self, entry_price: Decimal, exit_price: Decimal, quantity: Decimal, side: str,
                     entry_fee: Decimal, exit_fee: Decimal, timestamp: Any):
        """
        Records a completed trade and updates PnL and trade statistics.

        Args:
            entry_price (Decimal): Price at which the position was opened.
            exit_price (Decimal): Price at which the position was closed.
            quantity (Decimal): Quantity of the asset traded.
            side (str): 'BUY' or 'SELL' (side of the entry trade).
            entry_fee (Decimal): Fee incurred for the entry trade.
            exit_fee (Decimal): Fee incurred for the exit trade.
            timestamp (Any): Timestamp of the exit trade.
        """
        pnl = Decimal('0')
        if side.upper() == 'BUY':
            pnl = (exit_price - entry_price) * quantity
        elif side.upper() == 'SELL':
            pnl = (entry_price - exit_price) * quantity

        net_pnl = pnl - entry_fee - exit_fee
        self.total_realized_pnl += net_pnl
        self.total_trades += 1

        if net_pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1

        trade_details = {
            'entry_price': entry_price,
            'exit_price': exit_price,
            'quantity': quantity,
            'side': side,
            'gross_pnl': pnl.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP),
            'entry_fee': entry_fee,
            'exit_fee': exit_fee,
            'net_pnl': net_pnl.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP),
            'timestamp': timestamp
        }
        self.trade_history.append(trade_details)
        trade_metrics_logger.info(f"Trade recorded: Side={side}, Gross PnL={pnl:.8f}, Net PnL={net_pnl:.8f}")

    def get_win_rate(self) -> Decimal:
        """
        Calculates the win rate.
        """
        if self.total_trades == 0:
            return Decimal('0.0')
        return (Decimal(self.winning_trades) / Decimal(self.total_trades)) * Decimal('100')

    def get_total_realized_pnl(self) -> Decimal:
        """
        Returns the total realized PnL.
        """
        return self.total_realized_pnl

    def get_trade_statistics(self) -> dict[str, Any]:
        """
        Returns a dictionary of overall trade statistics.
        """
        return {
            'total_realized_pnl': self.total_realized_pnl.quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP),
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': self.get_win_rate(),
            'trade_history_count': len(self.trade_history)
        }
