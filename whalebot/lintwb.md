E501 Line too long (140 > 88)
   --> whalebot1.0.1.py:289:89
    |
287 | …mbol.endswith("USDT"):
288 | …
289 | … might not be in the expected format (e.g., BTCUSDT). Ensure it's correct for Bybit.{RESET}"
    |                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
290 | …
    |

E501 Line too long (133 > 88)
   --> whalebot1.0.1.py:295:89
    |
293 |         if not isinstance(loop_delay, (int, float)) or loop_delay <= 0:
294 |             logger.error(
295 |                 f"{NEON_RED}Invalid 'loop_delay' in config. It must be a positive number. Using default {LOOP_DELAY_SECONDS}.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
296 |             )
297 |             config["loop_delay"] = LOOP_DELAY_SECONDS
    |

E501 Line too long (94 > 88)
   --> whalebot1.0.1.py:300:89
    |
298 |             is_valid = False
299 |
300 |         risk_per_trade = config.get("trade_management", {}).get("risk_per_trade_percent", 1.0)
    |                                                                                         ^^^^^^
301 |         if not isinstance(risk_per_trade, (int, float)) or not (0 < risk_per_trade <= 100):
302 |             logger.error(
    |

E501 Line too long (91 > 88)
   --> whalebot1.0.1.py:301:89
    |
300 |         risk_per_trade = config.get("trade_management", {}).get("risk_per_trade_percent", 1.0)
301 |         if not isinstance(risk_per_trade, (int, float)) or not (0 < risk_per_trade <= 100):
    |                                                                                         ^^^
302 |             logger.error(
303 |                 f"{NEON_RED}Invalid 'risk_per_trade_percent' in config. It must be between 0 and 100. Using default 1.0.{RESET}"
    |

E501 Line too long (128 > 88)
   --> whalebot1.0.1.py:303:89
    |
301 |         if not isinstance(risk_per_trade, (int, float)) or not (0 < risk_per_trade <= 100):
302 |             logger.error(
303 |                 f"{NEON_RED}Invalid 'risk_per_trade_percent' in config. It must be between 0 and 100. Using default 1.0.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
304 |             )
305 |             config["trade_management"]["risk_per_trade_percent"] = 1.0
    |

E501 Line too long (143 > 88)
   --> whalebot1.0.1.py:316:89
    |
314 | …t=4)
315 | …
316 | …not found. Created default config at {filepath} for symbol {default_config['symbol']}{RESET}"
    |                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
317 | …
318 | …
    |

E501 Line too long (128 > 88)
   --> whalebot1.0.1.py:328:89
    |
326 |         _ensure_config_keys(config, default_config)
327 |         if not _validate_config(config, logger):
328 |             logger.error(f"{NEON_RED}Configuration validation failed. Please correct the issues in {filepath}. Exiting.{RESET}")
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
329 |             sys.exit(1)
330 |         with Path(filepath).open("w", encoding="utf-8") as f_write:
    |

E501 Line too long (96 > 88)
   --> whalebot1.0.1.py:335:89
    |
333 |     except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
334 |         logger.error(
335 |             f"{NEON_RED}Error loading config: {e}. Using default and attempting to save.{RESET}"
    |                                                                                         ^^^^^^^^
336 |         )
337 |         try:
    |

E501 Line too long (123 > 88)
   --> whalebot1.0.1.py:403:89
    |
401 |     return price * quantity * fee_rate
402 |
403 | def calculate_slippage(price: Decimal, quantity: Decimal, slippage_rate: Decimal, side: Literal["BUY", "SELL"]) -> Decimal:
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
404 |     if side == "BUY":
405 |         return price * (Decimal("1") + slippage_rate)
    |

E501 Line too long (92 > 88)
   --> whalebot1.0.1.py:409:89
    |
407 |         return price * (Decimal("1") - slippage_rate)
408 |
409 | def load_indicator_colors(config: dict[str, Any], logger: logging.Logger) -> dict[str, str]:
    |                                                                                         ^^^^
410 |     default_colors = {
411 |         "SMA_10": Fore.LIGHTBLUE_EX,
    |

E501 Line too long (109 > 88)
   --> whalebot1.0.1.py:571:89
    |
569 |                 if ret_code == 30037:
570 |                     self.logger.error(
571 |                         f"{NEON_RED}Insufficient balance on Bybit. Please check your account balance.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^
572 |                     )
573 |                     return None
    |

E501 Line too long (92 > 88)
   --> whalebot1.0.1.py:579:89
    |
577 |         except requests.exceptions.HTTPError as e:
578 |             self.logger.error(
579 |                 f"{NEON_RED}HTTP Error: {e.response.status_code} - {e.response.text}{RESET}"
    |                                                                                         ^^^^
580 |             )
581 |         except requests.exceptions.ConnectionError as e:
    |

E501 Line too long (147 > 88)
   --> whalebot1.0.1.py:665:89
    |
663 | …
664 | …
665 | …r {symbol} {interval} but DataFrame is empty after processing. Raw response: {response}{RESET}"
    |                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
666 | …
667 | …
    |

E501 Line too long (147 > 88)
   --> whalebot1.0.1.py:672:89
    |
670 | …
671 | …
672 | …r {symbol} {interval}. API response might be empty or invalid. Raw response: {response}{RESET}"
    |                                      ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
673 | …
674 | …
    |

E501 Line too long (89 > 88)
   --> whalebot1.0.1.py:719:89
    |
717 |         account_balance = self._get_current_balance()
718 |         risk_per_trade_percent = (
719 |             Decimal(str(self.config["trade_management"]["risk_per_trade_percent"])) / 100
    |                                                                                         ^
720 |         )
721 |         stop_loss_atr_multiple = Decimal(
    |

E501 Line too long (118 > 88)
   --> whalebot1.0.1.py:730:89
    |
728 |         if stop_loss_distance <= 0:
729 |             self.logger.warning(
730 |                 f"{NEON_YELLOW}Calculated stop loss distance is zero or negative. Cannot determine order size.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
731 |             )
732 |             return Decimal("0")
    |

E501 Line too long (119 > 88)
   --> whalebot1.0.1.py:741:89
    |
740 |         self.logger.info(
741 |             f"[{self.symbol}] Calculated order size: {order_qty.normalize()} (Risk: {risk_amount.normalize():.2f} USD)"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
742 |         )
743 |         return order_qty
    |

E501 Line too long (111 > 88)
   --> whalebot1.0.1.py:753:89
    |
751 |         if not self.trade_management_enabled:
752 |             self.logger.info(
753 |                 f"{NEON_YELLOW}[{self.symbol}] Trade management is disabled. Skipping opening position.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^
754 |             )
755 |             return None
    |

E501 Line too long (136 > 88)
   --> whalebot1.0.1.py:759:89
    |
757 | …x_open_positions:
758 | …
759 | … Max open positions ({self.max_open_positions}) reached. Cannot open new position.{RESET}"
    |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
760 | …
761 | …
    |

E501 Line too long (112 > 88)
   --> whalebot1.0.1.py:766:89
    |
764 |         if order_qty <= 0:
765 |             self.logger.warning(
766 |                 f"{NEON_YELLOW}[{self.symbol}] Order quantity is zero or negative. Cannot open position.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^
767 |             )
768 |             return None
    |

E501 Line too long (110 > 88)
   --> whalebot1.0.1.py:778:89
    |
777 |         if signal == "BUY":
778 |             adjusted_entry_price = calculate_slippage(current_price, order_qty, self.slippage_percent, signal)
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^
779 |             stop_loss = adjusted_entry_price - (atr_value * stop_loss_atr_multiple)
780 |             take_profit = adjusted_entry_price + (atr_value * take_profit_atr_multiple)
    |

E501 Line too long (90 > 88)
   --> whalebot1.0.1.py:833:89
    |
831 |             if current_price <= stop_loss:
832 |                 closed_by = "STOP_LOSS"
833 |                 close_price_at_trigger = current_price * (Decimal("1") - slippage_percent)
    |                                                                                         ^^
834 |             elif current_price >= take_profit:
835 |                 closed_by = "TAKE_PROFIT"
    |

E501 Line too long (90 > 88)
   --> whalebot1.0.1.py:836:89
    |
834 |             elif current_price >= take_profit:
835 |                 closed_by = "TAKE_PROFIT"
836 |                 close_price_at_trigger = current_price * (Decimal("1") - slippage_percent)
    |                                                                                         ^^
837 |         elif side == "SELL":
838 |             if current_price >= stop_loss:
    |

E501 Line too long (90 > 88)
   --> whalebot1.0.1.py:840:89
    |
838 |             if current_price >= stop_loss:
839 |                 closed_by = "STOP_LOSS"
840 |                 close_price_at_trigger = current_price * (Decimal("1") + slippage_percent)
    |                                                                                         ^^
841 |             elif current_price <= take_profit:
842 |                 closed_by = "TAKE_PROFIT"
    |

E501 Line too long (90 > 88)
   --> whalebot1.0.1.py:843:89
    |
841 |             elif current_price <= take_profit:
842 |                 closed_by = "TAKE_PROFIT"
843 |                 close_price_at_trigger = current_price * (Decimal("1") + slippage_percent)
    |                                                                                         ^^
844 |
845 |         if closed_by:
    |

E501 Line too long (152 > 88)
   --> whalebot1.0.1.py:891:89
    |
889 | …osition, pnl)
890 | …
891 | … Closed {position['side']} position by {closed_by}: {position}. PnL: {pnl.normalize():.2f}{RESET}"
    |                                    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
892 | …
    |

E501 Line too long (102 > 88)
   --> whalebot1.0.1.py:931:89
    |
929 |         self.total_pnl += pnl
930 |
931 |         entry_fee = calculate_fees(position["entry_price"], position["qty"], self.trading_fee_percent)
    |                                                                                         ^^^^^^^^^^^^^^
932 |         exit_fee = calculate_fees(position["exit_price"], position["qty"], self.trading_fee_percent)
933 |         total_fees = entry_fee + exit_fee
    |

E501 Line too long (100 > 88)
   --> whalebot1.0.1.py:932:89
    |
931 |         entry_fee = calculate_fees(position["entry_price"], position["qty"], self.trading_fee_percent)
932 |         exit_fee = calculate_fees(position["exit_price"], position["qty"], self.trading_fee_percent)
    |                                                                                         ^^^^^^^^^^^^
933 |         total_fees = entry_fee + exit_fee
934 |         self.total_pnl -= total_fees
    |

E501 Line too long (262 > 88)
   --> whalebot1.0.1.py:941:89
    |
939 | …
940 | …
941 | …{pnl.normalize():.2f}, Total Fees: {total_fees.normalize():.2f}, Current Total PnL (after fees): {self.total_pnl.normalize():.2f}, Wins: {self.wins}, Losses: {self.losses}{RESET}"
    |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
942 | …
    |

E501 Line too long (126 > 88)
   --> whalebot1.0.1.py:993:89
    |
991 |         if self.df.empty:
992 |             self.logger.warning(
993 |                 f"{NEON_YELLOW}TradingAnalyzer initialized with an empty DataFrame. Indicators will not be calculated.{RESET}"
    |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
994 |             )
995 |             return
    |

E501 Line too long (125 > 88)
    --> whalebot1.0.1.py:1014:89
     |
1012 |         if len(self.df) < min_data_points:
1013 |             self.logger.debug(
1014 |                 f"[{self.symbol}] Skipping indicator '{name}': Not enough data. Need {min_data_points}, have {len(self.df)}."
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1015 |             )
1016 |             return None
     |

E501 Line too long (142 > 88)
    --> whalebot1.0.1.py:1031:89
     |
1029 | …
1030 | …
1031 | … Indicator '{name}' returned empty or None after calculation. Not enough valid data?{RESET}"
     |                                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1032 | …
1033 | …
     |

E501 Line too long (116 > 88)
    --> whalebot1.0.1.py:1037:89
     |
1035 |         except Exception as e:
1036 |             self.logger.error(
1037 |                 f"{NEON_RED}[{self.symbol}] Error calculating indicator '{name}': {e}. Parameters: {kwargs}.{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1038 |             )
1039 |             return None
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:1286:165
     |
1284 | …
1285 | …
1286 | …                                                               else:
     |                                                                 ^^^^
1287 | …                                                                   self.logger.warning(
1288 | …                                                                      f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_…
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:1286:169
     |
1284 | …
1285 | …
1286 | …                                                             else:
     |                                                                   ^
1287 | …                                                                 self.logger.warning(
1288 | …                                                                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_ke…
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:1286:170
     |
1284 | …
1285 | …
1286 | …                                                            else:
     |                                                                   ^
1287 | …                                                                self.logger.warning(
1288 | …                                                                   f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_key…
     |

invalid-syntax: Unexpected indentation
    --> whalebot1.0.1.py:1287:1
     |
1285 |                             ):
1286 |                                                                                                                                                                     else:
1287 |                                                                                                                                                                         self.…
     | ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1288 |                                                                                                                                                                            f"…
1289 |                                                                                                                                                                         )
     |

E501 Line too long (299 > 88)
    --> whalebot1.0.1.py:1288:89
     |
1286 | …                                                                                 else:
1287 | …                                                                                     self.logger.warning(
1288 | …                                                                                        f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. Skipping storage."
     |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1289 | …                                                                                     )
1290 | …                                                                         elif isinstance(result, pd.Series):
     |

E501 Line too long (191 > 88)
    --> whalebot1.0.1.py:1290:89
     |
1288 | …                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. S…
1289 | …                 )
1290 | …     elif isinstance(result, pd.Series):
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1291 | …         # Ensure the Series is of object dtype to preserve Decimals
1292 | …         series_to_assign = result.astype(object).reindex(self.df.index)
     |

invalid-syntax: unindent does not match any outer indentation level
    --> whalebot1.0.1.py:1290:157
     |
1288 | …                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. S…
1289 | …                 )
1290 | …     elif isinstance(result, pd.Series):
     |       ^
1291 | …         # Ensure the Series is of object dtype to preserve Decimals
1292 | …         series_to_assign = result.astype(object).reindex(self.df.index)
     |

invalid-syntax: Invalid annotated assignment target
    --> whalebot1.0.1.py:1290:162
     |
1288 | …                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. S…
1289 | …                 )
1290 | …     elif isinstance(result, pd.Series):
     |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1291 | …         # Ensure the Series is of object dtype to preserve Decimals
1292 | …         series_to_assign = result.astype(object).reindex(self.df.index)
     |

invalid-syntax: Expected an expression
    --> whalebot1.0.1.py:1290:192
     |
1288 | …                    f"[{self.symbol}] Indicator '{ind_key}' expected {len(result_keys)} results but got {type(result)}: {result}. S…
1289 | …                 )
1290 | …     elif isinstance(result, pd.Series):
     |                                          ^
1291 | …         # Ensure the Series is of object dtype to preserve Decimals
1292 | …         series_to_assign = result.astype(object).reindex(self.df.index)
     |

E501 Line too long (219 > 88)
    --> whalebot1.0.1.py:1291:89
     |
1289 | …                                 )
1290 | …                     elif isinstance(result, pd.Series):
1291 | …                         # Ensure the Series is of object dtype to preserve Decimals
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1292 | …                         series_to_assign = result.astype(object).reindex(self.df.index)
1293 | …                         self.df[result_keys] = series_to_assign
     |

invalid-syntax: Unexpected indentation
    --> whalebot1.0.1.py:1292:1
     |
1290 | …                     elif isinstance(result, pd.Series):
1291 | …                         # Ensure the Series is of object dtype to preserve Decimals
1292 | …                         series_to_assign = result.astype(object).reindex(self.df.index)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1293 | …                         self.df[result_keys] = series_to_assign
1294 | …                         if not result.empty:
     |

E501 Line too long (223 > 88)
    --> whalebot1.0.1.py:1292:89
     |
1290 | …                     elif isinstance(result, pd.Series):
1291 | …                         # Ensure the Series is of object dtype to preserve Decimals
1292 | …                         series_to_assign = result.astype(object).reindex(self.df.index)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1293 | …                         self.df[result_keys] = series_to_assign
1294 | …                         if not result.empty:
     |

E501 Line too long (199 > 88)
    --> whalebot1.0.1.py:1293:89
     |
1291 | …                     # Ensure the Series is of object dtype to preserve Decimals
1292 | …                     series_to_assign = result.astype(object).reindex(self.df.index)
1293 | …                     self.df[result_keys] = series_to_assign
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1294 | …                     if not result.empty:
1295 | …                         self.indicator_values[result_keys] = result.tail(1).item()
     |

E501 Line too long (180 > 88)
    --> whalebot1.0.1.py:1294:89
     |
1292 | …                             series_to_assign = result.astype(object).reindex(self.df.index)
1293 | …                             self.df[result_keys] = series_to_assign
1294 | …                             if not result.empty:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
1296 | …                     else:
     |

E501 Line too long (222 > 88)
    --> whalebot1.0.1.py:1295:89
     |
1293 | …                             self.df[result_keys] = series_to_assign
1294 | …                             if not result.empty:
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1296 | …                     else:
1297 | …                         # This case is less common for indicator results, but for safety:
     |

invalid-syntax: unindent does not match any outer indentation level
    --> whalebot1.0.1.py:1296:153
     |
1294 | …                             if not result.empty:
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
1296 | …                     else:
     |                       ^
1297 | …                         # This case is less common for indicator results, but for safety:
1298 | …                         # Ensure the Series is of object dtype to preserve Decimals
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:1296:157
     |
1294 | …                             if not result.empty:
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
1296 | …                     else:
     |                           ^
1297 | …                         # This case is less common for indicator results, but for safety:
1298 | …                         # Ensure the Series is of object dtype to preserve Decimals
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:1296:158
     |
1294 | …                             if not result.empty:
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
1296 | …                     else:
     |                            ^
1297 | …                         # This case is less common for indicator results, but for safety:
1298 | …                         # Ensure the Series is of object dtype to preserve Decimals
     |

E501 Line too long (221 > 88)
    --> whalebot1.0.1.py:1297:89
     |
1295 | …                                 self.indicator_values[result_keys] = result.tail(1).item()
1296 | …                     else:
1297 | …                         # This case is less common for indicator results, but for safety:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1298 | …                         # Ensure the Series is of object dtype to preserve Decimals
1299 | …                         series_to_assign = pd.Series(result, index=self.df.index, dtype=object)
     |

E501 Line too long (215 > 88)
    --> whalebot1.0.1.py:1298:89
     |
1296 | …                     else:
1297 | …                         # This case is less common for indicator results, but for safety:
1298 | …                         # Ensure the Series is of object dtype to preserve Decimals
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1299 | …                         series_to_assign = pd.Series(result, index=self.df.index, dtype=object)
1300 | …                         self.df[result_keys] = series_to_assign
     |

invalid-syntax: Unexpected indentation
    --> whalebot1.0.1.py:1299:1
     |
1297 | …                     # This case is less common for indicator results, but for safety:
1298 | …                     # Ensure the Series is of object dtype to preserve Decimals
1299 | …                     series_to_assign = pd.Series(result, index=self.df.index, dtype=object)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1300 | …                     self.df[result_keys] = series_to_assign
1301 | …                     self.indicator_values[result_keys] = result
     |

E501 Line too long (227 > 88)
    --> whalebot1.0.1.py:1299:89
     |
1297 | …                     # This case is less common for indicator results, but for safety:
1298 | …                     # Ensure the Series is of object dtype to preserve Decimals
1299 | …                     series_to_assign = pd.Series(result, index=self.df.index, dtype=object)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1300 | …                     self.df[result_keys] = series_to_assign
1301 | …                     self.indicator_values[result_keys] = result
     |

E501 Line too long (195 > 88)
    --> whalebot1.0.1.py:1300:89
     |
1298 | …                     # Ensure the Series is of object dtype to preserve Decimals
1299 | …                     series_to_assign = pd.Series(result, index=self.df.index, dtype=object)
1300 | …                     self.df[result_keys] = series_to_assign
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1301 | …                     self.indicator_values[result_keys] = result
     |

E501 Line too long (199 > 88)
    --> whalebot1.0.1.py:1301:89
     |
1299 | …                                                                              series_to_assign = pd.Series(result, index=self.df.in…
1300 | …                                                                              self.df[result_keys] = series_to_assign
1301 | …                                                                              self.indicator_values[result_keys] = result
     |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1302 | …
1303 | …
     |

E501 Line too long (100 > 88)
    --> whalebot1.0.1.py:1309:89
     |
1307 |         if len(self.df) < initial_len:
1308 |             self.logger.debug(
1309 |                 f"Dropped {initial_len - len(self.df)} rows with NaNs after indicator calculations."
     |                                                                                         ^^^^^^^^^^^^
1310 |             )
     |

E501 Line too long (125 > 88)
    --> whalebot1.0.1.py:1314:89
     |
1312 |         if self.df.empty:
1313 |             self.logger.warning(
1314 |                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty after calculating all indicators and dropping NaNs.{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1315 |             )
1316 |         else:
     |

E501 Line too long (94 > 88)
    --> whalebot1.0.1.py:1318:89
     |
1316 |         else:
1317 |             self.logger.debug(
1318 |                 f"[{self.symbol}] Indicators calculated. Final DataFrame size: {len(self.df)}"
     |                                                                                         ^^^^^^
1319 |             )
     |

E501 Line too long (124 > 88)
    --> whalebot1.0.1.py:1425:89
     |
1423 |         if len(self.df) < period * 3:
1424 |             self.logger.debug(
1425 |                 f"[{self.symbol}] Not enough data for Ehlers SuperTrend (period={period}). Need at least {period * 3} bars."
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1426 |             )
1427 |             return None
     |

E501 Line too long (102 > 88)
    --> whalebot1.0.1.py:1443:89
     |
1441 |         if df_copy.empty:
1442 |             self.logger.warning(
1443 |                 f"[{self.symbol}] Ehlers SuperTrend: DataFrame empty after smoothing. Returning None."
     |                                                                                         ^^^^^^^^^^^^^^
1444 |             )
1445 |             return None
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1517:89
     |
1515 |         if len(self.df) < slow_period + signal_period:
1516 |             # Return NaNs with Decimal type if not enough data
1517 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1518 |             return nan_series, nan_series, nan_series
     |

E501 Line too long (106 > 88)
    --> whalebot1.0.1.py:1521:89
     |
1520 |         # Convert 'close' prices to Decimal for precise calculations
1521 |         close_prices_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^^^^^^^^
1522 |
1523 |         # Calculate EMAs using Decimal
     |

E501 Line too long (102 > 88)
    --> whalebot1.0.1.py:1545:89
     |
1543 |         if len(self.df) <= period:
1544 |             # Return a Series of NaNs with Decimal type if not enough data
1545 |             return pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^
1546 |
1547 |         # Convert 'close' prices to Decimal for precise calculations
     |

E501 Line too long (106 > 88)
    --> whalebot1.0.1.py:1548:89
     |
1547 |         # Convert 'close' prices to Decimal for precise calculations
1548 |         close_prices_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^^^^^^^^
1549 |
1550 |         # Calculate price differences using Decimal
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1609:89
     |
1607 |         if len(self.df) < period * 2:
1608 |             # Return NaNs with Decimal type if not enough data
1609 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1610 |             return nan_series, nan_series, nan_series
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1619:89
     |
1617 |         )
1618 |         if tr is None or tr.isnull().all():
1619 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1620 |             return nan_series, nan_series, nan_series
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1623:89
     |
1622 |         # Convert 'high' and 'low' prices to Decimal for precise calculations
1623 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1624 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1624:89
     |
1622 |         # Convert 'high' and 'low' prices to Decimal for precise calculations
1623 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1624 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1625 |
1626 |         # Calculate Directional Movement (+DM and -DM) using Decimal
     |

E501 Line too long (93 > 88)
    --> whalebot1.0.1.py:1631:89
     |
1630 |         # Initialize final DM Series with Decimal zeros
1631 |         plus_dm_final = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index)
     |                                                                                         ^^^^^
1632 |         minus_dm_final = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index)
     |

E501 Line too long (94 > 88)
    --> whalebot1.0.1.py:1632:89
     |
1630 |         # Initialize final DM Series with Decimal zeros
1631 |         plus_dm_final = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index)
1632 |         minus_dm_final = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index)
     |                                                                                         ^^^^^^
1633 |
1634 |         # Populate final DM values using Decimal comparisons
     |

E501 Line too long (132 > 88)
    --> whalebot1.0.1.py:1646:89
     |
1644 | …DI and -DI) using Decimal
1645 | …
1646 | …iod, adjust=False).mean() / atr.replace(Decimal('0'), Decimal('NaN'))) * Decimal('100')
     |                                             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1647 | …eriod, adjust=False).mean() / atr.replace(Decimal('0'), Decimal('NaN'))) * Decimal('100')
     |

E501 Line too long (134 > 88)
    --> whalebot1.0.1.py:1647:89
     |
1645 | …
1646 | …od, adjust=False).mean() / atr.replace(Decimal('0'), Decimal('NaN'))) * Decimal('100')
1647 | …riod, adjust=False).mean() / atr.replace(Decimal('0'), Decimal('NaN'))) * Decimal('100')
     |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1648 | …
1649 | …dling potential NaNs
     |

E501 Line too long (107 > 88)
    --> whalebot1.0.1.py:1654:89
     |
1653 |         # Calculate DX, handling division by zero
1654 |         dx = (di_diff / di_sum.replace(Decimal('0'), Decimal('NaN'))).fillna(Decimal('0')) * Decimal('100')
     |                                                                                         ^^^^^^^^^^^^^^^^^^^
1655 |
1656 |         # Calculate ADX using EMA with Decimal
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1673:89
     |
1671 |         if len(self.df) < period:
1672 |             # Return NaNs with Decimal type if not enough data
1673 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1674 |             return nan_series, nan_series, nan_series
     |

E501 Line too long (106 > 88)
    --> whalebot1.0.1.py:1677:89
     |
1676 |         # Convert 'close' prices to Decimal for precise calculations
1677 |         close_prices_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^^^^^^^^
1678 |
1679 |         # Calculate middle band (SMA) using Decimal
     |

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:1680:89
     |
1679 |         # Calculate middle band (SMA) using Decimal
1680 |         middle_band = close_prices_decimal.rolling(window=period, min_periods=period).mean()
     |                                                                                         ^^^^
1681 |
1682 |         # Calculate standard deviation using Decimal
     |

E501 Line too long (102 > 88)
    --> whalebot1.0.1.py:1699:89
     |
1697 |         if self.df.empty:
1698 |             # Return NaNs with Decimal type if DataFrame is empty
1699 |             return pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^
1700 |
1701 |         # Convert relevant columns to Decimal for precise calculations
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1702:89
     |
1701 |         # Convert relevant columns to Decimal for precise calculations
1702 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1703 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1704 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1703:89
     |
1701 |         # Convert relevant columns to Decimal for precise calculations
1702 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1703 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1704 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
1705 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1704:89
     |
1702 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1703 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1704 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^
1705 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:1705:89
     |
1703 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1704 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
1705 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^^^
1706 |
1707 |         # Calculate typical price using Decimal
     |

E501 Line too long (89 > 88)
    --> whalebot1.0.1.py:1710:89
     |
1708 |         typical_price = (high_decimal + low_decimal + close_decimal) / Decimal('3')
1709 |
1710 |         # Calculate cumulative typical price * volume and cumulative volume using Decimal
     |                                                                                         ^
1711 |         cumulative_tp_vol = (typical_price * volume_decimal).cumsum()
1712 |         cumulative_vol = volume_decimal.cumsum()
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1725:89
     |
1723 |         if len(self.df) < period:
1724 |             # Return NaNs with Decimal type if not enough data
1725 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1726 |             return nan_series
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1729:89
     |
1728 |         # Convert relevant columns to Decimal for precise calculations
1729 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1730 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1731 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1730:89
     |
1728 |         # Convert relevant columns to Decimal for precise calculations
1729 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1730 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1731 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1731:89
     |
1729 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1730 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1731 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^
1732 |
1733 |         # Calculate typical price using Decimal
     |

E501 Line too long (113 > 88)
    --> whalebot1.0.1.py:1742:89
     |
1740 |         # The lambda function needs to be adapted for Decimal objects
1741 |         mad = tp.rolling(window=period, min_periods=period).apply(
1742 |             lambda x: sum(abs(val - x.mean()) for val in x) / period if not x.isnull().all() else Decimal('NaN'),
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^
1743 |             raw=False,
1744 |         )
     |

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:1747:89
     |
1746 |         # Calculate CCI, handling division by zero
1747 |         cci = (tp - sma_tp) / (Decimal('0.015') * mad.replace(Decimal('0'), Decimal('NaN')))
     |                                                                                         ^^^^
1748 |
1749 |         # Ensure NaNs are handled correctly for Decimal Series
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1757:89
     |
1755 |         if len(self.df) < period:
1756 |             # Return NaNs with Decimal type if not enough data
1757 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1758 |             return nan_series
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1761:89
     |
1760 |         # Convert relevant columns to Decimal for precise calculations
1761 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1762 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1763 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1762:89
     |
1760 |         # Convert relevant columns to Decimal for precise calculations
1761 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1762 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1763 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1763:89
     |
1761 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1762 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1763 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^
1764 |
1765 |         # Calculate highest high and lowest low using Decimal
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1788:89
     |
1786 |         chikou_span_offset: int,
1787 |     ) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
1788 |         required_bars = max(tenkan_period, kijun_period, senkou_span_b_period) + chikou_span_offset
     |                                                                                         ^^^^^^^^^^^
1789 |         if len(self.df) < required_bars:
1790 |             # Return NaNs with Decimal type if not enough data
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1791:89
     |
1789 |         if len(self.df) < required_bars:
1790 |             # Return NaNs with Decimal type if not enough data
1791 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1792 |             return nan_series, nan_series, nan_series, nan_series, nan_series
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1795:89
     |
1794 |         # Convert 'high' and 'low' prices to Decimal for precise calculations
1795 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1796 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1797 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1796:89
     |
1794 |         # Convert 'high' and 'low' prices to Decimal for precise calculations
1795 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1796 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1797 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1797:89
     |
1795 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1796 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1797 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^
1798 |
1799 |         # Calculate Tenkan-sen using Decimal
     |

E501 Line too long (91 > 88)
    --> whalebot1.0.1.py:1829:89
     |
1827 |         tenkan_sen = tenkan_sen.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
1828 |         kijun_sen = kijun_sen.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
1829 |         senkou_span_a = senkou_span_a.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
     |                                                                                         ^^^
1830 |         senkou_span_b = senkou_span_b.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
1831 |         chikou_span = chikou_span.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
     |

E501 Line too long (91 > 88)
    --> whalebot1.0.1.py:1830:89
     |
1828 |         kijun_sen = kijun_sen.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
1829 |         senkou_span_a = senkou_span_a.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
1830 |         senkou_span_b = senkou_span_b.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
     |                                                                                         ^^^
1831 |         chikou_span = chikou_span.apply(lambda x: x if pd.notna(x) else Decimal('NaN'))
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1838:89
     |
1836 |         if len(self.df) <= period:
1837 |             # Return NaNs with Decimal type if not enough data
1838 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1839 |             return nan_series
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1842:89
     |
1841 |         # Convert relevant columns to Decimal for precise calculations
1842 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^
1843 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1844 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:1843:89
     |
1841 |         # Convert relevant columns to Decimal for precise calculations
1842 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1843 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
     |                                                                                         ^^^^^^^
1844 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
1845 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:1844:89
     |
1842 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index)
1843 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1844 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^
1845 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:1845:89
     |
1843 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index)
1844 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index)
1845 |         volume_decimal = pd.Series([Decimal(str(p)) for p in self.df["volume"]], index=self.df.index)
     |                                                                                         ^^^^^^^^^^^^^
1846 |
1847 |         # Calculate typical price using Decimal
     |

E501 Line too long (187 > 88)
    --> whalebot1.0.1.py:1889:89
     |
1887 | …
1888 | …
1889 | …x=self.df.index, dtype=object), pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
1890 | …
1891 | …
     |

E501 Line too long (115 > 88)
    --> whalebot1.0.1.py:1901:89
     |
1900 |         # Ensure volume is treated as Decimal
1901 |         volume_decimal = pd.Series([Decimal(str(v)) for v in self.df["volume"]], index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^
1902 |
1903 |         # Initialize OBV Series with Decimal zeros
     |

E501 Line too long (97 > 88)
    --> whalebot1.0.1.py:1904:89
     |
1903 |         # Initialize OBV Series with Decimal zeros
1904 |         obv = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^
1905 |         
1906 |         # Calculate direction using Decimal sign function
     |

W293 Blank line contains whitespace
    --> whalebot1.0.1.py:1905:1
     |
1903 |         # Initialize OBV Series with Decimal zeros
1904 |         obv = pd.Series([Decimal('0.0')] * len(self.df.index), index=self.df.index, dtype=object)
1905 |         
     | ^^^^^^^^
1906 |         # Calculate direction using Decimal sign function
1907 |         close_diff = self.df["close"].diff()
     |
help: Remove whitespace from blank line

W293 Blank line contains whitespace
    --> whalebot1.0.1.py:1910:1
     |
1908 |         # Fill NaN in diff with Decimal('0') before applying sign
1909 |         obv_direction = close_diff.fillna(Decimal('0')).apply(decimal_sign)
1910 |         
     | ^^^^^^^^
1911 |         obv = (obv_direction * volume_decimal)
     |
help: Remove whitespace from blank line

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:1942:89
     |
1940 |         if len(self.df) < MIN_DATA_POINTS_PSAR:
1941 |             # Return NaNs with Decimal type if not enough data
1942 |             nan_series = pd.Series([Decimal('NaN')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
1943 |             return nan_series, nan_series
     |

E501 Line too long (113 > 88)
    --> whalebot1.0.1.py:1950:89
     |
1949 |         # Ensure close, high, low are treated as Decimal
1950 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^
1951 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index, dtype=object)
1952 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index, dtype=object)
     |

E501 Line too long (111 > 88)
    --> whalebot1.0.1.py:1951:89
     |
1949 |         # Ensure close, high, low are treated as Decimal
1950 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index, dtype=object)
1951 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^
1952 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index, dtype=object)
     |

E501 Line too long (109 > 88)
    --> whalebot1.0.1.py:1952:89
     |
1950 |         close_decimal = pd.Series([Decimal(str(p)) for p in self.df["close"]], index=self.df.index, dtype=object)
1951 |         high_decimal = pd.Series([Decimal(str(p)) for p in self.df["high"]], index=self.df.index, dtype=object)
1952 |         low_decimal = pd.Series([Decimal(str(p)) for p in self.df["low"]], index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^
1953 |
1954 |         psar = close_decimal.copy()
     |

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:2017:89
     |
2015 |                 )
2016 |
2017 |         # Initialize direction Series with Decimal('0') and use Decimal values for direction
     |                                                                                         ^^^^
2018 |         direction = pd.Series([Decimal('0')] * len(self.df.index), index=self.df.index, dtype=object)
2019 |         direction[psar < close_decimal] = Decimal('1')
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:2018:89
     |
2017 |         # Initialize direction Series with Decimal('0') and use Decimal values for direction
2018 |         direction = pd.Series([Decimal('0')] * len(self.df.index), index=self.df.index, dtype=object)
     |                                                                                         ^^^^^^^^^^^^^
2019 |         direction[psar < close_decimal] = Decimal('1')
2020 |         direction[psar > close_decimal] = Decimal('-1')
     |

E501 Line too long (113 > 88)
    --> whalebot1.0.1.py:2028:89
     |
2026 |         if len(self.df) < window:
2027 |             self.logger.warning(
2028 |                 f"{NEON_YELLOW}[{self.symbol}] Not enough data for Fibonacci levels (need {window} bars).{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^
2029 |             )
2030 |             return
     |

E501 Line too long (117 > 88)
    --> whalebot1.0.1.py:2039:89
     |
2037 |         if diff <= 0:
2038 |             self.logger.warning(
2039 |                 f"{NEON_YELLOW}[{self.symbol}] Invalid high-low range for Fibonacci calculation. Diff: {diff}{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2040 |             )
2041 |             return
     |

E501 Line too long (117 > 88)
    --> whalebot1.0.1.py:2083:89
     |
2081 |         if self.df.empty or len(self.df) < 2:
2082 |             self.logger.warning(
2083 |                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is too short for Fibonacci Pivot Points calculation.{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2084 |             )
2085 |             return
     |

E501 Line too long (149 > 88)
    --> whalebot1.0.1.py:2326:89
     |
2324 | …
2325 | …se"]:
2326 | …["low"]) > 2 * body_length and (current_bar["high"] - current_bar["close"]) < 0.5 * body_length:
     |                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2327 | …
2328 | …
     |

E501 Line too long (149 > 88)
    --> whalebot1.0.1.py:2329:89
     |
2327 | …
2328 | …
2329 | …["open"]) > 2 * body_length and (current_bar["close"] - current_bar["low"]) < 0.5 * body_length:
     |                                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2330 | …
     |

E501 Line too long (108 > 88)
    --> whalebot1.0.1.py:2349:89
     |
2347 |         imbalance = (bid_volume - ask_volume) / (bid_volume + ask_volume)
2348 |         self.logger.debug(
2349 |             f"[{self.symbol}] Orderbook Imbalance: {imbalance:.4f} (Bids: {bid_volume}, Asks: {ask_volume})"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^
2350 |         )
2351 |         return float(imbalance)
     |

E501 Line too long (103 > 88)
    --> whalebot1.0.1.py:2382:89
     |
2380 |             )
2381 |             self.logger.debug(
2382 |                 f"[{self.symbol}] Identified Support Level: {support_level} (Volume: {max_bid_volume})"
     |                                                                                         ^^^^^^^^^^^^^^^
2383 |             )
2384 |         if resistance_level > 0:
     |

E501 Line too long (109 > 88)
    --> whalebot1.0.1.py:2390:89
     |
2388 |             )
2389 |             self.logger.debug(
2390 |                 f"[{self.symbol}] Identified Resistance Level: {resistance_level} (Volume: {max_ask_volume})"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^
2391 |             )
     |

E501 Line too long (110 > 88)
    --> whalebot1.0.1.py:2403:89
     |
2401 |             if len(higher_tf_df) < period:
2402 |                 self.logger.debug(
2403 |                     f"[{self.symbol}] MTF SMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^
2404 |                 )
2405 |                 return "UNKNOWN"
     |

E501 Line too long (110 > 88)
    --> whalebot1.0.1.py:2420:89
     |
2418 |             if len(higher_tf_df) < period:
2419 |                 self.logger.debug(
2420 |                     f"[{self.symbol}] MTF EMA: Not enough data for {period} period. Have {len(higher_tf_df)}."
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^
2421 |                 )
2422 |                 return "UNKNOWN"
     |

E501 Line too long (125 > 88)
    --> whalebot1.0.1.py:2468:89
     |
2466 |         if self.df.empty:
2467 |             self.logger.warning(
2468 |                 f"{NEON_YELLOW}[{self.symbol}] DataFrame is empty in generate_trading_signal. Cannot generate signal.{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
2469 |             )
2470 |             return "HOLD", 0.0, {}
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:2473:89
     |
2472 |         current_close = Decimal(str(self.df["close"].iloc[-1]))
2473 |         prev_close = Decimal(str(self.df["close"].iloc[-2])) if len(self.df) > 1 else current_close
     |                                                                                         ^^^^^^^^^^^
2474 |
2475 |         trend_strength_multiplier = 1.0
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:2489:89
     |
2487 |                         adx_contrib = adx_weight
2488 |                         self.logger.debug(
2489 |                             f"ADX: Strong BUY trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, +DI > -DI)."
     |                                                                                         ^^^^^^^^^^^^^
2490 |                         )
2491 |                         trend_strength_multiplier = 1.2
     |

E501 Line too long (102 > 88)
    --> whalebot1.0.1.py:2495:89
     |
2493 |                         adx_contrib = -adx_weight
2494 |                         self.logger.debug(
2495 |                             f"ADX: Strong SELL trend (ADX > {ADX_STRONG_TREND_THRESHOLD}, -DI > +DI)."
     |                                                                                         ^^^^^^^^^^^^^^
2496 |                         )
2497 |                         trend_strength_multiplier = 1.2
     |

E501 Line too long (94 > 88)
    --> whalebot1.0.1.py:2500:89
     |
2498 |                 elif adx_val < ADX_WEAK_TREND_THRESHOLD:
2499 |                     self.logger.debug(
2500 |                         f"ADX: Weak trend (ADX < {ADX_WEAK_TREND_THRESHOLD}). Neutral signal."
     |                                                                                         ^^^^^^
2501 |                     )
2502 |                     trend_strength_multiplier = 0.8
     |

E501 Line too long (89 > 88)
    --> whalebot1.0.1.py:2565:89
     |
2563 |                         stoch_contrib = momentum_weight * 0.6
2564 |                         self.logger.debug(
2565 |                             f"[{self.symbol}] StochRSI: Bullish crossover from oversold."
     |                                                                                         ^
2566 |                         )
2567 |                     elif (
     |

E501 Line too long (91 > 88)
    --> whalebot1.0.1.py:2574:89
     |
2572 |                         stoch_contrib = -momentum_weight * 0.6
2573 |                         self.logger.debug(
2574 |                             f"[{self.symbol}] StochRSI: Bearish crossover from overbought."
     |                                                                                         ^^^
2575 |                         )
2576 |                     elif stoch_k > stoch_d and stoch_k < STOCH_RSI_MID_POINT:
     |

E501 Line too long (90 > 88)
    --> whalebot1.0.1.py:2734:89
     |
2732 |                 elif current_close > pivot and prev_close <= pivot:
2733 |                     signal_score += fib_pivot_contrib * 0.2
2734 |                     signal_breakdown["Fibonacci Pivot Breakout"] = fib_pivot_contrib * 0.2
     |                                                                                         ^^
2735 |                 
2736 |                 if current_close < s1 and prev_close >= s1:
     |

W293 Blank line contains whitespace
    --> whalebot1.0.1.py:2735:1
     |
2733 |                     signal_score += fib_pivot_contrib * 0.2
2734 |                     signal_breakdown["Fibonacci Pivot Breakout"] = fib_pivot_contrib * 0.2
2735 |                 
     | ^^^^^^^^^^^^^^^^
2736 |                 if current_close < s1 and prev_close >= s1:
2737 |                     signal_score -= fib_pivot_contrib * 0.5
     |
help: Remove whitespace from blank line

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:2744:89
     |
2742 |                 elif current_close < pivot and prev_close >= pivot:
2743 |                     signal_score -= fib_pivot_contrib * 0.2
2744 |                     signal_breakdown["Fibonacci Pivot Breakdown"] = -fib_pivot_contrib * 0.2
     |                                                                                         ^^^^
2745 |
2746 |         if active_indicators.get("ehlers_supertrend", False):
     |

E501 Line too long (99 > 88)
    --> whalebot1.0.1.py:2768:89
     |
2766 |                     st_contrib = weight
2767 |                     self.logger.debug(
2768 |                         "Ehlers SuperTrend: Strong BUY signal (fast flip aligned with slow trend)."
     |                                                                                         ^^^^^^^^^^^
2769 |                     )
2770 |                 elif st_slow_dir == -1 and st_fast_dir == -1 and prev_st_fast_dir == 1:
     |

E501 Line too long (100 > 88)
    --> whalebot1.0.1.py:2773:89
     |
2771 |                     st_contrib = -weight
2772 |                     self.logger.debug(
2773 |                         "Ehlers SuperTrend: Strong SELL signal (fast flip aligned with slow trend)."
     |                                                                                         ^^^^^^^^^^^^
2774 |                     )
2775 |                 elif st_slow_dir == 1 and st_fast_dir == 1:
     |

E501 Line too long (91 > 88)
    --> whalebot1.0.1.py:2886:89
     |
2884 |                     ichimoku_contrib += weight * 0.3
2885 |                     self.logger.debug(
2886 |                         "Ichimoku: Chikou Span crossed above price (bullish confirmation)."
     |                                                                                         ^^^
2887 |                     )
2888 |                 elif (
     |

E501 Line too long (91 > 88)
    --> whalebot1.0.1.py:2894:89
     |
2892 |                     ichimoku_contrib -= weight * 0.3
2893 |                     self.logger.debug(
2894 |                         "Ichimoku: Chikou Span crossed below price (bearish confirmation)."
     |                                                                                         ^^^
2895 |                     )
2896 |                 signal_score += ichimoku_contrib
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:3046:89
     |
3044 |                         rv_contrib = weight
3045 |                         self.logger.debug(
3046 |                             f"Volume: High relative bullish volume ({relative_volume:.2f}x average)."
     |                                                                                         ^^^^^^^^^^^^^
3047 |                         )
3048 |                     elif current_close < prev_close:
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:3051:89
     |
3049 |                         rv_contrib = -weight
3050 |                         self.logger.debug(
3051 |                             f"Volume: High relative bearish volume ({relative_volume:.2f}x average)."
     |                                                                                         ^^^^^^^^^^^^^
3052 |                         )
3053 |                 signal_score += rv_contrib
     |

E501 Line too long (104 > 88)
    --> whalebot1.0.1.py:3190:89
     |
3188 |                     mtf_contribution = mtf_weight * 1.5
3189 |                     self.logger.debug(
3190 |                         f"MTF: All {total_mtf_indicators} higher TFs are UP. Strong bullish confluence."
     |                                                                                         ^^^^^^^^^^^^^^^^
3191 |                     )
3192 |                 elif mtf_sell_count == total_mtf_indicators:
     |

E501 Line too long (106 > 88)
    --> whalebot1.0.1.py:3195:89
     |
3193 |                     mtf_contribution = -mtf_weight * 1.5
3194 |                     self.logger.debug(
3195 |                         f"MTF: All {total_mtf_indicators} higher TFs are DOWN. Strong bearish confluence."
     |                                                                                         ^^^^^^^^^^^^^^^^^^
3196 |                     )
3197 |                 else:
     |

E501 Line too long (125 > 88)
    --> whalebot1.0.1.py:3206:89
     |
3204 |                 signal_breakdown["MTF Confluence"] = mtf_contribution
3205 |                 self.logger.debug(
3206 |                     f"MTF Confluence: Buy: {mtf_buy_count}, Sell: {mtf_sell_count}. MTF contribution: {mtf_contribution:.2f}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3207 |                 )
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:3217:89
     |
3216 |         self.logger.info(
3217 |             f"{NEON_YELLOW}Raw Signal Score: {signal_score:.2f}, Final Signal: {final_signal}{RESET}"
     |                                                                                         ^^^^^^^^^^^^^
3218 |         )
3219 |         return final_signal, signal_score, signal_breakdown
     |

invalid-syntax: Expected a statement
    --> whalebot1.0.1.py:3252:1
     |
3252 | def display_indicator_values_and_price(
     | ^
3253 |     config: dict[str, Any],
3254 |     logger: logging.Logger,
     |

E501 Line too long (100 > 88)
    --> whalebot1.0.1.py:3266:89
     |
3264 |     if analyzer.df.empty:
3265 |         logger.warning(
3266 |             f"{NEON_YELLOW}Cannot display indicators: DataFrame is empty after calculations.{RESET}"
     |                                                                                         ^^^^^^^^^^^^
3267 |         )
3268 |         return
     |

E501 Line too long (141 > 88)
    --> whalebot1.0.1.py:3295:89
     |
3293 | …i Pivot Points ---{RESET}")
3294 | …
3295 | …, NEON_YELLOW)}Pivot              : {analyzer.indicator_values['Pivot'].normalize()}{RESET}"
     |                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3296 | …
3297 | …
     |

E501 Line too long (134 > 88)
    --> whalebot1.0.1.py:3298:89
     |
3296 | …
3297 | …
3298 | …, NEON_GREEN)}R1                 : {analyzer.indicator_values['R1'].normalize()}{RESET}"
     |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3299 | …
3300 | …
     |

E501 Line too long (134 > 88)
    --> whalebot1.0.1.py:3301:89
     |
3299 | …
3300 | …
3301 | …, NEON_GREEN)}R2                 : {analyzer.indicator_values['R2'].normalize()}{RESET}"
     |                                            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3302 | …
3303 | …
     |

E501 Line too long (132 > 88)
    --> whalebot1.0.1.py:3304:89
     |
3302 |             )
3303 |             logger.info(
3304 |                 f"  {INDICATOR_COLORS.get('S1', NEON_RED)}S1                 : {analyzer.indicator_values['S1'].normalize()}{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3305 |             )
3306 |             logger.info(
     |

E501 Line too long (132 > 88)
    --> whalebot1.0.1.py:3307:89
     |
3305 |             )
3306 |             logger.info(
3307 |                 f"  {INDICATOR_COLORS.get('S2', NEON_RED)}S2                 : {analyzer.indicator_values['S2'].normalize()}{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3308 |             )
     |

E501 Line too long (156 > 88)
    --> whalebot1.0.1.py:3317:89
     |
3315 | …
3316 | …
3317 | …, NEON_YELLOW)}Support Level     : {analyzer.indicator_values['Support_Level'].normalize()}{RESET}"
     |                                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3318 | …
3319 | …s:
     |

E501 Line too long (162 > 88)
    --> whalebot1.0.1.py:3321:89
     |
3319 | …
3320 | …
3321 | …, NEON_YELLOW)}Resistance Level  : {analyzer.indicator_values['Resistance_Level'].normalize()}{RESET}"
     |                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3322 | …
     |

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:3397:89
     |
3395 |                 if plus_di > minus_di:
3396 |                     trend_summary_lines.append(
3397 |                         f"{Fore.LIGHTGREEN_EX}ADX Trend  : Strong Up ({adx_val:.0f}){RESET}"
     |                                                                                         ^^^^
3398 |                     )
3399 |                 else:
     |

E501 Line too long (92 > 88)
    --> whalebot1.0.1.py:3401:89
     |
3399 |                 else:
3400 |                     trend_summary_lines.append(
3401 |                         f"{Fore.LIGHTRED_EX}ADX Trend  : Strong Down ({adx_val:.0f}){RESET}"
     |                                                                                         ^^^^
3402 |                     )
3403 |         elif adx_val < ADX_WEAK_TREND_THRESHOLD:
     |

E501 Line too long (98 > 88)
    --> whalebot1.0.1.py:3439:89
     |
3437 |             elif up_count > down_count:
3438 |                 trend_summary_lines.append(
3439 |                     f"{Fore.LIGHTGREEN_EX}MTF Confl. : Mostly Bullish ({up_count}/{total}){RESET}"
     |                                                                                         ^^^^^^^^^^
3440 |                 )
3441 |             elif down_count > up_count:
     |

E501 Line too long (98 > 88)
    --> whalebot1.0.1.py:3443:89
     |
3441 |             elif down_count > up_count:
3442 |                 trend_summary_lines.append(
3443 |                     f"{Fore.LIGHTRED_EX}MTF Confl. : Mostly Bearish ({down_count}/{total}){RESET}"
     |                                                                                         ^^^^^^^^^^
3444 |                 )
3445 |             else:
     |

E501 Line too long (114 > 88)
    --> whalebot1.0.1.py:3447:89
     |
3445 |             else:
3446 |                 trend_summary_lines.append(
3447 |                     f"{Fore.YELLOW}MTF Confl. : Mixed ({up_count}/{total} Bull, {down_count}/{total} Bear){RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^
3448 |                 )
     |

E501 Line too long (169 > 88)
    --> whalebot1.0.1.py:3480:89
     |
3478 | …
3479 | …
3480 | …rval']}' in config.json. Please use Bybit's valid string formats (e.g., '15', '60', 'D'). Exiting.{RESET}"
     |                           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3481 | …
3482 | …
     |

E501 Line too long (172 > 88)
    --> whalebot1.0.1.py:3487:89
     |
3485 | …
3486 | …
3487 | …tf_interval}' in config.json. Please use Bybit's valid string formats (e.g., '60', '240'). Exiting.{RESET}"
     |                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3488 | …
3489 | …
     |

E501 Line too long (129 > 88)
    --> whalebot1.0.1.py:3501:89
     |
3499 |         try:
3500 |             logger.info(
3501 |                 f"{NEON_PURPLE}--- New Analysis Loop Started ({datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M:%S')}) ---{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3502 |             )
3503 |             current_price = bybit_client.fetch_current_price(config["symbol"])
     |

E501 Line too long (90 > 88)
    --> whalebot1.0.1.py:3510:89
     |
3508 |             if current_price is None:
3509 |                 alert_system.send_alert(
3510 |                     f"[{config['symbol']}] Failed to fetch current price. Skipping loop.",
     |                                                                                         ^^
3511 |                     "WARNING",
3512 |                 )
     |

E501 Line too long (113 > 88)
    --> whalebot1.0.1.py:3519:89
     |
3517 |             if df is None or df.empty:
3518 |                 alert_system.send_alert(
3519 |                     f"[{config['symbol']}] Failed to fetch primary klines or DataFrame is empty. Skipping loop.",
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^
3520 |                     "WARNING",
3521 |                 )
     |

E501 Line too long (158 > 88)
    --> whalebot1.0.1.py:3559:89
     |
3557 | …
3558 | …
3559 | … klines for higher timeframe {htf_interval} or it was empty. Skipping MTF trend for this TF.{RESET}"
     |                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3560 | …
3561 | …_request_delay_seconds"])
     |

E501 Line too long (133 > 88)
    --> whalebot1.0.1.py:3567:89
     |
3565 |             if analyzer.df.empty:
3566 |                 alert_system.send_alert(
3567 |                     f"[{config['symbol']}] TradingAnalyzer DataFrame is empty after indicator calculations. Cannot generate signal.",
     |                                                                                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3568 |                     "WARNING",
3569 |                 )
     |

E501 Line too long (95 > 88)
    --> whalebot1.0.1.py:3601:89
     |
3599 |             ):
3600 |                 logger.info(
3601 |                     f"{NEON_GREEN}Strong BUY signal detected! Score: {signal_score:.2f}{RESET}"
     |                                                                                         ^^^^^^^
3602 |                 )
3603 |                 position_manager.open_position("BUY", current_price, atr_value)
     |

E501 Line too long (94 > 88)
    --> whalebot1.0.1.py:3609:89
     |
3607 |             ):
3608 |                 logger.info(
3609 |                     f"{NEON_RED}Strong SELL signal detected! Score: {signal_score:.2f}{RESET}"
     |                                                                                         ^^^^^^
3610 |                 )
3611 |                 position_manager.open_position("SELL", current_price, atr_value)
     |

E501 Line too long (101 > 88)
    --> whalebot1.0.1.py:3614:89
     |
3612 |             else:
3613 |                 logger.info(
3614 |                     f"{NEON_BLUE}No strong trading signal. Holding. Score: {signal_score:.2f}{RESET}"
     |                                                                                         ^^^^^^^^^^^^^
3615 |                 )
     |

E501 Line too long (161 > 88)
    --> whalebot1.0.1.py:3622:89
     |
3620 | …
3621 | …
3622 | …rice'].normalize()} (SL: {pos['stop_loss'].normalize()}, TP: {pos['take_profit'].normalize()}){RESET}"
     |                               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3623 | …
3624 | …
     |

E501 Line too long (216 > 88)
    --> whalebot1.0.1.py:3629:89
     |
3627 | …
3628 | …
3629 | …_pnl'].normalize():.2f}, Wins: {perf_summary['wins']}, Losses: {perf_summary['losses']}, Win Rate: {perf_summary['win_rate']}{RESET}"
     |       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
3630 | …
     |

E501 Line too long (102 > 88)
    --> whalebot1.0.1.py:3633:89
     |
3632 |             logger.info(
3633 |                 f"{NEON_PURPLE}--- Analysis Loop Finished. Waiting {config['loop_delay']}s ---{RESET}"
     |                                                                                         ^^^^^^^^^^^^^^
3634 |             )
3635 |             time.sleep(config["loop_delay"])
     |

E501 Line too long (90 > 88)
    --> whalebot1.0.1.py:3639:89
     |
3637 |         except Exception as e:
3638 |             alert_system.send_alert(
3639 |                 f"[{config['symbol']}] An unhandled error occurred in the main loop: {e}",
     |                                                                                         ^^
3640 |                 "ERROR",
3641 |             )
     |

Found 175 errors.
