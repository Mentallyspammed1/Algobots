eractive shell
Type help for instructions on how to use fish
u0_a439@localhost ~/A/whalebot (main)> node ait.js
/data/data/com.termux/files/home/Algobots/whalebot/ait.js:244
    tradeBuffer.filter(t => t.ts >= s && t.ts < e).forEach(t => (t.side === 'buy' ? b : se) += t.size);
                                                                ^^^^^^^^^^^^^^^^^^^^^^^^^^^

SyntaxError: Invalid left-hand side in assignment
    at wrapSafe (node:internal/modules/cjs/loader:1691:18)
    at Module._compile (node:internal/modules/cjs/loader:1734:20)
    at Module._extensions..js (node:internal/modules/cjs/loader:1893:10)
    at Module.load (node:internal/modules/cjs/loader:1480:32)
    at Module._load (node:internal/modules/cjs/loader:1299:12)
    at TracingChannel.traceSync (node:diagnostics_channel:328:14)
    at wrapModuleLoad (node:internal/modules/cjs/loader:244:24)
    at Module.executeUserEntryPoint [as runMain] (node:internal/modules/run_main:154:5)
    at node:internal/main/run_main_module:33:47

Node.js v24.9.0
u0_a439@localhost ~/A/whalebot (main) [1]> node aitrend.js

--- Definitive Gemini Scalping Engine ---
Symbol (e.g. BTCUSDT): BCHUSDT
Timeframes (comma-separated, e.g., 1,5,15): 1
FATAL ERROR: TypeError: C.red is not a function
    at main (/data/data/com.termux/files/home/Algobots/whalebot/aitrend.js:890:40)
    at process.processTicksAndRejections (node:internal/process/task_queues:105:5)
