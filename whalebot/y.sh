#!/data/data/com.termux/files/usr/bin/env bash
# =============================================================================
#  setup_bot.sh – generate everything you need to run the BCH‑OMNI‑SENTINEL V22.4 bot
# =============================================================================
#  1️⃣  Creates the project skeleton
#  2️⃣  Writes a default config.json (filled with the same defaults used in the
#      Python code – you can edit it later)
#  3️⃣  Writes a minimal .env.example (copy → .env and put your API keys)
#  4️⃣  Creates a requirements.txt with the exact third‑party packages used
#  5️⃣  Optionally creates a virtual‑environment and installs the deps
#  6️⃣  Touches a placeholder hist.csv (used only by the optional --simulate flag)
#  7️⃣  Prints a short “how‑to‑run” reminder at the end
#
#  The script is deliberately idempotent – you can rerun it safely.
# =============================================================================

set -euo pipefail   # abort on error, treat unset vars as errors, preserve pipelines

# -------------------------------------------------------------------------
#  1️⃣  Project root folder creation
# -------------------------------------------------------------------------
PROJECT_ROOT="${PWD}"                     # run from wherever you want
LOG_DIR="${PROJECT_ROOT}"
mkdir -p "${PROJECT_ROOT}"

# -------------------------------------------------------------------------
#  2️⃣  Write the default configuration file (config.json)
# -------------------------------------------------------------------------
cat > "${PROJECT_ROOT}/config.json" <<'EOF'
{
  "symbol": "BCHUSDT",
  "category": "linear",
  "initial_max_leverage": 35,
  "leverage": 35,
  "risk_per_trade_pct": "0.01",
  "max_risk_per_trade_pct": "0.03",
  "kelly_fraction_floor": "0.0",
  "sl_atr_mult": "0.5",
  "tp_partial_atr_mult": "0.2",
  "trail_atr_mult": "0.3",
  "equity_stop_pct": "0.10",
  "daily_profit_target_pct": "0.25",
  "daily_loss_limit_pct": "0.10",
  "max_consecutive_losses": 3,
  "stasis_duration_sec": 300,
  "trade_count_daily_reset": true,
  "min_alpha_score": 60.0,
  "vsi_threshold": 1.0,
  "rsi_period": 5,
  "fisher_period": 14,
  "adx_period": 14,
  "adx_threshold": 20.0,
  "supertrend_atr_mult": 10,
  "keltner_mult": 2.0,
  "keltner_window": 10,
  "bollinger_window": 20,
  "bollinger_std_mult": 2.0,
  "bollinger_enabled": true,
  "limit_max_bps_offset": "0.006",
  "limit_min_bps_offset": "0.0005",
  "wait_time_min_sec": "0.2",
  "wait_time_max_sec": "1.0",
  "confirm_order_max_retries": 2,
  "confirm_order_delay_sec_multiplier": "0.5",
  "OBI_WEIGHT": "0.4",
  "MOMENTUM_WEIGHT": "0.3",
  "RSI_WEIGHT": "0.2",
  "TREND_WEIGHT": "0.1",
  "DIR_SCORE_THRESHOLD": "5",
  "ADX_WEIGHT": "0.1",
  "SUPER_TREND_WEIGHT": "0.15",
  "KELTNER_WEIGHT": "0.15",
  "VWAP_WEIGHT": "0.05",
  "VOL_MOM_WEIGHT": "0.05",
  "param_tuning_interval": 30,
  "tunable_params": ["sl_atr_mult","tp_partial_atr_mult","bollinger_std_mult"],
  "battery_alert_threshold": 20,
  "critical_battery_level": 10,
  "max_daily_trades": 500,
  "daily_reset_hour_utc": 0,
  "entry_confirmation_candles": 0,
  "price_ema_proximity_pct": "0.0003",
  "low_vol_atr_threshold": 0.4,
  "superpass_period": 10
}
EOF

echo "✅  config.json created (feel free to edit it later)."

# -------------------------------------------------------------------------
#  3️⃣  Write a .env.example template (you will copy → .env later)
# -------------------------------------------------------------------------
cat > "${PROJECT_ROOT}/.env.example" <<'EOF'
# ----------------------------------------------------------------------
#  Bybit API credentials – copy this file to .env and fill the values.
# ----------------------------------------------------------------------
BYBIT_API_KEY="YOUR_API_KEY_HERE"
BYBIT_API_SECRET="YOUR_API_SECRET_HERE"
BYBIT_TESTNET="false"           # true → use the test‑net endpoint
# ----------------------------------------------------------------------
EOF

echo "✅  .env.example created – copy it to .env and edit the values."

# -------------------------------------------------------------------------
#  4️⃣  Write a minimal requirements.txt with the exact third‑party libs used
# -------------------------------------------------------------------------
cat > "${PROJECT_ROOT}/requirements.txt" <<'EOF'
aiohttp
python-dotenv
rich
colorama
pyyaml
numpy
pandas
xgboost
optuna
# NOTE: pandas is optional – the script will run fine if it is not installed.
EOF

echo "✅  requirements.txt created."

# -------------------------------------------------------------------------
#  5️⃣  (Optional) Create a virtual‑environment and install deps
# -------------------------------------------------------------------------
if [[ "${VIRTUAL_ENV:-}" == "" ]]; then
    echo "⚙️  Creating a virtual environment…"
    python3 -m venv "${PROJECT_ROOT}/venv"
    source "${PROJECT_ROOT}/venv/bin/activate"
    echo "⚙️  Installing Python dependencies…"
    pip install --upgrade pip
    pip install -r "${PROJECT_ROOT}/requirements.txt"
    echo "✅  Dependencies installed into ./venv."
    echo "   To activate it later run: source ${PROJECT_ROOT}/venv/bin/activate"
else
    echo "⚙️  A virtual environment is already active – installing into it."
    pip install -r "${PROJECT_ROOT}/requirements.txt"
fi

# -------------------------------------------------------------------------
#  6️⃣  Touch a placeholder hist.csv (used only by the --simulate flag)
# -------------------------------------------------------------------------
if [[ ! -f "${PROJECT_ROOT}/hist.csv" ]]; then
    echo "# timestamp,open,high,low,close,volume" > "${PROJECT_ROOT}/hist.csv"
    echo "2024-01-01T00:00:00,200,210,195,208,12.5" >> "${PROJECT_ROOT}/hist.csv"
    echo "2024-01-01T01:00:00,208,215,205,212,13.1" >> "${PROJECT_ROOT}/hist.csv"
    echo "… (add more rows if you want to run the back‑test)…" >> "${PROJECT_ROOT}/hist.csv"
    echo "✅  Empty hist.csv created – add real historical candles if you plan to use --simulate."
else
    echo "✅  hist.csv already exists – leaving untouched."
fi

# -------------------------------------------------------------------------
#  7️⃣  Final reminder
# -------------------------------------------------------------------------
cat <<EOF

=====================================================================
🚀  Setup complete!
=====================================================================
1️⃣  Edit ${PROJECT_ROOT}/config.json  (if you need different defaults)
2️⃣  Copy ${PROJECT_ROOT}/.env.example → ${PROJECT_ROOT}/.env
    and paste your Bybit API key / secret (and set BYBIT_TESTNET="true"
    for the test‑net).

3️⃣  (Optional) Activate the virtual‑env if you created one:
        source ${PROJECT_ROOT}/venv/bin/activate

4️⃣  Run the bot:
        python3 bot.py          # normal execution
        # or, to test the optional back‑test mode:
        python3 bot.py --simulate

5️⃣  Keep ${PROJECT_ROOT}/bot.log for rotating logs – the script already
    creates it on first run.

Good luck, and happy trading! 🎯
=====================================================================

EOF