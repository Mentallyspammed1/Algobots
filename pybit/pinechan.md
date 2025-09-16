//@version=5
strategy("Neon Chandelier Scalper Pro 🚀", overlay=true, pyramiding=0, default_qty_type=strategy.percent_of_equity, default_qty_value=10, initial_capital=1000, currency=currency.USDT, process_orders_on_close=true, max_bars_back=5000, commission_value=0.075, commission_type=strategy.commission.percent)

// --- Strategy & UI Parameters ---
// User-friendly inputs for customization, grouped for better organization.
atr_period = input.int(14, title="ATR Period", minval=1, group="Core Strategy")
chandelier_multiplier = input.float(3.0, title="Chandelier Multiplier", minval=0.1, step=0.1, group="Core Strategy")
risk_reward_ratio = input.float(1.5, title="Take Profit / Stop Loss Ratio", minval=0.1, step=0.1, group="Core Strategy")

// --- Enhanced Risk Management ---
use_trailing_stop = input.bool(true, title="Use Trailing Stop", group="Risk Management")
use_break_even = input.bool(true, title="Use Break-Even Stop", group="Risk Management")
break_even_level = input.float(1.0, title="Break-Even at R:R", minval=0.5, step=0.1, group="Risk Management")
max_intraday_loss = input.float(5.0, title="Max Intraday Loss %", minval=0.1, maxval=50.0, step=0.1, group="Risk Management")

// --- Filters & Confirmation ---
// Additional indicators to filter out false signals.
trend_ema_period = input.int(50, title="Trend EMA Period", minval=1, group="Filters & Confirmation")
short_ema_period = input.int(12, title="Short EMA Period", minval=1, group="Filters & Confirmation")
long_ema_period = input.int(26, title="Long EMA Period", minval=1, group="Filters & Confirmation")
rsi_period = input.int(14, title="RSI Period", minval=1, group="Filters & Confirmation")
rsi_overbought = input.int(70, title="RSI Overbought", minval=50, maxval=100, group="Filters & Confirmation")
rsi_oversold = input.int(30, title="RSI Oversold", minval=0, maxval=50, group="Filters & Confirmation")
volume_ma_period = input.int(20, title="Volume MA Period", minval=1, group="Filters & Confirmation")
volume_spike_threshold = input.float(1.5, title="Volume Spike Threshold", minval=1.0, step=0.1, group="Filters & Confirmation")
use_macd_filter = input.bool(true, title="Use MACD Filter", group="Filters & Confirmation")
use_adx_filter = input.bool(true, title="Use ADX Filter", group="Filters & Confirmation")
adx_threshold = input.int(20, title="ADX Threshold", minval=10, maxval=50, group="Filters & Confirmation")

// --- Time & Session Filters ---
use_session_filter = input.bool(true, title="Use Session Filter", group="Time Filters")
start_hour = input.int(9, title="Start Hour", minval=0, maxval=23, group="Time Filters")
end_hour = input.int(16, title="End Hour", minval=0, maxval=23, group="Time Filters")
use_high_impact_time_filter = input.bool(false, title="Filter High-Impact News", group="Time Filters")

// --- Advanced Indicator Settings ---
use_heikin_ashi = input.bool(false, title="Use Heikin Ashi Candles", group="Advanced Settings")
use_vwap = input.bool(true, title="Use VWAP Filter", group="Advanced Settings")
vwap_band_multiplier = input.float(1.5, title="VWAP Band Multiplier", minval=0.5, step=0.1, group="Advanced Settings")

// --- Alert Settings ---
enable_alerts = input.bool(true, title="Enable Alerts", group="Alert Settings")

// --- Indicator Calculations ---
// Heikin Ashi conversion for smoother trends
ha_close = (open + high + low + close) / 4
ha_open = na(ha_open[1]) ? (open + close) / 2 : (ha_open[1] + ha_close[1]) / 2
ha_high = math.max(high, math.max(ha_open, ha_close))
ha_low = math.min(low, math.min(ha_open, ha_close))

// Use Heikin Ashi or regular prices based on setting
price_close = use_heikin_ashi ? ha_close : close
price_open = use_heikin_ashi ? ha_open : open
price_high = use_heikin_ashi ? ha_high : high
price_low = use_heikin_ashi ? ha_low : low

// ATR calculation
atr_val = ta.atr(atr_period)

// Chandelier Exit with dynamic calculation
chandelier_long = ta.highest(price_high, atr_period) - (atr_val * chandelier_multiplier)
chandelier_short = ta.lowest(price_low, atr_period) + (atr_val * chandelier_multiplier)

// EMAs
trend_ema = ta.ema(price_close, trend_ema_period)
ema_short = ta.ema(price_close, short_ema_period)
ema_long = ta.ema(price_close, long_ema_period)

// RSI and Volume SMA
rsi = ta.rsi(price_close, rsi_period)
volume_sma = ta.sma(volume, volume_ma_period)

// MACD for additional confirmation
[macd_line, signal_line, _] = ta.macd(price_close, 12, 26, 9)
macd_bullish = macd_line > signal_line
macd_bearish = macd_line < signal_line

// ADX for trend strength
adx = ta.adx(high, low, close, 14)
strong_trend = adx > adx_threshold

// VWAP with bands for dynamic support/resistance
vwap_value = ta.vwap(hlc3)
vwap_upper = vwap_value + (atr_val * vwap_band_multiplier)
vwap_lower = vwap_value - (atr_val * vwap_band_multiplier)

// Session filter
hour_val = hour(time(timeframe.period))
in_session = not use_session_filter or (hour_val >= start_hour and hour_val < end_hour)

// News filter (simple time-based example)
is_high_impact_time = not use_high_impact_time_filter or (hour_val != 13)

// --- Entry & Exit Conditions ---
// Combine multiple indicators for a higher-probability signal.
macd_filter = not use_macd_filter or macd_bullish
adx_filter = not use_adx_filter or strong_trend
vwap_filter = not use_vwap or (price_close > vwap_lower and price_close < vwap_upper)

bool buy_entry_condition = (ema_short > ema_long) and
(price_close > trend_ema) and
(price_close > chandelier_long) and
(rsi < rsi_overbought) and
(volume > volume_sma * volume_spike_threshold) and
macd_filter and
adx_filter and
vwap_filter and
in_session and
is_high_impact_time

bool sell_entry_condition = (ema_short < ema_long) and
(price_close < trend_ema) and
(price_close < chandelier_short) and
(rsi > rsi_oversold) and
(volume > volume_sma * volume_spike_threshold) and
(not use_macd_filter or macd_bearish) and
adx_filter and
vwap_filter and
in_session and
is_high_impact_time

// --- Risk Management ---
// Calculate position size based on risk
risk_amount = strategy.equity * (max_intraday_loss / 100)
risk_per_trade = risk_amount / (atr_val * chandelier_multiplier)
position_size = math.min(risk_per_trade, strategy.equity * 0.1) // Cap at 10% of equity

// Check if daily loss limit reached
var float daily_high_equity = 0.0
daily_high_equity := math.max(daily_high_equity, strategy.equity)
daily_drawdown = ((daily_high_equity - strategy.equity) / daily_high_equity) * 100
max_daily_loss_reached = daily_drawdown >= max_intraday_loss

// Reset daily high equity at the start of each day
if ta.change(time("D"))
daily_high_equity := strategy.equity

// --- Order Placement ---
// The strategy handles entries and exits automatically.
if not max_daily_loss_reached and buy_entry_condition and strategy.position_size == 0
// Calculate SL/TP based on entry candle's ATR
float sl_price_long = chandelier_long
float risk_distance = price_close - sl_price_long
float tp_price_long = price_close + risk_distance * risk_reward_ratio

// Place a long entry and attach a fixed TP/SL.
strategy.entry("Long", strategy.long, qty=position_size, comment="Enter Long")
strategy.exit("Long Exit", from_entry="Long", stop=sl_price_long, limit=tp_price_long, comment="Exit Long (TP/SL)")

// Send a real-time alert for automation.
if enable_alerts
alert("LONG ENTRY SIGNAL on " + syminfo.ticker + "! Price: " + str.tostring(price_close) +
", SL: " + str.tostring(sl_price_long) + ", TP: " + str.tostring(tp_price_long),
alert.freq_once_per_bar_close)

if not max_daily_loss_reached and sell_entry_condition and strategy.position_size == 0
// Calculate SL/TP based on entry candle's ATR
float sl_price_short = chandelier_short
float risk_distance = sl_price_short - price_close
float tp_price_short = price_close - risk_distance * risk_reward_ratio

// Place a short entry and attach a fixed TP/SL.
strategy.entry("Short", strategy.short, qty=position_size, comment="Enter Short")
strategy.exit("Short Exit", from_entry="Short", stop=sl_price_short, limit=tp_price_short, comment="Exit Short (TP/SL)")

// Send a real-time alert for automation.
if enable_alerts
alert("SHORT ENTRY SIGNAL on " + syminfo.ticker + "! Price: " + str.tostring(price_close) +
", SL: " + str.tostring(sl_price_short) + ", TP: " + str.tostring(tp_price_short),
alert.freq_once_per_bar_close)

// --- Enhanced Exit Logic ---
// Break-even stop logic
var float long_entry_price = 0.0
var float short_entry_price = 0.0

if strategy.position_size > 0
if long_entry_price == 0.0
long_entry_price := close
// Move stop to break-even when profit reaches target
if use_break_even and close >= long_entry_price + (long_entry_price - chandelier_long) * break_even_level
strategy.exit("Long BreakEven", from_entry="Long", stop=long_entry_price, comment="Break-Even Exit")
else
long_entry_price := 0.0

if strategy.position_size < 0
if short_entry_price == 0.0
short_entry_price := close
// Move stop to break-even when profit reaches target
if use_break_even and close <= short_entry_price - (chandelier_short - short_entry_price) * break_even_level
strategy.exit("Short BreakEven", from_entry="Short", stop=short_entry_price, comment="Break-Even Exit")
else
short_entry_price := 0.0

// Trailing Stop Logic
if use_trailing_stop and strategy.position_size > 0 and close < chandelier_long
strategy.close("Long", comment="Chandelier Exit Long")
if enable_alerts
alert("LONG POSITION CLOSED via Chandelier Trailing Stop on " + syminfo.ticker, alert.freq_once_per_bar_close)

if use_trailing_stop and strategy.position_size < 0 and close > chandelier_short
strategy.close("Short", comment="Chandelier Exit Short")
if enable_alerts
alert("SHORT POSITION CLOSED via Chandelier Trailing Stop on " + syminfo.ticker, alert.freq_once_per_bar_close)

// Force close all positions if daily loss limit reached
if max_daily_loss_reached and strategy.position_size != 0
strategy.close_all("Daily Loss Limit Reached")
if enable_alerts
alert("ALL POSITIONS CLOSED - Daily loss limit reached on " + syminfo.ticker, alert.freq_once_per_bar_close)

// --- Visual & UI Enhancements (Neon Theme) ---
// Plotting the Chandelier Exit lines and EMAs with a neon color palette.
plot(chandelier_long, "Chandelier Long", color=color.new(color.lime, 0), linewidth=2, style=plot.style_stepline)
plot(chandelier_short, "Chandelier Short", color=color.new(color.fuchsia, 0), linewidth=2, style=plot.style_stepline)

// EMAs with a semi-transparent look.
plot(trend_ema, "Trend EMA", color=color.new(color.white, 25), linewidth=1)
plot(ema_short, "Short EMA", color=color.new(color.aqua, 0), linewidth=2)
plot(ema_long, "Long EMA", color=color.new(color.orange, 0), linewidth=2)

// VWAP bands
plot(use_vwap ? vwap_value : na, "VWAP", color=color.new(color.purple, 0), linewidth=1)
plot(use_vwap ? vwap_upper : na, "VWAP Upper", color=color.new(color.purple, 70), linewidth=1)
plot(use_vwap ? vwap_lower : na, "VWAP Lower", color=color.new(color.purple, 70), linewidth=1)

// Plotting signals on the chart.
plotshape(buy_entry_condition and not max_daily_loss_reached, style=shape.triangleup, location=location.belowbar, color=color.new(color.lime, 0), size=size.small, title="Buy Signal")
plotshape(sell_entry_condition and not max_daily_loss_reached, style=shape.triangledown, location=location.abovebar, color=color.new(color.fuchsia, 0), size=size.small, title="Sell Signal")

// Background color to highlight the trend.
bgcolor(close > trend_ema ? color.new(color.green, 90) : color.new(color.red, 90))

// Session highlights
bgcolor(use_session_filter and not in_session ? color.new(color.gray, 80) : na, title="Off-Session Highlight")

// High-impact time highlights
bgcolor(use_high_impact_time_filter and not is_high_impact_time ? color.new(color.orange, 80) : na, title="High-Impact Time Highlight")

// Daily loss limit warning
bgcolor(max_daily_loss_reached ? color.new(color.red, 90) : na, title="Daily Loss Limit Reached")

// Display performance statistics as a detailed table on the chart.
var table performance_table = table.new(position.top_right, 2, 7, border_width=1, frame_color=color.new(color.gray, 50), frame_width=1)
if barstate.islast
// Header
table.cell(performance_table, 0, 0, "Performance Metric", text_color=color.white, bgcolor=color.new(color.gray, 70))
table.cell(performance_table, 1, 0, "Value", text_color=color.white, bgcolor=color.new(color.gray, 70))

// Rows
table.cell(performance_table, 0, 1, "Total Net Profit")
table.cell(performance_table, 1, 1, str.tostring(strategy.netprofit, format.percent),
text_color=strategy.netprofit > 0 ? color.lime : color.fuchsia)

table.cell(performance_table, 0, 2, "Win Rate")
win_rate = strategy.wintrades / math.max(1, strategy.wintrades + strategy.losstrades) * 100
table.cell(performance_table, 1, 2, str.tostring(win_rate, "#.##") + "% (" + str.tostring(strategy.wintrades) + "/" + str.tostring(strategy.wintrades + strategy.losstrades) + ")")

table.cell(performance_table, 0, 3, "Profit Factor")
profit_factor = strategy.grossprofit / math.max(1, strategy.grossloss)
table.cell(performance_table, 1, 3, str.tostring(profit_factor, "#.##"))

table.cell(performance_table, 0, 4, "Max Drawdown")
table.cell(performance_table, 1, 4, str.tostring(strategy.max_drawdown, format.percent),
text_color=strategy.max_drawdown < 10 ? color.lime : strategy.max_drawdown < 20 ? color.orange : color.fuchsia)

table.cell(performance_table, 0, 5, "Daily P/L")
table.cell(performance_table, 1, 5, str.tostring(daily_drawdown, "#.##") + "%" + (max_daily_loss_reached ? " (LIMIT!)" : ""),
text_color=daily_drawdown <= 0 ? color.lime : daily_drawdown < max_intraday_loss/2 ? color.orange : color.fuchsia)

table.cell(performance_table, 0, 6, "Open P/L")
table.cell(performance_table, 1, 6, str.tostring(strategy.openprofit, format.percent),
text_color=strategy.openprofit > 0 ? color.lime : strategy.openprofit < 0 ? color.fuchsia : color.white)