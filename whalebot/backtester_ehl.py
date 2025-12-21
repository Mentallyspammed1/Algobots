import asyncio
import time
from decimal import ROUND_DOWN
from decimal import Decimal
from typing import Any

import numpy as np
from ehl import BASE_RISK_PERCENT
from ehl import CATEGORY
from ehl import SCALPING_COOLDOWN_SECONDS
from ehl import SCALPING_DYNAMIC_THRESHOLD
from ehl import SCALPING_SL_MULT
from ehl import SCALPING_TP_MULT
from ehl import SCALPING_TREND_STRENGTH_MIN
from ehl import SYMBOL

# Import necessary components from ehl.py
from ehl import SentinelState
from ehl import update_oracle
from rich.console import Console
from rich.panel import Panel

# --- Backtesting Specific Global Constants ---
# These can be overridden for optimization
BACKTEST_START_DATE = "2023-01-01"
BACKTEST_END_DATE = "2023-03-01"
INITIAL_CAPITAL = Decimal("1000.0")

# Parameter ranges for optimization
COOLDOWN_RANGE = [15, 30, 45] # seconds
DYNAMIC_THRESHOLD_RANGE = [0.5, 0.8, 1.0] # Fisher threshold
TREND_STRENGTH_RANGE = [0.2, 0.3, 0.4] # Minimum trend strength
SL_MULT_RANGE = [Decimal("1.0"), Decimal("1.2"), Decimal("1.5")] # Stop Loss multiplier
TP_MULT_RANGE = [Decimal("1.2"), Decimal("1.5"), Decimal("1.8")] # Take Profit multiplier

# --- Mock BybitForge for Backtesting ---
class MockBybitForge:
    def __init__(self, historical_klines: list[dict], state: SentinelState):
        self.historical_klines = historical_klines
        self.current_kline_index = 0
        self.state = state # Reference to the backtest_state
        self.simulated_balance = INITIAL_CAPITAL
        self.simulated_position = {
            "size": Decimal("0.0"),
            "side": "None",
            "avgPrice": Decimal("0.0"),
            "unrealisedPnl": Decimal("0.0")
        }
        self.simulated_orders = [] # To track placed orders for PnL calculation

    async def ignite(self):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    def _sign(self, ts: str, payload: str) -> str:
        return "mock_signature" # Not actually used in backtesting

    async def call(self, method: str, path: str, params: dict = None, signed: bool = False) -> dict[str, Any]:
        if path == "/v5/market/kline":
            if self.current_kline_index < len(self.historical_klines):
                kline_data = self.historical_klines[self.current_kline_index]
                # Simulate fetching one kline at a time for the logic engine
                self.current_kline_index += 1
                return {"retCode": 0, "result": {"list": [kline_data]}}
            return {"retCode": 1, "retMsg": "No more historical data"}
        if path == "/v5/account/wallet-balance":
            return {"retCode": 0, "result": {"list": [{"coin": [{"coin": "USDT", "walletBalance": str(self.simulated_balance)}]}]}}
        if path == "/v5/order/create":
            # Simulate order creation
            order_side = params["side"]
            order_qty = Decimal(params["qty"])
            order_price = state.price # Use current simulated price for market order

            # Update simulated position
            if order_side == "Buy":
                if self.simulated_position["side"] == "None":
                    self.simulated_position["side"] = "Buy"
                    self.simulated_position["avgPrice"] = order_price
                    self.simulated_position["size"] = order_qty
                elif self.simulated_position["side"] == "Buy":
                    # Average down
                    total_cost = (self.simulated_position["avgPrice"] * self.simulated_position["size"]) + (order_price * order_qty)
                    total_qty = self.simulated_position["size"] + order_qty
                    self.simulated_position["avgPrice"] = total_cost / total_qty
                    self.simulated_position["size"] = total_qty
                elif self.simulated_position["side"] == "Sell":
                    # Closing short position or flipping to long
                    if order_qty >= self.simulated_position["size"]:
                        # Close short and potentially open long
                        remaining_qty = order_qty - self.simulated_position["size"]
                        self.simulated_position["size"] = remaining_qty
                        self.simulated_position["side"] = "Buy" if remaining_qty > 0 else "None"
                        self.simulated_position["avgPrice"] = order_price if remaining_qty > 0 else Decimal("0.0")
                    else:
                        # Partially close short
                        self.simulated_position["size"] -= order_qty
            elif order_side == "Sell":
                if self.simulated_position["side"] == "None":
                    self.simulated_position["side"] = "Sell"
                    self.simulated_position["avgPrice"] = order_price
                    self.simulated_position["size"] = order_qty
                elif self.simulated_position["side"] == "Sell":
                    # Average up (short)
                    total_cost = (self.simulated_position["avgPrice"] * self.simulated_position["size"]) + (order_price * order_qty)
                    total_qty = self.simulated_position["size"] + order_qty
                    self.simulated_position["avgPrice"] = total_cost / total_qty
                    self.simulated_position["size"] = total_qty
                elif self.simulated_position["side"] == "Buy":
                    # Closing long position or flipping to short
                    if order_qty >= self.simulated_position["size"]:
                        # Close long and potentially open short
                        remaining_qty = order_qty - self.simulated_position["size"]
                        self.simulated_position["size"] = remaining_qty
                        self.simulated_position["side"] = "Sell" if remaining_qty > 0 else "None"
                        self.simulated_position["avgPrice"] = order_price if remaining_qty > 0 else Decimal("0.0")
                    else:
                        # Partially close long
                        self.simulated_position["size"] -= order_qty

            # For simplicity in backtesting, we'll assume market orders fill at state.price
            # and update balance based on PnL later when position is closed or managed.
            self.simulated_orders.append({
                "side": order_side,
                "qty": order_qty,
                "price": order_price,
                "takeProfit": Decimal(params.get("takeProfit", "0.0")),
                "stopLoss": Decimal(params.get("stopLoss", "0.0")),
                "reduceOnly": params.get("reduceOnly", False),
                "timestamp": time.time() # Use current simulated time
            })
            return {"retCode": 0, "result": {"orderId": "mock_order_id"}}
        if path == "/v5/market/instruments-info":
            # Mock instrument info for precision
            return {"retCode": 0, "result": {"list": [{"priceFilter": {"tickSize": "0.01"}, "lotSizeFilter": {"qtyStep": "0.001"}}]}}

        return {"retCode": -1, "retMsg": f"Mock API call not implemented for {path}"}

# --- Backtesting Trade Execution and Management ---
async def execute_trade(forge: MockBybitForge, side: str):
    state = forge.state # Get the state from the forge
    console = Console()

    if state.price == Decimal("0.0"):
        state.logs.append("[bold red]❌ Cannot execute trade: Price is 0.[/bold red]")
        return

    # Calculate order quantity based on available balance and risk
    available_balance = forge.simulated_balance
    risk_amount = available_balance * BASE_RISK_PERCENT

    # Determine position size based on risk and leverage
    # For backtesting, we'll simplify and assume we use a fixed percentage of capital
    # or a calculated amount based on risk.
    # Let's use a simple fixed percentage of initial capital for now.
    # In a real scenario, this would be more dynamic based on SL distance.

    # For simplicity, let's assume a fixed order size for now, or a percentage of initial capital
    # This needs to be refined for proper risk management in backtesting
    order_qty_decimal = (INITIAL_CAPITAL * Decimal("0.01") / state.price).quantize(state.qty_step, rounding=ROUND_DOWN) # Example: 1% of initial capital

    if order_qty_decimal == Decimal("0.0"):
        state.logs.append("[bold red]❌ Calculated order quantity is zero. Aborting trade.[/bold red]")
        return

    # Calculate TP/SL prices
    if side == "Buy":
        take_profit_price = state.price * (Decimal("1.0") + SCALPING_TP_MULT)
        stop_loss_price = state.price * (Decimal("1.0") - SCALPING_SL_MULT)
    else: # Sell
        take_profit_price = state.price * (Decimal("1.0") - SCALPING_TP_MULT)
        stop_loss_price = state.price * (Decimal("1.0") + SCALPING_SL_MULT)

    # Place order
    order_params = {
        "category": CATEGORY,
        "symbol": SYMBOL,
        "side": side,
        "orderType": "Market",
        "qty": str(order_qty_decimal),
        "takeProfit": str(take_profit_price.quantize(Decimal(f"1e-{state.price_prec}"))),
        "stopLoss": str(stop_loss_price.quantize(Decimal(f"1e-{state.price_prec}"))),
        "timeInForce": "GoodTillCancel",
        "reduceOnly": False,
        "closeOnTrigger": False,
        "isLeverage": 1,
        "triggerDirection": 1 if side == "Buy" else 2,
        "tpslMode": "Full"
    }

    state.logs.append(f"[bold yellow]Attempting to place {side} order:[/bold yellow] Qty: {order_qty_decimal}, TP: {take_profit_price:.{state.price_prec}f}, SL: {stop_loss_price:.{state.price_prec}f}")

    response = await forge.call("POST", "/v5/order/create", order_params, signed=True)

    if response and response.get("retCode") == 0:
        state.logs.append(f"[bold green]✅ {side} Order placed successfully![/bold green] Order ID: {response['result']['orderId']}")
        state.trade_active = True
        state.side = side
        state.entry_price = state.price
        state.qty = order_qty_decimal
        state.last_ritual = time.time() # Reset cooldown
        state.trade_count += 1
    else:
        state.logs.append(f"[bold red]❌ Failed to place {side} order: {response.get('retMsg', 'Unknown error')}[/bold red]")

async def manage_trade(forge: MockBybitForge):
    state = forge.state # Get the state from the forge
    console = Console()

    if not state.trade_active:
        return

    current_price = state.price
    position_size = forge.simulated_position["size"]
    position_side = forge.simulated_position["side"]
    entry_price = forge.simulated_position["avgPrice"]

    if position_size == Decimal("0.0"): # Position was closed by SL/TP or other means
        state.trade_active = False
        state.side = "None"
        state.entry_price = Decimal("0.0")
        state.qty = Decimal("0.0")
        state.upnl = Decimal("0.0")
        return

    # Check for Take Profit / Stop Loss (simulated)
    # This is a simplified simulation. In a real scenario, the exchange would trigger these.
    # Here, we check if current price crosses the simulated TP/SL levels from the last order.

    # Find the active order's TP/SL (simplistic: assumes last order's TP/SL are current)
    active_order_tp = Decimal("0.0")
    active_order_sl = Decimal("0.0")
    if forge.simulated_orders:
        last_order = forge.simulated_orders[-1]
        active_order_tp = last_order["takeProfit"]
        active_order_sl = last_order["stopLoss"]

    trade_closed = False
    pnl = Decimal("0.0")

    if position_side == "Buy":
        if current_price >= active_order_tp > Decimal("0.0"):
            state.logs.append(f"[bold green]🎉 Take Profit hit for Buy position at {current_price:.{state.price_prec}f}![/bold green]")
            pnl = (active_order_tp - entry_price) * position_size
            trade_closed = True
        elif current_price <= active_order_sl and active_order_sl > Decimal("0.0"):
            state.logs.append(f"[bold red]💔 Stop Loss hit for Buy position at {current_price:.{state.price_prec}f}![/bold red]")
            pnl = (active_order_sl - entry_price) * position_size
            trade_closed = True
    elif position_side == "Sell":
        if current_price <= active_order_tp and active_order_tp > Decimal("0.0"):
            state.logs.append(f"[bold green]🎉 Take Profit hit for Sell position at {current_price:.{state.price_prec}f}![/bold green]")
            pnl = (entry_price - active_order_tp) * position_size
            trade_closed = True
        elif current_price >= active_order_sl > Decimal("0.0"):
            state.logs.append(f"[bold red]💔 Stop Loss hit for Sell position at {current_price:.{state.price_prec}f}![/bold red]")
            pnl = (entry_price - active_order_sl) * position_size
            trade_closed = True

    if trade_closed:
        forge.simulated_balance += pnl # Update balance with realized PnL
        forge.simulated_position = { # Reset position
            "size": Decimal("0.0"),
            "side": "None",
            "avgPrice": Decimal("0.0"),
            "unrealisedPnl": Decimal("0.0")
        }
        state.trade_active = False
        state.side = "None"
        state.entry_price = Decimal("0.0")
        state.qty = Decimal("0.0")
        state.upnl = Decimal("0.0")

        if pnl > 0:
            state.win_count += 1
            state.total_profit += pnl
            state.logs.append(f"[bold green]Realized PnL: +{pnl:.2f} USDT[/bold green]")
        else:
            state.loss_count += 1
            state.total_loss += pnl
            state.logs.append(f"[bold red]Realized PnL: {pnl:.2f} USDT[/bold red]")

        state.logs.append(f"New Balance: {forge.simulated_balance:.2f} USDT")
        state.last_ritual = time.time() # Reset cooldown after trade close

# --- Backtesting SentinelState ---
# We'll use the same SentinelState but initialize balance for backtesting
class BacktestingSentinelState(SentinelState):
    def __init__(self):
        super().__init__()
        self.balance = INITIAL_CAPITAL
        self.initial_balance = INITIAL_CAPITAL
        self.high_water_mark_equity = INITIAL_CAPITAL
        self.daily_pnl = Decimal("0.0")
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_profit = Decimal("0.0")
        self.total_loss = Decimal("0.0")
        self.max_drawdown = Decimal("0.0")
        self.peak_equity = INITIAL_CAPITAL
        self.equity_history = []

backtest_state = BacktestingSentinelState()

# --- Backtesting Logic Engine ---
async def backtest_logic_engine(forge: MockBybitForge):
    global state # Use the global state object from ehl.py for indicators
    state = backtest_state # Override with backtesting state

    while forge.current_kline_index < len(forge.historical_klines):
        kline_response = await forge.call("GET", "/v5/market/kline", {"category": CATEGORY, "symbol": SYMBOL, "interval": "1", "limit": 1})

        if kline_response and kline_response.get('retCode') == 0:
            candle = kline_response['result']['list'][0]
            # Update OHLC and price
            state.ohlc.append((float(candle[2]), float(candle[3]), float(candle[4])))
            state.price = Decimal(candle[4])

            # Update indicators
            update_oracle(state)
            state.is_ready = True

            # Simulate position updates from mock forge
            mock_pos = forge.simulated_position
            if mock_pos["size"] > 0:
                state.trade_active = True
                state.side = mock_pos["side"]
                state.entry_price = mock_pos["avgPrice"]
                state.qty = mock_pos["size"]
                # Calculate unrealised PnL for display
                if state.side == "Buy":
                    state.upnl = (state.price - state.entry_price) * state.qty
                else:
                    state.upnl = (state.entry_price - state.price) * state.qty
            else:
                state.trade_active = False
                state.side = "HOLD"
                state.entry_price = Decimal("0.0")
                state.qty = Decimal("0.0")
                state.upnl = Decimal("0.0")

            # Check entry conditions
            if not state.trade_active and (time.time() - state.last_ritual > state.cooldown_seconds): # time.time() will be simulated
                if len(state.fisher_series) >= 2:
                    is_bull = state.price > state.macro_trend
                    buy_confirm = state.fisher_series[-1] > state.fisher_series[-2] and state.fisher_series[-2] < -state.dynamic_threshold
                    sell_confirm = state.fisher_series[-1] < state.fisher_series[-2] and state.fisher_series[-2] > state.dynamic_threshold


                    if is_bull and buy_confirm and state.trend_strength > SCALPING_TREND_STRENGTH_MIN:
                        await execute_trade(forge, "Buy")
                    elif not is_bull and sell_confirm and state.trend_strength > SCALPING_TREND_STRENGTH_MIN:
                        await execute_trade(forge, "Sell")

            # Manage existing trade (SL/TP/Pullback)
            await manage_trade(forge)

            # Update equity history and drawdown
            current_equity = forge.simulated_balance + state.upnl # Current balance + unrealised PnL
            state.equity_history.append(current_equity)
            state.peak_equity = max(state.peak_equity, current_equity)
            drawdown = (state.peak_equity - current_equity) / state.peak_equity if state.peak_equity > 0 else Decimal("0.0")
            state.max_drawdown = max(state.max_drawdown, drawdown)

            # Simulate time passing for cooldown
            state.last_ritual += 60 # Assuming 1-minute candles

        else:
            backtest_state.logs.append(f"[bold red]❌ Failed to fetch kline data during backtest: {kline_response.get('retMsg')}[/bold red]")

        # In backtesting, we process one candle at a time, so no asyncio.sleep is needed here.

# --- Backtesting Main Function ---
async def backtest_main(historical_klines: list[dict], state: BacktestingSentinelState):
    forge = MockBybitForge(historical_klines, state)

    # Initialize precision (mocked)
    res = await forge.call("GET", "/v5/market/instruments-info", {"category": CATEGORY, "symbol": SYMBOL})
    if res and res.get('retCode') == 0:
        specs = res['result']['list'][0]
        backtest_state.price_prec = abs(Decimal(specs['priceFilter']['tickSize']).normalize().as_tuple().exponent)
        backtest_state.qty_step = Decimal(specs['lotSizeFilter']['qtyStep'])
    else:
        backtest_state.logs.append(f"[bold red]❌ Failed to fetch instrument info during backtest: {res.get('retCode')}[/bold red]")
        backtest_state.logs.append("[bold yellow]Using default precision values for backtest.[/bold yellow]")

    # Run the backtest
    await backtest_logic_engine(forge)

    # --- Generate Backtest Report ---
    console = Console()
    console.print(Panel("[bold green]📊 Backtest Report 📊[/bold green]", style="green"))
    console.print(f"Initial Capital: [bold blue]{INITIAL_CAPITAL:.2f} USDT[/bold blue]")
    console.print(f"Final Equity: [bold blue]{forge.simulated_balance:.2f} USDT[/bold blue]")
    console.print(f"Total PnL: [bold green]{(forge.simulated_balance - INITIAL_CAPITAL):.2f} USDT[/bold green]")
    console.print(f"Max Drawdown: [bold red]{(backtest_state.max_drawdown * 100):.2f}%[/bold red]")
    console.print(f"Trade Count: [bold yellow]{backtest_state.trade_count}[/bold yellow]")
    console.print(f"Win Rate: [bold green]{(backtest_state.win_count / backtest_state.trade_count * 100):.2f}%[/bold green]" if backtest_state.trade_count > 0 else "Win Rate: N/A")
    console.print(f"Profit Factor: [bold green]{(backtest_state.total_profit / abs(backtest_state.total_loss)):.2f}[/bold green]" if backtest_state.total_loss != 0 else "Profit Factor: N/A")

    # You might want to plot equity curve here using matplotlib or similar

# --- Historical Data Fetching (for actual backtesting) ---
async def fetch_historical_klines(symbol: str, interval: str, start_date: str, end_date: str) -> list[dict]:
    # This part would actually fetch data from Bybit API
    # For now, let's create some dummy data
    klines = []
    start_ts = int(time.mktime(time.strptime(start_date, "%Y-%m-%d"))) * 1000
    end_ts = int(time.mktime(time.strptime(end_date, "%Y-%m-%d"))) * 1000

    current_ts = start_ts
    price = Decimal("200.0")
    while current_ts < end_ts:
        # [timestamp, open, high, low, close, volume, turnover]
        open_price = price
        close_price = price + Decimal(str(np.random.uniform(-1.0, 1.0)))
        high_price = max(open_price, close_price) + Decimal(str(np.random.uniform(0.1, 0.5)))
        low_price = min(open_price, close_price) - Decimal(str(np.random.uniform(0.1, 0.5)))
        volume = Decimal(str(np.random.uniform(100, 1000)))
        turnover = volume * close_price

        klines.append([
            str(current_ts),
            f"{open_price:.2f}",
            f"{high_price:.2f}",
            f"{low_price:.2f}",
            f"{close_price:.2f}",
            f"{volume:.2f}",
            f"{turnover:.2f}"
        ])
        price = close_price # Update price for next candle
        current_ts += 60 * 1000 # 1 minute interval

    return klines

async def optimize_parameters():
    console = Console()
    console.print(Panel("[bold magenta]🚀 Starting Parameter Optimization 🚀[/bold magenta]", style="magenta"))

    best_pnl = Decimal("-999999999.0")
    best_params = {}
    optimization_results = []

    # Fetch historical data once for all backtests
    historical_klines = await fetch_historical_klines(SYMBOL, "1", BACKTEST_START_DATE, BACKTEST_END_DATE)

    total_combinations = (
        len(COOLDOWN_RANGE) *
        len(DYNAMIC_THRESHOLD_RANGE) *
        len(TREND_STRENGTH_RANGE) *
        len(SL_MULT_RANGE) *
        len(TP_MULT_RANGE)
    )
    current_combination = 0

    for cooldown in COOLDOWN_RANGE:
        for dynamic_threshold in DYNAMIC_THRESHOLD_RANGE:
            for trend_strength in TREND_STRENGTH_RANGE:
                for sl_mult in SL_MULT_RANGE:
                    for tp_mult in TP_MULT_RANGE:
                        current_combination += 1
                        console.print(f"Running combination {current_combination}/{total_combinations}...")

                        # Reset backtest_state for each new combination
                        global backtest_state
                        backtest_state = BacktestingSentinelState()

                        # Apply current parameters to the state
                        backtest_state.cooldown_seconds = cooldown
                        backtest_state.dynamic_threshold = dynamic_threshold
                        # Note: TREND_STRENGTH_MIN and SL/TP MULT are global constants,
                        # so we need to temporarily override them or pass them differently.
                        # For simplicity in this example, we'll assume they are passed
                        # or directly used by the logic_engine.
                        # A more robust solution would involve passing these as arguments
                        # to execute_trade and manage_trade, and then to backtest_logic_engine.
                        # For now, let's assume we can temporarily modify the global constants
                        # or pass them through a config object.
                        # Given the current structure, the easiest is to pass them to backtest_main
                        # and then to backtest_logic_engine.

                        # Re-initialize backtest_state with current parameters
                        temp_state = BacktestingSentinelState()
                        temp_state.cooldown_seconds = cooldown
                        temp_state.dynamic_threshold = dynamic_threshold

                        # Temporarily override global constants for backtesting context
                        # This is not ideal but works for demonstration.
                        # A better approach would be to pass a config object down.
                        global SCALPING_COOLDOWN_SECONDS, SCALPING_DYNAMIC_THRESHOLD, SCALPING_TREND_STRENGTH_MIN, SCALPING_SL_MULT, SCALPING_TP_MULT
                        original_cooldown = SCALPING_COOLDOWN_SECONDS
                        original_dynamic_threshold = SCALPING_DYNAMIC_THRESHOLD
                        original_trend_strength = SCALPING_TREND_STRENGTH_MIN
                        original_sl_mult = SCALPING_SL_MULT
                        original_tp_mult = SCALPING_TP_MULT

                        SCALPING_COOLDOWN_SECONDS = cooldown
                        SCALPING_DYNAMIC_THRESHOLD = dynamic_threshold
                        SCALPING_TREND_STRENGTH_MIN = trend_strength
                        SCALPING_SL_MULT = sl_mult
                        SCALPING_TP_MULT = tp_mult

                        await backtest_main(historical_klines, temp_state)

                        # Restore original global constants
                        SCALPING_COOLDOWN_SECONDS = original_cooldown
                        SCALPING_DYNAMIC_THRESHOLD = original_dynamic_threshold
                        SCALPING_TREND_STRENGTH_MIN = original_trend_strength
                        SCALPING_SL_MULT = original_sl_mult
                        SCALPING_TP_MULT = original_tp_mult

                        result = {
                            "cooldown": cooldown,
                            "dynamic_threshold": dynamic_threshold,
                            "trend_strength": trend_strength,
                            "sl_mult": sl_mult,
                            "tp_mult": tp_mult,
                            "final_pnl": temp_state.balance - INITIAL_CAPITAL,
                            "max_drawdown": temp_state.max_drawdown,
                            "win_rate": (temp_state.win_count / temp_state.trade_count * 100) if temp_state.trade_count > 0 else 0,
                            "profit_factor": (temp_state.total_profit / abs(temp_state.total_loss)) if temp_state.total_loss != 0 else 0
                        }
                        optimization_results.append(result)

                        if result["final_pnl"] > best_pnl:
                            best_pnl = result["final_pnl"]
                            best_params = result

    console.print(Panel("[bold green]✅ Optimization Complete! ✅[/bold green]", style="green"))
    console.print("[bold yellow]Best Parameters Found:[/bold yellow]")
    console.print(best_params)

if __name__ == "__main__":
    asyncio.run(optimize_parameters())
