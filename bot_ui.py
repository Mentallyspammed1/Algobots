import pandas as pd
from typing import Any, Dict, List, Optional
from decimal import Decimal # Import Decimal

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

def display_market_info(
    klines_df: Optional[pd.DataFrame],
    current_price: Decimal, # Changed to Decimal
    symbol: str,
    pivot_resistance_levels: Dict[str, Decimal],
    pivot_support_levels: Dict[str, Decimal],
    bot_logger: Any # Assuming bot_logger is passed for warnings
):
    """Prints current market information to the console."""
    if klines_df is None:
        bot_logger.warning("No klines_df available to display market info.")
        return

    latest_stoch_k = klines_df['stoch_k'].iloc[-1] if 'stoch_k' in klines_df.columns and not pd.isna(klines_df['stoch_k'].iloc[-1]) else "N/A"
    latest_stoch_d = klines_df['stoch_d'].iloc[-1] if 'stoch_d' in klines_df.columns and not pd.isna(klines_df['stoch_d'].iloc[-1]) else "N/A"
    latest_atr = klines_df['atr'].iloc[-1] if 'atr' in klines_df.columns and not pd.isna(klines_df['atr'].iloc[-1]) else "N/A"
    latest_sma = klines_df['sma'].iloc[-1] if 'sma' in klines_df.columns and not pd.isna(klines_df['sma'].iloc[-1]) else "N/A"
    latest_ehlers_fisher = klines_df['ehlers_fisher'].iloc[-1] if 'ehlers_fisher' in klines_df.columns and not pd.isna(klines_df['ehlers_fisher'].iloc[-1]) else "N/A"
    latest_ehlers_fisher_signal = klines_df['ehlers_fisher_signal'].iloc[-1] if 'ehlers_fisher_signal' in klines_df.columns and not pd.isna(klines_df['ehlers_fisher_signal'].iloc[-1]) else "N/A"
    latest_ehlers_supersmoother = klines_df['ehlers_supersmoother'].iloc[-1] if 'ehlers_supersmoother' in klines_df.columns and not pd.isna(klines_df['ehlers_supersmoother'].iloc[-1]) else "N/A"

    print(f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {current_price:.4f} @ {klines_df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}{COLOR_RESET}")
    stoch_k_str = f"{latest_stoch_k:.2f}" if isinstance(latest_stoch_k, Decimal) else str(latest_stoch_k)
    stoch_d_str = f"{latest_stoch_d:.2f}" if isinstance(latest_stoch_d, Decimal) else str(latest_stoch_d)
    atr_str = f"{latest_atr:.4f}" if isinstance(latest_atr, Decimal) else str(latest_atr)
    sma_str = f"{latest_sma:.4f}" if isinstance(latest_sma, Decimal) else str(latest_sma)
    ehlers_fisher_str = f"{latest_ehlers_fisher:.4f}" if isinstance(latest_ehlers_fisher, Decimal) else str(latest_ehlers_fisher)
    ehlers_fisher_signal_str = f"{latest_ehlers_fisher_signal:.4f}" if isinstance(latest_ehlers_fisher_signal, Decimal) else str(latest_ehlers_fisher_signal)
    ehlers_supersmoother_str = f"{latest_ehlers_supersmoother:.4f}" if isinstance(latest_ehlers_supersmoother, Decimal) else str(latest_ehlers_supersmoother)

    print(f"{PYRMETHUS_BLUE}📈 StochRSI K: {stoch_k_str}, D: {stoch_d_str}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}🌊 ATR: {atr_str}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}📊 SMA: {sma_str}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}🎣 Ehlers Fisher: {ehlers_fisher_str}, Signal: {ehlers_fisher_signal_str}{COLOR_RESET}")
    print(f"{PYRMETHUS_BLUE}✨ Ehlers Super Smoother: {ehlers_supersmoother_str}{COLOR_RESET}")

    if pivot_resistance_levels:
        print(f"{COLOR_CYAN}Resistance Levels Detected:{COLOR_RESET}")
        for r_type, r_price in pivot_resistance_levels.items():
            print(f"  {COLOR_CYAN}- {r_price:.2f} ({r_type}){COLOR_RESET}")
    if pivot_support_levels:
        print(f"{COLOR_MAGENTA}Support Levels Detected:{COLOR_RESET}")
        for s_type, s_price in pivot_support_levels.items():
            print(f"  {COLOR_MAGENTA}- {s_price:.2f} ({s_type}){COLOR_RESET}")