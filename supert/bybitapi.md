{
  "websockets": {
    "connection": {
      "initialize": "Creates a WebSocket connection to Bybit's real-time data feed. Requires authentication (API key/secret) for subscribed streams.",
      "parameters": {
        "testnet": "Boolean flag for testnet/mainnet environment.",
        "category_type": "String specifying data product category. Common values: 'spot', 'linear' (USDⓈ-M), 'inverse' (COIN-M), 'option'.",
        "api_key": "Your Bybit API key (required for authenticated streams).",
        "api_secret": "Your Bybit API secret (required for authenticated streams)."
      }
    },
    "streams": {
      "kline_stream": {
        "description": "Subscribe to real-time kline/candlestick data.",
        "format": "kline.{interval}.{symbol}",
        "example": "kline.1.BTCUSDT",
        "intervals_available": ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"],
        "authentication_required": false,
        "data_example": "{'start': 1677657600000, 'end': 1677661200000, 'open': '23000.50', 'high': '23100.75', 'low': '22950.20', 'close': '23050.00', 'volume': '1000.500', 'turnover': '23151100.500', 'count': 5000}"
      },
      "ticker_stream": {
        "description": "Subscribe to real-time ticker updates (last price, highest bid, lowest ask, etc.).",
        "format": "tickers.{symbol}",
        "example": "tickers.BTCUSDT",
        "authentication_required": false,
        "data_example": "{'symbol': 'BTCUSDT', 'bid1Price': '23045.00', 'ask1Price': '23045.50', 'lastPrice': '23045.20', 'lastScale': '2', 'openPrice': '22500.00', 'highPrice': '23200.00', 'lowPrice': '22400.00', 'volume': '50000.000', 'turnover': '1150000000.000', 'markPrice': '23045.10', 'indexPrice': '23045.05', 'change24h': '0.0202'}"
      },
      "orderbook_stream": {
        "description": "Subscribe to real-time order book depth (bid and ask prices and quantities).",
        "format": "orderbook.{depth}.{symbol}",
        "example": "orderbook.1.BTCUSDT",
        "depth_options": ["1", "25", "50", "100", "200", "500"],
        "authentication_required": false,
        "data_example": "{'symbol': 'BTCUSDT', 'updateId': 123456, 'bids': [['23045.00', '10.500']], 'asks': [['23045.50', '5.200']]}"
      },
      "trade_stream": {
        "description": "Subscribe to real-time public trades executed on the exchange.",
        "format": "publicTrade.{symbol}",
        "example": "publicTrade.BTCUSDT",
        "authentication_required": false,
        "data_example": "{'symbol': 'BTCUSDT', 'tickDirection': 'PlusTick', 'price': '23045.20', 'size': '0.100', 'tradeTime': 1677661200123, 'execType': 'Trade', 'isBlockTrade': false}"
      },
      "liquidation_stream": {
        "description": "Subscribe to real-time liquidation data for forced liquidations.",
        "format": "liquidation.{symbol}",
        "example": "liquidation.BTCUSDT",
        "authentication_required": false,
        "data_example": "{'symbol': 'BTCUSDT', 'side': 'Sell', 'size': '50000', 'price': '22800.00', 'orderType': 'Market', 'positionSize': '200000', 'execTime': 1677661200500}"
      },
      "position_stream": {
        "description": "Subscribe to real-time position updates (entry price, size, PNL, etc.).",
        "authentication_required": true,
        "data_example": "{'symbol': 'BTCUSDT', 'side': 'Buy', 'size': '0.500', 'entryPrice': '23000.00', 'unrealisedPnl': '50.00', 'markPrice': '23050.00', 'positionMode': 'BothSides', 'leverage': '10'}"
      },
      "order_stream": {
        "description": "Subscribe to real-time order updates (creation, cancellation, modification, execution status).",
        "authentication_required": true,
        "data_example": "{'orderId': '1234567890', 'orderLinkId': 'my_order_1', 'symbol': 'BTCUSDT', 'side': 'Buy', 'orderType': 'Limit', 'price': '23000.00', 'qty': '0.100', 'status': 'New', 'leavesQty': '0.100', 'cumExecQty': '0.000', 'cTime': 1677661200000, 'updatedTime': 1677661200000}"
      },
      "execution_stream": {
        "description": "Subscribe to real-time trade execution updates for your orders.",
        "authentication_required": true,
        "data_example": "{'orderId': '1234567890', 'execId': 'exec123', 'symbol': 'BTCUSDT', 'side': 'Buy', 'orderType': 'Limit', 'execPrice': '23000.50', 'execQty': '0.050', 'execTime': 1677661200700, 'isMaker': false, 'fee': '0.00005BTC'}"
      },
      "wallet_stream": {
        "description": "Subscribe to real-time wallet balance updates (available, margin, PNL).",
        "authentication_required": true,
        "data_example": "{'accountType': 'CONTRACT', 'walletBalance': '10000.000', 'unrealisedPnl': '50.00', 'availableBalance': '9950.00', 'margin': '50.00'}"
      }
    },
    "management": {
      "ping_pong": {
        "description": "Send periodic PING messages to keep the WebSocket connection alive and detect disconnections. Bybit typically expects a PONG response.",
        "frequency": "Every 20 seconds (client-side implementation required to send PING)."
      }
    }
  },
  "order_placement": {
    "market_order": {
      "description": "Place a market order that executes immediately at the current market price.",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String: 'spot', 'linear', 'inverse', 'option'. Specifies the trading product.",
        "symbol": "Trading pair (e.g., BTCUSDT).",
        "side": "Enum: 'Buy' or 'Sell'.",
        "qty": "Order quantity (in base currency units, e.g., BTC). Must adhere to symbol's lot size rules."
      },
      "optional_parameters": {
        "timeInForce": "Enum: 'GTC' (Good Till Cancelled), 'IOC' (Immediate Or Cancel). By default 'GTC' for spot, 'IOC' for derivative market orders.",
        "orderLinkId": "Custom unique order ID (max 36 characters). Recommended for idempotency.",
        "stopLoss": "Stop loss price.",
        "takeProfit": "Take profit price.",
        "tpTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for take profit.",
        "slTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for stop loss.",
        "tpslMode": "Enum: 'Full' or 'Partial'. Specifies if SL/TP should close the entire position or a part.",
        "reduceOnly": "Boolean: 'true' or 'false'. If true, the order can only reduce existing positions.",
        "closeOnTrigger": "Boolean: 'true' or 'false'. If true, the order will be cancelled if the associated SL/TP is triggered.",
        "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Only applicable for contract categories and hedge mode.",
        "mmp": "Boolean: 'true' or 'false'. Enable Market Maker Protection. Default: false.",
        "triggerPrice": "Price to trigger the order (for conditional orders).",
        "triggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Condition for trigger price."
      }
    },
    "limit_order": {
      "description": "Place a limit order with a specified price and quantity. The order will only be executed at the specified price or better.",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String: 'spot', 'linear', 'inverse', 'option'. Specifies the trading product.",
        "symbol": "Trading pair (e.g., BTCUSDT).",
        "side": "Enum: 'Buy' or 'Sell'.",
        "orderType": "Enum: 'Limit'.",
        "price": "The limit price for the order. Must adhere to symbol's price precision rules.",
        "qty": "Order quantity (in base currency units, e.g., BTC). Must adhere to symbol's lot size rules."
      },
      "optional_parameters": {
        "timeInForce": "Enum: 'GTC', 'IOC', 'FOK', 'PostOnly'. 'PostOnly' ensures the order acts as a maker order.",
        "orderLinkId": "Custom unique order ID (max 36 characters). Recommended for idempotency.",
        "stopLoss": "Stop loss price.",
        "takeProfit": "Take profit price.",
        "tpTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for take profit.",
        "slTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for stop loss.",
        "tpslMode": "Enum: 'Full' or 'Partial'. Specifies if SL/TP should close the entire position or a part.",
        "reduceOnly": "Boolean: 'true' or 'false'. If true, the order can only reduce existing positions.",
        "closeOnTrigger": "Boolean: 'true' or 'false'. If true, the order will be cancelled if the associated SL/TP is triggered.",
        "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Only applicable for contract categories and hedge mode.",
        "triggerPrice": "Price to trigger the order (for conditional orders).",
        "triggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Condition for trigger price."
      }
    },
    "conditional_order": {
      "description": "Place a conditional order that triggers when a specified condition (e.g., price) is met, then creates a limit or market order.",
      "endpoint": "/v5/order/create",
      "required_parameters": {
        "category": "String: 'spot', 'linear', 'inverse', 'option'. Specifies the trading product.",
        "symbol": "Trading pair (e.g., BTCUSDT).",
        "side": "Enum: 'Buy' or 'Sell'.",
        "orderType": "Enum: 'Limit' or 'Market'. The type of order to be placed *after* the trigger condition is met.",
        "triggerPrice": "The price level that must be reached to activate the order.",
        "qty": "Order quantity (in base currency units, e.g., BTC). Must adhere to symbol's lot size rules.",
        "basePrice": "The price to compare with `triggerPrice`. Typically `lastPrice` for stop-limit, `indexPrice` for stop-index-limit, `markPrice` for stop-market-limit."
      },
      "optional_parameters": {
        "triggerDirection": "Integer: 1 (rise), 2 (fall). Specifies the direction of price movement to trigger.",
        "triggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. The price source for the trigger condition.",
        "price": "The limit price (if `orderType` is 'Limit'). Must adhere to symbol's price precision rules.",
        "timeInForce": "Enum: 'GTC', 'IOC', 'FOK', 'PostOnly'. Applies to the order placed after trigger.",
        "orderLinkId": "Custom unique order ID (max 36 characters). Recommended for idempotency.",
        "stopLoss": "Stop loss price.",
        "takeProfit": "Take profit price.",
        "tpTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for take profit.",
        "slTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for stop loss.",
        "tpslMode": "Enum: 'Full' or 'Partial'.",
        "reduceOnly": "Boolean: 'true' or 'false'.",
        "closeOnTrigger": "Boolean: 'true' or 'false'."
      }
    },
    "stop_loss_take_profit": {
      "description": "Set Stop Loss and Take Profit levels for an existing open position or an active order. This is often managed via `position/trading-stop` or parameters within `order/create`.",
      "endpoint": "/v5/position/trading-stop",
      "required_parameters": {
        "category": "String: 'linear', 'inverse', 'option'.",
        "symbol": "Trading pair (e.g., BTCUSDT).",
        "stopLoss": "The stop loss price level. Pass an empty string '' to remove SL.",
        "takeProfit": "The take profit price level. Pass an empty string '' to remove TP.",
        "slTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for stop loss.",
        "tpTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for take profit.",
        "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Specifies which side of the position to apply SL/TP to."
      },
      "optional_parameters": {
        "orderLinkId": "Custom unique order ID (max 36 characters) for the SL/TP order itself.",
        "tpslMode": "Enum: 'Full' or 'Partial'. Specifies if SL/TP should close the entire position or a part.",
        "reduceOnly": "Boolean: 'true' or 'false'. If true, SL/TP orders can only reduce existing positions."
      }
    },
    "batch_operations": {
      "place_batch_order": {
        "description": "Place multiple orders in bulk. Currently only supported for USDC Options, but Bybit may expand this.",
        "endpoint": "/v5/order/create-batch",
        "required_parameters": {
          "category": "String: 'option'. (This might be broader in future updates)",
          "request": "A JSON string or dictionary containing a list of order dictionaries. Each order dictionary follows the structure of a single order creation request."
        }
      },
      "amend_batch_order": {
        "description": "Modify multiple active orders in bulk.",
        "endpoint": "/v5/order/amend-batch",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "request": "A JSON string or dictionary containing a list of amendment requests. Each request typically includes orderId or orderLinkId, and parameters to change (e.g., 'price', 'qty')."
        }
      },
      "cancel_batch_order": {
        "description": "Cancel multiple active orders in bulk.",
        "endpoint": "/v5/order/cancel-batch",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "request": "A JSON string or dictionary containing a list of order IDs or orderLinkIds to cancel."
        }
      }
    }
  },
  "position_management": {
    "position_queries": {
      "get_positions": {
        "description": "Retrieve all open positions for a specified account type and symbol.",
        "endpoint": "/v5/position/list",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT). Optional: if omitted, returns positions for all symbols in the category."
        },
        "optional_parameters": {
          "accountType": "Enum: 'UNIFIED', 'CONTRACT', 'SPOT', 'FUND', 'ALL'. Specifies the account to query from. Default depends on category.",
          "positionMode": "Enum: 'BothSides', 'OneWay'. For contract categories. Filters positions by mode."
        }
      },
      "get_closed_pnl": {
        "description": "Retrieve historical records of closed profit and loss (PNL).",
        "endpoint": "/v5/position/closed-pnl",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT). Optional: if omitted, returns PNL for all symbols in the category.",
          "startTime": "Start timestamp in milliseconds.",
          "endTime": "End timestamp in milliseconds."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 50, max: 200).",
          "cursor": "For pagination, use the cursor returned in the previous response."
        }
      }
    },
    "position_configuration": {
      "set_leverage": {
        "description": "Adjust the leverage for a specific trading pair. This applies to open positions and future orders.",
        "endpoint": "/v5/position/set-leverage",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'. Not applicable for spot.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "buyLeverage": "Leverage for buy-side positions.",
          "sellLeverage": "Leverage for sell-side positions."
        },
        "optional_parameters": {
          "accountType": "Enum: 'UNIFIED', 'CONTRACT'. Specifies account type for leverage adjustment."
        }
      },
      "switch_margin_mode": {
        "description": "Switch between Isolated Margin and Cross Margin modes for contract trading.",
        "endpoint": "/v5/position/switch-isolated",
        "required_parameters": {
          "category": "String: 'linear', 'inverse'. Not applicable for spot or options.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "mode": "Integer: 3 for 'Both Sides' (Hedged mode), 5 for 'Single Side' (One-way mode). For Unified Account. For Classic account, use 'ISOLATED' or 'CROSSED' string values via different endpoints or specific parameters."
        },
        "notes": "The `mode` parameter values (3, 5) are specific to Unified Account. Classic account margin mode switching is handled differently or implicitly."
      },
      "set_trading_stop": {
        "description": "Set or update Stop Loss and Take Profit levels for an existing position.",
        "endpoint": "/v5/position/trading-stop",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "stopLoss": "The stop loss price level. Pass an empty string '' to remove SL.",
          "takeProfit": "The take profit price level. Pass an empty string '' to remove TP.",
          "slTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for stop loss.",
          "tpTriggerBy": "Enum: 'LastPrice', 'IndexPrice', 'MarkPrice'. Trigger for take profit.",
          "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Specifies which side of the position to apply SL/TP to."
        },
        "optional_parameters": {
          "orderLinkId": "Custom unique order ID (max 36 characters) for the SL/TP order itself.",
          "tpslMode": "Enum: 'Full' or 'Partial'. Specifies if SL/TP should close the entire position or a part.",
          "reduceOnly": "Boolean: 'true' or 'false'. If true, SL/TP orders can only reduce existing positions."
        }
      },
      "set_risk_limit": {
        "description": "Set the risk limit for a specified symbol. This controls the maximum position size at a given leverage.",
        "endpoint": "/v5/position/set-risk-limit",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "riskId": "The ID of the risk limit to set. This ID can be obtained from `/v5/position/risk-limit` or Bybit's documentation."
        },
        "optional_parameters": {
          "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Applicable for contract categories and hedge mode."
        }
      },
      "add_margin": {
        "description": "Add or reduce margin for an existing position. Positive amount adds margin, negative amount reduces it.",
        "endpoint": "/v5/position/add-margin",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "amount": "Margin amount to add/reduce (in quote currency units for linear/option, base currency units for inverse). Must be a positive value for adding margin.",
          "type": "Enum: 'Add' or 'Reduce'. Specifies the operation."
        },
        "optional_parameters": {
          "positionIdx": "Integer: 0 (one-way mode), 1 (buy side in hedge mode), 2 (sell side in hedge mode). Applicable for contract categories and hedge mode."
        }
      }
    }
  },
  "account_and_wallet_functions": {
    "account_information": {
      "get_wallet_balance": {
        "description": "Retrieve wallet balances for specified account types.",
        "endpoint": "/v5/account/wallet-balance",
        "required_parameters": {
          "accountType": "Enum: 'UNIFIED', 'CONTRACT', 'SPOT', 'FUND', 'ALL'. Specifies the account type(s) to query."
        },
        "optional_parameters": {
          "coin": "Specific coin (e.g., BTC) to get balance for. Optional."
        }
      },
      "get_account_info": {
        "description": "Retrieve overall account information, including account type, KYC status, and status.",
        "endpoint": "/v5/account/info",
        "required_parameters": {},
        "optional_parameters": {
          "accountType": "Enum: 'UNIFIED', 'CONTRACT', 'SPOT'."
        }
      },
      "get_fee_rate": {
        "description": "View trading fee rates for specified symbols and account types.",
        "endpoint": "/v5/account/fee-rate",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option', 'spot'.",
          "accountType": "Enum: 'UNIFIED', 'CONTRACT', 'SPOT', 'FUND'. Specifies the account type."
        },
        "optional_parameters": {
          "symbol": "Trading pair (e.g., BTCUSDT). Optional: if omitted, returns fee rates for all symbols in the category/account type."
        }
      },
      "get_transaction_log": {
        "description": "Retrieve transaction history (e.g., orders, trades, withdrawals, deposits).",
        "endpoint": "/v5/account/transaction-log",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "accountType": "Enum: 'UNIFIED', 'CONTRACT', 'SPOT', 'FUND'. Specifies the account type."
        },
        "optional_parameters": {
          "symbol": "Trading pair (e.g., BTCUSDT). Optional.",
          "startTime": "Start timestamp in milliseconds. Optional.",
          "endTime": "End timestamp in milliseconds. Optional.",
          "type": "Enum: 'ORDER', 'TRADE', 'TRANSFER', 'WITHDRAWAL', 'DEPOSIT', 'LIQUIDATION', etc. Filters transaction types. Optional.",
          "limit": "Number of results per page (default: 20, max: 200).",
          "cursor": "For pagination."
        }
      }
    }
  },
  "market_data_functions": {
    "public_market_data": {
      "get_tickers": {
        "description": "Get latest price snapshots for trading pairs.",
        "endpoint": "/v5/market/tickers",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'."
        },
        "optional_parameters": {
          "symbol": "Trading pair (e.g., BTCUSDT). Optional: if omitted, returns tickers for all symbols in the category."
        }
      },
      "get_orderbook": {
        "description": "Retrieve the order book depth for a specified trading pair.",
        "endpoint": "/v5/market/orderbook",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "limit": "Integer: Depth of order book to retrieve. Options: 1, 25, 50, 100, 200, 500."
        },
        "optional_parameters": {
          "level": "Integer: Alias for 'limit' parameter (deprecated, use limit)."
        }
      },
      "get_kline": {
        "description": "Get historical candlestick data for a specified trading pair and interval.",
        "endpoint": "/v5/market/kline",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "interval": "String: Time interval for candlesticks. Common values: '1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D' (Daily), 'W' (Weekly), 'M' (Monthly).",
          "start": "Start timestamp in milliseconds.",
          "end": "End timestamp in milliseconds."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 200, max: 1000)."
        }
      },
      "get_mark_price_kline": {
        "description": "Get historical mark price candlestick data for contract categories.",
        "endpoint": "/v5/market/mark-price-kline",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "interval": "String: Time interval for candlesticks.",
          "start": "Start timestamp in milliseconds.",
          "end": "End timestamp in milliseconds."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 200, max: 1000)."
        }
      },
      "get_index_price_kline": {
        "description": "Get historical index price candlestick data for contract categories.",
        "endpoint": "/v5/market/index-price-kline",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT).",
          "interval": "String: Time interval for candlesticks.",
          "start": "Start timestamp in milliseconds.",
          "end": "End timestamp in milliseconds."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 200, max: 1000)."
        }
      },
      "get_premium_index_price_kline": {
        "description": "Get historical premium index candlestick data for option categories.",
        "endpoint": "/v5/market/premium-index-price-kline",
        "required_parameters": {
          "category": "String: 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDSOpt).",
          "interval": "String: Time interval for candlesticks.",
          "start": "Start timestamp in milliseconds.",
          "end": "End timestamp in milliseconds."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 200, max: 1000)."
        }
      },
      "query_recent_trade": {
        "description": "Get recent public trades for a specified trading pair.",
        "endpoint": "/v5/market/recent-trade",
        "required_parameters": {
          "category": "String: 'spot', 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT)."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 50, max: 1000)."
        }
      },
      "get_recent_liquidations": {
        "description": "Retrieve recent liquidation orders via REST API.",
        "endpoint": "/v5/market/liquidation-stream",
        "required_parameters": {
          "category": "String: 'linear', 'inverse', 'option'.",
          "symbol": "Trading pair (e.g., BTCUSDT)."
        },
        "optional_parameters": {
          "limit": "Number of results per page (default: 50, max: 200)."
        },
        "notes": "This endpoint fetches recent liquidations via REST, distinct from the WebSocket `liquidation_stream`."
      }
    },
    "legacy_pybit_functions": {
      "description": "These functions are deprecated and have been superseded by the V5 API structure. It is recommended to use the V5 endpoints directly.",
      "place_active_order": "Deprecated function for active orders. Use `/v5/order/create`.",
      "cancel_active_order": "Deprecated function for active orders. Use `/v5/order/cancel` or `/v5/order/cancel-batch`.",
      "place_conditional_order": "Deprecated function for conditional orders. Use `/v5/order/create` with trigger parameters.",
      "cancel_conditional_order": "Deprecated function for conditional orders. Use `/v5/order/cancel` or `/v5/order/cancel-batch`.",
      "query_active_order": "Deprecated function for active orders. Use `/v5/order/list`.",
      "query_conditional_order": "Deprecated function for conditional orders. Use `/v5/order/list` with specific query parameters.",
      "replace_active_order": "Deprecated function for replacing active orders. Use `/v5/order/amend` or `/v5/order/amend-batch`."
    },
    "order_parameters": {
      "parameter_definitions": {
        "category_values": ["spot", "linear", "inverse", "option"],
        "accountType_values": ["UNIFIED", "CONTRACT", "SPOT", "FUND", "ALL"],
        "interval_values": ["1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D", "W", "M"],
        "orderType_options": ["Limit", "Market", "StopLimit", "StopMarket"],
        "side_options": ["Buy", "Sell"],
        "timeInForce_options": ["GTC", "IOC", "FOK", "PostOnly"],
        "triggerBy_options": ["LastPrice", "IndexPrice", "MarkPrice"],
        "tpslMode_options": ["Full", "Partial"],
        "positionMode_options": ["BothSides", "OneWay"],
        "margin_mode_options_unified": ["3 (Both Sides)", "5 (Single Side)"],
        "margin_mode_options_classic": ["ISOLATED", "CROSSED"]
      },
      "rate_limits": {
        "description": "Bybit API has rate limits to prevent abuse. These typically apply per API key and/or IP address.",
        "market_data": "120 requests per minute (e.g., /v5/market/* endpoints).",
        "order_management": "60 requests per minute (e.g., /v5/order/* endpoints).",
        "position_queries": "120 requests per minute (e.g., /v5/position/* endpoints).",
        "account_management": "60 requests per minute (e.g., /v5/account/* endpoints).",
        "websocket_streams": "Connection limits apply, and subscription limits per connection are common (e.g., 200 public streams, 100 private streams). Refer to Bybit documentation for exact numbers."
      },
      "best_practices": [
        "Securely manage API keys and secrets. Do not hardcode them directly into scripts; use environment variables or secure configuration files.",
        "Always test your trading bot thoroughly on the Bybit testnet environment before deploying to the live mainnet.",
        "Implement robust error handling. Handle API errors, network issues, and unexpected responses gracefully. Use retry mechanisms with exponential backoff for transient errors.",
        "Utilize `orderLinkId` for all orders. This unique identifier ensures idempotency and helps track orders, preventing duplicate order placements or cancellations.",
        "Before placing orders, always fetch and check symbol information (e.g., via `/v5/market/instruments-info`) to understand precision rules for price, quantity, and lot size. Ensure your order parameters comply.",
        "For WebSocket connections, implement PING/PONG mechanisms to maintain the connection and detect disconnections promptly. Handle reconnection logic.",
        "Be mindful of API rate limits. Implement client-side rate limiting or request throttling if necessary to avoid hitting limits and getting blocked.",
        "Keep detailed logs of all API requests, responses, orders placed, trades executed, and any errors encountered. This is crucial for debugging and auditing.",
        "Understand the differences between account types (Unified vs. Classic) and how they affect parameters like `category`, `positionMode`, and margin settings.",
        "For historical data queries (e.g., klines, PNL), specify `startTime` and `endTime` to retrieve relevant data efficiently and avoid excessive data transfer or API limits.",
        "When querying lists of items (orders, positions, logs), use pagination parameters (`limit`, `cursor`) to process data in manageable chunks.",
        "Consider using a well-maintained Bybit API wrapper library (e.g., `pybit`) which abstracts many of the complexities of signing requests, handling responses, and managing connections."
      ],
      "symbol_information_retrieval": {
        "description": "Essential for trading. Fetch symbol details to get valid order parameters and contract specifications.",
        "endpoint": "/v5/market/instruments-info",
        "usage": "Call this endpoint for each symbol you intend to trade to retrieve `lotSizeFilter`, `priceFilter`, `leverageFilter`, and other crucial trading rules.",
        "key_filters_to_check": ["lotSizeFilter", "priceFilter", "leverageFilter", "tickSizeFilter", "maxLeverage"]
      }
    }
  }
}
