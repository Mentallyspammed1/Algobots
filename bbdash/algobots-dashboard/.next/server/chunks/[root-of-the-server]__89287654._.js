module.exports = {

"[project]/.next-internal/server/app/api/trades/route/actions.js [app-rsc] (server actions loader, ecmascript)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
}}),
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}}),
"[externals]/@opentelemetry/api [external] (@opentelemetry/api, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("@opentelemetry/api", () => require("@opentelemetry/api"));

module.exports = mod;
}}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}}),
"[externals]/next/dist/server/app-render/after-task-async-storage.external.js [external] (next/dist/server/app-render/after-task-async-storage.external.js, cjs)": (function(__turbopack_context__) {

var { g: global, __dirname, m: module, e: exports } = __turbopack_context__;
{
const mod = __turbopack_context__.x("next/dist/server/app-render/after-task-async-storage.external.js", () => require("next/dist/server/app-render/after-task-async-storage.external.js"));

module.exports = mod;
}}),
"[project]/src/lib/bybit-api.ts [app-route] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
// Types
__turbopack_context__.s({
    "BYBIT_WEBSOCKET_URL": (()=>BYBIT_WEBSOCKET_URL),
    "DEFAULT_REQUEST_TIMEOUT": (()=>DEFAULT_REQUEST_TIMEOUT),
    "getKline": (()=>getKline),
    "getOrderBook": (()=>getOrderBook),
    "getRecentTrades": (()=>getRecentTrades),
    "getTicker": (()=>getTicker),
    "getTickers": (()=>getTickers)
});
// Constants
const BYBIT_API_URL = 'https://api.bybit.com';
const BYBIT_WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/spot';
const DEFAULT_REQUEST_TIMEOUT = 10000; // 10 seconds
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
// Enhanced fetch function with retry logic and timeout
async function fetchFromBybit(endpoint, params = {}, options = {}) {
    const url = new URL(endpoint, BYBIT_API_URL);
    url.search = new URLSearchParams(params).toString();
    const controller = new AbortController();
    const timeoutId = setTimeout(()=>controller.abort(), DEFAULT_REQUEST_TIMEOUT);
    const fetchOptions = {
        cache: 'no-store',
        signal: options.signal || controller.signal,
        headers: {
            'Content-Type': 'application/json'
        },
        ...options
    };
    let retryCount = 0;
    while(retryCount <= MAX_RETRIES){
        try {
            const response = await fetch(url.toString(), fetchOptions);
            clearTimeout(timeoutId); // Clear timeout once response is received
            if (!response.ok) {
                throw new Error(`Bybit API error: ${response.status} ${response.statusText}`);
            }
            const data = await response.json();
            if (data.retCode !== 0) {
                throw new Error(`Bybit API error: ${data.retMsg} (Code: ${data.retCode})`);
            }
            return data.result;
        } catch (error) {
            clearTimeout(timeoutId);
            // Don't retry on abort errors or if we've reached max retries
            if (error instanceof Error && error.name === 'AbortError') {
                console.error(`Request to ${endpoint} timed out or was aborted`);
                return null;
            }
            if (retryCount === MAX_RETRIES) {
                console.error(`Failed to fetch from Bybit endpoint ${endpoint} after ${MAX_RETRIES} retries:`, error);
                return null;
            }
            // Exponential backoff
            const delay = RETRY_DELAY_MS * Math.pow(2, retryCount);
            console.warn(`Retry ${retryCount + 1}/${MAX_RETRIES} for ${endpoint} in ${delay}ms`);
            await new Promise((resolve)=>setTimeout(resolve, delay));
            retryCount++;
        }
    }
    return null;
}
async function getTicker(symbol) {
    try {
        const result = await fetchFromBybit('/v5/market/tickers', {
            category: 'spot',
            symbol
        });
        if (!result || !result.list || result.list.length === 0) {
            console.warn(`No ticker data found for symbol: ${symbol}`);
            return null;
        }
        // Extract and validate the ticker data
        const ticker = result.list[0];
        // Validate required fields
        const requiredFields = [
            'lastPrice',
            'highPrice24h',
            'lowPrice24h',
            'turnover24h',
            'volume24h'
        ];
        for (const field of requiredFields){
            if (ticker[field] === undefined || ticker[field] === null) {
                console.warn(`Missing required field ${field} in ticker data for ${symbol}`);
                return null;
            }
        }
        return {
            lastPrice: ticker.lastPrice,
            highPrice24h: ticker.highPrice24h,
            lowPrice24h: ticker.lowPrice24h,
            turnover24h: ticker.turnover24h,
            volume24h: ticker.volume24h,
            price24hPcnt: ticker.price24hPcnt || '0'
        };
    } catch (error) {
        console.error(`Error fetching ticker for ${symbol}:`, error);
        return null;
    }
}
async function getOrderBook(symbol, limit = 20) {
    try {
        const result = await fetchFromBybit('/v5/market/orderbook', {
            category: 'spot',
            symbol,
            limit: limit.toString()
        });
        if (!result) {
            console.warn(`No orderbook data found for symbol: ${symbol}`);
            return null;
        }
        // Validate the orderbook structure
        if (!result.b || !result.a || !Array.isArray(result.b) || !Array.isArray(result.a)) {
            console.warn(`Invalid orderbook structure for symbol: ${symbol}`);
            return null;
        }
        // Ensure bids and asks are properly formatted
        const bids = result.b.filter((entry)=>Array.isArray(entry) && entry.length === 2 && entry[0] && entry[1]);
        const asks = result.a.filter((entry)=>Array.isArray(entry) && entry.length === 2 && entry[0] && entry[1]);
        return {
            bids,
            asks,
            ts: result.ts || Date.now().toString()
        };
    } catch (error) {
        console.error(`Error fetching orderbook for ${symbol}:`, error);
        return null;
    }
}
async function getRecentTrades(symbol, limit = 30, options = {}) {
    try {
        const result = await fetchFromBybit('/v5/market/recent-trade', {
            category: 'spot',
            symbol,
            limit: limit.toString()
        }, options);
        if (!result || !result.list || !Array.isArray(result.list)) {
            return [];
        }
        // Filter and validate trade data
        return result.list.filter((trade)=>{
            return trade.execId && trade.execTime && trade.price && trade.qty && (trade.side === 'Buy' || trade.side === 'Sell');
        }).map((trade)=>({
                execId: trade.execId,
                execTime: trade.execTime,
                price: trade.price,
                qty: trade.qty,
                side: trade.side,
                isBlockTrade: trade.isBlockTrade || false
            }));
    } catch (error) {
        if (!(error instanceof Error && error.name === 'AbortError')) {
            console.error(`Error fetching recent trades for ${symbol}:`, error);
        }
        return [];
    }
}
async function getKline(symbol, interval, limit = 100) {
    try {
        // Map user-friendly intervals to Bybit format
        const intervalMap = {
            '1m': '1',
            '5m': '5',
            '15m': '15',
            '30m': '30',
            '1h': '60',
            '2h': '120',
            '4h': '240',
            '6h': '360',
            '12h': '720',
            '1d': 'D',
            '1w': 'W',
            '1M': 'M'
        };
        const bybitInterval = intervalMap[interval] || interval;
        const result = await fetchFromBybit('/v5/market/kline', {
            category: 'spot',
            symbol,
            interval: bybitInterval,
            limit: limit.toString()
        });
        if (!result || !result.list || !Array.isArray(result.list)) {
            console.warn(`No kline data found for symbol: ${symbol} with interval: ${interval}`);
            return null;
        }
        // Validate and format kline entries
        return result.list.filter((entry)=>{
            return Array.isArray(entry) && entry.length >= 7 && entry.every((val)=>val !== null && val !== undefined);
        }).map((entry)=>entry.slice(0, 7));
    } catch (error) {
        console.error(`Error fetching kline data for ${symbol} with interval ${interval}:`, error);
        return null;
    }
}
async function getTickers(symbols) {
    const results = {};
    // Use Promise.allSettled to handle partial failures
    const promises = symbols.map(async (symbol)=>{
        const ticker = await getTicker(symbol);
        return {
            symbol,
            ticker
        };
    });
    const settledResults = await Promise.allSettled(promises);
    settledResults.forEach((result)=>{
        if (result.status === 'fulfilled' && result.value.ticker) {
            const { symbol, ticker } = result.value;
            results[symbol] = ticker;
        }
    });
    return results;
}
}}),
"[project]/src/app/api/trades/route.ts [app-route] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "GET": (()=>GET),
    "dynamic": (()=>dynamic)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/server.js [app-route] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/bybit-api.ts [app-route] (ecmascript)");
;
;
function calculateVolumePressure(trades) {
    const emptyState = {
        buyVolume: 0,
        sellVolume: 0,
        totalVolume: 0,
        buyPercentage: 50,
        sellPercentage: 50
    };
    if (!trades || trades.length === 0) {
        return emptyState;
    }
    let buyVolume = 0;
    let sellVolume = 0;
    trades.forEach((trade)=>{
        const volume = parseFloat(trade.qty);
        if (isNaN(volume)) return;
        if (trade.side === 'Buy') {
            buyVolume += volume;
        } else {
            sellVolume += volume;
        }
    });
    const totalVolume = buyVolume + sellVolume;
    if (totalVolume === 0) {
        return emptyState;
    }
    const buyPercentage = buyVolume / totalVolume * 100;
    const sellPercentage = sellVolume / totalVolume * 100;
    return {
        buyVolume,
        sellVolume,
        totalVolume,
        buyPercentage,
        sellPercentage
    };
}
async function GET(request) {
    const { searchParams } = new URL(request.url);
    const symbol = searchParams.get('symbol');
    if (!symbol) {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Symbol parameter is required'
        }, {
            status: 400
        });
    }
    try {
        const trades = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$route$5d$__$28$ecmascript$29$__["getRecentTrades"])(symbol);
        const volumePressure = calculateVolumePressure(trades);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            trades,
            volumePressure
        });
    } catch (error) {
        console.error(`API Route Error for /api/trades?symbol=${symbol}:`, error);
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$server$2e$js__$5b$app$2d$route$5d$__$28$ecmascript$29$__["NextResponse"].json({
            error: 'Failed to fetch trade data',
            details: errorMessage
        }, {
            status: 500
        });
    }
}
const dynamic = 'force-dynamic';
}}),

};

//# sourceMappingURL=%5Broot-of-the-server%5D__89287654._.js.map