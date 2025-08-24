UP009 UTF-8 encoding declaration is unnecessary
 --> stupdated.py:2:1
  |
1 | #!/usr/bin/env python3
2 | # -*- coding: utf-8 -*-
  | ^^^^^^^^^^^^^^^^^^^^^^^
3 | import os
4 | import time
  |
help: Remove unnecessary coding comment

W293 Blank line contains whitespace
   --> stupdated.py:344:1
    |
342 | …         except json.JSONDecodeError:
343 | …             print(f"Warning: Could not decode PARTIAL_TP_TARGETS from environment variable: {partial_tp_targets_str}. Using default…
344 | …     
    ^^^^^^^^
345 | …     self.VOLATILITY_ADJUSTED_SIZING_ENABLED = os.getenv("VOLATILITY_ADJUSTED_SIZING_ENABLED", str(self.VOLATILITY_ADJUSTED_SIZING_E…
346 | …     self.VOLATILITY_WINDOW = int(os.getenv("VOLATILITY_WINDOW", self.VOLATILITY_WINDOW))
    |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
   --> stupdated.py:556:101
    |
554 |         max_order_qty = safe_decimal(unified_lot_size_filter.get('maxOrderQty', lot_size_filter.get('maxOrderQty', '1e9')))
555 |
556 |         # Max/Min Order Amount for position value limits (in quote currency, e.g., USD for USDT pairs)
    |                                                                                                     ^^
557 |         max_position_value_usd = safe_decimal(unified_lot_size_filter.get('maxOrderAmt', '1e9'))
558 |         min_position_value_usd = safe_decimal(unified_lot_size_filter.get('minOrderAmt', '1')) # minOrderQty is for base units, minOr…
    |

W293 Blank line contains whitespace
   --> stupdated.py:563:1
    |
561 |         max_leverage = safe_decimal(leverage_filter.get('maxLeverage', '100')) # Default max leverage
562 |         leverage_step = safe_decimal(leverage_filter.get('leverageStep', '0.1'))
563 |         
    | ^^^^^^^^
564 |         contract_value = safe_decimal(inst.get('contractValue', '1')) # e.g., 1 for BTCUSDT perpetual
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
   --> stupdated.py:713:1
    |
711 |             # Calculate dollar risk based on MAX_RISK_PER_TRADE_BALANCE_PCT
712 |             dollar_risk_per_trade = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
713 |             
    | ^^^^^^^^^^^^
714 |             # Position size is inversely proportional to volatility (ATR)
715 |             # Dollar value of position = (Dollar Risk / ATR_in_dollars) * TARGET_RISK_ATR_MULTIPLIER
    |
help: Remove whitespace from blank line

W505 Doc line too long (123 > 100)
   --> stupdated.py:718:101
    |
716 | …     # Here, ATR_in_dollars is effectively stop_distance_price for a 1x ATR stop.
717 | …     # So, if stop_distance_price is considered 1 ATR unit, then:
718 | …     # position_value_usd = dollar_risk_per_trade / (stop_distance_price / entry_price) * TARGET_RISK_ATR_MULTIPLIER
    |                                                                                               ^^^^^^^^^^^^^^^^^^^^^^^
719 | …     # Simplified: position_value_usd = (dollar_risk_per_trade * entry_price) / stop_distance_price * TARGET_RISK_ATR_MULTIPLIER
    |

W505 Doc line too long (135 > 100)
   --> stupdated.py:719:101
    |
717 | …ed 1 ATR unit, then:
718 | …rade / (stop_distance_price / entry_price) * TARGET_RISK_ATR_MULTIPLIER
719 | …ar_risk_per_trade * entry_price) / stop_distance_price * TARGET_RISK_ATR_MULTIPLIER
    |                                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
720 | …
721 | … USD / (ATR * ATR_MULTIPLIER) = position size in base units
    |

W293 Blank line contains whitespace
   --> stupdated.py:720:1
    |
718 | …     # position_value_usd = dollar_risk_per_trade / (stop_distance_price / entry_price) * TARGET_RISK_ATR_MULTIPLIER
719 | …     # Simplified: position_value_usd = (dollar_risk_per_trade * entry_price) / stop_distance_price * TARGET_RISK_ATR_MULTIPLIER
720 | …     
^^^^^^^^^^^^
721 | …     # A more direct approach: Risk amount in USD / (ATR * ATR_MULTIPLIER) = position size in base units
722 | …     # Then convert base units to USD value.
    |
help: Remove whitespace from blank line

W505 Doc line too long (111 > 100)
   --> stupdated.py:721:101
    |
719 | …     # Simplified: position_value_usd = (dollar_risk_per_trade * entry_price) / stop_distance_price * TARGET_RISK_ATR_MULTIPLIER
720 | …     
721 | …     # A more direct approach: Risk amount in USD / (ATR * ATR_MULTIPLIER) = position size in base units
    |                                                                                               ^^^^^^^^^^^
722 | …     # Then convert base units to USD value.
723 | …     # Risk_USD = Pos_Qty * Stop_Loss_Distance_USD
    |

W505 Doc line too long (127 > 100)
   --> stupdated.py:725:101
    |
723 |             # Risk_USD = Pos_Qty * Stop_Loss_Distance_USD
724 |             # Pos_Qty = Risk_USD / Stop_Loss_Distance_USD
725 |             # Here, we want to maintain dollar risk, so Risk_USD is defined by account_balance * MAX_RISK_PER_TRADE_BALANCE_PCT
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
726 |             # The stop_loss_price is already calculated.
    |

W293 Blank line contains whitespace
   --> stupdated.py:727:1
    |
725 |             # Here, we want to maintain dollar risk, so Risk_USD is defined by account_balance * MAX_RISK_PER_TRADE_BALANCE_PCT
726 |             # The stop_loss_price is already calculated.
727 |             
    | ^^^^^^^^^^^^
728 |             # Let's re-think: the goal is to risk 'X' dollars per trade.
729 |             # Risk_USD = Position_Quantity * (Entry_Price - Stop_Loss_Price)
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
   --> stupdated.py:732:1
    |
730 |             # Position_Quantity = Risk_USD / (Entry_Price - Stop_Loss_Price)
731 |             # Position_Value_USD = Position_Quantity * Entry_Price
732 |             
    | ^^^^^^^^^^^^
733 |             # With volatility adjustment, we want to define the stop distance based on ATR.
734 |             # Let's say we define the stop loss as `ATR * TARGET_RISK_ATR_MULTIPLIER`.
    |
help: Remove whitespace from blank line

W505 Doc line too long (110 > 100)
   --> stupdated.py:735:101
    |
733 |             # With volatility adjustment, we want to define the stop distance based on ATR.
734 |             # Let's say we define the stop loss as `ATR * TARGET_RISK_ATR_MULTIPLIER`.
735 |             # Effective_Stop_Distance_USD = current_atr * Decimal(str(self.config.TARGET_RISK_ATR_MULTIPLIER))
    |                                                                                                     ^^^^^^^^^^
736 |             # If the calculated stop_loss_price is already based on a percentage, we use that.
737 |             # The feature description says "reduces size to maintain equivalent dollar risk".
    |

W505 Doc line too long (128 > 100)
   --> stupdated.py:738:101
    |
736 |             # If the calculated stop_loss_price is already based on a percentage, we use that.
737 |             # The feature description says "reduces size to maintain equivalent dollar risk".
738 |             # This implies `risk_amount_usdt` is the primary driver, but `stop_distance_pct` changes with volatility implicitly.
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
739 |             
740 |             # Let's adjust based on the *actual* stop_distance_price (which we assume reflects current volatility)
    |

W293 Blank line contains whitespace
   --> stupdated.py:739:1
    |
737 |             # The feature description says "reduces size to maintain equivalent dollar risk".
738 |             # This implies `risk_amount_usdt` is the primary driver, but `stop_distance_pct` changes with volatility implicitly.
739 |             
    | ^^^^^^^^^^^^
740 |             # Let's adjust based on the *actual* stop_distance_price (which we assume reflects current volatility)
741 |             # The risk_percent from config is the maximum allowed.
    |
help: Remove whitespace from blank line

W505 Doc line too long (114 > 100)
   --> stupdated.py:740:101
    |
738 |             # This implies `risk_amount_usdt` is the primary driver, but `stop_distance_pct` changes with volatility implicitly.
739 |             
740 |             # Let's adjust based on the *actual* stop_distance_price (which we assume reflects current volatility)
    |                                                                                                     ^^^^^^^^^^^^^^
741 |             # The risk_percent from config is the maximum allowed.
742 |             risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
    |

W293 Blank line contains whitespace
   --> stupdated.py:744:1
    |
742 |             risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
743 |             position_value_usd_unadjusted = (risk_amount_usdt * entry_price) / stop_distance_price
744 |             
    | ^^^^^^^^^^^^
745 |             # If the market is more volatile (larger stop_distance_price for same risk_percent),
746 |             # the calculated position_value_usd_unadjusted will be smaller, which is the desired effect.
    |
help: Remove whitespace from blank line

W505 Doc line too long (104 > 100)
   --> stupdated.py:746:101
    |
745 |             # If the market is more volatile (larger stop_distance_price for same risk_percent),
746 |             # the calculated position_value_usd_unadjusted will be smaller, which is the desired effect.
    |                                                                                                     ^^^^
747 |             # The 'TARGET_RISK_ATR_MULTIPLIER' might be better used to dynamically set the SL,
748 |             # but the JSON suggests it's for sizing.
    |

W505 Doc line too long (127 > 100)
   --> stupdated.py:750:101
    |
748 |             # but the JSON suggests it's for sizing.
749 |             # For now, let's use it to scale the calculated position value based on volatility.
750 |             # The existing logic already implicitly does this: smaller stop_distance_price -> larger position_value_needed_usd.
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^
751 |             # So, if stop_loss_price is set by ATR, then this calculation is already volatility-adjusted.
752 |             # If the stop_loss_price is fixed percentage, then this feature needs to override that.
    |

W505 Doc line too long (105 > 100)
   --> stupdated.py:751:101
    |
749 |             # For now, let's use it to scale the calculated position value based on volatility.
750 |             # The existing logic already implicitly does this: smaller stop_distance_price -> larger position_value_needed_usd.
751 |             # So, if stop_loss_price is set by ATR, then this calculation is already volatility-adjusted.
    |                                                                                                     ^^^^^
752 |             # If the stop_loss_price is fixed percentage, then this feature needs to override that.
    |

W293 Blank line contains whitespace
   --> stupdated.py:753:1
    |
751 |             # So, if stop_loss_price is set by ATR, then this calculation is already volatility-adjusted.
752 |             # If the stop_loss_price is fixed percentage, then this feature needs to override that.
753 |             
    | ^^^^^^^^^^^^
754 |             # Let's assume the SL provided to this function *is* the chosen stop based on strategy,
755 |             # and we want to size the position such that the dollar risk is limited.
    |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
   --> stupdated.py:756:101
    |
754 |             # Let's assume the SL provided to this function *is* the chosen stop based on strategy,
755 |             # and we want to size the position such that the dollar risk is limited.
756 |             # The description "In high volatility, it reduces size to maintain equivalent dollar risk"
    |                                                                                                     ^^
757 |             # means that if the stop_distance_price (which can be derived from ATR) is large, the position size should be small.
758 |             # This is exactly what `risk_amount_usdt / stop_distance_pct` does.
    |

W505 Doc line too long (128 > 100)
   --> stupdated.py:757:101
    |
755 |             # and we want to size the position such that the dollar risk is limited.
756 |             # The description "In high volatility, it reduces size to maintain equivalent dollar risk"
757 |             # means that if the stop_distance_price (which can be derived from ATR) is large, the position size should be small.
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
758 |             # This is exactly what `risk_amount_usdt / stop_distance_pct` does.
759 |             # The `TARGET_RISK_ATR_MULTIPLIER` and `VOLATILITY_WINDOW` are more for determining the stop_loss_price itself.
    |

W505 Doc line too long (123 > 100)
   --> stupdated.py:759:101
    |
757 |             # means that if the stop_distance_price (which can be derived from ATR) is large, the position size should be small.
758 |             # This is exactly what `risk_amount_usdt / stop_distance_pct` does.
759 |             # The `TARGET_RISK_ATR_MULTIPLIER` and `VOLATILITY_WINDOW` are more for determining the stop_loss_price itself.
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^
760 |             # For now, let's stick to the current definition of `stop_distance_price` and
761 |             # ensure `risk_amount_usdt` is capped by `MAX_RISK_PER_TRADE_BALANCE_PCT`.
    |

W293 Blank line contains whitespace
   --> stupdated.py:762:1
    |
760 |             # For now, let's stick to the current definition of `stop_distance_price` and
761 |             # ensure `risk_amount_usdt` is capped by `MAX_RISK_PER_TRADE_BALANCE_PCT`.
762 |             
    | ^^^^^^^^^^^^
763 |             # The existing logic for `position_value_needed_usd` is already risk-adjusted.
764 |             # If `stop_loss_price` is dynamic (e.g., based on ATR), then this calculation inherently adjusts for volatility.
    |
help: Remove whitespace from blank line

W505 Doc line too long (124 > 100)
   --> stupdated.py:764:101
    |
763 |             # The existing logic for `position_value_needed_usd` is already risk-adjusted.
764 |             # If `stop_loss_price` is dynamic (e.g., based on ATR), then this calculation inherently adjusts for volatility.
    |                                                                                                     ^^^^^^^^^^^^^^^^^^^^^^^^
765 |             # So, we just need to use `MAX_RISK_PER_TRADE_BALANCE_PCT` instead of `risk_percent` if enabled.
    |

W505 Doc line too long (108 > 100)
   --> stupdated.py:765:101
    |
763 |             # The existing logic for `position_value_needed_usd` is already risk-adjusted.
764 |             # If `stop_loss_price` is dynamic (e.g., based on ATR), then this calculation inherently adjusts for volatility.
765 |             # So, we just need to use `MAX_RISK_PER_TRADE_BALANCE_PCT` instead of `risk_percent` if enabled.
    |                                                                                                     ^^^^^^^^
766 |             
767 |             risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
    |

W293 Blank line contains whitespace
   --> stupdated.py:766:1
    |
764 |             # If `stop_loss_price` is dynamic (e.g., based on ATR), then this calculation inherently adjusts for volatility.
765 |             # So, we just need to use `MAX_RISK_PER_TRADE_BALANCE_PCT` instead of `risk_percent` if enabled.
766 |             
    | ^^^^^^^^^^^^
767 |             risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
768 |             position_value_usd_unadjusted = risk_amount_usdt / (stop_distance_price / entry_price) # This is position value in USD
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
   --> stupdated.py:769:1
    |
767 |             risk_amount_usdt = account_balance_usdt * Decimal(str(self.config.MAX_RISK_PER_TRADE_BALANCE_PCT))
768 |             position_value_usd_unadjusted = risk_amount_usdt / (stop_distance_price / entry_price) # This is position value in USD
769 |             
    | ^^^^^^^^^^^^
770 |         else: # Original logic
771 |             # Calculate risk amount in USDT
    |
help: Remove whitespace from blank line

W505 Doc line too long (104 > 100)
   --> stupdated.py:784:101
    |
782 |         max_tradeable_value_usd = account_balance_usdt * leverage
783 |
784 |         # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
    |                                                                                                     ^^^^
785 |         position_value_usd = min(
786 |             position_value_usd_unadjusted,
    |

W293 Blank line contains whitespace
   --> stupdated.py:790:1
    |
788 |             specs.max_position_value # Apply Bybit's specific max order value if available
789 |         )
790 |         
    | ^^^^^^^^
791 |         # FEATURE: Max Position Size USD from config
792 |         position_value_usd = min(position_value_usd, Decimal(str(self.config.MAX_POSITION_SIZE_USD)))
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
   --> stupdated.py:799:1
    |
797 | …         self.logger.warning(f"Calculated position value ({position_value_usd:.{self.precision.get_decimal_places(symbol)[0]}f} USD)…
798 | …         position_value_usd = specs.min_position_value
799 | …     
    ^^^^^^^^
800 | …     # FEATURE: Min Position Size USD from config
801 | …     if position_value_usd < Decimal(str(self.config.MIN_POSITION_SIZE_USD)):
    |
help: Remove whitespace from blank line

W505 Doc line too long (148 > 100)
   --> stupdated.py:861:101
    |
859 | …e bot's api_call method
860 | …ailing
861 | …e': 'Buy'/'Sell', 'trail_percent': Decimal, 'initial_sl': Decimal, 'initial_tp': Decimal}}
    |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
862 | …
863 | …c
    |

W293 Blank line contains whitespace
   --> stupdated.py:928:1
    |
926 |         Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
927 |         For Bybit's native `callbackRate`, this usually means ensuring it's still active.
928 |         
    | ^^^^^^^^
929 |         FEATURE: Profit Target Trailing Stop (Dynamic Trailing)
930 |         Adjusts the trailing stop percentage based on current profit tiers.
    |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
   --> stupdated.py:945:101
    |
944 |         if self.config.DYNAMIC_TRAILING_ENABLED:
945 |             # Sort tiers by profit_pct_trigger in descending order to find the highest applicable tier
    |                                                                                                     ^^
946 |             sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
    |

W293 Blank line contains whitespace
   --> stupdated.py:947:1
    |
945 | …     # Sort tiers by profit_pct_trigger in descending order to find the highest applicable tier
946 | …     sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
947 | …     
^^^^^^^^^^^^
948 | …     for tier in sorted_tiers:
949 | …         if current_unrealized_pnl_pct >= Decimal(str(tier['profit_pct_trigger'])) * Decimal('100'): # Convert to % for comparison
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
   --> stupdated.py:963:1
    |
961 |         # This will override any existing trailing stop settings for the symbol.
962 |         ts_info = self.active_trailing_stops[symbol]
963 |         
    | ^^^^^^^^
964 |         # Update the active_trailing_stops with the new effective_trail_pct BEFORE calling initialize
965 |         # to ensure it's consistent if initialize fails.
    |
help: Remove whitespace from blank line

W505 Doc line too long (101 > 100)
   --> stupdated.py:964:101
    |
962 |         ts_info = self.active_trailing_stops[symbol]
963 |         
964 |         # Update the active_trailing_stops with the new effective_trail_pct BEFORE calling initialize
    |                                                                                                     ^
965 |         # to ensure it's consistent if initialize fails.
966 |         ts_info['trail_percent'] = effective_trail_pct
    |

W293 Blank line contains whitespace
   --> stupdated.py:967:1
    |
965 |         # to ensure it's consistent if initialize fails.
966 |         ts_info['trail_percent'] = effective_trail_pct
967 |         
    | ^^^^^^^^
968 |         return self.initialize_trailing_stop(
969 |             symbol=symbol,
    |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1005:1
     |
1003 | …     self.logger = logger
1004 | …     self.price_precision = price_precision
1005 | …     
     ^^^^^^^^
1006 | …     if not self.recipient_number:
1007 | …         self.logger.warning(Fore.YELLOW + "TERMUX_SMS_RECIPIENT_NUMBER not set. SMS notifications will be disabled." + Style.RESET…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1012:1
     |
1010 |             self.logger.info(Fore.CYAN + f"Termux SMS Notifier initialized for {self.recipient_number}." + Style.RESET_ALL)
1011 |             self.is_enabled = True
1012 |     
     | ^^^^
1013 |     def send_sms(self, message: str):
1014 |         """Send message via Termux SMS."""
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1017:1
     |
1015 |         if not self.is_enabled:
1016 |             return
1017 |         
     | ^^^^^^^^
1018 |         try:
1019 |             subprocess.run(["termux-sms-send", "-n", self.recipient_number, message], check=True, capture_output=True)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1027:1
     |
1025 |         except Exception as e:
1026 |             self.logger.error(Fore.RED + f"Failed to send Termux SMS: {e}" + Style.RESET_ALL)
1027 |             
     | ^^^^^^^^^^^^
1028 |     def send_trade_alert(self, side: str, symbol: str, price: float, sl: float, tp: float, reason: str):
1029 |         emoji = "🟢" if side == "Buy" else "🔴"
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1032:1
     |
1030 |         message = f"{emoji} {side} {symbol}\nEntry: ${price:.{self.price_precision}f}\nSL: ${sl:.{self.price_precision}f}\nTP: ${tp:…
1031 |         self.send_sms(message)
1032 |         
     | ^^^^^^^^
1033 |     def send_pnl_update(self, pnl: float, balance: float):
1034 |         emoji = "✅" if pnl > 0 else "❌"
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1105:29
     |
1103 |             'positionIdx': positionIdx
1104 |         }
1105 |         if price is not None: params['price'] = price
     |                             ^
1106 |         if stopLoss is not None:
1107 |             params['stopLoss'] = stopLoss
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1108:27
     |
1106 |         if stopLoss is not None:
1107 |             params['stopLoss'] = stopLoss
1108 |             if slOrderType: params['slOrderType'] = slOrderType
     |                           ^
1109 |         if takeProfit is not None:
1110 |             params['takeProfit'] = takeProfit
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1111:27
     |
1109 |         if takeProfit is not None:
1110 |             params['takeProfit'] = takeProfit
1111 |             if tpOrderType: params['tpOrderType'] = tpOrderType
     |                           ^
1112 |         if tpslMode is not None: params['tpslMode'] = tpslMode
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1112:32
     |
1110 |             params['takeProfit'] = takeProfit
1111 |             if tpOrderType: params['tpOrderType'] = tpOrderType
1112 |         if tpslMode is not None: params['tpslMode'] = tpslMode
     |                                ^
1113 |
1114 |         return self.session.place_order(**params)
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1126:36
     |
1124 |             'side': side # Side is required for set_trading_stop on unified account
1125 |         }
1126 |         if callbackRate is not None: params['callbackRate'] = callbackRate
     |                                    ^
1127 |         if stopLoss is not None:
1128 |             params['stopLoss'] = stopLoss
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1129:27
     |
1127 |         if stopLoss is not None:
1128 |             params['stopLoss'] = stopLoss
1129 |             if slOrderType: params['slOrderType'] = slOrderType
     |                           ^
1130 |         if takeProfit is not None:
1131 |             params['takeProfit'] = takeProfit
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1132:27
     |
1130 |         if takeProfit is not None:
1131 |             params['takeProfit'] = takeProfit
1132 |             if tpOrderType: params['tpOrderType'] = tpOrderType
     |                           ^
1133 |         if tpslMode is not None: params['tpslMode'] = tpslMode
1134 |         return self.session.set_trading_stop(**params)
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1133:32
     |
1131 |             params['takeProfit'] = takeProfit
1132 |             if tpOrderType: params['tpOrderType'] = tpOrderType
1133 |         if tpslMode is not None: params['tpslMode'] = tpslMode
     |                                ^
1134 |         return self.session.set_trading_stop(**params)
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1140:19
     |
1138 |         """Fetches the chronicles of past orders."""
1139 |         params = {'category': category or self._default_category, 'symbol': symbol, 'limit': limit}
1140 |         if orderId: params['orderId'] = orderId
     |                   ^
1141 |         return self.session.get_order_history(**params)
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1147:18
     |
1145 |         """Reveals orders that currently lie in wait."""
1146 |         params = {'category': category or self._default_category, 'limit': limit}
1147 |         if symbol: params['symbol'] = symbol
     |                  ^
1148 |         if orderId: params['orderId'] = orderId
1149 |         return self.session.get_open_orders(**params)
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:1148:19
     |
1146 |         params = {'category': category or self._default_category, 'limit': limit}
1147 |         if symbol: params['symbol'] = symbol
1148 |         if orderId: params['orderId'] = orderId
     |                   ^
1149 |         return self.session.get_open_orders(**params)
     |

W293 Blank line contains whitespace
    --> stupdated.py:1261:1
     |
1259 |     """
1260 |     lock: threading.Lock = field(default_factory=threading.Lock) # Guards against simultaneous writes from different threads
1261 |     
     | ^^^^
1262 |     current_price: Decimal = field(default=Decimal('0.0'))
1263 |     bid_price: Decimal = field(default=Decimal('0.0'))
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1265:1
     |
1263 |     bid_price: Decimal = field(default=Decimal('0.0'))
1264 |     ask_price: Decimal = field(default=Decimal('0.0'))
1265 |     
     | ^^^^
1266 |     ehlers_supertrend_value: Decimal = field(default=Decimal('0.0')) # The actual ST line value
1267 |     ehlers_supertrend_direction: str = field(default="NONE") # e.g., "UP", "DOWN"
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1269:1
     |
1267 |     ehlers_supertrend_direction: str = field(default="NONE") # e.g., "UP", "DOWN"
1268 |     ehlers_filter_value: Decimal = field(default=Decimal('0.0')) # From Ehlers Adaptive Trend custom filter
1269 |     
     | ^^^^
1270 |     adx_value: Decimal = field(default=Decimal('0.0'))
1271 |     adx_plus_di: Decimal = field(default=Decimal('0.0'))
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1274:1
     |
1272 |     adx_minus_di: Decimal = field(default=Decimal('0.0'))
1273 |     adx_trend_strength: str = field(default="N/A") # e.g., "Weak", "Developing", "Strong"
1274 |     
     | ^^^^
1275 |     rsi_value: Decimal = field(default=Decimal('0.0'))
1276 |     rsi_state: str = field(default="N/A") # e.g., "Overbought", "Oversold", "Neutral"
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1290:1
     |
1288 |     unrealized_pnl_pct: Decimal = field(default=Decimal('0.0'))
1289 |     realized_pnl_total: Decimal = field(default=Decimal('0.0')) # Cumulative PnL from closed trades
1290 |     
     | ^^^^
1291 |     last_updated_time: datetime = field(default_factory=datetime.now)
1292 |     bot_status: str = field(default="Initializing")
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:1295:44
     |
1293 |     symbol: str = field(default="")
1294 |     timeframe: str = field(default="")
1295 |     price_precision: int = field(default=3) 
     |                                            ^
1296 |     qty_precision: int = field(default=1)
1297 |     dry_run: bool = field(default=False)
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:1336:1
     |
1334 |         """Renders the entire UI to the console."""
1335 |         self._clear_screen()
1336 |         
     | ^^^^^^^^
1337 |         with self.bot_state.lock:
1338 |             # Create a local copy of the state for consistent display during rendering
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:1339:35
     |
1337 |         with self.bot_state.lock:
1338 |             # Create a local copy of the state for consistent display during rendering
1339 |             state = self.bot_state 
     |                                   ^
1340 |             
1341 |             # Formatting and Coloring Logic
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:1340:1
     |
1338 |             # Create a local copy of the state for consistent display during rendering
1339 |             state = self.bot_state 
1340 |             
     | ^^^^^^^^^^^^
1341 |             # Formatting and Coloring Logic
1342 |             pnl_color_realized = Fore.GREEN if state.realized_pnl_total >= Decimal('0') else Fore.RED
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1358:1
     |
1356 |             elif state.rsi_state == "Oversold":
1357 |                 rsi_color = Fore.GREEN
1358 |             
     | ^^^^^^^^^^^^
1359 |             ehlers_color = Fore.WHITE
1360 |             if state.ehlers_supertrend_direction == "UP":
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1364:1
     |
1362 |             elif state.ehlers_supertrend_direction == "DOWN":
1363 |                 ehlers_color = Fore.LIGHTRED_EX
1364 |             
     | ^^^^^^^^^^^^
1365 |             # --- UI Layout ---
1366 |             # Main Header
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1379:1
     |
1377 | …     status_len_no_color = len(state.bot_status) + len(f" ({'TESTNET' if state.testnet else 'MAINNET'})")
1378 | …     padding_len = 73 - (len("Status: ") + status_len_no_color + len(last_update_text) + len("Last Updated: "))
1379 | …     
 ^^^^^^^^^^^^
1380 | …     print(f"{Fore.CYAN}║ {status_text_display}{' ' * padding_len}{last_update_text} {Fore.CYAN}║{Style.RESET_ALL}")
1381 | …     print(f"{Fore.CYAN}╚═══════════════════════════════════════════════════════════════════════════╝{Style.RESET_ALL}\n")
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1387:1
     |
1385 | …     print(f"{Fore.BLUE}║ MARKET DATA                                                               {Fore.BLUE}║{Style.RESET_ALL}")
1386 | …     print(f"{Fore.BLUE}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
1387 | …     
 ^^^^^^^^^^^^
1388 | …     # Current Price string, 3 decimals
1389 | …     print(f"{Fore.BLUE}║ Current Price:          {Fore.YELLOW}${state.current_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Sty…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1390:1
     |
1388 | …     # Current Price string, 3 decimals
1389 | …     print(f"{Fore.BLUE}║ Current Price:          {Fore.YELLOW}${state.current_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Sty…
1390 | …     
 ^^^^^^^^^^^^
1391 | …     # Bid Price string, 3 decimals
1392 | …     print(f"{Fore.BLUE}║ Bid:                    {Fore.YELLOW}${state.bid_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.R…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1393:1
     |
1391 | …     # Bid Price string, 3 decimals
1392 | …     print(f"{Fore.BLUE}║ Bid:                    {Fore.YELLOW}${state.bid_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.R…
1393 | …     
 ^^^^^^^^^^^^
1394 | …     # Ask Price string, 3 decimals
1395 | …     print(f"{Fore.BLUE}║ Ask:                    {Fore.YELLOW}${state.ask_price:.{state.price_precision}f}{Fore.BLUE:<46}║{Style.R…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1402:1
     |
1400 | …     print(f"{Fore.MAGENTA}║ INDICATOR VALUES                                                          {Fore.MAGENTA}║{Style.RESET_…
1401 | …     print(f"{Fore.MAGENTA}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
1402 | …     
 ^^^^^^^^^^^^
1403 | …     ehlers_st_val_str = f"${state.ehlers_supertrend_value:.{state.price_precision}f}"
1404 | …     ehlers_st_display_str = f"{ehlers_st_val_str} ({state.ehlers_supertrend_direction})"
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1406:1
     |
1404 | …     ehlers_st_display_str = f"{ehlers_st_val_str} ({state.ehlers_supertrend_direction})"
1405 | …     print(f"{Fore.MAGENTA}║ Ehlers SuperTrend:      {ehlers_color}{ehlers_st_display_str}{Fore.MAGENTA:<{73 - len('Ehlers SuperTre…
1406 | …     
 ^^^^^^^^^^^^
1407 | …     ehlers_filter_str = f"{state.ehlers_filter_value:.2f}"
1408 | …     print(f"{Fore.MAGENTA}║ Ehlers Filter:          {Fore.WHITE}{ehlers_filter_str}{Fore.MAGENTA:<{73 - len('Ehlers Filter:       …
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1409:1
     |
1407 | …     ehlers_filter_str = f"{state.ehlers_filter_value:.2f}"
1408 | …     print(f"{Fore.MAGENTA}║ Ehlers Filter:          {Fore.WHITE}{ehlers_filter_str}{Fore.MAGENTA:<{73 - len('Ehlers Filter:       …
1409 | …     
 ^^^^^^^^^^^^
1410 | …     adx_str = f"{state.adx_value:.1f} (Trend: {state.adx_trend_strength})"
1411 | …     print(f"{Fore.MAGENTA}║ ADX:                    {adx_color}{adx_str}{Fore.MAGENTA:<{73 - len('ADX:                    ') - len…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1412:1
     |
1410 | …     adx_str = f"{state.adx_value:.1f} (Trend: {state.adx_trend_strength})"
1411 | …     print(f"{Fore.MAGENTA}║ ADX:                    {adx_color}{adx_str}{Fore.MAGENTA:<{73 - len('ADX:                    ') - len…
1412 | …     
 ^^^^^^^^^^^^
1413 | …     rsi_str = f"{state.rsi_value:.1f} (State: {state.rsi_state})"
1414 | …     print(f"{Fore.MAGENTA}║ RSI:                    {rsi_color}{rsi_str}{Fore.MAGENTA:<{73 - len('RSI:                    ') - len…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1433:1
     |
1431 | …     print(f"{Fore.GREEN}║ PORTFOLIO & PNL                                                           {Fore.GREEN}║{Style.RESET_ALL}…
1432 | …     print(f"{Fore.GREEN}╠═══════════════════════════════════════════════════════════════════════════╣{Style.RESET_ALL}")
1433 | …     
 ^^^^^^^^^^^^
1434 | …     initial_equity_str = f"${state.initial_equity:.2f}"
1435 | …     print(f"{Fore.GREEN}║ Initial Equity:         {Fore.WHITE}{initial_equity_str}{Fore.GREEN:<{73 - len('Initial Equity:         …
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1436:1
     |
1434 | …     initial_equity_str = f"${state.initial_equity:.2f}"
1435 | …     print(f"{Fore.GREEN}║ Initial Equity:         {Fore.WHITE}{initial_equity_str}{Fore.GREEN:<{73 - len('Initial Equity:         …
1436 | …     
 ^^^^^^^^^^^^
1437 | …     current_equity_str = f"${state.current_equity:.2f}"
1438 | …     equity_change_pct_val = Decimal('0.0')
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1451:1
     |
1449 | …     entry_price_str = f"${state.open_position_entry_price:.{state.price_precision}f}"
1450 | …     unrealized_pnl_str = f"${state.unrealized_pnl:.2f} ({state.unrealized_pnl_pct:+.2f}%)" # PNL to 2 decimals, PCT to 2 decimals
1451 | …     
^^^^^^^^^^^^^
1452 | …     print(f"{Fore.GREEN}║ Open Position:          {Fore.WHITE}{pos_info}{Fore.GREEN:<{73 - len('Open Position:          ') - len(p…
1453 | …     print(f"{Fore.GREEN}║ Avg Entry Price:        {Fore.WHITE}{entry_price_str}{Fore.GREEN:<{73 - len('Avg Entry Price:        ') …
     |
help: Remove whitespace from blank line

W505 Doc line too long (110 > 100)
    --> stupdated.py:1456:101
     |
1454 | …     print(f"{Fore.GREEN}║ Unrealized PNL:         {pnl_color_unrealized}{unrealized_pnl_str}{Fore.GREEN:<{73 - len('Unrealized PNL…
1455 | …     # SL/TP for open position are not stored in BotState.open_position_info.
1456 | …     # If needed, they should be extracted from 'pos' dict in get_positions and passed to BotState.
     |                                                                                           ^^^^^^^^^^
1457 | …     # For now, print placeholders.
1458 | …     print(f"{Fore.GREEN}║ Stop Loss:              {Fore.WHITE}$0.000 (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len…
     |

W505 Doc line too long (103 > 100)
    --> stupdated.py:1463:101
     |
1461 | …     else:
1462 | …         # Consistent padding for "no open position" state
1463 | …         # Adjust formatting to use Decimal('0.0') for consistency and correct precision padding
     |                                                                                               ^^^
1464 | …         print(f"{Fore.GREEN}║ Open Position:          {Fore.WHITE}{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}{Fore.GRE…
1465 | …         print(f"{Fore.GREEN}║ Avg Entry Price:        {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f}{Fore.GREEN:<{73 - le…
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1464:198
     |
1462 | …
1463 | …
1464 | …re.GREEN:<{73 - len('Open Position:          ') - len(f'{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}')}}║{Style.RESET_AL…
     |                                                                   ^
1465 | …3 - len('Avg Entry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
1466 | …<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1465:187
     |
1463 | …
1464 | ….symbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(f'{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}')}}║{Sty…
1465 | …e.GREEN:<{73 - len('Avg Entry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
     |                                                                   ^
1466 | …Fore.GREEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
1467 | …A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL…
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1466:190
     |
1464 | …mbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(f'{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}')}}║{Style.…
1465 | …REEN:<{73 - len('Avg Entry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
1466 | …e.GREEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1467 | …Fore.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
1468 | …Fore.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1466:212
     |
1464 | …- len('Open Position:          ') - len(f'{Decimal('0.0'):.{state.qty_precision}f} {state.symbol}')}}║{Style.RESET_ALL}")
1465 | …ntry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
1466 | …realized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1467 | …'Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
1468 | …'Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1467:193
     |
1465 | …N:<{73 - len('Avg Entry Price:        ') - len(f'${Decimal('0.0'):.{state.price_precision}f}')}}║{Style.RESET_ALL}")
1466 | …REEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
1467 | …e.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1468 | …e.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated.py:1468:193
     |
1466 | …REEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
1467 | …e.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
1468 | …e.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1469 | …
1470 | …
     |

W293 Blank line contains whitespace
    --> stupdated.py:1583:1
     |
1581 |                 self.logger.info(Fore.YELLOW + reason + Style.RESET_ALL)
1582 |                 return True, reason
1583 |         
     | ^^^^^^^^
1584 |         return False, "No high-impact news events requiring pause."
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1596:23
     |
1594 |     def _is_bullish_engulfing(self, df: pd.DataFrame) -> bool:
1595 |         """Detects a bullish engulfing pattern."""
1596 |         if len(df) < 2: return False
     |                       ^
1597 |         
1598 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
     |

W293 Blank line contains whitespace
    --> stupdated.py:1597:1
     |
1595 |         """Detects a bullish engulfing pattern."""
1596 |         if len(df) < 2: return False
1597 |         
     | ^^^^^^^^
1598 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1599:1
     |
1598 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
1599 |         
     | ^^^^^^^^
1600 |         # Previous candle must be bearish, latest must be bullish
1601 |         prev_is_bearish = c2['close'] < c2['open']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1603:1
     |
1601 |         prev_is_bearish = c2['close'] < c2['open']
1602 |         curr_is_bullish = c1['close'] > c1['open']
1603 |         
     | ^^^^^^^^
1604 |         if not (prev_is_bearish and curr_is_bullish): return False
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1604:53
     |
1602 |         curr_is_bullish = c1['close'] > c1['open']
1603 |         
1604 |         if not (prev_is_bearish and curr_is_bullish): return False
     |                                                     ^
1605 |         
1606 |         # Current candle body must engulf previous candle body
     |

W293 Blank line contains whitespace
    --> stupdated.py:1605:1
     |
1604 |         if not (prev_is_bearish and curr_is_bullish): return False
1605 |         
     | ^^^^^^^^
1606 |         # Current candle body must engulf previous candle body
1607 |         engulfs_low = c1['open'] < c2['close']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1609:1
     |
1607 |         engulfs_low = c1['open'] < c2['close']
1608 |         engulfs_high = c1['close'] > c2['open']
1609 |         
     | ^^^^^^^^
1610 |         return engulfs_low and engulfs_high
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1614:23
     |
1612 |     def _is_bearish_engulfing(self, df: pd.DataFrame) -> bool:
1613 |         """Detects a bearish engulfing pattern."""
1614 |         if len(df) < 2: return False
     |                       ^
1615 |         
1616 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
     |

W293 Blank line contains whitespace
    --> stupdated.py:1615:1
     |
1613 |         """Detects a bearish engulfing pattern."""
1614 |         if len(df) < 2: return False
1615 |         
     | ^^^^^^^^
1616 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1617:1
     |
1616 |         c2, c1 = df.iloc[-2], df.iloc[-1] # Previous, Latest
1617 |         
     | ^^^^^^^^
1618 |         # Previous candle must be bullish, latest must be bearish
1619 |         prev_is_bullish = c2['close'] > c2['open']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1621:1
     |
1619 |         prev_is_bullish = c2['close'] > c2['open']
1620 |         curr_is_bearish = c1['close'] < c1['open']
1621 |         
     | ^^^^^^^^
1622 |         if not (prev_is_bullish and curr_is_bearish): return False
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1622:53
     |
1620 |         curr_is_bearish = c1['close'] < c1['open']
1621 |         
1622 |         if not (prev_is_bullish and curr_is_bearish): return False
     |                                                     ^
1623 |         
1624 |         # Current candle body must engulf previous candle body
     |

W293 Blank line contains whitespace
    --> stupdated.py:1623:1
     |
1622 |         if not (prev_is_bullish and curr_is_bearish): return False
1623 |         
     | ^^^^^^^^
1624 |         # Current candle body must engulf previous candle body
1625 |         engulfs_low = c1['close'] < c2['open']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1627:1
     |
1625 |         engulfs_low = c1['close'] < c2['open']
1626 |         engulfs_high = c1['open'] > c2['close']
1627 |         
     | ^^^^^^^^
1628 |         return engulfs_low and engulfs_high
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1632:23
     |
1630 |     def _is_hammer(self, df: pd.DataFrame) -> bool:
1631 |         """Detects a hammer pattern."""
1632 |         if len(df) < 1: return False
     |                       ^
1633 |         c1 = df.iloc[-1]
     |

W293 Blank line contains whitespace
    --> stupdated.py:1634:1
     |
1632 |         if len(df) < 1: return False
1633 |         c1 = df.iloc[-1]
1634 |         
     | ^^^^^^^^
1635 |         body_size = abs(c1['close'] - c1['open'])
1636 |         lower_shadow = min(c1['open'], c1['close']) - c1['low']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1638:1
     |
1636 |         lower_shadow = min(c1['open'], c1['close']) - c1['low']
1637 |         upper_shadow = c1['high'] - max(c1['open'], c1['close'])
1638 |         
     | ^^^^^^^^
1639 |         # Hammer criteria: small body, long lower shadow (at least 2x body), little/no upper shadow
1640 |         return body_size > 0 and lower_shadow >= 2 * body_size and upper_shadow < body_size / 2
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:1644:23
     |
1642 |     def _is_shooting_star(self, df: pd.DataFrame) -> bool:
1643 |         """Detects a shooting star pattern."""
1644 |         if len(df) < 1: return False
     |                       ^
1645 |         c1 = df.iloc[-1]
     |

W293 Blank line contains whitespace
    --> stupdated.py:1646:1
     |
1644 |         if len(df) < 1: return False
1645 |         c1 = df.iloc[-1]
1646 |         
     | ^^^^^^^^
1647 |         body_size = abs(c1['close'] - c1['open'])
1648 |         lower_shadow = min(c1['open'], c1['close']) - c1['low']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1650:1
     |
1648 |         lower_shadow = min(c1['open'], c1['close']) - c1['low']
1649 |         upper_shadow = c1['high'] - max(c1['open'], c1['close'])
1650 |         
     | ^^^^^^^^
1651 |         # Shooting Star criteria: small body, long upper shadow (at least 2x body), little/no lower shadow
1652 |         return body_size > 0 and upper_shadow >= 2 * body_size and lower_shadow < body_size / 2
     |
help: Remove whitespace from blank line

W505 Doc line too long (106 > 100)
    --> stupdated.py:1651:101
     |
1649 |         upper_shadow = c1['high'] - max(c1['open'], c1['close'])
1650 |         
1651 |         # Shooting Star criteria: small body, long upper shadow (at least 2x body), little/no lower shadow
     |                                                                                                     ^^^^^^
1652 |         return body_size > 0 and upper_shadow >= 2 * body_size and lower_shadow < body_size / 2
     |

W293 Blank line contains whitespace
    --> stupdated.py:1661:1
     |
1659 |         if df.empty or len(df) < 2: # Need at least 2 candles for most patterns for context
1660 |             return None
1661 |         
     | ^^^^^^^^
1662 |         # Ensure 'open', 'high', 'low', 'close' are present
1663 |         if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1692:1
     |
1690 |     def __init__(self, config: Config):
1691 |         self.config = config
1692 |         
     | ^^^^^^^^
1693 |         # --- Logger Setup ---
1694 |         global logger # Use the global logger instance
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1698:1
     |
1696 |         self.logger = logger
1697 |         self.logger.info("Initializing Ehlers SuperTrend Trading Bot...")
1698 |         
     | ^^^^^^^^
1699 |         # --- BotState Initialization (for UI) ---
1700 |         self.bot_state = BotState()
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1701:1
     |
1699 |         # --- BotState Initialization (for UI) ---
1700 |         self.bot_state = BotState()
1701 |         
     | ^^^^^^^^
1702 |         # --- API Session Initialization (using BybitClient) ---
1703 |         self.bybit_client = BybitClient(
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1719:1
     |
1717 |         self.news_calendar_manager = NewsCalendarManager(self.config, self.logger) # New: News Calendar Manager
1718 |         self.candlestick_detector = CandlestickPatternDetector(self.logger) # New: Candlestick Pattern Detector
1719 |         
     | ^^^^^^^^
1720 |         # --- Termux SMS Notifier ---
1721 |         # Get initial precision for SMS notifier
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1728:1
     |
1726 |             price_precision=price_prec
1727 |         )
1728 |         
     | ^^^^^^^^
1729 |         # --- Data Storage ---
1730 |         self.market_data: pd.DataFrame = pd.DataFrame() # Stores historical klines with indicators
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:1735:54
     |
1733 |         self.open_orders: Dict[str, dict] = {} # {order_id: order_data}
1734 |         self.account_balance_usdt: Decimal = Decimal('0.0')
1735 |         self.initial_equity: Decimal = Decimal('0.0') 
     |                                                      ^
1736 |         
1737 |         # --- Strategy State ---
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:1736:1
     |
1734 |         self.account_balance_usdt: Decimal = Decimal('0.0')
1735 |         self.initial_equity: Decimal = Decimal('0.0') 
1736 |         
     | ^^^^^^^^
1737 |         # --- Strategy State ---
1738 |         self.position_active: bool = False # Whether there's an active position for self.config.SYMBOL
     |
help: Remove whitespace from blank line

W505 Doc line too long (112 > 100)
    --> stupdated.py:1751:101
     |
1750 |         # New: State for Partial Take Profit
1751 |         # {symbol: {target_idx: True}} indicates which partial TP targets have been hit for the current position
     |                                                                                                     ^^^^^^^^^^^^
1752 |         self.partial_tp_targets_hit: Dict[str, Dict[int, bool]] = {} 
1753 |         self.initial_position_qty: Decimal = Decimal('0.0') # Store initial quantity for partial TP
     |

W291 Trailing whitespace
    --> stupdated.py:1752:69
     |
1750 |         # New: State for Partial Take Profit
1751 |         # {symbol: {target_idx: True}} indicates which partial TP targets have been hit for the current position
1752 |         self.partial_tp_targets_hit: Dict[str, Dict[int, bool]] = {} 
     |                                                                     ^
1753 |         self.initial_position_qty: Decimal = Decimal('0.0') # Store initial quantity for partial TP
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:1776:1
     |
1774 |         self._validate_symbol_timeframe() # Validate symbol and timeframe
1775 |         self._capture_initial_equity() # Capture initial equity for cumulative loss protection
1776 |         
     | ^^^^^^^^
1777 |         if self.config.CATEGORY_ENUM != Category.SPOT:
1778 |             self._configure_trading_parameters() # Set margin mode and leverage for derivatives
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1836:1
     |
1834 | …         self.logger.error(Fore.RED + f"Unexpected API response format: {type(response).__name__}, expected a dict." + Style.RESET_…
1835 | …         raise ValueError("Unexpected API response format, expected a dict")
1836 | …     
     ^^^^^^^^
1837 | …     ret_code = response.get('retCode')
1838 | …     ret_msg = response.get('retMsg', 'No message provided')
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1840:1
     |
1838 |         ret_msg = response.get('retMsg', 'No message provided')
1839 |         result = response.get('result')
1840 |         
     | ^^^^^^^^
1841 |         if ret_code != 0:
1842 |             # Common authentication / permission errors
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:1843:72
     |
1841 |         if ret_code != 0:
1842 |             # Common authentication / permission errors
1843 |             if ret_code in {10001, 10002, 10003, 10004, 10005, 130006}: 
     |                                                                        ^
1844 |                 self.logger.critical(Fore.RED + f"Fatal Bybit API authentication error {ret_code}: {ret_msg}." + Style.RESET_ALL)
1845 |                 subprocess.run(["termux-toast", f"Ehlers Bot: Fatal API Auth Error {ret_code}"])
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:1859:1
     |
1857 |                 self.sms_notifier.send_sms(f"ERROR: Bybit API error {ret_code} for {self.config.SYMBOL}: {ret_msg}")
1858 |             raise RuntimeError(f"Bybit API returned error {ret_code}: {ret_msg}")
1859 |         
     | ^^^^^^^^
1860 |         # Even if retCode is 0, ensure 'result' field is present for data calls
1861 |         if result is None:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1864:1
     |
1862 | …         self.logger.warning(Fore.YELLOW + "Bybit API response missing 'result' field despite success code. Returning empty dict." …
1863 | …         return {}
1864 | …     
     ^^^^^^^^
1865 | …     return result
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1880:1
     |
1878 |                 result_data = self._handle_bybit_response(raw_resp)
1879 |                 return result_data # Success, return the extracted result
1880 |             
     | ^^^^^^^^^^^^
1881 |             except PermissionError as e:
1882 |                 self.logger.critical(Fore.RED + Style.BRIGHT + f"Fatal API error: {e}. Exiting bot." + Style.RESET_ALL)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1884:1
     |
1882 |                 self.logger.critical(Fore.RED + Style.BRIGHT + f"Fatal API error: {e}. Exiting bot." + Style.RESET_ALL)
1883 |                 sys.exit(1) # Halt the bot immediately
1884 |             
     | ^^^^^^^^^^^^
1885 |             except (ConnectionRefusedError, RuntimeError, FailedRequestError, InvalidRequestError) as e:
1886 |                 # Explicitly check for the non-retriable error and re-raise immediately.
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1901:1
     |
1899 | …             self.sms_notifier.send_sms(f"CRITICAL: API call failed after {self.config.MAX_API_RETRIES} retries for {self.config.SY…
1900 | …         return None
1901 | …     
^^^^^^^^^^^^^
1902 | …     sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
1903 | …     sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1906:1
     |
1904 | …         self.logger.warning(Fore.YELLOW + f"API transient error: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} in {sleep_…
1905 | …         time.sleep(sleep_time)
1906 | …     
 ^^^^^^^^^^^^
1907 | …     except Exception as e:
1908 | …         if self.stop_event.is_set(): # Check if shutdown is requested during retry loop
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1918:1
     |
1916 | …             self.sms_notifier.send_sms(f"CRITICAL: API call failed unexpectedly after {self.config.MAX_API_RETRIES} retries for {s…
1917 | …         return None
1918 | …     
^^^^^^^^^^^^^
1919 | …     sleep_time = min(60.0, self.config.API_RETRY_DELAY_SEC * (2 ** (attempt - 1)))
1920 | …     sleep_time *= (1.0 + random.uniform(-0.2, 0.2)) # Add jitter for backoff
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1923:1
     |
1921 | …             self.logger.warning(Fore.YELLOW + f"API unexpected exception: {e} | Retrying {attempt}/{self.config.MAX_API_RETRIES} i…
1922 | …             time.sleep(sleep_time)
1923 | …     
     ^^^^^^^^
1924 | …     self.logger.error(Fore.RED + "API call exhausted retries and did not return success." + Style.RESET_ALL)
1925 | …     return None
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:1963:1
     |
1961 | …             self.sms_notifier.send_sms(f"CRITICAL: Invalid timeframe '{self.config.TIMEFRAME}' for {self.config.SYMBOL}. Exiting.")
1962 | …         sys.exit(1)
1963 | …     
     ^^^^^^^^
1964 | …     # Validate higher timeframe if enabled
1965 | …     if self.config.MULTI_TIMEFRAME_CONFIRMATION_ENABLED and str(self.config.HIGHER_TIMEFRAME) not in valid_intervals:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2014:1
     |
2012 | …     """
2013 | …     current_equity = self.get_account_balance_usdt() # This also updates bot_state.current_equity
2014 | …     
     ^^^^^^^^
2015 | …     if self.initial_equity <= Decimal('0') or current_equity <= Decimal('0'): # Ensure valid initial and current equity
2016 | …         self.logger.warning(Fore.YELLOW + "Could not fetch valid initial or current equity for cumulative loss guard. Proceeding c…
     |
help: Remove whitespace from blank line

W505 Doc line too long (105 > 100)
    --> stupdated.py:2017:101
     |
2015 | …     if self.initial_equity <= Decimal('0') or current_equity <= Decimal('0'): # Ensure valid initial and current equity
2016 | …         self.logger.warning(Fore.YELLOW + "Could not fetch valid initial or current equity for cumulative loss guard. Proceeding c…
2017 | …         # Fallback to cumulative PnL-based logic if initial equity wasn't captured or current is zero
     |                                                                                                   ^^^^^
2018 | …         if self.cumulative_pnl < -abs(Decimal(str(self.config.MAX_DAILY_LOSS_PCT))) * self.initial_equity: # Assuming initial_equi…
2019 | …             self.logger.critical(Fore.RED + f"Cumulative PnL loss limit reached ({self.cumulative_pnl:.2f} USDT). Trading halted!"…
     |

W293 Blank line contains whitespace
    --> stupdated.py:2034:1
     |
2032 | …     if self.sms_notifier.is_enabled:
2033 | …         self.sms_notifier.send_sms(f"CRITICAL: Cumulative equity drawdown {drop_pct:.2f}% exceeded limit for {self.config.SYMBOL}.…
2034 | …     
 ^^^^^^^^^^^^
2035 | …     # Optional: close open position if loss limit is hit
2036 | …     if self.position_active: # Check bot's internal state
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2132:1
     |
2130 |                                 self.logger.debug(f"Successfully fetched account balance: {balance:.4f} USDT ({account_type})")
2131 |                                 return balance
2132 |                 
     | ^^^^^^^^^^^^^^^^
2133 |                 self.logger.warning(f"USDT balance not found in response for account type {account_type}. Returning 0.")
2134 |                 self.account_balance_usdt = Decimal('0.0')
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2203:1
     |
2201 |             leverage_str = str(leverage_to_set_decimal)
2202 |             self.logger.info(f"Attempting to set leverage to {leverage_str}x for {self.config.SYMBOL}...")
2203 |             
     | ^^^^^^^^^^^^
2204 |             self.api_call(
2205 |                 self.bybit_client.set_leverage,
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2234:1
     |
2232 |         # FEATURE: Adaptive Indicator Parameters (Volatility-Based)
2233 |         """
2234 |         
     | ^^^^^^^^
2235 |         # Determine indicator parameters dynamically if enabled
2236 |         ehlers_length = self.config.EHLERS_LENGTH
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2264:1
     |
2262 | …         else:
2263 | …             self.logger.warning(f"Not enough data for adaptive indicators (need {self.config.VOLATILITY_MEASURE_WINDOW} periods). …
2264 | …     
     ^^^^^^^^
2265 | …     # Update bot_state with adaptive parameters
2266 | …     if not is_higher_timeframe:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2300:1
     |
2298 |         b1 = 2 * a1 * np.cos(np.sqrt(2) * np.pi / float(self.config.SMOOTHING_LENGTH))
2299 |         c2, c3, c1 = b1, -a1 * a1, 1 - b1 + a1 * a1
2300 |         
     | ^^^^^^^^
2301 |         filt = np.zeros(len(close), dtype=float)
2302 |         # Handle initial values for filt to avoid index errors or NaN propagation
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2314:1
     |
2312 | …     # Use min_periods to allow calculation with less than full window at start
2313 | …     volatility = vol_series.rolling(ehlers_length, min_periods=max(1, ehlers_length//2)).std().ewm(span=self.config.SMOOTHING_LENG…
2314 | …     
     ^^^^^^^^
2315 | …     raw_trend = np.where(df['close'] > (filt + (volatility * self.config.SENSITIVITY)), 1,\
2316 | …                          np.where(df['close'] < (filt - (volatility * self.config.SENSITIVITY)), -1, np.nan))
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2359:1
     |
2357 |                 elif supertrend_line.iloc[i-1] == final_lower.iloc[i-1] and df['close'].iloc[i] >= final_lower.iloc[i]:
2358 |                     supertrend_line.iloc[i] = final_lower.iloc[i]
2359 |         
     | ^^^^^^^^
2360 |         df['supertrend_line_value'] = supertrend_line
2361 |         df['supertrend_direction'] = np.where(df['close'] > df['supertrend_line_value'], 1, -1)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2372:1
     |
2370 | …     df['macd_signal'] = macd.macd_signal()
2371 | …     df['macd_diff'] = macd.macd_diff()
2372 | …     
     ^^^^^^^^
2373 | …     # ADX: Trend Strength and Direction
2374 | …     adx_indicator = ta.trend.ADXIndicator(high=df['high'], low=df['low'], close=df['close'], window=self.config.ADX_WINDOW, fillna…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2387:1
     |
2385 | …         fillna=True
2386 | …     ).average_true_range()
2387 | …     
     ^^^^^^^^
2388 | …     # Drop rows where indicators are NaN (remove initial NaN rows, after fillna)
2389 | …     required_indicator_cols = ['ehlers_trend', 'ehlers_filter', 'supertrend_direction', 'supertrend_line_value', 'rsi', 'macd', 'm…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2422:1
     |
2420 |         price_above_filter = latest['close'] > latest['ehlers_filter']
2421 |         price_below_filter = latest['close'] < latest['ehlers_filter']
2422 |         
     | ^^^^^^^^
2423 |         rsi_bullish = latest['rsi'] > 52
2424 |         rsi_bearish = latest['rsi'] < 48
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2433:1
     |
2431 |             if latest['adx'] < self.config.ADX_MIN_THRESHOLD:
2432 |                 return None, f"ADX ({latest['adx']:.1f}) below min threshold ({self.config.ADX_MIN_THRESHOLD}). No trade."
2433 |             
     | ^^^^^^^^^^^^
2434 |             if self.config.ADX_TREND_DIRECTION_CONFIRMATION:
2435 |                 if st_flipped_up and latest['adx_plus_di'] < latest['adx_minus_di']:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2476:1
     |
2474 |                 if not pattern_detected:
2475 |                     return None, f"Bearish signal detected, but no required bearish candlestick pattern found."
2476 |             
     | ^^^^^^^^^^^^
2477 |             if pattern_detected:
2478 |                 self.logger.debug(f"Candlestick pattern '{pattern_detected}' confirmed signal.")
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2503:1
     |
2501 |         """
2502 |         sl_pct_decimal = Decimal(str(self.config.STOP_LOSS_PCT))
2503 |         
     | ^^^^^^^^
2504 |         # FEATURE: Dynamic Take Profit (DTP) via ATR
2505 |         if self.config.DYNAMIC_TP_ENABLED and not df.empty and 'atr' in df.columns:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2510:1
     |
2508 |                 # Calculate TP in price units based on ATR
2509 |                 dynamic_tp_price_units = atr_value * Decimal(str(self.config.ATR_TP_MULTIPLIER))
2510 |                 
     | ^^^^^^^^^^^^^^^^
2511 |                 # Convert to percentage relative to entry price
2512 |                 dynamic_tp_pct = dynamic_tp_price_units / entry_price
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2513:1
     |
2511 |                 # Convert to percentage relative to entry price
2512 |                 dynamic_tp_pct = dynamic_tp_price_units / entry_price
2513 |                 
     | ^^^^^^^^^^^^^^^^
2514 |                 # Clamp between min and max TP percentages
2515 |                 tp_pct_decimal = max(Decimal(str(self.config.MIN_TAKE_PROFIT_PCT)), 
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:2515:84
     |
2514 | …     # Clamp between min and max TP percentages
2515 | …     tp_pct_decimal = max(Decimal(str(self.config.MIN_TAKE_PROFIT_PCT)), 
     |                                                                          ^
2516 | …                          min(dynamic_tp_pct, Decimal(str(self.config.MAX_TAKE_PROFIT_PCT))))
2517 | …     self.logger.debug(f"Dynamic TP calculated: ATR={atr_value:.4f}, Price Units={dynamic_tp_price_units:.4f}, Raw PCT={dynamic_tp_…
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:2523:1
     |
2521 |         else:
2522 |             tp_pct_decimal = Decimal(str(self.config.TAKE_PROFIT_PCT))
2523 |         
     | ^^^^^^^^
2524 |         if side == 'Buy':
2525 |             stop_loss = entry_price * (Decimal('1') - sl_pct_decimal)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2550:1
     |
2548 |         Includes verification if the order was actually filled.
2549 |         Returns the filled order details on success, None otherwise.
2550 |         
     | ^^^^^^^^
2551 |         FEATURE: Slippage Tolerance for Market Orders
2552 |         Checks for excessive slippage for market orders and logs a warning.
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2579:1
     |
2577 | …     self.logger.info(f"Placing order for {self.config.SYMBOL}: Side={side}, Qty={str_qty}, Type={order_type.value}, "
2578 | …                      f"Price={str_price}, SL={str_stopLoss}, TP={str_takeProfit}, ReduceOnly={reduce_only}")
2579 | …     
     ^^^^^^^^
2580 | …     if self.config.DRY_RUN:
2581 | …         self.logger.info(Fore.YELLOW + f"[DRY RUN] Would place {side} order of {str_qty} {self.config.SYMBOL} ({order_type.value})…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2605:1
     |
2603 |                 tpslMode='Full' if (stopLoss is not None or takeProfit is not None) else None
2604 |             )
2605 |             
     | ^^^^^^^^^^^^
2606 |             if order_response and order_response.get('orderId'):
2607 |                 order_id = order_response['orderId']
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2609:1
     |
2607 | …     order_id = order_response['orderId']
2608 | …     self.logger.info(Fore.GREEN + f"Order spell cast with ID: {order_id}. Awaiting the market's response..." + Style.RESET_ALL)
2609 | …     
^^^^^^^^^^^^^
2610 | …     # --- VERIFY ORDER EXECUTION --- 
2611 | …     # Poll for order status to confirm fill
     |
help: Remove whitespace from blank line

W291 Trailing whitespace
    --> stupdated.py:2610:49
     |
2608 | …     self.logger.info(Fore.GREEN + f"Order spell cast with ID: {order_id}. Awaiting the market's response..." + Style.RESET_ALL)
2609 | …     
2610 | …     # --- VERIFY ORDER EXECUTION --- 
     |                                       ^
2611 | …     # Poll for order status to confirm fill
2612 | …     max_retries = 5
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:2617:1
     |
2615 | …     time.sleep(retry_delay)
2616 | …     order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id, category=specs…
2617 | …     
^^^^^^^^^^^^^
2618 | …     if order_details and order_details.get('list') and order_details['list']:
2619 | …         filled_order = order_details['list'][0]
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2621:1
     |
2619 |                         filled_order = order_details['list'][0]
2620 |                         order_status = filled_order.get('orderStatus')
2621 |                         
     | ^^^^^^^^^^^^^^^^^^^^^^^^
2622 |                         if order_status in ('Filled', 'PartiallyFilled'):
2623 |                             avg_price_str = filled_order.get('avgPrice')
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2626:1
     |
2624 | …     filled_price = Decimal(avg_price_str) if avg_price_str and Decimal(avg_price_str) > Decimal('0') else (entry_price or Decimal(…
2625 | …     filled_qty = Decimal(filled_order.get('cumExecQty', '0'))
2626 | …     
^^^^^^^^^^^^^
2627 | …     # FEATURE: Slippage Tolerance for Market Orders
2628 | …     if order_type == OrderType.MARKET and intended_price is not None and intended_price > Decimal('0'):
     |
help: Remove whitespace from blank line

W505 Doc line too long (118 > 100)
    --> stupdated.py:2632:101
     |
2630 | …     if actual_slippage_pct > Decimal(str(self.config.SLIPPAGE_TOLERANCE_PCT)):
2631 | …         self.logger.warning(Fore.YELLOW + f"⚠️ High Slippage Detected for Market Order {order_id}: {actual_slippage_pct*100:.2f}% …I
2632 | …         # Depending on policy, might raise an error or just log. For now, log and proceed.
     |                                                                           ^^^^^^^^^^^^^^^^^^
2633 | …     else:
2634 | …         self.logger.info(f"Slippage for market order {order_id}: {actual_slippage_pct*100:.2f}% (within tolerance).")
     |

W293 Blank line contains whitespace
    --> stupdated.py:2654:1
     |
2652 | …         else:
2653 | …             self.logger.debug(f"No order history for {order_id} yet. Retrying...")
2654 | …     
^^^^^^^^^^^^^
2655 | …     self.logger.error(Fore.RED + f"Order {order_id} not confirmed filled after {max_retries} retries. Manual check needed." + Styl…
2656 | …     subprocess.run(["termux-toast", f"Order NOT FILLED: {self.config.SYMBOL} (ID: {order_id})"])
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2768:1
     |
2766 |                     symbol=self.config.SYMBOL
2767 |                 )
2768 |             
     | ^^^^^^^^^^^^
2769 |             if response_data is not None:
2770 |                 orders = response_data.get('list', [])
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2789:1
     |
2787 |         Fetch and update current positions for the configured symbol.
2788 |         Also updates BotState with position details.
2789 |         
     | ^^^^^^^^
2790 |         FEATURE: Max Concurrent Positions Limit
2791 |         This method now fetches *all* active positions across the account
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2811:1
     |
2809 |                 positions_list = response_data.get('list', [])
2810 |                 self.all_open_positions.clear() # Reset all_open_positions
2811 |                 
     | ^^^^^^^^^^^^^^^^
2812 |                 # Filter for positions with actual size > 0 and store them
2813 |                 for pos in positions_list:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2816:1
     |
2814 |                     if Decimal(pos.get('size', '0')) > Decimal('0'):
2815 |                         self.all_open_positions[pos['symbol']] = pos
2816 |                 
     | ^^^^^^^^^^^^^^^^
2817 |                 self.logger.debug(f"Fetched {len(self.all_open_positions)} active positions across all symbols.")
     |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
    --> stupdated.py:2839:101
     |
2837 | …     self.bot_state.open_position_side = position_for_current_symbol['side']
2838 | …     self.bot_state.open_position_entry_price = Decimal(position_for_current_symbol['avgPrice'])
2839 | …     # Unrealized PnL from position data is for last mark price, can be used for UI
     |                                                                                   ^^
2840 | …     self.bot_state.unrealized_pnl = Decimal(position_for_current_symbol.get('unrealisedPnl', '0.0')) 
2841 | …     pos_value = Decimal(position_for_current_symbol['size']) * Decimal(position_for_current_symbol.get('markPrice', '0'))
     |

W291 Trailing whitespace
    --> stupdated.py:2840:121
     |
2838 | …     self.bot_state.open_position_entry_price = Decimal(position_for_current_symbol['avgPrice'])
2839 | …     # Unrealized PnL from position data is for last mark price, can be used for UI
2840 | …     self.bot_state.unrealized_pnl = Decimal(position_for_current_symbol.get('unrealisedPnl', '0.0')) 
     |                                                                                                       ^
2841 | …     pos_value = Decimal(position_for_current_symbol['size']) * Decimal(position_for_current_symbol.get('markPrice', '0'))
2842 | …     if pos_value > Decimal('0'):
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:2935:1
     |
2933 |             self.logger.warning(Fore.YELLOW + "No active position to close." + Style.RESET_ALL)
2934 |             return False
2935 |         
     | ^^^^^^^^
2936 |         side_to_close = 'Sell' if current_pos['side'] == 'Buy' else 'Buy'
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2937:1
     |
2936 |         side_to_close = 'Sell' if current_pos['side'] == 'Buy' else 'Buy'
2937 |         
     | ^^^^^^^^
2938 |         # If qty_to_close is not specified, close the full position
2939 |         if qty_to_close is None:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2955:1
     |
2953 | …     self.logger.info(Fore.YELLOW + f"[DRY RUN] Would close {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']…
2954 | …     self.sms_notifier.send_sms(f"DRY RUN: Close {qty_to_close:.{self.bot_state.qty_precision}f} {current_pos['side']} {self.config…
2955 | …     
 ^^^^^^^^^^^^
2956 | …     # Simulate updating internal position state and BotState
2957 | …     remaining_qty = Decimal(current_pos['size']) - qty_to_close
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2986:1
     |
2984 |         try:
2985 |             self.logger.info(f"Attempting to close {qty_to_close} of {current_pos['side']} position for {self.config.SYMBOL}...")
2986 |             
     | ^^^^^^^^^^^^
2987 |             close_order_data = self.place_order( # Use place_order for closing to leverage its verification logic
2988 |                 side=side_to_close,
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:2993:1
     |
2991 |                 reduce_only=True
2992 |             )
2993 |             
     | ^^^^^^^^^^^^
2994 |             if close_order_data: # place_order returns filled order data on success
2995 |                 # For realized PnL, Bybit's get_positions gives unrealisedPnl.
     |
help: Remove whitespace from blank line

W505 Doc line too long (110 > 100)
    --> stupdated.py:2999:101
     |
2997 |                 # For simplicity, we can use the last known unrealized PnL from the position
2998 |                 # before it was closed, or fetch the trade history for exact realized PnL.
2999 |                 # Here, we use the unrealized PnL from `current_pos` as a proxy for realized PnL upon closure.
     |                                                                                                     ^^^^^^^^^^
3000 |                 pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size']))
3001 |                 self.cumulative_pnl += pnl_realized 
     |

W291 Trailing whitespace
    --> stupdated.py:3001:52
     |
2999 | …     # Here, we use the unrealized PnL from `current_pos` as a proxy for realized PnL upon closure.
3000 | …     pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size']))
3001 | …     self.cumulative_pnl += pnl_realized 
     |                                          ^
3002 | …     
3003 | …     self.logger.info(Fore.MAGENTA + f"✅ Position Closed: {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']} …
     |
help: Remove trailing whitespace

W293 Blank line contains whitespace
    --> stupdated.py:3002:1
     |
3000 | …     pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size']))
3001 | …     self.cumulative_pnl += pnl_realized 
3002 | …     
^^^^^^^^^^^^^
3003 | …     self.logger.info(Fore.MAGENTA + f"✅ Position Closed: {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']} …
3004 | …     subprocess.run(["termux-toast", f"Position Closed: {self.config.SYMBOL}. PnL: {pnl_realized:.{self.bot_state.price_precision}f…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3005:1
     |
3003 | …     self.logger.info(Fore.MAGENTA + f"✅ Position Closed: {qty_to_close:.{self.bot_state.qty_precision}f} of {current_pos['side']} …
3004 | …     subprocess.run(["termux-toast", f"Position Closed: {self.config.SYMBOL}. PnL: {pnl_realized:.{self.bot_state.price_precision}f…
3005 | …     
^^^^^^^^^^^^^
3006 | …     current_equity = self.get_account_balance_usdt() # Refresh equity for notification
3007 | …     if self.sms_notifier.is_enabled:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3009:1
     |
3007 |                 if self.sms_notifier.is_enabled:
3008 |                     self.sms_notifier.send_pnl_update(float(pnl_realized), float(current_equity))
3009 |                 
     | ^^^^^^^^^^^^^^^^
3010 |                 # Update internal position state. Call get_positions to fully sync.
3011 |                 self.get_positions() # This will update self.position_active, self.current_position_size etc.
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3047:1
     |
3045 | …         self.logger.info(f"Trading is outside allowed hours ({self.config.TRADE_START_HOUR_UTC}-{self.config.TRADE_END_HOUR_UTC} U…
3046 | …         return False
3047 | …     
     ^^^^^^^^
3048 | …     return True
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3068:1
     |
3066 | …     next_funding_dt = datetime.fromtimestamp(next_funding_time_ms / 1000, tz=dateutil.tz.UTC)
3067 | …     time_until_funding = next_funding_dt - datetime.now(dateutil.tz.UTC)
3068 | …     
^^^^^^^^^^^^^
3069 | …     if abs(funding_rate) >= Decimal(str(self.config.FUNDING_RATE_THRESHOLD_PCT)):
3070 | …         if time_until_funding <= timedelta(minutes=self.config.FUNDING_GRACE_PERIOD_MINUTES) and time_until_funding > timedelta(se…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3084:1
     |
3082 |         order_id = self.pending_retracement_order['orderId']
3083 |         time_placed_kline_ts = self.pending_retracement_order['time_placed_kline_ts']
3084 |         
     | ^^^^^^^^
3085 |         # Check if the order is still open or has been filled
3086 |         self.fetch_open_orders() # Refresh self.open_orders
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3087:1
     |
3085 |         # Check if the order is still open or has been filled
3086 |         self.fetch_open_orders() # Refresh self.open_orders
3087 |         
     | ^^^^^^^^
3088 |         if order_id not in self.open_orders:
3089 |             # Order is no longer open, likely filled or cancelled by exchange/user
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:3108:28
     |
3106 |         """Helper to convert timeframe string to milliseconds."""
3107 |         tf = self.config.TIMEFRAME
3108 |         if tf.endswith('D'): return 24 * 60 * 60 * 1000
     |                            ^
3109 |         if tf.endswith('W'): return 7 * 24 * 60 * 60 * 1000
3110 |         if tf.endswith('M'): return 30 * 24 * 60 * 60 * 1000 # Approx month
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3109:28
     |
3107 |         tf = self.config.TIMEFRAME
3108 |         if tf.endswith('D'): return 24 * 60 * 60 * 1000
3109 |         if tf.endswith('W'): return 7 * 24 * 60 * 60 * 1000
     |                            ^
3110 |         if tf.endswith('M'): return 30 * 24 * 60 * 60 * 1000 # Approx month
3111 |         return int(tf) * 60 * 1000 # Minutes to milliseconds
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3110:28
     |
3108 |         if tf.endswith('D'): return 24 * 60 * 60 * 1000
3109 |         if tf.endswith('W'): return 7 * 24 * 60 * 60 * 1000
3110 |         if tf.endswith('M'): return 30 * 24 * 60 * 60 * 1000 # Approx month
     |                            ^
3111 |         return int(tf) * 60 * 1000 # Minutes to milliseconds
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3123:27
     |
3122 |         current_pos = self.all_open_positions.get(symbol)
3123 |         if not current_pos: return
     |                           ^
3124 |
3125 |         current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct # From BotState, already updated
     |

W293 Blank line contains whitespace
    --> stupdated.py:3126:1
     |
3125 |         current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct # From BotState, already updated
3126 |         
     | ^^^^^^^^
3127 |         if current_unrealized_pnl_pct >= Decimal(str(self.config.BREAKEVEN_PROFIT_TRIGGER_PCT)) * Decimal('100'):
3128 |             entry_price = self.current_position_entry_price
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3134:1
     |
3132 |             else: # Sell
3133 |                 breakeven_sl = entry_price - entry_price * Decimal(str(self.config.BREAKEVEN_OFFSET_PCT))
3134 |             
     | ^^^^^^^^^^^^
3135 |             breakeven_sl = self.precision_manager.round_price(symbol, breakeven_sl)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3147:1
     |
3146 | …     self.logger.info(Fore.YELLOW + f"Breakeven activated for {symbol}: PnL {current_unrealized_pnl_pct:.2f}% >= {self.config.BREAK…
3147 | …     
 ^^^^^^^^^^^^
3148 | …     try:
3149 | …         self.api_call(
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3172:1
     |
3171 |         current_unrealized_pnl_pct = self.bot_state.unrealized_pnl_pct
3172 |         
     | ^^^^^^^^
3173 |         for i, target in enumerate(self.config.PARTIAL_TP_TARGETS):
3174 |             if not self.partial_tp_targets_hit.get(symbol, {}).get(i, False): # If this target hasn't been hit yet
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3177:1
     |
3175 |                 if current_unrealized_pnl_pct >= Decimal(str(target['profit_pct'])) * Decimal('100'):
3176 |                     qty_to_close = self.initial_position_qty * Decimal(str(target['close_qty_pct']))
3177 |                     
     | ^^^^^^^^^^^^^^^^^^^^
3178 |                     # Ensure we don't try to close more than currently open
3179 |                     current_remaining_qty = Decimal(current_pos['size'])
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3181:1
     |
3179 | …     current_remaining_qty = Decimal(current_pos['size'])
3180 | …     qty_to_close = min(qty_to_close, current_remaining_qty)
3181 | …     
^^^^^^^^^^^^^
3182 | …     if qty_to_close > Decimal('0'):
3183 | …         self.logger.info(Fore.YELLOW + f"Partial TP hit for {symbol} (Target {i+1}): PnL {current_unrealized_pnl_pct:.2f}% >= {tar…
     |
help: Remove whitespace from blank line

W505 Doc line too long (134 > 100)
    --> stupdated.py:3189:101
     |
3187 | …                         self.partial_tp_targets_hit[symbol] = {}
3188 | …                     self.partial_tp_targets_hit[symbol][i] = True
3189 | …                     # After a partial close, `get_positions` will update `self.current_position_size` and `all_open_positions`
     |                                                                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3190 | …                     # which is crucial for subsequent partial TP calculations.
3191 | …                     self.last_trade_time = time.time() # Apply cooldown
     |

W293 Blank line contains whitespace
    --> stupdated.py:3196:1
     |
3194 |                     else:
3195 |                         self.logger.info(f"Partial TP target {i+1} met, but calculated quantity to close is zero or less than curren…
3196 |             
     | ^^^^^^^^^^^^
3197 |     def execute_trade_based_on_signal(self, signal_type: Optional[str], reason: str):
3198 |         """
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3202:1
     |
3200 |         Manages opening new positions, closing existing ones based on signal reversal,
3201 |         and updating stop losses (including trailing stops).
3202 |         
     | ^^^^^^^^
3203 |         Includes checks for:
3204 |         - Cumulative Loss Guard
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3217:1
     |
3215 |             self.logger.warning("Cumulative loss limit reached. Skipping trade execution for this cycle.")
3216 |             return
3217 |         
     | ^^^^^^^^
3218 |         if not self._is_time_to_trade():
3219 |             self.logger.info("Outside allowed trading window. Skipping trade execution for this cycle.")
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3266:1
     |
3264 |                 self.logger.info(f"Exit Signal: Supertrend flipped UP while in a SHORT position. Closing position.")
3265 |                 perform_close = True
3266 |             
     | ^^^^^^^^^^^^
3267 |             if perform_close:
3268 |                 if self.close_position():
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3278:1
     |
3276 | …         self.logger.warning(f"Max concurrent positions limit ({self.config.MAX_CONCURRENT_POSITIONS}) reached. Cannot open new pos…
3277 | …         return
3278 | …     
 ^^^^^^^^^^^^
3279 | …     # FEATURE: Funding Rate Avoidance (Perpetuals)
3280 | …     if self._is_funding_rate_avoidance_active():
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3308:1
     |
3306 |                 order_type_to_place = self.config.ORDER_TYPE_ENUM
3307 |                 entry_price_to_place = current_market_price # Default for market or if retracement not enabled
3308 |                 
     | ^^^^^^^^^^^^^^^^
3309 |                 # FEATURE: Signal Retracement Entry
3310 |                 if self.config.RETRACEMENT_ENTRY_ENABLED:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3316:1
     |
3314 | …     else: # Sell
3315 | …         entry_price_to_place = current_market_price * (Decimal('1') + Decimal(str(self.config.RETRACEMENT_PCT_FROM_CLOSE)))
3316 | …     
^^^^^^^^^^^^^
3317 | …     entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
3318 | …     self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.price_p…
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3319:1
     |
3317 | …         entry_price_to_place = self.precision_manager.round_price(self.config.SYMBOL, entry_price_to_place)
3318 | …         self.logger.info(f"Placing {order_type_to_place.value} order for retracement at {entry_price_to_place:.{self.bot_state.pri…
3319 | …     
^^^^^^^^^^^^^
3320 | …     order_result = self.place_order(
3321 | …         side=trade_side,
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3347:1
     |
3346 | …     self.logger.info(f"{trade_side} order placed and confirmed filled. Entry: {filled_price}, Qty: {filled_qty}.")
3347 | …     
^^^^^^^^^^^^^
3348 | …     # Update BotState with new position
3349 | …     with self.bot_state.lock:
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3394:1
     |
3392 |                 # FEATURE: Breakeven Stop Loss Activation
3393 |                 self._manage_breakeven_stop_loss()
3394 |                 
     | ^^^^^^^^^^^^^^^^
3395 |                 # FEATURE: Partial Take Profit (Scaling Out)
3396 |                 self._manage_partial_take_profit()
     |
help: Remove whitespace from blank line

W505 Doc line too long (116 > 100)
    --> stupdated.py:3400:101
     |
3398 |                 # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing)
3399 |                 if self.config.TRAILING_STOP_PCT > 0 and specs.category != 'spot':
3400 |                     # `get_positions` already fetches markPrice and updates internal state for trailing stop manager
     |                                                                                                     ^^^^^^^^^^^^^^^^
3401 |                     # So we just need to ensure the trailing stop is set/active.
3402 |                     self.trailing_stop_manager.update_trailing_stop(
     |

W293 Blank line contains whitespace
    --> stupdated.py:3434:1
     |
3432 | …     self.ws = WebSocket(testnet=self.config.TESTNET, channel_type=self.config.CATEGORY_ENUM.value)
3433 | …     self.ws.kline_stream(interval=self.config.TIMEFRAME, symbol=self.config.SYMBOL, callback=self._process_websocket_message)
3434 | …     
^^^^^^^^^^^^^
3435 | …     with self.bot_state.lock:
3436 | …         self.bot_state.bot_status = "Running" # Update UI status
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3463:1
     |
3461 |         """Fetches klines, calculates indicators, and updates BotState."""
3462 |         self.logger.info("Updating market data and indicators...")
3463 |         
     | ^^^^^^^^
3464 |         # Primary timeframe data
3465 |         self.market_data = self.fetch_klines(self.config.SYMBOL, self.config.TIMEFRAME, limit=self.config.LOOKBACK_PERIODS)
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> stupdated.py:3492:1
     |
3490 |             self.bot_state.bid_price = bid_price_dec
3491 |             self.bot_state.ask_price = ask_price_dec
3492 |             
     | ^^^^^^^^^^^^
3493 |             latest_indicator_row = self.market_data.iloc[-1]
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:3498:34
     |
3496 |             self.bot_state.ehlers_supertrend_value = Decimal(str(latest_indicator_row.get('supertrend_line_value', '0.0')))
3497 |             direction_val = latest_indicator_row.get('supertrend_direction', 0)
3498 |             if direction_val == 1: self.bot_state.ehlers_supertrend_direction = "UP"
     |                                  ^
3499 |             elif direction_val == -1: self.bot_state.ehlers_supertrend_direction = "DOWN"
3500 |             else: self.bot_state.ehlers_supertrend_direction = "NONE"
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3499:37
     |
3497 |             direction_val = latest_indicator_row.get('supertrend_direction', 0)
3498 |             if direction_val == 1: self.bot_state.ehlers_supertrend_direction = "UP"
3499 |             elif direction_val == -1: self.bot_state.ehlers_supertrend_direction = "DOWN"
     |                                     ^
3500 |             else: self.bot_state.ehlers_supertrend_direction = "NONE"
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3500:17
     |
3498 |             if direction_val == 1: self.bot_state.ehlers_supertrend_direction = "UP"
3499 |             elif direction_val == -1: self.bot_state.ehlers_supertrend_direction = "DOWN"
3500 |             else: self.bot_state.ehlers_supertrend_direction = "NONE"
     |                 ^
3501 |             
3502 |             self.bot_state.ehlers_filter_value = Decimal(str(latest_indicator_row.get('ehlers_filter', '0.0')))
     |

W293 Blank line contains whitespace
    --> stupdated.py:3501:1
     |
3499 |             elif direction_val == -1: self.bot_state.ehlers_supertrend_direction = "DOWN"
3500 |             else: self.bot_state.ehlers_supertrend_direction = "NONE"
3501 |             
     | ^^^^^^^^^^^^
3502 |             self.bot_state.ehlers_filter_value = Decimal(str(latest_indicator_row.get('ehlers_filter', '0.0')))
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:3507:39
     |
3505 |             adx_val = Decimal(str(latest_indicator_row.get('adx', '0.0')))
3506 |             self.bot_state.adx_value = adx_val
3507 |             if adx_val > Decimal('25'): self.bot_state.adx_trend_strength = "Strong"
     |                                       ^
3508 |             elif adx_val > Decimal('20'): self.bot_state.adx_trend_strength = "Developing"
3509 |             else: self.bot_state.adx_trend_strength = "Weak"
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3508:41
     |
3506 |             self.bot_state.adx_value = adx_val
3507 |             if adx_val > Decimal('25'): self.bot_state.adx_trend_strength = "Strong"
3508 |             elif adx_val > Decimal('20'): self.bot_state.adx_trend_strength = "Developing"
     |                                         ^
3509 |             else: self.bot_state.adx_trend_strength = "Weak"
3510 |             self.bot_state.adx_plus_di = Decimal(str(latest_indicator_row.get('adx_plus_di', '0.0')))
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3509:17
     |
3507 |             if adx_val > Decimal('25'): self.bot_state.adx_trend_strength = "Strong"
3508 |             elif adx_val > Decimal('20'): self.bot_state.adx_trend_strength = "Developing"
3509 |             else: self.bot_state.adx_trend_strength = "Weak"
     |                 ^
3510 |             self.bot_state.adx_plus_di = Decimal(str(latest_indicator_row.get('adx_plus_di', '0.0')))
3511 |             self.bot_state.adx_minus_di = Decimal(str(latest_indicator_row.get('adx_minus_di', '0.0')))
     |

W293 Blank line contains whitespace
    --> stupdated.py:3512:1
     |
3510 |             self.bot_state.adx_plus_di = Decimal(str(latest_indicator_row.get('adx_plus_di', '0.0')))
3511 |             self.bot_state.adx_minus_di = Decimal(str(latest_indicator_row.get('adx_minus_di', '0.0')))
3512 |             
     | ^^^^^^^^^^^^
3513 |             # RSI
3514 |             rsi_val = Decimal(str(latest_indicator_row.get('rsi', '0.0')))
     |
help: Remove whitespace from blank line

E701 Multiple statements on one line (colon)
    --> stupdated.py:3516:39
     |
3514 |             rsi_val = Decimal(str(latest_indicator_row.get('rsi', '0.0')))
3515 |             self.bot_state.rsi_value = rsi_val
3516 |             if rsi_val > Decimal('70'): self.bot_state.rsi_state = "Overbought"
     |                                       ^
3517 |             elif rsi_val < Decimal('30'): self.bot_state.rsi_state = "Oversold"
3518 |             else: self.bot_state.rsi_state = "Neutral"
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3517:41
     |
3515 |             self.bot_state.rsi_value = rsi_val
3516 |             if rsi_val > Decimal('70'): self.bot_state.rsi_state = "Overbought"
3517 |             elif rsi_val < Decimal('30'): self.bot_state.rsi_state = "Oversold"
     |                                         ^
3518 |             else: self.bot_state.rsi_state = "Neutral"
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3518:17
     |
3516 |             if rsi_val > Decimal('70'): self.bot_state.rsi_state = "Overbought"
3517 |             elif rsi_val < Decimal('30'): self.bot_state.rsi_state = "Oversold"
3518 |             else: self.bot_state.rsi_state = "Neutral"
     |                 ^
3519 |
3520 |             # MACD
     |

invalid-syntax: Expected an indented block after function definition
    --> stupdated.py:3605:9
     |
3603 |         self.cleanup() # Perform cleanup after the main loop exit
3604 |         def cleanup(self):
3605 |         """Perform cleanup actions before exiting the bot. Enhanced with optional auto-close."""
     |         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3606 |         self.logger.info("Starting bot cleanup process...")
3607 |         try:
     |

invalid-syntax: Expected a statement
    --> stupdated.py:3617:149
     |
3615 | …
3616 | …
3617 | …on. Not closing positions.")                                  except Exception as e:                                               …
     |                                                                ^^^^^^
3618 | …========================================================# MAIN ENTRY POINT                                                     # ==…
3619 | …
     |

invalid-syntax: Expected a statement
    --> stupdated.py:3617:166
     |
3615 | …
3616 | …
3617 | … positions.")                                  except Exception as e:                                                     self.logg…
     |                                                                  ^^
3618 | …=========================================# MAIN ENTRY POINT                                                     # =================…
3619 | …
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3617:170
     |
3615 | …
3616 | …
3617 | …sitions.")                                  except Exception as e:                                                     self.logger.…
     |                                                                   ^
3618 | …======================================# MAIN ENTRY POINT                                                     # ====================…
3619 | …
     |

invalid-syntax: Expected a statement
    --> stupdated.py:3617:362
     |
3615 | …
3616 | …
3617 | …                                                              finally:                                                             …
     |                                                                ^^^^^^^
3618 | …                                                        if __name__ == "__main__":
3619 | …
     |

invalid-syntax: Expected a statement
    --> stupdated.py:3617:369
     |
3615 | …
3616 | …
3617 | …                                                          finally:                                                                 …
     |                                                                   ^
3618 | …                                                    if __name__ == "__main__":
3619 | …
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3617:369
     |
3615 | …
3616 | …
3617 | …                                                          finally:                                                                 …
     |                                                                   ^
3618 | …                                                    if __name__ == "__main__":
3619 | …
     |

invalid-syntax: Simple statements must be separated by newlines or semicolons
    --> stupdated.py:3617:650
     |
3615 | …
3616 | …
3617 | …                                                            subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.confi…
     |                                                              ^^^^^^^^^^
3618 | …
3619 | …
     |

invalid-syntax: Invalid annotated assignment target
    --> stupdated.py:3617:650
     |
3615 | …
3616 | …
3617 | …     subprocess.run(["termux-toast", f"Ehlers SuperTrend Bot for {self.config.SYMBOL} has ceased operations."])                                    if self.sms_notifier.is_enabled:    …
     |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3618 | …
3619 | …
     |

invalid-syntax: Expected 'else', found ':'
    --> stupdated.py:3617:823
     |
3615 | …
3616 | …
3617 | …                                  if self.sms_notifier.is_enabled:                                           self.sms_notifier.send…
     |                                                                   ^
3618 | …
3619 | …
     |

E701 Multiple statements on one line (colon)
    --> stupdated.py:3617:823
     |
3615 | …
3616 | …
3617 | …                                  if self.sms_notifier.is_enabled:                                           self.sms_notifier.send…
     |                                                                   ^
3618 | …
3619 | …
     |

W505 Doc line too long (381 > 100)
    --> stupdated.py:3618:101
     |
3616 | …
3617 | …losing positions.")                                  except Exception as e:                                                     self.logger.error(f"Error during cleanup: {e}", exc_info=True)                                                                            finally:                 …
3618 | …===============================================# MAIN ENTRY POINT                                                     # =====================================================================                                                                       if __name__ == "__main__":
     |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3619 | …
3620 | …
     |

invalid-syntax: Expected `except` or `finally` after `try` block
    --> stupdated.py:3620:5
     |
3618 |                                                                        # ===========================================================…
3619 |     # Load configuration
3620 |     config = Config()
     |     ^
3621 |
3622 |     # Create and run the bot
     |

Found 229 errors.
