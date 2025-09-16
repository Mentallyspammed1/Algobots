<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pyrmethus's Neon Bybit Bot Grimoire</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700&display=swap');
        body {
            font-family: 'Inter', sans-serif;
            background-color: #020617; /* slate-950 */
            color: #E2E8F0; /* slate-200 */
        }
        .neon-border {
            border: 2px solid;
            border-image-slice: 1;
            border-image-source: linear-gradient(to right, #a855f7, #ec4899, #6ee7b7);
            border-radius: 12px;
        }
        .neon-text-glow {
            text-shadow: 0 0 5px #ec4899, 0 0 10px #ec4899, 0 0 15px #ec4899;
        }
        .bg-gradient-neon {
            background-image: linear-gradient(to right, #a855f7, #ec4899);
        }
        .scrollable-log {
            overflow-y: auto;
            max-height: 24rem; /* 96 tall */
        }
        .llm-button-glow {
            box-shadow: 0 0 5px #a855f7, 0 0 10px #a855f7, 0 0 15px #a855f7;
        }
        /* Enhanced animations */
        @keyframes pulse-neon {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }
        .pulse-neon {
            animation: pulse-neon 2s ease-in-out infinite;
        }
        .transition-all {
            transition: all 0.3s ease;
        }
        /* Loading spinner */
        .spinner {
            border: 2px solid rgba(255, 255, 255, 0.1);
            border-left-color: #ec4899;
            border-radius: 50%;
            width: 20px;
            height: 20px;
            animation: spin 1s linear infinite;
            display: inline-block;
            margin-left: 8px;
            vertical-align: middle;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        /* Enhanced log styling */
        .log-entry {
            padding: 2px 0;
            border-left: 2px solid transparent;
            padding-left: 8px;
            margin: 2px 0;
            transition: all 0.2s ease;
        }
        .log-entry:hover {
            background-color: rgba(255, 255, 255, 0.05);
            border-left-color: #ec4899;
        }
        .log-entry.error { border-left-color: #F87171; } /* Red */
        .log-entry.success { border-left-color: #86EFAC; } /* Green */
        .log-entry.info { border-left-color: #67E8F9; } /* Cyan */
        .log-entry.warning { border-left-color: #FACC15; } /* Yellow */
        .log-entry.signal { border-left-color: #EC4899; } /* Pink */
        .log-entry.llm { border-left-color: #A855F7; } /* Purple */
    </style>
</head>
<body class="bg-slate-950 text-slate-200 p-4 md:p-8">

    <div class="max-w-4xl mx-auto space-y-8">
        <!-- Main Title and Subtitle -->
        <header class="text-center space-y-2 mb-8">
            <h1 class="text-4xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-500 via-pink-500 to-green-300 neon-text-glow pulse-neon">
                Pyrmethus's Neon Grimoire
            </h1>
            <p class="text-lg text-slate-400">Transcribing the Supertrend incantation to the digital ether.</p>
        </header>

        <!-- Configuration Section -->
        <div class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 transition-all hover:border-purple-600">
            <h2 class="text-2xl font-bold mb-4 text-purple-400">Configuration</h2>
            <p class="text-sm text-slate-500 mb-4">
                <strong class="text-red-400">WARNING:</strong> This is for educational/testnet use only. API keys are stored client-side and are not secure.
                For real trading, a secure backend is essential.
            </p>
            <div class="grid md:grid-cols-2 gap-4">
                <div>
                    <label for="apiKey" class="block text-sm font-medium mb-1 text-slate-300">API Key</label>
                    <input type="text" id="apiKey" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all" placeholder="Enter your API Key">
                </div>
                <div>
                    <label for="apiSecret" class="block text-sm font-medium mb-1 text-slate-300">API Secret</label>
                    <input type="password" id="apiSecret" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all" placeholder="Enter your API Secret">
                </div>
                <div>
                    <label for="symbol" class="block text-sm font-medium mb-1 text-slate-300">Trading Symbol</label>
                    <select id="symbol" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                        <option value="BTCUSDT" selected>BTCUSDT</option>
                        <option value="ETHUSDT">ETHUSDT</option>
                        <option value="SOLUSDT">SOLUSDT</option>
                        <option value="BNBUSDT">BNBUSDT</option>
                        <option value="XRPUSDT">XRPUSDT</option>
                    </select>
                </div>
                <div>
                    <label for="interval" class="block text-sm font-medium mb-1 text-slate-300">Interval (in min)</label>
                    <select id="interval" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                        <option value="1">1 min</option>
                        <option value="5">5 min</option>
                        <option value="15">15 min</option>
                        <option value="30">30 min</option>
                        <option value="60" selected>1 hour</option>
                        <option value="240">4 hours</option>
                        <option value="D">1 day</option>
                    </select>
                </div>
                <div>
                    <label for="leverage" class="block text-sm font-medium mb-1 text-slate-300">Leverage</label>
                    <input type="number" id="leverage" value="10" min="1" max="100" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                </div>
                <div>
                    <label for="riskPct" class="block text-sm font-medium mb-1 text-slate-300">Risk % per Trade</label>
                    <input type="number" id="riskPct" value="1" step="0.1" min="0.1" max="10" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                </div>
                <div>
                    <label for="stopLossPct" class="block text-sm font-medium mb-1 text-slate-300">Stop Loss % (from Entry)</label>
                    <input type="number" id="stopLossPct" value="2" step="0.1" min="0.1" max="10" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                </div>
                <div>
                    <label for="takeProfitPct" class="block text-sm font-medium mb-1 text-slate-300">Take Profit % (from Entry)</label>
                    <input type="number" id="takeProfitPct" value="5" step="0.1" min="0.1" max="20" class="w-full p-2 rounded bg-slate-700 text-slate-200 border border-slate-600 focus:outline-none focus:ring-2 focus:ring-purple-500 transition-all">
                </div>
            </div>
            <button id="startBot" class="mt-6 w-full py-3 rounded-lg bg-gradient-neon text-white font-bold transition-transform transform hover:scale-105 shadow-md shadow-pink-500/50" aria-live="polite">
                <span id="buttonText">Start the Bot</span>
            </button>
        </div>

        <!-- Dashboard Section -->
        <div class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 transition-all hover:border-green-600">
            <h2 class="text-2xl font-bold mb-4 text-green-400">Live Dashboard</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-cyan-500">
                    <p class="text-sm text-slate-400">Current Price</p>
                    <p id="currentPrice" class="text-xl font-bold text-cyan-400 mt-1">---</p>
                    <p id="priceChange" class="text-xs text-slate-500 mt-1">---</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-fuchsia-500">
                    <p class="text-sm text-slate-400">Supertrend Direction</p>
                    <p id="stDirection" class="text-xl font-bold text-fuchsia-400 mt-1">---</p>
                    <p id="stValue" class="text-xs text-slate-500 mt-1">---</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-yellow-500">
                    <p class="text-sm text-slate-400">RSI Value</p>
                    <p id="rsiValue" class="text-xl font-bold text-yellow-400 mt-1">---</p>
                    <p id="rsiStatus" class="text-xs text-slate-500 mt-1">---</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-pink-500">
                    <p class="text-sm text-slate-400">Current Position</p>
                    <p id="currentPosition" class="text-xl font-bold text-pink-400 mt-1">None</p>
                    <p id="positionPnL" class="text-xs text-slate-500 mt-1">---</p>
                </div>
            </div>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center mt-4">
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-blue-500">
                    <p class="text-sm text-slate-400">Account Balance</p>
                    <p id="accountBalance" class="text-xl font-bold text-blue-400 mt-1">---</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-emerald-500">
                    <p class="text-sm text-slate-400">Total Trades</p>
                    <p id="totalTrades" class="text-xl font-bold text-emerald-400 mt-1">0</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-orange-500">
                    <p class="text-sm text-slate-400">Win Rate</p>
                    <p id="winRate" class="text-xl font-bold text-orange-400 mt-1">0%</p>
                </div>
                <div class="bg-slate-900 p-4 rounded-lg border-2 border-slate-600 transition-all hover:border-violet-500">
                    <p class="text-sm text-slate-400">Bot Status</p>
                    <p id="botStatus" class="text-xl font-bold text-violet-400 mt-1">Idle</p>
                </div>
            </div>
            <div class="mt-6 flex gap-4">
                <button id="askGemini" class="flex-1 py-3 rounded-lg bg-slate-700 text-purple-300 font-bold transition-transform transform hover:scale-105 llm-button-glow" aria-live="polite">
                    ✨ Ask Gemini for Market Insight
                </button>
                <button id="exportLogs" class="flex-1 py-3 rounded-lg bg-slate-700 text-blue-300 font-bold transition-transform transform hover:scale-105 hover:shadow-lg hover:shadow-blue-500/50">
                    📊 Export Trading Logs
                </button>
            </div>
        </div>
        
        <!-- Log Section -->
        <div class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 transition-all hover:border-blue-600">
            <div class="flex justify-between items-center mb-4">
                <h2 class="text-2xl font-bold text-blue-400">Ritual Log</h2>
                <button id="clearLogs" class="px-4 py-2 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 transition-all text-sm">
                    Clear Logs
                </button>
            </div>
            <div id="logArea" class="bg-slate-900 p-4 rounded-lg scrollable-log text-xs text-slate-300 font-mono" aria-live="polite">
                <div class="log-entry info">Awaiting your command, Master Pyrmethus...</div>
            </div>
        </div>
    </div>

    <script>
        // --- Core JavaScript Grimoire ---
        // This is for educational use only. DO NOT USE FOR REAL TRADING.
        // API keys are stored client-side and are HIGHLY INSECURE.

        const logArea = document.getElementById('logArea');
        const currentPriceEl = document.getElementById('currentPrice');
        const priceChangeEl = document.getElementById('priceChange');
        const stDirectionEl = document.getElementById('stDirection');
        const stValueEl = document.getElementById('stValue');
        const rsiValueEl = document.getElementById('rsiValue');
        const rsiStatusEl = document.getElementById('rsiStatus');
        const currentPositionEl = document.getElementById('currentPosition');
        const positionPnLEl = document.getElementById('positionPnL');
        const accountBalanceEl = document.getElementById('accountBalance');
        const totalTradesEl = document.getElementById('totalTrades');
        const winRateEl = document.getElementById('winRate');
        const botStatusEl = document.getElementById('botStatus');

        const startBotBtn = document.getElementById('startBot');
        const buttonTextEl = document.getElementById('buttonText');
        const apiKeyInput = document.getElementById('apiKey');
        const apiSecretInput = document.getElementById('apiSecret');
        const symbolInput = document.getElementById('symbol');
        const intervalInput = document.getElementById('interval');
        const leverageInput = document.getElementById('leverage');
        const riskPctInput = document.getElementById('riskPct');
        const stopLossPctInput = document.getElementById('stopLossPct');
        const takeProfitPctInput = document.getElementById('takeProfitPct');

        const askGeminiBtn = document.getElementById('askGemini');
        const clearLogsBtn = document.getElementById('clearLogs');
        const exportLogsBtn = document.getElementById('exportLogs');

        let botRunning = false;
        let lastSupertrendData = { direction: 0, value: 0 }; // Initialize for Supertrend calculation
        let intervalId = null;
        let lastKlineData = null; // Store for Gemini insight
        let previousClosePrice = 0;

        let tradeHistory = []; // In-memory trade history for stats
        let wins = 0;
        let losses = 0;

        const BYBIT_API_URL = 'https://api-testnet.bybit.com';
        const CONFIG = {
            symbol: 'BTCUSDT',
            category: 'linear',
            interval: '60', // '60' for 1 hour, 'D' for 1 day etc.
            supertrend_length: 10,
            supertrend_multiplier: 3.0,
            rsi_length: 14,
            rsi_overbought: 70,
            rsi_oversold: 30,
            riskPct: 1, // 1%
            leverage: 10,
            stopLossPct: 2, // 2% from entry
            takeProfitPct: 5, // 5% from entry
            price_precision: 2, // Default for BTCUSDT, needs dynamic lookup for real use
            qty_precision: 4, // Default for BTCUSDT, needs dynamic lookup for real use
            max_retries: 3,
            retry_delay_base: 1000, // 1 second
        };

        // --- Hashing and Authentication (The API's Key Binding) ---
        async function getSignature(data, secret) {
            const hmac = await crypto.subtle.importKey(
                "raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
            );
            const signature = await crypto.subtle.sign(
                "HMAC", hmac, new TextEncoder().encode(data)
            );
            return Array.from(new Uint8Array(signature)).map(b => b.toString(16).padStart(2, '0')).join('');
        }

        async function createBybitRequest(method, endpoint, params, apiKey, apiSecret, retries = 0) {
            const timestamp = Date.now().toString();
            const recvWindow = '5000';
            let signatureString;
            let requestBody = null;

            if (method === 'GET') {
                const sortedParams = Object.keys(params).sort().map(key => `${key}=${params[key]}`).join('&');
                signatureString = `${timestamp}${apiKey}${recvWindow}${sortedParams}`;
            } else { // POST
                requestBody = JSON.stringify(params);
                signatureString = `${timestamp}${apiKey}${recvWindow}${requestBody}`;
            }
            
            const signature = await getSignature(signatureString, apiSecret);

            const headers = {
                'X-BAPI-API-KEY': apiKey,
                'X-BAPI-TIMESTAMP': timestamp,
                'X-BAPI-SIGN': signature,
                'X-BAPI-RECV-WINDOW': recvWindow,
            };
            if (method === 'POST') {
                headers['Content-Type'] = 'application/json';
            }

            const url = method === 'GET'
                ? `${BYBIT_API_URL}${endpoint}?${Object.keys(params).map(key => `${key}=${params[key]}`).join('&')}`
                : `${BYBIT_API_URL}${endpoint}`;
            
            try {
                const response = await fetch(url, { method, headers, body: requestBody });
                const data = await response.json();

                if (data.retCode !== 0) {
                    if ((data.retCode === 10006 || data.retCode === 10007 || data.retCode === 10001 || response.status === 429) && retries < CONFIG.max_retries) {
                        const delay = CONFIG.retry_delay_base * Math.pow(2, retries);
                        log(`Bybit API Error: ${data.retMsg || response.statusText}. Retrying in ${delay / 1000}s... (Attempt ${retries + 1})`, 'warning');
                        await new Promise(res => setTimeout(res, delay));
                        return createBybitRequest(method, endpoint, params, apiKey, apiSecret, retries + 1);
                    }
                    log(`Bybit API Error (${data.retCode}): ${data.retMsg}`, 'error');
                }
                return data;
            } catch (e) {
                if (retries < CONFIG.max_retries) {
                    const delay = CONFIG.retry_delay_base * Math.pow(2, retries);
                    log(`Network error: ${e.message}. Retrying in ${delay / 1000}s... (Attempt ${retries + 1})`, 'warning');
                    await new Promise(res => setTimeout(res, delay));
                    return createBybitRequest(method, endpoint, params, apiKey, apiSecret, retries + 1);
                }
                log(`Final Network Error: ${e.message}`, 'error');
                return { retCode: 10000, retMsg: `Network Error: ${e.message}` };
            }
        }

        // UI Log function with neon colors
        function log(message, type = 'info') {
            const timestamp = new Date().toISOString().split('T')[1].split('.')[0];
            let color = '#E2E8F0'; // slate-200 (default)
            
            switch (type) {
                case 'success': color = '#86EFAC'; break; // green-300
                case 'info':    color = '#67E8F9'; break; // cyan-300
                case 'warning': color = '#FACC15'; break; // yellow-400
                case 'error':   color = '#F87171'; break; // red-400
                case 'signal':  color = '#EC4899'; break; // pink-400
                case 'llm':     color = '#A855F7'; break; // purple-500
            }

            const logEntryDiv = document.createElement('div');
            logEntryDiv.className = `log-entry ${type}`;
            logEntryDiv.innerHTML = `<span style="color: #64748B;">[${timestamp}]</span> <span style="color: ${color};">${message}</span>`;
            logArea.appendChild(logEntryDiv);
            logArea.scrollTop = logArea.scrollHeight; // Auto-scroll
        }

        function updateBotStatus(status, type = 'info') {
            botStatusEl.innerText = status;
            switch(type) {
                case 'running': botStatusEl.className = 'text-xl font-bold text-green-400 mt-1'; break;
                case 'idle': botStatusEl.className = 'text-xl font-bold text-violet-400 mt-1'; break;
                case 'error': botStatusEl.className = 'text-xl font-bold text-red-400 mt-1'; break;
                case 'waiting': botStatusEl.className = 'text-xl font-bold text-yellow-400 mt-1'; break;
            }
        }

        function updateTradeStats() {
            totalTradesEl.innerText = tradeHistory.length;
            const total = wins + losses;
            winRateEl.innerText = total > 0 ? `${((wins / total) * 100).toFixed(1)}%` : '0%';
            totalTradesEl.className = `text-xl font-bold mt-1 ${wins > losses ? 'text-green-400' : (losses > wins ? 'text-red-400' : 'text-emerald-400')}`;
            winRateEl.className = `text-xl font-bold mt-1 ${parseFloat(winRateEl.innerText) >= 50 ? 'text-green-400' : 'text-red-400'}`;
        }

        // --- API Interaction (The Spell's Channeling) ---
        async function fetchKlineData(symbol, interval, limit = 200) {
            log(`Channelling market data for ${symbol} (${interval})...`, 'info');
            try {
                const url = `${BYBIT_API_URL}/v5/market/kline?category=${CONFIG.category}&symbol=${symbol}&interval=${interval}&limit=${limit}`;
                const response = await fetch(url);
                const data = await response.json();
                if (data.retCode !== 0) {
                    log(`API Error: ${data.retMsg}`, 'error');
                    return null;
                }
                // Bybit returns newest last, we need oldest first for indicator calculation
                return data.result.list.reverse().map(item => ({
                    open: parseFloat(item[1]),
                    high: parseFloat(item[2]),
                    low: parseFloat(item[3]),
                    close: parseFloat(item[4]),
                    volume: parseFloat(item[5]),
                    timestamp: parseInt(item[0]), // candlestick start time
                }));
            } catch (e) {
                log(`Failed to channel data: ${e.message}`, 'error');
                return null;
            }
        }

        async function _getOpenPositions() {
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;
            const params = { category: CONFIG.category, symbol: CONFIG.symbol };
            const response = await createBybitRequest('GET', '/v5/position/list', params, apiKey, apiSecret);
            
            if (response.retCode !== 0) {
                // Ignore empty positions as it's a common state
                if (response.retMsg.includes("empty positions")) {
                    return null;
                }
                log(`Failed to get positions: ${response.retMsg}`, 'error');
                return null;
            }
            const positions = response.result.list.filter(p => parseFloat(p.size) > 0);
            return positions.length > 0 ? positions[0] : null;
        }

        async function _closePosition(position, currentPrice) {
            log(`Closing existing ${position.side} position of size ${parseFloat(position.size).toFixed(CONFIG.qty_precision)}...`, 'warning');
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;
            const params = {
                category: CONFIG.category,
                symbol: CONFIG.symbol,
                side: position.side === 'Buy' ? 'Sell' : 'Buy', // Opposite side to close
                orderType: 'Market',
                qty: position.size,
                reduceOnly: true
            };
            const response = await createBybitRequest('POST', '/v5/order/create', params, apiKey, apiSecret);
            if (response.retCode !== 0) {
                log(`Failed to close position: ${response.retMsg}`, 'error');
                return false;
            }
            
            const pnl = (position.side === 'Buy' ? (currentPrice - parseFloat(position.entryPrice)) : (parseFloat(position.entryPrice) - currentPrice)) * parseFloat(position.size);
            
            log(`Position closed successfully. PnL: ${pnl.toFixed(2)} USDT`, pnl >= 0 ? 'success' : 'error');
            tradeHistory.push({
                symbol: CONFIG.symbol,
                side: position.side,
                entryPrice: parseFloat(position.entryPrice),
                exitPrice: currentPrice,
                qty: parseFloat(position.size),
                pnl: pnl,
                date: new Date().toISOString()
            });
            if (pnl >= 0) {
                wins++;
            } else {
                losses++;
            }
            updateTradeStats();
            return true;
        }

        async function _placeOrder(side, currentPrice, balance) {
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;
            
            const stopLossPct = CONFIG.stopLossPct / 100;
            const takeProfitPct = CONFIG.takeProfitPct / 100;
            const riskAmount = balance * (CONFIG.riskPct / 100);

            // Calculate stop loss price
            const slPrice = side === 'Buy' ? currentPrice * (1 - stopLossPct) : currentPrice * (1 + stopLossPct);
            const stopDistance = Math.abs(currentPrice - slPrice);
            
            if (stopDistance === 0 || isNaN(stopDistance) || riskAmount === 0 || isNaN(riskAmount)) {
                log('Calculated stop loss distance or risk amount is invalid. Cannot place order.', 'error');
                return false;
            }

            // Calculate quantity based on risk amount
            // Formula: Quantity = (Risk Amount / Stop Loss Distance) * Leverage
            // On Bybit, `qty` is the number of contracts. If inverse, it's BTC. If USDT perp, it's USDT value.
            // For USDT perp, qty = (Risk Amount / Stop Loss Distance) * Leverage / CurrentPrice * CurrentPrice (Simplified to: Risk Amount / Stop Loss Distance * Leverage)
            // No, it's simpler: contract value = qty * price. So for USDT perp, qty = USDT_value_of_position / currentPrice
            // We're risking `riskAmount` and have a stop loss `stopLossPct`.
            // So, margin for position = RiskAmount / stopLossPct.
            // Position value = margin * leverage = (RiskAmount / stopLossPct) * leverage.
            // Qty = Position value / CurrentPrice = (RiskAmount / stopLossPct * leverage) / CurrentPrice
            const qty = (riskAmount / stopLossPct) / currentPrice;

            // Calculate take profit price
            const tpPrice = side === 'Buy' ? currentPrice * (1 + takeProfitPct) : currentPrice * (1 - takeProfitPct);
            
            // Format prices and quantity to correct precision
            // These precisions are hardcoded for BTCUSDT. For dynamic symbol, need to fetch exchange info.
            const formattedQty = qty.toFixed(CONFIG.qty_precision);
            const formattedSl = slPrice.toFixed(CONFIG.price_precision);
            const formattedTp = tpPrice.toFixed(CONFIG.price_precision);

            log(`Placing a ${side} order for ${formattedQty} contracts. SL: ${formattedSl}, TP: ${formattedTp}`, 'signal');

            const params = {
                category: CONFIG.category,
                symbol: CONFIG.symbol,
                side: side,
                orderType: 'Market',
                qty: formattedQty,
                takeProfit: formattedTp,
                stopLoss: formattedSl,
                tpslMode: 'Full', // Ensures TP/SL are tied to the position
            };
            
            const response = await createBybitRequest('POST', '/v5/order/create', params, apiKey, apiSecret);
            if (response.retCode !== 0) {
                log(`Order failed: ${response.retMsg}`, 'error');
                return false;
            }
            log(`Order placed successfully! ID: ${response.result.orderId}`, 'success');
            return true;
        }

        async function _getAccountBalance() {
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;
            const params = { accountType: 'UNIFIED', coin: 'USDT' };
            const response = await createBybitRequest('GET', '/v5/account/wallet-balance', params, apiKey, apiSecret);
            if (response.retCode !== 0) {
                return null; // Error already logged by createBybitRequest
            }
            if (!response.result || !response.result.list || response.result.list.length === 0) {
                 log('Could not find wallet balance in API response.', 'error');
                 return null;
            }
            return parseFloat(response.result.list[0].totalWalletBalance);
        }

        async function _setLeverage(symbol, leverage) {
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;
            const params = {
                category: CONFIG.category,
                symbol: symbol,
                buyLeverage: leverage.toString(),
                sellLeverage: leverage.toString(),
            };
            const response = await createBybitRequest('POST', '/v5/position/set-leverage', params, apiKey, apiSecret);
            if (response.retCode === 0) {
                log(`Leverage set to ${leverage}x for ${symbol}.`, 'success');
                return true;
            } else {
                log(`Failed to set leverage: ${response.retMsg}`, 'error');
                return false;
            }
        }

        // --- Indicator Calculation (The Core Rune) ---
        function calculateIndicators(klines) {
            if (!klines || klines.length < Math.max(CONFIG.supertrend_length, CONFIG.rsi_length) + 1) {
                return null;
            }
            
            // Supertrend Calculation (More robust than original simple version)
            const atrPeriod = CONFIG.supertrend_length;
            const multiplier = CONFIG.supertrend_multiplier;
            const supertrendData = [];
            const atrValues = [];

            for (let i = 0; i < klines.length; i++) {
                const kline = klines[i];
                let tr = 0;
                if (i === 0) {
                    tr = kline.high - kline.low;
                } else {
                    const prevClose = klines[i-1].close;
                    tr = Math.max(
                        kline.high - kline.low,
                        Math.abs(kline.high - prevClose),
                        Math.abs(kline.low - prevClose)
                    );
                }
                atrValues.push(tr);

                let currentATR = 0;
                if (i < atrPeriod) {
                    currentATR = atrValues.slice(0, i + 1).reduce((sum, val) => sum + val, 0) / (i + 1);
                } else {
                    currentATR = atrValues.slice(i - atrPeriod + 1, i + 1).reduce((sum, val) => sum + val, 0) / atrPeriod;
                }

                const basicUpperBand = (kline.high + kline.low) / 2 + multiplier * currentATR;
                const basicLowerBand = (kline.high + kline.low) / 2 - multiplier * currentATR;

                let finalUpperBand = basicUpperBand;
                let finalLowerBand = basicLowerBand;
                let supertrend = 0;
                let direction = 0; // 1 for uptrend, -1 for downtrend

                if (i > 0) {
                    const prevSTData = supertrendData[i - 1];
                    // Adjust final bands
                    if (basicUpperBand < prevSTData.finalUpperBand || klines[i-1].close > prevSTData.finalUpperBand) {
                        finalUpperBand = basicUpperBand;
                    } else {
                        finalUpperBand = prevSTData.finalUpperBand;
                    }
                    if (basicLowerBand > prevSTData.finalLowerBand || klines[i-1].close < prevSTData.finalLowerBand) {
                        finalLowerBand = basicLowerBand;
                    } else {
                        finalLowerBand = prevSTData.finalLowerBand;
                    }

                    // Determine Supertrend value and direction
                    if (prevSTData.direction === 1) { // Previous was uptrend
                        if (kline.close <= finalUpperBand) { // Close dropped below upper band
                            direction = -1; // New downtrend
                            supertrend = finalUpperBand;
                        } else {
                            direction = 1; // Continues uptrend
                            supertrend = finalLowerBand;
                        }
                    } else if (prevSTData.direction === -1) { // Previous was downtrend
                        if (kline.close >= finalLowerBand) { // Close rose above lower band
                            direction = 1; // New uptrend
                            supertrend = finalLowerBand;
                        } else {
                            direction = -1; // Continues downtrend
                            supertrend = finalUpperBand;
                        }
                    } else { // First bar or no clear direction yet
                        if (kline.close > finalUpperBand) {
                            direction = 1;
                            supertrend = finalLowerBand;
                        } else if (kline.close < finalLowerBand) {
                            direction = -1;
                            supertrend = finalUpperBand;
                        } else {
                            // If close is between bands, maintain previous direction or default
                            direction = prevSTData.direction === 0 ? 1 : prevSTData.direction;
                            supertrend = direction === 1 ? finalLowerBand : finalUpperBand;
                        }
                    }
                } else { // For the very first bar, default to uptrend
                    direction = 1;
                    supertrend = finalLowerBand;
                }

                supertrendData.push({
                    finalUpperBand,
                    finalLowerBand,
                    supertrend,
                    direction
                });
            }

            const finalSupertrend = supertrendData[supertrendData.length - 1];

            // RSI Calculation (Wilder's Smoothing)
            const rsiPeriod = CONFIG.rsi_length;
            let avgGain = 0;
            let avgLoss = 0;
            const rsiValues = [];

            // Calculate initial average gain/loss over the first 'rsiPeriod' bars
            let initialGains = 0;
            let initialLosses = 0;
            for (let i = 1; i <= rsiPeriod; i++) {
                const change = klines[i].close - klines[i-1].close;
                if (change > 0) initialGains += change;
                else initialLosses += Math.abs(change);
            }
            avgGain = initialGains / rsiPeriod;
            avgLoss = initialLosses / rsiPeriod;

            let currentRSI = 0;
            if (avgLoss === 0) {
                currentRSI = 100;
            } else {
                const rs = avgGain / avgLoss;
                currentRSI = 100 - (100 / (1 + rs));
            }
            rsiValues.push(currentRSI);

            // Calculate subsequent RSI values using Wilder's smoothing
            for (let i = rsiPeriod + 1; i < klines.length; i++) {
                const change = klines[i].close - klines[i-1].close;
                const gain = Math.max(0, change);
                const loss = Math.max(0, -change);

                avgGain = (avgGain * (rsiPeriod - 1) + gain) / rsiPeriod;
                avgLoss = (avgLoss * (rsiPeriod - 1) + loss) / rsiPeriod;

                if (avgLoss === 0) {
                    currentRSI = 100;
                } else {
                    const rs = avgGain / avgLoss;
                    currentRSI = 100 - (100 / (1 + rs));
                }
                rsiValues.push(currentRSI);
            }

            const finalRSI = rsiValues[rsiValues.length - 1];

            return { supertrend: finalSupertrend, rsi: finalRSI };
        }

        // --- Trading Logic (The Signal Rite) ---
        async function checkSignals() {
            if (!botRunning) return;
            updateBotStatus('Scanning market...', 'running');

            const klines = await fetchKlineData(CONFIG.symbol, CONFIG.interval, 200);
            if (!klines || klines.length === 0) {
                log('No kline data received. Check symbol/interval or API.', 'error');
                updateBotStatus('Error', 'error');
                return;
            }
            lastKlineData = klines; // Store for Gemini
            
            const currentPrice = klines[klines.length - 1].close;
            if (previousClosePrice === 0) previousClosePrice = currentPrice;
            const priceChange = currentPrice - previousClosePrice;
            previousClosePrice = currentPrice;

            const indicators = calculateIndicators(klines);
            if (!indicators) {
                log('Insufficient data for indicators. Awaiting more klines...', 'warning');
                updateBotStatus('Waiting for data', 'waiting');
                return;
            }
            
            const currentPosition = await _getOpenPositions();
            const supertrend = indicators.supertrend;
            const rsi = indicators.rsi;
            const balance = await _getAccountBalance();
            if (balance === null) {
                log('Could not retrieve account balance. Check API keys.', 'error');
                updateBotStatus('Error', 'error');
                return;
            }

            // Update UI Dashboard
            currentPriceEl.innerText = `$${currentPrice.toFixed(CONFIG.price_precision)}`;
            if (priceChange !== 0) {
                priceChangeEl.innerText = `${priceChange > 0 ? '↑' : '↓'} ${Math.abs(priceChange).toFixed(CONFIG.price_precision)}`;
                priceChangeEl.className = `text-xs mt-1 ${priceChange > 0 ? 'text-green-500' : 'text-red-500'}`;
            } else {
                priceChangeEl.innerText = 'No change';
                priceChangeEl.className = 'text-xs text-slate-500 mt-1';
            }
            
            stDirectionEl.innerText = supertrend.direction === 1 ? 'UPTREND' : 'DOWNTREND';
            stDirectionEl.className = `text-xl font-bold mt-1 ${supertrend.direction === 1 ? 'text-green-400' : 'text-red-400'}`;
            stValueEl.innerText = `Value: ${supertrend.value.toFixed(CONFIG.price_precision)}`;

            rsiValueEl.innerText = rsi.toFixed(2);
            let rsiStatusText = 'Neutral';
            let rsiStatusColor = 'text-yellow-400';
            if (rsi > CONFIG.rsi_overbought) {
                rsiStatusText = 'Overbought';
                rsiStatusColor = 'text-red-400';
            } else if (rsi < CONFIG.rsi_oversold) {
                rsiStatusText = 'Oversold';
                rsiStatusColor = 'text-green-400';
            }
            rsiValueEl.className = `text-xl font-bold mt-1 ${rsiStatusColor}`;
            rsiStatusEl.innerText = `Status: ${rsiStatusText}`;

            currentPositionEl.innerText = currentPosition ? (currentPosition.side.toUpperCase() + ' ' + parseFloat(currentPosition.size).toFixed(CONFIG.qty_precision)) : 'NONE';
            currentPositionEl.className = `text-xl font-bold mt-1 ${
                currentPosition ? (currentPosition.side === 'Buy' ? 'text-green-400' : 'text-red-400') : 'text-white'
            }`;
            
            accountBalanceEl.innerText = `$${balance.toFixed(2)}`;
            updateTradeStats();

            if (currentPosition) {
                const entryPrice = parseFloat(currentPosition.entryPrice);
                const positionSize = parseFloat(currentPosition.size);
                let pnl = 0;
                if (currentPosition.side === 'Buy') {
                    pnl = (currentPrice - entryPrice) * positionSize;
                } else { // Sell
                    pnl = (entryPrice - currentPrice) * positionSize;
                }
                positionPnLEl.innerText = `PnL: ${pnl.toFixed(2)} USDT`;
                positionPnLEl.className = `text-xs mt-1 ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`;
            } else {
                positionPnLEl.innerText = 'PnL: ---';
                positionPnLEl.className = 'text-xs text-slate-500 mt-1';
            }
            
            // Core Trading Logic
            if (lastSupertrendData.direction === 0) { // Initial run
                lastSupertrendData = supertrend;
                log('Initial Supertrend direction set. Awaiting next signal...', 'info');
                updateBotStatus('Idle', 'idle');
                return;
            }

            const buySignal = supertrend.direction === 1 && lastSupertrendData.direction === -1 && rsi < CONFIG.rsi_overbought;
            const sellSignal = supertrend.direction === -1 && lastSupertrendData.direction === 1 && rsi > CONFIG.rsi_oversold;

            if (buySignal) {
                log('BUY SIGNAL DETECTED! (RSI Confirmed)', 'signal');
                if (currentPosition) {
                    if (currentPosition.side === 'Sell') {
                        log('Reversal detected. Closing short position first.', 'warning');
                        const closed = await _closePosition(currentPosition, currentPrice);
                        if (closed) {
                            await _placeOrder('Buy', currentPrice, balance);
                        }
                    } else {
                        log('Already in a long position. No action needed.', 'info');
                    }
                } else {
                    await _placeOrder('Buy', currentPrice, balance);
                }
            } else if (sellSignal) {
                log('SELL SIGNAL DETECTED! (RSI Confirmed)', 'signal');
                if (currentPosition) {
                    if (currentPosition.side === 'Buy') {
                        log('Reversal detected. Closing long position first.', 'warning');
                        const closed = await _closePosition(currentPosition, currentPrice);
                        if (closed) {
                            await _placeOrder('Sell', currentPrice, balance);
                        }
                    } else {
                        log('Already in a short position. No action needed.', 'info');
                    }
                } else {
                    await _placeOrder('Sell', currentPrice, balance);
                }
            } else {
                log('No new signal detected. Observing...', 'info');
            }

            lastSupertrendData = supertrend; // Update last Supertrend data for next check
            updateBotStatus('Idle', 'idle');
        }
        
        async function _askGeminiForInsight() {
            if (!lastKlineData) {
                log("Gemini's insight requires recent market data. Please wait for the next market scan.", 'warning');
                return;
            }

            askGeminiBtn.disabled = true;
            askGeminiBtn.innerHTML = 'Consulting the Oracle... <span class="spinner"></span>';
            log('Consulting the Gemini Oracle for market insight...', 'llm');
            
            const klines = lastKlineData;
            const indicators = calculateIndicators(klines);
            
            if (!indicators || isNaN(indicators.rsi)) { // Check if rsi is valid
                log("Insufficient data for Gemini's insight. Indicators not fully calculated.", 'warning');
                askGeminiBtn.disabled = false;
                askGeminiBtn.innerHTML = '✨ Ask Gemini for Market Insight';
                return;
            }

            const currentPrice = klines[klines.length - 1].close;
            const stDirection = indicators.supertrend.direction === 1 ? 'Uptrend' : 'Downtrend';
            const rsiValue = indicators.rsi;
            
            // This is where you would put your actual Gemini API key.
            // **NEVER put this in production client-side code.**
            // This key is for demonstration purposes only.
            const GEMINI_API_KEY = ""; // REPLACE WITH YOUR GEMINI API KEY IF YOU WANT TO TEST
            const GEMINI_API_URL = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key=${GEMINI_API_KEY}`;
            
            if (!GEMINI_API_KEY) {
                log("Gemini API Key is missing. Please enter it in the script.", 'error');
                askGeminiBtn.disabled = false;
                askGeminiBtn.innerHTML = '✨ Ask Gemini for Market Insight';
                return;
            }

            const prompt = `Analyze the current market conditions for ${CONFIG.symbol} based on the following:
            - Current Price: ${currentPrice.toFixed(CONFIG.price_precision)}
            - Supertrend Direction: ${stDirection}
            - RSI Value: ${rsiValue.toFixed(2)} (Oversold < ${CONFIG.rsi_oversold}, Overbought > ${CONFIG.rsi_overbought})
            
            Provide a concise, neutral market analysis. Focus on interpreting these indicators and potential price implications. Avoid financial advice or predicting specific price targets. Max 100 words.`;
            
            let chatHistory = [];
            chatHistory.push({ role: "user", parts: [{ text: prompt }] });
            const payload = { contents: chatHistory };
            
            try {
                let response = null;
                let retries = 0;
                while (retries < CONFIG.max_retries) {
                    response = await fetch(GEMINI_API_URL, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    if (response.status === 429) { // Too many requests
                        const delay = CONFIG.retry_delay_base * Math.pow(2, retries);
                        log(`Gemini Rate limit exceeded. Retrying in ${delay / 1000} seconds. (Attempt ${retries + 1})`, 'warning');
                        await new Promise(res => setTimeout(res, delay));
                        retries++;
                    } else if (!response.ok) {
                        throw new Error(`API returned status ${response.status}: ${await response.text()}`);
                    } else {
                        break; // Success or non-retryable error
                    }
                }

                if (!response.ok) {
                    throw new Error(`Failed after retries. API returned status ${response.status}: ${await response.text()}`);
                }
                
                const result = await response.json();
                const text = result.candidates?.[0]?.content?.parts?.[0]?.text || "No insight available.";
                
                log('--- Gemini Insight ---', 'llm');
                log(text, 'llm');
                log('--------------------', 'llm');

            } catch (e) {
                log(`Failed to get Gemini Insight: ${e.message}`, 'error');
            } finally {
                askGeminiBtn.disabled = false;
                askGeminiBtn.innerHTML = '✨ Ask Gemini for Market Insight';
            }
        }

        function exportLogs() {
            const allLogEntries = Array.from(logArea.children).map(div => div.innerText).join('\n');
            const blob = new Blob([allLogEntries], { type: 'text/plain;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `pyrmethus_grimoire_logs_${new Date().toISOString().slice(0, 10)}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            log('Logs exported successfully.', 'info');
        }

        function clearLogs() {
            logArea.innerHTML = '<div class="log-entry info">Logs cleared. Awaiting your command, Master Pyrmethus...</div>';
            log('Log area cleared.', 'info');
        }

        // --- Main Ritual Activation ---
        async function startBot() {
            if (botRunning) {
                clearInterval(intervalId);
                botRunning = false;
                buttonTextEl.innerText = 'Start the Bot';
                startBotBtn.classList.remove('bg-red-600', 'shadow-red-500/50');
                startBotBtn.classList.add('bg-gradient-neon', 'shadow-pink-500/50');
                log('The ritual is paused.', 'warning');
                updateBotStatus('Idle', 'idle');
                return;
            }
            
            const apiKey = apiKeyInput.value;
            const apiSecret = apiSecretInput.value;

            if (!apiKey || !apiSecret) {
                log('Master, you must bind the grimoire to your API keys first!', 'error');
                return;
            }

            log('Credentials verified. Initiating the ritual...', 'success');

            CONFIG.symbol = symbolInput.value.toUpperCase();
            CONFIG.interval = intervalInput.value;
            CONFIG.leverage = parseInt(leverageInput.value);
            CONFIG.riskPct = parseFloat(riskPctInput.value);
            CONFIG.stopLossPct = parseFloat(stopLossPctInput.value);
            CONFIG.takeProfitPct = parseFloat(takeProfitPctInput.value);

            // Set leverage at the start
            const leverageSet = await _setLeverage(CONFIG.symbol, CONFIG.leverage);
            if (!leverageSet) {
                log('Failed to set leverage. Bot cannot start.', 'error');
                updateBotStatus('Error', 'error');
                return;
            }
            
            botRunning = true;
            buttonTextEl.innerText = 'Stop the Bot';
            startBotBtn.classList.remove('bg-gradient-neon', 'shadow-pink-500/50');
            startBotBtn.classList.add('bg-red-600', 'shadow-red-500/50');
            log('The bot is now active. Its eyes are open to the market winds.', 'success');
            updateBotStatus('Running', 'running');
            
            // Clear last Supertrend direction to re-initialize on first check
            lastSupertrendData = { direction: 0, value: 0 }; 
            previousClosePrice = 0; // Reset for price change calculation

            await checkSignals(); // Run once immediately
            const intervalMilliseconds = CONFIG.interval === 'D' ? 24 * 60 * 60 * 1000 : CONFIG.interval * 60 * 1000;
            intervalId = setInterval(checkSignals, intervalMilliseconds);
        }

        // Event Listeners
        startBotBtn.addEventListener('click', startBot);
        askGeminiBtn.addEventListener('click', _askGeminiForInsight);
        clearLogsBtn.addEventListener('click', clearLogs);
        exportLogsBtn.addEventListener('click', exportLogs);

        // Initial UI Update
        updateTradeStats();
        updateBotStatus('Idle', 'idle');
    </script>
</body>
</html>
import os
import time
import json
import logging
import google.generativeai as genai
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from pybit.unified_trading import HTTP

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Configuration ---
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if not BYBIT_API_KEY or not BYBIT_API_SECRET:
    logging.error("Bybit API Key or Secret not found in environment variables. Please check your .env file.")
if not GEMINI_API_KEY:
    logging.warning("Gemini API Key not found in environment variables. Gemini insight will be unavailable.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# Initialize Pybit client (Testnet)
bybit_session = HTTP(
    testnet=True,
    api_key=BYBIT_API_KEY,
    api_secret=BYBIT_API_SECRET
)

# --- Helper for API Calls with Retry ---
def make_api_call(api_client, method, endpoint, params=None, max_retries=3, initial_delay=1):
    """Generic function to make API calls with retry logic."""
    for attempt in range(max_retries):
        try:
            if method == 'get':
                response = getattr(api_client, endpoint)(**params) if params else getattr(api_client, endpoint)()
            elif method == 'post':
                response = getattr(api_client, endpoint)(**params)
            else:
                return {"retCode": 1, "retMsg": "Invalid method"}

            if response.get('retCode') == 0:
                return response
            else:
                ret_code = response.get('retCode')
                ret_msg = response.get('retMsg')
                logging.warning(f"API Error ({ret_code}): {ret_msg}. Retrying {endpoint} in {initial_delay * (2**attempt)}s...")
                time.sleep(initial_delay * (2**attempt)) # Exponential backoff
        except Exception as e:
            logging.error(f"Network/Client error for {endpoint}: {e}. Retrying in {initial_delay * (2**attempt)}s...")
            time.sleep(initial_delay * (2**attempt)) # Exponential backoff
    return {"retCode": 1, "retMsg": f"Failed after {max_retries} attempts: {endpoint}"}


# --- Bybit API Endpoints ---
@app.route('/api/klines', methods=['GET'])
def get_klines():
    symbol = request.args.get('symbol')
    interval = request.args.get('interval')
    limit = request.args.get('limit', type=int)

    if not all([symbol, interval, limit]):
        return jsonify({"retCode": 1, "retMsg": "Missing symbol, interval, or limit"}), 400

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    response = make_api_call(bybit_session, 'get', 'get_kline', params)
    return jsonify(response)

@app.route('/api/position', methods=['GET'])
def get_position():
    symbol = request.args.get('symbol')
    if not symbol:
        return jsonify({"retCode": 1, "retMsg": "Missing symbol"}), 400
    params = {"category": "linear", "symbol": symbol}
    response = make_api_call(bybit_session, 'get', 'get_positions', params)
    return jsonify(response)

@app.route('/api/order', methods=['POST'])
def place_order():
    data = request.json
    required_params = ['symbol', 'side', 'orderType', 'qty', 'category']
    if not all(k in data for k in required_params):
        return jsonify({"retCode": 1, "retMsg": "Missing required order parameters"}), 400

    # Ensure TP/SL are numbers if provided
    if 'takeProfit' in data:
        data['takeProfit'] = float(data['takeProfit'])
    if 'stopLoss' in data:
        data['stopLoss'] = float(data['stopLoss'])
    if 'qty' in data:
        data['qty'] = str(data['qty']) # Pybit expects qty as string for API

    response = make_api_call(bybit_session, 'post', 'place_order', data)
    return jsonify(response)

@app.route('/api/balance', methods=['GET'])
def get_balance():
    coin = request.args.get('coin', 'USDT')
    params = {"accountType": "UNIFIED", "coin": coin}
    response = make_api_call(bybit_session, 'get', 'get_wallet_balance', params)
    return jsonify(response)

@app.route('/api/leverage', methods=['POST'])
def set_leverage():
    data = request.json
    symbol = data.get('symbol')
    leverage = data.get('leverage')
    if not all([symbol, leverage]):
        return jsonify({"retCode": 1, "retMsg": "Missing symbol or leverage"}), 400
    
    params = {
        "category": "linear",
        "symbol": symbol,
        "buyLeverage": str(leverage), # Pybit expects leverage as string
        "sellLeverage": str(leverage),
    }
    response = make_api_call(bybit_session, 'post', 'set_leverage', params)
    return jsonify(response)

# --- Gemini AI Endpoint ---
@app.route('/api/gemini-insight', methods=['POST'])
def gemini_insight():
    if not GEMINI_API_KEY:
        return jsonify({"retCode": 1, "retMsg": "Gemini API Key is not configured on the server."}), 503

    data = request.json
    prompt = data.get('prompt')
    if not prompt:
        return jsonify({"retCode": 1, "retMsg": "Missing prompt"}), 400

    try:
        model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
        chat = model.start_chat(history=[])
        response = chat.send_message(prompt)
        return jsonify({"retCode": 0, "retMsg": "Success", "insight": response.text})
    except Exception as e:
        logging.error(f"Gemini API error: {e}")
        return jsonify({"retCode": 1, "retMsg": f"Gemini API Error: {str(e)}"}), 500

# --- Run Server ---
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
