#!/bin/bash

# setup_bybit_bot.sh
# Version: 2.0.0 (Improvement 40: Script version tracking)

# --- Constants ---
SCRIPT_VERSION="2.0.0"
PROJECT_NAME_DEFAULT="bybit_trading_bot"
LOG_FILE_DEFAULT="setup_bybit_bot.log"
MIN_PYTHON_VERSION="3.7"
REQUIRED_COMMANDS=("python3" "pip3" "chmod" "mkdir" "touch" "cat" "tee" "awk" "cut" "sed" "mv" "rm" "ping" "command")
DEPENDENCIES=("pybit-unified-trading" "numpy" "pyyaml" "pytest") # Added pytest for test_bot.py
DEFAULT_SYMBOLS=("BTCUSDT" "ETHUSDT")
DEFAULT_INTERVAL=5
DEFAULT_MAX_POSITIONS=10
DEFAULT_MAX_INVENTORY=15
DEFAULT_ORDER_CAPITAL=0.00005
DEFAULT_PNL_THRESHOLD=-50
DEFAULT_MAX_RETRIES=5

# --- Colors for Output (Improvement 8: Colorized output) ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Logging Setup (Improvement 9: Logging to file) ---
# Check if BYBIT_SETUP_LOG_FILE env var is set, otherwise use default
LOG_FILE="${BYBIT_SETUP_LOG_FILE:-$LOG_FILE_DEFAULT}"
# Ensure log file directory is writable
LOG_DIR=$(dirname "$LOG_FILE")
if [[ ! -w "$LOG_DIR" ]]; then
    echo -e "${RED}Error: Log directory '$LOG_DIR' is not writable. Please check permissions.${NC}"
    exit 1
fi
# Redirect stdout and stderr to tee for logging to file and console
exec 1> >(tee -a "$LOG_FILE") 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Starting setup_bybit_bot.sh (Version: $SCRIPT_VERSION)"

# --- Cleanup Function (Improvement 11: Handle interruptions) ---
cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Script interrupted. Cleaning up temporary files..."
    rm -f /tmp/bybit_temp_* 2>/dev/null
    # Attempt to deactivate virtual environment if it was created and activated in this script's context (limited scope)
    if [[ -n "$VENV_PATH" && -f "$VENV_PATH/bin/activate" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Attempting to deactivate virtual environment..."
        # Note: Deactivation is tricky in bash scripts as it affects the current shell.
        # This is more of a symbolic cleanup. User will need to deactivate manually if needed.
    fi
    exit 1
}
trap cleanup SIGINT SIGTERM

# --- Help Message (Improvement 26: Detailed help message) ---
show_help() {
    echo -e "${BLUE}Usage: $0 [-d PROJECT_DIR] [-h] [--dry-run]${NC}"
    echo "Sets up a Bybit trading bot project with necessary files and configurations."
    echo ""
    echo "Options:"
    echo "  -d, --dir PROJECT_DIR  Specify the project directory (default: $PROJECT_NAME_DEFAULT)"
    echo "  -h, --help             Display this help message and exit"
    echo "  --dry-run              Preview actions without executing them"
    echo ""
    echo "Environment Variables:"
    echo "  BYBIT_API_KEY          Bybit API key (optional, prompted if not set)"
    echo "  BYBIT_API_SECRET       Bybit API secret (optional, prompted if not set)"
    echo "  BYBIT_USE_TESTNET      Set to 'true' for testnet (default: true)"
    echo "  BYBIT_LOG_LEVEL        Logging level (DEBUG or INFO, default: INFO)"
    echo "  BYBIT_SETUP_LOG_FILE   Log file for setup (default: $LOG_FILE_DEFAULT)"
    echo "  BYBIT_SYMBOLS          Comma-separated list of symbols (e.g., BTCUSDT,ETHUSDT)"
    echo "  BYBIT_INTERVAL         Bot loop interval in seconds"
    echo "  BYBIT_MAX_POSITIONS    Maximum open positions"
    echo "  BYBIT_MAX_INVENTORY    Maximum inventory units"
    echo "  BYBIT_ORDER_CAPITAL    Capital percentage per order"
    echo "  BYBIT_PNL_THRESHOLD    PNL alert threshold"
    echo "  BYBIT_MAX_RETRIES      Max retries for API calls"
    echo "  BYBIT_BASE_CURRENCY    Base currency for calculations"
    echo "  BYBIT_EMAIL_ALERTS     Set to 'true' to enable email alerts"
    echo "  BYBIT_EMAIL_HOST, PORT, USER, PASS, FROM, TO : SMTP server details"
    exit 0
}

# --- Parse Command-Line Arguments (Improvement 5: Custom project directory) ---
DRY_RUN=false
PROJECT_NAME="$PROJECT_NAME_DEFAULT"
while [[ "$#" -gt 0 ]]; do
    case $1 in
        -d|--dir) PROJECT_NAME="$2"; shift ;;
        -h|--help) show_help ;;
        --dry-run) DRY_RUN=true ;;
        *) echo -e "${RED}Unknown option: $1${NC}" | tee -a "$LOG_FILE"; show_help ;;
    esac
    shift
done
PROJECT_DIR="./$PROJECT_NAME"

# --- Check Required Commands (Improvement 10: Check for required tools) ---
for cmd in "${REQUIRED_COMMANDS[@]}"; do
    if ! command -v "$cmd" &>/dev/null; then
        echo -e "${RED}Error: Required command '$cmd' not found. Please install it and try again.${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi
done

# --- Check Python Version (Improvement 1: Python version check) ---
PYTHON_CMD="python3"
if ! command -v "$PYTHON_CMD" &>/dev/null; then
    PYTHON_CMD="python" # Try 'python' if 'python3' is not found
    if ! command -v "$PYTHON_CMD" &>/dev/null; then
        echo -e "${RED}Error: Python 3 not found. Please install Python $MIN_PYTHON_VERSION or higher.${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi
fi
PYTHON_VERSION=$("$PYTHON_CMD" --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)
if [[ "$PYTHON_MAJOR" -lt 3 || ("$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 7) ]]; then
    echo -e "${RED}Error: Python $PYTHON_VERSION found, but $MIN_PYTHON_VERSION or higher is required.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Found Python $PYTHON_VERSION using command '$PYTHON_CMD'." | tee -a "$LOG_FILE"

# --- Check Pip Availability (Improvement 2: Pip check) ---
PIP_CMD="pip3"
if ! command -v "$PIP_CMD" &>/dev/null; then
    PIP_CMD="pip" # Try 'pip' if 'pip3' is not found
    if ! command -v "$PIP_CMD" &>/dev/null; then
        echo -e "${RED}Error: pip3 not found. Please install pip for Python 3 and try again.${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi
fi
if ! "$PIP_CMD" --version &>/dev/null; then
    echo -e "${RED}Error: pip command found but not working. Please ensure pip is correctly installed.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Found pip using command '$PIP_CMD'." | tee -a "$LOG_FILE"

# --- Check Disk Space (Improvement 24: Disk space check) ---
DISK_SPACE=$(df -k . | tail -1 | awk '{print $4}')
if [[ "$DISK_SPACE" -lt 102400 ]]; then # 100MB in KB
    echo -e "${RED}Error: Insufficient disk space ($((DISK_SPACE/1024)) MB available). At least 100 MB required.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

# --- Check Internet Connectivity (Improvement 32: Internet check) ---
if ! ping -c 1 google.com &>/dev/null; then
    echo -e "${YELLOW}Warning: No internet connection detected. Dependency installation may fail.${NC}" | tee -a "$LOG_FILE"
fi

# --- Backup Existing Directory (Improvement 6: Backup existing project) ---
if [[ -d "$PROJECT_DIR" ]]; then
    BACKUP_DIR="${PROJECT_DIR}_backup_$(date '+%Y%m%d_%H%M%S')"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Existing project directory found. Backing up to $BACKUP_DIR" | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would backup '$PROJECT_DIR' to '$BACKUP_DIR'"
    else
        mv "$PROJECT_DIR" "$BACKUP_DIR"
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to backup existing directory '$PROJECT_DIR'. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# --- Create Project Directory (Improvement 7: Validate writable directory) ---
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create project directory: $PROJECT_DIR"
else
    mkdir -p "$PROJECT_DIR"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Error: Failed to create project directory '$PROJECT_DIR'. Please check permissions.${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Created project directory: $PROJECT_DIR" | tee -a "$LOG_FILE"
fi

# --- Change Directory ---
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would change to directory: $PROJECT_DIR"
else
    cd "$PROJECT_DIR" || { echo -e "${RED}Error: Failed to change directory to '$PROJECT_DIR'. Exiting.${NC}" | tee -a "$LOG_FILE"; exit 1; }
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Changed to directory: $(pwd)" | tee -a "$LOG_FILE"
fi

# --- User Prompts for Configuration (Improvements 13-16, 28-29: User inputs) ---
API_KEY="${BYBIT_API_KEY}"
API_SECRET="${BYBIT_API_SECRET}"
USE_TESTNET="${BYBIT_USE_TESTNET:-true}"
SYMBOLS="${BYBIT_SYMBOLS:-${DEFAULT_SYMBOLS[*]}}"
INTERVAL="${BYBIT_INTERVAL:-$DEFAULT_INTERVAL}"
MAX_POSITIONS="${BYBIT_MAX_POSITIONS:-$DEFAULT_MAX_POSITIONS}"
MAX_INVENTORY="${BYBIT_MAX_INVENTORY:-$DEFAULT_MAX_INVENTORY}"
ORDER_CAPITAL="${BYBIT_ORDER_CAPITAL:-$DEFAULT_ORDER_CAPITAL}"
PNL_THRESHOLD="${BYBIT_PNL_THRESHOLD:-$DEFAULT_PNL_THRESHOLD}"
MAX_RETRIES="${BYBIT_MAX_RETRIES:-$DEFAULT_MAX_RETRIES}"
LOG_LEVEL="${BYBIT_LOG_LEVEL:-INFO}"
BASE_CURRENCY="${BYBIT_BASE_CURRENCY:-USDT}"
EMAIL_ALERTS="false"
EMAIL_HOST=""
EMAIL_PORT=""
EMAIL_USER=""
EMAIL_PASS=""
EMAIL_FROM=""
EMAIL_TO=""

if [[ -z "$API_KEY" || -z "$API_SECRET" ]]; then
    echo -e "${YELLOW}API credentials not found in environment variables. Please provide them:${NC}"
    read -p "Enter Bybit API Key: " API_KEY
    read -s -p "Enter Bybit API Secret: " API_SECRET # Use -s for secret input
    echo "" # Newline after secret input
fi

# Validate API key/secret format (Improvement 15)
if [[ -z "$API_KEY" || -z "$API_SECRET" || "${#API_KEY}" -lt 10 || "${#API_SECRET}" -lt 20 ]]; then
    echo -e "${RED}Error: Invalid or missing API key/secret. Keys must be at least 10 characters, secrets at least 20 characters.${NC}" | tee -a "$LOG_FILE"
    exit 1
fi

read -p "Use Bybit Testnet? (y/n, default: y): " testnet_input
if [[ "$testnet_input" =~ ^[Nn]$ ]]; then
    USE_TESTNET="false"
fi

read -p "Enter trading symbols (comma-separated, e.g., BTCUSDT,ETHUSDT) or press Enter for default ($SYMBOLS): " symbols_input
if [[ -n "$symbols_input" ]]; then
    SYMBOLS="$symbols_input"
fi

read -p "Enter loop interval in seconds (default: $INTERVAL): " interval_input
if [[ -n "$interval_input" && "$interval_input" =~ ^[0-9]+$ && "$interval_input" -gt 0 ]]; then
    INTERVAL="$interval_input"
fi

read -p "Enable email alerts? (y/n, default: n): " email_alerts_input
if [[ "$email_alerts_input" =~ ^[Yy]$ ]]; then
    EMAIL_ALERTS="true"
    read -p "Enter SMTP host (e.g., smtp.gmail.com): " EMAIL_HOST
    read -p "Enter SMTP port (e.g., 587): " EMAIL_PORT
    read -p "Enter SMTP user (e.g., your_email@gmail.com): " EMAIL_USER
    read -s -p "Enter SMTP password: " EMAIL_PASS # Use -s for secret input
    echo "" # Newline after secret input
    read -p "Enter sender email (usually same as user): " EMAIL_FROM
    read -p "Enter recipient email (for alerts): " EMAIL_TO
    # Validate email settings (Improvement 44)
    if [[ -z "$EMAIL_HOST" || -z "$EMAIL_PORT" || -z "$EMAIL_USER" || -z "$EMAIL_PASS" || -z "$EMAIL_FROM" || -z "$EMAIL_TO" ]]; then
        echo -e "${YELLOW}Warning: Incomplete email server configuration. Disabling email alerts.${NC}" | tee -a "$LOG_FILE"
        EMAIL_ALERTS="false"
    fi
fi

# --- Create Virtual Environment (Improvement 3: Virtual env creation) ---
VENV_PATH="./venv"
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create virtual environment at $VENV_PATH"
else
    if [[ ! -d "$VENV_PATH" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating Python virtual environment at $VENV_PATH..." | tee -a "$LOG_FILE"
        "$PYTHON_CMD" -m venv "$VENV_PATH"
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create virtual environment. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Virtual environment created successfully." | tee -a "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Virtual environment already exists at $VENV_PATH." | tee -a "$LOG_FILE"
    fi
fi

# --- Install Dependencies (Improvement 21, 33: Auto install with retry) ---
INSTALL_DEPS=true
if [[ "$DRY_RUN" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would install dependencies."
else
    read -p "Install dependencies now? (y/n, default: y): " install_deps_input
    if [[ "$install_deps_input" =~ ^[Nn]$ ]]; then
        INSTALL_DEPS=false
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Skipping dependency installation. Please run 'pip install -r requirements.txt' manually after activating the virtual environment." | tee -a "$LOG_FILE"
    fi
fi

if [[ "$INSTALL_DEPS" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Installing dependencies using pip..." | tee -a "$LOG_FILE"
    # Activate venv for pip command (this is tricky in scripts, better to use the venv's pip directly)
    VENV_PIP="$VENV_PATH/bin/pip"
    if [[ ! -f "$VENV_PIP" ]]; then
        echo -e "${RED}Error: Virtual environment pip executable not found at $VENV_PIP. Exiting.${NC}" | tee -a "$LOG_FILE"
        exit 1
    fi

    # Attempt installation with retries (Improvement 33)
    MAX_PIP_RETRIES=3
    for ((i=1; i<=$MAX_PIP_RETRIES; i++)); do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Pip install attempt $i/$MAX_PIP_RETRIES..." | tee -a "$LOG_FILE"
        "$VENV_PIP" install -r requirements.txt
        if [ $? -eq 0 ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Dependencies installed successfully." | tee -a "$LOG_FILE"
            break # Exit retry loop if successful
        else
            echo -e "${YELLOW}Warning: Pip install failed on attempt $i. Retrying in 5 seconds...${NC}" | tee -a "$LOG_FILE"
            sleep 5
        fi
        if [[ $i -eq $MAX_PIP_RETRIES ]]; then
            echo -e "${RED}Error: Failed to install dependencies after $MAX_PIP_RETRIES attempts. Please check your internet connection and requirements.txt.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    done
fi

# --- Create Python Files ---

# Create bybit_bot.py (Improvement 25: Skip if exists with prompt)
OVERWRITE_BOT=false
if [[ -f "bybit_bot.py" && "$DRY_RUN" == "false" ]]; then
    read -p "bybit_bot.py already exists. Overwrite? (y/n, default: n): " overwrite_bot_input
    if [[ "$overwrite_bot_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_BOT=true
    fi
else
    OVERWRITE_BOT=true # Always overwrite if it doesn't exist or in dry-run
fi

if [[ "$OVERWRITE_BOT" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating bybit_bot.py..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create bybit_bot.py"
    else
        cat << 'EOF' > bybit_bot.py
# bybit_bot.py

import os
import time
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable, Any
from pybit.unified_trading import HTTP, WebSocket
from decimal import Decimal, getcontext
import asyncio
import functools
import yaml
import smtplib
from email.mime.text import MIMEText
import traceback
import random
import sys

# Set decimal precision for financial calculations
getcontext().prec = 28

# --- Logging Setup ---
log_level = logging.DEBUG if os.getenv("DEBUG_LOG", "false").lower() == "true" else logging.INFO
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bybit_bot.log")
    ]
)
logger = logging.getLogger(__name__)

# --- Configuration ---
config = {}
try:
    with open("bot_config.yaml", "r") as f:
        config = yaml.safe_load(f)
except FileNotFoundError:
    logger.warning("bot_config.yaml not found. Relying on environment variables.")
except Exception as e:
    logger.error(f"Error loading bot_config.yaml: {e}")

API_KEY = os.getenv("BYBIT_API_KEY") or config.get("BYBIT_API_KEY")
API_SECRET = os.getenv("BYBIT_API_SECRET") or config.get("BYBIT_API_SECRET")
USE_TESTNET = (os.getenv("BYBIT_USE_TESTNET", "false") or config.get("BYBIT_USE_TESTNET", "false")).lower() == "true"
EMAIL_ALERTS = config.get("EMAIL_ALERTS", False)
EMAIL_SERVER = config.get("EMAIL_SERVER", {})
MAX_RETRIES = int(config.get("MAX_RETRIES", 5))

def send_email_alert(subject: str, body: str):
    if not EMAIL_ALERTS:
        return
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = EMAIL_SERVER.get('from')
        msg['To'] = EMAIL_SERVER.get('to')
        
        if not all([EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port'), EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass')]):
            logger.error("Email server configuration is incomplete. Cannot send alert.")
            return

        with smtplib.SMTP(EMAIL_SERVER.get('host'), EMAIL_SERVER.get('port')) as server:
            server.starttls()
            server.login(EMAIL_SERVER.get('user'), EMAIL_SERVER.get('pass'))
            server.send_message(msg)
        logger.info("Email alert sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email alert: {e}", exc_info=True)

# --- WebSocket Manager ---
class BybitWebSocketManager:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True, category: str = "linear"):
        self.ws_public: Optional[WebSocket] = None
        self.ws_private: Optional[WebSocket] = None
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        self.category = category
        self.market_data: Dict[str, Any] = {}
        self.positions: Dict[str, Any] = {}
        self.orders: Dict[str, Any] = {}
        self._public_subscriptions: List[str] = []
        self._private_subscriptions: List[str] = []
        self.reconnect_attempts: int = 0

    def _init_public_ws(self):
        if not self.ws_public or not self.ws_public.is_connected():
            try:
                self.ws_public = WebSocket(
                    testnet=self.testnet,
                    channel_type=self.category,
                )
                logger.info(f"Public WebSocket initialized for category: {self.category}.")
            except Exception as e:
                logger.error(f"Failed to initialize public WebSocket: {e}", exc_info=True)
                send_email_alert("WS Init Error", f"Failed to initialize public WebSocket: {e}")

    def _init_private_ws(self):
        if not self.ws_private or not self.ws_private.is_connected():
            try:
                self.ws_private = WebSocket(
                    testnet=self.testnet,
                    channel_type="private",
                    api_key=self.api_key,
                    api_secret=self.api_secret,
                    recv_window=10000
                )
                logger.info("Private WebSocket initialized.")
            except Exception as e:
                logger.error(f"Failed to initialize private WebSocket: {e}", exc_info=True)
                send_email_alert("WS Init Error", f"Failed to initialize private WebSocket: {e}")

    def handle_orderbook(self, message: Dict):
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["orderbook"] = data
                self.market_data[symbol]["timestamp"] = message.get("ts")
        except Exception as e:
            logger.error(f"Error handling orderbook: {e}", exc_info=True)
            send_email_alert("Orderbook Error", str(e))

    def handle_trades(self, message: Dict):
        try:
            data = message.get("data", [])
            for trade in data:
                symbol = trade.get("s")
                if symbol:
                    self.market_data.setdefault(symbol, {})["last_trade"] = trade
        except Exception as e:
            logger.error(f"Error handling trades: {e}", exc_info=True)
            send_email_alert("Trades Error", str(e))

    def handle_ticker(self, message: Dict):
        try:
            data = message.get("data", {})
            symbol = data.get("s")
            if symbol:
                self.market_data.setdefault(symbol, {})["ticker"] = data
        except Exception as e:
            logger.error(f"Error handling ticker: {e}", exc_info=True)
            send_email_alert("Ticker Error", str(e))

    def handle_position(self, message: Dict):
        try:
            data = message.get("data", [])
            for position in data:
                symbol = position.get("symbol")
                if symbol:
                    self.positions[symbol] = position
        except Exception as e:
            logger.error(f"Error handling position: {e}", exc_info=True)
            send_email_alert("Position Error", str(e))

    def handle_order(self, message: Dict):
        try:
            data = message.get("data", [])
            for order in data:
                order_id = order.get("orderId")
                if order_id:
                    self.orders[order_id] = order
        except Exception as e:
            logger.error(f"Error handling order: {e}", exc_info=True)
            send_email_alert("Order Error", str(e))

    def handle_execution(self, message: Dict):
        try:
            data = message.get("data", [])
            for execution in data:
                order_id = execution.get("orderId")
                if order_id:
                    logger.info(f"Execution for {order_id}: Price: {execution.get('execPrice')}, Qty: {execution.get('execQty')}, Side: {execution.get('side')}")
        except Exception as e:
            logger.error(f"Error handling execution: {e}", exc_info=True)
            send_email_alert("Execution Error", str(e))

    def handle_wallet(self, message: Dict):
        try:
            data = message.get("data", [])
            for wallet_data in data:
                coin = wallet_data.get("coin")
                if coin:
                    logger.info(f"Wallet update for {coin}: Available: {wallet_data.get('availableToWithdraw')}, Total: {wallet_data.get('walletBalance')}")
        except Exception as e:
            logger.error(f"Error handling wallet: {e}", exc_info=True)
            send_email_alert("Wallet Error", str(e))

    def handle_kline(self, message: Dict):
        try:
            data = message.get("data", [])
            symbol = None
            if "topic" in message:
                parts = message["topic"].split(".")
                if len(parts) >= 3 and parts[0] == "kline":
                    symbol = parts[-1]
            if symbol and data:
                self.market_data.setdefault(symbol, {})["kline"] = data
        except Exception as e:
            logger.error(f"Error handling kline: {e}", exc_info=True)

    async def subscribe_public_channels(self, symbols: List[str], channels: List[str] = ["orderbook", "publicTrade", "tickers", "kline"]):
        self._init_public_ws()
        if not self.ws_public or not self.ws_public.is_connected():
            logger.error("Public WebSocket not initialized or connected for subscription.")
            return
        await asyncio.sleep(0.5)
        for symbol in symbols:
            if "orderbook" in channels and f"orderbook.1.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.orderbook_stream(
                        depth=1,
                        symbol=symbol,
                        callback=self.handle_orderbook
                    )
                    self._public_subscriptions.append(f"orderbook.1.{symbol}")
                    logger.info(f"Subscribed to orderbook.1.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to orderbook for {symbol}: {e}", exc_info=True)
            if "publicTrade" in channels and f"publicTrade.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.trade_stream(
                        symbol=symbol,
                        callback=self.handle_trades
                    )
                    self._public_subscriptions.append(f"publicTrade.{symbol}")
                    logger.info(f"Subscribed to publicTrade.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to publicTrade for {symbol}: {e}", exc_info=True)
            if "tickers" in channels and f"tickers.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.ticker_stream(
                        symbol=symbol,
                        callback=self.handle_ticker
                    )
                    self._public_subscriptions.append(f"tickers.{symbol}")
                    logger.info(f"Subscribed to tickers.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to tickers for {symbol}: {e}", exc_info=True)
            if "kline" in channels and f"kline.1m.{symbol}" not in self._public_subscriptions:
                try:
                    self.ws_public.kline_stream(
                        interval="1",
                        symbol=symbol,
                        callback=self.handle_kline
                    )
                    self._public_subscriptions.append(f"kline.1m.{symbol}")
                    logger.info(f"Subscribed to kline.1m.{symbol}")
                except Exception as e:
                    logger.error(f"Error subscribing to kline for {symbol}: {e}", exc_info=True)

    async def subscribe_private_channels(self, channels: List[str] = ["position", "order", "execution", "wallet"]):
        self._init_private_ws()
        if not self.ws_private or not self.ws_private.is_connected():
            logger.error("Private WebSocket not initialized or connected for subscription.")
            return
        await asyncio.sleep(0.5)
        if "position" in channels and "position" not in self._private_subscriptions:
            try:
                self.ws_private.position_stream(callback=self.handle_position)
                self._private_subscriptions.append("position")
                logger.info("Subscribed to position stream.")
            except Exception as e:
                logger.error(f"Error subscribing to position stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to position stream: {e}")
        if "order" in channels and "order" not in self._private_subscriptions:
            try:
                self.ws_private.order_stream(callback=self.handle_order)
                self._private_subscriptions.append("order")
                logger.info("Subscribed to order stream.")
            except Exception as e:
                logger.error(f"Error subscribing to order stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to order stream: {e}")
        if "execution" in channels and "execution" not in self._private_subscriptions:
            try:
                self.ws_private.execution_stream(callback=self.handle_execution)
                self._private_subscriptions.append("execution")
                logger.info("Subscribed to execution stream.")
            except Exception as e:
                logger.error(f"Error subscribing to execution stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to execution stream: {e}")
        if "wallet" in channels and "wallet" not in self._private_subscriptions:
            try:
                self.ws_private.wallet_stream(callback=self.handle_wallet)
                self._private_subscriptions.append("wallet")
                logger.info("Subscribed to wallet stream.")
            except Exception as e:
                logger.error(f"Error subscribing to wallet stream: {e}", exc_info=True)
                send_email_alert("WS Subscription Error", f"Failed to subscribe to wallet stream: {e}")

    def start(self):
        logger.info("WebSocket Manager started.")

    def stop(self):
        if self.ws_public:
            try:
                self.ws_public.exit()
                logger.info("Public WebSocket connection closed.")
            except Exception as e:
                logger.error(f"Error closing public WebSocket: {e}", exc_info=True)
        if self.ws_private:
            try:
                self.ws_private.exit()
                logger.info("Private WebSocket connection closed.")
            except Exception as e:
                logger.error(f"Error closing private WebSocket: {e}", exc_info=True)
        logger.info("WebSocket Manager stopped.")

    def is_public_connected(self) -> bool:
        return self.ws_public is not None and self.ws_public.is_connected()

    def is_private_connected(self) -> bool:
        return self.ws_private is not None and self.ws_private.is_connected()

    async def reconnect(self, symbols: List[str]):
        self.reconnect_attempts += 1
        if self.reconnect_attempts > MAX_RETRIES:
            logger.critical("Max reconnect attempts reached. Shutting down.")
            send_email_alert("Critical: Max Reconnects", "Bot shutting down due to persistent connection issues.")
            sys.exit(1)
        backoff = min(2 ** self.reconnect_attempts + random.uniform(0, 1), 60)
        logger.warning(f"Reconnecting WebSocket after {backoff:.2f} seconds (Attempt {self.reconnect_attempts}/{MAX_RETRIES})")
        await asyncio.sleep(backoff)
        try:
            await self.subscribe_public_channels(symbols)
            await self.subscribe_private_channels()
            if self.is_public_connected() and self.is_private_connected():
                self.reconnect_attempts = 0
                logger.info("WebSocket reconnected successfully.")
            else:
                logger.warning("WebSocket reconnection attempt finished, but connections not fully established.")
        except Exception as e:
            logger.error(f"Error during WebSocket reconnection: {e}", exc_info=True)
            send_email_alert("WS Reconnect Error", f"Error during reconnection attempt: {e}")

# --- Trading Bot Core ---
class BybitTradingBot:
    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        self.session = HTTP(
            testnet=testnet,
            api_key=api_key,
            api_secret=api_secret,
            recv_window=10000
        )
        self.category: str = config.get("CATEGORY", "linear")
        self.ws_manager = BybitWebSocketManager(api_key, api_secret, testnet, category=self.category)
        self.strategy: Optional[Callable[[Dict, Dict, HTTP, Any, List[str]], None]] = None
        self.symbol_info: Dict[str, Any] = {}
        self.max_open_positions: int = config.get("MAX_OPEN_POSITIONS", 5)
        self.base_currency: str = config.get("BASE_CURRENCY", "USDT")

        logger.info(f"Bybit Trading Bot initialized. Testnet: {testnet}, Category: {self.category}, Base Currency: {self.base_currency}")

    async def fetch_symbol_info(self, symbols: List[str]):
        logger.info(f"Fetching instrument info for symbols: {symbols}")
        try:
            for symbol in symbols:
                for attempt in range(MAX_RETRIES):
                    try:
                        response = await asyncio.to_thread(self.session.get_instruments_info, category=self.category, symbol=symbol)
                        if response and response.get('retCode') == 0:
                            instrument_list = response.get('result', {}).get('list', [])
                            found = False
                            for item in instrument_list:
                                if item.get('symbol') == symbol:
                                    self.symbol_info[symbol] = {
                                        "minOrderQty": Decimal(item.get('lotSizeFilter', {}).get('minOrderQty', '0')),
                                        "qtyStep": Decimal(item.get('lotSizeFilter', {}).get('qtyStep', '1')),
                                        "tickSize": Decimal(item.get('priceFilter', {}).get('tickSize', '0.000001')),
                                        "minPrice": Decimal(item.get('priceFilter', {}).get('minPrice', '0')),
                                        "maxPrice": Decimal(item.get('priceFilter', {}).get('maxPrice', '1000000')),
                                        "leverageFilter": item.get('leverageFilter', {}),
                                        "riskLimit": item.get('riskLimit', {})
                                    }
                                    logger.info(f"Successfully fetched instrument info for {symbol}.")
                                    found = True
                                    break
                            if not found:
                                logger.warning(f"Symbol {symbol} not found in instruments list response.")
                            break
                        else:
                            logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: API returned error code {response.get('retCode')}: {response.get('retMsg')}")
                            await asyncio.sleep(2 ** attempt)
                    except Exception as e:
                        logger.warning(f"Attempt {attempt+1}/{MAX_RETRIES} for {symbol}: Exception occurred: {e}")
                        await asyncio.sleep(2 ** attempt)
                else:
                    logger.error(f"Failed to fetch instrument info for {symbol} after {MAX_RETRIES} retries.")
                    send_email_alert("Symbol Info Failure", f"Failed to fetch instrument info for {symbol} after retries.")
        except Exception as e:
            logger.error(f"An unexpected error occurred during fetch_symbol_info: {e}", exc_info=True)

    def set_strategy(self, strategy_func: Callable[[Dict, Dict, HTTP, Any, List[str]], None]):
        self.strategy = strategy_func
        logger.info("Trading strategy set.")

    def _round_to_qty_step(self, symbol: str, quantity: Decimal) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round quantity.")
            return quantity
        try:
            qty_step = self.symbol_info[symbol]["qtyStep"]
            if qty_step <= 0:
                logger.warning(f"Invalid qtyStep ({qty_step}) for {symbol}. Returning original quantity.")
                return quantity
            return (quantity // qty_step) * qty_step
        except Exception as e:
            logger.error(f"Error rounding quantity for {symbol}: {e}", exc_info=True)
            return quantity

    def _round_to_tick_size(self, symbol: str, price: Decimal) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot round price.")
            return price
        try:
            tick_size = self.symbol_info[symbol]["tickSize"]
            if tick_size <= 0:
                logger.warning(f"Invalid tickSize ({tick_size}) for {symbol}. Returning original price.")
                return price
            return price.quantize(tick_size)
        except Exception as e:
            logger.error(f"Error rounding price for {symbol}: {e}", exc_info=True)
            return price

    async def get_market_data(self, symbol: str) -> Optional[Dict]:
        ws_data = self.ws_manager.market_data.get(symbol)
        if ws_data and ws_data.get("orderbook") and ws_data.get("ticker") and (time.time() * 1000 - ws_data.get("timestamp", 0)) < 2000:
            return ws_data
        logger.debug(f"WebSocket data for {symbol} not fresh or complete. Falling back to REST API.")
        try:
            orderbook_resp = await asyncio.to_thread(self.session.get_orderbook, category=self.category, symbol=symbol)
            ticker_resp = await asyncio.to_thread(self.session.get_tickers, category=self.category, symbol=symbol)
            if orderbook_resp and orderbook_resp.get('retCode') == 0 and ticker_resp and ticker_resp.get('retCode') == 0:
                ticker_list = ticker_resp.get('result', {}).get('list', [])
                ticker_data = ticker_list[0] if ticker_list else {}
                combined_data = {
                    "orderbook": orderbook_resp.get('result', {}),
                    "ticker": ticker_data,
                    "last_trade": ws_data.get("last_trade") if ws_data else []
                }
                if combined_data.get("orderbook"):
                    combined_data["timestamp"] = time.time() * 1000
                return combined_data
            else:
                logger.warning(f"Failed to get market data for {symbol} via REST. Orderbook: {orderbook_resp.get('retMsg')}, Ticker: {ticker_resp.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching market data for {symbol} via REST: {e}", exc_info=True)
            return None

    async def get_account_info(self, account_type: str = "UNIFIED") -> Optional[Dict]:
        try:
            balance_response = await asyncio.to_thread(self.session.get_wallet_balance, accountType=account_type)
            if balance_response and balance_response.get('retCode') == 0:
                return balance_response.get('result', {})
            else:
                logger.warning(f"Failed to get account balance. API Response: {balance_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}", exc_info=True)
            return None

    async def calculate_position_size(self, symbol: str, capital_percentage: float, price: Decimal, account_info: Dict) -> Decimal:
        if symbol not in self.symbol_info:
            logger.warning(f"Symbol info not available for {symbol}. Cannot calculate position size.")
            return Decimal(0)
        try:
            available_balance = Decimal(0)
            for wallet_entry in account_info.get('list', []):
                for coin_info in wallet_entry.get('coin', []):
                    if coin_info.get('coin') == self.base_currency:
                        available_balance = Decimal(coin_info.get('availableToWithdraw', '0'))
                        break
                if available_balance > 0:
                    break
            if available_balance <= 0:
                logger.warning(f"No available balance for {self.base_currency} to calculate position size.")
                return Decimal(0)
            if price <= 0:
                logger.warning(f"Invalid price ({price}) for {symbol}. Cannot calculate position size.")
                return Decimal(0)
            target_capital = available_balance * Decimal(str(capital_percentage))
            raw_qty = target_capital / price
            rounded_qty = self._round_to_qty_step(symbol, raw_qty)
            min_order_qty = self.symbol_info[symbol]["minOrderQty"]
            if rounded_qty < min_order_qty:
                logger.info(f"Calculated quantity {rounded_qty} for {symbol} is below minimum order quantity {min_order_qty}. Skipping.")
                return Decimal(0)
            max_leverage = Decimal(self.symbol_info[symbol]["leverageFilter"].get("maxLeverage", "1"))
            max_qty_by_leverage = (available_balance * max_leverage) / price
            if rounded_qty > max_qty_by_leverage:
                logger.warning(f"Calculated quantity {rounded_qty} for {symbol} exceeds max quantity by leverage ({max_qty_by_leverage}). Adjusting.")
                rounded_qty = self._round_to_qty_step(symbol, max_qty_by_leverage)
                if rounded_qty < min_order_qty:
                    logger.warning(f"Adjusted quantity for {symbol} is now below minimum order quantity. Skipping.")
                    return Decimal(0)
            logger.info(f"Calculated position size for {symbol}: {rounded_qty} (Capital: {target_capital:.4f} {self.base_currency}, Price: {price})")
            return rounded_qty
        except Exception as e:
            logger.error(f"Error calculating position size for {symbol}: {e}", exc_info=True)
            return Decimal(0)

    async def get_historical_klines(self, symbol: str, interval: str, limit: int = 200) -> Optional[Dict]:
        try:
            klines_response = await asyncio.to_thread(self.session.get_kline,
                                             category=self.category,
                                             symbol=symbol,
                                             interval=interval,
                                             limit=limit)
            if klines_response and klines_response.get('retCode') == 0:
                return klines_response
            else:
                logger.warning(f"Failed to get historical klines for {symbol}. API Response: {klines_response.get('retMsg')}")
                return None
        except Exception as e:
            logger.error(f"Error fetching historical klines for {symbol}: {e}", exc_info=True)
            return None

    def get_open_positions_count(self) -> int:
        count = sum(1 for position_data in self.ws_manager.positions.values() if Decimal(position_data.get('size', '0')) != Decimal('0'))
        return count

    async def place_order(self, symbol: str, side: str, order_type: str, qty: Decimal, price: Optional[Decimal] = None, stop_loss_price: Optional[Decimal] = None, take_profit_price: Optional[Decimal] = None, trigger_by: str = "LastPrice", time_in_force: str = "GTC", **kwargs) -> Optional[Dict]:
        if qty <= 0:
            logger.warning(f"Order quantity for {symbol} is zero or negative. Skipping order placement.")
            return None
        if order_type == "Limit" and (price is None or price <= 0):
            logger.warning(f"Limit order for {symbol} requires a valid price. Skipping order placement.")
            return None
        current_open_positions = self.get_open_positions_count()
        if current_open_positions >= self.max_open_positions:
            logger.warning(f"Max open positions ({self.max_open_positions}) reached. Cannot place new order for {symbol}.")
            return None
        qty = self._round_to_qty_step(symbol, qty)
        if qty <= 0:
            logger.warning(f"Rounded quantity for {symbol} is zero. Skipping order placement.")
            return None
        if price is not None:
            price = self._round_to_tick_size(symbol, price)
        if stop_loss_price is not None:
            stop_loss_price = self._round_to_tick_size(symbol, stop_loss_price)
        if take_profit_price is not None:
            take_profit_price = self._round_to_tick_size(symbol, take_profit_price)
        try:
            params = {
                "category": self.category,
                "symbol": symbol,
                "side": side,
                "orderType": order_type,
                "qty": str(qty),
                "timeInForce": time_in_force,
                **kwargs
            }
            if price is not None:
                params["price"] = str(price)
            if stop_loss_price is not None:
                params["stopLoss"] = str(stop_loss_price)
                params["triggerBy"] = trigger_by
            if take_profit_price is not None:
                params["takeProfit"] = str(take_profit_price)
            order_response = await asyncio.to_thread(self.session.place_order, **params)
            if order_response and order_response.get('retCode') == 0:
                order_result = order_response.get('result', {})
                logger.info(f"Order placed successfully for {symbol}: OrderID={order_result.get('orderId')}, Type={order_type}, Side={side}, Qty={qty}, Price={price if price else 'N/A'}")
                return order_result
            else:
                error_msg = order_response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to place order for {symbol}: {error_msg}")
                send_email_alert("Order Placement Failure", f"For {symbol} ({order_type} {side} {qty}): {error_msg}")
                return None
        except Exception as e:
            logger.error(f"Exception occurred while placing order for {symbol}: {e}", exc_info=True)
            return None

    async def cancel_order(self, symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None) -> bool:
        if order_id is None and order_link_id is None:
            logger.warning(f"Cannot cancel order for {symbol}: No orderId or orderLinkId provided.")
            return False
        try:
            params = {"category": self.category, "symbol": symbol}
            if order_id:
                params["orderId"] = order_id
            elif order_link_id:
                params["orderLinkId"] = order_link_id
            cancel_response = await asyncio.to_thread(self.session.cancel_order, **params)
            if cancel_response and cancel_response.get('retCode') == 0:
                logger.info(f"Order cancelled successfully for {symbol} (ID: {order_id or order_link_id}).")
                return True
            else:
                error_msg = cancel_response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to cancel order for {symbol} (ID: {order_id or order_link_id}): {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while cancelling order for {symbol} (ID: {order_id or order_link_id}): {e}", exc_info=True)
            return False

    async def cancel_all_orders(self, symbol: str) -> bool:
        try:
            response = await asyncio.to_thread(self.session.cancel_all_orders, category=self.category, symbol=symbol)
            if response and response.get('retCode') == 0:
                logger.info(f"All open orders cancelled for {symbol}.")
                return True
            else:
                error_msg = response.get('retMsg', 'Unknown error')
                logger.error(f"Failed to cancel all orders for {symbol}: {error_msg}")
                return False
        except Exception as e:
            logger.error(f"Exception occurred while cancelling all orders for {symbol}: {e}", exc_info=True)
            return False

    async def log_current_pnl(self):
        total_unrealized_pnl = Decimal('0')
        has_pnl_data = False
        for symbol, position_data in self.ws_manager.positions.items():
            if isinstance(position_data, dict) and 'unrealisedPnl' in position_data:
                try:
                    unrealized_pnl = Decimal(position_data.get('unrealisedPnl', '0'))
                    if unrealized_pnl != Decimal('0'):
                        total_unrealized_pnl += unrealized_pnl
                        logger.info(f"Unrealized PnL for {symbol}: {unrealized_pnl:.4f}")
                        has_pnl_data = True
                except Exception as e:
                    logger.error(f"Error processing PnL for {symbol}: {e}", exc_info=True)
        if has_pnl_data:
            logger.info(f"Total Unrealized PnL: {total_unrealized_pnl:.4f}")
            pnl_threshold_str = config.get("PNL_ALERT_THRESHOLD", "-100")
            try:
                pnl_threshold = Decimal(pnl_threshold_str)
                if total_unrealized_pnl < pnl_threshold:
                    logger.warning(f"Total PNL ({total_unrealized_pnl:.4f}) is below threshold ({pnl_threshold:.4f}). Sending alert.")
                    send_email_alert("PNL Alert", f"Total PNL dropped below threshold to {total_unrealized_pnl:.4f}")
            except Exception as e:
                logger.error(f"Invalid PNL_ALERT_THRESHOLD configuration: {pnl_threshold_str}. Error: {e}")

    async def close_all_positions(self, symbols: List[str]):
        logger.info("Closing all open positions...")
        for symbol in symbols:
            position = self.ws_manager.positions.get(symbol, {})
            size = Decimal(position.get('size', '0'))
            side = position.get('side')
            if size > 0:
                close_side = "Sell" if side == "Buy" else "Buy"
                logger.info(f"Closing {side} position for {symbol} with size {size}...")
                try:
                    await self.place_order(symbol, close_side, "Market", size.abs())
                    await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Error closing position for {symbol}: {e}", exc_info=True)
                    send_email_alert("Position Close Error", f"Error closing position for {symbol}: {e}")
            else:
                logger.debug(f"No open position found for {symbol} to close.")
        logger.info("Finished closing all open positions.")

    async def run(self, symbols: List[str], interval: int = 5):
        if not self.strategy:
            logger.error("No trading strategy set. Bot cannot run.")
            return
        self.ws_manager.start()
        await self.ws_manager.subscribe_public_channels(symbols)
        await self.ws_manager.subscribe_private_channels()
        await self.fetch_symbol_info(symbols)
        logger.info("Bot starting main loop...")
        try:
            while True:
                await self._check_ws_connection(symbols)
                current_market_data: Dict[str, Any] = {}
                for symbol in symbols:
                    market_data_for_symbol = await self.get_market_data(symbol)
                    if market_data_for_symbol:
                        current_market_data[symbol] = market_data_for_symbol
                    else:
                        logger.warning(f"Could not retrieve market data for {symbol}. Skipping strategy execution for this symbol.")
                account_info = await self.get_account_info()
                if not current_market_data or not account_info:
                    logger.warning("Missing market data or account info. Waiting for next cycle.")
                    await asyncio.sleep(interval)
                    continue
                await self.strategy(current_market_data, account_info, self.session, self, symbols)
                await self.log_current_pnl()
                sleep_duration = interval + random.uniform(-1, 1)
                if sleep_duration < 1: sleep_duration = 1
                await asyncio.sleep(sleep_duration)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (KeyboardInterrupt).")
        except Exception as e:
            logger.critical(f"Unhandled critical error in main loop: {e}", exc_info=True)
            send_email_alert("Critical Bot Error", f"An unhandled critical error occurred:\n{traceback.format_exc()}")
        finally:
            logger.info("Initiating shutdown sequence...")
            for symbol in symbols:
                await self.cancel_all_orders(symbol)
            await self.close_all_positions(symbols)
            self.ws_manager.stop()
            logger.info("Bot gracefully shut down.")

async def main():
    if not API_KEY or not API_SECRET:
        logger.error("API credentials (BYBIT_API_KEY, BYBIT_API_SECRET) are missing. Please set them in environment variables or bot_config.yaml.")
        return
    bot = BybitTradingBot(api_key=API_KEY, api_secret=API_SECRET, testnet=USE_TESTNET)
    symbols_to_trade = config.get("SYMBOLS", ["BTCUSDT", "ETHUSDT"])
    if not symbols_to_trade:
        logger.error("No trading symbols configured in SYMBOLS. Please add symbols to bot_config.yaml or environment variables.")
        return
    try:
        from market_making_strategy import market_making_strategy
        bot.set_strategy(market_making_strategy)
        logger.info("Market making strategy loaded successfully.")
    except ImportError:
        logger.error("Failed to import 'market_making_strategy'. Ensure 'market_making_strategy.py' is in the same directory and correctly named.")
        return
    except Exception as e:
        logger.error(f"An error occurred during strategy import: {e}", exc_info=True)
        return
    interval = config.get("INTERVAL", 5)
    if not isinstance(interval, int) or interval <= 0:
        logger.warning(f"Invalid INTERVAL configuration: {interval}. Using default of 5 seconds.")
        interval = 5
    await bot.run(symbols=symbols_to_trade, interval=interval)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot terminated by user.")
    except Exception as e:
        logger.critical(f"Unhandled error during asyncio run: {e}", exc_info=True)
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create bybit_bot.py. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create market_making_strategy.py
OVERWRITE_STRATEGY=false
if [[ -f "market_making_strategy.py" && "$DRY_RUN" == "false" ]]; then
    read -p "market_making_strategy.py already exists. Overwrite? (y/n, default: n): " overwrite_strategy_input
    if [[ "$overwrite_strategy_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_STRATEGY=true
    fi
else
    OVERWRITE_STRATEGY=true
fi

if [[ "$OVERWRITE_STRATEGY" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating market_making_strategy.py..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create market_making_strategy.py"
    else
        cat << 'EOF' > market_making_strategy.py
# market_making_strategy.py

import logging
import time
from datetime import datetime
from typing import Dict, List, Any
from pybit.unified_trading import HTTP
from decimal import Decimal
import numpy as np

logger = logging.getLogger(__name__)

async def market_making_strategy(
    market_data: Dict[str, Any],
    account_info: Dict[str, Any],
    http_client: HTTP,
    bot_instance: Any,
    symbols: List[str]
):
    logger.info("-" * 50)
    logger.info(f"Executing Market Making Strategy at {datetime.now()}")
    base_currency = bot_instance.base_currency
    for wallet_entry in account_info.get('list', []):
        for coin_info in wallet_entry.get('coin', []):
            if coin_info.get('coin') == base_currency:
                logger.info(f"{base_currency} Balance: Available={coin_info.get('availableToWithdraw')}, Total={coin_info.get('walletBalance')}")
                break
    for symbol in symbols:
        logger.info(f"Processing symbol: {symbol}")
        symbol_market_data = market_data.get(symbol)
        if not symbol_market_data:
            logger.warning(f"  No market data available for {symbol}. Skipping.")
            continue
        orderbook = symbol_market_data.get("orderbook", {})
        ticker = symbol_market_data.get("ticker", {})
        bids = orderbook.get('b', [])
        asks = orderbook.get('a', [])
        best_bid_price = Decimal('0')
        if bids and isinstance(bids, list) and len(bids) > 0 and isinstance(bids[0], list) and len(bids[0]) > 0:
            best_bid_price = Decimal(bids[0][0])
        best_ask_price = Decimal('0')
        if asks and isinstance(asks, list) and len(asks) > 0 and isinstance(asks[0], list) and len(asks[0]) > 0:
            best_ask_price = Decimal(asks[0][0])
        last_price = Decimal(ticker.get('lastPrice', '0')) if ticker else Decimal('0')
        logger.info(f"  {symbol} - Last Price: {last_price}, Best Bid: {best_bid_price}, Best Ask: {best_ask_price}")
        position_data = bot_instance.ws_manager.positions.get(symbol, {})
        current_position_size = Decimal(position_data.get('size', '0'))
        position_side = position_data.get('side', 'None')
        logger.info(f"  Current position for {symbol}: {position_side} {current_position_size}")
        klines_data = await bot_instance.get_historical_klines(symbol, "1", limit=100)
        volatility = Decimal('0.01')
        if klines_data and klines_data.get('result', {}).get('list'):
            closes = [Decimal(k[4]) for k in klines_data.get('result', {}).get('list', []) if len(k) > 4]
            if len(closes) > 1:
                returns = np.diff([float(c) for c in closes]) / [float(c) for c in closes[:-1]]
                volatility = Decimal(np.std(returns))
                logger.info(f"  Volatility for {symbol}: {volatility:.4f}")
            else:
                logger.warning(f"  Not enough kline data for {symbol} to calculate volatility.")
        else:
            logger.warning(f"  Failed to fetch klines for {symbol}. Using default volatility.")
        base_spread = Decimal('0.001')
        adjusted_spread = base_spread * (Decimal('1') + volatility * Decimal('10'))
        inventory_skew = Decimal('0')
        max_inventory_units = Decimal(config.get("MAX_INVENTORY_UNITS", "10"))
        if current_position_size > 0:
            inventory_skew = (current_position_size / max_inventory_units) * adjusted_spread
        elif current_position_size < 0:
            inventory_skew = (current_position_size / max_inventory_units) * adjusted_spread
        if current_position_size.abs() < max_inventory_units and best_bid_price > 0 and best_ask_price > 0:
            if bot_instance.get_open_positions_count() < bot_instance.max_open_positions:
                capital_percentage_per_order = Decimal(config.get("ORDER_CAPITAL_PERCENTAGE", "0.0001"))
                buy_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_bid_price, account_info)
                if buy_qty > 0:
                    limit_buy_price = bot_instance._round_to_tick_size(symbol, best_bid_price * (Decimal('1') - adjusted_spread - inventory_skew))
                    if limit_buy_price > 0:
                        logger.info(f"  Attempting to place BUY order for {symbol}: Qty={buy_qty}, Price={limit_buy_price}")
                        stop_loss_buy = limit_buy_price * Decimal('0.98')
                        take_profit_buy = limit_buy_price * Decimal('1.02')
                        buy_order_response = await bot_instance.place_order(
                            symbol=symbol,
                            side="Buy",
                            order_type="Limit",
                            qty=buy_qty,
                            price=limit_buy_price,
                            time_in_force="GTC",
                            orderLinkId=f"mm_buy_{int(time.time() * 1000)}_{symbol}",
                            stop_loss_price=stop_loss_buy,
                            take_profit_price=take_profit_buy
                        )
                        if buy_order_response:
                            logger.info(f"  Placed BUY order: {buy_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Calculated limit buy price for {symbol} is invalid ({limit_buy_price}). Skipping BUY order.")
                else:
                    logger.info(f"  Buy quantity for {symbol} is too small. Skipping.")
                sell_qty = await bot_instance.calculate_position_size(symbol, float(capital_percentage_per_order), best_ask_price, account_info)
                if sell_qty > 0:
                    limit_sell_price = bot_instance._round_to_tick_size(symbol, best_ask_price * (Decimal('1') + adjusted_spread + inventory_skew))
                    if limit_sell_price > 0:
                        logger.info(f"  Attempting to place SELL order for {symbol}: Qty={sell_qty}, Price={limit_sell_price}")
                        stop_loss_sell = limit_sell_price * Decimal('1.02')
                        take_profit_sell = limit_sell_price * Decimal('0.98')
                        sell_order_response = await bot_instance.place_order(
                            symbol=symbol,
                            side="Sell",
                            order_type="Limit",
                            qty=sell_qty,
                            price=limit_sell_price,
                            time_in_force="GTC",
                            orderLinkId=f"mm_sell_{int(time.time() * 1000)}_{symbol}",
                            stop_loss_price=stop_loss_sell,
                            take_profit_price=take_profit_sell
                        )
                        if sell_order_response:
                            logger.info(f"  Placed SELL order: {sell_order_response.get('orderId')}")
                    else:
                        logger.warning(f"  Calculated limit sell price for {symbol} is invalid ({limit_sell_price}). Skipping SELL order.")
                else:
                    logger.info(f"  Sell quantity for {symbol} is too small. Skipping.")
            else:
                logger.info(f"  Max open positions ({bot_instance.max_open_positions}) reached. Not placing new orders for {symbol}.")
        elif current_position_size.abs() >= max_inventory_units:
            logger.warning(f"  Inventory limit reached for {symbol} (Current: {current_position_size.abs()}, Limit: {max_inventory_units}). Closing position.")
            close_side = "Sell" if position_side == "Buy" else "Buy"
            await bot_instance.place_order(symbol, close_side, "Market", current_position_size.abs())
        current_time_ms = int(time.time() * 1000)
        stale_order_threshold_ms = 60000
        for order_id, order in list(bot_instance.ws_manager.orders.items()):
            if order.get('orderStatus') == "New":
                try:
                    order_creation_time_ms = int(order.get('createdTime', 0))
                    if current_time_ms - order_creation_time_ms > stale_order_threshold_ms:
                        logger.info(f"  Cancelling stale order {order_id} for {symbol} (Created: {datetime.fromtimestamp(order_creation_time_ms/1000)})")
                        await bot_instance.cancel_order(symbol, order_id=order_id)
                except Exception as e:
                    logger.error(f"  Error processing stale order {order_id} for {symbol}: {e}", exc_info=True)
    logger.info("-" * 50)
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create market_making_strategy.py. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create bot_config.yaml
OVERWRITE_CONFIG=false
if [[ -f "bot_config.yaml" && "$DRY_RUN" == "false" ]]; then
    read -p "bot_config.yaml already exists. Overwrite? (y/n, default: n): " overwrite_config_input
    if [[ "$overwrite_config_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_CONFIG=true
    fi
else
    OVERWRITE_CONFIG=true
fi

if [[ "$OVERWRITE_CONFIG" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating bot_config.yaml..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create bot_config.yaml"
    else
        # Format symbols for YAML list
        YAML_SYMBOLS=$(echo "$SYMBOLS" | sed 's/,/","/g' | sed 's/^/"/;s/$/"/' | sed 's/"/"/g')
        
        cat << EOF > bot_config.yaml
# bot_config.yaml

# --- Bybit API Credentials ---
# IMPORTANT: Replace with your actual API Key and Secret.
# It is highly recommended to use environment variables for security.
# If BYBIT_API_KEY/BYBIT_API_SECRET are set in your environment, they will be used.
BYBIT_API_KEY: "$API_KEY"
BYBIT_API_SECRET: "$API_SECRET"

# --- Trading Settings ---
# Set to true to use the Bybit Testnet, false for the live Bybit trading environment.
BYBIT_USE_TESTNET: $USE_TESTNET
# The trading category (e.g., 'linear', 'inverse', 'spot'). 'linear' is common for perpetual futures.
CATEGORY: linear
# The base currency for calculations and balance checks (e.g., USDT, USDC).
BASE_CURRENCY: "$BASE_CURRENCY"
# List of symbols to trade (e.g., BTCUSDT, ETHUSDT).
SYMBOLS: [$YAML_SYMBOLS]
# The main loop interval in seconds. Affects how often the strategy is re-evaluated.
INTERVAL: $INTERVAL
# Maximum number of open positions the bot will manage across all symbols.
MAX_OPEN_POSITIONS: $MAX_POSITIONS
# Maximum units of a single asset the bot will hold in inventory before attempting to close.
MAX_INVENTORY_UNITS: $MAX_INVENTORY
# Percentage of available capital to risk per order. e.g., 0.0001 for 0.01%.
ORDER_CAPITAL_PERCENTAGE: $ORDER_CAPITAL
# PNL Alerting
# Alert when total unrealized PnL drops below this threshold. Set to a very low number to disable.
PNL_ALERT_THRESHOLD: $PNL_THRESHOLD
# Maximum number of retries for API calls before failing.
MAX_RETRIES: $MAX_RETRIES

# --- Alerting ---
# Enable or disable email alerts.
EMAIL_ALERTS: $EMAIL_ALERTS
# Email server configuration for sending alerts.
EMAIL_SERVER:
  host: "$EMAIL_HOST"
  port: "$EMAIL_PORT"
  user: "$EMAIL_USER"
  pass: "$EMAIL_PASS"
  from: "$EMAIL_FROM"
  to: "$EMAIL_TO"
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create bot_config.yaml. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
        # Validate YAML syntax (Improvement 20)
        if ! "$PYTHON_CMD" -c "import yaml; yaml.safe_load(open('bot_config.yaml'))" 2>/dev/null; then
            echo -e "${RED}Error: Generated bot_config.yaml has invalid YAML syntax. Please check the file.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create .gitignore (Improvement 18)
OVERWRITE_GITIGNORE=false
if [[ -f ".gitignore" && "$DRY_RUN" == "false" ]]; then
    read -p ".gitignore already exists. Overwrite? (y/n, default: n): " overwrite_gitignore_input
    if [[ "$overwrite_gitignore_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_GITIGNORE=true
    fi
else
    OVERWRITE_GITIGNORE=true
fi

if [[ "$OVERWRITE_GITIGNORE" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating .gitignore..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create .gitignore"
    else
        cat << 'EOF' > .gitignore
# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
*.egg-info/

# Logs
*.log
setup_bybit_bot.log

# Environment
.env
bot_config.yaml

# IDE
.vscode/
.idea/
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create .gitignore. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create requirements.txt (Improvement 19)
OVERWRITE_REQS=false
if [[ -f "requirements.txt" && "$DRY_RUN" == "false" ]]; then
    read -p "requirements.txt already exists. Overwrite? (y/n, default: n): " overwrite_reqs_input
    if [[ "$overwrite_reqs_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_REQS=true
    fi
else
    OVERWRITE_REQS=true
fi

if [[ "$OVERWRITE_REQS" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating requirements.txt..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create requirements.txt"
    else
        cat << 'EOF' > requirements.txt
pybit-unified-trading>=3.0.0
numpy>=1.19.0
pyyaml>=5.4.0
pytest>=7.0.0
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create requirements.txt. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create .env file (Improvement 46)
OVERWRITE_ENV=false
if [[ -f ".env" && "$DRY_RUN" == "false" ]]; then
    read -p ".env already exists. Overwrite? (y/n, default: n): " overwrite_env_input
    if [[ "$overwrite_env_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_ENV=true
    fi
else
    OVERWRITE_ENV=true
fi

if [[ "$OVERWRITE_ENV" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating .env..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create .env"
    else
        cat << EOF > .env
BYBIT_API_KEY="$API_KEY"
BYBIT_API_SECRET="$API_SECRET"
BYBIT_USE_TESTNET=$USE_TESTNET
BYBIT_LOG_LEVEL=$LOG_LEVEL
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create .env. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create Dockerfile (Improvement 17)
OVERWRITE_DOCKERFILE=false
if [[ -f "Dockerfile" && "$DRY_RUN" == "false" ]]; then
    read -p "Dockerfile already exists. Overwrite? (y/n, default: n): " overwrite_dockerfile_input
    if [[ "$overwrite_dockerfile_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_DOCKERFILE=true
    fi
else
    OVERWRITE_DOCKERFILE=true
fi

if [[ "$OVERWRITE_DOCKERFILE" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating Dockerfile..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create Dockerfile"
    else
        cat << 'EOF' > Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "bybit_bot.py"]
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create Dockerfile. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create docker-compose.yml (Improvement 17)
OVERWRITE_DOCKER_COMPOSE=false
if [[ -f "docker-compose.yml" && "$DRY_RUN" == "false" ]]; then
    read -p "docker-compose.yml already exists. Overwrite? (y/n, default: n): " overwrite_docker_compose_input
    if [[ "$overwrite_docker_compose_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_DOCKER_COMPOSE=true
    fi
else
    OVERWRITE_DOCKER_COMPOSE=true
fi

if [[ "$OVERWRITE_DOCKER_COMPOSE" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating docker-compose.yml..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create docker-compose.yml"
    else
        cat << 'EOF' > docker-compose.yml
version: '3.8'
services:
  bybit-bot:
    build: .
    env_file:
      - .env
    volumes:
      - .:/app
    restart: unless-stopped
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create docker-compose.yml. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create README.md (Improvement 37)
OVERWRITE_README=false
if [[ -f "README.md" && "$DRY_RUN" == "false" ]]; then
    read -p "README.md already exists. Overwrite? (y/n, default: n): " overwrite_readme_input
    if [[ "$overwrite_readme_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_README=true
    fi
else
    OVERWRITE_README=true
fi

if [[ "$OVERWRITE_README" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating README.md..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create README.md"
    else
        cat << EOF > README.md
# Bybit Trading Bot

This project sets up a Bybit trading bot with a market-making strategy.

## Setup

1. **Configure Environment:**
   - Edit \`bot_config.yaml\` and \`.env\` files to set your API keys, trading parameters, and email settings.
   - Ensure \`BYBIT_USE_TESTNET\` is set correctly.

2. **Activate Virtual Environment:**
   \`\`\`bash
   source venv/bin/activate
   \`\`\`

3. **Install Dependencies:**
   \`\`\`bash
   pip install -r requirements.txt
   \`\`\`

4. **Run the Bot:**
   \`\`\`bash
   python bybit_bot.py
   \`\`\`

5. **Run with Docker:**
   \`\`\`bash
   docker-compose up -d
   \`\`\`

6. **Setup Systemd Service (for background execution):**
   - Edit \`bybit-bot.service\` to set correct paths and user.
   - Copy the service file to the systemd directory:
     \`\`\`bash
     sudo cp bybit-bot.service /etc/systemd/system/
     \`\`\`
   - Reload systemd:
     \`\`\`bash
     sudo systemctl daemon-reload
     \`\`\`
   - Enable and start the service:
     \`\`\`bash
     sudo systemctl enable bybit-bot.service
     sudo systemctl start bybit-bot.service
     \`\`\`
   - Check status:
     \`\`\`bash
     sudo systemctl status bybit-bot.service
     \`\`\`

## Files
- \`bybit_bot.py\`: Main bot application logic.
- \`market_making_strategy.py\`: Trading strategy implementation.
- \`bot_config.yaml\`: Bot configuration (API keys, settings).
- \`.env\`: Environment variables for Docker/shell.
- \`requirements.txt\`: Python dependencies.
- \`.gitignore\`: Git ignore file.
- \`Dockerfile\` and \`docker-compose.yml\`: Docker setup.
- \`README.md\`: Project documentation and setup guide.
- \`test_bot.py\`: Basic test script.
- \`bybit-bot.service\`: Systemd service file template.
- \`venv/\`: Python virtual environment.
- \`bybit_bot.log\`: Bot runtime logs.
- \`setup_bybit_bot.log\`: Setup script logs.

## Testing
Run tests with:
\`\`\`bash
pytest test_bot.py
\`\`\`
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create README.md. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create test_bot.py (Improvement 48)
OVERWRITE_TEST=false
if [[ -f "test_bot.py" && "$DRY_RUN" == "false" ]]; then
    read -p "test_bot.py already exists. Overwrite? (y/n, default: n): " overwrite_test_input
    if [[ "$overwrite_test_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_TEST=true
    fi
else
    OVERWRITE_TEST=true
fi

if [[ "$OVERWRITE_TEST" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating test_bot.py..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create test_bot.py"
    else
        cat << 'EOF' > test_bot.py
# test_bot.py
import pytest
from decimal import Decimal
import os
import yaml

# Assume bot_config.yaml and venv are in the same directory for testing purposes
# In a real scenario, you might mock these or set up a test environment differently.

def test_decimal_precision():
    from decimal import getcontext
    assert getcontext().prec == 28

def test_config_loading():
    # Ensure bot_config.yaml exists before trying to load it
    assert os.path.exists("bot_config.yaml"), "bot_config.yaml not found."
    with open("bot_config.yaml", "r") as f:
        config = yaml.safe_load(f)
    assert config is not None
    # Basic checks for essential keys
    assert "BYBIT_API_KEY" in config
    assert "BYBIT_API_SECRET" in config
    assert "BYBIT_USE_TESTNET" in config
    assert "SYMBOLS" in config
    assert isinstance(config["SYMBOLS"], list)
    assert len(config["SYMBOLS"]) > 0

# Add more tests here for strategy logic, order placement, etc.
# These would typically require mocking the Bybit API or using a testnet environment.
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create test_bot.py. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
    fi
fi

# Create systemd service file (Improvement 42)
OVERWRITE_SYSTEMD=false
if [[ -f "bybit-bot.service" && "$DRY_RUN" == "false" ]]; then
    read -p "bybit-bot.service already exists. Overwrite? (y/n, default: n): " overwrite_systemd_input
    if [[ "$overwrite_systemd_input" =~ ^[Yy]$ ]]; then
        OVERWRITE_SYSTEMD=true
    fi
else
    OVERWRITE_SYSTEMD=true
fi

if [[ "$OVERWRITE_SYSTEMD" == "true" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Creating bybit-bot.service..." | tee -a "$LOG_FILE"
    if [[ "$DRY_RUN" == "true" ]]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] DRY-RUN: Would create bybit-bot.service"
    else
        # Construct the absolute path for venv and script
        # This assumes the script is run from the project's root directory
        PROJECT_ROOT_ABS=$(pwd)
        VENV_PYTHON_PATH="$PROJECT_ROOT_ABS/venv/bin/python"
        BOT_SCRIPT_PATH="$PROJECT_ROOT_ABS/bybit_bot.py"

        # Determine the system user to run the bot as. Default to the current user if not root.
        RUN_AS_USER=$(whoami)
        if [[ "$RUN_AS_USER" == "root" ]]; then
            echo -e "${YELLOW}Warning: Running setup as root. Consider specifying a dedicated user for the bot service.${NC}" | tee -a "$LOG_FILE"
            # Prompt for user if running as root
            read -p "Enter the system user to run the bot service as (e.g., 'botuser'): " RUN_AS_USER
            if [[ -z "$RUN_AS_USER" ]]; then
                echo -e "${RED}Error: User must be specified when running as root. Exiting.${NC}" | tee -a "$LOG_FILE"
                exit 1
            fi
        fi

        cat << EOF > bybit-bot.service
[Unit]
Description=Bybit Trading Bot Service
After=network.target

[Service]
User=$RUN_AS_USER
Group=$RUN_AS_USER
WorkingDirectory=$PROJECT_ROOT_ABS
# Use the python executable from the virtual environment
ExecStart=$VENV_PYTHON_PATH $BOT_SCRIPT_PATH
Restart=always
RestartSec=10 # Restart after 10 seconds if it crashes

[Install]
WantedBy=multi-user.target
EOF
        if [ $? -ne 0 ]; then
            echo -e "${RED}Error: Failed to create bybit-bot.service. Exiting.${NC}" | tee -a "$LOG_FILE"
            exit 1
        fi
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO: Created bybit-bot.service template." | tee -a "$LOG_FILE"
        echo -e "${YELLOW}IMPORTANT: You need to edit 'bybit-bot.service' to ensure 'User', 'Group', 'WorkingDirectory', and 'ExecStart' paths are correct for your system.${NC}" | tee -a "$LOG_FILE"
    fi
fi

# --- Final Summary and Instructions (Improvement 50: Summary table) ---
echo ""
echo -e "${GREEN}---------------------------------------------------------------------${NC}"
echo -e "${GREEN} Project Setup Summary${NC}"
echo -e "${GREEN}---------------------------------------------------------------------${NC}"
echo ""
echo -e "${BLUE}Project Directory:${NC} $PROJECT_DIR"
echo ""
echo -e "${BLUE}Created Files:${NC}"
echo -e "  - ${GREEN}bybit_bot.py${NC}       : Main bot application logic."
echo -e "  - ${GREEN}market_making_strategy.py${NC} : Trading strategy implementation."
echo -e "  - ${GREEN}bot_config.yaml${NC}    : Bot configuration (API keys, settings)."
echo -e "  - ${GREEN}.env${NC}             : Environment variables for Docker/shell."
echo -e "  - ${GREEN}requirements.txt${NC} : Python dependencies."
echo -e "  - ${GREEN}.gitignore${NC}       : Git ignore file."
echo -e "  - ${GREEN}Dockerfile${NC}       : Docker build configuration."
echo -e "  - ${GREEN}docker-compose.yml${NC} : Docker Compose configuration."
echo -e "  - ${GREEN}README.md${NC}        : Project documentation and setup guide."
echo -e "  - ${GREEN}test_bot.py${NC}        : Basic test script."
echo -e "  - ${GREEN}bybit-bot.service${NC}  : Systemd service file template (requires manual editing)."
echo -e "  - ${GREEN}venv/${NC}           : Python virtual environment."
echo -e "  - ${GREEN}bybit_bot.log${NC}      : Bot runtime logs."
echo -e "  - ${GREEN}setup_bybit_bot.log${NC} : Setup script logs."
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. ${YELLOW}Activate Virtual Environment:${NC}"
echo "   Navigate to your project directory if you aren't already there:"
echo "   cd $PROJECT_NAME"
echo "   Source the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. ${YELLOW}Configure bot_config.yaml & .env:${NC}"
echo "   Open \`bot_config.yaml\` and \`.env\` files to finalize your settings, especially API keys and email server details."
echo ""
echo "3. ${YELLOW}Install Dependencies (if not done by script):${NC}"
echo "   If you skipped automatic installation or it failed, run:"
echo "   pip install -r requirements.txt"
echo ""
echo "4. ${YELLOW}Test the Bot (Optional):${NC}"
echo "   Run the basic test:"
echo "   pytest test_bot.py"
echo ""
echo "5. ${YELLOW}Run the Bot:${NC}"
echo "   Ensure your virtual environment is activated:"
echo "   python bybit_bot.py"
echo ""
echo "6. ${YELLOW}Run with Docker:${NC}"
echo "   Build and run the Docker container:"
echo "   docker-compose up -d"
echo ""
echo "7. ${YELLOW}Setup Systemd Service (for background execution):${NC}"
echo "   a. Edit \`bybit-bot.service\` to set correct paths and user."
echo "   b. Copy the service file to the systemd directory:"
echo "      sudo cp bybit-bot.service /etc/systemd/system/"
echo "   c. Reload systemd:"
echo "      sudo systemctl daemon-reload"
echo "   d. Enable and start the service:"
echo "      sudo systemctl enable bybit-bot.service"
echo "      sudo systemctl start bybit-bot.service"
echo "   e. Check status:"
echo "      sudo systemctl status bybit-bot.service"
echo ""
echo -e "${GREEN}---------------------------------------------------------------------${NC}"
echo -e "${GREEN}Setup script finished. Happy trading!${NC}"
echo -e "${GREEN}---------------------------------------------------------------------${NC}"

exit 0
