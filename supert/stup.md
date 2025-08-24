W505 Doc line too long (102 > 100)
   --> stupdated2.py:558:101
    |
556 |         max_order_qty = safe_decimal(unified_lot_size_filter.get('maxOrderQty', lot_size_filter.get('maxOrderQty', '1e9')))
557 |
558 |         # Max/Min Order Amount for position value limits (in quote currency, e.g., USD for USDT pairs)
    |                                                                                                     ^^
559 |         max_position_value_usd = safe_decimal(unified_lot_size_filter.get('maxOrderAmt', '1e9'))
560 |         min_position_value_usd = safe_decimal(unified_lot_size_filter.get('minOrderAmt', '1')) # minOrderQty is for base units, minOr…
    |

W505 Doc line too long (104 > 100)
   --> stupdated2.py:713:101
    |
711 |         if self.config.VOLATILITY_ADJUSTED_SIZING_ENABLED and current_atr is not None and current_atr > Decimal('0'):
712 |             self.logger.debug(f"Using Volatility-Adjusted Sizing with ATR: {current_atr:.4f}")
713 |             # The goal is to risk a maximum dollar amount (derived from MAX_RISK_PER_TRADE_BALANCE_PCT).
    |                                                                                                     ^^^^
714 |             # Position_Value_USD = (Risk_Amount_USD / (Stop_Loss_Distance_Price / Entry_Price))
715 |             # If the stop_loss_price is dynamically set (e.g., based on ATR),
    |

W505 Doc line too long (101 > 100)
   --> stupdated2.py:716:101
    |
714 |             # Position_Value_USD = (Risk_Amount_USD / (Stop_Loss_Distance_Price / Entry_Price))
715 |             # If the stop_loss_price is dynamically set (e.g., based on ATR),
716 |             # then a larger ATR (higher volatility) will result in a larger stop_loss_distance_price,
    |                                                                                                     ^
717 |             # which in turn leads to a smaller calculated position_value_usd_unadjusted for the same risk amount.
718 |             # This implicitly adjusts position size for volatility.
    |

W505 Doc line too long (113 > 100)
   --> stupdated2.py:717:101
    |
715 |             # If the stop_loss_price is dynamically set (e.g., based on ATR),
716 |             # then a larger ATR (higher volatility) will result in a larger stop_loss_distance_price,
717 |             # which in turn leads to a smaller calculated position_value_usd_unadjusted for the same risk amount.
    |                                                                                                     ^^^^^^^^^^^^^
718 |             # This implicitly adjusts position size for volatility.
    |

W505 Doc line too long (104 > 100)
   --> stupdated2.py:737:101
    |
735 |         max_tradeable_value_usd = account_balance_usdt * leverage
736 |
737 |         # Cap the needed position value by maximum tradeable value and Bybit's max position value limits
    |                                                                                                     ^^^^
738 |         position_value_usd = min(
739 |             position_value_usd_unadjusted,
    |

W505 Doc line too long (102 > 100)
   --> stupdated2.py:814:101
    |
812 |         self.api_call = api_call_wrapper # Reference to the bot's api_call method
813 |         self.config = config # Added config for dynamic trailing
814 |         # Stores active trailing stop info: {symbol: {'side': 'Buy'/'Sell', 'trail_percent': Decimal}}
    |                                                                                                     ^^
815 |         self.active_trailing_stops: dict[str, dict] = {}
816 |         # Store current PnL for dynamic trailing stop logic
    |

W293 Blank line contains whitespace
   --> stupdated2.py:881:1
    |
879 |         Re-confirms or re-sets the trailing stop on the exchange if `update_exchange` is True.
880 |         For Bybit's native `callbackRate`, this usually means ensuring it's still active.
881 |         
    | ^^^^^^^^
882 |         FEATURE: Profit Target Trailing Stop (Dynamic Trailing)
883 |         Adjusts the trailing stop percentage based on current profit tiers.
    |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
   --> stupdated2.py:898:101
    |
897 |         if self.config.DYNAMIC_TRAILING_ENABLED:
898 |             # Sort tiers by profit_pct_trigger in descending order to find the highest applicable tier
    |                                                                                                     ^^
899 |             sorted_tiers = sorted(self.config.TRAILING_PROFIT_TIERS, key=lambda x: x['profit_pct_trigger'], reverse=True)
    |

W505 Doc line too long (101 > 100)
   --> stupdated2.py:917:101
    |
915 |         ts_info = self.active_trailing_stops[symbol]
916 |
917 |         # Update the active_trailing_stops with the new effective_trail_pct BEFORE calling initialize
    |                                                                                                     ^
918 |         # to ensure it's consistent if initialize fails.
919 |         ts_info['trail_percent'] = effective_trail_pct
    |

W505 Doc line too long (110 > 100)
    --> stupdated2.py:1420:101
     |
1418 | …     print(f"{Fore.GREEN}║ Unrealized PNL:         {pnl_color_unrealized}{unrealized_pnl_str}{Fore.GREEN:<{73 - len('Unrealized PNL…
1419 | …     # SL/TP for open position are not stored in BotState.open_position_info.
1420 | …     # If needed, they should be extracted from 'pos' dict in get_positions and passed to BotState.
     |                                                                                           ^^^^^^^^^^
1421 | …     # For now, print placeholders.
1422 | …     print(f"{Fore.GREEN}║ Stop Loss:              {Fore.WHITE}${Decimal('0.0'):.{state.price_precision}f} (N/A){Fore.GREEN:<{73 - …
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated2.py:1422:193
     |
1420 | …
1421 | …
1422 | …e.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1423 | …e.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated2.py:1423:193
     |
1421 | …
1422 | …e.GREEN:<{73 - len('Stop Loss:              ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
1423 | …e.GREEN:<{73 - len('Take Profit:            ') - len(f'${Decimal('0.0'):.{state.price_precision}f} (N/A)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1424 | …
1425 | …
     |

W505 Doc line too long (103 > 100)
    --> stupdated2.py:1427:101
     |
1425 | …     else:
1426 | …         # Consistent padding for "no open position" state
1427 | …         # Adjust formatting to use Decimal('0.0') for consistency and correct precision padding
     |                                                                                               ^^^
1428 | …         print(f"{Fore.GREEN}║ Open Position:          {Fore.WHITE}{Decimal('0.0').quantize(Decimal(f'1e-{state.qty_precision}'))} …
1429 | …         print(f"{Fore.GREEN}║ Avg Entry Price:        {Fore.WHITE}${Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')…
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated2.py:1430:190
     |
1428 | …recision}'))} {state.symbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{stat…
1429 | …e_precision}'))}{Fore.GREEN:<{73 - len('Avg Entry Price:        ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_prec…
1430 | …e.GREEN:<{73 - len('Unrealized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1431 | …e_precision}'))} (N/A){Fore.GREEN:<{73 - len('Stop Loss:              ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.pric…
1432 | …e_precision}'))} (N/A){Fore.GREEN:<{73 - len('Take Profit:            ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.pric…
     |

invalid-syntax: Cannot reuse outer quote character in f-strings on Python 3.10 (syntax was added in Python 3.12)
    --> stupdated2.py:1430:212
     |
1428 | …ymbol}{Fore.GREEN:<{73 - len('Open Position:          ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.qty_precision}'))) +…
1429 | …GREEN:<{73 - len('Avg Entry Price:        ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - 1}}║{Sty…
1430 | …realized PNL:         ') - len(f'${Decimal('0.0'):.2f} ({Decimal('0.0'):+.2f}%)')}}║{Style.RESET_ALL}")
     |                                                                   ^
1431 | …{Fore.GREEN:<{73 - len('Stop Loss:              ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - le…
1432 | …{Fore.GREEN:<{73 - len('Take Profit:            ') - len(str(Decimal('0.0').quantize(Decimal(f'1e-{state.price_precision}')))) - le…
     |

W505 Doc line too long (106 > 100)
    --> stupdated2.py:1621:101
     |
1619 |         upper_shadow = c1['high'] - max(c1['open'], c1['close'])
1620 |
1621 |         # Shooting Star criteria: small body, long upper shadow (at least 2x body), little/no lower shadow
     |                                                                                                     ^^^^^^
1622 |         return body_size > 0 and upper_shadow >= 2 * body_size and lower_shadow < body_size / 2
     |

W505 Doc line too long (112 > 100)
    --> stupdated2.py:1721:101
     |
1720 |         # New: State for Partial Take Profit
1721 |         # {symbol: {target_idx: True}} indicates which partial TP targets have been hit for the current position
     |                                                                                                     ^^^^^^^^^^^^
1722 |         self.partial_tp_targets_hit: dict[str, dict[int, bool]] = {}
1723 |         self.initial_position_qty: Decimal = Decimal('0.0') # Store initial quantity for partial TP
     |

W505 Doc line too long (105 > 100)
    --> stupdated2.py:1987:101
     |
1985 | …     if self.initial_equity <= Decimal('0') or current_equity <= Decimal('0'): # Ensure valid initial and current equity
1986 | …         self.logger.warning(Fore.YELLOW + "Could not fetch valid initial or current equity for cumulative loss guard. Proceeding c…
1987 | …         # Fallback to cumulative PnL-based logic if initial equity wasn't captured or current is zero
     |                                                                                                   ^^^^^
1988 | …         # This fallback assumes initial_equity was at least captured once.
1989 | …         if self.initial_equity > Decimal('0') and self.cumulative_pnl < -abs(Decimal(str(self.config.MAX_DAILY_LOSS_PCT))) * self.…
     |

W293 Blank line contains whitespace
    --> stupdated2.py:2523:1
     |
2521 |         Includes verification if the order was actually filled.
2522 |         Returns the filled order details on success, None otherwise.
2523 |         
     | ^^^^^^^^
2524 |         FEATURE: Slippage Tolerance for Market Orders
2525 |         Checks for excessive slippage for market orders and logs a warning.
     |
help: Remove whitespace from blank line

B007 Loop control variable `i` not used within loop body
    --> stupdated2.py:2587:21
     |
2585 | …     max_retries = 5
2586 | …     retry_delay = 1 # seconds
2587 | …     for i in range(max_retries):
     |           ^
2588 | …         time.sleep(retry_delay)
2589 | …         order_details = self.api_call(self.bybit_client.get_order_history, symbol=self.config.SYMBOL, orderId=order_id, category=s…
     |
help: Rename unused `i` to `_i`

W505 Doc line too long (118 > 100)
    --> stupdated2.py:2605:101
     |
2603 | …     if actual_slippage_pct > Decimal(str(self.config.SLIPPAGE_TOLERANCE_PCT)):
2604 | …         self.logger.warning(Fore.YELLOW + f"⚠️ High Slippage Detected for Market Order {order_id}: {actual_slippage_pct*100:.2f}% …I
2605 | …         # Depending on policy, might raise an error or just log. For now, log and proceed.
     |                                                                           ^^^^^^^^^^^^^^^^^^
2606 | …     else:
2607 | …         self.logger.info(f"Slippage for market order {order_id}: {actual_slippage_pct*100:.2f}% (within tolerance).")
     |

W293 Blank line contains whitespace
    --> stupdated2.py:2762:1
     |
2760 |         Fetch and update current positions for the configured symbol.
2761 |         Also updates BotState with position details.
2762 |         
     | ^^^^^^^^
2763 |         FEATURE: Max Concurrent Positions Limit
2764 |         This method now fetches *all* active positions across the account
     |
help: Remove whitespace from blank line

W505 Doc line too long (102 > 100)
    --> stupdated2.py:2812:101
     |
2810 | …     self.bot_state.open_position_side = position_for_current_symbol['side']
2811 | …     self.bot_state.open_position_entry_price = Decimal(position_for_current_symbol['avgPrice'])
2812 | …     # Unrealized PnL from position data is for last mark price, can be used for UI
     |                                                                                   ^^
2813 | …     self.bot_state.unrealized_pnl = Decimal(position_for_current_symbol.get('unrealisedPnl', '0.0'))
2814 | …     pos_value = Decimal(position_for_current_symbol['size']) * Decimal(position_for_current_symbol.get('markPrice', '0'))
     |

W505 Doc line too long (110 > 100)
    --> stupdated2.py:2971:101
     |
2969 |                 # For realized PnL, Bybit's get_positions gives unrealisedPnl.
2970 |                 # When a position is closed, this becomes realized.
2971 |                 # Here, we use the unrealized PnL from `current_pos` as a proxy for realized PnL upon closure.
     |                                                                                                     ^^^^^^^^^^
2972 |                 pnl_realized = Decimal(current_pos.get('unrealisedPnl', '0.0')) * (qty_to_close / Decimal(current_pos['size']))
2973 |                 self.cumulative_pnl += pnl_realized
     |

SIM102 Use a single `if` statement instead of nested `if` statements
    --> stupdated2.py:3041:17
     |
3039 |   …     time_until_funding = next_funding_dt - datetime.now(dateutil.tz.UTC)
3040 |   …
3041 | / …     if abs(funding_rate) >= Decimal(str(self.config.FUNDING_RATE_THRESHOLD_PCT)):
3042 | | …         if time_until_funding <= timedelta(minutes=self.config.FUNDING_GRACE_PERIOD_MINUTES) and time_until_funding > timedelta(seconds=0):
     | |_____________________________________________________________________________________________________________________________________________^
3043 |   …             self.logger.warning(Fore.YELLOW + f"Funding rate avoidance active: Funding rate {funding_rate*100:.4f}% is high and funding payment …
3044 |   …             return True
     |
help: Combine `if` statements using `and`

SIM102 Use a single `if` statement instead of nested `if` statements
    --> stupdated2.py:3115:13
     |
3113 |   …     # Check if current SL is already better than breakeven_sl
3114 |   …     current_sl_from_exchange = Decimal(current_pos.get('stopLoss', '0'))
3115 | / …     if current_sl_from_exchange > Decimal('0'): # If an SL is already set
3116 | | …         if (self.current_position_side == 'Buy' and current_sl_from_exchange >= breakeven_sl) or \
3117 | | …            (self.current_position_side == 'Sell' and current_sl_from_exchange <= breakeven_sl):
     | |_________________________________________________________________________________________________^
3118 |   …             self.logger.debug(f"Breakeven SL ({breakeven_sl:.{self.bot_state.price_precision}f}) not better than existing SL ({cur…
3119 |   …             self.breakeven_activated[symbol] = True # Consider it activated if current SL is already at or past breakeven
     |
help: Combine `if` statements using `and`

SIM102 Use a single `if` statement instead of nested `if` statements
    --> stupdated2.py:3150:13
     |
3149 |           for i, target in enumerate(self.config.PARTIAL_TP_TARGETS):
3150 | /             if not self.partial_tp_targets_hit.get(symbol, {}).get(i, False): # If this target hasn't been hit yet
3151 | |                 if current_unrealized_pnl_pct >= Decimal(str(target['profit_pct'])) * Decimal('100'):
     | |_____________________________________________________________________________________________________^
3152 |                       qty_to_close = self.initial_position_qty * Decimal(str(target['close_qty_pct']))
     |
help: Combine `if` statements using `and`

W505 Doc line too long (134 > 100)
    --> stupdated2.py:3165:101
     |
3163 | …                         self.partial_tp_targets_hit[symbol] = {}
3164 | …                     self.partial_tp_targets_hit[symbol][i] = True
3165 | …                     # After a partial close, `get_positions` will update `self.current_position_size` and `all_open_positions`
     |                                                                                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3166 | …                     # which is crucial for subsequent partial TP calculations.
3167 | …                     self.last_trade_time = time.time() # Apply cooldown
     |

W293 Blank line contains whitespace
    --> stupdated2.py:3178:1
     |
3176 |         Manages opening new positions, closing existing ones based on signal reversal,
3177 |         and updating stop losses (including trailing stops).
3178 |         
     | ^^^^^^^^
3179 |         Includes checks for:
3180 |         - Cumulative Loss Guard
     |
help: Remove whitespace from blank line

W505 Doc line too long (116 > 100)
    --> stupdated2.py:3376:101
     |
3374 |                 # FEATURE: Trailing Stop Loss Updates (Dynamic Trailing)
3375 |                 if self.config.TRAILING_STOP_PCT > 0 and specs.category != 'spot':
3376 |                     # `get_positions` already fetches markPrice and updates internal state for trailing stop manager
     |                                                                                                     ^^^^^^^^^^^^^^^^
3377 |                     # So we just need to ensure the trailing stop is set/active.
3378 |                     self.trailing_stop_manager.update_trailing_stop(
     |

Found 278 errors (248 fixed, 30 remaining).
No fixes available (5 hidden fixes can be enabled with the `--unsafe-fixes` option).
