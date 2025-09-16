

# Batch Order Placement with Order Book Analysis

## Complete Order Book Analysis System

```python
import ccxt
import numpy as np
from decimal import Decimal, ROUND_DOWN
import time
from typing import List, Dict, Tuple

class OrderBookAnalyzer:
    def __init__(self, exchange, symbol):
        self.exchange = exchange
        self.symbol = symbol
        self.market = None
        self.load_market_info()
    
    def load_market_info(self):
        """Load market information and precision requirements"""
        markets = self.exchange.load_markets()
        self.market = self.exchange.market(self.symbol)
        
    def fetch_order_book(self, limit=100):
        """Fetch current order book with specified depth"""
        return self.exchange.fetch_order_book(self.symbol, limit)
    
    def analyze_liquidity_levels(self, order_book, side='buy'):
        """Identify key liquidity levels and gaps in the order book"""
        if side == 'buy':
            orders = order_book['asks']
        else:
            orders = order_book['bids']
        
        # Calculate volume-weighted average price for different depths
        vwap_levels = []
        cumulative_volume = 0
        cumulative_cost = 0
        
        for price, volume in orders[:20]:  # Analyze top 20 levels
            cumulative_volume += volume
            cumulative_cost += price * volume
            vwap = cumulative_cost / cumulative_volume if cumulative_volume > 0 else price
            vwap_levels.append({
                'price': price,
                'volume': volume,
                'cumulative_volume': cumulative_volume,
                'vwap': vwap
            })
        
        # Find significant gaps (price levels with low liquidity)
        gaps = []
        for i in range(1, len(orders[:50])):
            price_diff = abs(orders[i] - orders[i-1])
            avg_price = (orders[i] + orders[i-1]) / 2
            gap_percentage = (price_diff / avg_price) * 100
            
            if gap_percentage > 0.05:  # Gap larger than 0.05%
                gaps.append({
                    'start_price': orders[i-1],
                    'end_price': orders[i],
                    'gap_size': gap_percentage
                })
        
        return {
            'vwap_levels': vwap_levels,
            'gaps': gaps,
            'best_price': orders if orders else None,
            'total_volume_10_levels': sum([o for o in orders[:10]])
        }
    
    def calculate_optimal_prices(self, analysis, side, num_orders, spread_percentage=0.1):
        """Calculate optimal prices for batch orders based on order book analysis"""
        optimal_prices = []
        
        if side == 'buy':
            base_price = analysis['best_price'] * (1 - spread_percentage / 100)
            
            # Place orders at key support levels
            for i in range(num_orders):
                # Distribute orders with increasing distance from best price
                price_factor = 1 - (spread_percentage / 100) * (i + 1)
                price = analysis['best_price'] * price_factor
                optimal_prices.append(price)
                
        else:  # sell
            base_price = analysis['best_price'] * (1 + spread_percentage / 100)
            
            for i in range(num_orders):
                price_factor = 1 + (spread_percentage / 100) * (i + 1)
                price = analysis['best_price'] * price_factor
                optimal_prices.append(price)
        
        # Place additional orders in identified gaps
        for gap in analysis['gaps'][:3]:  # Use top 3 gaps
            gap_price = (gap['start_price'] + gap['end_price']) / 2
            optimal_prices.append(gap_price)
        
        return sorted(optimal_prices, reverse=(side == 'sell'))

# Initialize exchange and analyzer
exchange = ccxt.bybit({
    'apiKey': 'YOUR_API_KEY',
    'secret': 'YOUR_SECRET_KEY',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',
        'adjustForTimeDifference': True,
    }
})

analyzer = OrderBookAnalyzer(exchange, 'BTC/USDT')
```

## Dynamic Batch Order Builder

```python
class BatchOrderBuilder:
    def __init__(self, exchange, analyzer):
        self.exchange = exchange
        self.analyzer = analyzer
        
    def calculate_order_sizes(self, total_amount, num_orders, distribution='linear'):
        """Calculate individual order sizes based on distribution strategy"""
        if distribution == 'linear':
            # Equal distribution
            sizes = [total_amount / num_orders] * num_orders
            
        elif distribution == 'weighted':
            # Larger orders at better prices
            weights = np.array([1 / (i + 1) for i in range(num_orders)])
            weights = weights / weights.sum()
            sizes = [total_amount * w for w in weights]
            
        elif distribution == 'pyramid':
            # Increasing size with distance from market
            weights = np.array([i + 1 for i in range(num_orders)])
            weights = weights / weights.sum()
            sizes = [total_amount * w for w in weights]
            
        return sizes
    
    def format_order_params(self, symbol, side, amount, price):
        """Format order parameters with proper precision"""
        market = self.exchange.market(symbol)
        
        # Apply precision formatting
        formatted_amount = self.exchange.amount_to_precision(symbol, amount)
        formatted_price = self.exchange.price_to_precision(symbol, price)
        
        # Check minimum requirements
        cost = float(formatted_amount) * float(formatted_price)
        min_cost = market['limits']['cost']['min']
        
        if cost < min_cost:
            return None  # Skip orders below minimum
        
        return {
            'symbol': symbol,
            'side': side,
            'orderType': 'Limit',
            'qty': formatted_amount,
            'price': formatted_price,
            'timeInForce': 'GTC',
            'orderLinkId': f"{side[:3]}-{int(time.time()*1000)}-{np.random.randint(1000)}"
        }
    
    def build_batch_orders(self, symbol, side, total_amount, strategy='adaptive'):
        """Build batch orders based on order book analysis"""
        # Fetch and analyze order book
        order_book = self.analyzer.fetch_order_book()
        analysis = self.analyzer.analyze_liquidity_levels(order_book, side)
        
        # Determine number of orders based on liquidity
        if strategy == 'adaptive':
            # More orders when liquidity is thin
            liquidity_ratio = analysis['total_volume_10_levels'] / total_amount
            if liquidity_ratio < 5:
                num_orders = 10  # Many small orders in thin market
            elif liquidity_ratio < 20:
                num_orders = 5   # Medium distribution
            else:
                num_orders = 3   # Few large orders in liquid market
        else:
            num_orders = 5  # Default
        
        # Calculate optimal prices
        optimal_prices = self.analyzer.calculate_optimal_prices(
            analysis, side, num_orders, spread_percentage=0.2
        )
        
        # Calculate order sizes
        sizes = self.calculate_order_sizes(
            total_amount, 
            len(optimal_prices), 
            distribution='weighted'
        )
        
        # Build order list
        orders = []
        for price, size in zip(optimal_prices, sizes):
            order_params = self.format_order_params(symbol, side, size, price)
            if order_params:
                orders.append(order_params)
        
        return orders, analysis
```

## Batch Order Execution with Smart Placement

```python
class SmartBatchExecutor:
    def __init__(self, exchange):
        self.exchange = exchange
        self.exchange.load_markets()
        
    def place_batch_orders(self, category, orders):
        """Execute batch order placement with error handling"""
        try:
            # Validate all orders before submission
            validated_orders = []
            for order in orders:
                if self.validate_order(order):
                    validated_orders.append(order)
            
            if not validated_orders:
                return {'success': False, 'error': 'No valid orders to place'}
            
            # Place batch orders using Bybit API
            response = self.exchange.private_post_v5_order_create_batch({
                'category': category,
                'request': validated_orders
            })
            
            return self.parse_batch_response(response)
            
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def validate_order(self, order):
        """Validate individual order parameters"""
        symbol = order['symbol']
        market = self.exchange.market(symbol)
        
        amount = float(order['qty'])
        price = float(order['price'])
        
        # Check amount limits
        if amount < market['limits']['amount']['min']:
            print(f"Order amount {amount} below minimum for {symbol}")
            return False
            
        # Check cost limits
        cost = amount * price
        if cost < market['limits']['cost']['min']:
            print(f"Order cost {cost} below minimum for {symbol}")
            return False
            
        return True
    
    def parse_batch_response(self, response):
        """Parse batch order response"""
        result = response.get('result', {})
        ret_code = response.get('retCode', -1)
        
        if ret_code == 0:
            return {
                'success': True,
                'orders': result.get('list', []),
                'message': response.get('retMsg', 'Success')
            }
        else:
            return {
                'success': False,
                'error': response.get('retMsg', 'Unknown error'),
                'code': ret_code
            }

# Example implementation
def smart_batch_trading_strategy():
    """Complete batch trading strategy with order book analysis"""
    
    # Initialize components
    exchange = ccxt.bybit({
        'apiKey': 'YOUR_API_KEY',
        'secret': 'YOUR_SECRET_KEY',
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    symbol = 'BTC/USDT'
    analyzer = OrderBookAnalyzer(exchange, symbol)
    builder = BatchOrderBuilder(exchange, analyzer)
    executor = SmartBatchExecutor(exchange)
    
    # Build orders based on order book analysis
    total_usdt = 1000  # Total amount to trade
    orders, analysis = builder.build_batch_orders(
        symbol, 
        'buy', 
        total_usdt, 
        strategy='adaptive'
    )
    
    print(f"Order book analysis:")
    print(f"  Best ask: ${analysis['best_price']:.2f}")
    print(f"  Liquidity (10 levels): {analysis['total_volume_10_levels']:.2f}")
    print(f"  Gaps found: {len(analysis['gaps'])}")
    print(f"\nGenerated {len(orders)} orders:")
    
    for i, order in enumerate(orders):
        print(f"  Order {i+1}: {order['qty']} @ ${order['price']}")
    
    # Execute batch placement
    result = executor.place_batch_orders('spot', orders)
    
    if result['success']:
        print(f"\nSuccessfully placed {len(result['orders'])} orders")
        for order_result in result['orders']:
            print(f"  Order ID: {order_result.get('orderId')}")
    else:
        print(f"\nFailed to place orders: {result['error']}")
    
    return result
```

## Advanced Order Book Imbalance Detection

```python
class OrderBookImbalanceStrategy:
    def __init__(self, exchange, symbol):
        self.exchange = exchange
        self.symbol = symbol
        self.market = exchange.market(symbol)
        
    def calculate_order_book_imbalance(self, depth=20):
        """Calculate order book imbalance to determine market pressure"""
        order_book = self.exchange.fetch_order_book(self.symbol, depth * 2)
        
        bid_volume = sum([bid for bid in order_book['bids'][:depth]])
        ask_volume = sum([ask for ask in order_book['asks'][:depth]])
        
        # Calculate imbalance ratio (-1 to 1)
        total_volume = bid_volume + ask_volume
        if total_volume == 0:
            return 0
            
        imbalance = (bid_volume - ask_volume) / total_volume
        
        # Calculate weighted mid price
        if order_book['bids'] and order_book['asks']:
            best_bid = order_book['bids']
            best_ask = order_book['asks']
            weighted_mid = (best_bid * bid_volume + best_ask * ask_volume) / total_volume
        else:
            weighted_mid = 0
        
        return {
            'imbalance': imbalance,
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'weighted_mid': weighted_mid,
            'spread': best_ask - best_bid if order_book['bids'] and order_book['asks'] else 0
        }
    
    def generate_imbalance_based_orders(self, total_amount, imbalance_data):
        """Generate orders based on order book imbalance"""
        orders = []
        
        # Strong buy pressure (positive imbalance)
        if imbalance_data['imbalance'] > 0.3:
            # Place aggressive buy orders near the ask
            strategy = 'aggressive_buy'
            side = 'buy'
            base_price = imbalance_data['weighted_mid']
            num_orders = 3
            spread = 0.05  # Tight spread
            
        # Strong sell pressure (negative imbalance)
        elif imbalance_data['imbalance'] < -0.3:
            # Place defensive sell orders above market
            strategy = 'defensive_sell'
            side = 'sell'
            base_price = imbalance_data['weighted_mid']
            num_orders = 3
            spread = 0.1  # Wider spread
            
        # Balanced market
        else:
            # Place orders on both sides
            strategy = 'balanced'
            return self.generate_balanced_orders(total_amount, imbalance_data)
        
        # Generate orders for imbalanced market
        for i in range(num_orders):
            if side == 'buy':
                price = base_price * (1 - (spread / 100) * i)
            else:
                price = base_price * (1 + (spread / 100) * i)
            
            amount = total_amount / num_orders
            
            # Format with precision
            formatted_price = self.exchange.price_to_precision(self.symbol, price)
            formatted_amount = self.exchange.amount_to_precision(self.symbol, amount)
            
            orders.append({
                'symbol': self.symbol,
                'side': side,
                'orderType': 'Limit',
                'qty': formatted_amount,
                'price': formatted_price,
                'timeInForce': 'PostOnly' if strategy == 'defensive_sell' else 'GTC',
                'orderLinkId': f"{strategy}-{int(time.time()*1000)}-{i}"
            })
        
        return orders
    
    def generate_balanced_orders(self, total_amount, imbalance_data):
        """Generate orders for balanced market conditions"""
        orders = []
        mid_price = imbalance_data['weighted_mid']
        spread_percentage = (imbalance_data['spread'] / mid_price) * 100
        
        # Place orders on both sides of the spread
        for side in ['buy', 'sell']:
            for i in range(2):
                if side == 'buy':
                    # Below mid price
                    price = mid_price * (1 - (spread_percentage / 2) * (i + 1))
                else:
                    # Above mid price
                    price = mid_price * (1 + (spread_percentage / 2) * (i + 1))
                
                amount = (total_amount / 4)  # Split among 4 orders total
                
                formatted_price = self.exchange.price_to_precision(self.symbol, price)
                formatted_amount = self.exchange.amount_to_precision(self.symbol, amount)
                
                orders.append({
                    'symbol': self.symbol,
                    'side': side,
                    'orderType': 'Limit',
                    'qty': formatted_amount,
                    'price': formatted_price,
                    'timeInForce': 'PostOnly',
                    'orderLinkId': f"balanced-{side}-{int(time.time()*1000)}-{i}"
                })
        
        return orders
```

## Complete Execution Example

```python
async def execute_smart_batch_strategy():
    """Execute complete batch order strategy with order book analysis"""
    
    # Initialize exchange
    exchange = ccxt.bybit({
        'apiKey': 'YOUR_API_KEY',
        'secret': 'YOUR_SECRET_KEY',
        'enableRateLimit': True,
        'options': {'defaultType': 'spot'}
    })
    
    symbol = 'ETH/USDT'
    total_amount = 500  # USDT
    
    # Analyze order book imbalance
    imbalance_strategy = OrderBookImbalanceStrategy(exchange, symbol)
    imbalance_data = imbalance_strategy.calculate_order_book_imbalance()
    
    print(f"Market Analysis for {symbol}:")
    print(f"  Imbalance: {imbalance_data['imbalance']:.2%}")
    print(f"  Bid Volume: {imbalance_data['bid_volume']:.2f}")
    print(f"  Ask Volume: {imbalance_data['ask_volume']:.2f}")
    print(f"  Weighted Mid: ${imbalance_data['weighted_mid']:.2f}")
    print(f"  Spread: ${imbalance_data['spread']:.2f}")
    
    # Generate orders based on imbalance
    orders = imbalance_strategy.generate_imbalance_based_orders(
        total_amount, 
        imbalance_data
    )
    
    # Place batch orders
    if orders:
        print(f"\nPlacing {len(orders)} orders:")
        for order in orders:
            print(f"  {order['side'].upper()}: {order['qty']} @ ${order['price']}")
        
        try:
            response = exchange.private_post_v5_order_create_batch({
                'category': 'spot',
                'request': orders
            })
            
            if response.get('retCode') == 0:
                print("\nOrders placed successfully!")
                for result in response.get('result', {}).get('list', []):
                    print(f"  Order ID: {result.get('orderId')}")
            else:
                print(f"\nFailed: {response.get('retMsg')}")
                
        except Exception as e:
            print(f"\nError placing orders: {e}")
    
    return orders

# Run the strategy
# import asyncio
# asyncio.run(execute_smart_batch_strategy())
```

This comprehensive implementation provides intelligent batch order placement based on real-time order book analysis. The system analyzes market liquidity, detects imbalances, identifies gaps, and places orders at optimal price levels to maximize execution probability while minimizing market impact. The strategy adapts to market conditions by adjusting the number of orders, their distribution, and pricing based on the current order book state.
