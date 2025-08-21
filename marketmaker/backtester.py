
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from pybit.unified_trading import HTTP
import json
from dataclasses import dataclass, asdict
import csv
from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class Trade:
    """Trade record for backtesting"""
    timestamp: datetime
    side: str
    price: float
    quantity: float
    fee: float
    pnl: float = 0
    position_after: float = 0
    balance_after: float = 0

class BybitDataFetcher:
    """Fetches historical data from Bybit"""
    
    def __init__(self, testnet: bool = False):
        self.session = HTTP(testnet=testnet)
        
    def fetch_klines(self, symbol: str, interval: str, start_time: int, end_time: int, category: str = "linear") -> pd.DataFrame:
        """Fetch historical kline/candlestick data from Bybit"""
        all_klines = []
        current_end = end_time
        
        while current_end > start_time:
            try:
                response = self.session.get_kline(
                    category=category,
                    symbol=symbol,
                    interval=interval,
                    start=start_time,
                    end=current_end,
                    limit=1000
                )
                
                if response['retCode'] == 0:
                    klines = response['result']['list']
                    if not klines:
                        break
                    
                    all_klines.extend(klines)
                    # Update current_end to the timestamp of the oldest kline
                    current_end = int(klines[-1][0]) - 1
                    
                    logger.info(f"Fetched {len(klines)} klines, total: {len(all_klines)}")
                else:
                    logger.error(f"Failed to fetch klines: {response['retMsg']}")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching klines: {e}")
                break
        
        if all_klines:
            df = pd.DataFrame(all_klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        
        return pd.DataFrame()
    
    def fetch_orderbook_snapshot(self, symbol: str, category: str = "linear", limit: int = 50) -> Dict:
        """Fetch current orderbook snapshot"""
        try:
            response = self.session.get_orderbook(
                category=category,
                symbol=symbol,
                limit=limit
            )
            if response['retCode'] == 0:
                return response['result']
            else:
                logger.error(f"Failed to fetch orderbook: {response['retMsg']}")
                return {}
        except Exception as e:
            logger.error(f"Error fetching orderbook: {e}")
            return {}

class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(self, market_maker, config: Config):
        self.market_maker = market_maker
        self.config = config
        self.data_fetcher = BybitDataFetcher()
        
        # Performance tracking
        self.initial_capital = config.INITIAL_CAPITAL
        self.balance = config.INITIAL_CAPITAL
        self.trades: List[Trade] = []
        self.equity_curve = []
        self.orderbook_history = []
        
        # Market data
        self.historical_data = pd.DataFrame()
        self.current_index = 0
        
    def fetch_historical_data(self):
        """Fetch historical data from Bybit"""
        logger.info(f"Fetching historical data for {self.config.SYMBOL}")
        
        start_timestamp = int(pd.Timestamp(self.config.START_DATE).timestamp() * 1000)
        end_timestamp = int(pd.Timestamp(self.config.END_DATE).timestamp() * 1000)
        
        self.historical_data = self.data_fetcher.fetch_klines(
            symbol=self.config.SYMBOL,
            interval=self.config.INTERVAL,
            start_time=start_timestamp,
            end_time=end_timestamp,
            category=self.config.CATEGORY
        )
        
        logger.info(f"Fetched {len(self.historical_data)} data points")
        return self.historical_data
    
    def simulate_orderbook(self, price: float, volume: float) -> Dict:
        """Simulate orderbook based on historical price and volume"""
        spread_pct = 0.0005  # 0.05% spread
        depth_levels = 20
        
        bids = []
        asks = []
        
        for i in range(depth_levels):
            bid_price = price * (1 - spread_pct * (i + 1))
            ask_price = price * (1 + spread_pct * (i + 1))
            
            # Simulate volume distribution
            level_volume = volume * np.exp(-i * 0.3) / depth_levels
            
            bids.append([str(bid_price), str(level_volume)])
            asks.append([str(ask_price), str(level_volume)])
        
        return {
            'b': bids,
            'a': asks,
            'ts': int(datetime.now().timestamp() * 1000),
            'u': self.current_index
        }
    
    def execute_order(self, side: str, price: float, size: float) -> Optional[Trade]:
        """Simulate order execution with fees and slippage"""
        if size <= 0:
            return None
        
        # Apply slippage
        if side.lower() == "buy":
            execution_price = price * (1 + self.config.SLIPPAGE)
            cost = execution_price * size
            fee = cost * self.config.MAKER_FEE
            
            if self.balance < cost + fee:
                logger.warning(f"Insufficient balance for buy order: {cost + fee:.2f} > {self.balance:.2f}")
                return None
            
            self.balance -= (cost + fee)
            self.market_maker.position += size
            
        else:  # sell
            execution_price = price * (1 - self.config.SLIPPAGE)
            proceeds = execution_price * size
            fee = proceeds * self.config.MAKER_FEE
            
            if self.market_maker.position < size:
                logger.warning(f"Insufficient position for sell order: {size:.4f} > {self.market_maker.position:.4f}")
                return None
            
            self.balance += (proceeds - fee)
            self.market_maker.position -= size
        
        # Calculate PnL for sells
        pnl = 0
        if side.lower() == "sell" and self.market_maker.avg_entry_price > 0:
            pnl = (execution_price - self.market_maker.avg_entry_price) * size - fee
        
        # Update average entry price for buys
        if side.lower() == "buy":
            if self.market_maker.position > 0:
                total_cost = self.market_maker.avg_entry_price * (self.market_maker.position - size) + execution_price * size
                self.market_maker.avg_entry_price = total_cost / self.market_maker.position
            else:
                self.market_maker.avg_entry_price = execution_price
        
        trade = Trade(
            timestamp=self.historical_data.iloc[self.current_index]['timestamp'],
            side=side,
            price=execution_price,
            quantity=size,
            fee=fee,
            pnl=pnl,
            position_after=self.market_maker.position,
            balance_after=self.balance
        )
        
        self.trades.append(trade)
        return trade
    
    def check_order_fills(self, current_price: float, current_volume: float):
        """Check if any pending orders would be filled"""
        filled_orders = []
        
        # Check buy orders
        for order_id, order in list(self.market_maker.active_orders['buy'].items()):
            if current_price <= order['price']:
                trade = self.execute_order("Buy", order['price'], order['size'])
                if trade:
                    filled_orders.append(order_id)
                    logger.debug(f"Buy order filled: {order['size']:.4f} @ {order['price']:.2f}")
        
        # Check sell orders
        for order_id, order in list(self.market_maker.active_orders['sell'].items()):
            if current_price >= order['price']:
                trade = self.execute_order("Sell", order['price'], order['size'])
                if trade:
                    filled_orders.append(order_id)
                    logger.debug(f"Sell order filled: {order['size']:.4f} @ {order['price']:.2f}")
        
        # Remove filled orders
        for order_id in filled_orders:
            if order_id in self.market_maker.active_orders['buy']:
                del self.market_maker.active_orders['buy'][order_id]
            if order_id in self.market_maker.active_orders['sell']:
                del self.market_maker.active_orders['sell'][order_id]
    
    def update_market_data(self, row):
        """Update market maker with current market data"""
        current_price = float(row['close'])
        current_volume = float(row['volume'])
        
        # Simulate orderbook
        orderbook = self.simulate_orderbook(current_price, current_volume)
        
        # Update market maker's orderbook
        self.market_maker.orderbook['bid'] = [(float(b[0]), float(b[1])) for b in orderbook['b']]
        self.market_maker.orderbook['ask'] = [(float(a[0]), float(a[1])) for a in orderbook['a']]
        
        if self.market_maker.orderbook['bid'] and self.market_maker.orderbook['ask']:
            best_bid = self.market_maker.orderbook['bid'][0][0]
            best_ask = self.market_maker.orderbook['ask'][0][0]
            self.market_maker.mid_price = (best_bid + best_ask) / 2
            self.market_maker.last_price = self.market_maker.mid_price
    
    def calculate_metrics(self) -> Dict:
        """Calculate performance metrics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'total_pnl': 0,
                'win_rate': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'final_balance': self.balance,
                'return_pct': 0
            }
        
        df_trades = pd.DataFrame([asdict(t) for t in self.trades])
        
        # Calculate metrics
        total_pnl = df_trades['pnl'].sum()
        profitable_trades = df_trades[df_trades['pnl'] > 0]
        win_rate = len(profitable_trades) / len(df_trades) * 100 if len(df_trades) > 0 else 0
        
        # Calculate returns for Sharpe ratio
        if len(self.equity_curve) > 1:
            returns = pd.Series(self.equity_curve).pct_change().dropna()
            sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std() if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Calculate max drawdown
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.expanding().max()
        drawdowns = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdowns.min() * 100 if len(drawdowns) > 0 else 0
        
        # Final metrics
        final_equity = self.balance + (self.market_maker.position * self.market_maker.last_price if self.market_maker.position != 0 else 0)
        return_pct = ((final_equity - self.initial_capital) / self.initial_capital) * 100
        
        return {
            'total_trades': len(df_trades),
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'final_balance': self.balance,
            'final_equity': final_equity,
            'return_pct': return_pct,
            'avg_trade_pnl': total_pnl / len(df_trades) if len(df_trades) > 0 else 0,
            'total_fees': df_trades['fee'].sum()
        }
    
    async def run_backtest(self):
        """Main backtest loop"""
        logger.info("Starting backtest...")
        
        # Fetch historical data
        if self.historical_data.empty:
            self.fetch_historical_data()
        
        if self.historical_data.empty:
            logger.error("No historical data available")
            return
        
        # Main backtest loop
        for index, row in self.historical_data.iterrows():
            self.current_index = index
            
            # Update market data
            self.update_market_data(row)
            
            # Check for order fills
            self.check_order_fills(float(row['close']), float(row['volume']))
            
            # Update orders (market maker logic)
            self.market_maker.update_orders()
            
            # Calculate current equity
            current_equity = self.balance
            if self.market_maker.position != 0:
                current_equity += self.market_maker.position * float(row['close'])
            self.equity_curve.append(current_equity)
            
            # Log progress
            if index % 100 == 0:
                logger.info(f"Progress: {index}/{len(self.historical_data)} | "
                          f"Balance: ${self.balance:.2f} | "
                          f"Position: {self.market_maker.position:.4f} | "
                          f"Equity: ${current_equity:.2f}")
        
        # Calculate final metrics
        metrics = self.calculate_metrics()
        
        logger.info("=" * 50)
        logger.info("BACKTEST RESULTS")
        logger.info("=" * 50)
        for key, value in metrics.items():
            if isinstance(value, float):
                logger.info(f"{key}: {value:.2f}")
            else:
                logger.info(f"{key}: {value}")
        
        return metrics
    
    def save_results(self, filename: str = "backtest_results.csv"):
        """Save backtest results to CSV"""
        if self.trades:
            df_trades = pd.DataFrame([asdict(t) for t in self.trades])
            df_trades.to_csv(f"trades_{filename}", index=False)
            logger.info(f"Trades saved to trades_{filename}")
        
        # Save equity curve
        df_equity = pd.DataFrame({
            'timestamp': self.historical_data['timestamp'][:len(self.equity_curve)],
            'equity': self.equity_curve
        })
        df_equity.to_csv(f"equity_{filename}", index=False)
        logger.info(f"Equity curve saved to equity_{filename}")
