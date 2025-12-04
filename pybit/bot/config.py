import os

import yaml

# --- CORE BOT SETTINGS ---
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.yaml")

with open(CONFIG_FILE) as f:
    BOT_CONFIG = yaml.safe_load(f)

# API keys are always loaded from environment variables for security
BOT_CONFIG["API_KEY"] = os.environ.get("BYBIT_API_KEY")
BOT_CONFIG["API_SECRET"] = os.environ.get("BYBIT_API_SECRET")

if not BOT_CONFIG["API_KEY"] or not BOT_CONFIG["API_SECRET"]:
    raise ValueError(
        "BYBIT_API_KEY and BYBIT_API_SECRET environment variables must be set.",
    )
