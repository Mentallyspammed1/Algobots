from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import pandas as pd
import numpy as np
import random
import time

from indicators_api import calculate_ema, calculate_rsi, calculate_supertrend

app = FastAPI(
    title="Bybit Trading Bot Backend",
    description="API for fetching market data and calculating technical indicators."
)

class KlineData(BaseModel):
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

class IndicatorRequest(BaseModel):
    klines: List[KlineData]
    ema_period: Optional[int] = None
    rsi_period: Optional[int] = None
    supertrend_period: Optional[int] = None
    supertrend_multiplier: Optional[float] = None

@app.get("/klines", response_model=List[KlineData])
async def get_klines(
    symbol: str = "BTCUSDT",
    interval: str = "15",
    limit: int = 200
):
    """
    Fetches mock historical kline data.
    In a real application, this would fetch data from Bybit API.
    """
    print(f"Fetching mock klines for {symbol}, interval {interval}, limit {limit}")
    mock_klines = []
    current_time = int(time.time() * 1000) # milliseconds
    
    # Generate mock klines
    for i in range(limit):
        timestamp = current_time - (limit - 1 - i) * 15 * 60 * 1000 # 15-minute interval
        open_price = round(random.uniform(40000, 41000), 2)
        close_price = round(random.uniform(open_price - 100, open_price + 100), 2)
        high_price = max(open_price, close_price) + round(random.uniform(10, 50), 2)
        low_price = min(open_price, close_price) - round(random.uniform(10, 50), 2)
        volume = round(random.uniform(100, 1000), 2)
        
        mock_klines.append(KlineData(
            timestamp=timestamp,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume
        ))
    return mock_klines

@app.post("/indicators")
async def get_indicators(request: IndicatorRequest):
    """
    Calculates technical indicators based on provided kline data.
    """
    if not request.klines:
        raise HTTPException(status_code=400, detail="No kline data provided.")

    # Convert list of KlineData to pandas DataFrame
    df = pd.DataFrame([kline.model_dump() for kline in request.klines])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.set_index('timestamp')

    # Calculate indicators based on request
    if request.ema_period:
        df = calculate_ema(df.copy(), period=request.ema_period)
    if request.rsi_period:
        df = calculate_rsi(df.copy(), period=request.rsi_period)
    if request.supertrend_period and request.supertrend_multiplier:
        df = calculate_supertrend(df.copy(), period=request.supertrend_period, multiplier=request.supertrend_multiplier)

    # Convert DataFrame back to a list of dictionaries for response
    # Handle NaN values for JSON serialization
    df = df.replace({np.nan: None})
    df['timestamp'] = df.index.astype(np.int64) // 10**6 # Convert back to milliseconds for consistency
    response_data = df.to_dict(orient="records")

    return {"status": "success", "data": response_data}