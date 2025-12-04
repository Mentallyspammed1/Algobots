import json
import os
import random
import time

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException
from indicators_api import calculate_ema, calculate_rsi, calculate_supertrend
from pydantic import BaseModel

app = FastAPI(
    title="Bybit Trading Bot Backend",
    description="API for fetching market data and calculating technical indicators.",
)

# Define the path to the bot_state.json file
# Assuming wblive.py is in /data/data/com.termux/files/home/Algobots/whalebot/
BOT_STATE_FILE = "/data/data/com.termux/files/home/Algobots/whalebot/bot_state.json"


class KlineData(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class IndicatorRequest(BaseModel):
    klines: list[KlineData]
    ema_period: int | None = None
    rsi_period: int | None = None
    supertrend_period: int | None = None
    supertrend_multiplier: float | None = None


@app.get("/klines", response_model=list[KlineData])
async def get_klines(symbol: str = "BTCUSDT", interval: str = "15", limit: int = 200):
    """Fetches mock historical kline data.
    In a real application, this would fetch data from Bybit API.
    """
    print(f"Fetching mock klines for {symbol}, interval {interval}, limit {limit}")
    mock_klines = []
    current_time = int(time.time() * 1000)  # milliseconds

    # Generate mock klines
    for i in range(limit):
        timestamp = (
            current_time - (limit - 1 - i) * 15 * 60 * 1000
        )  # 15-minute interval
        open_price = round(random.uniform(40000, 41000), 2)
        close_price = round(random.uniform(open_price - 100, open_price + 100), 2)
        high_price = max(open_price, close_price) + round(random.uniform(10, 50), 2)
        low_price = min(open_price, close_price) - round(random.uniform(10, 50), 2)
        volume = round(random.uniform(100, 1000), 2)

        mock_klines.append(
            KlineData(
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            ),
        )
    return mock_klines


@app.get("/bot_status")
async def get_bot_status():
    """Reads and returns the current state of the trading bot from bot_state.json."""
    if not os.path.exists(BOT_STATE_FILE):
        raise HTTPException(
            status_code=404, detail="Bot state file not found. Is the bot running?",
        )

    try:
        with open(BOT_STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
        return state
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=500,
            detail="Error decoding bot state JSON. File might be corrupted.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"An unexpected error occurred: {e}",
        )


@app.post("/indicators")
async def get_indicators(request: IndicatorRequest):
    """Calculates technical indicators based on provided kline data."""
    if not request.klines:
        raise HTTPException(status_code=400, detail="No kline data provided.")

    # Convert list of KlineData to pandas DataFrame
    df = pd.DataFrame([kline.model_dump() for kline in request.klines])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df.set_index("timestamp")

    # Calculate indicators based on request
    if request.ema_period:
        df = calculate_ema(df.copy(), period=request.ema_period)
    if request.rsi_period:
        df = calculate_rsi(df.copy(), period=request.rsi_period)
    if request.supertrend_period and request.supertrend_multiplier:
        df = calculate_supertrend(
            df.copy(),
            period=request.supertrend_period,
            multiplier=request.supertrend_multiplier,
        )

    # Convert DataFrame back to a list of dictionaries for response
    # Handle NaN values for JSON serialization
    df = df.replace({np.nan: None})
    df["timestamp"] = (
        df.index.astype(np.int64) // 10**6
    )  # Convert back to milliseconds for consistency
    response_data = df.to_dict(orient="records")

    return {"status": "success", "data": response_data}
