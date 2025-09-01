import asyncio
import json
import logging
import os
from datetime import datetime
from decimal import Decimal, ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

# Import necessary components from bbwb.py
from bbwb import (
    load_config, setup_logger, BybitClient, IndicatorCalculator, TradingAnalyzer,
    NEON_GREEN, NEON_YELLOW, NEON_RED, NEON_BLUE, NEON_CYAN, NEON_PURPLE, RESET,
    PriceLevel, AdvancedOrderbookManager # Imported for mocking purposes
)

# Set Decimal precision
getcontext().prec = 28

class MockOrderbookManager:
    """A mock orderbook manager for backtesting, always returning None/empty."""
    async def get_best_bid_ask(self) -> Tuple[float | None, float | None]:
        return None, None
    async def get_depth(self, depth: int) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        return [], []

class Backtester:
    """
    Simulates trading strategy on historical data to evaluate performance.
    """
    def __init__(
        self,
        config: Dict[str, Any],
        logger: logging.Logger,
        bybit_client: BybitClient,
        indicator_calculator: IndicatorCalculator,
        trading_analyzer: TradingAnalyzer,
    ):
        self.config = config
        self.logger = logger
        self.bybit_client = bybit_client
        self.indicator_calculator = indicator_calculator
        self.trading_analyzer = trading_analyzer

        self.initial_capital = Decimal(str(config["trade_management"]["account_balance"]))
        self.capital = self.initial_capital
        self.position_size = Decimal("0")
        self.entry_price = Decimal("0")
        self.side = None  # 'buy' or 'sell'
        self.trade_history = []
        self.fees_incurred = Decimal("0")
        self.leverage = Decimal(str(config["trade_management"]["default_leverage"]))
        self.risk_per_trade_percent = Decimal(str(config["trade_management"]["risk_per_trade_percent"])) / Decimal("100")

        self.mock_orderbook_manager = MockOrderbookManager()
        self.mock_mtf_trends = {} # For simplicity, MTF trends are not simulated in this basic backtest

        self.logger.info(f"{NEON_BLUE}Backtester initialized with capital: {self.initial_capital}{RESET}")

    async def run_backtest(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str
    ) -> Dict[str, Any]:
        """
        Runs the backtest over a specified historical period.
        """
        self.logger.info(f"{NEON_BLUE}Fetching historical data for {symbol} ({interval}) from {start_date} to {end_date}...{RESET}")

        all_klines_df = pd.DataFrame()
        current_end_time = int(datetime.now().timestamp() * 1000) # Start from now
        start_timestamp_ms = int(pd.to_datetime(start_date).timestamp() * 1000)
        
        max_fetches = 100 # Limit the number of API calls to prevent excessive fetching
        fetched_count = 0

        self.logger.debug(f"Initial current_end_time: {current_end_time}, Target start_timestamp_ms: {start_timestamp_ms}")

        while fetched_count < max_fetches:
            self.logger.debug(f"Fetching attempt {fetched_count + 1}. Requesting data ending at: {current_end_time}")
            response = await self.bybit_client._bybit_request_with_retry(
                "fetch_klines_iterative",
                self.bybit_client.http_session.get_kline,
                category=self.bybit_client.category,
                symbol=symbol,
                interval=interval,
                limit=200, # Max limit per request
                end=current_end_time
            )

            if response and response["result"] and response["result"]["list"]:
                df = pd.DataFrame(
                    response["result"]["list"],
                    columns=[
                        "start_time", "open", "high", "low", "close", "volume", "turnover",
                    ],
                )
                df["start_time"] = pd.to_datetime(
                    df["start_time"].astype(int), unit="ms", utc=True
                ).dt.tz_convert(self.config["timezone"])
                for col in ["open", "high", "low", "close", "volume", "turnover"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                df.set_index("start_time", inplace=True)
                df.sort_index(inplace=True) # Ensure chronological order

                if df.empty:
                    self.logger.info(f"{NEON_YELLOW}Fetched empty DataFrame. Stopping iterative fetch.{RESET}")
                    break

                all_klines_df = pd.concat([df, all_klines_df]).drop_duplicates().sort_index()
                
                # Update current_end_time to the start_time of the oldest bar fetched
                current_end_time = int(df.index.min().timestamp() * 1000) - 1 # Subtract 1ms to avoid fetching the same bar
                
                self.logger.debug(f"Fetched {len(df)} klines. Total: {len(all_klines_df)}. Oldest bar fetched: {df.index.min()}")

                if current_end_time <= start_timestamp_ms:
                    self.logger.info(f"{NEON_GREEN}Reached desired start date. Stopping iterative fetch.{RESET}")
                    break
            else:
                self.logger.warning(f"{NEON_YELLOW}No more historical data or error fetching. Stopping iterative fetch.{RESET}")
                break
            
            fetched_count += 1
            await asyncio.sleep(0.1) # Small delay to avoid hitting rate limits

        self.logger.debug(f"Finished fetching loop. Total klines fetched: {len(all_klines_df)}")
        if all_klines_df.empty:
            self.logger.error(f"{NEON_RED}No historical data fetched for the specified range. Exiting backtest.{RESET}")
            return self._generate_report([], self.initial_capital, self.capital)

        # Filter data by date range
        klines_df = all_klines_df[(all_klines_df.index >= start_date) & (all_klines_df.index <= end_date)]
        
        if klines_df.empty:
            self.logger.warning(f"{NEON_YELLOW}No data within the specified date range after fetching. Exiting backtest.{RESET}")
            return self._generate_report([], self.initial_capital, self.capital)
        
        self.logger.info(f"{NEON_GREEN}Starting backtest with {len(klines_df)} historical bars.{RESET}")
        
        # Ensure klines_df is sorted by index (timestamp)
        klines_df.sort_index(inplace=True)

        for i, (timestamp, bar) in enumerate(klines_df.iterrows()):
            current_price = Decimal(str(bar["close"]))
            
            # Update TradingAnalyzer with current bar and recalculate indicators
            # Pass a slice of the DataFrame up to the current bar
            current_df_slice = klines_df.iloc[:i+1].copy()
            self.trading_analyzer.update_data(current_df_slice)

            # Generate signal
            signal, score = await self.trading_analyzer.generate_trading_signal(
                current_price, self.mock_orderbook_manager, self.mock_mtf_trends
            )
            self.logger.debug(f"Signal: {signal}, Score: {score}")
            self.logger.debug(f"Bar {timestamp}: Price={current_price}, Signal={signal}, Score={score}, Capital={self.capital:.2f}, Position={self.position_size:.4f}")

            # Simulate trade execution
            if self.side is None:  # No open position
                if signal == "BUY":
                    await self._execute_trade(bar, "buy", current_price)
                elif signal == "SELL":
                    await self._execute_trade(bar, "sell", current_price)
            else:  # Position open
                # Check for exit signals or SL/TP
                if (self.side == 'buy' and signal == 'SELL') or \
                   (self.side == 'sell' and signal == 'BUY'):
                    self.logger.info(f"{NEON_YELLOW}Closing {self.side.upper()} position due to reversal signal at {current_price}{RESET}")
                    await self._close_position(bar, current_price, self.entry_price, self.side)
                else:
                    # Apply SL/TP logic (simplified: check against current bar's high/low)
                    await self._apply_sl_tp(bar, current_price)

        self.logger.info(f"{NEON_BLUE}Backtest finished. Final Capital: {self.capital:.2f}{RESET}")
        return self._generate_report(self.trade_history, self.initial_capital, self.capital)

    async def _execute_trade(self, bar: pd.Series, signal_side: str, current_price: Decimal):
        """Simulates placing a trade."""
        self.logger.debug(f"Attempting to execute {signal_side} trade. Capital: {self.capital:.2f}")
        if self.position_size > 0: # Already in a position
            self.logger.debug("Skipping trade: Already in a position.")
            return

        # Calculate position size based on risk per trade and leverage
        # Simplified: risk_amount = capital * risk_per_trade_percent
        # max_loss_per_unit = entry_price - stop_loss_price (for long)
        # quantity = risk_amount / max_loss_per_unit
        # For simplicity, let's use a fixed percentage of capital for now, adjusted by leverage
        trade_amount_usd = self.capital * Decimal("0.01") * self.leverage # 1% of capital, leveraged

        # Ensure trade_amount_usd is not zero or negative
        if trade_amount_usd <= 0:
            self.logger.warning(f"{NEON_YELLOW}Calculated trade amount ({trade_amount_usd:.2f}) is zero or negative. Skipping trade.{RESET}")
            return

        # Calculate quantity based on current price
        quantity = (trade_amount_usd / current_price).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
        self.logger.debug(f"Calculated trade_amount_usd: {trade_amount_usd:.2f}, quantity: {quantity:.8f}")

        # Ensure quantity meets minimum requirements (mocking precision manager)
        if quantity < Decimal("0.00001"): # Example min quantity
            self.logger.warning(f"{NEON_YELLOW}Calculated quantity ({quantity:.8f}) is too small. Skipping trade.{RESET}")
            return

        fee_rate = Decimal("0.0005") # Example: 0.05% taker fee
        trade_fee = (quantity * current_price * fee_rate).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        if self.capital < trade_fee:
            self.logger.warning(f"{NEON_YELLOW}Insufficient capital ({self.capital:.2f}) for trade fees ({trade_fee:.8f}). Skipping trade.{RESET}")
            return

        self.capital -= trade_fee
        self.fees_incurred += trade_fee

        self.position_size = quantity
        self.entry_price = current_price
        self.side = signal_side

        self.logger.info(
            f"{NEON_GREEN}Simulated {self.side.upper()} entry at {self.entry_price} with {self.position_size:.4f} units. Capital: {self.capital:.2f}{RESET}"
        )

        # Record the trade
        self.trade_history.append({
            "timestamp": bar.name,
            "type": "entry",
            "side": self.side,
            "price": float(self.entry_price),
            "quantity": float(self.position_size),
            "fee": float(trade_fee),
            "pnl": 0.0,
            "cumulative_pnl": float(self.capital - self.initial_capital)
        })

    async def _close_position(self, bar: pd.Series, exit_price: Decimal, entry_price: Decimal, side: str):
        """Simulates closing an open position."""
        if self.position_size == 0:
            return

        pnl = Decimal("0")
        if side == 'buy':
            pnl = (exit_price - entry_price) * self.position_size
        elif side == 'sell':
            pnl = (entry_price - exit_price) * self.position_size

        fee_rate = Decimal("0.0005") # Example: 0.05% taker fee
        close_fee = (self.position_size * exit_price * fee_rate).quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)

        self.capital += pnl - close_fee
        self.fees_incurred += close_fee

        trade_result = "WIN" if pnl > 0 else "LOSS" if pnl < 0 else "BREAKEVEN"
        self.logger.info(
            f"{NEON_YELLOW}Simulated {side.upper()} exit at {exit_price}. PnL: {pnl:.2f} ({trade_result}). Capital: {self.capital:.2f}{RESET}"
        )

        self.trade_history.append({
            "timestamp": bar.name,
            "type": "exit",
            "side": side,
            "price": float(exit_price),
            "quantity": float(self.position_size),
            "fee": float(close_fee),
            "pnl": float(pnl),
            "cumulative_pnl": float(self.capital - self.initial_capital)
        })

        self.position_size = Decimal("0")
        self.entry_price = Decimal("0")
        self.side = None

    async def _apply_sl_tp(self, bar: pd.Series, current_price: Decimal):
        """Applies stop-loss and take-profit logic."""
        if self.position_size == 0:
            return

        # For simplicity, SL/TP are checked against the current bar's close price.
        # A more robust backtester would check against high/low of the bar.
        stop_loss_atr_multiple = Decimal(str(self.config["trade_management"]["stop_loss_atr_multiple"]))
        take_profit_atr_multiple = Decimal(str(self.config["trade_management"]["take_profit_atr_multiple"]))

        atr_value = Decimal(str(self.trading_analyzer.indicator_values.get("ATR", "0")))
        if atr_value == 0:
            self.logger.warning(f"{NEON_YELLOW}ATR is zero, cannot apply SL/TP based on ATR.{RESET}")
            return

        sl_price = Decimal("0")
        tp_price = Decimal("0")

        if self.side == 'buy':
            sl_price = self.entry_price - (atr_value * stop_loss_atr_multiple)
            tp_price = self.entry_price + (atr_value * take_profit_atr_multiple)
            
            if current_price <= sl_price:
                self.logger.info(f"{NEON_RED}Simulated BUY position hit Stop Loss at {current_price} (SL: {sl_price:.2f}){RESET}")
                await self._close_position(bar, sl_price, self.entry_price, self.side)
            elif current_price >= tp_price:
                self.logger.info(f"{NEON_GREEN}Simulated BUY position hit Take Profit at {current_price} (TP: {tp_price:.2f}){RESET}")
                await self._close_position(bar, tp_price, self.entry_price, self.side)
        elif self.side == 'sell':
            sl_price = self.entry_price + (atr_value * stop_loss_atr_multiple)
            tp_price = self.entry_price - (atr_value * take_profit_atr_multiple)

            if current_price >= sl_price:
                self.logger.info(f"{NEON_RED}Simulated SELL position hit Stop Loss at {current_price} (SL: {sl_price:.2f}){RESET}")
                await self._close_position(bar, sl_price, self.entry_price, self.side)
            elif current_price <= tp_price:
                self.logger.info(f"{NEON_GREEN}Simulated SELL position hit Take Profit at {current_price} (TP: {tp_price:.2f}){RESET}")
                await self._close_position(bar, tp_price, self.entry_price, self.side)

    def _generate_report(self, trade_history: List[Dict[str, Any]], initial_capital: Decimal, final_capital: Decimal) -> Dict[str, Any]:
        """Generates and prints a backtest report."""
        total_pnl = final_capital - initial_capital
        num_trades = len([t for t in trade_history if t["type"] == "exit"])
        winning_trades = [t for t in trade_history if t["type"] == "exit" and t["pnl"] > 0]
        losing_trades = [t for t in trade_history if t["type"] == "exit" and t["pnl"] < 0]

        win_rate = (len(winning_trades) / num_trades * 100) if num_trades > 0 else 0

        self.logger.info(f"\n{NEON_BLUE}--- Backtest Report ---{RESET}")
        self.logger.info(f"{NEON_CYAN}Initial Capital: {initial_capital:.2f}{RESET}")
        self.logger.info(f"{NEON_CYAN}Final Capital: {final_capital:.2f}{RESET}")
        self.logger.info(f"{NEON_CYAN}Total PnL: {total_pnl:.2f}{RESET}")
        self.logger.info(f"{NEON_CYAN}Total Fees Incurred: {self.fees_incurred:.2f}{RESET}")
        self.logger.info(f"{NEON_CYAN}Number of Trades: {num_trades}{RESET}")
        self.logger.info(f"{NEON_CYAN}Winning Trades: {len(winning_trades)}{RESET}")
        self.logger.info(f"{NEON_CYAN}Losing Trades: {len(losing_trades)}{RESET}")
        self.logger.info(f"{NEON_CYAN}Win Rate: {win_rate:.2f}%{RESET}")
        self.logger.info(f"{NEON_BLUE}-----------------------{RESET}")

        return {
            "initial_capital": float(initial_capital),
            "final_capital": float(final_capital),
            "total_pnl": float(total_pnl),
            "total_fees": float(self.fees_incurred),
            "num_trades": num_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "trade_history": trade_history,
        }

async def main():
    logger = setup_logger("Backtester", level=logging.DEBUG)
    config = load_config(Path("config.json"), logger)

    # Override config for backtesting if needed
    config["testnet"] = False # Use real data, so set to False
    if "gemini_ai_analysis" in config and isinstance(config["gemini_ai_analysis"], dict):
        config["gemini_ai_analysis"]["enabled"] = False # Disable Gemini AI for backtesting speed
    else:
        # If gemini_ai_analysis block is missing or malformed, create a default one
        config["gemini_ai_analysis"] = {"enabled": False, "model_name": "gemini-pro", "temperature": 0.7, "top_p": 0.9, "weight": 0.3}

    bybit_client = BybitClient(
        api_key=os.getenv("BYBIT_API_KEY"),
        api_secret=os.getenv("BYBIT_API_SECRET"),
        config=config,
        logger=logger
    )
    indicator_calculator = IndicatorCalculator(logger)
    trading_analyzer = TradingAnalyzer(config, logger, config["symbol"], indicator_calculator)

    backtester = Backtester(config, logger, bybit_client, indicator_calculator, trading_analyzer)

    # Define backtest period
    symbol = config["symbol"]
    interval = config["interval"]
    # Adjust these dates for your desired backtest period
    start_date = "2024-01-01 00:00:00"
    end_date = "2024-01-31 23:59:59"

    report = await backtester.run_backtest(symbol, interval, start_date, end_date)

if __name__ == "__main__":
    asyncio.run(main())
