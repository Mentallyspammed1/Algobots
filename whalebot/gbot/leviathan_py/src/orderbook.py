"""
Python port of the `LocalOrderBook` class from `aimm.cjs`.
"""
from typing import Dict, List, Tuple, Any

class LocalOrderBook:
    """
    Manages a local copy of the order book and calculates liquidity metrics.
    """
    def __init__(self, depth: int = 20):
        self.bids: Dict[float, float] = {}
        self.asks: Dict[float, float] = {}
        self.ready: bool = False
        self.depth = depth
        self.metrics: Dict[str, Any] = {
            'wmp': 0.0,
            'spread': 0.0,
            'bid_wall': 0.0,
            'ask_wall': 0.0,
            'skew': 0.0,
            'prev_bid_wall': 0.0,
            'prev_ask_wall': 0.0,
            'wall_status': 'Stable'
        }

    def _process_levels(self, levels: List[Tuple[str, str]], book: Dict[float, float]):
        """Helper to update a bid or ask book."""
        if not levels:
            return
        for price_str, size_str in levels:
            price, size = float(price_str), float(size_str)
            if size == 0:
                book.pop(price, None)
            else:
                book[price] = size

    def update(self, data: Dict[str, Any], is_snapshot: bool = False):
        """
        Update the order book with new data from the stream.
        `data` is expected to have 'b' for bids and 'a' for asks.
        """
        if is_snapshot:
            self.bids.clear()
            self.asks.clear()
            self._process_levels(data.get('b', []), self.bids)
            self._process_levels(data.get('a', []), self.asks)
            self.ready = True
        else:
            if not self.ready:
                return
            self._process_levels(data.get('b', []), self.bids)
            self._process_levels(data.get('a', []), self.asks)
        
        self.calculate_metrics()

    def get_best_bid_ask(self) -> Dict[str, float]:
        """Get the current best bid and ask prices."""
        if not self.ready or not self.bids or not self.asks:
            return {'bid': 0.0, 'ask': 0.0}
        
        best_bid = max(self.bids.keys())
        best_ask = min(self.asks.keys())
        return {'bid': best_bid, 'ask': best_ask}

    def calculate_metrics(self):
        """
        Calculates key order book metrics like WMP, skew, and wall status.
        """
        if not self.ready or not self.bids or not self.asks:
            return

        bids = sorted(self.bids.items(), key=lambda x: x[0], reverse=True)[:self.depth]
        asks = sorted(self.asks.items(), key=lambda x: x[0])[:self.depth]

        if not bids or not asks:
            return

        best_bid_price, best_bid_size = bids[0]
        best_ask_price, best_ask_size = asks[0]
        
        total_top_level_vol = best_bid_size + best_ask_size
        if total_top_level_vol > 0:
            imb_weight = best_bid_size / total_top_level_vol
            self.metrics['wmp'] = (best_bid_price * (1 - imb_weight)) + (best_ask_price * imb_weight)
        else:
            self.metrics['wmp'] = (best_bid_price + best_ask_price) / 2

        self.metrics['spread'] = best_ask_price - best_bid_price

        current_bid_wall = max(s for p, s in bids)
        current_ask_wall = max(s for p, s in asks)

        # Wall Exhaustion Logic
        if self.metrics['prev_bid_wall'] > 0 and current_bid_wall < self.metrics['prev_bid_wall'] * 0.7:
            self.metrics['wall_status'] = 'BID_WALL_BROKEN'
        elif self.metrics['prev_ask_wall'] > 0 and current_ask_wall < self.metrics['prev_ask_wall'] * 0.7:
            self.metrics['wall_status'] = 'ASK_WALL_BROKEN'
        elif current_bid_wall > current_ask_wall * 1.5:
            self.metrics['wall_status'] = 'BID_SUPPORT'
        elif current_ask_wall > current_bid_wall * 1.5:
            self.metrics['wall_status'] = 'ASK_RESISTANCE'
        else:
            self.metrics['wall_status'] = 'BALANCED'

        self.metrics['prev_bid_wall'] = current_bid_wall
        self.metrics['prev_ask_wall'] = current_ask_wall
        self.metrics['bid_wall'] = current_bid_wall
        self.metrics['ask_wall'] = current_ask_wall

        total_bid_vol = sum(s for p, s in bids)
        total_ask_vol = sum(s for p, s in asks)
        total_vol = total_bid_vol + total_ask_vol
        self.metrics['skew'] = (total_bid_vol - total_ask_vol) / total_vol if total_vol > 0 else 0

    def get_analysis(self) -> Dict[str, Any]:
        """Return the calculated metrics."""
        return self.metrics

