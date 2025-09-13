import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

@dataclass
class APIConfig:
    KEY: str = os.getenv("BYBIT_API_KEY", "")
    SECRET: str = os.getenv("BYBIT_API_SECRET", "")
    TESTNET: bool = os.getenv("BYBIT_TESTNET", "False").lower() == "true"

@dataclass
class Config:
    api: APIConfig = field(default_factory=APIConfig)
    SYMBOL: str = "BTCUSDT"
    TIMEFRAME: str = "15"
    LOOP_INTERVAL_SECONDS: int = 30
    LOG_LEVEL: str = "INFO"
    MIN_KLINES_FOR_STRATEGY: int = 200
