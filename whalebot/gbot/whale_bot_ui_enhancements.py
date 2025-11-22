
# Assuming WhaleBot class and necessary imports (rich, Decimal, settings, IS_TERMUX) are defined elsewhere.
# This snippet focuses on the _render_ui method modifications.

from decimal import Decimal
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich import box

# Placeholder for settings and IS_TERMUX, replace with actual imports/definitions
class Settings:
    class Trader:
        initial_balance = Decimal("10000.00")
settings = Settings()
IS_TERMUX = False # Set to True if running in Termux

# Mock classes and data for demonstration purposes
class Analysis:
    def __init__(self, action: str, confidence: float):
        self.action = action
        self.confidence = confidence

class Indicators:
    def __init__(self, rsi: float, trend: str, macd_hist: float, ob_imbalance: float):
        self.rsi = rsi
        self.trend = trend
        self.macd_hist = macd_hist
        self.ob_imbalance = ob_imbalance

class Snapshot:
    def __init__(self, symbol: str, price: float, analysis: Analysis | None = None, indicators: Indicators | None = None, error: str | None = None):
        self.symbol = symbol
        self.price = price
        self.analysis = analysis
        self.indicators = indicators
        self.error = error

class Trader:
    def __init__(self):
        self.positions = {}
        self.history = []
        self.balance = Decimal("10500.50")

class WhaleBot:
    def __init__(self):
        self.snapshots = {}
        self.trader = Trader()
        self.recent_trades_count = 5 # New attribute

        # Sample data for demonstration
        self.snapshots = {
            "BTCUSDT": Snapshot("BTCUSDT", 40000.50, Analysis("BUY", 0.85), Indicators(75, "BULL", 0.15, 0.05)),
            "ETHUSDT": Snapshot("ETHUSDT", 2200.75, Analysis("HOLD", 0.50), Indicators(45, "BEAR", -0.05, -0.02)),
            "SOLUSDT": Snapshot("SOLUSDT", 100.20, Analysis("SELL", 0.90), Indicators(25, "NEUTRAL", 0.02, 0.15), error="API Error"),
            "ADAUSDT": Snapshot("ADAUSDT", 0.60, Analysis("BUY", 0.70), Indicators(60, "BULL", 0.01, 0.01)),
        }
        self.trader.positions = {
            "BTCUSDT": {"side": "BUY", "entry_price": 39000.00, "qty": Decimal("0.001")},
            "ETHUSDT": {"side": "BUY", "entry_price": 2100.00, "qty": Decimal("0.05")},
        }
        self.trader.history = [
            {"time": "2023-10-27 10:00:00", "symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", "entry_price": "39000.00", "exit_price": "40000.50", "pnl": "105.50", "reason": "TP hit"},
            {"time": "2023-10-27 09:30:00", "symbol": "ETHUSDT", "side": "BUY", "qty": "0.05", "entry_price": "2100.00", "exit_price": "2150.00", "pnl": "25.00", "reason": "RSI Oversold"},
            {"time": "2023-10-27 08:00:00", "symbol": "SOLUSDT", "side": "SELL", "qty": "1.0", "entry_price": "105.00", "exit_price": "100.20", "pnl": "-4.80", "reason": "SL hit"},
            {"time": "2023-10-26 15:00:00", "symbol": "ADAUSDT", "side": "BUY", "qty": "10.0", "entry_price": "0.58", "exit_price": "0.60", "pnl": "0.20", "reason": "AI Signal"},
            {"time": "2023-10-26 14:00:00", "symbol": "BTCUSDT", "side": "BUY", "qty": "0.001", "entry_price": "38000.00", "exit_price": "38500.00", "pnl": "50.00", "reason": "TP hit"},
            {"time": "2023-10-26 13:00:00", "symbol": "ETHUSDT", "side": "BUY", "qty": "0.05", "entry_price": "2000.00", "exit_price": "1980.00", "pnl": "-1.00", "reason": "SL hit"},
        ]


    def _render_ui(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="history", size=5) # New layout for history
        )

        # --- Header ---
        total_unrealized_pnl = Decimal(0)
        for sym, pos in self.trader.positions.items():
            snap = self.snapshots.get(sym)
            if snap and snap.price > 0:
                pnl = (snap.price - pos['entry_price']) * pos['qty']
                if pos['side'] == "SELL":
                    pnl = -pnl
                total_unrealized_pnl += pnl

        total_equity = self.trader.balance + total_unrealized_pnl
        equity_color = "green" if total_equity >= settings.trader.initial_balance else "red"
        pnl_color = "green" if total_unrealized_pnl >= 0 else "red"

        header_text = (
            f"[bold]WhaleBot v8.2[/] | "
            f"Balance: [cyan]${self.trader.balance:.2f}[/] | "
            f"Unrealized PnL: [{pnl_color}]${total_unrealized_pnl:.2f}[/] | "
            f"Equity: [{equity_color}]${total_equity:.2f}[/]"
        )
        layout["header"].update(Panel(header_text, style="on blue", box=box.SIMPLE))

        # --- Body Table ---
        # Modified to include an 'Error' column
        table = Table(expand=True, box=box.SIMPLE, padding=(0, 1), show_header=True)
        table.add_column("Sym", style="bold", width=8)
        table.add_column("Price", justify="right")
        table.add_column("Act", justify="center", width=12)
        if not IS_TERMUX:
            table.add_column("Ind", justify="center")
        table.add_column("Error", justify="left") # New column for errors

        # Sort snapshots by AI confidence (descending) for better visibility
        sorted_snapshots = sorted(
            [snap for snap in self.snapshots.values() if snap.price > 0],
            key=lambda s: s.analysis.confidence if s.analysis else 0,
            reverse=True
        )

        for s in sorted_snapshots:
            pos = self.trader.positions.get(s.symbol)
            price_str = f"{s.price:.3f}"
            action_str = "[dim]-[/]"
            indicator_str = ""
            error_str = "" # Initialize error string

            # --- Error Handling ---
            if s.error:
                error_str = f"[bold red]! {s.error}[/]"
                # You might want to skip adding rows with critical errors or handle them differently

            # Position display
            if pos:
                current_pnl = Decimal(0)
                if s.price > 0:
                    pnl_calc = (s.price - pos['entry_price']) * pos['qty']
                    if pos['side'] == "SELL":
                        pnl_calc = -pnl_calc
                    current_pnl = pnl_calc

                pnl_color = "green" if current_pnl >= 0 else "red"
                # Enhanced action string to include PnL
                action_str = f"[{pnl_color}]{pos['side']}[/]
[{pnl_color}]{current_pnl:+.2f}[/]"
                price_str += f"
[{pnl_color}]{current_pnl:+.2f}[/]" # Show PnL next to price

            # AI Signal display
            elif s.analysis and s.analysis.action != "HOLD":
                ai_color = "green" if s.analysis.action == "BUY" else "red"
                action_str = f"[{ai_color}]{s.analysis.action}[/]
[{ai_color}]{s.analysis.confidence*100:.0f}%[/]"

            # Indicator summary (for non-Termux UI)
            if not IS_TERMUX:
                rsi_color = "red" if s.indicators.rsi > 70 else "green" if s.indicators.rsi < 30 else "dim"
                trend_color = "green" if s.indicators.trend == "BULL" else "red" if s.indicators.trend == "BEAR" else "dim"
                macd_color = "green" if s.indicators.macd_hist > 0 else "red" if s.indicators.macd_hist < 0 else "dim"
                ob_imbalance_color = "green" if s.indicators.ob_imbalance > 0.1 else "red" if s.indicators.ob_imbalance < -0.1 else "dim"

                indicator_str = (
                    f"RSI:[{rsi_color}]{s.indicators.rsi:.0f}[/] "
                    f"T:[{trend_color}]{s.indicators.trend[0]}[/] "
                    f"MACD:[{macd_color}]{s.indicators.macd_hist:+.2f}[/] "
                    f"OB:[{ob_imbalance_color}]{s.indicators.ob_imbalance:.2f}[/]"
                )

            row = [s.symbol, price_str, action_str]
            if not IS_TERMUX:
                row.append(indicator_str)
            row.append(error_str) # Append error message
            table.add_row(*row)

        layout["body"].update(table)

        # --- History Table ---
        history_table = Table(expand=True, box=box.SIMPLE, padding=(0, 1), show_header=True)
        history_table.add_column("Time", style="dim", width=20)
        history_table.add_column("Symbol", style="bold")
        history_table.add_column("Side", justify="center")
        history_table.add_column("Qty", justify="right")
        history_table.add_column("Entry", justify="right")
        history_table.add_column("Exit", justify="right")
        history_table.add_column("PnL", justify="right")
        history_table.add_column("Reason", justify="center")

        # Display only the most recent trades
        recent_trades = self.trader.history[:self.recent_trades_count]
        for trade in recent_trades:
            pnl = Decimal(trade.get("pnl", "0"))
            pnl_color = "green" if pnl >= 0 else "red"
            history_table.add_row(
                trade.get("time", "N/A"),
                trade.get("symbol", "N/A"),
                f"[{pnl_color}]{trade.get('side', 'N/A')}[/]",
                f"{Decimal(trade.get('qty', '0')):.5f}",
                f"{Decimal(trade.get('entry_price', '0')):.4f}",
                f"{Decimal(trade.get('exit_price', '0')):.4f}",
                f"[{pnl_color}]{pnl:+.4f}[/]",
                trade.get("reason", "N/A")
            )
        layout["history"].update(Panel(history_table, title="[bold blue]Recent Trades[/]", box=box.ROUNDED))

        return layout

# --- Example Usage ---
if __name__ == "__main__":
    bot = WhaleBot()
    ui_layout = bot._render_ui()

    # To display the UI, you would typically use rich.live.Live
    # For this example, we'll just print a representation of the layout structure
    # In a real application, you'd use:
    # from rich.live import Live
    # with Live(ui_layout, refresh_per_second=4) as live:
    #     while True:
    #         # Update bot.snapshots, bot.trader.history etc.
    #         # live.update(bot._render_ui())
    #         pass # Replace with actual bot logic

    print("--- UI Layout Structure ---")
    print(ui_layout)
    print("\n--- Main Table Content (Simulated) ---")
    # This part is tricky to simulate perfectly without Rich's Live display
    # The _render_ui method returns a Layout object which Rich renders.
    # We can print the table content as a string representation.
    print(ui_layout["body"].renderable)
    print("\n--- History Table Content (Simulated) ---")
    print(ui_layout["history"].renderable)