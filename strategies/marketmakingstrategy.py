from typing import List, Dict, Any, Tuple
from decimal import Decimal
import pandas as pd
from algobots_types import OrderBlock  # Assuming this is available
from .strategy_template import StrategyTemplate
from colorama import init, Fore, Style

init()  # Initialize Colorama for vibrant terminal output

class MarketMakingStrategy(StrategyTemplate):
    """
    An enhanced, adaptive market making strategy with ATR-based dynamic spreads,
    inventory-aware skewing, S/R and Order Block avoidance, dynamic stop-loss,
    and improved hedging and logging for Termux compatibility.
    """
    def __init__(self, logger,
                 spread_bps: int = 20,  # Base spread in BPS
                 # --- Size & Position ---
                 use_volatility_adjusted_size: bool = True,
                 base_order_quantity: Decimal = Decimal('0.01'),
                 volatility_sensitivity: Decimal = Decimal('0.5'),
                 max_position_size: Decimal = Decimal('0.05'),
                 # --- Skew & Spread ---
                 use_dynamic_spread: bool = True,
                 atr_spread_multiplier: Decimal = Decimal('0.5'),
                 inventory_skew_intensity: Decimal = Decimal('5.0'),
                 # --- Trend & S/R ---
                 use_trend_filter: bool = True,
                 sr_level_avoidance_bps: int = 2,
                 use_order_block_logic: bool = True,
                 ob_avoidance_bps: int = 1,
                 # --- Risk Management ---
                 rebalance_threshold: Decimal = Decimal('0.03'),
                 rebalance_aggressiveness: str = 'MARKET',
                 use_dynamic_stop_loss: bool = True,
                 stop_loss_atr_multiplier: Decimal = Decimal('2.5'),
                 # --- New Parameters ---
                 hedge_ratio: Decimal = Decimal('0.2'),  # Hedge 20% of position
                 max_spread_bps: int = 50,  # Cap for dynamic spread
                 min_order_quantity: Decimal = Decimal('0.005')  # Minimum order size
                ):
        super().__init__(logger)
        # Assign parameters with type conversion
        self.spread_bps = Decimal(str(spread_bps))
        self.use_volatility_adjusted_size = use_volatility_adjusted_size
        self.base_order_quantity = base_order_quantity
        self.volatility_sensitivity = volatility_sensitivity
        self.max_position_size = max_position_size
        self.use_dynamic_spread = use_dynamic_spread
        self.atr_spread_multiplier = atr_spread_multiplier
        self.inventory_skew_intensity = inventory_skew_intensity
        self.use_trend_filter = use_trend_filter
        self.sr_level_avoidance_bps = Decimal(str(sr_level_avoidance_bps)) / Decimal('10000')
        self.use_order_block_logic = use_order_block_logic
        self.ob_avoidance_bps = Decimal(str(ob_avoidance_bps)) / Decimal('10000')
        self.rebalance_threshold = rebalance_threshold
        self.rebalance_aggressiveness = rebalance_aggressiveness
        self.use_dynamic_stop_loss = use_dynamic_stop_loss
        self.stop_loss_atr_multiplier = stop_loss_atr_multiplier
        self.hedge_ratio = hedge_ratio
        self.max_spread_bps = Decimal(str(max_spread_bps))
        self.min_order_quantity = min_order_quantity

        # Validation
        if self.rebalance_threshold > self.max_position_size:
            self.logger.warning(Fore.YELLOW + f"Rebalance threshold exceeds max position size. Adjusting to {self.max_position_size}." + Style.RESET_ALL)
            self.rebalance_threshold = self.max_position_size
        if self.rebalance_aggressiveness not in ['MARKET', 'AGGRESSIVE_LIMIT']:
            self.logger.warning(Fore.YELLOW + f"Invalid rebalance_aggressiveness. Defaulting to 'MARKET'." + Style.RESET_ALL)
            self.rebalance_aggressiveness = 'MARKET'
        if self.min_order_quantity >= self.base_order_quantity:
            self.logger.warning(Fore.YELLOW + f"Min order quantity >= base order quantity. Setting min to {self.base_order_quantity / 2}." + Style.RESET_ALL)
            self.min_order_quantity = self.base_order_quantity / 2

        self.logger.info(Fore.CYAN + "Summoning Enhanced MarketMakingStrategy..." + Style.RESET_ALL)

    def _calculate_volatility_adjusted_size(self, latest_atr: Decimal, current_price: Decimal) -> Decimal:
        """Calculate order size adjusted for volatility, with a minimum size cap."""
        if not self.use_volatility_adjusted_size or latest_atr <= 0 or current_price <= 0:
            self.logger.debug(Fore.YELLOW + f"Using base order quantity: {self.base_order_quantity}" + Style.RESET_ALL)
            return self.base_order_quantity

        # Normalize ATR as a percentage of price
        normalized_atr = latest_atr / current_price
        # Dampen volatility effect with smoother scaling
        size_multiplier = Decimal('1') / (Decimal('1') + normalized_atr * self.volatility_sensitivity)
        adjusted_size = max(self.min_order_quantity, self.base_order_quantity * size_multiplier)
        self.logger.debug(Fore.GREEN + f"Volatility-Adjusted Size: {adjusted_size:.4f} (Base: {self.base_order_quantity}, Multiplier: {size_multiplier:.4f})" + Style.RESET_ALL)
        return adjusted_size

    def _calculate_hedge_size(self, current_position_size: Decimal) -> Decimal:
        """Calculate hedge order size based on position size."""
        hedge_size = current_position_size * self.hedge_ratio
        self.logger.debug(Fore.CYAN + f"Hedging {hedge_size:.4f} of position {current_position_size}." + Style.RESET_ALL)
        return min(hedge_size, self.max_position_size)

    def generate_signals(self,
                         df: pd.DataFrame,
                         resistance_levels: List[Dict[str, Any]],
                         support_levels: List[Dict[str, Any]],
                         active_bull_obs: List[OrderBlock],
                         active_bear_obs: List[OrderBlock],
                         **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """Generate market making signals with dynamic spreads and hedging."""
        signals = []
        required_cols = ['close', 'atr', 'ehlers_supersmoother']
        if df.empty or not all(col in df.columns for col in required_cols):
            self.logger.warning(Fore.RED + f"DataFrame missing required columns: {required_cols}." + Style.RESET_ALL)
            return []

        # --- Extract Data ---
        latest_candle = df.iloc[-1]
        current_price = Decimal(str(latest_candle['close']))
        latest_atr = Decimal(str(latest_candle['atr']))
        timestamp = df.index[-1]
        current_position_side = kwargs.get('current_position_side', 'NONE')
        current_position_size = Decimal(str(kwargs.get('current_position_size', '0')))
        signed_inventory = current_position_size if current_position_side == 'BUY' else -current_position_size

        # --- Calculate Dynamic Order Size ---
        order_quantity = self._calculate_volatility_adjusted_size(latest_atr, current_price)

        # --- Dynamic Spread with Cap ---
        dynamic_spread_bps = self.spread_bps
        if self.use_dynamic_spread and current_price > 0:
            atr_spread_adj = (latest_atr / current_price) * self.atr_spread_multiplier * Decimal('10000')
            dynamic_spread_bps = min(self.max_spread_bps, dynamic_spread_bps + atr_spread_adj)
            self.logger.debug(Fore.BLUE + f"Dynamic spread adjusted to {dynamic_spread_bps:.2f} bps." + Style.RESET_ALL)

        # --- Trend Filter & Skew ---
        skewed_mid_price = current_price
        if self.use_trend_filter:
            trend_ma = Decimal(str(latest_candle['ehlers_supersmoother']))
            trend_direction = "Uptrend" if current_price > trend_ma else "Downtrend" if current_price < trend_ma else "Neutral"
            skew_factor = self.inventory_skew_intensity / Decimal('10000')
            skewed_mid_price *= (Decimal('1') + skew_factor if current_price > trend_ma else
                                Decimal('1') - skew_factor if current_price < trend_ma else Decimal('1'))
            self.logger.debug(Fore.MAGENTA + f"Trend: {trend_direction}, Skewed Mid Price: {skewed_mid_price:.8f}" + Style.RESET_ALL)

        # --- Inventory Skew ---
        if self.max_position_size > 0:
            inventory_ratio = signed_inventory / self.max_position_size
            inventory_skew = (current_price * self.inventory_skew_intensity / Decimal('100')) * inventory_ratio
            skewed_mid_price -= inventory_skew
            self.logger.debug(Fore.YELLOW + f"Inventory Skew: {inventory_skew:.8f}, Adjusted Mid Price: {skewed_mid_price:.8f}" + Style.RESET_ALL)

        # --- Calculate Bid/Ask ---
        spread_factor = dynamic_spread_bps / Decimal('20000')
        bid_price = skewed_mid_price * (Decimal('1') - spread_factor)
        ask_price = skewed_mid_price * (Decimal('1') + spread_factor)

        # --- S/R and Order Block Avoidance ---
        all_support = [Decimal(str(lvl['price'])) for lvl in support_levels] + \
                      [Decimal(str(ob['top'])) for ob in active_bull_obs if self.use_order_block_logic]
        all_resistance = [Decimal(str(lvl['price'])) for lvl in resistance_levels] + \
                         [Decimal(str(ob['bottom'])) for ob in active_bear_obs if self.use_order_block_logic]

        for s_lvl in all_support:
            if s_lvl < bid_price < s_lvl * (Decimal('1') + self.sr_level_avoidance_bps):
                bid_price = s_lvl * (Decimal('1') - self.ob_avoidance_bps)
                self.logger.debug(Fore.CYAN + f"Adjusted bid to {bid_price:.8f} to avoid support at {s_lvl:.8f}" + Style.RESET_ALL)

        for r_lvl in all_resistance:
            if r_lvl > ask_price > r_lvl * (Decimal('1') - self.sr_level_avoidance_bps):
                ask_price = r_lvl * (Decimal('1') + self.ob_avoidance_bps)
                self.logger.debug(Fore.CYAN + f"Adjusted ask to {ask_price:.8f} to avoid resistance at {r_lvl:.8f}" + Style.RESET_ALL)

        # --- Hedging Logic ---
        if abs(signed_inventory) > self.rebalance_threshold:
            hedge_size = self._calculate_hedge_size(abs(signed_inventory))
            hedge_side = 'SELL' if signed_inventory > 0 else 'BUY'
            hedge_price = bid_price if hedge_side == 'BUY' else ask_price
            signals.append((f'{hedge_side}_LIMIT', hedge_price, timestamp,
                           {'order_type': 'LIMIT', 'quantity': hedge_size, 'strategy_id': 'MM_HEDGE'}))

        # --- Final Signal Generation ---
        if not (current_position_side == 'BUY' and (current_position_size + order_quantity > self.max_position_size)):
            signals.append(('BUY_LIMIT', bid_price, timestamp,
                           {'order_type': 'LIMIT', 'quantity': order_quantity, 'strategy_id': 'MM_BID'}))
        if not (current_position_side == 'SELL' and (current_position_size + order_quantity > self.max_position_size)):
            signals.append(('SELL_LIMIT', ask_price, timestamp,
                           {'order_type': 'LIMIT', 'quantity': order_quantity, 'strategy_id': 'MM_ASK'}))

        self.logger.info(Fore.GREEN + f"Generated {len(signals)} signals: {signals}" + Style.RESET_ALL)
        return signals

    def generate_exit_signals(self,
                              df: pd.DataFrame,
                              current_position_side: str,
                              active_bull_obs: List[OrderBlock],
                              active_bear_obs: List[OrderBlock],
                              **kwargs) -> List[Tuple[str, Decimal, Any, Dict[str, Any]]]:
        """Generate exit signals with dynamic stop-loss and rebalancing."""
        exit_signals = []
        if df.empty or current_position_side == 'NONE':
            self.logger.warning(Fore.RED + f"No position or empty DataFrame. Skipping exit signals." + Style.RESET_ALL)
            return []

        latest_candle = df.iloc[-1]
        current_price = Decimal(str(latest_candle['close']))
        latest_atr = Decimal(str(latest_candle['atr']))
        timestamp = df.index[-1]
        current_position_size = Decimal(str(kwargs.get('current_position_size', '0')))
        entry_price = Decimal(str(kwargs.get('entry_price', '0')))

        # --- Dynamic Stop-Loss ---
        if self.use_dynamic_stop_loss and entry_price > 0:
            stop_loss_trigger_price = (entry_price - (latest_atr * self.stop_loss_atr_multiplier)
                                     if current_position_side == 'BUY' else
                                     entry_price + (latest_atr * self.stop_loss_atr_multiplier))
            if (current_position_side == 'BUY' and current_price <= stop_loss_trigger_price) or \
               (current_position_side == 'SELL' and current_price >= stop_loss_trigger_price):
                self.logger.warning(Fore.RED + f"PANIC EXIT: Stop-Loss triggered at {current_price:.8f} (Entry: {entry_price:.8f}, SL: {stop_loss_trigger_price:.8f})" + Style.RESET_ALL)
                exit_side = 'SELL' if current_position_side == 'BUY' else 'BUY'
                exit_signals.append((f'{exit_side}_MARKET', current_price, timestamp,
                                   {'order_type': 'MARKET', 'quantity': current_position_size, 'strategy_id': 'MM_PANIC_EXIT'}))
                return exit_signals  # Prioritize panic exit

        # --- Rebalancing Logic ---
        if current_position_size >= self.rebalance_threshold:
            self.logger.info(Fore.YELLOW + f"Rebalancing: Position size ({current_position_size}) >= threshold ({self.rebalance_threshold})." + Style.RESET_ALL)
            exit_side = 'SELL' if current_position_side == 'BUY' else 'BUY'
            if self.rebalance_aggressiveness == 'MARKET':
                exit_signals.append((f'{exit_side}_MARKET', current_price, timestamp,
                                   {'order_type': 'MARKET', 'quantity': current_position_size, 'strategy_id': 'MM_REBALANCE'}))
            else:  # AGGRESSIVE_LIMIT
                aggressive_price = (current_price * (Decimal('1') - self.spread_bps / Decimal('40000'))
                                  if exit_side == 'SELL' else
                                  current_price * (Decimal('1') + self.spread_bps / Decimal('40000')))
                exit_signals.append((f'{exit_side}_LIMIT', aggressive_price, timestamp,
                                   {'order_type': 'LIMIT', 'quantity': current_position_size, 'strategy_id': 'MM_REBALANCE'}))

        self.logger.info(Fore.GREEN + f"Generated {len(exit_signals)} exit signals: {exit_signals}" + Style.RESET_ALL)
        return exit_signals