Looking at your request, you want a comprehensive tutorial for building a market making bot using the pybit library, specifically focusing on the functions needed from the unified trading interface. <cite/>

## Market Making Bot Tutorial with pybit

This tutorial covers all essential pybit functions for building a market making bot using Bybit's v5 API through the unified trading interface. [1](#0-0) 

### JSON Configuration Structure

```json
{
  "market_making_bot": {
    "setup": {
      "authentication": {
        "api_key": "your_api_key",
        "api_secret": "your_api_secret",
        "testnet": true
      },
      "trading_parameters": {
        "symbol": "BTCUSDT",
        "category": "linear",
        "spread_percentage": 0.1,
        "order_size": "0.01",
        "max_position": "1.0"
      }
    },
    "required_functions": {
      "market_data": [],
      "order_management": [],
      "position_management": [],
      "account_management": [],
      "websocket_streams": []
    }
  }
}
```

### 1. Market Data Functions

Essential for price discovery and spread calculation: [2](#0-1) 

```json
{
  "market_data_functions": {
    "get_server_time": {
      "purpose": "Synchronize with exchange time",
      "code": "session.get_server_time()",
      "returns": "Server timestamp"
    },
    "get_orderbook": {
      "purpose": "Get current bid/ask prices for spread calculation",
      "code": "session.get_orderbook(category='linear', symbol='BTCUSDT')",
      "required_params": ["category", "symbol"]
    },
    "get_tickers": {
      "purpose": "Get 24h price statistics and current prices",
      "code": "session.get_tickers(category='linear', symbol='BTCUSDT')",
      "required_params": ["category"]
    },
    "get_kline": {
      "purpose": "Historical price data for volatility analysis",
      "code": "session.get_kline(category='linear', symbol='BTCUSDT', interval='1h')",
      "required_params": ["category", "symbol", "interval"]
    },
    "get_instruments_info": {
      "purpose": "Get trading pair specifications (min order size, tick size)",
      "code": "session.get_instruments_info(category='linear')",
      "required_params": ["category"]
    }
  }
}
``` [3](#0-2) [4](#0-3) [5](#0-4) 

### 2. Order Management Functions

Core trading operations for market making: [6](#0-5) 

```json
{
  "order_management_functions": {
    "place_order": {
      "purpose": "Place buy/sell limit orders",
      "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')",
      "required_params": ["category", "symbol", "side", "orderType", "qty"],
      "optional_params": ["price", "timeInForce", "orderLinkId"]
    },
    "amend_order": {
      "purpose": "Modify existing orders (price/quantity)",
      "code": "session.amend_order(category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')",
      "required_params": ["category", "symbol", "orderId or orderLinkId"]
    },
    "cancel_order": {
      "purpose": "Cancel specific orders",
      "code": "session.cancel_order(category='linear', symbol='BTCUSDT', orderId='order_id')",
      "required_params": ["category", "symbol", "orderId or orderLinkId"]
    },
    "cancel_all_orders": {
      "purpose": "Cancel all orders for risk management",
      "code": "session.cancel_all_orders(category='linear', symbol='BTCUSDT')",
      "required_params": ["category"]
    },
    "get_open_orders": {
      "purpose": "Monitor active orders",
      "code": "session.get_open_orders(category='linear', symbol='BTCUSDT')",
      "required_params": ["category"]
    }
  }
}
``` [7](#0-6) [8](#0-7) [9](#0-8) 

### 3. Position Management Functions

Monitor and manage positions: [10](#0-9) 

```json
{
  "position_management_functions": {
    "get_positions": {
      "purpose": "Monitor current positions and PnL",
      "code": "session.get_positions(category='linear', symbol='BTCUSDT')",
      "required_params": ["category"]
    },
    "set_leverage": {
      "purpose": "Adjust position leverage",
      "code": "session.set_leverage(category='linear', symbol='BTCUSDT', buyLeverage='10', sellLeverage='10')",
      "required_params": ["category", "symbol", "buyLeverage", "sellLeverage"]
    },
    "set_trading_stop": {
      "purpose": "Set stop loss/take profit",
      "code": "session.set_trading_stop(category='linear', symbol='BTCUSDT', stopLoss='49000', takeProfit='51000')",
      "required_params": ["category", "symbol"]
    }
  }
}
```

### 4. Account Management Functions

Risk management and balance monitoring: [11](#0-10) 

```json
{
  "account_management_functions": {
    "get_wallet_balance": {
      "purpose": "Monitor available balance",
      "code": "session.get_wallet_balance(accountType='UNIFIED')",
      "required_params": ["accountType"]
    },
    "set_mmp": {
      "purpose": "Market Maker Protection - auto risk management",
      "code": "session.set_mmp(baseCoin='BTC', window='5000', frozenPeriod='10000', qtyLimit='1.00', deltaLimit='0.50')",
      "required_params": ["baseCoin", "window", "frozenPeriod", "qtyLimit", "deltaLimit"]
    },
    "reset_mmp": {
      "purpose": "Reset MMP after trigger",
      "code": "session.reset_mmp(baseCoin='BTC')",
      "required_params": ["baseCoin"]
    }
  }
}
``` [12](#0-11) 

### 5. WebSocket Streams

Real-time data for responsive market making: [13](#0-12) 

```json
{
  "websocket_streams": {
    "orderbook_stream": {
      "purpose": "Real-time order book updates",
      "code": "ws.orderbook_stream(depth=50, symbol='BTCUSDT', callback=handle_orderbook)",
      "frequency": "10-100ms depending on depth"
    },
    "ticker_stream": {
      "purpose": "Real-time price updates",
      "code": "ws.ticker_stream(symbol='BTCUSDT', callback=handle_ticker)",
      "frequency": "100ms"
    },
    "trade_stream": {
      "purpose": "Real-time trade executions",
      "code": "ws.trade_stream(symbol='BTCUSDT', callback=handle_trades)",
      "frequency": "real-time"
    },
    "position_stream": {
      "purpose": "Real-time position updates",
      "code": "ws.position_stream(callback=handle_position)",
      "frequency": "real-time"
    },
    "order_stream": {
      "purpose": "Real-time order status updates",
      "code": "ws.order_stream(callback=handle_orders)",
      "frequency": "real-time"
    },
    "execution_stream": {
      "purpose": "Real-time execution notifications",
      "code": "ws.execution_stream(callback=handle_executions)",
      "frequency": "real-time"
    }
  }
}
``` [14](#0-13) [15](#0-14) [16](#0-15) [17](#0-16) [18](#0-17) 

### 6. WebSocket Trading Operations

For high-frequency order management: [19](#0-18) 

```json
{
  "websocket_trading_functions": {
    "place_order": {
      "purpose": "Place orders via WebSocket (faster)",
      "code": "ws_trading.place_order(callback=handle_order_response, category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')"
    },
    "amend_order": {
      "purpose": "Modify orders via WebSocket",
      "code": "ws_trading.amend_order(callback=handle_amend_response, category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')"
    },
    "cancel_order": {
      "purpose": "Cancel orders via WebSocket",
      "code": "ws_trading.cancel_order(callback=handle_cancel_response, category='linear', symbol='BTCUSDT', orderId='order_id')"
    }
  }
}
```

### Complete Implementation Example

```json
{
  "market_making_bot_implementation": {
    "initialization": {
      "http_client": "from pybit.unified_trading import HTTP\nsession = HTTP(testnet=True, api_key='key', api_secret='secret')",
      "websocket_client": "from pybit.unified_trading import WebSocket\nws = WebSocket(channel_type='private', testnet=True, api_key='key', api_secret='secret')",
      "websocket_trading": "from pybit.unified_trading import WebSocketTrading\nws_trading = WebSocketTrading(testnet=True, api_key='key', api_secret='secret')"
    },
    "core_loop_functions": [
      "get_orderbook() - for spread calculation",
      "get_positions() - for risk management", 
      "place_order() - for bid/ask placement",
      "amend_order() - for price updates",
      "cancel_all_orders() - for emergency stops"
    ],
    "risk_management": [
      "set_mmp() - automated protection",
      "get_wallet_balance() - balance monitoring",
      "set_trading_stop() - stop loss/take profit"
    ]
  }
}
```

## Notes

This tutorial covers all essential pybit functions for market making bots using the unified trading interface. [20](#0-19)  The functions are organized by purpose: market data for price discovery, order management for trading operations, position management for risk control, account management for balance monitoring, and WebSocket streams for real-time updates. [21](#0-20)  All endpoints use Bybit's v5 API through the unified interface, supporting spot, linear, inverse, and options markets depending on the specific function. [22](#0-21) 

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)
Looking at your request, you want a comprehensive JSON guide covering all HTTP, private, public, and hedge functions for market making in pybit. <cite/>

## Complete Market Maker Functions JSON Guide

This covers all HTTP endpoints, WebSocket streams (private/public), and hedge mode functions from the unified trading interface.

### HTTP Functions - Complete Reference

```json
{
  "http_functions": {
    "market_data_public": {
      "get_server_time": {
        "code": "session.get_server_time()",
        "auth_required": false,
        "endpoint": "/v5/market/time"
      },
      "get_orderbook": {
        "code": "session.get_orderbook(category='linear', symbol='BTCUSDT')",
        "auth_required": false,
        "endpoint": "/v5/market/orderbook",
        "required_params": ["category", "symbol"]
      },
      "get_tickers": {
        "code": "session.get_tickers(category='linear')",
        "auth_required": false,
        "endpoint": "/v5/market/tickers",
        "required_params": ["category"]
      },
      "get_instruments_info": {
        "code": "session.get_instruments_info(category='linear')",
        "auth_required": false,
        "endpoint": "/v5/market/instruments-info",
        "required_params": ["category"]
      },
      "get_kline": {
        "code": "session.get_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_funding_rate_history": {
        "code": "session.get_funding_rate_history(category='linear', symbol='BTCUSDT')",
        "auth_required": false,
        "endpoint": "/v5/market/funding/history",
        "required_params": ["category", "symbol"]
      },
      "get_public_trade_history": {
        "code": "session.get_public_trade_history(category='linear', symbol='BTCUSDT')",
        "auth_required": false,
        "endpoint": "/v5/market/recent-trade",
        "required_params": ["category", "symbol"]
      },
      "get_open_interest": {
        "code": "session.get_open_interest(category='linear', symbol='BTCUSDT', intervalTime='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/open-interest",
        "required_params": ["category", "symbol", "intervalTime"]
      },
      "get_long_short_ratio": {
        "code": "session.get_long_short_ratio(category='linear', symbol='BTCUSDT')",
        "auth_required": false,
        "endpoint": "/v5/market/account-ratio",
        "required_params": ["category", "symbol"]
      }
    }
  }
}
``` [1](#1-0) 

### Private HTTP Functions - Account & Trading

```json
{
  "private_http_functions": {
    "account_management": {
      "get_wallet_balance": {
        "code": "session.get_wallet_balance(accountType='UNIFIED')",
        "auth_required": true,
        "endpoint": "/v5/account/wallet-balance",
        "required_params": ["accountType"]
      },
      "set_mmp": {
        "code": "session.set_mmp(baseCoin='BTC', window='5000', frozenPeriod='10000', qtyLimit='1.00', deltaLimit='0.50')",
        "auth_required": true,
        "endpoint": "/v5/account/mmp-modify",
        "required_params": ["baseCoin", "window", "frozenPeriod", "qtyLimit", "deltaLimit"]
      },
      "reset_mmp": {
        "code": "session.reset_mmp(baseCoin='BTC')",
        "auth_required": true,
        "endpoint": "/v5/account/reset-mmp",
        "required_params": ["baseCoin"]
      },
      "get_mmp_state": {
        "code": "session.get_mmp_state(baseCoin='BTC')",
        "auth_required": true,
        "endpoint": "/v5/account/get-mmp-state",
        "required_params": ["baseCoin"]
      },
      "set_margin_mode": {
        "code": "session.set_margin_mode(setMarginMode='PORTFOLIO_MARGIN')",
        "auth_required": true,
        "endpoint": "/v5/account/set-margin-mode",
        "required_params": ["setMarginMode"]
      }
    }
  }
}
``` [2](#1-1) 

### Position Management - Including Hedge Mode

```json
{
  "position_management_private": {
    "get_positions": {
      "code": "session.get_positions(category='linear', symbol='BTCUSDT')",
      "auth_required": true,
      "endpoint": "/v5/position/list",
      "required_params": ["category"]
    },
    "set_leverage": {
      "code": "session.set_leverage(category='linear', symbol='BTCUSDT', buyLeverage='10', sellLeverage='10')",
      "auth_required": true,
      "endpoint": "/v5/position/set-leverage",
      "required_params": ["category", "symbol", "buyLeverage", "sellLeverage"]
    },
    "switch_position_mode": {
      "code": "session.switch_position_mode(category='linear', mode='3')",
      "auth_required": true,
      "endpoint": "/v5/position/switch-mode",
      "required_params": ["category"],
      "hedge_mode_support": true,
      "modes": {
        "0": "one_way_mode",
        "3": "hedge_mode"
      }
    },
    "set_risk_limit": {
      "code": "session.set_risk_limit(category='linear', symbol='BTCUSDT', riskId=1)",
      "auth_required": true,
      "endpoint": "/v5/position/set-risk-limit",
      "required_params": ["category", "symbol", "riskId"]
    },
    "set_trading_stop": {
      "code": "session.set_trading_stop(category='linear', symbol='BTCUSDT', stopLoss='49000', takeProfit='51000')",
      "auth_required": true,
      "endpoint": "/v5/position/trading-stop",
      "required_params": ["category", "symbol"]
    }
  }
}
``` [3](#1-2) 

### WebSocket Public Streams

```json
{
  "websocket_public_streams": {
    "initialization": {
      "linear": "ws = WebSocket(channel_type='linear', testnet=True)",
      "spot": "ws = WebSocket(channel_type='spot', testnet=True)",
      "inverse": "ws = WebSocket(channel_type='inverse', testnet=True)",
      "option": "ws = WebSocket(channel_type='option', testnet=True)"
    },
    "public_streams": {
      "orderbook_stream": {
        "code": "ws.orderbook_stream(depth=50, symbol='BTCUSDT', callback=handle_orderbook)",
        "frequency": "10-100ms",
        "auth_required": false
      },
      "ticker_stream": {
        "code": "ws.ticker_stream(symbol='BTCUSDT', callback=handle_ticker)",
        "frequency": "100ms",
        "auth_required": false
      },
      "trade_stream": {
        "code": "ws.trade_stream(symbol='BTCUSDT', callback=handle_trades)",
        "frequency": "real-time",
        "auth_required": false
      },
      "kline_stream": {
        "code": "ws.kline_stream(interval='1m', symbol='BTCUSDT', callback=handle_kline)",
        "frequency": "real-time",
        "auth_required": false
      }
    }
  }
}
``` [4](#1-3) 

### WebSocket Private Streams

```json
{
  "websocket_private_streams": {
    "initialization": {
      "private": "ws = WebSocket(channel_type='private', testnet=True, api_key='key', api_secret='secret')"
    },
    "private_streams": {
      "position_stream": {
        "code": "ws.position_stream(callback=handle_position)",
        "frequency": "real-time",
        "auth_required": true,
        "hedge_mode_support": true
      },
      "order_stream": {
        "code": "ws.order_stream(callback=handle_orders)",
        "frequency": "real-time",
        "auth_required": true
      },
      "execution_stream": {
        "code": "ws.execution_stream(callback=handle_executions)",
        "frequency": "real-time",
        "auth_required": true
      },
      "wallet_stream": {
        "code": "ws.wallet_stream(callback=handle_wallet)",
        "frequency": "real-time",
        "auth_required": true
      }
    }
  }
}
``` [5](#1-4) 

### WebSocket Trading Operations

```json
{
  "websocket_trading_private": {
    "initialization": {
      "trading_ws": "ws_trading = WebSocketTrading(testnet=True, api_key='key', api_secret='secret')"
    },
    "trading_operations": {
      "place_order": {
        "code": "ws_trading.place_order(callback=handle_response, category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')",
        "auth_required": true,
        "hedge_mode_support": true
      },
      "amend_order": {
        "code": "ws_trading.amend_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')",
        "auth_required": true
      },
      "cancel_order": {
        "code": "ws_trading.cancel_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id')",
        "auth_required": true
      },
      "place_batch_order": {
        "code": "ws_trading.place_batch_order(callback=handle_response, category='linear', request=[{order1}, {order2}])",
        "auth_required": true,
        "hedge_mode_support": true
      },
      "cancel_batch_order": {
        "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{cancel1}, {cancel2}])",
        "auth_required": true
      }
    }
  }
}
``` [6](#1-5) 

### Hedge Mode Specific Functions

```json
{
  "hedge_mode_functions": {
    "position_mode_switch": {
      "enable_hedge_mode": {
        "code": "session.switch_position_mode(category='linear', mode='3')",
        "description": "Enable hedge mode - allows simultaneous Buy and Sell positions"
      },
      "disable_hedge_mode": {
        "code": "session.switch_position_mode(category='linear', mode='0')",
        "description": "Switch to one-way mode - only one position direction allowed"
      }
    },
    "hedge_position_management": {
      "get_both_positions": {
        "code": "session.get_positions(category='linear', symbol='BTCUSDT')",
        "description": "Returns both Buy and Sell positions when in hedge mode"
      },
      "set_leverage_both_sides": {
        "code": "session.set_leverage(category='linear', symbol='BTCUSDT', buyLeverage='10', sellLeverage='15')",
        "description": "Set different leverage for Buy and Sell sides in hedge mode"
      }
    },
    "hedge_order_placement": {
      "place_buy_hedge": {
        "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')",
        "description": "Place Buy order in hedge mode"
      },
      "place_sell_hedge": {
        "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Sell', orderType='Limit', qty='0.01', price='50200')",
        "description": "Place Sell order simultaneously in hedge mode"
      }
    }
  }
}
```

### Complete Market Maker Implementation

```json
{
  "complete_market_maker_setup": {
    "initialization": {
      "http_client": "from pybit.unified_trading import HTTP\nsession = HTTP(testnet=True, api_key='key', api_secret='secret')",
      "public_ws": "ws_public = WebSocket(channel_type='linear', testnet=True)",
      "private_ws": "ws_private = WebSocket(channel_type='private', testnet=True, api_key='key', api_secret='secret')",
      "trading_ws": "ws_trading = WebSocketTrading(testnet=True, api_key='key', api_secret='secret')"
    },
    "essential_functions": {
      "public_data": ["get_orderbook", "get_tickers", "get_instruments_info"],
      "private_account": ["get_wallet_balance", "set_mmp", "reset_mmp"],
      "position_mgmt": ["get_positions", "set_leverage", "switch_position_mode"],
      "order_mgmt": ["place_order", "amend_order", "cancel_order", "cancel_all_orders"],
      "websocket_streams": ["orderbook_stream", "position_stream", "order_stream", "execution_stream"],
      "websocket_trading": ["place_order", "amend_order", "cancel_order"]
    },
    "hedge_mode_support": {
      "enabled": true,
      "functions": ["switch_position_mode", "get_positions", "set_leverage", "place_order"]
    }
  }
}
```

## Notes

This comprehensive JSON guide covers all HTTP endpoints (public/private), WebSocket streams (public/private), and hedge mode functions available in pybit for market making. <cite/> The unified trading interface supports all major product categories (spot, linear, inverse, option) with consistent API patterns. <cite/> Market Maker Protection (MMP) functions provide automated risk management specifically designed for high-frequency market making operations. <cite/> Hedge mode allows simultaneous Buy and Sell positions, essential for advanced market making strategies. <cite/>

Wiki pages you might want to explore:
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)
- [Account Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.2)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
