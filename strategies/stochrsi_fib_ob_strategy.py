import logging
from decimal import Decimal
from typing import Any

import pandas as pd
from algobots_types import OrderBlock
from color_codex import COLOR_CYAN
from color_codex import COLOR_GREEN
from color_codex import COLOR_RED
from color_codex import COLOR_RESET
from color_codex import COLOR_YELLOW
from config import EHLERS_FISHER_SIGNAL_PERIOD
from config import OB_TOLERANCE_PCT
from config import PIVOT_TOLERANCE_PCT
from config import SMA_PERIOD
from strategies.strategy_template import StrategyTemplate

strategy_logger = logging.getLogger("stochrsi_fib_ob_strategy")
strategy_logger.setLevel(logging.DEBUG)


def _to_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception as e:
        strategy_logger.error(
            f"{COLOR_RED}Failed to transmute '{value}' to Decimal: {e}{COLOR_RESET}"
        )
        return Decimal("0")


def _check_confluence(
    latest_close: Decimal,
    levels: list[dict[str, Any]],
    level_tolerance_pct: float,
    active_obs: list[OrderBlock],
    ob_tolerance_pct: float,
    is_for_buy_signal: bool,
) -> tuple[bool, str]:
    level_tolerance_dec = _to_decimal(level_tolerance_pct)
    ob_tolerance_dec = _to_decimal(ob_tolerance_pct)

    for level in levels:
        level_price = _to_decimal(level.get("price"))
        if level_price > Decimal("0"):
            price_diff = abs(latest_close - level_price)
            if (
                level_price != Decimal("0")
                and price_diff / level_price <= level_tolerance_dec
            ):
                level_type = "Support" if is_for_buy_signal else "Resistance"
                return (
                    True,
                    f"Near {level_type} {level_price:.2f} ({level_tolerance_pct * 100:.3f}%)",
                )

    for ob in active_obs:
        ob_bottom = _to_decimal(ob.get("bottom"))
        ob_top = _to_decimal(ob.get("top"))

        if ob_bottom == Decimal("0") or ob_top == Decimal("0") or ob_bottom > ob_top:
            strategy_logger.warning(
                f"{COLOR_YELLOW}Order Block with invalid boundary detected: {ob}. Skipping.{COLOR_RESET}"
            )
            continue

        ob_range = ob_top - ob_bottom
        extended_ob_bottom = ob_bottom - ob_range * ob_tolerance_dec
        extended_ob_top = ob_top + ob_range * ob_tolerance_dec

        if ob_range == Decimal("0"):
            extended_ob_bottom = ob_bottom * (Decimal("1") - ob_tolerance_dec)
            extended_ob_top = ob_top * (Decimal("1") + ob_tolerance_dec)

        if latest_close >= extended_ob_bottom and latest_close <= extended_ob_top:
            ob_label = "Bullish" if is_for_buy_signal else "Bearish"
            return (
                True,
                f"Near {ob_label} Order Block (B: {ob_bottom:.2f}, T: {ob_top:.2f})",
            )

    return False, "No structural confluence"


class StochRSI_Fib_OB_Strategy(StrategyTemplate):
    def __init__(self, logger):
        super().__init__(logger)
        self.logger.info("StochRSI_Fib_OB_Strategy initialized.")

    def generate_signals(
        self,
        df: pd.DataFrame,
        resistance_levels: list[dict[str, Any]],
        support_levels: list[dict[str, Any]],
        active_bull_obs: list[OrderBlock],
        active_bear_obs: list[OrderBlock],
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        signals = []

        stoch_k_period = kwargs.get("stoch_k_period")
        stoch_d_period = kwargs.get("stoch_d_period")
        overbought = kwargs.get("overbought")
        oversold = kwargs.get("oversold")
        use_crossover = kwargs.get("use_crossover")
        enable_fib_pivot_actions = kwargs.get("enable_fib_pivot_actions")
        fib_entry_confirm_percent = kwargs.get("fib_entry_confirm_percent")
        pivot_support_levels = kwargs.get("pivot_support_levels")
        pivot_resistance_levels = kwargs.get("pivot_resistance_levels")

        min_rows_needed = max(
            SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2
        )
        if df.empty or len(df) < min_rows_needed:
            self.logger.debug(
                f"{COLOR_YELLOW}DataFrame too short or empty for signal generation. Required at least {min_rows_needed} rows. Skipping signal generation.{COLOR_RESET}"
            )
            return signals

        required_cols = [
            "stoch_k",
            "stoch_d",
            "sma",
            "ehlers_fisher",
            "ehlers_fisher_signal",
            "ehlers_supersmoother",
            "close",
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            self.logger.error(
                f"{COLOR_RED}DataFrame is missing crucial columns for signal generation: {missing_cols}. Skipping signal generation.{COLOR_RESET}"
            )
            return signals

        latest_close = _to_decimal(df["close"].iloc[-1])
        current_timestamp = df.index[-1]

        latest_stoch_k = _to_decimal(df["stoch_k"].iloc[-1])
        latest_stoch_d = _to_decimal(df["stoch_d"].iloc[-1])
        prev_stoch_k = _to_decimal(df["stoch_k"].iloc[-2])
        prev_stoch_d = _to_decimal(df["stoch_d"].iloc[-2])

        latest_ehlers_fisher = _to_decimal(df["ehlers_fisher"].iloc[-1])
        prev_ehlers_fisher = _to_decimal(df["ehlers_fisher"].iloc[-2])
        latest_ehlers_fisher_signal = _to_decimal(df["ehlers_fisher_signal"].iloc[-1])
        prev_ehlers_fisher_signal = _to_decimal(df["ehlers_fisher_signal"].iloc[-2])

        latest_sma = _to_decimal(df["sma"].iloc[-1])
        latest_ehlers_supersmoother = _to_decimal(df["ehlers_supersmoother"].iloc[-1])

        overbought_dec = _to_decimal(overbought)
        oversold_dec = _to_decimal(oversold)
        fib_entry_confirm_dec = _to_decimal(fib_entry_confirm_percent)

        current_trend_is_up = latest_close > latest_sma
        current_trend_is_down = latest_close < latest_sma

        fisher_buy_signal = (
            prev_ehlers_fisher < prev_ehlers_fisher_signal
            and latest_ehlers_fisher >= latest_ehlers_fisher_signal
        )
        fisher_sell_signal = (
            prev_ehlers_fisher > prev_ehlers_fisher_signal
            and latest_ehlers_fisher <= latest_ehlers_fisher_signal
        )

        fisher_long_bias = (
            latest_ehlers_fisher > Decimal("0")
            and latest_ehlers_fisher > prev_ehlers_fisher
        )
        fisher_short_bias = (
            latest_ehlers_fisher < Decimal("0")
            and latest_ehlers_fisher < prev_ehlers_fisher
        )

        fib_long_confirm = False
        fib_short_confirm = False
        fib_reason_part = ""

        if enable_fib_pivot_actions:
            if not pivot_support_levels and not pivot_resistance_levels:
                self.logger.warning(
                    f"{COLOR_YELLOW}Fib Pivot confirmation enabled, but no pivot levels calculated. Entry check may be impacted.{COLOR_RESET}"
                )

            if current_trend_is_up:
                for name, price in pivot_support_levels.items():
                    if (
                        price > Decimal("0")
                        and abs(latest_close - price) / price <= fib_entry_confirm_dec
                    ):
                        fib_long_confirm = True
                        fib_reason_part = f"Near Fib Support {name}={price:.2f} ({fib_entry_confirm_percent * 100:.3f}%)"
                        break
                if not fib_long_confirm:
                    self.logger.debug(
                        f"Buy signal considered, but price {latest_close:.2f} not near any Fib support level within {fib_entry_confirm_dec * 100:.3f}%. (Current: {pivot_support_levels})"
                    )

            if current_trend_is_down:
                for name, price in pivot_resistance_levels.items():
                    if (
                        price > Decimal("0")
                        and abs(latest_close - price) / price <= fib_entry_confirm_dec
                    ):
                        fib_short_confirm = True
                        fib_reason_part = f"Near Fib Resistance {name}={price:.2f} ({fib_entry_confirm_dec * 100:.3f}%)"
                        break
                if not fib_short_confirm:
                    self.logger.debug(
                        f"Sell signal considered, but price {latest_close:.2f} not near any Fib resistance level within {fib_entry_confirm_dec * 100:.3f}%. (Current: {pivot_resistance_levels})"
                    )
        else:
            fib_long_confirm = True
            fib_short_confirm = True

        stoch_info = {"stoch_k": latest_stoch_k, "stoch_d": latest_stoch_d}
        ehlers_info = {
            "fisher": latest_ehlers_fisher,
            "fisher_signal": latest_ehlers_fisher_signal,
            "supersmoother": latest_ehlers_supersmoother,
        }

        if current_trend_is_up and fib_long_confirm:
            confluence_found_buy, confluence_reason_buy = _check_confluence(
                latest_close,
                support_levels,
                PIVOT_TOLERANCE_PCT,
                active_bull_obs,
                OB_TOLERANCE_PCT,
                True,
            )

            if confluence_found_buy:
                stoch_condition_met = False
                stoch_type_str = ""
                if use_crossover:
                    if (
                        prev_stoch_k < prev_stoch_d
                        and latest_stoch_k > latest_stoch_d
                        and latest_stoch_k < overbought_dec
                    ):
                        stoch_condition_met = True
                        stoch_type_str = "k_cross_d_buy"
                elif prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec:
                    stoch_condition_met = True
                    stoch_type_str = "k_oversold_bounce"

                if stoch_condition_met:
                    if fisher_buy_signal or fisher_long_bias:
                        signals.append(
                            (
                                "BUY",
                                latest_close,
                                current_timestamp,
                                {
                                    **stoch_info,
                                    **ehlers_info,
                                    "stoch_type": stoch_type_str,
                                    "confluence": confluence_reason_buy,
                                    "fib_confirm": fib_reason_part,
                                    "ehlers_confirm": f"Fisher {'crossover' if fisher_buy_signal else 'bias'} confirmed",
                                },
                            )
                        )
                        self.logger.info(
                            f"{COLOR_GREEN}BUY Signal ({stoch_type_str}) at {latest_close:.2f}. {confluence_reason_buy}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}"
                        )
                    else:
                        self.logger.debug(
                            f"Buy signal considered, but Ehlers Fisher not confirming (Fisher: {latest_ehlers_fisher:.2f}, Signal: {latest_ehlers_fisher_signal:.2f}, Prev Fisher: {prev_ehlers_fisher:.2f})."
                        )
                else:
                    self.logger.debug(
                        f"Buy signal considered, but StochRSI condition not met (K: {latest_stoch_k:.2f}, D: {latest_stoch_d:.2f})."
                    )
            else:
                self.logger.debug(
                    f"Buy signal considered, but no confluence found: {confluence_reason_buy}"
                )
        else:
            self.logger.debug(
                f"Buy signal skipped: Trend Up={current_trend_is_up}, FibConfirm={fib_long_confirm}."
            )

        if current_trend_is_down and fib_short_confirm:
            confluence_found_sell, confluence_reason_sell = _check_confluence(
                latest_close,
                resistance_levels,
                PIVOT_TOLERANCE_PCT,
                active_bear_obs,
                OB_TOLERANCE_PCT,
                False,
            )

            if confluence_found_sell:
                stoch_condition_met = False
                stoch_type_str = ""
                if use_crossover:
                    if (
                        prev_stoch_k > prev_stoch_d
                        and latest_stoch_k < latest_stoch_d
                        and latest_stoch_k > oversold_dec
                    ):
                        stoch_condition_met = True
                        stoch_type_str = "k_cross_d_sell"
                elif prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec:
                    stoch_condition_met = True
                    stoch_type_str = "k_overbought_rejection"

                if stoch_condition_met:
                    if fisher_sell_signal or fisher_short_bias:
                        signals.append(
                            (
                                "SELL",
                                latest_close,
                                current_timestamp,
                                {
                                    **stoch_info,
                                    **ehlers_info,
                                    "stoch_type": stoch_type_str,
                                    "confluence": confluence_reason_sell,
                                    "fib_confirm": fib_reason_part,
                                    "ehlers_confirm": f"Fisher {'crossover' if fisher_sell_signal else 'bias'} confirmed",
                                },
                            )
                        )
                        self.logger.info(
                            f"{COLOR_RED}SELL Signal ({stoch_type_str}) at {latest_close:.2f}. {confluence_reason_sell}. {fib_reason_part}. Ehlers Fisher confirmed.{COLOR_RESET}"
                        )
                    else:
                        self.logger.debug(
                            f"Sell signal considered, but Ehlers Fisher not confirming (Fisher: {latest_ehlers_fisher:.2f}, Signal: {latest_ehlers_fisher_signal:.2f}, Prev Fisher: {prev_ehlers_fisher:.2f})."
                        )
                else:
                    self.logger.debug(
                        f"Sell signal considered, but StochRSI condition not met (K: {latest_stoch_k:.2f}, D: {latest_stoch_d:.2f})."
                    )
            else:
                self.logger.debug(
                    f"Sell signal considered, but no confluence found: {confluence_reason_sell}"
                )
        else:
            self.logger.debug(
                f"Sell signal skipped: Trend Down={current_trend_is_down}, FibConfirm={fib_short_confirm}."
            )

        return signals

    def generate_exit_signals(
        self,
        df: pd.DataFrame,
        current_position_side: str,
        active_bull_obs: list["OrderBlock"],
        active_bear_obs: list["OrderBlock"],
        **kwargs,
    ) -> list[tuple[str, Decimal, Any, dict[str, Any]]]:
        exit_signals = []

        stoch_k_period = kwargs.get("stoch_k_period")
        stoch_d_period = kwargs.get("stoch_d_period")
        overbought = kwargs.get("overbought")
        oversold = kwargs.get("oversold")
        use_crossover = kwargs.get("use_crossover")
        enable_fib_pivot_actions = kwargs.get("enable_fib_pivot_actions")
        fib_exit_warn_percent = kwargs.get("fib_exit_warn_percent")
        fib_exit_action = kwargs.get("fib_exit_action")
        pivot_support_levels = kwargs.get("pivot_support_levels")
        pivot_resistance_levels = kwargs.get("pivot_resistance_levels")

        min_rows_needed = max(
            SMA_PERIOD, stoch_k_period, stoch_d_period, EHLERS_FISHER_SIGNAL_PERIOD, 2
        )
        if df.empty or len(df) < min_rows_needed:
            self.logger.warning(
                f"{COLOR_YELLOW}DataFrame too short or empty for exit signal generation. Required at least {min_rows_needed} rows.{COLOR_RESET}"
            )
            return exit_signals

        required_cols = [
            "stoch_k",
            "stoch_d",
            "sma",
            "ehlers_fisher",
            "ehlers_fisher_signal",
            "ehlers_supersmoother",
            "close",
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            self.logger.error(
                f"{COLOR_RED}DataFrame is missing crucial columns for exit signal generation: {missing_cols}{COLOR_RESET}"
            )
            return exit_signals

        latest_close = _to_decimal(df["close"].iloc[-1])
        current_timestamp = df.index[-1]

        latest_stoch_k = _to_decimal(df["stoch_k"].iloc[-1])
        latest_stoch_d = _to_decimal(df["stoch_d"].iloc[-1])
        prev_stoch_k = _to_decimal(df["stoch_k"].iloc[-2])
        prev_stoch_d = _to_decimal(df["stoch_d"].iloc[-2])

        latest_ehlers_fisher = _to_decimal(df["ehlers_fisher"].iloc[-1])
        prev_ehlers_fisher = _to_decimal(df["ehlers_fisher"].iloc[-2])
        latest_ehlers_fisher_signal = _to_decimal(df["ehlers_fisher_signal"].iloc[-1])
        prev_ehlers_fisher_signal = _to_decimal(df["ehlers_fisher_signal"].iloc[-2])

        latest_sma = _to_decimal(df["sma"].iloc[-1])

        overbought_dec = _to_decimal(overbought)
        oversold_dec = _to_decimal(oversold)
        fib_exit_warn_dec = _to_decimal(fib_exit_warn_percent)

        stoch_info = {"stoch_k": latest_stoch_k, "stoch_d": latest_stoch_d}
        ehlers_info = {
            "fisher": latest_ehlers_fisher,
            "fisher_signal": latest_ehlers_fisher_signal,
        }

        trend_reversal_buy_exit = latest_close < latest_sma
        trend_reversal_sell_exit = latest_close > latest_sma

        fisher_exit_long_signal = (
            prev_ehlers_fisher > prev_ehlers_fisher_signal
            and latest_ehlers_fisher <= latest_ehlers_fisher_signal
        )
        fisher_exit_short_signal = (
            prev_ehlers_fisher < prev_ehlers_fisher_signal
            and latest_ehlers_fisher >= latest_ehlers_fisher_signal
        )

        fisher_exit_long_bias_change = latest_ehlers_fisher < Decimal("0")
        fisher_exit_short_bias_change = latest_ehlers_fisher > Decimal("0")

        fib_exit_triggered = False
        fib_exit_reason = ""

        if enable_fib_pivot_actions:
            if not pivot_support_levels and not pivot_resistance_levels:
                self.logger.warning(
                    f"{COLOR_YELLOW}Fib Pivot exit check enabled, but no pivot levels calculated. Exit check may be impacted.{COLOR_RESET}"
                )

            if current_position_side == "BUY":
                for name, price in pivot_resistance_levels.items():
                    if (
                        price > Decimal("0")
                        and abs(latest_close - price) / price <= fib_exit_warn_dec
                    ):
                        fib_exit_reason = f"Approaching Fib Resistance {name}={price:.2f} ({fib_exit_warn_percent * 100:.3f}%)"
                        if fib_exit_action == "exit":
                            fib_exit_triggered = True
                            self.logger.info(
                                f"{COLOR_YELLOW}Fibonacci Exit Triggered (BUY position): {fib_exit_reason}{COLOR_RESET}"
                            )
                        else:
                            self.logger.warning(
                                f"{COLOR_YELLOW}Fibonacci Exit Warning (BUY position): {fib_exit_reason}{COLOR_RESET}"
                            )
                        break
            elif current_position_side == "SELL":
                for name, price in pivot_support_levels.items():
                    if (
                        price > Decimal("0")
                        and abs(latest_close - price) / price <= fib_exit_warn_dec
                    ):
                        fib_exit_reason = f"Approaching Fib Support {name}={price:.2f} ({fib_exit_warn_percent * 100:.3f}%)"
                        if fib_exit_action == "exit":
                            fib_exit_triggered = True
                            self.logger.info(
                                f"{COLOR_YELLOW}Fibonacci Exit Triggered (SELL position): {fib_exit_reason}{COLOR_RESET}"
                            )
                        else:
                            self.logger.warning(
                                f"{COLOR_YELLOW}Fibonacci Exit Warning (SELL position): {fib_exit_reason}{COLOR_RESET}"
                            )
                        break

        if current_position_side == "BUY":
            confluence_found_exit, confluence_reason_exit = _check_confluence(
                latest_close,
                resistance_levels,
                PIVOT_TOLERANCE_PCT,
                active_bear_obs,
                OB_TOLERANCE_PCT,
                False,
            )

            stoch_exit_condition = False
            stoch_exit_type_str = ""
            if use_crossover:
                if prev_stoch_k > prev_stoch_d and latest_stoch_k < latest_stoch_d:
                    stoch_exit_condition = True
                    stoch_exit_type_str = "k_cross_d_exit_long"
            elif prev_stoch_k > overbought_dec and latest_stoch_k <= overbought_dec:
                stoch_exit_condition = True
                stoch_exit_type_str = "k_overbought_rejection_exit_long"

            ehlers_exit_condition = (
                fisher_exit_long_signal or fisher_exit_long_bias_change
            )

            if (
                stoch_exit_condition
                or ehlers_exit_condition
                or trend_reversal_buy_exit
                or confluence_found_exit
                or fib_exit_triggered
            ):
                reason_parts = []
                if stoch_exit_condition:
                    reason_parts.append(f"StochRSI ({stoch_exit_type_str})")
                if ehlers_exit_condition:
                    reason_parts.append("Ehlers Fisher (cross/bias reversal)")
                if trend_reversal_buy_exit:
                    reason_parts.append("Trend reversal (below SMA)")
                if confluence_found_exit:
                    reason_parts.append(f"Confluence ({confluence_reason_exit})")
                if fib_exit_triggered:
                    reason_parts.append(f"Fibonacci Exit ({fib_exit_reason})")

                exit_reason_str = "; ".join(reason_parts)

                exit_signals.append(
                    (
                        "EXIT_BUY",
                        latest_close,
                        current_timestamp,
                        {
                            **stoch_info,
                            **ehlers_info,
                            "exit_reason": exit_reason_str,
                            "confluence_detail": confluence_reason_exit,
                            "fib_trigger_detail": fib_exit_reason,
                        },
                    )
                )
                self.logger.info(
                    f"{COLOR_CYAN}EXIT BUY Signal at {latest_close:.2f}. Reason: {exit_reason_str}{COLOR_RESET}"
                )

        elif current_position_side == "SELL":
            confluence_found_exit, confluence_reason_exit = _check_confluence(
                latest_close,
                support_levels,
                PIVOT_TOLERANCE_PCT,
                active_bull_obs,
                OB_TOLERANCE_PCT,
                True,
            )

            stoch_exit_condition = False
            stoch_exit_type_str = ""
            if use_crossover:
                if prev_stoch_k < prev_stoch_d and latest_stoch_k > latest_stoch_d:
                    stoch_exit_condition = True
                    stoch_exit_type_str = "k_cross_d_exit_short"
            elif prev_stoch_k < oversold_dec and latest_stoch_k >= oversold_dec:
                stoch_exit_condition = True
                stoch_exit_type_str = "k_oversold_bounce_exit_short"

            ehlers_exit_condition = (
                fisher_exit_short_signal or fisher_exit_short_bias_change
            )

            if (
                stoch_exit_condition
                or ehlers_exit_condition
                or trend_reversal_sell_exit
                or confluence_found_exit
                or fib_exit_triggered
            ):
                reason_parts = []
                if stoch_exit_condition:
                    reason_parts.append(f"StochRSI ({stoch_exit_type_str})")
                if ehlers_exit_condition:
                    reason_parts.append("Ehlers Fisher (cross/bias reversal)")
                if trend_reversal_sell_exit:
                    reason_parts.append("Trend reversal (above SMA)")
                if confluence_found_exit:
                    reason_parts.append(f"Confluence ({confluence_reason_exit})")
                if fib_exit_triggered:
                    reason_parts.append(f"Fibonacci Exit ({fib_exit_reason})")

                exit_reason_str = "; ".join(reason_parts)

                exit_signals.append(
                    (
                        "EXIT_SELL",
                        latest_close,
                        current_timestamp,
                        {
                            **stoch_info,
                            **ehlers_info,
                            "exit_reason": exit_reason_str,
                            "confluence_detail": confluence_reason_exit,
                            "fib_trigger_detail": fib_exit_reason,
                        },
                    )
                )
                self.logger.info(
                    f"{COLOR_CYAN}EXIT SELL Signal at {latest_close:.2f}. Reason: {exit_reason_str}{COLOR_RESET}"
                )
        else:
            self.logger.debug(
                f"No active position to generate exit signals for, or unknown position side: {current_position_side}."
            )

    return exit_signals
