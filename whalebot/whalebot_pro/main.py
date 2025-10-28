import asyncio
import logging
import sys
from datetime import datetime
from decimal import Decimal

# Explicitly add the directory containing the 'whalebot_pro' package to sys.path
# This directory is '/data/data/com.termux/files/home/Algobots/whalebot/'
package_parent_dir = "/data/data/com.termux/files/home/Algobots/whalebot/"
if package_parent_dir not in sys.path:
    sys.path.insert(0, package_parent_dir)

# Import local modules
# Color Scheme
from colorama import Fore, Style

from whalebot_pro.analysis.indicators import IndicatorCalculator
from whalebot_pro.analysis.trading_analyzer import (
    TradingAnalyzer,
    display_indicator_values_and_price,
    fetch_latest_sentiment,
)
from whalebot_pro.api.bybit_client import BybitClient
from whalebot_pro.config import Config
from whalebot_pro.core.performance_tracker import PerformanceTracker
from whalebot_pro.core.position_manager import PositionManager
from whalebot_pro.utils.alert_system import AlertSystem
from whalebot_pro.utils.logger_setup import setup_logging
from whalebot_pro.utils.utilities import InMemoryCache, KlineDataFetcher

NEON_GREEN = Fore.LIGHTGREEN_EX
NEON_BLUE = Fore.CYAN
NEON_PURPLE = Fore.MAGENTA
NEON_YELLOW = Fore.YELLOW
NEON_RED = Fore.LIGHTRED_EX
RESET = Style.RESET_ALL


class BybitTradingBot:
    """Orchestrates the trading bot's operations."""

    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger("TradingBot")
        self.alert_system = AlertSystem(self.logger)

        self.bybit_client = BybitClient(
            api_key=self.config.BYBIT_API_KEY,
            api_secret=self.config.BYBIT_API_SECRET,
            config=self.config.get_config(),
            logger=self.logger,
        )
        self.position_manager = PositionManager(
            self.config.get_config(),
            self.logger,
            self.bybit_client,
        )
        self.performance_tracker = PerformanceTracker(
            self.logger,
            self.config.get_config(),
        )
        self.indicator_calculator = IndicatorCalculator(self.logger)
        self.analyzer = TradingAnalyzer(
            self.config.get_config(),
            self.logger,
            self.config.symbol,
            self.indicator_calculator,
        )
        self.kline_data_fetcher = KlineDataFetcher(
            self.bybit_client,
            self.logger,
            self.config.get_config(),
        )
        self.kline_cache = InMemoryCache(
            ttl_seconds=self.config.loop_delay * 0.8,
            max_size=5,
        )

        self.is_running = True

    async def start(self):
        """Starts the trading bot."""
        self.logger.info(f"{NEON_GREEN}--- Whalebot Trading Bot Initialized ---{RESET}")
        self.logger.info(
            f"Symbol: {self.config.symbol}, Interval: {self.config.interval}",
        )
        self.logger.info(
            f"Trade Management Enabled: {self.config.trade_management['enabled']}",
        )

        # --- DEBUGGING: Print loaded higher timeframes ---
        loaded_higher_timeframes = self.config.mtf_analysis.get("higher_timeframes", [])
        self.logger.debug(
            f"Loaded higher_timeframes from config: {loaded_higher_timeframes}",
        )
        # --- END DEBUGGING ---

        # Validate intervals
        valid_bybit_intervals = [
            "1",
            "3",
            "5",
            "15m",
            "30m",
            "60m",
            "120m",
            "240m",
            "360m",
            "720m",
            "D",
            "W",
            "M",
        ]
        if self.config.interval not in valid_bybit_intervals:
            self.logger.error(
                f"{NEON_RED}Invalid primary interval '{self.config.interval}'. Exiting.{RESET}",
            )
            sys.exit(1)
        for htf_interval in self.config.mtf_analysis["higher_timeframes"]:
            if htf_interval not in valid_bybit_intervals:
                self.logger.error(
                    f"{NEON_RED}Invalid higher timeframe interval '{htf_interval}'. Exiting.{RESET}",
                )
                sys.exit(1)

        await self.bybit_client.initialize()  # Load instrument info
        await self.bybit_client.start_public_ws()
        await self.bybit_client.start_private_ws()

        self.logger.info(f"{NEON_BLUE}Waiting for initial WebSocket data...{RESET}")
        await asyncio.sleep(5)  # Give WS a moment to connect and receive data

        try:
            while self.is_running:
                await self._trading_loop()
        except KeyboardInterrupt:
            self.logger.info(
                f"{NEON_YELLOW}Bot stopping due to KeyboardInterrupt.{RESET}",
            )
        except Exception as e:
            self.alert_system.send_alert(
                f"[{self.config.symbol}] An unhandled error occurred in the main loop: {e}",
                "ERROR",
            )
            self.logger.exception(
                f"{NEON_RED}[{self.config.symbol}] Unhandled exception in main loop:{RESET}",
            )
            await asyncio.sleep(self.config.loop_delay * 2)
        finally:
            await self.bybit_client.stop_ws()
            self.logger.info(
                f"{NEON_GREEN}--- Whalebot Trading Bot Shut Down ---{RESET}",
            )

    async def _trading_loop(self):
        """The main trading loop logic."""
        self.logger.info(
            f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}",
        )

        current_price = await self.bybit_client.fetch_current_price()
        if current_price is None:
            self.alert_system.send_alert(
                f"[{self.config.symbol}] Failed to fetch current price. Skipping loop.",
                "WARNING",
            )
            await asyncio.sleep(self.config.loop_delay)
            return

        kline_cache_key = self.kline_cache.generate_kline_cache_key(
            self.config.symbol,
            self.config.category,
            self.config.interval,
            1000,  # Fixed limit for fetching klines
            60,  # Fixed history window for cache key
        )
        df = self.kline_cache.get(kline_cache_key)

        if df is None or df.empty:
            df = await self.kline_data_fetcher.fetch_klines(
                self.config.symbol,
                self.config.category,
                self.config.interval,
                1000,  # Fixed limit for fetching klines
                60,  # Fixed history window for cache key
            )
            if df is None or df.empty:
                self.alert_system.send_alert(
                    f"[{self.config.symbol}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
                    "WARNING",
                )
                await asyncio.sleep(self.config.loop_delay)
                return
            self.kline_cache.set(kline_cache_key, df)

        self.analyzer.update_data(df)
        if self.analyzer.df.empty:
            self.alert_system.send_alert(
                f"[{self.config.symbol}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
                "WARNING",
            )
            await asyncio.sleep(self.config.loop_delay)
            return

        mtf_trends: dict[str, str] = {}
        if self.config.mtf_analysis["enabled"]:
            mtf_trends = await self.analyzer._fetch_and_analyze_mtf(self.bybit_client)

        sentiment_score: float | None = None
        if self.config.ml_enhancement.get("sentiment_analysis_enabled", False):
            sentiment_score = await fetch_latest_sentiment(
                self.config.symbol,
                self.logger,
            )

        if self.config.adaptive_strategy_enabled:
            market_conditions = self.analyzer.assess_market_conditions()
            suggested_strategy = self.config.current_strategy_profile

            for profile_name, profile_details in self.config.strategy_profiles.items():
                criteria = profile_details.get("market_condition_criteria")
                if not criteria:
                    continue

                adx_match = True
                if (
                    "adx_range" in criteria
                    and market_conditions["adx_value"] is not None
                    and not pd.isna(market_conditions["adx_value"])
                ):
                    adx_min, adx_max = criteria["adx_range"]
                    if not (adx_min <= market_conditions["adx_value"] <= adx_max):
                        adx_match = False

                vol_match = True
                if (
                    "volatility_range" in criteria
                    and market_conditions["volatility_index_value"] is not None
                    and not pd.isna(market_conditions["volatility_index_value"])
                ):
                    vol_min, vol_max = criteria["volatility_range"]
                    vol_min_dec = Decimal(str(vol_min))
                    vol_max_dec = Decimal(str(vol_max))
                    market_vol_dec = Decimal(
                        str(market_conditions["volatility_index_value"]),
                    )
                    if not (vol_min_dec <= market_vol_dec <= vol_max_dec):
                        vol_match = False

                if adx_match and vol_match:
                    if (
                        profile_name != suggested_strategy
                    ):  # Check against suggested, not current_strategy_profile directly
                        suggested_strategy = profile_name
                        break

            if suggested_strategy != self.config.current_strategy_profile:
                self.logger.info(
                    f"{NEON_YELLOW}[{self.config.symbol}] Market conditions suggest switching strategy from '{self.config.current_strategy_profile}' to '{suggested_strategy}'. Reloading config.{RESET}",
                )
                self.config.set_active_strategy_profile(
                    suggested_strategy,
                )  # Update config object
                self.analyzer.config = (
                    self.config.get_config()
                )  # Update analyzer's config
                self.analyzer.weights = (
                    self.config.active_weights
                )  # Update analyzer's weights

        atr_value = Decimal(
            str(self.analyzer._get_indicator_value("ATR", Decimal("0.0001"))),
        )
        if atr_value <= 0:
            atr_value = Decimal("0.0001")
            self.logger.warning(
                f"{NEON_YELLOW}[{self.config.symbol}] ATR value was zero or negative, defaulting to {atr_value}.{RESET}",
            )

        (
            trading_signal,
            signal_score,
            signal_breakdown,
        ) = await self.analyzer.generate_trading_signal(
            current_price,
            self.bybit_client.orderbook_manager,
            mtf_trends,
            sentiment_score,
        )

        await self.position_manager.manage_positions(
            current_price,
            self.performance_tracker,
            atr_value,
        )

        await display_indicator_values_and_price(
            self.config.get_config(),
            self.logger,
            current_price,
            df,
            self.bybit_client.orderbook_manager,
            mtf_trends,
            signal_breakdown,
            self.indicator_calculator,
        )

        signal_threshold = self.config.signal_score_threshold

        has_buy_position = any(
            p["side"].upper() == "BUY"
            for p in self.position_manager.get_open_positions()
        )
        has_sell_position = any(
            p["side"].upper() == "SELL"
            for p in self.position_manager.get_open_positions()
        )

        if trading_signal == "BUY" and signal_score >= signal_threshold:
            self.logger.info(
                f"{NEON_GREEN}[{self.config.symbol}] Strong BUY signal detected! Score: {signal_score:.2f}{RESET}",
            )
            if has_sell_position:
                if self.config.trade_management["close_on_opposite_signal"]:
                    self.logger.warning(
                        f"{NEON_YELLOW}[{self.config.symbol}] Detected strong BUY signal while a SELL position is open. Attempting to close SELL position.{RESET}",
                    )
                    sell_pos = next(
                        p
                        for p in self.position_manager.get_open_positions()
                        if p["side"].upper() == "SELL"
                    )
                    await self.position_manager.close_position(
                        sell_pos,
                        current_price,
                        self.performance_tracker,
                        closed_by="OPPOSITE_SIGNAL",
                    )
                    if self.config.trade_management[
                        "reverse_position_on_opposite_signal"
                    ]:
                        self.logger.info(
                            f"{NEON_GREEN}[{self.config.symbol}] Reversing position: Opening new BUY position after closing SELL.{RESET}",
                        )
                        await self.position_manager.open_position(
                            "Buy",
                            current_price,
                            atr_value,
                        )
                else:
                    self.logger.info(
                        f"{NEON_YELLOW}[{self.config.symbol}] Close on opposite signal is disabled. Holding SELL position.{RESET}",
                    )
            elif not has_buy_position:
                await self.position_manager.open_position(
                    "Buy",
                    current_price,
                    atr_value,
                )
            else:
                self.logger.info(
                    f"{NEON_YELLOW}[{self.config.symbol}] Already have a BUY position. Not opening another.{RESET}",
                )

        elif trading_signal == "SELL" and signal_score <= -signal_threshold:
            selfP.logger.info(
                f"{NEON_RED}[{self.config.symbol}] Strong SELL signal detected! Score: {signal_score:.2f}{RESET}",
            )
            if has_buy_position:
                if self.config.trade_management["close_on_opposite_signal"]:
                    self.logger.warning(
                        f"{NEON_YELLOW}[{self.config.symbol}] Detected strong SELL signal while a BUY position is open. Attempting to close BUY position.{RESET}",
                    )
                    buy_pos = next(
                        p
                        for p in self.position_manager.get_open_positions()
                        if p["side"].upper() == "BUY"
                    )
                    await self.position_manager.close_position(
                        buy_pos,
                        current_price,
                        self.performance_tracker,
                        closed_by="OPPOSITE_SIGNAL",
                    )
                    if self.config.trade_management[
                        "reverse_position_on_opposite_signal"
                    ]:
                        self.logger.info(
                            f"{NEON_RED}[{self.config.symbol}] Reversing position: Opening new SELL position after closing BUY.{RESET}",
                        )
                        await self.position_manager.open_position(
                            "Sell",
                            current_price,
                            atr_value,
                        )
                else:
                    self.logger.info(
                        f"{NEON_YELLOW}[{self.config.symbol}] Close on opposite signal is disabled. Holding BUY position.{RESET}",
                    )
            elif not has_sell_position:
                await self.position_manager.open_position(
                    "Sell",
                    current_price,
                    atr_value,
                )
            else:
                self.logger.info(
                    f"{NEON_YELLOW}[{self.config.symbol}] Already have a SELL position. Not opening another.{RESET}",
                )
        else:
            self.logger.info(
                f"{NEON_BLUE}[{self.config.symbol}] No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}",
            )

        open_positions = self.position_manager.get_open_positions()
        if open_positions:
            self.logger.info(
                f"{NEON_CYAN}[{self.config.symbol}] Open Positions: {len(open_positions)}{RESET}",
            )
            for pos in open_positions:
                self.logger.info(
                    f"  - {pos['side']} @ {pos['entry_price'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}, TSL Active: {pos['trailing_stop_activated']}){RESET}",
                )
        else:
            self.logger.info(
                f"{NEON_CYAN}[{self.config.symbol}] No open positions.{RESET}",
            )

        perf_summary = self.performance_tracker.get_summary()
        self.logger.info(
            f"{NEON_YELLOW}[{self.config.symbol}] Performance Summary: Total PnL: {perf_summary['total_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}",
        )

        self.logger.info(
            f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {self.config.loop_delay}s ---{RESET}",
        )
        await asyncio.sleep(self.config.loop_delay)


async def main():
    # Initial logger setup for config loading
    temp_logger = logging.getLogger("config_loader")
    temp_logger.setLevel(logging.INFO)
    if not temp_logger.handlers:
        temp_logger.addHandler(logging.StreamHandler(sys.stdout))

    config = Config(temp_logger)  # Pass temp_logger to Config
    logger = setup_logging(config.get_config())  # Final logger setup

    bot = BybitTradingBot(config)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
