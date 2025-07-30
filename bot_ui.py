import pandas as pd
from typing import Any, Dict, List, Optional

# --- Pyrmethus's Color Codex ---
from color_codex import (
    COLOR_RESET, COLOR_BOLD, COLOR_DIM,
    COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN,
    PYRMETHUS_GREEN, PYRMETHUS_BLUE, PYRMETHUS_PURPLE, PYRMETHUS_ORANGE, PYRMETHUS_GREY
)

def display_market_info(
    klines_df: Optional[pd.DataFrame],
    current_price: float,
    symbol: str,
    resistance: List[Dict[str, Any]],
    support: List[Dict[str, Any]],
    bot_logger: Any # Assuming bot_logger is passed for warnings
):
    """Prints current market information to the console."""
    if klines_df is None:
        bot_logger.warning("No klines_df available to display market info.")
        return

    latest_stoch_k = klines_df['stoch_k'].iloc[-1] if 'stoch_k' in klines_df.columns and not pd.isna(klines_df['stoch_k'].iloc[-1]) else "N/A"
    latest_stoch_d = klines_df['stoch_d'].iloc[-1] if 'stoch_d' in klines_df.columns and not pd.isna(klines_df['stoch_d'].iloc[-1]) else "N/A"

    print(f"\n{PYRMETHUS_BLUE}📊 Current Price ({symbol}): {current_price:.4f} @ {klines_df.index[-1].strftime('%Y-%m-%d %H:%M:%S')}{COLOR_RESET}")
    stoch_k_str = f"{latest_stoch_k:.2f}" if isinstance(latest_stoch_k, float) else str(latest_stoch_k)
    stoch_d_str = f"{latest_stoch_d:.2f}" if isinstance(latest_stoch_d, float) else str(latest_stoch_d)
    print(f"{PYRMETHUS_BLUE}📈 StochRSI K: {stoch_k_str}, D: {stoch_d_str}{COLOR_RESET}")

    if resistance:
        print(f"{COLOR_CYAN}Resistance Levels Detected:{COLOR_RESET}")
        for r_level in resistance:
            print(f"  {COLOR_CYAN}- {r_level['price']:.4f} ({r_level['type']}){COLOR_RESET}")
    if support:
        print(f"{COLOR_MAGENTA}Support Levels Detected:{COLOR_RESET}")
        for s_level in support:
            print(f"  {COLOR_MAGENTA}- {s_level['price']:.4f} ({s_level['type']}){COLOR_RESET}")
