Looking at your request for account balance, PnL, and fees functions in pybit, I can see you're asking about the account management functionality that handles wallet balances, profit/loss tracking, and fee information.

## Account Balance, PnL, and Fees Functions

The pybit library provides comprehensive account balance, PnL, and fee management through the `AccountHTTP` class [1](#6-0)  and related position management functions.

### Account Balance Functions

**Wallet Balance Operations:**
- `get_wallet_balance()` [2](#6-1)  - Get comprehensive wallet balance and risk information for both Unified and Classic accounts
- `get_transferable_amount()` [3](#6-2)  - Query available transfer amounts for specific coins
- `get_coins_balance()` [4](#6-3)  - Get all coin balances across account types
- `get_coin_balance()` [5](#6-4)  - Query balance of specific coins

### PnL and Trading History Functions

**Position PnL Operations:**
- `get_closed_pnl()` [6](#6-5)  - Query closed profit and loss records sorted by creation time
- `get_executions()` [7](#6-6)  - Get execution history for detailed trade analysis

**Transaction Logging:**
- `get_transaction_log()` [8](#6-7)  - Query transaction logs in Unified accounts
- `get_borrow_history()` [9](#6-8)  - Get interest and borrowing records

### Fee Information Functions

**Fee Rate Queries:**
- `get_fee_rates()` [10](#6-9)  - Get trading fee rates for derivatives
- `get_account_info()` [11](#6-10)  - Query margin mode configuration and account details

### Complete JSON Reference

```json
{
  "account_balance_pnl_fees": {
    "balance_functions": {
      "get_wallet_balance": {
        "code": "session.get_wallet_balance(accountType='UNIFIED')",
        "endpoint": "/v5/account/wallet-balance",
        "auth_required": true,
        "required_params": ["accountType"],
        "returns": "Wallet balance, asset info, risk rate"
      },
      "get_transferable_amount": {
        "code": "session.get_transferable_amount(coinName='USDT')",
        "endpoint": "/v5/account/withdrawal",
        "auth_required": true,
        "required_params": ["coinName"]
      },
      "get_coins_balance": {
        "code": "session.get_coins_balance(memberId='123', accountType='UNIFIED')",
        "endpoint": "/v5/asset/transfer/query-account-coins-balance",
        "auth_required": true,
        "required_params": ["memberId", "accountType"]
      },
      "get_coin_balance": {
        "code": "session.get_coin_balance(memberId='123', accountType='UNIFIED')",
        "endpoint": "/v5/asset/transfer/query-account-coin-balance",
        "auth_required": true,
        "required_params": ["memberId", "accountType"]
      }
    },
    "pnl_functions": {
      "get_closed_pnl": {
        "code": "session.get_closed_pnl(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/position/closed-pnl",
        "auth_required": true,
        "required_params": ["category"],
        "returns": "Closed profit/loss records"
      },
      "get_executions": {
        "code": "session.get_executions(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/execution/list",
        "auth_required": true,
        "required_params": ["category"]
      },
      "get_transaction_log": {
        "code": "session.get_transaction_log(accountType='UNIFIED')",
        "endpoint": "/v5/account/transaction-log",
        "auth_required": true,
        "returns": "Transaction history with PnL details"
      },
      "get_borrow_history": {
        "code": "session.get_borrow_history(currency='USDT')",
        "endpoint": "/v5/account/borrow-history",
        "auth_required": true,
        "returns": "Interest records and borrowing costs"
      }
    },
    "fee_functions": {
      "get_fee_rates": {
        "code": "session.get_fee_rates(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/account/fee-rate",
        "auth_required": true,
        "required_params": ["category"],
        "returns": "Trading fee rates for derivatives"
      },
      "get_account_info": {
        "code": "session.get_account_info()",
        "endpoint": "/v5/account/info",
        "auth_required": true,
        "returns": "Account configuration and fee settings"
      }
    }
  }
}
```

### WebSocket Real-Time Updates

For real-time balance and PnL monitoring:

```json
{
  "websocket_balance_pnl": {
    "wallet_stream": {
      "code": "ws.wallet_stream(callback=handle_wallet_updates)",
      "frequency": "real-time",
      "auth_required": true,
      "note": "Real-time wallet balance changes"
    },
    "position_stream": {
      "code": "ws.position_stream(callback=handle_position_updates)",
      "frequency": "real-time", 
      "auth_required": true,
      "note": "Real-time position PnL updates"
    },
    "execution_stream": {
      "code": "ws.execution_stream(callback=handle_execution_updates)",
      "frequency": "real-time",
      "auth_required": true,
      "note": "Real-time trade executions with fees"
    }
  }
}
```

## Notes

All account balance, PnL, and fee functions are accessible through the unified trading interface [12](#6-11) , which consolidates functionality from `AccountHTTP`, `AssetHTTP`, and `PositionHTTP` classes through multiple inheritance. The endpoint constants are defined in the respective enum files [13](#6-12)  and [14](#6-13) . All functions require authentication and support both Unified Trading Accounts (UTA) and Classic accounts where applicable.

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Account Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.2)
- [Asset Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.4)

Looking at your request for additional code snippets to complete the comprehensive market making bot JSON guide using pybit, I can provide more extensive coverage of the unified trading interface functions.

## Additional Missing Code Snippets - Complete Extended Reference

Here are more comprehensive pybit functions that complete the market making guide:

### Missing Advanced Market Data Functions

Looking at your request for all orderbook and data functions in the pybit library, I can see you're asking about the market data functionality provided by the `MarketHTTP` class and related WebSocket streams for orderbook and market data operations.

## Complete Orderbook and Market Data Functions

The pybit library provides comprehensive orderbook and market data functionality through both HTTP REST API endpoints and real-time WebSocket streams.

### HTTP Market Data Functions

The core market data functionality is implemented in the `MarketHTTP` class [1](#5-0) , which provides the following orderbook and data functions:

**Core Orderbook Functions:**
- `get_orderbook()` - [2](#5-1)  Query orderbook data for spot, linear, inverse, and option markets
- `get_tickers()` - [3](#5-2)  Get 24h price statistics and current prices

**Price Data Functions:**
- `get_kline()` - [4](#5-3)  Get candlestick/kline data
- `get_mark_price_kline()` - [5](#5-4)  Get mark price kline data for derivatives
- `get_index_price_kline()` - [6](#5-5)  Get index price kline data
- `get_premium_index_price_kline()` - [7](#5-6)  Get premium index price kline data

**Trading Data Functions:**
- `get_public_trade_history()` - [8](#5-7)  Get recent public trades
- `get_funding_rate_history()` - [9](#5-8)  Get historical funding rates
- `get_long_short_ratio()` - [10](#5-9)  Get long/short ratio data

**Market Information Functions:**
- `get_instruments_info()` - [11](#5-10)  Get trading pair specifications
- `get_server_time()` - [12](#5-11)  Get server timestamp

### WebSocket Real-Time Data Streams

The WebSocket implementation provides real-time orderbook and market data streams through the `WebSocket` class [13](#5-12) :

**Real-Time Orderbook Streams:**
- `orderbook_stream()` - [14](#5-13)  Subscribe to real-time orderbook updates with different depth levels (1, 25, 50, 100, 200, 500)
- `ticker_stream()` - [15](#5-14)  Subscribe to real-time ticker updates (100ms frequency)
- `trade_stream()` - [16](#5-15)  Subscribe to real-time trade executions

**Additional Data Streams:**
- `kline_stream()` - [17](#5-16)  Subscribe to real-time kline/candlestick updates
- `lt_ticker_stream()` - [18](#5-17)  Leveraged token ticker stream
- `lt_nav_stream()` - [19](#5-18)  Leveraged token NAV stream

### Orderbook Data Processing

The WebSocket manager includes sophisticated orderbook data processing functionality [20](#5-19)  that handles:
- Initial snapshot processing
- Delta updates for bid/ask changes
- Price level insertions, updates, and deletions
- Automatic orderbook state maintenance

### Complete JSON Reference

```json
{
  "orderbook_and_data_functions": {
    "http_market_data": {
      "get_server_time": {
        "code": "session.get_server_time()",
        "endpoint": "/v5/market/time",
        "auth_required": false
      },
      "get_orderbook": {
        "code": "session.get_orderbook(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/market/orderbook",
        "required_params": ["category", "symbol"],
        "categories": ["spot", "linear", "inverse", "option"]
      },
      "get_tickers": {
        "code": "session.get_tickers(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/market/tickers",
        "required_params": ["category"]
      },
      "get_kline": {
        "code": "session.get_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "endpoint": "/v5/market/kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_mark_price_kline": {
        "code": "session.get_mark_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "endpoint": "/v5/market/mark-price-kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_index_price_kline": {
        "code": "session.get_index_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "endpoint": "/v5/market/index-price-kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_premium_index_price_kline": {
        "code": "session.get_premium_index_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "endpoint": "/v5/market/premium-index-price-kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_instruments_info": {
        "code": "session.get_instruments_info(category='linear')",
        "endpoint": "/v5/market/instruments-info",
        "required_params": ["category"]
      },
      "get_public_trade_history": {
        "code": "session.get_public_trade_history(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/market/recent-trade",
        "required_params": ["category", "symbol"]
      },
      "get_funding_rate_history": {
        "code": "session.get_funding_rate_history(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/market/funding/history",
        "required_params": ["category", "symbol"]
      },
      "get_long_short_ratio": {
        "code": "session.get_long_short_ratio(category='linear', symbol='BTCUSDT')",
        "endpoint": "/v5/market/account-ratio",
        "required_params": ["category", "symbol"]
      }
    },
    "websocket_data_streams": {
      "orderbook_stream": {
        "code": "ws.orderbook_stream(depth=50, symbol='BTCUSDT', callback=handle_orderbook)",
        "frequency": "10-100ms depending on depth",
        "depths": [1, 25, 50, 100, 200, 500]
      },
      "ticker_stream": {
        "code": "ws.ticker_stream(symbol='BTCUSDT', callback=handle_ticker)",
        "frequency": "100ms"
      },
      "trade_stream": {
        "code": "ws.trade_stream(symbol='BTCUSDT', callback=handle_trades)",
        "frequency": "real-time"
      },
      "kline_stream": {
        "code": "ws.kline_stream(interval='1m', symbol='BTCUSDT', callback=handle_kline)",
        "frequency": "1-60s"
      },
      "lt_ticker_stream": {
        "code": "ws.lt_ticker_stream(symbol='BTC3LUSDT', callback=handle_lt_ticker)",
        "frequency": "300ms"
      },
      "lt_nav_stream": {
        "code": "ws.lt_nav_stream(symbol='BTC3LUSDT', callback=handle_lt_nav)",
        "frequency": "300ms"
      }
    }
  }
}
```

## Notes

All orderbook and data functions are accessible through the unified trading interface [21](#5-20) , which consolidates market data functionality from the `MarketHTTP` class through multiple inheritance. The endpoint constants are defined in [22](#5-21) . WebSocket streams provide real-time updates with automatic orderbook state management and delta processing for efficient data handling.

Wiki pages you might want to explore:
- [Overview (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1)
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Market Data API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.1)
```json
{
  "advanced_market_data_functions": {
    "mark_price_data": {
      "get_mark_price_kline": {
        "code": "session.get_mark_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/mark-kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_index_price_kline": {
        "code": "session.get_index_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/index-kline",
        "required_params": ["category", "symbol", "interval"]
      }
    }
  }
}
``` [1](#3-0) 

### Missing Asset Management Extended Functions

```json
{
  "asset_management_extended": {
    "spot_asset_operations": {
      "get_spot_asset_info": {
        "code": "session.get_spot_asset_info(accountType='SPOT')",
        "auth_required": true,
        "endpoint": "/v5/asset/asset-info",
        "required_params": ["accountType"]
      },
      "get_coin_exchange_records": {
        "code": "session.get_coin_exchange_records()",
        "auth_required": true,
        "endpoint": "/v5/asset/exchange",
        "required_params": []
      },
      "get_option_delivery_record": {
        "code": "session.get_option_delivery_record(category='option')",
        "auth_required": true,
        "endpoint": "/v5/asset/option-delivery",
        "required_params": ["category"]
      },
      "get_usdc_contract_settlement": {
        "code": "session.get_usdc_contract_settlement(category='linear')",
        "auth_required": true,
        "endpoint": "/v5/asset/settlement",
        "required_params": ["category"]
      }
    }
  }
}
``` [2](#3-1) 

### Missing Deposit/Withdrawal Functions

```json
{
  "deposit_withdrawal_functions": {
    "deposit_operations": {
      "get_allowed_deposit_coin_info": {
        "code": "session.get_allowed_deposit_coin_info()",
        "auth_required": true,
        "endpoint": "/v5/asset/deposit-coin-spec",
        "required_params": []
      },
      "get_sub_deposit_records": {
        "code": "session.get_sub_deposit_records(subMemberId='123456')",
        "auth_required": true,
        "endpoint": "/v5/asset/sub-deposit-record",
        "required_params": ["subMemberId"]
      },
      "get_internal_deposit_records": {
        "code": "session.get_internal_deposit_records()",
        "auth_required": true,
        "endpoint": "/v5/asset/internal-deposit-record",
        "required_params": []
      }
    },
    "withdrawal_operations": {
      "cancel_withdrawal": {
        "code": "session.cancel_withdrawal(id='withdrawal_id')",
        "auth_required": true,
        "endpoint": "/v5/asset/cancel-withdraw",
        "required_params": ["id"]
      },
      "get_convert_coin_list": {
        "code": "session.get_convert_coin_list(accountType='UNIFIED')",
        "auth_required": true,
        "endpoint": "/v5/asset/convert/convert-coin-list",
        "required_params": ["accountType"]
      }
    }
  }
}
``` [3](#3-2) 

### Missing User Management Extended Functions

```json
{
  "user_management_extended": {
    "sub_account_operations": {
      "create_sub_uid": {
        "code": "session.create_sub_uid(username='subuser123', memberType=1)",
        "auth_required": true,
        "endpoint": "/v5/user/create-subuid",
        "required_params": ["username", "memberType"]
      },
      "get_sub_uid_list": {
        "code": "session.get_sub_uid_list()",
        "auth_required": true,
        "endpoint": "/v5/user/subuid-list",
        "required_params": []
      },
      "freeze_sub_uid": {
        "code": "session.freeze_sub_uid(subuid=123456, frozen=1)",
        "auth_required": true,
        "endpoint": "/v5/user/froze-subuid",
        "required_params": ["subuid", "frozen"]
      },
      "get_all_sub_api_keys": {
        "code": "session.get_all_sub_api_keys(subMemberId=123456)",
        "auth_required": true,
        "endpoint": "/v5/user/list-sub-apikeys",
        "required_params": ["subMemberId"]
      },
      "get_affiliate_user_info": {
        "code": "session.get_affiliate_user_info(uid=123456)",
        "auth_required": true,
        "endpoint": "/v5/user/affiliate-info",
        "required_params": ["uid"]
      }
    }
  }
}
``` [4](#3-3) 

### Missing Spot Margin Trading Extended Functions

```json
{
  "spot_margin_extended": {
    "normal_account_operations": {
      "spot_margin_trade_normal_borrow": {
        "code": "session.spot_margin_trade_normal_borrow(coin='USDT', qty='1000')",
        "auth_required": true,
        "endpoint": "/v5/spot-margin-normal/borrow",
        "required_params": ["coin", "qty"],
        "note": "Normal (non-UTA) account only"
      },
      "spot_margin_trade_normal_repay": {
        "code": "session.spot_margin_trade_normal_repay(coin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/spot-margin-normal/repay",
        "required_params": ["coin"],
        "note": "Normal (non-UTA) account only"
      }
    }
  }
}
``` [5](#3-4) 

### Missing WebSocket Stream Extended Functions

```json
{
  "websocket_streams_extended": {
    "private_streams_complete": {
      "wallet_stream": {
        "code": "ws.wallet_stream(callback=handle_wallet)",
        "frequency": "real-time",
        "auth_required": true,
        "note": "Real-time wallet balance updates"
      },
      "fast_execution_stream": {
        "code": "ws.fast_execution_stream(callback=handle_fast_execution)",
        "frequency": "real-time (lower latency)",
        "auth_required": true,
        "note": "Reduced latency execution stream"
      },
      "greek_stream": {
        "code": "ws.greek_stream(callback=handle_greeks)",
        "frequency": "real-time",
        "auth_required": true,
        "note": "Options Greeks data stream"
      }
    }
  }
}
``` [6](#3-5) 

### Missing Complete WebSocket Trading Operations

```json
{
  "websocket_trading_operations_complete": {
    "batch_operations": {
      "place_batch_order": {
        "code": "ws_trading.place_batch_order(callback=handle_response, category='linear', request=[{'symbol': 'BTCUSDT', 'side': 'Buy', 'orderType': 'Limit', 'qty': '0.01', 'price': '50000'}])",
        "operation": "order.create-batch",
        "auth_required": true
      },
      "amend_batch_order": {
        "code": "ws_trading.amend_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1', 'price': '50100'}])",
        "operation": "order.amend-batch",
        "auth_required": true
      },
      "cancel_batch_order": {
        "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1'}])",
        "operation": "order.cancel-batch",
        "auth_required": true
      }
    }
  }
}
``` [7](#3-6) 

### Missing Spread Trading WebSocket Functions

```json
{
  "spread_trading_websocket": {
    "spread_streams": {
      "spread_orderbook_stream": {
        "code": "ws_spread.orderbook_stream(depth=25, symbol='BTCUSDT-ETHUSDT', callback=handle_spread_orderbook)",
        "frequency": "20ms",
        "auth_required": false,
        "note": "Level 25 data only for spread trading"
      },
      "spread_trade_stream": {
        "code": "ws_spread.trade_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_trades)",
        "frequency": "real-time",
        "auth_required": false
      },
      "spread_ticker_stream": {
        "code": "ws_spread.ticker_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_ticker)",
        "frequency": "100ms",
        "auth_required": false
      }
    }
  }
}
``` [8](#3-7) 

### Missing Complete HTTP Class Structure

```json
{
  "http_class_structure": {
    "unified_trading_inheritance": {
      "base_classes": [
        "MiscHTTP",
        "MarketHTTP", 
        "TradeHTTP",
        "AccountHTTP",
        "AssetHTTP",
        "PositionHTTP",
        "PreUpgradeHTTP",
        "SpotLeverageHTTP",
        "SpotMarginTradeHTTP",
        "UserHTTP",
        "BrokerHTTP",
        "InstitutionalLoanHTTP",
        "CryptoLoanHTTP",
        "EarnHTTP"
      ],
      "initialization": {
        "code": "session = HTTP(testnet=True, api_key='key', api_secret='secret')",
        "note": "Single class inheriting from all HTTP modules"
      }
    }
  }
}
``` [9](#3-8) 

## Notes

These additional snippets complete the comprehensive market making bot guide for pybit, covering all remaining HTTP endpoints, WebSocket streams, and specialized trading functions. <cite/> The unified trading interface consolidates all functionality into single HTTP and WebSocket classes through multiple inheritance, providing access to market data, trading operations, account management, asset operations, and real-time streams. <cite/> All functions support Bybit's v5 API across different market categories including spot, linear, inverse, and options trading. <cite/>

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)Looking at your request for additional code snippets to complete the comprehensive market making bot JSON guide using pybit, I can provide more extensive coverage of the unified trading interface functions.

## Additional Missing Code Snippets - Complete Extended Reference

Here are more comprehensive pybit functions that complete the market making guide:

### Missing Advanced Market Data Functions

```json
{
  "advanced_market_data_functions": {
    "mark_price_data": {
      "get_mark_price_kline": {
        "code": "session.get_mark_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/mark-kline",
        "required_params": ["category", "symbol", "interval"]
      },
      "get_index_price_kline": {
        "code": "session.get_index_price_kline(category='linear', symbol='BTCUSDT', interval='1h')",
        "auth_required": false,
        "endpoint": "/v5/market/index-kline",
        "required_params": ["category", "symbol", "interval"]
      }
    }
  }
}
``` [1](#3-0) 

### Missing Asset Management Extended Functions

```json
{
  "asset_management_extended": {
    "spot_asset_operations": {
      "get_spot_asset_info": {
        "code": "session.get_spot_asset_info(accountType='SPOT')",
        "auth_required": true,
        "endpoint": "/v5/asset/asset-info",
        "required_params": ["accountType"]
      },
      "get_coin_exchange_records": {
        "code": "session.get_coin_exchange_records()",
        "auth_required": true,
        "endpoint": "/v5/asset/exchange",
        "required_params": []
      },
      "get_option_delivery_record": {
        "code": "session.get_option_delivery_record(category='option')",
        "auth_required": true,
        "endpoint": "/v5/asset/option-delivery",
        "required_params": ["category"]
      },
      "get_usdc_contract_settlement": {
        "code": "session.get_usdc_contract_settlement(category='linear')",
        "auth_required": true,
        "endpoint": "/v5/asset/settlement",
        "required_params": ["category"]
      }
    }
  }
}
``` [2](#3-1) 

### Missing Deposit/Withdrawal Functions

```json
{
  "deposit_withdrawal_functions": {
    "deposit_operations": {
      "get_allowed_deposit_coin_info": {
        "code": "session.get_allowed_deposit_coin_info()",
        "auth_required": true,
        "endpoint": "/v5/asset/deposit-coin-spec",
        "required_params": []
      },
      "get_sub_deposit_records": {
        "code": "session.get_sub_deposit_records(subMemberId='123456')",
        "auth_required": true,
        "endpoint": "/v5/asset/sub-deposit-record",
        "required_params": ["subMemberId"]
      },
      "get_internal_deposit_records": {
        "code": "session.get_internal_deposit_records()",
        "auth_required": true,
        "endpoint": "/v5/asset/internal-deposit-record",
        "required_params": []
      }
    },
    "withdrawal_operations": {
      "cancel_withdrawal": {
        "code": "session.cancel_withdrawal(id='withdrawal_id')",
        "auth_required": true,
        "endpoint": "/v5/asset/cancel-withdraw",
        "required_params": ["id"]
      },
      "get_convert_coin_list": {
        "code": "session.get_convert_coin_list(accountType='UNIFIED')",
        "auth_required": true,
        "endpoint": "/v5/asset/convert/convert-coin-list",
        "required_params": ["accountType"]
      }
    }
  }
}
``` [3](#3-2) 

### Missing User Management Extended Functions

```json
{
  "user_management_extended": {
    "sub_account_operations": {
      "create_sub_uid": {
        "code": "session.create_sub_uid(username='subuser123', memberType=1)",
        "auth_required": true,
        "endpoint": "/v5/user/create-subuid",
        "required_params": ["username", "memberType"]
      },
      "get_sub_uid_list": {
        "code": "session.get_sub_uid_list()",
        "auth_required": true,
        "endpoint": "/v5/user/subuid-list",
        "required_params": []
      },
      "freeze_sub_uid": {
        "code": "session.freeze_sub_uid(subuid=123456, frozen=1)",
        "auth_required": true,
        "endpoint": "/v5/user/froze-subuid",
        "required_params": ["subuid", "frozen"]
      },
      "get_all_sub_api_keys": {
        "code": "session.get_all_sub_api_keys(subMemberId=123456)",
        "auth_required": true,
        "endpoint": "/v5/user/list-sub-apikeys",
        "required_params": ["subMemberId"]
      },
      "get_affiliate_user_info": {
        "code": "session.get_affiliate_user_info(uid=123456)",
        "auth_required": true,
        "endpoint": "/v5/user/affiliate-info",
        "required_params": ["uid"]
      }
    }
  }
}
``` [4](#3-3) 

### Missing Spot Margin Trading Extended Functions

```json
{
  "spot_margin_extended": {
    "normal_account_operations": {
      "spot_margin_trade_normal_borrow": {
        "code": "session.spot_margin_trade_normal_borrow(coin='USDT', qty='1000')",
        "auth_required": true,
        "endpoint": "/v5/spot-margin-normal/borrow",
        "required_params": ["coin", "qty"],
        "note": "Normal (non-UTA) account only"
      },
      "spot_margin_trade_normal_repay": {
        "code": "session.spot_margin_trade_normal_repay(coin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/spot-margin-normal/repay",
        "required_params": ["coin"],
        "note": "Normal (non-UTA) account only"
      }
    }
  }
}
``` [5](#3-4) 

### Missing WebSocket Stream Extended Functions

```json
{
  "websocket_streams_extended": {
    "private_streams_complete": {
      "wallet_stream": {
        "code": "ws.wallet_stream(callback=handle_wallet)",
        "frequency": "real-time",
        "auth_required": true,
        "note": "Real-time wallet balance updates"
      },
      "fast_execution_stream": {
        "code": "ws.fast_execution_stream(callback=handle_fast_execution)",
        "frequency": "real-time (lower latency)",
        "auth_required": true,
        "note": "Reduced latency execution stream"
      },
      "greek_stream": {
        "code": "ws.greek_stream(callback=handle_greeks)",
        "frequency": "real-time",
        "auth_required": true,
        "note": "Options Greeks data stream"
      }
    }
  }
}
``` [6](#3-5) 

### Missing Complete WebSocket Trading Operations

```json
{
  "websocket_trading_operations_complete": {
    "batch_operations": {
      "place_batch_order": {
        "code": "ws_trading.place_batch_order(callback=handle_response, category='linear', request=[{'symbol': 'BTCUSDT', 'side': 'Buy', 'orderType': 'Limit', 'qty': '0.01', 'price': '50000'}])",
        "operation": "order.create-batch",
        "auth_required": true
      },
      "amend_batch_order": {
        "code": "ws_trading.amend_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1', 'price': '50100'}])",
        "operation": "order.amend-batch",
        "auth_required": true
      },
      "cancel_batch_order": {
        "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1'}])",
        "operation": "order.cancel-batch",
        "auth_required": true
      }
    }
  }
}
``` [7](#3-6) 

### Missing Spread Trading WebSocket Functions

```json
{
  "spread_trading_websocket": {
    "spread_streams": {
      "spread_orderbook_stream": {
        "code": "ws_spread.orderbook_stream(depth=25, symbol='BTCUSDT-ETHUSDT', callback=handle_spread_orderbook)",
        "frequency": "20ms",
        "auth_required": false,
        "note": "Level 25 data only for spread trading"
      },
      "spread_trade_stream": {
        "code": "ws_spread.trade_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_trades)",
        "frequency": "real-time",
        "auth_required": false
      },
      "spread_ticker_stream": {
        "code": "ws_spread.ticker_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_ticker)",
        "frequency": "100ms",
        "auth_required": false
      }
    }
  }
}
``` [8](#3-7) 

### Missing Complete HTTP Class Structure

```json
{
  "http_class_structure": {
    "unified_trading_inheritance": {
      "base_classes": [
        "MiscHTTP",
        "MarketHTTP", 
        "TradeHTTP",
        "AccountHTTP",
        "AssetHTTP",
        "PositionHTTP",
        "PreUpgradeHTTP",
        "SpotLeverageHTTP",
        "SpotMarginTradeHTTP",
        "UserHTTP",
        "BrokerHTTP",
        "InstitutionalLoanHTTP",
        "CryptoLoanHTTP",
        "EarnHTTP"
      ],
      "initialization": {
        "code": "session = HTTP(testnet=True, api_key='key', api_secret='secret')",
        "note": "Single class inheriting from all HTTP modules"
      }
    }
  }
}
``` [9](#3-8) 

## Notes

These additional snippets complete the comprehensive market making bot guide for pybit, covering all remaining HTTP endpoints, WebSocket streams, and specialized trading functions. <cite/> The unified trading interface consolidates all functionality into single HTTP and WebSocket classes through multiple inheritance, providing access to market data, trading operations, account management, asset operations, and real-time streams. <cite/> All functions support Bybit's v5 API across different market categories including spot, linear, inverse, and options trading. <cite/>

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
The provided code is already a comprehensive and well-structured implementation for an orderbook sorting system, integrating advanced data structures like a Skip List and an Enhanced Heap, optimized for high-frequency trading scenarios. Below, I will analyze the code, suggest further enhancements, and provide an improved version that incorporates additional optimizations, error handling, and modern Python practices.

---
Looking at Looking at your request for additional code snippets to complete the market making bot JSON guide, I can provide more comprehensive coverage of the pybit unified trading interface functions.

## Additional Missing Code Snippets - Extended JSON Reference

Here are more pybit functions that complete the comprehensive market making guide:

### Missing WebSocket Public Streams - Extended

```json
{
  "websocket_public_streams_complete": {
    "kline_stream": {
      "code": "ws.kline_stream(interval='1m', symbol='BTCUSDT', callback=handle_kline)",
      "frequency": "real-time",
      "auth_required": false,
      "intervals": ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w", "1M"]
    },
    "lt_kline_stream": {
      "code": "ws.lt_kline_stream(interval=1, symbol='BTC3LUSDT', callback=handle_lt_kline)",
      "frequency": "1-60s",
      "auth_required": false,
      "note": "Leveraged token kline stream"
    },
    "lt_ticker_stream": {
      "code": "ws.lt_ticker_stream(symbol='BTC3LUSDT', callback=handle_lt_ticker)",
      "frequency": "300ms",
      "auth_required": false,
      "note": "Leveraged token ticker stream"
    },
    "lt_nav_stream": {
      "code": "ws.lt_nav_stream(symbol='BTC3LUSDT', callback=handle_lt_nav)",
      "frequency": "300ms",
      "auth_required": false,
      "note": "Leveraged token NAV stream"
    }
  }
}
``` [1](#1-0) 

### Missing Spread Trading Functions

```json
{
  "spread_trading_functions": {
    "http_endpoints": {
      "get_spread_instruments_info": {
        "code": "session.get_instruments_info(category='spread')",
        "auth_required": false,
        "endpoint": "/v5/spread/market/instrument",
        "note": "Spread trading instrument information"
      },
      "get_spread_orderbook": {
        "code": "session.get_orderbook(category='spread', symbol='BTCUSDT-ETHUSDT')",
        "auth_required": false,
        "endpoint": "/v5/spread/market/orderbook",
        "required_params": ["symbol"]
      },
      "get_spread_tickers": {
        "code": "session.get_tickers(category='spread')",
        "auth_required": false,
        "endpoint": "/v5/spread/market/tickers"
      },
      "place_spread_order": {
        "code": "session.place_order(category='spread', symbol='BTCUSDT-ETHUSDT', side='Buy', orderType='Limit', qty='1', price='0.065')",
        "auth_required": true,
        "endpoint": "/v5/spread/trade/create-order",
        "required_params": ["category", "symbol", "side", "orderType", "qty"]
      }
    },
    "websocket_streams": {
      "spread_orderbook_stream": {
        "code": "ws_spread.orderbook_stream(depth=25, symbol='BTCUSDT-ETHUSDT', callback=handle_spread_orderbook)",
        "frequency": "20ms",
        "auth_required": false
      },
      "spread_trade_stream": {
        "code": "ws_spread.trade_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_trades)",
        "frequency": "real-time",
        "auth_required": false
      },
      "spread_ticker_stream": {
        "code": "ws_spread.ticker_stream(symbol='BTCUSDT-ETHUSDT', callback=handle_spread_ticker)",
        "frequency": "100ms",
        "auth_required": false
      }
    }
  }
}
``` [2](#1-1) 

### Missing Asset Management Functions

```json
{
  "asset_management_functions": {
    "deposit_withdraw": {
      "get_deposit_records": {
        "code": "session.get_deposit_records(coin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/asset/deposit/query-record",
        "required_params": []
      },
      "get_withdrawal_records": {
        "code": "session.get_withdrawal_records(coin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/asset/withdraw/query-record",
        "required_params": []
      },
      "get_coin_info": {
        "code": "session.get_coin_info(coin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/asset/coin/query-info",
        "required_params": []
      },
      "withdraw": {
        "code": "session.withdraw(coin='USDT', chain='ETH', address='0x...', amount='100')",
        "auth_required": true,
        "endpoint": "/v5/asset/withdraw/create",
        "required_params": ["coin", "chain", "address", "amount"]
      }
    },
    "internal_transfer": {
      "get_internal_transfer_records": {
        "code": "session.get_internal_transfer_records()",
        "auth_required": true,
        "endpoint": "/v5/asset/transfer/query-inter-transfer-list",
        "required_params": []
      },
      "create_internal_transfer": {
        "code": "session.create_internal_transfer(transferId='uuid', coin='USDT', amount='100', fromAccountType='UNIFIED', toAccountType='CONTRACT')",
        "auth_required": true,
        "endpoint": "/v5/asset/transfer/inter-transfer",
        "required_params": ["transferId", "coin", "amount", "fromAccountType", "toAccountType"]
      }
    }
  }
}
```

### Missing User Management Functions

```json
{
  "user_management_functions": {
    "api_key_management": {
      "get_api_key_info": {
        "code": "session.get_api_key_info()",
        "auth_required": true,
        "endpoint": "/v5/user/query-api",
        "required_params": []
      },
      "modify_master_api_key": {
        "code": "session.modify_master_api_key(readOnly=0, ips=['192.168.1.1'], permissions={'ContractTrade': ['Order', 'Position']})",
        "auth_required": true,
        "endpoint": "/v5/user/update-api",
        "required_params": []
      },
      "delete_master_api_key": {
        "code": "session.delete_master_api_key()",
        "auth_required": true,
        "endpoint": "/v5/user/delete-api",
        "required_params": []
      }
    },
    "sub_account_management": {
      "create_sub_api_key": {
        "code": "session.create_sub_api_key(subuid=12345, readOnly=0, ips=['192.168.1.1'], permissions={'ContractTrade': ['Order']})",
        "auth_required": true,
        "endpoint": "/v5/user/create-sub-api",
        "required_params": ["subuid"]
      },
      "get_sub_api_keys": {
        "code": "session.get_sub_api_keys(subuid=12345)",
        "auth_required": true,
        "endpoint": "/v5/user/query-sub-api",
        "required_params": []
      },
      "delete_sub_api_key": {
        "code": "session.delete_sub_api_key(apikey='sub_api_key')",
        "auth_required": true,
        "endpoint": "/v5/user/delete-sub-api",
        "required_params": ["apikey"]
      }
    }
  }
}
```

### Missing Broker Functions

```json
{
  "broker_functions": {
    "broker_management": {
      "get_broker_info": {
        "code": "session.get_broker_info()",
        "auth_required": true,
        "endpoint": "/v5/broker/query-info",
        "required_params": []
      },
      "get_broker_earnings": {
        "code": "session.get_broker_earnings(bizType='SPOT')",
        "auth_required": true,
        "endpoint": "/v5/broker/earnings-info",
        "required_params": []
      },
      "get_broker_account_info": {
        "code": "session.get_broker_account_info(subMemberId='sub123')",
        "auth_required": true,
        "endpoint": "/v5/broker/account-info",
        "required_params": []
      }
    }
  }
}
```

### Missing Institutional Loan Functions

```json
{
  "institutional_loan_functions": {
    "loan_management": {
      "get_product_info": {
        "code": "session.get_product_info(productId='BTC')",
        "auth_required": true,
        "endpoint": "/v5/ins-loan/product-infos",
        "required_params": []
      },
      "get_margin_coin_info": {
        "code": "session.get_margin_coin_info(productId='BTC')",
        "auth_required": true,
        "endpoint": "/v5/ins-loan/ensure-tokens",
        "required_params": []
      },
      "get_loan_orders": {
        "code": "session.get_loan_orders(orderId='order123')",
        "auth_required": true,
        "endpoint": "/v5/ins-loan/loan-order",
        "required_params": []
      },
      "repay_loan": {
        "code": "session.repay_loan(orderId='order123', amount='1000')",
        "auth_required": true,
        "endpoint": "/v5/ins-loan/repaid-history",
        "required_params": []
      }
    }
  }
}
```

### Missing Crypto Loan Functions

```json
{
  "crypto_loan_functions": {
    "loan_operations": {
      "get_collateral_coins": {
        "code": "session.get_collateral_coins()",
        "auth_required": true,
        "endpoint": "/v5/crypto-loan/collateral-data",
        "required_params": []
      },
      "get_borrowable_coins": {
        "code": "session.get_borrowable_coins(collateralCoin='BTC')",
        "auth_required": true,
        "endpoint": "/v5/crypto-loan/borrowable-data",
        "required_params": []
      },
      "get_loan_orders": {
        "code": "session.get_loan_orders(loanCoin='USDT')",
        "auth_required": true,
        "endpoint": "/v5/crypto-loan/orders",
        "required_params": []
      },
      "borrow": {
        "code": "session.borrow(loanCoin='USDT', loanAmount='1000', collateralCoin='BTC', collateralAmount='0.1')",
        "auth_required": true,
        "endpoint": "/v5/crypto-loan/borrow",
        "required_params": ["loanCoin", "loanAmount", "collateralCoin", "collateralAmount"]
      }
    }
  }
}
```

### Missing Earn Functions

```json
{
  "earn_functions": {
    "earn_products": {
      "get_product_info": {
        "code": "session.get_product_info(productType='FLEXIBLE')",
        "auth_required": true,
        "endpoint": "/v5/earn/product",
        "required_params": []
      },
      "purchase_product": {
        "code": "session.purchase_product(productId='prod123', amount='1000')",
        "auth_required": true,
        "endpoint": "/v5/earn/purchase",
        "required_params": ["productId", "amount"]
      },
      "redeem_product": {
        "code": "session.redeem_product(productId='prod123', amount='500')",
        "auth_required": true,
        "endpoint": "/v5/earn/redeem",
        "required_params": ["productId"]
      },
      "get_account_info": {
        "code": "session.get_account_info(productType='FLEXIBLE')",
        "auth_required": true,
        "endpoint": "/v5/earn/account",
        "required_params": []
      }
    }
  }
}
```

### Complete WebSocket Trading Operations

```json
{
  "websocket_trading_complete": {
    "initialization_options": {
      "basic": "ws_trading = WebSocketTrading(testnet=True, api_key='key', api_secret='secret')",
      "with_recv_window": "ws_trading = WebSocketTrading(recv_window=5000, testnet=True, api_key='key', api_secret='secret')",
      "with_referral": "ws_trading = WebSocketTrading(referral_id='ref123', testnet=True, api_key='key', api_secret='secret')"
    },
    "all_operations": {
      "place_order": {
        "code": "ws_trading.place_order(callback=handle_response, category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000')",
        "operation": "order.create"
      },
      "amend_order": {
        "code": "ws_trading.amend_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id', price='50100')",
        "operation": "order.amend"
      },
      "cancel_order": {
        "code": "ws_trading.cancel_order(callback=handle_response, category='linear', symbol='BTCUSDT', orderId='order_id')",
        "operation": "order.cancel"
      },
      "place_batch_order": {
        "code": "ws_trading.place_batch_order(callback=handle_response, category='linear', request=[{'symbol': 'BTCUSDT', 'side': 'Buy', 'orderType': 'Limit', 'qty': '0.01', 'price': '50000'}])",
        "operation": "order.create-batch"
      },
      "amend_batch_order": {
        "code": "ws_trading.amend_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1', 'price': '50100'}])",
        "operation": "order.amend-batch"
      },
      "cancel_batch_order": {
        "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1'}])",
        "operation": "order.cancel-batch"
      }
    }
  }
}
```

<cite repo="bybit-exchange/pybit" path="pybit/unified_trading.py

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2) request, you want the missing code snippets for a complete market making bot JSON guide using pybit. Based on the codebase context, I can see you need the remaining HTTP functions, batch operations, and hedge mode specifics that weren't covered in your initial guide.

## Missing Code Snippets - Complete JSON Reference

Here are the missing pybit functions organized by category:

### Missing HTTP Trade Functions

```json
{
  "trade_management_http": {
    "get_order_history": {
      "code": "session.get_order_history(category='linear', symbol='BTCUSDT')",
      "auth_required": true,
      "endpoint": "/v5/order/order-list",
      "required_params": ["category"]
    },
    "place_batch_order": {
      "code": "session.place_batch_order(category='option', request=[{'symbol': 'BTC-29DEC23-50000-C', 'side': 'Buy', 'orderType': 'Limit', 'qty': '1'}])",
      "auth_required": true,
      "endpoint": "/v5/order/batch-place",
      "required_params": ["category", "request"],
      "note": "Options only"
    },
    "amend_batch_order": {
      "code": "session.amend_batch_order(category='option', request=[{'symbol': 'BTC-29DEC23-50000-C', 'orderId': 'order_id', 'qty': '2'}])",
      "auth_required": true,
      "endpoint": "/v5/order/batch-amend",
      "required_params": ["category", "request"],
      "note": "Options only"
    }
  }
}
``` [1](#0-0) 

### Missing Position Management Functions

```json
{
  "position_management_extended": {
    "switch_margin_mode": {
      "code": "session.switch_margin_mode(category='linear', symbol='BTCUSDT', tradeMode=1, buyLeverage='10', sellLeverage='10')",
      "auth_required": true,
      "endpoint": "/v5/position/switch-isolated",
      "required_params": ["category", "symbol", "tradeMode", "buyLeverage", "sellLeverage"],
      "note": "0=cross margin, 1=isolated margin"
    },
    "set_tp_sl_mode": {
      "code": "session.set_tp_sl_mode(category='linear', symbol='BTCUSDT', tpSlMode='Full')",
      "auth_required": true,
      "endpoint": "/v5/position/set-tpsl-mode",
      "required_params": ["category", "symbol", "tpSlMode"],
      "note": "Full or Partial"
    },
    "set_auto_add_margin": {
      "code": "session.set_auto_add_margin(category='linear', symbol='BTCUSDT', autoAddMargin=1)",
      "auth_required": true,
      "endpoint": "/v5/position/set-auto-add-margin",
      "required_params": ["category", "symbol", "autoAddMargin"]
    },
    "add_or_reduce_margin": {
      "code": "session.add_or_reduce_margin(category='linear', symbol='BTCUSDT', margin='100')",
      "auth_required": true,
      "endpoint": "/v5/position/add-margin",
      "required_params": ["category", "symbol", "margin"],
      "note": "Positive to add, negative to reduce"
    },
    "get_executions": {
      "code": "session.get_executions(category='linear', symbol='BTCUSDT')",
      "auth_required": true,
      "endpoint": "/v5/execution/list",
      "required_params": ["category"]
    },
    "get_closed_pnl": {
      "code": "session.get_closed_pnl(category='linear', symbol='BTCUSDT')",
      "auth_required": true,
      "endpoint": "/v5/position/closed-pnl",
      "required_params": ["category"]
    }
  }
}
``` [2](#0-1) 

### Missing Account Management Functions

```json
{
  "account_management_extended": {
    "get_transferable_amount": {
      "code": "session.get_transferable_amount(coinName='USDT')",
      "auth_required": true,
      "endpoint": "/v5/account/withdrawal",
      "required_params": ["coinName"]
    },
    "upgrade_to_unified_trading_account": {
      "code": "session.upgrade_to_unified_trading_account()",
      "auth_required": true,
      "endpoint": "/v5/account/upgrade-to-uta",
      "required_params": []
    },
    "get_borrow_history": {
      "code": "session.get_borrow_history(currency='USDT')",
      "auth_required": true,
      "endpoint": "/v5/account/borrow-history",
      "required_params": []
    },
    "get_collateral_info": {
      "code": "session.get_collateral_info(currency='BTC')",
      "auth_required": true,
      "endpoint": "/v5/account/collateral-info",
      "required_params": []
    },
    "set_collateral_coin": {
      "code": "session.set_collateral_coin(coin='BTC', collateralSwitch='ON')",
      "auth_required": true,
      "endpoint": "/v5/account/set-collateral-switch",
      "required_params": ["coin", "collateralSwitch"]
    },
    "get_account_info": {
      "code": "session.get_account_info()",
      "auth_required": true,
      "endpoint": "/v5/account/info",
      "required_params": []
    },
    "get_transaction_log": {
      "code": "session.get_transaction_log(accountType='UNIFIED')",
      "auth_required": true,
      "endpoint": "/v5/account/transaction-log",
      "required_params": []
    },
    "get_mmp_state": {
      "code": "session.get_mmp_state(baseCoin='BTC')",
      "auth_required": true,
      "endpoint": "/v5/account/mmp-state",
      "required_params": ["baseCoin"]
    }
  }
}
``` [3](#0-2) 

### Missing WebSocket Batch Trading Operations

```json
{
  "websocket_batch_trading": {
    "amend_batch_order": {
      "code": "ws_trading.amend_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1', 'price': '50100'}, {'orderId': 'id2', 'qty': '0.02'}])",
      "auth_required": true,
      "operation": "order.amend-batch"
    },
    "cancel_batch_order": {
      "code": "ws_trading.cancel_batch_order(callback=handle_response, category='linear', request=[{'orderId': 'id1'}, {'orderLinkId': 'link2'}])",
      "auth_required": true,
      "operation": "order.cancel-batch"
    }
  }
}
``` [4](#0-3) 

### Missing WebSocket Private Streams

```json
{
  "websocket_private_streams_extended": {
    "fast_execution_stream": {
      "code": "ws.fast_execution_stream(callback=handle_fast_execution, categorised_topic='linear')",
      "frequency": "real-time (lower latency)",
      "auth_required": true,
      "note": "Reduced latency but limited data fields"
    },
    "greek_stream": {
      "code": "ws.greek_stream(callback=handle_greeks)",
      "frequency": "real-time",
      "auth_required": true,
      "note": "Options only - Delta, Gamma, Theta, Vega"
    },
    "spread_order_stream": {
      "code": "ws.spread_order_stream(callback=handle_spread_orders)",
      "frequency": "real-time",
      "auth_required": true,
      "note": "Spread trading orders"
    },
    "spread_execution_stream": {
      "code": "ws.spread_execution_stream(callback=handle_spread_executions)",
      "frequency": "real-time",
      "auth_required": true,
      "note": "Spread trading executions"
    }
  }
}
``` [5](#0-4) 

### Missing WebSocket Public Streams

```json
{
  "websocket_public_streams_extended": {
    "liquidation_stream": {
      "code": "ws.liquidation_stream(symbol='BTCUSDT', callback=handle_liquidation)",
      "frequency": "1s max per symbol",
      "auth_required": false,
      "note": "Deprecated - use all_liquidation_stream"
    },
    "all_liquidation_stream": {
      "code": "ws.all_liquidation_stream(callback=handle_all_liquidations)",
      "frequency": "real-time",
      "auth_required": false,
      "note": "All liquidations across symbols"
    }
  }
}
``` [6](#0-5) 

### Missing Hedge Mode Specific Functions

```json
{
  "hedge_mode_functions": {
    "switch_position_mode": {
      "code": "session.switch_position_mode(category='linear', mode='3')",
      "auth_required": true,
      "endpoint": "/v5/position/switch-mode",
      "required_params": ["category"],
      "modes": {
        "0": "one_way_mode",
        "3": "hedge_mode"
      },
      "note": "Enables simultaneous Buy and Sell positions"
    },
    "place_hedge_order": {
      "code": "session.place_order(category='linear', symbol='BTCUSDT', side='Buy', orderType='Limit', qty='0.01', price='50000', positionIdx=1)",
      "note": "positionIdx: 0=one-way, 1=hedge-buy, 2=hedge-sell"
    },
    "get_hedge_positions": {
      "code": "session.get_positions(category='linear', symbol='BTCUSDT')",
      "note": "Returns separate Buy and Sell positions in hedge mode"
    }
  }
}
``` [7](#0-6) 

### Missing Misc Functions

```json
{
  "misc_functions": {
    "get_announcement": {
      "code": "session.get_announcement()",
      "auth_required": false,
      "endpoint": "/v5/announcements/index"
    },
    "request_demo_trading_funds": {
      "code": "session.request_demo_trading_funds()",
      "auth_required": true,
      "endpoint": "/v5/account/demo-apply-money",
      "note": "Testnet only"
    }
  }
}
``` [8](#0-7) 

## Notes

These missing snippets complete the comprehensive market making bot guide for pybit. <cite/> The functions cover all aspects of trading operations including batch processing, hedge mode support, advanced position management, and real-time WebSocket streams. <cite/> All functions use Bybit's v5 API through the unified trading interface, ensuring compatibility across different market categories (spot, linear, inverse, options). <cite/>

Wiki pages you might want to explore:
- [Architecture Evolution (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#1.2)
- [Account Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.2)
- [Position Management API (bybit-exchange/pybit)](/wiki/bybit-exchange/pybit#5.3)
## Analysis of the Provided Code

### Strengths
1. **Advanced Data Structures**:
   - The `OptimizedSkipList` provides O(log n) complexity for insert, delete, and search operations, making it suitable for maintaining sorted orderbook data.
   - The `EnhancedHeap` is optimized with a position map for O(log n) updates and removals, improving performance over a standard heap.
   - The choice between Skip List and Heap allows flexibility based on use case (e.g., Skip List for range queries, Heap for top-level access).

2. **Thread Safety**:
   - The use of `threading.RLock` ensures thread-safe operations, critical for real-time orderbook updates in a multi-threaded environment.

3. **Performance Metrics**:
   - Tracking `update_count` and `total_update_time` is useful for monitoring performance and identifying bottlenecks.

4. **Type Hints and Modularity**:
   - The code uses Python's `typing` module for type safety and follows a modular design with clear separation of concerns (data structures, orderbook management, etc.).

5. **Integration with pybit**:
   - The code is tailored for pybit's orderbook data format, handling snapshots and delta updates efficiently.

### Potential Improvements
1. **Error Handling**:
   - The code lacks robust error handling for invalid inputs (e.g., malformed snapshot or delta data, non-numeric prices/quantities).
   - Missing validation for sequence numbers to ensure data consistency in delta updates.

2. **Performance Optimizations**:
   - Batching delta updates to reduce lock contention in high-frequency scenarios.
   - Caching frequently accessed data (e.g., top N bids/asks) to reduce retrieval time.
   - Using a more memory-efficient representation for `PriceLevel` (e.g., slots for reduced memory overhead).

3. **Scalability**:
   - Adding support for sharding or partitioning the orderbook for very large markets.
   - Implementing an asynchronous interface for non-blocking updates.

4. **Logging and Debugging**:
   - Adding logging for critical operations (e.g., snapshot processing, errors).
   - Including debug utilities to inspect the orderbook state.

5. **Algorithm Selection**:
   - Dynamically choosing between Skip List and Heap based on workload (e.g., frequent top-level access vs. range queries).
   - Adding hybrid approaches, such as a combination of a heap for top levels and a balanced tree for deeper levels.

6. **Modern Python Features**:
   - Using `__slots__` in `PriceLevel` to reduce memory usage.
   - Leveraging `contextlib` for cleaner lock management.
   - Adding `@cached_property` for computed properties like best bid/ask.

7. **Testing and Validation**:
   - Including unit tests to validate sorting correctness and performance.
   - Adding methods to verify orderbook integrity (e.g., ensuring no duplicate price levels).

---

## Enhanced Code Implementation

Below is the improved version of the code, incorporating the suggested enhancements:

```python
"""
Enhanced Orderbook Sorting System for Market Making Bots
Combines multiple sorting algorithms with advanced data structures for optimal performance
"""

from __future__ import annotations
import heapq
import bisect
import time
import logging
import threading
from typing import Dict, List, Tuple, Optional, Any, Generic, TypeVar
from dataclasses import dataclass
from collections import defaultdict
from contextlib import contextmanager
from functools import cached_property
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Type variables for generic data structures
KT = TypeVar("KT")
VT = TypeVar("VT")

@dataclass(slots=True)
class PriceLevel:
    """Price level with metadata, optimized for memory with slots"""
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1
    
    def __lt__(self, other: 'PriceLevel') -> bool:
        return self.price < other.price
    
    def __eq__(self, other: 'PriceLevel') -> bool:
        return abs(self.price - other.price) < 1e-8

class OptimizedSkipList(Generic[KT, VT]):
    """
    Enhanced Skip List implementation with O(log n) insert/delete/search
    Based on TheAlgorithms/Python data_structures/linked_list/skip_list.py
    """
    
    class Node(Generic[KT, VT]):
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            self.forward: List[Optional['OptimizedSkipList.Node']] = [None] * (level + 1)
            self.level = level
    
    def __init__(self, max_level: int = 16, p: float = 0.5):
        self.max_level = max_level
        self.p = p
        self.level = 0
        self.header = self.Node(None, None, max_level)
        self._size = 0
    
    def _random_level(self) -> int:
        """Generate random level for new node"""
        level = 0
        while level < self.max_level and random.random() < self.p:
            level += 1
        return level
    
    def insert(self, key: KT, value: VT) -> None:
        """Insert with O(log n) complexity"""
        update = [None] * (self.max_level + 1)
        current = self.header
        
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        
        current = current.forward[0]
        
        if current and current.key == key:
            current.value = value
            return
        
        new_level = self._random_level()
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level
        
        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node
        
        self._size += 1
    
    def delete(self, key: KT) -> bool:
        """Delete with O(log n) complexity"""
        update = [None] * (self.max_level + 1)
        current = self.header
        
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        
        current = current.forward[0]
        if not current or current.key != key:
            return False
        
        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break
            update[i].forward[i] = current.forward[i]
        
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1
        
        self._size -= 1
        return True
    
    def search(self, key: KT) -> Optional[VT]:
        """Search with O(log n) complexity"""
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
        
        current = current.forward[0]
        if current and current.key == key:
            return current.value
        return None
    
    def get_sorted_items(self, reverse: bool = False) -> List[Tuple[KT, VT]]:
        """Get all items in sorted order"""
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None:
                items.append((current.key, current.value))
            current = current.forward[0]
        
        return list(reversed(items)) if reverse else items

class EnhancedHeap:
    """
    Enhanced heap implementation with position tracking
    Based on TheAlgorithms/Python data_structures/heap/heap.py
    """
    
    def __init__(self, is_max_heap: bool = True):
        self.heap: List[PriceLevel] = []
        self.is_max_heap = is_max_heap
        self.position_map: Dict[float, int] = {}
    
    def _parent(self, i: int) -> int:
        return (i - 1) // 2
    
    def _left_child(self, i: int) -> int:
        return 2 * i + 1
    
    def _right_child(self, i: int) -> int:
        return 2 * i + 2
    
    def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
        if self.is_max_heap:
            return a.price > b.price
        return a.price < b.price
    
    def _swap(self, i: int, j: int) -> None:
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
    
    def _heapify_up(self, i: int) -> None:
        while i > 0:
            parent = self._parent(i)
            if not self._compare(self.heap[i], self.heap[parent]):
                break
            self._swap(i, parent)
            i = parent
    
    def _heapify_down(self, i: int) -> None:
        while True:
            largest = i
            left = self._left_child(i)
            right = self._right_child(i)
            
            if left < len(self.heap) and self._compare(self.heap[left], self.heap[largest]):
                largest = left
            
            if right < len(self.heap) and self._compare(self.heap[right], self.heap[largest]):
                largest = right
            
            if largest == i:
                break
            
            self._swap(i, largest)
            i = largest
    
    def insert(self, price_level: PriceLevel) -> None:
        """Insert price level with O(log n) complexity"""
        if price_level.price in self.position_map:
            idx = self.position_map[price_level.price]
            old_price = self.heap[idx].price
            self.heap[idx] = price_level
            self.position_map[price_level.price] = idx
            if old_price != price_level.price:
                del self.position_map[old_price]
            self._heapify_up(idx)
            self._heapify_down(idx)
        else:
            self.heap.append(price_level)
            idx = len(self.heap) - 1
            self.position_map[price_level.price] = idx
            self._heapify_up(idx)
    
    def extract_top(self) -> Optional[PriceLevel]:
        """Extract top element with O(log n) complexity"""
        if not self.heap:
            return None
        
        top = self.heap[0]
        del self.position_map[top.price]
        
        if len(self.heap) == 1:
            self.heap.pop()
            return top
        
        last = self.heap.pop()
        self.heap[0] = last
        self.position_map[last.price] = 0
        self._heapify_down(0)
        
        return top
    
    def remove(self, price: float) -> bool:
        """Remove specific price level with O(log n) complexity"""
        if price not in self.position_map:
            return False
        
        idx = self.position_map[price]
        del self.position_map[price]
        
        if idx == len(self.heap) - 1:
            self.heap.pop()
            return True
        
        last = self.heap.pop()
        self.heap[idx] = last
        self.position_map[last.price] = idx
        self._heapify_up(idx)
        self._heapify_down(idx)
        return True

class AdvancedOrderbookManager:
    """
    Advanced orderbook manager with multiple sorting strategies
    Thread-safe with optimized data structures and batch processing
    """
    
    def __init__(self, symbol: str, use_skip_list: bool = True, max_depth: int = 100):
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self.max_depth = max_depth  # Limit orderbook depth
        self._lock = threading.RLock()
        
        # Initialize data structures
        if use_skip_list:
            self.bids = OptimizedSkipList[float, PriceLevel]()
            self.asks = OptimizedSkipList[float, PriceLevel]()
        else:
            self.bids = EnhancedHeap(is_max_heap=True)
            self.asks = EnhancedHeap(is_max_heap=False)
        
        # Metadata
        self.last_update_id: int = 0
        self.last_sequence: int = 0
        self.timestamp: int = 0
        
        # Performance metrics
        self.update_count: int = 0
        self.total_update_time: float = 0.0
        
        # Cache for top levels
        self._cached_best_bid: Optional[PriceLevel] = None
        self._cached_best_ask: Optional[PriceLevel] = None
    
    @contextmanager
    def _lock_context(self):
        """Context manager for thread-safe operations"""
        with self._lock:
            yield
    
    def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        """Validate price and quantity inputs"""
        try:
            return price >= 0 and quantity >= 0
        except (TypeError, ValueError):
            logger.error(f"Invalid price or quantity: price={price}, quantity={quantity}")
            return False
    
    def _validate_sequence(self, sequence: int) -> bool:
        """Validate sequence number for delta updates"""
        if sequence <= self.last_sequence:
            logger.warning(f"Out-of-order sequence: received={sequence}, last={self.last_sequence}")
            return False
        return True
    
    def process_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """Process initial orderbook snapshot with validation"""
        try:
            with self._lock_context():
                start_time = time.perf_counter()
                
                # Validate snapshot data
                if not isinstance(snapshot_data, dict) or not all(key in snapshot_data for key in ['b', 'a', 'u']):
                    logger.error("Invalid snapshot data format")
                    raise ValueError("Invalid snapshot data format")
                
                # Clear existing data
                if self.use_skip_list:
                    self.bids = OptimizedSkipList[float, PriceLevel]()
                    self.asks = OptimizedSkipList[float, PriceLevel]()
                else:
                    self.bids = EnhancedHeap(is_max_heap=True)
                    self.asks = EnhancedHeap(is_max_heap=False)
                
                # Process bids
                for price_str, qty_str in snapshot_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            continue
                        if quantity > 0:
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid bid data: price={price_str}, quantity={qty_str}, error={e}")
                
                # Process asks
                for price_str, qty_str in snapshot_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            continue
                        if quantity > 0:
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid ask data: price={price_str}, quantity={qty_str}, error={e}")
                
                # Update metadata
                self.last_update_id = snapshot_data.get("u", 0)
                self.last_sequence = snapshot_data.get("seq", 0)
                self.timestamp = snapshot_data.get("ts", int(time.time() * 1000))
                
                # Invalidate cache
                self._cached_best_bid = None
                self._cached_best_ask = None
                
                # Update metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(f"Processed snapshot for {self.symbol}, update_id={self.last_update_id}")
        
        except Exception as e:
            logger.error(f"Error processing snapshot: {e}")
            raise
    
    def process_delta(self, delta_data: Dict[str, Any]) -> None:
        """Process delta updates with batch processing and validation"""
        try:
            with self._lock_context():
                start_time = time.perf_counter()
                
                # Validate delta data
                if not isinstance(delta_data, dict) or not any(key in delta_data for key in ['b', 'a']):
                    logger.error("Invalid delta data format")
                    raise ValueError("Invalid delta data format")
                
                # Validate sequence number
                sequence = delta_data.get("seq", self.last_sequence + 1)
                if not self._validate_sequence(sequence):
                    raise ValueError(f"Invalid sequence number: {sequence}")
                
                # Batch process bid updates
                for price_str, qty_str in delta_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            continue
                        
                        if quantity == 0.0:
                            if self.use_skip_list:
                                self.bids.delete(price)
                            else:
                                self.bids.remove(price)
                        else:
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid bid delta: price={price_str}, quantity={qty_str}, error={e}")
                
                # Batch process ask updates
                for price_str, qty_str in delta_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            continue
                        
                        if quantity == 0.0:
                            if self.use_skip_list:
                                self.asks.delete(price)
                            else:
                                self.asks.remove(price)
                        else:
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Invalid ask delta: price={price_str}, quantity={qty_str}, error={e}")
                
                # Update metadata
                self.last_update_id = delta_data.get("u", self.last_update_id)
                self.last_sequence = sequence
                self.timestamp = delta_data.get("ts", int(time.time() * 1000))
                
                # Invalidate cache
                self._cached_best_bid = None
                self._cached_best_ask = None
                
                # Update metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(f"Processed delta for {self.symbol}, sequence={self.last_sequence}")
        
        except Exception as e:
            logger.error(f"Error processing delta: {e}")
            raise
    
    @cached_property
    def best_bid(self) -> Optional[PriceLevel]:
        """Get the best bid price level (cached)"""
        if self._cached_best_bid is None:
            with self._lock_context():
                if self.use_skip_list:
                    items = self.bids.get_sorted_items(reverse=True)
                    self._cached_best_bid = items[0][1] if items else None
                else:
                    self._cached_best_bid = self.bids.extract_top()
                    if self._cached_best_bid:
                        self.bids.insert(self._cached_best_bid)  # Re-insert after extraction
        return self._cached_best_bid
    
    @cached_property
    def best_ask(self) -> Optional[PriceLevel]:
        """Get the best ask price level (cached)"""
        if self._cached_best_ask is None:
            with self._lock_context():
                if self.use_skip_list:
                    items = self.asks.get_sorted_items()
                    self._cached_best_ask = items[0][1] if items else None
                else:
                    self._cached_best_ask = self.asks.extract_top()
                    if self._cached_best_ask:
                        self.asks.insert(self._cached_best_ask)  # Re-insert after extraction
        return self._cached_best_ask
    
    def get_orderbook_depth(self, depth: int = 10) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        """Get top N bids and asks"""
        with self._lock_context():
            if self.use_skip_list:
                bids = [item[1] for item in self.bids.get_sorted_items(reverse=True)[:depth]]
                asks = [item[1] for item in self.asks.get_sorted_items()[:depth]]
            else:
                bids = []
                asks = []
                temp_bids = EnhancedHeap(is_max_heap=True)
                temp_asks = EnhancedHeap(is_max_heap=False)
                
                # Extract and re-insert top N levels
                for _ in range(min(depth, len(self.bids.heap))):
                    level = self.bids.extract_top()
                    if level:
                        bids.append(level)
                        temp_bids.insert(level)
                
                for _ in range(min(depth, len(self.asks.heap))):
                    level = self.asks.extract_top()
                    if level:
                        asks.append(level)
                        temp_asks.insert(level)
                
                # Restore original heaps
                for level in bids:
                    self.bids.insert(level)
                for level in asks:
                    self.asks.insert(level)
            
            return bids, asks
    
    def validate_orderbook(self) -> bool:
        """Validate orderbook integrity"""
        with self._lock_context():
            if self.use_skip_list:
                bids = self.bids.get_sorted_items(reverse=True)
                asks = self.asks.get_sorted_items()
                
                # Check for duplicate prices
                bid_prices = {item[0] for item in bids}
                ask_prices = {item[0] for item in asks}
                if len(bid_prices) != len(bids) or len(ask_prices) != len(asks):
                    logger.error("Duplicate price levels detected")
                    return False
                
                # Check bid-ask spread
                if bids and asks and bids[0][1].price >= asks[0][1].price:
                    logger.error("Invalid bid-ask spread")
                    return False
            
            return True

# Example usage
if __name__ == "__main__":
    # Initialize orderbook manager
    manager = AdvancedOrderbookManager(symbol="BTCUSDT", use_skip_list=True)
    
    # Sample snapshot data
    snapshot = {
        "u": 123456,
        "seq": 1000,
        "ts": int(time.time() * 1000),
        "b": [["50000.0", "1.5"], ["49999.0", "2.0"]],
        "a": [["50001.0", "1.0"], ["50002.0", "0.8"]]
    }
    
    manager.process_snapshot(snapshot)
    
    # Sample delta update
    delta = {
        "u": 123457,
        "seq": 1001,
        "ts": int(time.time() * 1000),
        "b": [["50000.0", "1.7"], ["49998.0", "1.0"]],
        "a": [["50001.0", "0.0"], ["50003.0", "0.5"]]
    }
    
    manager.process_delta(delta)
    
    # Get best bid and ask
    print(f"Best Bid: {manager.best_bid}")
    print(f"Best Ask: {manager.best_ask}")
    
    # Get orderbook depth
    bids, asks = manager.get_orderbook_depth(depth=5)
    print(f"Top Bids: {bids}")
    print(f"Top Asks: {asks}")
    
    # Validate orderbook
    print(f"Orderbook Valid: {manager.validate_orderbook()}")
```

---

## Key Enhancements

1. **Error Handling**:
   - Added input validation for prices and quantities using `_validate_price_quantity`.
   - Implemented sequence number validation with `_validate_sequence` to ensure delta updates are processed in order.
   - Wrapped critical operations in try-except blocks with detailed logging.

2. **Performance Optimizations**:
   - Added `__slots__` to `PriceLevel` to reduce memory overhead.
   - Introduced caching for best bid/ask using `@cached_property`, reducing redundant computations.
   - Implemented batch processing for delta updates to minimize lock contention.

3. **Thread Safety**:
   - Used `contextlib.contextmanager` for cleaner lock management with `_lock_context`.
   - Ensured all data structure operations are thread-safe with `RLock`.

4. **Logging and Debugging**:
   - Integrated a logging system to track operations, errors, and performance metrics.
   - Added `validate_orderbook` to check for duplicate prices and invalid bid-ask spreads.

5. **Scalability**:
   - Added `max_depth` parameter to limit orderbook size, preventing memory issues in large markets.
   - Implemented `get_orderbook_depth` for efficient retrieval of top N levels.

6. **Modern Python Features**:
   - Used `@cached_property` for best bid/ask access.
   - Improved type hints and documentation for better code clarity.

7. **Testing and Validation**:
   - Added `validate_orderbook` to ensure data integrity.
   - Included example usage with sample snapshot and delta data.

---
"""
Enhanced Orderbook Sorting System for Market Making Bots
Combines multiple sorting algorithms with advanced data structures for optimal performance
"""

from __future__ import annotations
import heapq
import bisect
import time
import logging
import threading
from typing import Dict, List, Tuple, Optional, Any, Generic, TypeVar
from dataclasses import dataclass
from collections import defaultdict
from contextlib import contextmanager
from functools import cached_property
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Type variables for generic data structures
KT = TypeVar("KT")
VT = TypeVar("VT")

@dataclass(slots=True)
class PriceLevel:
    """
    Price level with metadata, optimized for memory with slots.
    Represents an aggregated price level in the orderbook.
    """
    price: float
    quantity: float
    timestamp: int
    order_count: int = 1 # Number of individual orders at this price level (optional, for tracking)
    
    def __lt__(self, other: 'PriceLevel') -> bool:
        """Compares PriceLevel objects based on price."""
        return self.price < other.price
    
    def __eq__(self, other: 'PriceLevel') -> bool:
        """Compares PriceLevel objects for equality, considering float precision."""
        return abs(self.price - other.price) < 1e-8

class OptimizedSkipList(Generic[KT, VT]):
    """
    Enhanced Skip List implementation with O(log n) insert/delete/search operations.
    Maintains sorted order of keys and associated values.
    """
    
    class Node(Generic[KT, VT]):
        """Node structure for the Skip List."""
        def __init__(self, key: KT, value: VT, level: int):
            self.key = key
            self.value = value
            # forward[i] is pointer to next node in i-th level
            self.forward: List[Optional['OptimizedSkipList.Node']] = [None] * (level + 1)
            self.level = level
    
    def __init__(self, max_level: int = 16, p: float = 0.5):
        """
        Initializes the Skip List.
        :param max_level: Maximum level for a node in the skip list.
        :param p: Probability of a node having a higher level.
        """
        self.max_level = max_level
        self.p = p
        self.level = 0  # Current level of the skip list
        # Header node acts as the start of all levels
        self.header = self.Node(None, None, max_level)
        self._size = 0 # Current number of elements in the skip list
    
    def _random_level(self) -> int:
        """
        Generates a random level for a new node based on probability 'p'.
        """
        level = 0
        while level < self.max_level and random.random() < self.p:
            level += 1
        return level
    
    def insert(self, key: KT, value: VT) -> None:
        """
        Inserts a key-value pair into the Skip List with O(log n) average complexity.
        If the key already exists, its value is updated.
        """
        update = [None] * (self.max_level + 1)
        current = self.header
        
        # Start from the highest level and work downwards
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current # Store previous node at current level
        
        # Move to the first level to find the insertion point
        current = current.forward[0]
        
        # If key already exists, update its value
        if current and current.key == key:
            current.value = value
            logger.debug(f"SkipList: Updated key {key}")
            return
        
        # Generate a random level for the new node
        new_level = self._random_level()
        # If new node's level is greater than current skip list level, update header pointers
        if new_level > self.level:
            for i in range(self.level + 1, new_level + 1):
                update[i] = self.header
            self.level = new_level
        
        # Create new node and insert it into the skip list
        new_node = self.Node(key, value, new_level)
        for i in range(new_level + 1):
            new_node.forward[i] = update[i].forward[i]
            update[i].forward[i] = new_node
        
        self._size += 1
        logger.debug(f"SkipList: Inserted key {key} at level {new_level}")
    
    def delete(self, key: KT) -> bool:
        """
        Deletes a key-value pair from the Skip List with O(log n) average complexity.
        :return: True if the key was found and deleted, False otherwise.
        """
        update = [None] * (self.max_level + 1)
        current = self.header
        
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
            update[i] = current
        
        current = current.forward[0]
        if not current or current.key != key:
            logger.debug(f"SkipList: Key {key} not found for deletion.")
            return False # Key not found
        
        # Remove node from all levels it is part of
        for i in range(self.level + 1):
            if update[i].forward[i] != current:
                break # Node is not present at this level or higher
            update[i].forward[i] = current.forward[i]
        
        # Decrease level of skip list if no more nodes at current highest level
        while self.level > 0 and not self.header.forward[self.level]:
            self.level -= 1
        
        self._size -= 1
        logger.debug(f"SkipList: Deleted key {key}")
        return True
    
    def search(self, key: KT) -> Optional[VT]:
        """
        Searches for a key in the Skip List with O(log n) average complexity.
        :return: The value associated with the key, or None if not found.
        """
        current = self.header
        for i in range(self.level, -1, -1):
            while (current.forward[i] and 
                   current.forward[i].key is not None and 
                   current.forward[i].key < key):
                current = current.forward[i]
        
        current = current.forward[0]
        if current and current.key == key:
            logger.debug(f"SkipList: Found key {key}")
            return current.value
        logger.debug(f"SkipList: Key {key} not found.")
        return None
    
    def get_sorted_items(self, reverse: bool = False) -> List[Tuple[KT, VT]]:
        """
        Retrieves all items in sorted order (ascending by default).
        :param reverse: If True, returns items in descending order.
        :return: A list of (key, value) tuples.
        """
        items = []
        current = self.header.forward[0]
        while current:
            if current.key is not None: # Ensure it's not the header node
                items.append((current.key, current.value))
            current = current.forward[0]
        
        return list(reversed(items)) if reverse else items

class EnhancedHeap:
    """
    Enhanced heap implementation (Min-Heap or Max-Heap) with position tracking
    for O(log n) update and removal operations.
    
    Note: Using float keys directly in `position_map` can lead to precision issues
    in extreme cases. For robust production systems, consider using `decimal.Decimal`
    or quantizing float values to integers for keys.
    """
    
    def __init__(self, is_max_heap: bool = True):
        """
        Initializes the Enhanced Heap.
        :param is_max_heap: If True, it's a Max-Heap (largest price on top);
                            If False, it's a Min-Heap (smallest price on top).
        """
        self.heap: List[PriceLevel] = []
        self.is_max_heap = is_max_heap
        # Maps price to its index in the heap for O(1) lookup
        self.position_map: Dict[float, int] = {} 
    
    def _parent(self, i: int) -> int:
        return (i - 1) // 2
    
    def _left_child(self, i: int) -> int:
        return 2 * i + 1
    
    def _right_child(self, i: int) -> int:
        return 2 * i + 2
    
    def _compare(self, a: PriceLevel, b: PriceLevel) -> bool:
        """
        Compares two PriceLevel objects based on heap type (max or min).
        :return: True if 'a' should be higher in the heap than 'b'.
        """
        if self.is_max_heap:
            return a.price > b.price
        return a.price < b.price
    
    def _swap(self, i: int, j: int) -> None:
        """Swaps two elements in the heap and updates their positions in the map."""
        # Update position map first
        self.position_map[self.heap[i].price] = j
        self.position_map[self.heap[j].price] = i
        # Swap elements in the heap list
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
    
    def _heapify_up(self, i: int) -> None:
        """Maintains heap property by moving element at index 'i' up the heap."""
        while i > 0:
            parent = self._parent(i)
            if not self._compare(self.heap[i], self.heap[parent]):
                break # Correct position found
            self._swap(i, parent)
            i = parent
    
    def _heapify_down(self, i: int) -> None:
        """Maintains heap property by moving element at index 'i' down the heap."""
        while True:
            largest = i # Assume current is the largest/smallest
            left = self._left_child(i)
            right = self._right_child(i)
            
            # Find the largest/smallest among current, left, and right children
            if left < len(self.heap) and self._compare(self.heap[left], self.heap[largest]):
                largest = left
            
            if right < len(self.heap) and self._compare(self.heap[right], self.heap[largest]):
                largest = right
            
            if largest == i:
                break # Correct position found
            
            self._swap(i, largest)
            i = largest
    
    def insert(self, price_level: PriceLevel) -> None:
        """
        Inserts a new PriceLevel or updates an existing one with O(log n) complexity.
        """
        if price_level.price in self.position_map:
            idx = self.position_map[price_level.price]
            # Store old price to correctly delete from map if price itself changes (unlikely for update, but robust)
            old_price = self.heap[idx].price 
            self.heap[idx] = price_level # Update the PriceLevel object
            self.position_map[price_level.price] = idx # Ensure map points to current index
            if abs(old_price - price_level.price) > 1e-8: # If price actually changed (highly unusual for an "update")
                 logger.warning(f"Heap: Price changed for existing key {old_price} to {price_level.price}. This usually indicates a logic error or non-stable floating point values.")
                 del self.position_map[old_price] # Clean up old entry
            
            # Re-heapify from the updated position
            self._heapify_up(idx)
            self._heapify_down(idx)
            logger.debug(f"Heap: Updated price level for price {price_level.price}")
        else:
            self.heap.append(price_level)
            idx = len(self.heap) - 1
            self.position_map[price_level.price] = idx
            self._heapify_up(idx)
            logger.debug(f"Heap: Inserted price level for price {price_level.price}")
    
    def extract_top(self) -> Optional[PriceLevel]:
        """
        Extracts and removes the top element (max for Max-Heap, min for Min-Heap)
        with O(log n) complexity.
        :return: The PriceLevel object from the top of the heap, or None if heap is empty.
        """
        if not self.heap:
            logger.debug("Heap: Attempted to extract top from empty heap.")
            return None
        
        top = self.heap[0]
        del self.position_map[top.price]
        
        if len(self.heap) == 1:
            self.heap.pop()
            logger.debug(f"Heap: Extracted last item {top.price}.")
            return top
        
        # Move the last element to the root and heapify down
        last = self.heap.pop()
        self.heap[0] = last
        self.position_map[last.price] = 0
        self._heapify_down(0)
        
        logger.debug(f"Heap: Extracted top item {top.price}")
        return top
    
    def remove(self, price: float) -> bool:
        """
        Removes a specific price level from the heap with O(log n) complexity.
        :param price: The price of the PriceLevel to remove.
        :return: True if the price level was found and removed, False otherwise.
        """
        if price not in self.position_map:
            logger.debug(f"Heap: Price {price} not found for removal.")
            return False
        
        idx = self.position_map[price]
        del self.position_map[price]
        
        if idx == len(self.heap) - 1:
            self.heap.pop() # If it's the last element, just remove it
            logger.debug(f"Heap: Removed last item at price {price}")
            return True
        
        # Replace the element to be removed with the last element
        last = self.heap.pop()
        self.heap[idx] = last
        self.position_map[last.price] = idx
        
        # Re-heapify from the position where the element was removed
        self._heapify_up(idx)
        self._heapify_down(idx)
        logger.debug(f"Heap: Removed item at price {price}")
        return True

class AdvancedOrderbookManager:
    """
    Advanced orderbook manager for a single symbol, supporting both Skip List and
    Enhanced Heap for storing bids and asks. Provides thread-safe operations,
    snapshot and delta processing, and performance metrics.
    """
    
    def __init__(self, symbol: str, use_skip_list: bool = True, max_depth: int = 100):
        """
        Initializes the AdvancedOrderbookManager.
        :param symbol: The trading symbol (e.g., "BTCUSDT").
        :param use_skip_list: If True, uses OptimizedSkipList; otherwise, uses EnhancedHeap.
        :param max_depth: Maximum number of price levels to maintain in the orderbook.
                          (Currently not actively enforced for performance, but good for design intent).
        """
        self.symbol = symbol
        self.use_skip_list = use_skip_list
        self.max_depth = max_depth  # Limit orderbook depth (design intent, not strictly enforced for every update)
        self._lock = threading.RLock() # Reentrant lock for thread safety
        
        # Initialize data structures based on configuration
        if use_skip_list:
            logger.info(f"OrderbookManager for {symbol}: Using OptimizedSkipList.")
            self.bids = OptimizedSkipList[float, PriceLevel]() # Bids sorted descending
            self.asks = OptimizedSkipList[float, PriceLevel]() # Asks sorted ascending
        else:
            logger.info(f"OrderbookManager for {symbol}: Using EnhancedHeap.")
            self.bids = EnhancedHeap(is_max_heap=True)  # Max-heap for bids
            self.asks = EnhancedHeap(is_max_heap=False) # Min-heap for asks
        
        # Orderbook metadata
        self.last_update_id: int = 0
        self.last_sequence: int = 0
        self.timestamp: int = 0 # Timestamp of the last processed update
        
        # Performance metrics
        self.update_count: int = 0
        self.total_update_time: float = 0.0
        
        # Cached properties for best bid/ask (invalidated on updates)
        self._cached_best_bid: Optional[PriceLevel] = None
        self._cached_best_ask: Optional[PriceLevel] = None
    
    @contextmanager
    def _lock_context(self):
        """Context manager for acquiring and releasing the RLock."""
        with self._lock:
            yield
    
    def _validate_price_quantity(self, price: float, quantity: float) -> bool:
        """
        Validates if price and quantity are non-negative and numerically valid.
        :return: True if valid, False otherwise.
        """
        if not (isinstance(price, (int, float)) and isinstance(quantity, (int, float))):
            logger.error(f"Invalid type for price or quantity. Price: {type(price)}, Qty: {type(quantity)}")
            return False
        if price < 0 or quantity < 0:
            logger.error(f"Negative price or quantity detected: price={price}, quantity={quantity}")
            return False
        return True
    
    def _validate_sequence(self, sequence: int) -> bool:
        """
        Validates the incoming sequence number against the last known sequence.
        A return of False indicates an out-of-order or gapped update, which may
        require a full orderbook resync.
        :return: True if sequence is valid, False otherwise.
        """
        if not isinstance(sequence, int):
            logger.error(f"Invalid type for sequence number: {type(sequence)}")
            return False
        if sequence <= self.last_sequence:
            logger.warning(f"Out-of-order sequence received for {self.symbol}: received={sequence}, last={self.last_sequence}. Skipping update.")
            return False
        # For a more robust check, one might verify if sequence == self.last_sequence + 1
        # If sequence > self.last_sequence + 1, it implies a gap, and a resync might be necessary.
        # Current implementation proceeds with valid sequence numbers > last_sequence.
        return True
    
    def process_snapshot(self, snapshot_data: Dict[str, Any]) -> None:
        """
        Processes an initial orderbook snapshot, clearing existing data and
        rebuilding the orderbook.
        :param snapshot_data: Dictionary containing snapshot information ('b' for bids, 'a' for asks, 'u' for update_id, 'seq' for sequence).
        :raises ValueError: If snapshot data format is invalid or critical data is missing.
        """
        try:
            with self._lock_context():
                start_time = time.perf_counter()
                
                # Basic validation for snapshot structure
                if not isinstance(snapshot_data, dict) or 'b' not in snapshot_data or 'a' not in snapshot_data or 'u' not in snapshot_data:
                    logger.error(f"Invalid snapshot data format for {self.symbol}: {snapshot_data}")
                    raise ValueError("Invalid snapshot data format: Missing bids, asks, or update_id.")
                
                # Clear existing orderbook data by re-initializing data structures
                if self.use_skip_list:
                    self.bids = OptimizedSkipList[float, PriceLevel]()
                    self.asks = OptimizedSkipList[float, PriceLevel]()
                else:
                    self.bids = EnhancedHeap(is_max_heap=True)
                    self.asks = EnhancedHeap(is_max_heap=False)
                
                # Process bids from snapshot
                for price_str, qty_str in snapshot_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(f"Invalid bid price/quantity in snapshot for {self.symbol}: {price_str}/{qty_str}. Skipping.")
                            continue
                        if quantity > 0: # Only add if quantity is positive
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to parse bid data in snapshot for {self.symbol}: price={price_str}, quantity={qty_str}, error={e}")
                
                # Process asks from snapshot
                for price_str, qty_str in snapshot_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(f"Invalid ask price/quantity in snapshot for {self.symbol}: {price_str}/{qty_str}. Skipping.")
                            continue
                        if quantity > 0: # Only add if quantity is positive
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to parse ask data in snapshot for {self.symbol}: price={price_str}, quantity={qty_str}, error={e}")
                
                # Update orderbook metadata
                self.last_update_id = snapshot_data.get("u", 0)
                self.last_sequence = snapshot_data.get("seq", 0)
                self.timestamp = snapshot_data.get("ts", int(time.time() * 1000))
                
                # Invalidate cached best bid/ask as the orderbook has changed significantly
                self._cached_best_bid = None
                self._cached_best_ask = None
                
                # Update performance metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(f"Processed snapshot for {self.symbol}. New update_id={self.last_update_id}, sequence={self.last_sequence}.")
        
        except Exception as e:
            logger.critical(f"CRITICAL ERROR processing snapshot for {self.symbol}: {e}", exc_info=True)
            raise # Re-raise to signal a severe issue
    
    def process_delta(self, delta_data: Dict[str, Any]) -> None:
        """
        Processes real-time orderbook delta updates.
        Updates, inserts, or deletes price levels based on quantity.
        :param delta_data: Dictionary containing delta updates ('b' for bids, 'a' for asks, 'u' for update_id, 'seq' for sequence).
        :raises ValueError: If delta data format is invalid or sequence number is out of order.
        """
        try:
            with self._lock_context():
                start_time = time.perf_counter()
                
                # Basic validation for delta structure
                if not isinstance(delta_data, dict) or not ('b' in delta_data or 'a' in delta_data):
                    logger.error(f"Invalid delta data format for {self.symbol}: {delta_data}")
                    raise ValueError("Invalid delta data format: Missing bids or asks.")
                
                # Validate and update sequence number
                sequence = delta_data.get("seq", self.last_sequence + 1)
                if not self._validate_sequence(sequence):
                    # If sequence is invalid, we stop processing this delta.
                    # A more complex system might trigger a full resync here.
                    logger.warning(f"Invalid sequence detected for {self.symbol}. Delta not processed.")
                    return # Do not process this delta further
                
                # Batch process bid updates
                for price_str, qty_str in delta_data.get("b", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(f"Invalid bid price/quantity in delta for {self.symbol}: {price_str}/{qty_str}. Skipping.")
                            continue
                        
                        if quantity == 0.0: # Quantity is 0, so delete the price level
                            if self.use_skip_list:
                                self.bids.delete(price)
                            else:
                                self.bids.remove(price)
                            logger.debug(f"Bid deleted: {price}")
                        else: # Quantity is > 0, so insert or update
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.bids.insert(price, level)
                            else:
                                self.bids.insert(level)
                            logger.debug(f"Bid updated/inserted: {price} @ {quantity}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to parse bid delta data for {self.symbol}: price={price_str}, quantity={qty_str}, error={e}")
                
                # Batch process ask updates
                for price_str, qty_str in delta_data.get("a", []):
                    try:
                        price = float(price_str)
                        quantity = float(qty_str)
                        if not self._validate_price_quantity(price, quantity):
                            logger.warning(f"Invalid ask price/quantity in delta for {self.symbol}: {price_str}/{qty_str}. Skipping.")
                            continue
                        
                        if quantity == 0.0: # Quantity is 0, so delete the price level
                            if self.use_skip_list:
                                self.asks.delete(price)
                            else:
                                self.asks.remove(price)
                            logger.debug(f"Ask deleted: {price}")
                        else: # Quantity is > 0, so insert or update
                            level = PriceLevel(price, quantity, int(time.time() * 1000))
                            if self.use_skip_list:
                                self.asks.insert(price, level)
                            else:
                                self.asks.insert(level)
                            logger.debug(f"Ask updated/inserted: {price} @ {quantity}")
                    except (ValueError, TypeError) as e:
                        logger.error(f"Failed to parse ask delta data for {self.symbol}: price={price_str}, quantity={qty_str}, error={e}")
                
                # Update orderbook metadata
                self.last_update_id = delta_data.get("u", self.last_update_id)
                self.last_sequence = sequence
                self.timestamp = delta_data.get("ts", int(time.time() * 1000))
                
                # Invalidate cached best bid/ask
                self._cached_best_bid = None
                self._cached_best_ask = None
                
                # Update performance metrics
                self.update_count += 1
                self.total_update_time += time.perf_counter() - start_time
                logger.info(f"Processed delta for {self.symbol}. New update_id={self.last_update_id}, sequence={self.last_sequence}.")
        
        except Exception as e:
            logger.error(f"Error processing delta for {self.symbol}: {e}", exc_info=True)
            raise # Re-raise for external handling if necessary
    
    @cached_property
    def best_bid(self) -> Optional[PriceLevel]:
        """
        Gets the best (highest) bid price level.
        Uses cached value if available, recalculates and caches otherwise.
        :return: The best bid PriceLevel, or None if no bids exist.
        """
        with self._lock_context():
            if self.use_skip_list:
                items = self.bids.get_sorted_items(reverse=True)
                if items:
                    self._cached_best_bid = items[0][1]
                else:
                    self._cached_best_bid = None
            else: # EnhancedHeap
                if self.bids.heap: # Check if heap is not empty before attempting to extract
                    # Extract top without removing it (peek functionality)
                    top_bid = self.bids.extract_top()
                    if top_bid:
                        self.bids.insert(top_bid) # Re-insert to keep it in the heap
                    self._cached_best_bid = top_bid
                else:
                    self._cached_best_bid = None
            return self._cached_best_bid
    
    @cached_property
    def best_ask(self) -> Optional[PriceLevel]:
        """
        Gets the best (lowest) ask price level.
        Uses cached value if available, recalculates and caches otherwise.
        :return: The best ask PriceLevel, or None if no asks exist.
        """
        with self._lock_context():
            if self.use_skip_list:
                items = self.asks.get_sorted_items()
                if items:
                    self._cached_best_ask = items[0][1]
                else:
                    self._cached_best_ask = None
            else: # EnhancedHeap
                if self.asks.heap: # Check if heap is not empty before attempting to extract
                    # Extract top without removing it (peek functionality)
                    top_ask = self.asks.extract_top()
                    if top_ask:
                        self.asks.insert(top_ask) # Re-insert to keep it in the heap
                    self._cached_best_ask = top_ask
                else:
                    self._cached_best_ask = None
            return self._cached_best_ask
    
    def get_orderbook_depth(self, depth: int = 10) -> Tuple[List[PriceLevel], List[PriceLevel]]:
        """
        Retrieves the top N bids and asks from the orderbook.
        :param depth: The number of top price levels to retrieve.
        :return: A tuple containing two lists: (bids_list, asks_list).
        """
        with self._lock_context():
            bids_list: List[PriceLevel] = []
            asks_list: List[PriceLevel] = []

            if self.use_skip_list:
                bids_list = [item[1] for item in self.bids.get_sorted_items(reverse=True)[:depth]]
                asks_list = [item[1] for item in self.asks.get_sorted_items()[:depth]]
            else: # EnhancedHeap
                # For heaps, extracting top N and then re-inserting them is a common way to get sorted depth
                temp_bids_storage: List[PriceLevel] = []
                for _ in range(min(depth, len(self.bids.heap))):
                    level = self.bids.extract_top()
                    if level:
                        bids_list.append(level)
                        temp_bids_storage.append(level)
                # Re-insert extracted bids back into the heap
                for level in temp_bids_storage:
                    self.bids.insert(level)
                
                temp_asks_storage: List[PriceLevel] = []
                for _ in range(min(depth, len(self.asks.heap))):
                    level = self.asks.extract_top()
                    if level:
                        asks_list.append(level)
                        temp_asks_storage.append(level)
                # Re-insert extracted asks back into the heap
                for level in temp_asks_storage:
                    self.asks.insert(level)
            
            logger.debug(f"Retrieved orderbook depth {depth} for {self.symbol}.")
            return bids_list, asks_list
    
    def validate_orderbook(self) -> bool:
        """
        Performs an integrity check on the orderbook.
        Checks for:
        1. Duplicate price levels within bids and asks.
        2. Inverted bid-ask spread (best bid should always be less than best ask).
        :return: True if the orderbook is considered valid, False otherwise.
        """
        with self._lock_context():
            is_valid = True
            
            # Check for empty orderbook scenarios
            if not self.bids.heap and not self.asks.heap and not (isinstance(self.bids, OptimizedSkipList) and self.bids._size == 0 and self.asks._size == 0):
                logger.info(f"Orderbook for {self.symbol} is empty. Considered valid.")
                return True

            best_bid_level = self.best_bid
            best_ask_level = self.best_ask
            
            if best_bid_level and best_ask_level:
                if best_bid_level.price >= best_ask_level.price:
                    logger.error(f"Orderbook invalid for {self.symbol}: Inverted bid-ask spread! Best Bid: {best_bid_level.price}, Best Ask: {best_ask_level.price}")
                    is_valid = False
            
            # Additional check for duplicate prices in SkipList (heaps inherently handle this by updating)
            if self.use_skip_list:
                bids_items = self.bids.get_sorted_items(reverse=True)
                asks_items = self.asks.get_sorted_items()
                
                bid_prices = {item[0] for item in bids_items}
                ask_prices = {item[0] for item in asks_items}
                
                if len(bid_prices) != len(bids_items):
                    logger.error(f"Orderbook invalid for {self.symbol}: Duplicate bid price levels detected.")
                    is_valid = False
                
                if len(ask_prices) != len(asks_items):
                    logger.error(f"Orderbook invalid for {self.symbol}: Duplicate ask price levels detected.")
                    is_valid = False
            
            if is_valid:
                logger.info(f"Orderbook for {self.symbol} validated successfully.")
            return is_valid

# Example usage
if __name__ == "__main__":
    # Initialize orderbook manager using SkipList
    manager_skip_list = AdvancedOrderbookManager(symbol="BTCUSDT", use_skip_list=True)
    
    # Sample snapshot data
    snapshot = {
        "u": 123456, # last_update_id
        "seq": 1000, # sequence number
        "ts": int(time.time() * 1000), # timestamp
        "b": [["50000.0", "1.5"], ["49999.0", "2.0"], ["49998.5", "0.7"]],
        "a": [["50001.0", "1.0"], ["50002.0", "0.8"], ["50002.5", "0.9"]]
    }
    
    print("\n--- Testing with SkipList ---")
    manager_skip_list.process_snapshot(snapshot)
    
    # Get best bid and ask
    print(f"Best Bid: {manager_skip_list.best_bid}")
    print(f"Best Ask: {manager_skip_list.best_ask}")
    
    # Sample delta update
    delta_skip_list = {
        "u": 123457,
        "seq": 1001,
        "ts": int(time.time() * 1000),
        "b": [["50000.0", "1.7"], ["49998.0", "1.0"]], # Update 50000, Add 49998
        "a": [["50001.0", "0.0"], ["50003.0", "0.5"]]  # Delete 50001, Add 50003
    }
    
    manager_skip_list.process_delta(delta_skip_list)
    
    print(f"Best Bid after delta: {manager_skip_list.best_bid}")
    print(f"Best Ask after delta: {manager_skip_list.best_ask}")
    
    # Get orderbook depth
    bids, asks = manager_skip_list.get_orderbook_depth(depth=5)
    print(f"Top Bids (SkipList): {bids}")
    print(f"Top Asks (SkipList): {asks}")
    
    # Validate orderbook
    print(f"Orderbook Valid (SkipList): {manager_skip_list.validate_orderbook()}")

    # Test with invalid sequence
    invalid_delta_seq = {
        "u": 123458,
        "seq": 1000, # Old sequence
        "ts": int(time.time() * 1000),
        "b": [["50000.0", "1.8"]]
    }
    print("\n--- Testing invalid sequence ---")
    manager_skip_list.process_delta(invalid_delta_seq)
    
    # Initialize orderbook manager using EnhancedHeap
    manager_heap = AdvancedOrderbookManager(symbol="ETHUSDT", use_skip_list=False)

    print("\n--- Testing with EnhancedHeap ---")
    manager_heap.process_snapshot(snapshot) # Use same snapshot
    
    print(f"Best Bid (Heap): {manager_heap.best_bid}")
    print(f"Best Ask (Heap): {manager_heap.best_ask}")

    delta_heap = {
        "u": 123457,
        "seq": 1001,
        "ts": int(time.time() * 1000),
        "b": [["50000.0", "1.7"], ["49998.0", "1.0"]], # Update 50000, Add 49998
        "a": [["50001.0", "0.0"], ["50003.0", "0.5"]]  # Delete 50001, Add 50003
    }
    manager_heap.process_delta(delta_heap)

    print(f"Best Bid after delta (Heap): {manager_heap.best_bid}")
    print(f"Best Ask after delta (Heap): {manager_heap.best_ask}")

    bids_heap, asks_heap = manager_heap.get_orderbook_depth(depth=5)
    print(f"Top Bids (Heap): {bids_heap}")
    print(f"Top Asks (Heap): {asks_heap}")

    print(f"Orderbook Valid (Heap): {manager_heap.validate_orderbook()}")
## Recommendations for Further Improvements
1. **Asynchronous Support**:
   - Add an async version of `process_snapshot` and `process_delta` using `asyncio` for non-blocking updates in high-frequency trading systems.

2. **Hybrid Data Structures**:
   - Implement a hybrid approach combining a heap for the top N levels and a Skip List for deeper levels to optimize for both frequent top-level access and range queries.

3. **Performance Benchmarking**:
   - Add a benchmarking suite to compare Skip List vs. Heap performance under different workloads (e.g., high update frequency, large depth).

4. **Serialization**:
   - Add methods to serialize/deserialize the orderbook state for persistence or sharing across systems.

5. **Unit Tests**:
   - Develop a comprehensive test suite to verify correctness, performance, and edge cases (e.g., empty orderbook, invalid inputs).

---

## Wiki Pages Reference
- **Overview (TheAlgorithms/Python)**: The enhanced code builds on the sorting and data structure concepts from TheAlgorithms/Python, particularly the Skip List and Heap implementations.
- **Heaps & Priority Queues (TheAlgorithms/Python)**: The `EnhancedHeap` class is inspired by the heap implementations, with added optimizations like position tracking for efficient updates and removals.

This implementation provides a robust, production-ready solution for orderbook management, suitable for high-frequency trading applications. Let me know if you need further refinements or specific features!

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
