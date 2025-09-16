module.exports = {

"[project]/src/ai/genkit.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "ai": (()=>ai)
});
(()=>{
    const e = new Error("Cannot find module 'genkit'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
(()=>{
    const e = new Error("Cannot find module '@genkit-ai/googleai'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
;
;
const ai = genkit({
    plugins: [
        googleAI()
    ],
    model: 'googleai/gemini-2.5-flash',
    enableDevUI: true
});
}}),
"[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "BYBIT_WEBSOCKET_URL": (()=>BYBIT_WEBSOCKET_URL),
    "DEFAULT_REQUEST_TIMEOUT": (()=>DEFAULT_REQUEST_TIMEOUT),
    "KlineEntrySchema": (()=>KlineEntrySchema),
    "OrderBookEntrySchema": (()=>OrderBookEntrySchema),
    "OrderBookSchema": (()=>OrderBookSchema),
    "RecentTradeSchema": (()=>RecentTradeSchema),
    "TickerInfoSchema": (()=>TickerInfoSchema),
    "getKline": (()=>getKline),
    "getOrderBook": (()=>getOrderBook),
    "getRecentTrades": (()=>getRecentTrades),
    "getTicker": (()=>getTicker),
    "getTickers": (()=>getTickers)
});
(()=>{
    const e = new Error("Cannot find module 'zod'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
;
const TickerInfoSchema = z.object({
    lastPrice: z.string(),
    highPrice24h: z.string(),
    lowPrice24h: z.string(),
    turnover24h: z.string(),
    volume24h: z.string(),
    price24hPcnt: z.string()
});
const OrderBookEntrySchema = z.tuple([
    z.string(),
    z.string()
]); // [price, size]
const OrderBookSchema = z.object({
    bids: z.array(OrderBookEntrySchema),
    asks: z.array(OrderBookEntrySchema),
    ts: z.string()
});
const RecentTradeSchema = z.object({
    execId: z.string(),
    execTime: z.union([
        z.string(),
        z.number()
    ]),
    price: z.string(),
    qty: z.string(),
    side: z.enum([
        'Buy',
        'Sell'
    ]),
    isBlockTrade: z.boolean().optional()
});
const KlineEntrySchema = z.tuple([
    z.string(),
    z.string(),
    z.string(),
    z.string(),
    z.string(),
    z.string(),
    z.string(),
    z.string().optional() // Optional: Confirm flag (1 if the kline is closed)
]);
// #endregion
// #region Constants
const BYBIT_API_URL = 'https://api.bybit.com';
const BYBIT_WEBSOCKET_URL = 'wss://stream.bybit.com/v5/public/spot';
const DEFAULT_REQUEST_TIMEOUT = 10000; // 10 seconds
const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;
/**
 * An enhanced fetch function for interacting with the Bybit API.
 * Includes retry logic, request timeout, and standardized error handling.
 *
 * @param endpoint - The API endpoint path (e.g., '/v5/market/tickers').
 * @param params - A record of query parameters to include in the request.
 * @param options - Standard RequestInit options to pass to fetch.
 * @returns A promise that resolves to the 'result' field of the API response, or null if an error occurs.
 */ async function fetchFromBybit(endpoint, params = {}, options = {}) {
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
        const validation = TickerInfoSchema.safeParse(ticker);
        if (!validation.success) {
            console.warn(`Invalid ticker data received for ${symbol}:`, validation.error);
            return null;
        }
        return validation.data;
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
        const validation = OrderBookSchema.safeParse({
            bids: result.b,
            asks: result.a,
            ts: result.ts?.toString() || Date.now().toString()
        });
        if (!validation.success) {
            console.warn(`Invalid orderbook data for ${symbol}:`, validation.error);
            return null;
        }
        return validation.data;
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
        const validatedTrades = [];
        for (const trade of result.list){
            const mappedTrade = {
                execId: trade.i,
                execTime: trade.T,
                price: trade.p,
                qty: trade.v,
                side: trade.S,
                isBlockTrade: trade.m
            };
            const validation = RecentTradeSchema.safeParse(mappedTrade);
            if (validation.success) {
                validatedTrades.push(validation.data);
            }
        }
        return validatedTrades;
    } catch (error) {
        if (!(error instanceof Error && error.name === 'AbortError')) {
            console.error(`Error fetching recent trades for ${symbol}:`, error);
        }
        return [];
    }
}
async function getKline(symbol, interval, limit = 100) {
    try {
        // Map user-friendly intervals to Bybit's required format
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
        const validation = z.array(KlineEntrySchema).safeParse(result.list);
        if (!validation.success) {
            console.warn(`Invalid kline data for ${symbol} with interval ${interval}:`, validation.error);
            return null;
        }
        return validation.data;
    } catch (error) {
        console.error(`Error fetching kline data for ${symbol} with interval ${interval}:`, error);
        return null;
    }
}
async function getTickers(symbols) {
    const results = {};
    // Use Promise.allSettled to handle partial failures gracefully
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
"[project]/src/lib/indicators.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "IndicatorDataSchema": (()=>IndicatorDataSchema),
    "IndicatorSettingsSchema": (()=>IndicatorSettingsSchema),
    "calculateIndicators": (()=>calculateIndicators),
    "defaultIndicatorSettings": (()=>defaultIndicatorSettings)
});
(()=>{
    const e = new Error("Cannot find module 'zod'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
(()=>{
    const e = new Error("Cannot find module 'technicalindicators'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
;
;
const IndicatorSettingsSchema = z.object({
    rsi: z.object({
        period: z.number().default(14)
    }),
    macd: z.object({
        fastPeriod: z.number().default(12),
        slowPeriod: z.number().default(26),
        signalPeriod: z.number().default(9)
    }),
    bollingerBands: z.object({
        period: z.number().default(20),
        stdDev: z.number().default(2)
    }),
    stochastic: z.object({
        period: z.number().default(14),
        signalPeriod: z.number().default(3)
    }),
    atr: z.object({
        period: z.number().default(14)
    }),
    williamsR: z.object({
        period: z.number().default(14)
    }),
    cci: z.object({
        period: z.number().default(20)
    }),
    roc: z.object({
        period: z.number().default(14)
    }),
    mfi: z.object({
        period: z.number().default(14)
    }),
    awesomeOscillator: z.object({
        fastPeriod: z.number().default(5),
        slowPeriod: z.number().default(34)
    }),
    ichimokuCloud: z.object({
        conversionPeriod: z.number().default(9),
        basePeriod: z.number().default(26),
        spanPeriod: z.number().default(52),
        displacement: z.number().default(26)
    }),
    sma: z.object({
        period: z.number().default(20)
    }),
    supertrend: z.object({
        period: z.number().default(10),
        multiplier: z.number().default(3)
    })
});
// #endregion
// #region Result Schemas
const RsiResultSchema = z.number().nullable();
const MacdResultSchema = z.object({
    macd: z.number(),
    signal: z.number(),
    histogram: z.number()
}).nullable();
const BollingerBandsResultSchema = z.object({
    upper: z.number(),
    middle: z.number(),
    lower: z.number()
}).nullable();
const StochasticResultSchema = z.object({
    k: z.number(),
    d: z.number()
}).nullable();
const AtrResultSchema = z.number().nullable();
const WilliamsRResultSchema = z.number().nullable();
const CciResultSchema = z.number().nullable();
const RocResultSchema = z.number().nullable();
const MfiResultSchema = z.number().nullable();
const AwesomeOscillatorResultSchema = z.number().nullable();
const IchimokuCloudResultSchema = z.object({
    conversion: z.number(),
    base: z.number(),
    spanA: z.number(),
    spanB: z.number()
}).nullable();
const SmaResultSchema = z.number().nullable();
const SupertrendResultSchema = z.any().nullable();
const IndicatorDataSchema = z.object({
    rsi: RsiResultSchema,
    macd: MacdResultSchema,
    bollingerBands: BollingerBandsResultSchema,
    stochastic: StochasticResultSchema,
    atr: AtrResultSchema,
    williamsR: WilliamsRResultSchema,
    cci: CciResultSchema,
    roc: RocResultSchema,
    mfi: MfiResultSchema,
    awesomeOscillator: AwesomeOscillatorResultSchema,
    ichimokuCloud: IchimokuCloudResultSchema,
    sma: SmaResultSchema,
    supertrend: SupertrendResultSchema
});
const defaultIndicatorSettings = IndicatorSettingsSchema.parse({});
function calculateIndicators(closePrices, highPrices, lowPrices, volumes, settings) {
    const input = {
        high: highPrices,
        low: lowPrices,
        close: closePrices,
        volume: volumes,
        period: 0
    };
    const getLast = (arr)=>arr && arr.length > 0 ? arr[arr.length - 1] : null;
    const getLastObj = (arr)=>arr && arr.length > 0 ? arr[arr.length - 1] : null;
    const rsi = getLast(ti.RSI.calculate({
        ...input,
        period: settings.rsi.period,
        values: closePrices
    }));
    const macd = getLastObj(ti.MACD.calculate({
        ...input,
        ...settings.macd,
        values: closePrices
    }));
    const bollingerBands = getLastObj(ti.BollingerBands.calculate({
        ...input,
        ...settings.bollingerBands,
        values: closePrices
    }));
    const stochastic = getLastObj(ti.Stochastic.calculate({
        ...input,
        ...settings.stochastic
    }));
    const atr = getLast(ti.ATR.calculate({
        ...input,
        period: settings.atr.period
    }));
    const williamsR = getLast(ti.WilliamsR.calculate({
        ...input,
        period: settings.williamsR.period
    }));
    const cci = getLast(ti.CCI.calculate({
        ...input,
        period: settings.cci.period
    }));
    const roc = getLast(ti.ROC.calculate({
        ...input,
        period: settings.roc.period,
        values: closePrices
    }));
    const mfi = getLast(ti.MFI.calculate({
        ...input,
        period: settings.mfi.period
    }));
    const awesomeOscillator = getLast(ti.AwesomeOscillator.calculate({
        ...input,
        ...settings.awesomeOscillator
    }));
    const ichimokuCloud = getLastObj(ti.IchimokuCloud.calculate({
        ...input,
        ...settings.ichimokuCloud
    }));
    const sma = getLast(ti.SMA.calculate({
        ...input,
        period: settings.sma.period,
        values: closePrices
    }));
    const supertrend = getLastObj(ti.Supertrend.calculate({
        ...input,
        ...settings.supertrend
    }));
    return {
        rsi,
        macd,
        bollingerBands,
        stochastic,
        atr,
        williamsR,
        cci,
        roc,
        mfi,
        awesomeOscillator,
        ichimokuCloud,
        sma,
        supertrend
    };
}
}}),
"[project]/src/ai/flows/generate-trading-signal.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
/* __next_internal_action_entry_do_not_use__ [{"40fe1dd1a8fa94dbff281c3d6bbbf304f3e4c539f8":"generateTradingSignal"},"",""] */ __turbopack_context__.s({
    "generateTradingSignal": (()=>generateTradingSignal)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/server-reference.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$app$2d$render$2f$encryption$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/app-render/encryption.js [app-rsc] (ecmascript)");
/**
 * @fileOverview An AI agent that generates trading signals and market analysis.
 *
 * - generateTradingSignal - A function that generates trading signals and market analysis.
 * - GenerateTradingSignalInput - The input type for the generateTradingSignal function.
 * - GenerateTradingSignalOutput - The return type for the generateTradingSignal function.
 */ var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/ai/genkit.ts [app-rsc] (ecmascript)");
(()=>{
    const e = new Error("Cannot find module 'genkit'");
    e.code = 'MODULE_NOT_FOUND';
    throw e;
})();
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/action-validate.js [app-rsc] (ecmascript)");
;
;
;
;
;
;
;
const GenerateTradingSignalInputSchema = z.object({
    symbol: z.string().describe('The trading symbol (e.g., BTCUSDT).'),
    timeframe: z.string().describe('The timeframe for the chart and data (e.g., 1m, 5m, 1h, 1d).'),
    indicatorSettings: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorSettings"].optional().describe('The settings for the technical indicators.')
});
const GenerateTradingSignalOutputSchema = z.object({
    currentPrice: z.number().describe('The current price of the asset.'),
    entryPrice: z.number().describe('The recommended entry price for the trade.'),
    takeProfit: z.number().describe('The recommended take-profit price level.'),
    stopLoss: z.number().describe('The recommended stop-loss price level.'),
    signal: z.enum([
        'Buy',
        'Sell',
        'Hold'
    ]).describe('The trading signal: Buy, Sell, or Hold.'),
    reasoning: z.string().describe('Detailed reasoning for the generated signal, based on market analysis.'),
    confidenceLevel: z.enum([
        'High',
        'Medium',
        'Low'
    ]).describe('The confidence level of the signal.')
});
// Tool Definitions
const getKlineData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getKlineData',
    description: 'Get candlestick (Kline) data.',
    inputSchema: z.object({
        symbol: z.string(),
        timeframe: z.string()
    }),
    outputSchema: z.array(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["KlineEntrySchema"]).nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKlineData"]);
const getOrderBookData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getOrderBookData',
    description: 'Get order book data.',
    inputSchema: z.object({
        symbol: z.string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["OrderBookSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getOrderBookData"]);
const getRecentTradesData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getRecentTradesData',
    description: 'Get recent public trades.',
    inputSchema: z.object({
        symbol: z.string()
    }),
    outputSchema: z.array(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["RecentTradeSchema"])
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getRecentTrades"]);
const getIndicatorData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getIndicatorData',
    description: 'Get technical indicator data.',
    inputSchema: z.object({
        symbol: z.string(),
        timeframe: z.string(),
        settings: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorSettings"].optional()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["IndicatorDataSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getIndicatorData"]);
const getMarketData = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'getMarketData',
    description: 'Get the latest market ticker data.',
    inputSchema: z.object({
        symbol: z.string()
    }),
    outputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["TickerInfoSchema"].nullable()
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getMarketData"]);
const analyzeOrderBook = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineTool({
    name: 'analyzeOrderBook',
    description: 'Analyze order book to find support/resistance.',
    inputSchema: __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["OrderBookSchema"],
    outputSchema: z.object({
        support: z.array(z.number()),
        resistance: z.array(z.number())
    })
}, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["analyzeOrderBook"]);
async function generateTradingSignal(input) {
    return generateTradingSignalFlow(input);
}
const tradingSignalPrompt = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].definePrompt({
    name: 'tradingSignalPrompt',
    output: {
        format: 'json',
        schema: GenerateTradingSignalOutputSchema
    },
    tools: [
        getKlineData,
        getOrderBookData,
        getRecentTradesData,
        getIndicatorData,
        getMarketData,
        analyzeOrderBook
    ],
    system: `You are an expert financial analyst AI. Your goal is to generate a trading signal based on a comprehensive analysis of market data.

  **Process:**
  1.  **Get Current Price:** Start by calling \`getMarketData\` to get the current price. This is essential. If it fails, you cannot proceed.
  2.  **Gather Data:** Call all other available data tools (\`getKlineData\`, \`getOrderBookData\`, \`getRecentTradesData\`, \`getIndicatorData\`) to build a complete picture of the market.
  3.  **Analyze Order Book:** If \`getOrderBookData\` was successful, immediately pass its output to \`analyzeOrderBook\` to identify key support and resistance levels.
  4.  **Synthesize Findings:** Review all the data you have gathered. Look for confirmations or divergences between different data sources (e.g., does the RSI confirm the price action? Does the order book support a potential breakout?).
  5.  **Formulate Reasoning:** Construct a detailed, step-by-step \`reasoning\` for your final decision. Reference specific data points (e.g., "RSI is 78, indicating overbought conditions," "Strong resistance identified at $52,000 by order book analysis"). If a tool failed, you MUST mention it in your reasoning (e.g., "Could not retrieve indicator data, so confidence is lowered.").
  6.  **Generate Signal:** Based on your reasoning, determine the \`signal\` (Buy, Sell, or Hold), \`entryPrice\`, \`takeProfit\`, and \`stopLoss\`.
  7.  **Set Confidence:** Determine the \`confidenceLevel\` based on how much data you could retrieve and how strongly it points to a particular outcome.

  Your final output must be a valid JSON object matching the provided schema.`
});
const generateTradingSignalFlow = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$genkit$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ai"].defineFlow({
    name: 'generateTradingSignalFlow',
    inputSchema: GenerateTradingSignalInputSchema,
    outputSchema: GenerateTradingSignalOutputSchema
}, async (input)=>{
    const response = await tradingSignalPrompt({
        prompt: `Generate a trading signal for ${input.symbol} on the ${input.timeframe} timeframe. Indicator settings: ${JSON.stringify(input.indicatorSettings || {})}`
    });
    if (!response.output) {
        throw new Error("AI failed to produce a valid response.");
    }
    const output = response.output;
    // Final validation
    if (output.currentPrice === null || isNaN(output.currentPrice) || output.currentPrice <= 0) {
        throw new Error("AI failed to generate a valid signal with a positive current price.");
    }
    const requiredNumericFields = [
        'entryPrice',
        'takeProfit',
        'stopLoss'
    ];
    for (const field of requiredNumericFields){
        if (output[field] === null || isNaN(output[field]) || output[field] <= 0) {
            throw new Error(`AI generated an invalid or non-positive value for '${field}'.`);
        }
    }
    return output;
});
;
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ensureServerEntryExports"])([
    generateTradingSignal
]);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(generateTradingSignal, "40fe1dd1a8fa94dbff281c3d6bbbf304f3e4c539f8", null);
}}),
"[project]/src/lib/actions.ts [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
/* __next_internal_action_entry_do_not_use__ [{"404bceabf4524442855236b92fdc7049a3e2aa0d9e":"getOrderBookData","40ecf96ec3829da1facb2822b20b7b6fb2faedc074":"getMarketData","40ed26910e6df74305f6af4c2aa1e4f10fbe170c0d":"analyzeOrderBook","6075278ac703872d2e66765d6f6dbe7646dd10bb25":"getKlineData","70901addb4aa828fa13a5df1151b80af96986e9baf":"getIndicatorData","70c6125dbbad3595350503c517b30b35b439281e36":"getAiTradingSignal"},"",""] */ __turbopack_context__.s({
    "analyzeOrderBook": (()=>analyzeOrderBook),
    "getAiTradingSignal": (()=>getAiTradingSignal),
    "getIndicatorData": (()=>getIndicatorData),
    "getKlineData": (()=>getKlineData),
    "getMarketData": (()=>getMarketData),
    "getOrderBookData": (()=>getOrderBookData)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/server-reference.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$app$2d$render$2f$encryption$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/app-render/encryption.js [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$flows$2f$generate$2d$trading$2d$signal$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/ai/flows/generate-trading-signal.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/bybit-api.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/indicators.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/build/webpack/loaders/next-flight-loader/action-validate.js [app-rsc] (ecmascript)");
;
;
;
;
;
async function getAiTradingSignal(symbol, timeframe, indicatorSettings) {
    try {
        const result = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$ai$2f$flows$2f$generate$2d$trading$2d$signal$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["generateTradingSignal"])({
            symbol,
            timeframe,
            indicatorSettings
        });
        return {
            success: true,
            analysis: result
        };
    } catch (error) {
        console.error('Error generating AI trading signal:', error);
        const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
        return {
            success: false,
            error: errorMessage
        };
    }
}
async function getMarketData(symbol) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getTicker"])(symbol);
}
async function getOrderBookData(symbol) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getOrderBook"])(symbol);
}
async function getKlineData(symbol, interval) {
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKline"])(symbol, interval);
}
async function getIndicatorData(symbol, timeframe, settings = __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["defaultIndicatorSettings"]) {
    const klineData = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$bybit$2d$api$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getKline"])(symbol, timeframe);
    if (!klineData) return null;
    const reversedKline = [
        ...klineData
    ].reverse();
    const closePrices = reversedKline.map((k)=>parseFloat(k[4]));
    const highPrices = reversedKline.map((k)=>parseFloat(k[2]));
    const lowPrices = reversedKline.map((k)=>parseFloat(k[3]));
    const volumes = reversedKline.map((k)=>parseFloat(k[5]));
    return (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$indicators$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["calculateIndicators"])(closePrices, highPrices, lowPrices, volumes, settings);
}
async function analyzeOrderBook(orderBook) {
    const bids = orderBook.bids.map(([price, size])=>({
            price: parseFloat(price),
            size: parseFloat(size)
        }));
    const asks = orderBook.asks.map(([price, size])=>({
            price: parseFloat(price),
            size: parseFloat(size)
        }));
    // Helper function to find the levels with the largest order sizes
    const findLevels = (orders, count)=>{
        const sorted = [
            ...orders
        ].sort((a, b)=>b.size - a.size);
        return sorted.slice(0, count).map((o)=>o.price);
    };
    const supportLevels = findLevels(bids, 3);
    const resistanceLevels = findLevels(asks, 3);
    return {
        support: supportLevels,
        resistance: resistanceLevels
    };
}
;
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$action$2d$validate$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["ensureServerEntryExports"])([
    getAiTradingSignal,
    getMarketData,
    getOrderBookData,
    getKlineData,
    getIndicatorData,
    analyzeOrderBook
]);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getAiTradingSignal, "70c6125dbbad3595350503c517b30b35b439281e36", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getMarketData, "40ecf96ec3829da1facb2822b20b7b6fb2faedc074", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getOrderBookData, "404bceabf4524442855236b92fdc7049a3e2aa0d9e", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getKlineData, "6075278ac703872d2e66765d6f6dbe7646dd10bb25", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(getIndicatorData, "70901addb4aa828fa13a5df1151b80af96986e9baf", null);
(0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$build$2f$webpack$2f$loaders$2f$next$2d$flight$2d$loader$2f$server$2d$reference$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerServerReference"])(analyzeOrderBook, "40ed26910e6df74305f6af4c2aa1e4f10fbe170c0d", null);
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <locals>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
;
;
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <module evaluation>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <locals>');
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript) <exports>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "70901addb4aa828fa13a5df1151b80af96986e9baf": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getIndicatorData"]),
    "70c6125dbbad3595350503c517b30b35b439281e36": (()=>__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["getAiTradingSignal"])
});
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/actions.ts [app-rsc] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <locals>');
}}),
"[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => \"[project]/src/lib/actions.ts [app-rsc] (ecmascript)\" } [app-rsc] (server actions loader, ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "70901addb4aa828fa13a5df1151b80af96986e9baf": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["70901addb4aa828fa13a5df1151b80af96986e9baf"]),
    "70c6125dbbad3595350503c517b30b35b439281e36": (()=>__TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__["70c6125dbbad3595350503c517b30b35b439281e36"])
});
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <module evaluation>');
var __TURBOPACK__imported__module__$5b$project$5d2f2e$next$2d$internal$2f$server$2f$app$2f$page$2f$actions$2e$js__$7b$__ACTIONS_MODULE0__$3d3e$__$225b$project$5d2f$src$2f$lib$2f$actions$2e$ts__$5b$app$2d$rsc$5d$__$28$ecmascript$2922$__$7d$__$5b$app$2d$rsc$5d$__$28$server__actions__loader$2c$__ecmascript$29$__$3c$exports$3e$__ = __turbopack_context__.i('[project]/.next-internal/server/app/page/actions.js { ACTIONS_MODULE0 => "[project]/src/lib/actions.ts [app-rsc] (ecmascript)" } [app-rsc] (server actions loader, ecmascript) <exports>');
}}),
"[project]/src/app/favicon.ico.mjs { IMAGE => \"[project]/src/app/favicon.ico (static in ecmascript)\" } [app-rsc] (structured image object, ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/favicon.ico.mjs { IMAGE => \"[project]/src/app/favicon.ico (static in ecmascript)\" } [app-rsc] (structured image object, ecmascript)"));
}}),
"[project]/src/app/layout.tsx [app-rsc] (ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/layout.tsx [app-rsc] (ecmascript)"));
}}),
"[project]/src/app/page.tsx (client reference/proxy) <module evaluation>": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "default": (()=>__TURBOPACK__default__export__)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/rsc/react-server-dom-turbopack-server-edge.js [app-rsc] (ecmascript)");
;
const __TURBOPACK__default__export__ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerClientReference"])(function() {
    throw new Error("Attempted to call the default export of [project]/src/app/page.tsx <module evaluation> from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.");
}, "[project]/src/app/page.tsx <module evaluation>", "default");
}}),
"[project]/src/app/page.tsx (client reference/proxy)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.s({
    "default": (()=>__TURBOPACK__default__export__)
});
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/server/route-modules/app-page/vendored/rsc/react-server-dom-turbopack-server-edge.js [app-rsc] (ecmascript)");
;
const __TURBOPACK__default__export__ = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$server$2f$route$2d$modules$2f$app$2d$page$2f$vendored$2f$rsc$2f$react$2d$server$2d$dom$2d$turbopack$2d$server$2d$edge$2e$js__$5b$app$2d$rsc$5d$__$28$ecmascript$29$__["registerClientReference"])(function() {
    throw new Error("Attempted to call the default export of [project]/src/app/page.tsx from the server, but it's on the client. It's not possible to invoke a client function from the server, it can only be rendered as a Component or passed to props of a Client Component.");
}, "[project]/src/app/page.tsx", "default");
}}),
"[project]/src/app/page.tsx [app-rsc] (ecmascript)": ((__turbopack_context__) => {
"use strict";

var { g: global, __dirname } = __turbopack_context__;
{
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__$3c$module__evaluation$3e$__ = __turbopack_context__.i("[project]/src/app/page.tsx (client reference/proxy) <module evaluation>");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__ = __turbopack_context__.i("[project]/src/app/page.tsx (client reference/proxy)");
;
__turbopack_context__.n(__TURBOPACK__imported__module__$5b$project$5d2f$src$2f$app$2f$page$2e$tsx__$28$client__reference$2f$proxy$29$__);
}}),
"[project]/src/app/page.tsx [app-rsc] (ecmascript, Next.js server component)": ((__turbopack_context__) => {

var { g: global, __dirname } = __turbopack_context__;
{
__turbopack_context__.n(__turbopack_context__.i("[project]/src/app/page.tsx [app-rsc] (ecmascript)"));
}}),

};

//# sourceMappingURL=_a5a7f7fb._.js.map