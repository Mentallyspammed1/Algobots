import os, time, uuid
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Dict, Any, List
from collections import deque
import asyncio # Added for async run method

from pybit.unified_trading import WebSocket, HTTP  # pip install pybit

from config import Config # Import project's Config

# ========= Helpers =========
def q_round(v: Decimal, step: Decimal) -> Decimal:
    n = (v / step).to_integral_value(rounding=ROUND_HALF_UP)
    return (n * step).normalize()

# ========= REST wrapper =========
class BybitRest:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.http = HTTP(
            testnet=cfg.TESTNET, # Use project's Config
            api_key=cfg.API_KEY, # Use project's Config
            api_secret=cfg.API_SECRET # Use project's Config
        )
        self.tick: Decimal = Decimal("0.5")
        self.qty_step: Decimal = Decimal("0.001")
        self.min_notional: Decimal = Decimal("0")
        self.position_idx = 0  # one-way; use 1/2 for hedge-mode
        self.load_instrument()

    def load_instrument(self):
        info = self.http.get_instruments_info(category=self.cfg.CATEGORY, symbol=self.cfg.SYMBOL) # Use project's Config
        item = info["result"]["list"][0]
        self.tick = Decimal(item["priceFilter"]["tickSize"])
        lot = item["lotSizeFilter"]
        self.qty_step = Decimal(lot.get("qtyStep", lot.get("basePrecision", "0.000001")))
        self.min_notional = Decimal(lot.get("minNotionalValue", lot.get("minOrderAmt", "0")))

    # ---------- Batch trading ----------
    def place_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.place_batch_order(category=self.cfg.CATEGORY, request=reqs) # Use project's Config

    def amend_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.amend_batch_order(category=self.cfg.CATEGORY, request=reqs) # Use project's Config

    def cancel_batch(self, reqs: List[Dict[str, Any]]):
        return self.http.cancel_batch_order(category=self.cfg.CATEGORY, request=reqs) # Use project's Config

    # ---------- Position protection (TP/SL/Trailing) ----------
    def set_trailing(self, trailing_dist: Decimal, active_price: Optional[Decimal]):
        payload = {
            "category": self.cfg.CATEGORY, # Use project's Config
            "symbol": self.cfg.SYMBOL, # Use project's Config
            "tpslMode": "Full",
            "trailingStop": str(trailing_dist),
            "positionIdx": self.position_idx,
        }
        if active_price is not None:
            payload["activePrice"] = str(active_price)
        return self.http.set_trading_stop(payload)

    def set_stop_loss(self, stop_price: Decimal):
        payload = {
            "category": self.cfg.CATEGORY, # Use project's Config
            "symbol": self.cfg.SYMBOL, # Use project's Config
            "tpslMode": "Full",
            "stopLoss": str(stop_price),
            "positionIdx": self.position_idx,
        }
        return self.http.set_trading_stop(payload)

# ========= WS: public =========
class PublicWS:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ws = WebSocket(testnet=cfg.TESTNET, channel_type=cfg.CATEGORY) # Use project's Config
        self.best_bid = self.best_ask = None
        self.bid_sz = self.ask_sz = None
        self.ws.orderbook_stream(depth=50, symbol=cfg.SYMBOL, callback=self.on_book) # Use project's Config

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
        self.ws = WebSocket(
            testnet=cfg.TESTNET, # Use project's Config
            channel_type="private",
            api_key=cfg.API_KEY, # Use project's Config
            api_secret=cfg.API_SECRET, # Use project's Config
        )
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
            if p.get("symbol") != self.cfg.SYMBOL: continue # Use project's Config
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
    def __init__(self, cfg: Config, rest: BybitRest, pub: PublicWS, prv: PrivateWS):
        self.cfg, self.rest, self.pub, self.prv = cfg, rest, pub, prv
        base = uuid.uuid4().hex[:8].upper()
        self.bid_link = f"MM_BID_{base}"
        self.ask_link = f"MM_ASK_{base}"
        self.working_bid: Optional[Decimal] = None
        self.working_ask: Optional[Decimal] = None

    def compute_quotes(self):
        anchor = self.pub.microprice() or self.pub.mid()
        if anchor is None: return None, None
        half = max(
            (Decimal(self.cfg.BASE_SPREAD) / Decimal(1e4)) * anchor, # Use project's Config
            Decimal(self.cfg.MIN_SPREAD) * self.rest.tick # Use project's Config
        )
        bid = q_round(anchor - half, self.rest.tick)
        ask = q_round(anchor + half, self.rest.tick)
        if self.pub.best_bid and bid > self.pub.best_bid: bid = self.pub.best_bid
        if self.pub.best_ask and ask < self.pub.best_ask: ask = self.pub.best_ask
        return bid, ask

    def _ok_qty(self, qty: Decimal) -> Optional[Decimal]:
        q = q_round(qty, self.rest.qty_step)
        mid = self.pub.mid() or Decimal("0")
        notional = q * mid
        if (self.rest.min_notional and notional < self.rest.min_notional) or \
           (self.cfg.MAX_POSITION and notional > self.cfg.MAX_POSITION): # Use project's Config
            return None
        return q

    def upsert_both(self):
        bid, ask = self.compute_quotes()
        if (bid is None) or (ask is None) or (bid >= ask): return
        q = self._ok_qty(Decimal(str(self.cfg.MIN_ORDER_SIZE))) # Use project's Config
        if not q: return

        to_place, to_amend = [], []
        # Decide if each side needs place vs amend
        for side, px, link in [("Buy", bid, self.bid_link), ("Sell", ask, self.ask_link)]:
            wk = self.working_bid if side == "Buy" else self.working_ask
            if wk is None:
                to_place.append({
                    "symbol": self.cfg.SYMBOL, # Use project's Config
                    "side": side,
                    "orderType": "Limit",
                    "qty": str(q),
                    "price": str(px),
                    "timeInForce": "PostOnly" if self.cfg.POST_ONLY else "GTC", # Use project's Config
                    "orderLinkId": link,
                    "positionIdx": self.rest.position_idx,
                })
                if side == "Buy": self.working_bid = px
                else: self.working_ask = px
            else:
                moved_ticks = abs((px - wk) / self.rest.tick)
                if moved_ticks >= self.cfg.REPLACE_THRESHOLD_TICKS: # Use project's Config
                    to_amend.append({
                        "symbol": self.cfg.SYMBOL, # Use project's Config
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
            to_cancel.append({"symbol": self.cfg.SYMBOL, "orderLinkId": link}) # Use project's Config
        if to_cancel:
            self.rest.cancel_batch(to_cancel)

# ========= Protection manager =========
class Protection:
    def __init__(self, cfg: Config, rest: BybitRest, prv: PrivateWS):
        self.cfg, self.rest, self.prv = cfg, rest, prv
        self._be_applied = False
        self._trail_applied = False

    def step(self):
        if self.cfg.PROTECT_MODE == "off": return # Use project's Config
        sz = self.prv.position_qty
        entry = self.prv.entry_price
        mark = self.prv.mark_price
        if not sz or not entry or not mark: 
            self._be_applied = self._trail_applied = False
            return

        long = sz > 0
        pnl_bps = (mark / entry - 1) * Decimal(1e4) if long else (1 - mark / entry) * Decimal(1e4)

        if self.cfg.PROTECT_MODE == "trailing": # Use project's Config
            # Optional profit activation via activePrice
            active_px = None
            if self.cfg.TRAILING_ACTIVATE_PROFIT_BPS > 0: # Use project's Config
                mul = (Decimal(1) + self.cfg.TRAILING_ACTIVATE_PROFIT_BPS / Decimal(1e4)) if long \
                      else (Decimal(1) - self.cfg.TRAILING_ACTIVATE_PROFIT_BPS / Decimal(1e4))
                active_px = q_round(entry * mul, self.rest.tick)
            if not self._trail_applied:
                self.rest.set_trailing(Decimal(str(self.cfg.TRAILING_DISTANCE_PCT)), active_px)
                self._trail_applied = True

        elif self.cfg.PROTECT_MODE == "breakeven": # Use project's Config
            if (not self._be_applied) and (pnl_bps >= self.cfg.BE_TRIGGER_BPS): # Use project's Config
                offset = self.cfg.BE_OFFSET_TICKS * self.rest.tick # Use project's Config
                be_px = entry + offset if long else entry - offset
                self.rest.set_stop_loss(be_px)
                self._be_applied = True

# ========= MarketMaker (formerly App) =========
class MarketMaker:
    def __init__(self):
        self.config = Config()
        self.rest = BybitRest(self.config)
        self.rest.load_instrument()  # fetch tick/lot/minNotional
        self.pub = PublicWS(self.config)
        self.prv = PrivateWS(self.config)
        self.quoter = Quoter(self.config, self.rest, self.pub, self.prv)
        self.protect = Protection(self.config, self.rest, self.prv)
        self._stop = False
        self._last_log = 0

    async def run(self):
        print("Config:", asdict(self.config))
        # Start WebSocket connections
        if self.config.USE_WEBSOCKET: # Check if WebSocket is enabled in project's Config
            print("Connecting WebSockets...")
            # Pybit WebSocket run_forever is blocking, so run in separate threads/tasks
            # For simplicity, we'll use asyncio.create_task here.
            # Note: Pybit's WebSocket class handles its own internal loop.
            # We just need to ensure it's started.
            # The PublicStreams and PrivateStreams classes already initialize their WebSockets.
            # We just need to keep the main app running.
            pass # WebSockets are already initialized and subscribed in PublicStreams/PrivateStreams __init__ 

        while not self._stop:
            try:
                self.quoter.upsert_both()
                self.protect.step()
                if time.time() - self._last_log > self.config.UPDATE_INTERVAL: # Use project's Config
                    self._last_log = time.time()
                    print(f"[{time.strftime('%X')}] bid/ask={self.pub.best_bid}/{self.pub.best_ask} "
                          f"pos={self.prv.position_qty} entry={self.prv.entry_price} mark={self.prv.mark_price}")
                await asyncio.sleep(self.config.UPDATE_INTERVAL) # Use project's Config and await
            except KeyboardInterrupt:
                self.shutdown()
            except Exception as e:
                print("Main loop error:", e)
                self.shutdown()

    def shutdown(self):
        self._stop = True
        try:
            self.quoter.cancel_all_quotes()
        except Exception:
            pass
        print("Shutdown complete")

    def update_orders(self):
        """Wrapper for backtesting to update quotes and protection."""
        self.quoter.upsert_both()
        self.protect.step()

    def update_orders(self):
        """Wrapper for backtesting to update quotes and protection."""
        self.quoter.upsert_both()
        self.protect.step()

    def update_orders(self):
        """Wrapper for backtesting to update quotes and protection."""
        self.quoter.upsert_both()
        self.protect.step()