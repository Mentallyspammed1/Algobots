import os, time, uuid
from dataclasses import asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
from collections import deque
import asyncio # Added for async run method

from pybit.unified_trading import WebSocket, HTTP  # pip install pybit

from config import Config # Import project's Config

# ========= Helpers =========
def q_round(v: Decimal, step: Decimal) -> Decimal:
    n = (v / step).to_integral_value(rounding=ROUND_DOWN)
    return (n * step).normalize()

# ========= REST wrapper =========
class BybitRest:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = HTTP(testnet=cfg.TESTNET, api_key=cfg.API_KEY, api_secret=cfg.API_SECRET)
        self.tick: Decimal = Decimal("0.5")
        self.qty_step: Decimal = Decimal("0.001")
        self.min_notional: Decimal = Decimal("0")
        self.min_qty: Decimal = Decimal("0")
        self.max_qty: Decimal = Decimal("999999999") # Placeholder for a very large number
        self.position_idx = 0  # 0 one-way; use 1/2 for hedge-mode
        self.load_instrument()

    def load_instrument(self):
        info = self.http.get_instruments_info(category=self.cfg.CATEGORY, symbol=self.cfg.SYMBOL)
        item = info["result"]["list"][0]
        self.tick = Decimal(item["priceFilter"]["tickSize"])
        lot = item["lotSizeFilter"]
        self.qty_step = Decimal(lot.get("qtyStep", lot.get("basePrecision", "0.000001")))
        self.min_notional = Decimal(lot.get("minNotionalValue", lot.get("minOrderAmt", "0")))
        self.min_qty = Decimal(lot.get("minOrderQty", "0"))
        self.max_qty = Decimal(lot.get("maxOrderQty", "999999999"))

    # ---------- Batch trading ----------
    def place_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.place_batch_order(category=self.cfg.CATEGORY, request=reqs)  # /v5/order/create-batch

    def amend_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.amend_batch_order(category=self.cfg.CATEGORY, request=reqs)  # /v5/order/amend-batch

    def cancel_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.cancel_batch_order(category=self.cfg.CATEGORY, request=reqs)  # /v5/order/cancel-batch

    # ---------- Position protection (TP/SL/Trailing) ----------
    def set_trailing(self, trailing_dist: Decimal, active_price: Optional[Decimal]):
        payload = {
            "category": self.cfg.CATEGORY,
            "symbol": self.cfg.SYMBOL,
            "tpslMode": "Full",
            "trailingStop": str(trailing_dist),
            "positionIdx": self.position_idx,
        }
        if active_price is not None:
            payload["activePrice"] = str(active_price)
        return self.http.set_trading_stop(payload)  # /v5/position/trading-stop

    def set_stop_loss(self, stop_price: Decimal):
        payload = {
            "category": self.cfg.CATEGORY,
            "symbol": self.cfg.SYMBOL,
            "tpslMode": "Full",
            "stopLoss": str(stop_price),
            "positionIdx": self.position_idx,
        }
        return self.http.set_trading_stop(payload)

# ========= WS: public =========
class PublicWS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ws = WebSocket(testnet=cfg.TESTNET, channel_type=cfg.CATEGORY)
        self.best_bid = self.best_ask = None
        self.bid_sz = self.ask_sz = None
        self.ws.orderbook_stream(depth=50, symbol=cfg.SYMBOL, callback=self.on_book)

    def on_book(self, msg):
        d = msg.get("data") or {}
        b, a = d.get("b"), d.get("a")
        if b: self.best_bid, self.bid_sz = Decimal(b[0][0]), Decimal(b[0][1])
        if a: self.best_ask, self.ask_sz = Decimal(a[0][0]), Decimal(a[0][1])

    def mid(self) -> Optional[Decimal]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    def microprice(self) -> Optional[Decimal]:
        if None in (self.best_bid, self.best_ask, self.bid_sz, self.ask_sz):
            return None
        tot = self.bid_sz + self.ask_sz
        return (self.best_ask * self.bid_sz + self.best_bid * self.ask_sz) / tot if tot else self.mid()

# ========= WS: private =========
class PrivateWS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ws = WebSocket(testnet=cfg.TESTNET, channel_type="private",
                            api_key=cfg.API_KEY, api_secret=cfg.API_SECRET)
        self.position_qty = Decimal("0")
        self.entry_price = None
        self.mark_price = None
        self.stop_loss = None
        self.trailing_stop = None
        self.ws.position_stream(callback=self.on_position)
        self.orders: Dict[str, Dict] = {}
        self.ws.order_stream(callback=self.on_order)
        self.ws.execution_stream(callback=self.on_exec)

    def on_position(self, msg):
        for p in msg.get("data", []):
            if p.get("symbol") != self.cfg.SYMBOL: continue
            side = p.get("side", "")
            size = Decimal(p.get("size", "0"))
            self.position_qty = size if side == "Buy" else (-size if side == "Sell" else Decimal("0"))
            self.entry_price = Decimal(p.get("entryPrice", p.get("avgPrice", "0") or "0")) or None
            self.mark_price = Decimal(p.get("markPrice", "0") or "0") or None
            self.stop_loss = Decimal(p.get("stopLoss", "0") or "0") or None
            self.trailing_stop = Decimal(p.get("trailingStop", "0") or "0") or None

    def on_order(self, msg):
        for o in msg.get("data", []):
            link = o.get("orderLinkId") or o.get("orderId")
            if link: self.orders[link] = o

    def on_exec(self, msg):
        pass  # hook if you want PnL calc per fill

# ========= Quoter using batch endpoints =========
class Quoter:
    def __init__(self, cfg: Config, rest: BybitRest, pub: PublicWS, prv: PrivateWS, position_sizer: PositionSizer):
        self.cfg, self.rest, self.pub, self.prv, self.position_sizer = cfg, rest, pub, prv, position_sizer
        base = uuid.uuid4().hex[:8].upper()
        self.bid_link = f"MM_BID_{base}"
        self.ask_link = f"MM_ASK_{base}"
        self.working_bid: Optional[Decimal] = None
        self.working_ask: Optional[Optional[Decimal]] = None

    def compute_quotes(self):
        anchor = self.pub.microprice() or self.pub.mid()
        if anchor is None: return None, None
        half = max(
            (Decimal(self.cfg.BASE_SPREAD_BPS) / Decimal(1e4)) * anchor,
            Decimal(self.cfg.MIN_SPREAD_TICKS) * self.rest.tick
        )
        bid = q_round(anchor - half, self.rest.tick)
        ask = q_round(anchor + half, self.rest.tick)
        if self.pub.best_bid and bid > self.pub.best_bid: bid = self.pub.best_bid
        if self.pub.best_ask and ask < self.pub.best_ask: ask = self.pub.best_ask
        return bid, ask

    def _ok_qty(self, qty: Decimal) -> Optional[Decimal]:
        q = q_round(qty, self.rest.qty_step)
        # Validate against instrument min/max quantity
        if q < self.rest.min_qty or q > self.rest.max_qty:
            return None
        mid = self.pub.mid() or Decimal("0")
        notional = q * mid
        if (self.rest.min_notional and notional < self.rest.min_notional) or \
           (self.cfg.MAX_POSITION and notional > self.cfg.MAX_POSITION):
            return None
        return q

    def upsert_both(self):
        bid, ask = self.compute_quotes()
        if (bid is None) or (ask is None) or (bid >= ask): return
        q = self.position_sizer.calculate_quote_size(bid) # Use bid as anchor for quote size
        if not q: return

        to_place, to_amend = [], []
        # Decide if each side needs place vs amend
        for side, px, link in [("Buy", bid, self.bid_link), ("Sell", ask, self.ask_link)]:
            wk = self.working_bid if side == "Buy" else self.working_ask
            if wk is None:
                to_place.append({
                    "symbol": self.cfg.SYMBOL,
                    "side": side,
                    "orderType": "Limit",
                    "qty": str(q),
                    "price": str(px),
                    "timeInForce": "PostOnly" if self.cfg.POST_ONLY else "GTC",
                    "orderLinkId": link,
                    "positionIdx": self.rest.position_idx,
                })
                if side == "Buy": self.working_bid = px
                else: self.working_ask = px
            else:
                moved_ticks = abs((px - wk) / self.rest.tick)
                if moved_ticks >= self.cfg.REPLACE_THRESHOLD_TICKS:
                    to_amend.append({
                        "symbol": self.cfg.SYMBOL,
                        "orderLinkId": link,
                        "price": str(px),
                        "qty": str(q),
                    })
                    if side == "Buy": self.working_bid = px
                    else: self.working_ask = px

        if to_place:
            self.rest.place_batch(to_place)  # batch create both sides together
        if to_amend:
            self.rest.amend_batch(to_amend)  # batch amend both sides together

    def cancel_all_quotes(self):
        to_cancel = []
        for link in [self.bid_link, self.ask_link]:
            to_cancel.append({"symbol": self.cfg.SYMBOL, "orderLinkId": link})
        if to_cancel:
            self.rest.cancel_batch(to_cancel)

# ========= Protection manager =========
class Protection:
    def __init__(self, cfg: Config, rest: BybitRest, prv: PrivateWS):
        self.cfg, self.rest, self.prv = cfg, rest, prv
        self._be_applied = False
        self._trail_applied = False

    def step(self):
        if self.cfg.PROTECT_MODE == "off": return
        sz = self.prv.position_qty
        entry = self.prv.entry_price
        mark = self.prv.mark_price
        if not sz or not entry or not mark:
            self._be_applied = self._trail_applied = False
            return

        long = sz > 0
        pnl_bps = (mark / entry - 1) * Decimal(1e4) if long else (1 - mark / entry) * Decimal(1e4)

        if self.cfg.PROTECT_MODE == "trailing":
            # Optional profit activation via activePrice
            active_px = None
            if self.cfg.TRAILING_ACTIVATE_PROFIT_BPS > 0:
                mul = (Decimal(1) + self.cfg.TRAILING_ACTIVATE_PROFIT_BPS / Decimal(1e4)) if long \
                      else (Decimal(1) - self.cfg.TRAILING_ACTIVATE_PROFIT_BPS / Decimal(1e4))
                active_px = q_round(entry * mul, self.rest.tick)
            if not self._trail_applied:
                self.rest.set_trailing(self.cfg.TRAILING_DISTANCE, active_px)
                self._trail_applied = True

        elif self.cfg.PROTECT_MODE == "breakeven":
            if (not self._be_applied) and (pnl_bps >= self.cfg.BE_TRIGGER_BPS):
                offset = self.cfg.BE_OFFSET_TICKS * self.rest.tick
                be_px = entry + offset if long else entry - offset
                self.rest.set_stop_loss(be_px)
                self._be_applied = True

# ========= Position Sizer =========
class PositionSizer:
    def __init__(self, cfg: Config, rest: BybitRest):
        self.cfg = cfg
        self.rest = rest

    def calculate_quote_size(self, entry_price: Decimal) -> Decimal:
        # This is a simplified example. In a real bot, stop_loss_price
        # would come from strategy logic or a fixed percentage.
        # For market making, we can use a fraction of the spread as implied risk.
        # Let's use a fixed percentage from config for now.
        risk_per_trade_pct = Decimal(str(self.cfg.RISK_PER_TRADE_PCT)) # Assuming a new config param
        account_balance = Decimal("10000") # Placeholder: needs to be fetched from exchange

        # Calculate an implied stop loss price based on a percentage of entry price
        # This is a simplification for quoting, not actual SL for a position.
        implied_stop_loss_price = entry_price * (Decimal("1") - risk_per_trade_pct)
        stop_loss_distance = abs(entry_price - implied_stop_loss_price)

        if stop_loss_distance == Decimal("0"):
            return self.rest.min_qty # Avoid division by zero

        risk_amount = account_balance * risk_per_trade_pct
        position_size_raw = risk_amount / stop_loss_distance

        # Apply leverage if applicable (for linear/inverse)
        leverage = Decimal(str(self.cfg.LEVERAGE))
        position_size_leveraged = position_size_raw * leverage

        # Round to valid quantity step
        q = q_round(position_size_leveraged, self.rest.qty_step)

        # Validate against instrument min/max quantity
        q = max(q, self.rest.min_qty)
        q = min(q, self.rest.max_qty)

        # Validate against min notional
        notional = q * entry_price
        if notional < self.rest.min_notional:
            q = q_round(self.rest.min_notional / entry_price, self.rest.qty_step)
            q = max(q, self.rest.min_qty) # Re-validate after min_notional adjustment

        return q

# ========= MarketMaker (formerly App) =========
class MarketMaker:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rest = BybitRest(cfg)
        self.rest.load_instrument()  # fetch tick/lot/minNotional
        self.pub = PublicWS(cfg)
        self.prv = PrivateWS(cfg)
        self.position_sizer = PositionSizer(cfg, self.rest)
        self.quoter = Quoter(cfg, self.rest, self.pub, self.prv, self.position_sizer)
        self.protect = Protection(cfg, self.rest, self.prv)
        self._stop = False
        self._last_log = 0

    async def run(self):
        print("Config:", asdict(self.cfg))
        try:
            while not self._stop:
                self.quoter.upsert_both()
                self.protect.step()
                if time.time() - self._last_log > self.cfg.LOG_EVERY_SECS: # Changed from log_every_secs to LOG_EVERY_SECS
                    self._last_log = time.time()
                    print(f"[{time.strftime('%X')}] bid/ask={self.pub.best_bid}/{self.pub.best_ask} "
                          f"pos={self.prv.position_qty} entry={self.prv.entry_price} mark={self.prv.mark_price}")
                await asyncio.sleep(self.cfg.REFRESH_MS / 1000.0) # Changed from refresh_ms to REFRESH_MS
        except KeyboardInterrupt:
            self.shutdown()
        except Exception as e:
            print("Main loop error:", e)
            self.shutdown()

    def shutdown(self):
        self._stop = True
        try: self.quoter.cancel_all_quotes()
        except Exception: pass
        print("Shutdown complete")

    def update_orders(self):
        """Wrapper for backtesting to update quotes and protection."""
        self.quoter.upsert_both()
        self.protect.step()