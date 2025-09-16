import time

import ccxt
import pandas as pd
import ta


class ScalpingEngine:
    def __init__(self, config: dict):
        self.config = config
        self.exchange = ccxt.bybit({
            'apiKey': config['api_key'],
            'secret': config['api_secret'],
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        self.position = None
        self.ob_analysis = OrderBookAnalyzer()
        self.risk_mgr = RiskManager(config)

    def get_market_data(self) -> pd.DataFrame:
        """Fetch high-frequency tick data"""
        data = self.exchange.fetch_ohlcv(
            self.config['symbol'],
            timeframe='1m',
            limit=100
        )
        return pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    def calculate_scalping_indicators(self, df: pd.DataFrame) -> dict:
        """Calculate scalping-specific technical indicators"""
        indicators = {}

        # Momentum Indicators
        df['momentum'] = ta.momentum.roc(df['close'], window=3)
        df['stoch_rsi'] = ta.momentum.stochrsi(df['close'], window=3)

        # Volume-weighted Price
        df['vwap'] = ta.volume.volume_weighted_average_price(
            df['high'], df['low'], df['close'], df['volume'], window=5
        )

        # Order Flow Analysis
        ob = self.exchange.fetch_order_book(self.config['symbol'])
        indicators['ob_imbalance'] = self.ob_analysis.calculate_imbalance(ob)
        indicators['spread'] = ob['asks'][0][0] - ob['bids'][0][0]

        return {**indicators, **df.iloc[-1].to_dict()}

    def generate_signal(self, indicators: dict) -> str | None:
        """Scalping signal logic with multiple confirmation"""
        signals = []

        # Momentum Confirmation
        if indicators['momentum'] > self.config['momentum_threshold']:
            signals.append('BUY')
        elif indicators['momentum'] < -self.config['momentum_threshold']:
            signals.append('SELL')

        # StochRSI Overbought/Oversold
        if indicators['stoch_rsi'] > 0.8:
            signals.append('SELL')
        elif indicators['stoch_rsi'] < 0.2:
            signals.append('BUY')

        # Order Book Imbalance
        if indicators['ob_imbalance'] > self.config['ob_threshold']:
            signals.append('BUY')
        elif indicators['ob_imbalance'] < -self.config['ob_threshold']:
            signals.append('SELL')

        return self._resolve_signals(signals)

    def _resolve_signals(self, signals: list[str]) -> str | None:
        """Weighted signal resolution"""
        score = sum(1 if s == 'BUY' else -1 for s in signals)
        if score >= 2:
            return 'BUY'
        if score <= -2:
            return 'SELL'
        return None

    def execute_scalp(self, signal: str):
        """Execute scalping trade with risk management"""
        if not self.risk_mgr.approve_trade():
            return

        try:
            price = self.exchange.fetch_ticker(self.config['symbol'])['last']
            size = self.risk_mgr.calculate_position_size(price)

            # IOC order to ensure immediate execution
            order = self.exchange.create_order(
                symbol=self.config['symbol'],
                type='limit',
                side=signal.lower(),
                amount=size,
                price=price * (1.0001 if signal == 'BUY' else 0.9999),
                params={'timeInForce': 'IOC'}
            )

            # Handle partial fills
            if order['filled'] > 0:
                self._place_stop_orders(order)

        except Exception as e:
            print(f"Order failed: {e!s}")

    def _place_stop_orders(self, order: dict):
        """Place OCO stop orders after fill"""
        stop_price = order['price'] * (0.999 if order['side'] == 'buy' else 1.001)
        take_profit = order['price'] * (1.002 if order['side'] == 'buy' else 0.998)

        self.exchange.create_order(
            symbol=self.config['symbol'],
            type='stop_limit',
            side='sell' if order['side'] == 'buy' else 'buy',
            amount=order['filled'],
            stopPrice=stop_price,
            price=stop_price,
            params={'reduceOnly': True}
        )

        self.exchange.create_order(
            symbol=self.config['symbol'],
            type='limit',
            side='sell' if order['side'] == 'buy' else 'buy',
            amount=order['filled'],
            price=take_profit,
            params={'reduceOnly': True}
        )

class OrderBookAnalyzer:
    """Real-time order book analysis for scalping"""
    def calculate_imbalance(self, order_book: dict) -> float:
        bids = order_book['bids']
        asks = order_book['asks']
        bid_vol = sum([b[1] for b in bids[:5]])
        ask_vol = sum([a[1] for a in asks[:5]])
        return (bid_vol - ask_vol) / (bid_vol + ask_vol)

class RiskManager:
    """Scalping-specific risk management"""
    def __init__(self, config: dict):
        self.config = config
        self.max_daily_loss = config['max_daily_loss']
        self.trade_count = 0

    def approve_trade(self) -> bool:
        return self.trade_count < self.config['max_trades_per_hour']

    def calculate_position_size(self, price: float) -> float:
        balance = self.config['initial_balance']
        return (balance * self.config['risk_per_trade']) / price

# Configuration
CONFIG = {
    'api_key': 'YOUR_API_KEY',
    'api_secret': 'YOUR_API_SECRET',
    'symbol': 'BTC/USDT',
    'momentum_threshold': 0.15,
    'ob_threshold': 0.3,
    'risk_per_trade': 0.01,
    'max_daily_loss': 0.02,
    'max_trades_per_hour': 30,
    'initial_balance': 10000
}

if __name__ == "__main__":
    engine = ScalpingEngine(CONFIG)
    while True:
        try:
            data = engine.get_market_data()
            indicators = engine.calculate_scalping_indicators(data)
            signal = engine.generate_signal(indicators)

            if signal:
                engine.execute_scalp(signal)

            time.sleep(5)

        except KeyboardInterrupt:
            print("Stopping scalping engine...")
            break
