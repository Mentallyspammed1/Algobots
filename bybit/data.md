
             ✨-- MMXCEL v5.1 Ultra Enhanced - Neon Market Maker --✨
2025-08-09 03:44:25.289 - MMXCEL - INFO - 🚀 Initializing ultra-enhanced trading bot...
2025-08-09 03:44:25.290 - MMXCEL - INFO - ✨ Neon colors enabled
────────────────────────────────────────────────────────────────────────────────
2025-08-09 03:44:25.291 - MMXCEL - INFO - Plugin system disabled or folder not found.
2025-08-09 03:44:25.292 - MMXCEL - INFO - Bot state transition: INITIALIZING -> 🔐 TESTING_CREDENTIALS
2025-08-09 03:44:33.826 - MMXCEL - WARNING - Slow API call detected: get_wallet_balance [duration=8.533s]
2025-08-09 03:44:33.827 - MMXCEL - INFO - ✅ API credentials validated successfully
2025-08-09 03:44:33.828 - MMXCEL - INFO - Bot state transition: 🔐 TESTING_CREDENTIALS -> 📊 LOADING_SYMBOL_INFO
2025-08-09 03:44:34.194 - MMXCEL - INFO - 📊 Symbol info loaded successfully [symbol=XLMUSDT]
2025-08-09 03:44:34.195 - MMXCEL - INFO - Bot state transition: 📊 LOADING_SYMBOL_INFO -> 📡 CONNECTING_WEBSOCKETS
2025-08-09 03:44:34.195 - MMXCEL - INFO - Waiting for WebSocket connections to establish...
2025-08-09 03:44:37.680 - MMXCEL - INFO - 🟢 Public WebSocket connected.
2025-08-09 03:44:39.778 - MMXCEL - ERROR - Failed to subscribe to public topics: WebSocket.orderbook_stream() missing 1 required positional argument: 'callback'
2025-08-09 03:44:39.780 - MMXCEL - INFO - Subscribed to private streams
--- RAW PUBLIC WS MESSAGE ---
'{"success":true,"ret_msg":"pong","conn_id":"9d1fcfb9-3519-4666-938b-1312cbfb73df","req_id":"","op":"ping"}'
--- END RAW PUBLIC WS MESSAGE ---
2025-08-09 03:44:58.099 - MMXCEL - CRITICAL - Critical error in public WS handler: 'str' object has no attribute 'get' [exc_info=True]
2025-08-09 03:45:04.367 - MMXCEL - CRITICAL - ⏰ WebSocket connection timeout. Exiting.
2025-08-09 03:45:04.369 - MMXCEL - INFO - Bot state transition: 📡 CONNECTING_WEBSOCKETS -> 🛑 SHUTTING_DOWN
2025-08-09 03:45:04.370 - MMXCEL - INFO - Cleaning up resources...
2025-08-09 03:45:04.847 - MMXCEL - WARNING - 🔴 Public WebSocket disconnected.
2025-08-09 03:45:04.853 - MMXCEL - INFO - Public WebSocket closed.
2025-08-09 03:45:05.270 - MMXCEL - INFO - Private WebSocket closed.
2025-08-09 03:45:05.270 - MMXCEL - INFO - MMXCEL has shut down gracefully.
2025-08-09 03:45:05.271 - MMXCEL - WARNING - 🔴 Private WebSocket disconnected.
2025-08-09 03:45:05.273 - MMXCEL - INFO - Attempting to reconnect public WS in 1s [attempt=1]
2025-08-09 03:45:05.284 - MMXCEL - INFO - Attempting to reconnect private WS in 1s [attempt=1]
Task was destroyed but it is pending!
task: <Task pending name='Task-4' coro=<EnhancedBybitClient.reconnect_ws() done, defined at /data/data/com.termux/files/home/bybit/mmx.py:1414> wait_for=<Future pending cb=[Task.task_wakeup()]> cb=[_chain_future.<locals>._call_set_state() at /data/data/com.termux/files/usr/lib/python3.12/asyncio/futures.py:396]>
Task was destroyed but it is pending!
task: <Task pending name='Task-6' coro=<EnhancedBybitClient.reconnect_ws() done, defined at /data/data/com.termux/files/home/bybit/mmx.py:1414> wait_for=<Future pending cb=[Task.task_wakeup()]> cb=[_chain_future.<locals>._call_set_state() at /data/data/com.termux/files/usr/lib/python3.12/asyncio/futures.py:396]>

u0_a334 in ~/bybit took 41.7s …
