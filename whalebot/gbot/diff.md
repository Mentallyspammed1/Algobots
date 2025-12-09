
[34maimm.cjs ⟶   aimmx.md[0m
[34m────────────────────────────────────────────────────────────────────────────────[0m

[34m────────────────────────────────[0m[34m┐[0m
[34m18[0m:[38;2;255;255;255m const Ajv = require('ajv'); [0m[34m│[0m
[34m────────────────────────────────[0m[34m┘[0m

[38;2;255;255;255mconst VERSION = '3.5.1';[0m

[48;2;63;0;1m// [48;2;144;16;17m───[48;2;63;0;1m 0. CORE SETUP & CONFIGURATION ──────────────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// [48;2;0;96;0m---[48;2;0;40;0m 0. CORE SETUP & CONFIGURATION ──────────────────────────────────────────[0m[48;2;0;40;0m[0K[0m

[38;2;255;255;255mconst logger = winston.createLogger({[0m
[38;2;255;255;255m    level: process.env.LOG_LEVEL || 'info',[0m

[34m────────────────────────────[0m[34m┐[0m
[34m59[0m:[38;2;255;255;255m function loadConfig() { [0m[34m│[0m
[34m────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        symbol: "BTCUSDT", accountType: "UNIFIED",[0m
[38;2;174;129;255m        intervals: { main: "5", scalping: "1" },[0m
[38;2;174;129;255m        risk: { [0m
[48;2;63;0;1m            maxRiskPerTrade: 0.01, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            leverage: 10, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            rewardRatio: 1.5, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            trailingStopMultiplier: 2.0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            zombieTimeMs: 300000, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            zombiePnlTolerance: 0.0015, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            breakEvenTrigger: 1.0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            maxDailyLoss: 10, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            minOrderQty: 0.001, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            partialTakeProfitPct: 0.5, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            rewardRatioTP2: 3.0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            fundingThreshold: 0.0005,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            icebergOffset: 0.0001,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            fee: 0.0005,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            maxHoldingDuration: 7200000 // 2 hours[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            maxRiskPerTrade: 0.01, [48;2;0;96;0mleverage: 10, rewardRatio: 1.5, trailingStopMultiplier: 2.0, [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            zombieTimeMs: 300000, [48;2;0;96;0mzombiePnlTolerance: 0.0015, breakEvenTrigger: 1.0, [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            [48;2;0;96;0mmaxDailyLoss: 10, minOrderQty: 0.001, [48;2;0;40;0mpartialTakeProfitPct: 0.5, [48;2;0;96;0mrewardRatioTP2: 3.0, [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            fundingThreshold: 0.0005,[48;2;0;96;0m icebergOffset: 0.0001, fee: 0.0005, maxHoldingDuration: 7200000[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        },[0m
[38;2;174;129;255m        ai: { model: "gemini-2.5-flash", minConfidence: 0.85 },[0m
[38;2;174;129;255m        indicators: { atr: 14, fisher: 9 }[0m

[34m────────────────[0m[34m┐[0m
[34m175[0m:[38;2;255;255;255m class TA { [0m[34m│[0m
[34m────────────────[0m[34m┘[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m}[0m

[48;2;63;0;1m// ─── 2. LOCAL ORDER BOOK ─────────────────────────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1mclass LocalOrderBook {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    constructor() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.bids = new Map();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.asks = new Map();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.ready = false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.lastUpdate = 0;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    update(data, isSnapshot = false) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (isSnapshot) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.bids.clear();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.asks.clear();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (data.b) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.bids.clear();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                data.b.forEach(([price, size]) => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.bids.set(Number(price), Number(size));[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (data.a) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.asks.clear();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                data.a.forEach(([price, size]) => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.asks.set(Number(price), Number(size));[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.ready = true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.lastUpdate = Date.now();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`OrderBook update error: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    getBestBidAsk() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const bestBid = Math.max(...this.bids.keys());[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const bestAsk = Math.min(...this.asks.keys());[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return { bid: bestBid, ask: bestAsk };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    getAnalysis() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const { bid, ask } = this.getBestBidAsk();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const spread = ask - bid;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const skew = ((bid - ask) / ((bid + ask) / 2)) * 100;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const totalBidVol = Array.from(this.bids.values()).reduce((a, b) => a + b, 0);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const totalAskVol = Array.from(this.asks.values()).reduce((a, b) => a + b, 0);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return { bid, ask, spread, skew, totalBidVol, totalAskVol };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m// ─── [48;2;144;16;17m3[48;2;63;0;1m. DEEP VOID[48;2;144;16;17m (Orderbook[48;2;63;0;1m) ─────────────────────────────────[48;2;144;16;17m───────────────[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// ─── [48;2;0;96;0m2[48;2;0;40;0m. [48;2;0;96;0mORDER BOOK INTELLIGENCE ([48;2;0;40;0mDEEP VOID) ─────────────────────────────────[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255mclass DeepVoidEngine {[0m
[38;2;255;255;255m    constructor() {[0m
[38;2;255;255;255m        this.depth = 25; [0m
[38;2;255;255;255m        this.bids = new Map();[0m
[38;2;255;255;255m        this.asks = new Map();[0m
[48;2;63;0;1m        this.cvd = { cumulative: 0 };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.spoofThreshold = 5.0; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.liquidityVacuumThreshold = 0.3; [0m[48;2;63;0;1m[0K[0m
[38;2;255;255;255m        this.avgDepthHistory = [];[0m
[38;2;255;255;255m        this.spoofAlert = false;[0m
[38;2;255;255;255m        this.isVacuum = false;[0m

[34m────────────────────────────[0m[34m┐[0m
[34m193[0m:[38;2;255;255;255m class DeepVoidEngine { [0m[34m│[0m
[34m────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        this.calculateMetrics();[0m
[38;2;174;129;255m    }[0m

[48;2;63;0;1m    getDepthMetrics() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return this.metrics || {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            totalBidVol: 0, totalAskVol: 0, imbalance: 0, imbalanceRatio: 0,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            strongestBidWall: 0, strongestAskWall: 0, isVacuum: false, spoofAlert: false[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    getDepthMetrics() {[48;2;0;96;0m return this.metrics; }[0m[48;2;0;40;0m[0K[0m

[38;2;174;129;255m    calculateMetrics() {[0m
[38;2;174;129;255m        const bidLevels = Array.from(this.bids.entries()).sort((a, b) => b[0] - a[0]).slice(0, this.depth);[0m

[34m────────────────────────────[0m[34m┐[0m
[34m220[0m:[38;2;255;255;255m class DeepVoidEngine { [0m[34m│[0m
[34m────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        };[0m
[38;2;174;129;255m    }[0m

[48;2;63;0;1m    detectSpoofing() { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.spoofAlert = false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (Math.max(...Array.from(this.asks.values())) > 1000000) this.spoofAlert = true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    [48;2;0;96;0mdetectSpoofing() { /* ... (Simplified[48;2;0;40;0m [48;2;0;96;0mlogic)[48;2;0;40;0m [48;2;0;96;0m...[48;2;0;40;0m [48;2;0;96;0m*/[48;2;0;40;0m this.spoofAlert = false;[48;2;0;96;0m }[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    detectLiquidityVacuum(totalBidVol, totalAskVol) {[0m
[38;2;174;129;255m        this.avgDepthHistory.push((totalBidVol + totalAskVol) / 2);[0m

[34m────────────────────────────[0m[34m┐[0m
[34m232[0m:[38;2;255;255;255m class DeepVoidEngine { [0m[34m│[0m
[34m────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m    getNeonDisplay() { [0m
[38;2;174;129;255m        const m = this.getDepthMetrics();[0m
[38;2;174;129;255m        const skewColor = m.imbalanceRatio > 0.05 ? C.neonGreen : m.imbalanceRatio < -0.05 ? C.neonRed : C.dim;[0m
[48;2;63;0;1m        return `[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m${C.neonPurple}╔══ DEEP VOID ORDERBOOK DOMINION ═══════════════════════════════════╗${C.reset}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m${C.cyan}║ ${C.bright}BID WALL${C.reset} ${m.strongestBidWall.toFixed(1).padStart(8)}  │  ${C.bright}ASK WALL${C.reset} ${m.strongestAskWall.toFixed(1).padStart(8)}${C.reset} ${C.cyan}║${C.reset}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m${C.cyan}║ ${C.bright}LIQUIDITY${C.reset} ${m.totalBidVol.toFixed(1).padStart(6)} / ${m.totalAskVol.toFixed(1).padStart(6)}  │  ${C.bright}IMBALANCE${C.reset} ${skewColor}${ (m.imbalanceRatio*100).toFixed(1)}%${C.reset} ${C.cyan}║${C.reset}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m${C.cyan}║ ${m.isVacuum ? C.neonYellow + 'VACUUM ALERT' : 'Depth Normal'}     │  ${m.spoofAlert ? C.neonRed + 'SPOOF DETECTED' : 'No Spoofing'}     ${C.cyan}║${C.reset}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m${C.neonPurple}╚══════════════════════════════════════════════════════════════════╝${C.reset}`;[0m[48;2;63;0;1m[0K[0m
[48;2;0;96;0;38;2;174;129;255m        return `\n${C.neonPurple}╔══ DEEP VOID ORDERBOOK DOMINION ═══════════════════════════════════╗${C.reset}\n${C.cyan}║ ${C.bright}BID WALL${C.reset} ${m.strongestBidWall.toFixed(1).padStart(8)}  │  ${C.bright}ASK WALL${C.reset} ${m.strongestAskWall.toFixed(1).padStart(8)}${C.reset} ${C.cyan}║${C.reset}\n[48;2;0;40;0m${C.cyan}║ ${C.bright}LIQUIDITY${C.reset} ${m.totalBidVol.toFixed(1).padStart(6)} / ${m.t[0m[48;2;0;40;0motalAskVol.toFixed(1).padStart(6)}  │  ${C.bright}IMBALANCE${C.reset} ${skewColor}${ (m.imbalanceRatio*100).toFixed(1)}%${C.reset} ${C.cyan}║${C.reset}[48;2;0;96;0m\n${C.cyan}║ ${m.isVacuum ? C.neonYellow + 'VACUUM ALERT' : 'Depth Normal'}     │  ${m.spoofAlert ? C.neonRed + 'SPOOF DETECTED' : 'No Spoofing'}     ${C.cyan}║${C.reset}\n${C.neonPurple}╚══════════════════════════════════════════════════════════════════╝${C.reset}`;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m}[0m

[48;2;63;0;1m// ─── 4. [48;2;144;16;17mORDER FLOW INTELLIGENCE ([48;2;63;0;1mTAPE GOD[48;2;144;16;17m)[48;2;63;0;1m ──────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// ─── 4. TAPE GOD[48;2;0;96;0m ENGINE[48;2;0;40;0m ──────────────────────────────────[48;2;0;96;0m────────────────────[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255mclass TapeGodEngine {[0m
[38;2;255;255;255m    constructor() {[0m
[38;2;255;255;255m        this.trades = [];[0m

[34m───────────────────────────[0m[34m┐[0m
[34m263[0m:[38;2;255;255;255m class TapeGodEngine { [0m[34m│[0m
[34m───────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        if (this.trades.length > this.MAX_HISTORY) this.trades.shift();[0m

[38;2;174;129;255m        this.delta.cumulative += trade.delta;[0m
[48;2;63;0;1m[0K[0m
[7;35m        [0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        if (trade.aggressor) {[0m
[38;2;174;129;255m            if (trade.side === 'BUY') this.aggression.buy += size;[0m
[38;2;174;129;255m            else this.aggression.sell += size;[0m

[34m───────────────────────────[0m[34m┐[0m
[34m289[0m:[38;2;255;255;255m class TapeGodEngine { [0m[34m│[0m
[34m───────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        const recent = this.trades.slice(-50);[0m
[38;2;174;129;255m        const buyVol = recent.filter(t => t.side === 'BUY').reduce((a, t) => a + t.size, 0);[0m
[38;2;174;129;255m        const sellVol = recent.filter(t => t.side === 'SELL').reduce((a, t) => a + t.size, 0);[0m
[48;2;63;0;1m        return { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            delta: buyVol - sellVol, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            cumulativeDelta: this.delta.cumulative, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            dom: buyVol > sellVol * 1.1 ? 'BUYERS' : buyVol * 1.1 < sellVol ? 'SELLERS' : 'BALANCED'[48;2;144;16;17m,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            momentum: this.tapeMomentum,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            iceberg: this.icebergAlert,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            diverging: this.isDiverging[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        };[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        [48;2;0;96;0mreturn { delta: buyVol -[48;2;0;40;0m [48;2;0;96;0msellVol,[48;2;0;40;0m [48;2;0;96;0mcumulativeDelta:[48;2;0;40;0m [48;2;0;96;0mthis.delta.cumulative,[48;2;0;40;0m dom: buyVol > sellVol * 1.1 ? 'BUYERS' : buyVol * 1.1 < sellVol ? 'SELLERS' : 'BALANCED'[48;2;0;96;0m };[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m

[38;2;174;129;255m    getNeonTapeDisplay() {[0m
[38;2;174;129;255m        const m = this.getMetrics();[0m
[48;2;0;40;0;38;2;174;129;255m        if (!m) return '';[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        const deltaColor = m.delta > 0 ? C.neonGreen : C.neonRed;[0m
[38;2;174;129;255m        const domColor = m.dom === 'BUYERS' ? C.neonGreen : m.dom === 'SELLERS' ? C.neonRed : C.dim;[0m
[38;2;174;129;255m        const iceColor = this.icebergAlert ? C.neonYellow : C.dim;[0m

[34m──────────────────────────────────────────[0m[34m┐[0m
[34m308[0m:[38;2;255;255;255m ${C.neonPurple}╚════════════════════ [0m[34m│[0m
[34m──────────────────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m}[0m

[48;2;63;0;1m// ─── 5. [48;2;144;16;17mORACLE BRAIN[48;2;63;0;1m ──────────────────────────────────────────[48;2;144;16;17m──────────────[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// ─── 5. [48;2;0;96;0mVOLATILITY CLAMPING ENGINE[48;2;0;40;0m ──────────────────────────────────────────[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255mclass VolatilityClampingEngine {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m    constructor() {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.history = [];[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.REGIME_WINDOW = 48;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.MAX_CLAMP_MULT = 5.5;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.MIN_CLAMP_MULT = 1.2;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.CHOP_THRESHOLD = 0.45;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.VOL_BREAKOUT_MULT = 1.8;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.regime = 'WARMING';[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m    }[0m[48;2;0;40;0m[0K[0m
[7;35m    [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    update(candleContext, bookMetrics, fisher) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const volatility = candleContext.atr || 0.01;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.history.push({ atr: volatility, skew: bookMetrics.skew, fisher: Math.abs(fisher), price: candleContext.price, ts: Date.now() });[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.history.length > 200) this.history.shift();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.determineRegime(avgAtr, volatility);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    }[0m[48;2;0;40;0m[0K[0m
[7;35m    [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    determineRegime(avgAtr, currentAtr) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.history.length < this.REGIME_WINDOW) { this.regime = 'WARMING'; return; }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const volRatio = avgAtr === 0 ? 1 : currentAtr / avgAtr;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const entropy = this.history.reduce((a, c) => a + Math.abs(c.skew) + c.fisher, 0) / this.REGIME_WINDOW;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (volRatio > this.VOL_BREAKOUT_MULT && entropy < this.CHOP_THRESHOLD) this.regime = 'BREAKOUT';[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        else if (entropy > this.CHOP_THRESHOLD) this.regime = 'CHOPPY';[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        else if (volRatio > 1.3) this.regime = 'TRENDING';[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        else this.regime = 'RANGING';[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    getRegime() { return this.regime; }[0m[48;2;0;40;0m[0K[0m
[7;35m    [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    shouldEnter(atr, regime) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (regime === 'CHOPPY') return false;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (regime === 'BREAKOUT') return true;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const avgAtr = this.history.slice(-20).reduce((a, c) => a + c.atr, 0) / 20;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        return (avgAtr > 0 && atr > avgAtr * 1.2);[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    }[0m[48;2;0;40;0m[0K[0m
[7;35m    [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    clamp(signal, price, atr) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const regime = this.getRegime();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const mult = regime === 'BREAKOUT' ? 5.0 : regime === 'CHOPPY' ? 1.5 : 3.0;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const maxDist = D(atr).mul(mult);[0m[48;2;0;40;0m[0K[0m
[7;35m        [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const entry = D(price);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const rawTp = D(signal.tp);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const dir = signal.action === 'BUY' ? 1 : -1;[0m[48;2;0;40;0m[0K[0m
[7;35m        [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const limitTp = entry.plus(maxDist.mul(dir));[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const finalTp = dir === 1 ? D.min(rawTp, limitTp) : D.max(rawTp, limitTp);[0m[48;2;0;40;0m[0K[0m
[7;35m        [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        return { tp: Number(finalTp.toFixed(2)), regime };[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m}[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// ─── 6. ORACLE BRAIN ────────────────────────────────────────────────────────[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255mclass OracleBrain {[0m
[38;2;255;255;255m    constructor() {[0m
[38;2;255;255;255m        this.klines = [];[0m

[34m─────────────────────────[0m[34m┐[0m
[34m385[0m:[38;2;255;255;255m class OracleBrain { [0m[34m│[0m
[34m─────────────────────────[0m[34m┘[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    update(candle) {[0m
[48;2;63;0;1m        const fisher = TA.fisher([candle.high], [candle.low], CONFIG.indicators.fisher || 9);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const fVal = fisher[fisher.length - 1] || Decimal(0);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Store recent price history for analysis[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (this.klines.length [48;2;144;16;17m=== 0[48;2;63;0;1m) [48;2;144;16;17m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.klines.push({ ...candle, fisher: fVal });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.klines.push({ ...candle, fisher: fVal });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (this.klines.length > 200) this.klines.shift();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const fisher = TA.fisher([candle.high], [candle.low], CONFIG.indicators.fisher || 9)[48;2;0;96;0m.slice(-1)[0] || D(0)[48;2;0;40;0m;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.klines.push({ ...candle, fisher: fisher });[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.klines.length [48;2;0;96;0m> 200[48;2;0;40;0m) [48;2;0;96;0mthis.klines.shift();[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[48;2;144;16;17m    [0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    async divine(metrics) {[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (this.gemini && Math.random() > 0.3) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return await this.geminiDivine(metrics);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn(`Gemini divine failed: ${error.message}, falling back to heuristic`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return this.heuristicDivine(metrics);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async geminiDivine(metrics) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const model = this.gemini.getGenerativeModel({ [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            model: CONFIG.ai.model,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            generationConfig: { temperature: 0.1, topK: 40, topP: 0.95, maxOutputTokens: 200 }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const prompt = this.buildPrompt(metrics);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const result = await model.generateContent(prompt);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const response = await result.response;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const text = response.text();[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.klines.length < 50) return { action: 'HOLD', confidence: 0 };[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[48;2;0;40;0;38;2;174;129;255m        const last = this.klines[this.klines.length-1];[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const atr = TA.atr([last.high], [last.low], [last.close], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const fisher = last?.fisher?.toNumber() || 0;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const vwap = TA.vwap(this.klines.map(k=>k.high), this.klines.map(k=>k.low), this.klines.map(k=>k.close), this.klines.map(k=>k.volume));[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const prompt = `... (Prompt based on ATR, Fisher, Skew, VWAP) ...`;[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        try {[0m
[48;2;63;0;1m            // Try to parse JSON response[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const jsonMatch = [48;2;144;16;17mtext[48;2;63;0;1m.match(/\{[\s\S]*\}/);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (jsonMatch) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                const signal = JSON.parse(jsonMatch[0]);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return this.validateSignal(signal, metrics);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (this.gemini && Math.random() > 0.3) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const model = this.gemini.getGenerativeModel({ model: CONFIG.ai.model, generationConfig: { responseMimeType: 'application/json', temperature: 0.1 } });[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const result = await model.generateContent(prompt);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const responseText = String(await result.response.text()).trim();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            [48;2;0;96;0m    [48;2;0;40;0mconst jsonMatch = [48;2;0;96;0mresponseText[48;2;0;40;0m.match(/\{[\s\S]*\}/);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            [48;2;0;96;0m    [48;2;0;40;0mif (jsonMatch) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                [48;2;0;96;0m    [48;2;0;40;0mconst signal = JSON.parse(jsonMatch[0]);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                [48;2;0;96;0m    [48;2;0;40;0mreturn this.validateSignal(signal, metrics[48;2;0;96;0m, last.close.toNumber(), atr.toNumber()[48;2;0;40;0m);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m            }[0m
[48;2;63;0;1m        } catch ([48;2;144;16;17merror[48;2;63;0;1m) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn(`Gemini [48;2;144;16;17mresponse parsing[48;2;63;0;1m failed: ${[48;2;144;16;17merror[48;2;63;0;1m.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        } catch ([48;2;0;96;0me[48;2;0;40;0m) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            logger.warn(`Gemini [48;2;0;96;0minteraction[48;2;0;40;0m failed: ${[48;2;0;96;0me[48;2;0;40;0m.message}`);[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        // Fallback to heuristic if JSON parsing fails[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return this.heuristicDivine(metrics);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        return this.heuristicDivine(metrics[48;2;0;96;0m, last, atr.toNumber()[48;2;0;40;0m);[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[48;2;63;0;1m    buildPrompt(metrics) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const last = this.klines[this.klines.length - 1];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const price = last?.close?.toNumber() || 0;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const fisher = last?.fisher?.toNumber() || 0;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const atr = last?.atr?.toNumber() || 0;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return `You are an elite crypto trading oracle. Analyze the following market data and return ONLY a JSON object:[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1mMarket Data:[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Price: ${price}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Fisher Transform: ${fisher}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Order Book Skew: ${metrics.skew}%[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Bid/Ask Spread: ${metrics.spread}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- RSI would be calculated from recent price action[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1mTrading Rules:[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- ONLY return a BUY, SELL, or HOLD signal[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Use Fisher transform for momentum (above 0.5 = bullish, below -0.5 = bearish)[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Consider order book imbalance for confirmation[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m- Risk per trade: ${CONFIG.risk.maxRiskPerTrade * 100}%[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1mReturn JSON format:[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m  "action": "BUY|SELL|HOLD",[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m  "confidence": 0.0-1.0,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m  "sl": stop_loss_price,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m  "tp": take_profit_price,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m  "reason": "brief explanation"[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m}`;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    validateSignal(signal, metrics) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (!signal.action || !['BUY', 'SELL', 'HOLD'].includes(signal.action)) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            signal.action = 'HOLD';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if ([48;2;144;16;17msignal[48;2;63;0;1m.confidence < CONFIG.ai.minConfidence) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            signal.action = 'HOLD';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            signal.reason = 'Below confidence threshold';[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    validateSignal(sig, metrics, price, atr) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const valid = ajv.compile(llmSignalSchema)(sig);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if ([48;2;0;96;0m!valid || sig[48;2;0;40;0m.confidence < CONFIG.ai.minConfidence) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            return { action: 'HOLD', confidence: 0, reason: 'Validation/Confidence fail' };[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m
[48;2;144;16;17m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const last = this.klines[this.klines.length - 1];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if ([48;2;144;16;17mlast[48;2;63;0;1m) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const price = last.close.toNumber();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const atr = last.atr.toNumber();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            // Set default SL/TP if not provided[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (!signal.sl || !signal.tp) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                const slDistance = atr * 1.5;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                const tpDistance = atr * (CONFIG.risk.rewardRatio || 1.5);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                if (signal.action === 'BUY') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    signal.sl = signal.sl || price - slDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    signal.tp = signal.tp || price + tpDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                } else if (signal.action === 'SELL') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    signal.sl = signal.sl || price + slDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    signal.tp = signal.tp || price - tpDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const priceD = D(price);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const sl = D(sig.sl);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const tp = D(sig.tp);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const rrTarget = D(CONFIG.risk.rewardRatio || 1.5);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const risk = sig.action === 'BUY' ? priceD.minus(sl) : sl.minus(priceD);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const reward = sig.action === 'BUY' ? tp.minus(priceD) : priceD.minus(tp);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const rr = risk.gt(0) ? reward.div(risk) : D(0);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if ([48;2;0;96;0mrr.lt(rrTarget)[48;2;0;40;0m) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            const newTp = sig.action === 'BUY' ? priceD.plus(risk.mul(rrTarget)) : priceD.minus(risk.mul(rrTarget));[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            sig.tp = Number(newTp.toFixed(2));[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            sig.reason = (sig.reason || '') + ' | R/R enforced';[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        return [48;2;144;16;17msignal[48;2;63;0;1m;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        return [48;2;0;96;0msig[48;2;0;40;0m;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[48;2;63;0;1m    heuristicDivine(metrics) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const last = this.klines[this.klines.length - 1];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (!last) return { action: 'HOLD', confidence: 0, sl: 0, tp: 0, reason: 'No data' };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const price = last.close.toNumber();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const fisher = last.fisher.toNumber();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const atr = last.atr.toNumber();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    heuristicDivine(metrics[48;2;0;96;0m, last, atr[48;2;0;40;0m) {[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        let action = 'HOLD';[0m
[48;2;63;0;1m        let confidence = 0;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        let confidence = 0[48;2;0;96;0m.6[48;2;0;40;0m;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        // Fisher Transform analysis[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (fisher > 0.5) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            action = 'BUY';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            confidence = 0.7;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m} [48;2;63;0;1melse if (fisher < -0.5) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            action = 'SELL';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            confidence = 0.7;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Order book confirmation[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (metrics.skew > 0.5 && action === 'HOLD') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            action = 'BUY';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            confidence = 0.6;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else if (metrics.skew < -0.5 && action === 'HOLD') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            action = 'SELL';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            confidence = 0.6;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Adjust confidence based on spread[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (metrics.spread < 0.5) confidence += 0.1;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const fisher = last.fisher.toNumber();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const skew = metrics.skew;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (fisher > 0.5[48;2;0;96;0m && skew > 0.05[48;2;0;40;0m) {[48;2;0;96;0m action = 'BUY'; confidence = 0.75; }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        else if (fisher < -0.5[48;2;0;96;0m && skew < -0.05[48;2;0;40;0m) {[48;2;0;96;0m action = 'SELL'; confidence = 0.75; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        confidence = Math.min(confidence, 0.95);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (action === 'HOLD' && metrics.wallStatus === 'ASK_WALL_BROKEN') { action = 'BUY'; confidence = 0.85; }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (action === 'HOLD' && metrics.wallStatus === 'BID_WALL_BROKEN') { action = 'SELL'; confidence = 0.85; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[48;2;0;40;0;38;2;174;129;255m        if (action === 'HOLD') return { action: 'HOLD', confidence: 0 };[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        const slDistance = atr * 1.5;[0m
[48;2;63;0;1m        const tpDistance = atr * [48;2;144;16;17m([48;2;63;0;1mCONFIG.risk.rewardRatio[48;2;144;16;17m || 1.5)[48;2;63;0;1m;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const tpDistance = atr * CONFIG.risk.rewardRatio;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[38;2;174;129;255m        let sl = 0, tp = 0;[0m
[38;2;174;129;255m        if (action === 'BUY') {[0m
[38;2;174;129;255m            sl = price - slDistance;[0m
[38;2;174;129;255m            tp = price + tpDistance;[0m
[48;2;63;0;1m        } else if (action === 'SELL') {[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        } else {[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m            sl = price + slDistance;[0m
[38;2;174;129;255m            tp = price - tpDistance;[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m        [0m
[38;2;174;129;255m        return {[0m
[48;2;63;0;1m            action,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            confidence,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            sl,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            tp,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            reason: `[48;2;144;16;17mFisher[48;2;63;0;1m: ${fisher.toFixed([48;2;144;16;17m3[48;2;63;0;1m)}[48;2;144;16;17m,[48;2;63;0;1m Skew:[48;2;144;16;17m [48;2;63;0;1m${[48;2;144;16;17mmetrics.[48;2;63;0;1mskew.toFixed(2)}[48;2;144;16;17m%[48;2;63;0;1m`[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            action, confidence: Math.min(confidence, 0.95), sl, tp,[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            reason: `[48;2;0;96;0mHeuristic[48;2;0;40;0m: [48;2;0;96;0mF:[48;2;0;40;0m${fisher.toFixed([48;2;0;96;0m2[48;2;0;40;0m)} Skew:${skew.toFixed(2)}`[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        };[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m}[0m

[48;2;63;0;1m// ─── 6. VOLATILITY CLAMPING ENGINE ──────────────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1mclass VolatilityClampingEngine {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    constructor() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.regime = 'WARMING';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.volatilityHistory = [];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.maxHistory = 50;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.thresholds = {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            HIGH_VOL: 1.5,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            LOW_VOL: 0.5,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            NEUTRAL: 1.0[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    update(candle, metrics, fisherVal) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Update volatility history[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const volatility = candle.atr ? candle.atr.toNumber() : 0.01;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.volatilityHistory.push(volatility);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (this.volatilityHistory.length > this.maxHistory) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.volatilityHistory.shift();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Calculate average volatility[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const avgVol = this.volatilityHistory.reduce((a, b) => a + b, 0) / this.volatilityHistory.length;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const volRatio = avgVol > 0 ? volatility / avgVol : 1;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Determine regime[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (volRatio > this.thresholds.HIGH_VOL) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.regime = 'HIGH_VOL';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else if (volRatio < this.thresholds.LOW_VOL) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.regime = 'LOW_VOL';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.regime = 'NEUTRAL';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Additional regime adjustments based on Fisher and metrics[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (Math.abs(fisherVal) > 0.8) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.regime = 'TRENDING';[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    getRegime() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return this.regime;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    shouldEnter(atr, regime) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Don't enter in extremely high volatility unless signal is very strong[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (regime === 'HIGH_VOL') return false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    clamp(signal, price, atr) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const clamped = { ...signal };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const maxDistance = atr * (CONFIG.risk.atr_tp_limit || 3.5);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (signal.action === 'BUY') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const maxTp = price + maxDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (signal.tp > maxTp) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                clamped.tp = maxTp;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                clamped.regime = this.regime;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else if (signal.action === 'SELL') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const minTp = price - maxDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (signal.tp < minTp) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                clamped.tp = minTp;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                clamped.regime = this.regime;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return clamped;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m// ─── 7. BYBIT MASTER API WRAPPER ────────────────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1mclass BybitMaster {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    constructor(client, symbol, category = 'linear') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.client = client;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.symbol = symbol;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.category = category;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.cache = { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            balance: { value: 0, equity: 0, ts: 0 }, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            position: { size: 0, side: null, entry: 0, ts: 0, tp: 0 } [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async sync() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (Date.now() - this.cache.balance.ts < 8000) { /* Skip balance sync if recent */ } [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        else { await this.fetchBalance(); }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        await this.fetchPosition();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async fetchBalance() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const res = await this.client.getWalletBalance({ accountType: CONFIG.accountType });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (res.retCode !== 0 || !res.result?.list?.[0]) throw new Error('API error or no list');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const usdt = res.result.list[0].coin.find(c => c.coin === 'USDT');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const available = parseFloat(usdt.availableToWithdraw || usdt.walletBalance || '0');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const equity = parseFloat(usdt.equity || available);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.cache.balance = { value: available, equity, ts: Date.now() };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.info(`[BALANCE] Synced: $${available.toFixed(2)}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (e) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn(`[BALANCE] Sync failed: ${e.message}`); [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            // Set default values for testing[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.cache.balance = { value: 10000, equity: 10000, ts: Date.now() };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async fetchPosition() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const res = await this.client.getPositionInfo({ category: this.category, symbol: this.symbol });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (res.retCode !== 0 || !res.result?.list?.[0]) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const pos = res.result.list[0];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const size = parseFloat(pos.size || '0');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const side = size > 0 ? (pos.side === 'Buy' ? 'BUY' : 'SELL') : null;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.cache.position = { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                size, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                side, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                entry: parseFloat(pos.avgPrice || '0'), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                leverage: parseFloat(pos.leverage || '10'), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                ts: Date.now(),[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                tp: parseFloat(pos.takeProfit || '0')[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (e) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`[POSITION] Fetch failed: ${e.message}`); [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async getPosition() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        await this.fetchPosition();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return this.cache.position;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async placeLimitOrder({ side, price, qty, reduceOnly = false, isIceberg = false, icebergSlices = 1 }) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const qtyD = D(qty);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (isIceberg && icebergSlices > 1) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const slices = icebergSlices;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const sliceQty = qtyD.div(slices).toFixed(3);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const offsetMultiplier = CONFIG.risk.icebergOffset || price * 0.0001; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.info(`[ICEBERG] Splitting ${qty} into ${slices} slices.`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                for (let i = 0; i < slices; i++) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const offset = i * offsetMultiplier;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const slicePrice = side === 'BUY' ? price + offset : price - offset;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const order = await this.client.submitOrder({[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        category: this.category, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        symbol: this.symbol, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        side: side === 'BUY' ? 'Buy' : 'Sell',[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        orderType: 'Limit', [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        qty: sliceQty, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        price: slicePrice.toFixed(2),[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        timeInForce: 'PostOnly', [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        reduceOnly, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        positionIdx: 0[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    if (order.retCode !== 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        throw new Error(order.retMsg);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    await new Promise(r => setTimeout(r, 250));[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.success(`[ICEBERG] ${slices} slices placed.`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.error(`[ICEBERG] Failed: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                const order = await this.client.submitOrder({[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    category: this.category, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    symbol: this.symbol, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    side: side === 'BUY' ? 'Buy' : 'Sell',[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    orderType: 'Limit', [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    qty: qty.toString(), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    price: price.toFixed(2),[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    timeInForce: 'PostOnly', [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    reduceOnly, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    positionIdx: 0[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                if (order.retCode === 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    logger.success(`[ORDER] ${side} ${qty} @ ${price} POST-ONLY SUCCESS`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    return order.result.orderId;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    throw new Error(order.retMsg);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            } catch (e) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.error(`[ORDER FAILED] ${side} limit order: ${e.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return null;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async closePositionMarket() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const pos = await this.getPosition();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (pos.size === 0) return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const order = await this.client.submitOrder({[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                category: this.category, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                symbol: this.symbol, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                side: pos.side === 'BUY' ? 'Sell' : 'Buy',[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                orderType: 'Market', [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                qty: pos.size.toString(), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                reduceOnly: true, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                timeInForce: 'IOC'[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (order.retCode === 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.success(`[CLOSED] ${pos.side} ${pos.size} @ MARKET`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                this.cache.position = { size: 0, side: null, entry: 0, ts: Date.now(), tp: 0 };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                throw new Error(order.retMsg);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (e) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`[CLOSE FAILED] ${e.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m

[48;2;63;0;1m    async setTradingStop(sl = null, tp = null) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const params = { category: this.category, symbol: this.symbol, positionIdx: 0 };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (sl) params.stopLoss = sl.toFixed(2);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (tp) params.takeProfit = tp.toFixed(2);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const res = await this.client.setTradingStop(params);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (res.retCode === 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.info(`[STOP] SL: ${sl?.toFixed(2) || '—'} | TP: ${tp?.toFixed(2) || '—'}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            throw new Error(res.retMsg);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (e) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`[STOP ERROR] ${e.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    async cancelAllOrders() {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const res = await this.client.cancelAllOrders({[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                category: this.category,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                symbol: this.symbol[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (res.retCode === 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.info('[CANCEL] All orders cancelled');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                return true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            throw new Error(res.retMsg);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (e) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`[CANCEL FAILED] ${e.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m// ─── [48;2;144;16;17m8[48;2;63;0;1m. LEVIATHAN ENGINE [48;2;144;16;17m────────────────[48;2;63;0;1m──────────────────────────────────────[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;255;255;255m// ─── [48;2;0;96;0m6[48;2;0;40;0m. LEVIATHAN ENGINE [48;2;0;96;0m(Orchestrator) [48;2;0;40;0m──────────────────────────────────────[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255mclass LeviathanEngine {[0m
[38;2;255;255;255m    constructor() {[0m
[48;2;63;0;1m        this.client = new RestClientV5({ [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            key: process.env.BYBIT_API_KEY, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            secret: process.env.BYBIT_API_SECRET [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        this.ws = new WebsocketClient({ [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            key: process.env.BYBIT_API_KEY, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            secret: process.env.BYBIT_API_SECRET, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            market: 'v5' [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        });[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        this.client = new RestClientV5({ [48;2;0;96;0mkey: process.env.BYBIT_API_KEY, secret: process.env.BYBIT_API_SECRET });[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;255;255;255m        [48;2;0;96;0mthis.ws[48;2;0;40;0m [48;2;0;96;0m=[48;2;0;40;0m [48;2;0;96;0mnew[48;2;0;40;0m [48;2;0;96;0mWebsocketClient({[48;2;0;40;0m key: process.env.BYBIT_API_KEY, [48;2;0;96;0msecret: process.env.BYBIT_API_SECRET, market: 'v5' });[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255m        [0m
[38;2;174;129;255m        this.master = new BybitMaster(this.client, CONFIG.symbol);[0m
[38;2;174;129;255m        this.book = new LocalOrderBook();[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m490[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        this.vol = new VolatilityClampingEngine();[0m
[38;2;174;129;255m        this.deepVoid = new DeepVoidEngine();[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        this.state = { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            price: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            lastUiUpdate: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            pnl: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            equity: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            availableBalance: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            maxEquity: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            paused: false,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            consecutiveLosses: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            stats: { trades: 0, wins: 0, totalPnl: 0 },[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            position: { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                active: false, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                side: null, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                entryPrice: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                currentSl: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                entryTime: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                isBreakEven: false, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                originalSl: D0(),[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                tp: 0[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            },[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            currentVwap: 0, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            regime: 'WARMING',[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            bestBid: 0,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            bestAsk: 0[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.state = { price: 0, lastUiUpdate: 0, pnl: 0, equity: 0, availableBalance: 0, maxEquity: 0, paused: false,[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            consecutiveLosses: 0, [48;2;0;96;0mstats: { trades: 0, wins: 0, totalPnl: 0 },[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            position: { active: false, side: null, entryPrice: 0, currentSl: 0, entryTime: 0, isBreakEven: false, originalSl: D0(), tp: 0 },[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            currentVwap: 0, [48;2;0;96;0mregime: 'WARMING'[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        };[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        this.isRunning = false;[0m
[38;2;174;129;255m    }[0m


[34m─────────────────────────────[0m[34m┐[0m
[34m502[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        await this.master.sync();[0m
[38;2;174;129;255m        this.state.equity = this.master.cache.balance.equity;[0m
[38;2;174;129;255m        this.state.availableBalance = this.master.cache.balance.value;[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Update max equity for drawdown calculation[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (this.state.equity > this.state.maxEquity) [48;2;144;16;17m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.state.maxEquity = this.state.equity;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.state.equity > this.state.maxEquity) [48;2;0;96;0mthis.state.maxEquity = this.state.equity;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m

[38;2;174;129;255m    async warmUp() {[0m
[48;2;63;0;1m        await this.[48;2;144;16;17mrefreshEquity[48;2;63;0;1m();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        logger.info(`[INIT] Equity Sync Complete: $${this.state.equity.toFixed(2)}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Cancel any existing orders[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        await this.[48;2;0;96;0mmaster.sync[48;2;0;40;0m();[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        await this.master.cancelAllOrders();[0m
[48;2;0;40;0;38;2;174;129;255m        logger.info(`[INIT] Ready.`);[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m

[38;2;174;129;255m    updateOrderbook(data) {[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m529[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    displayLiveStatus() {[0m
[48;2;63;0;1m        if (Date.now() - this.state.lastUiUpdate < [48;2;144;16;17m200[48;2;63;0;1m) return; // UI DEBOUNCER[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (Date.now() - this.state.lastUiUpdate < [48;2;0;96;0m100[48;2;0;40;0m) return; // UI DEBOUNCER[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        this.state.lastUiUpdate = Date.now();[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        console.clear();[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        process.stdout.write('\x1b[12A');[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        console.log(this.tape.getNeonTapeDisplay());[0m
[38;2;174;129;255m        console.log(this.deepVoid.getNeonDisplay());[0m
[38;2;174;129;255m    }[0m

[48;2;63;0;1m    async calculateRiskSize(signal) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const balance = this.state.availableBalance || 10000; // Default for testing[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const riskAmount = balance * CONFIG.risk.maxRiskPerTrade;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const entry = signal.action === 'BUY' ? this.state.bestAsk : this.state.bestBid;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const slDistance = Math.abs(entry - signal.sl);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            if (slDistance === 0) return 0;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            let qty = riskAmount / slDistance;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            qty = Math.max(qty, CONFIG.risk.minOrderQty);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            // Apply leverage[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            const leveragedQty = qty * (CONFIG.risk.leverage || 10);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return leveragedQty;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`Risk size calculation failed: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return CONFIG.risk.minOrderQty;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[38;2;174;129;255m    async processCandleSignal(k, metrics, fisherVal) {[0m
[38;2;174;129;255m        const atr = TA.atr([D(k.high)], [D(k.low)], [D(k.close)], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1);[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        this.vol.update({ [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            close: D(k.close), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            atr: atr.toNumber(), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            price: parseFloat(k.close) [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }, metrics, fisherVal);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        [48;2;0;96;0mthis.vol.update({ close:[48;2;0;40;0m [48;2;0;96;0mD(k.close),[48;2;0;40;0m [48;2;0;96;0matr:[48;2;0;40;0m [48;2;0;96;0matr.toNumber(),[48;2;0;40;0m price: parseFloat(k.close) [48;2;0;96;0m}, metrics, fisherVal);[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        this.state.regime = this.vol.getRegime();[0m
[38;2;174;129;255m        [0m
[38;2;174;129;255m        const signal = await this.oracle.divine(metrics);[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m565[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m

[38;2;174;129;255m    async placeMakerOrder(signal) {[0m
[38;2;174;129;255m        const qty = await this.calculateRiskSize(signal);[0m
[48;2;0;40;0;38;2;174;129;255m        const price = signal.action === 'BUY' ? this.state.bestAsk : this.state.bestAsk;[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (qty < parseFloat(CONFIG.risk.minOrderQty || '0.001')) return;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        [0m
[48;2;63;0;1m        if (qty < parseFloat(CONFIG.risk.minOrderQty || '0.001')) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn('[RISK] Position size below minimum – aborting');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // Fixed price selection logic[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const price = signal.action === 'BUY' ? this.state.bestAsk : this.state.bestBid;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        logger.info(`[ORDER] ${signal.action} ${qty} @ ${price} (Risk: ${(CONFIG.risk.maxRiskPerTrade * 100).toFixed(2)}%)`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        // V3.5.1: Use Iceberg execution path[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17mconst orderSuccess = [48;2;63;0;1mawait this.master.placeLimitOrder({[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        await this.master.placeLimitOrder({[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m            side: signal.action,[0m
[38;2;174;129;255m            price: price,[0m
[38;2;174;129;255m            qty: qty,[0m
[38;2;174;129;255m            isIceberg: true,[0m
[48;2;63;0;1m            icebergSlices: 3 [48;2;144;16;17m// Default 3 slices[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            icebergSlices: 3[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        });[0m

[48;2;63;0;1m        if (orderSuccess) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            // Set initial stops immediately[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m    [48;2;63;0;1mawait this.master.setTradingStop(signal.sl, signal.tp);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.state.position = {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                active: true, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                side: signal.action, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                entryPrice: price, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                currentSl: signal.sl, [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                originalSl: D(signal.sl), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                entryTime: Date.now(), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                isBreakEven: false,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                tp: signal.tp[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            };[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.success(`[POSITION] ${signal.action} entered at ${price}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error('[ORDER] Failed to place iceberg order');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m    }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        await this.master.setTradingStop(signal.sl, signal.tp);[0m[48;2;0;40;0m[0K[0m

[48;2;63;0;1m    async closePosition(reason = 'MANUAL') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        const success = await this.master.closePositionMarket();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (success) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m    [48;2;63;0;1mthis.state.position[48;2;144;16;17m.active[48;2;63;0;1m = [48;2;144;16;17mfalse;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn(`[EXIT] Position closed: ${reason}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        return success;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.state.position = [48;2;0;96;0m{[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            active: true, side: signal.action, entryPrice: price, [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            currentSl: signal.sl, originalSl: D(signal.sl), entryTime: Date.now(), isBreakEven: false,[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            tp: signal.tp[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        }[48;2;0;96;0m;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    async closePosition(reason = 'MANUAL') { await this.master.closePositionMarket(); this.state.position.active = false; }[0m[48;2;0;40;0m[0K[0m
[38;2;255;255;255m    [0m
[48;2;0;40;0;38;2;174;129;255m    // --- EXIT LOGIC (FULLY ADVANCED) ---[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    async updateTrailingStop() {[0m
[38;2;174;129;255m        if (!this.state.position.active) return;[0m
[38;2;174;129;255m        const { side, currentSl } = this.state.position;[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m602[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m

[38;2;174;129;255m        if (side === 'BUY') {[0m
[38;2;174;129;255m            const potentialSl = D(currentPrice).minus(trailDist);[0m
[48;2;63;0;1m            if (potentialSl.gt(newSl)) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                newSl = potentialSl; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                updated = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (potentialSl.gt(newSl)) { [48;2;0;96;0mnewSl = potentialSl; updated = true; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        } else { // SELL[0m
[38;2;174;129;255m            const potentialSl = D(currentPrice).plus(trailDist);[0m
[48;2;63;0;1m            if (potentialSl.lt(newSl)) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                newSl = potentialSl; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                updated = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (potentialSl.lt(newSl)) { [48;2;0;96;0mnewSl = potentialSl; updated = true; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m

[38;2;174;129;255m        if (updated) {[0m
[38;2;174;129;255m            this.state.position.currentSl = newSl.toNumber();[0m
[38;2;174;129;255m            await this.master.setTradingStop(newSl.toNumber(), this.state.position.tp);[0m
[48;2;63;0;1m            logger.info(`[TRAIL] Stop moved to ${newSl.toFixed(2)}`);[0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    async checkVwapExit() {[0m
[48;2;63;0;1m        // Simple VWAP exit - exit if price moves 2% against position[0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        if (!this.state.position.active) return;[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        const { side, entryPrice } = this.state.position;[0m
[38;2;174;129;255m        const priceChange = (this.state.price - entryPrice) / entryPrice;[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        if (side === 'BUY' && priceChange < -0.02) [48;2;144;16;17m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            await this.closePosition('[48;2;144;16;17mVWAP_EXIT_BUY[48;2;63;0;1m');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } else if (side === 'SELL' && priceChange > 0.02) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            await this.closePosition('VWAP_EXIT_SELL');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (side === 'BUY' && priceChange < -0.02) [48;2;0;96;0mawait this.closePosition('VWAP_EXIT_BUY');[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        [48;2;0;96;0melse if (side === 'SELL' &&[48;2;0;40;0m [48;2;0;96;0mpriceChange[48;2;0;40;0m [48;2;0;96;0m>[48;2;0;40;0m [48;2;0;96;0m0.02)[48;2;0;40;0m await this.closePosition('[48;2;0;96;0mVWAP_EXIT_SELL[48;2;0;40;0m');[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    async checkTimeStop() {[0m
[38;2;174;129;255m        if (!this.state.position.active) return;[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        const elapsed = Date.now() - this.state.position.entryTime;[0m
[48;2;63;0;1m        const maxHoldingDuration = CONFIG.risk?.maxHoldingDuration || 7200000; [48;2;144;16;17m// 2 hours[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        const maxHoldingDuration = CONFIG.risk?.maxHoldingDuration || 7200000;[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        if (elapsed > maxHoldingDuration) {[0m
[48;2;63;0;1m            await this.closePosition('[48;2;144;16;17mTIME_STOP[48;2;63;0;1m');[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            await this.closePosition('[48;2;0;96;0mTIME_LIMIT[48;2;0;40;0m');[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    async checkExitConditions() {[0m
[38;2;174;129;255m        if (!this.state.position.active) return;[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m        await this.updateTrailingStop();[0m
[38;2;174;129;255m        await this.checkVwapExit();[0m
[38;2;174;129;255m        await this.checkTimeStop();[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m682[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m            }[0m
[38;2;174;129;255m            [0m
[38;2;174;129;255m            if (side === 'BUY') {[0m
[48;2;63;0;1m                if (currentPrice <= currentSl) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exit = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exitReason = 'SL_HIT'; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                else if (currentPrice >= this.state.position.tp) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exit = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exitReason = 'TP_HIT'; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                if (currentPrice <= currentSl) { [48;2;0;96;0mexit = true; exitReason = 'SL_HIT'; }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                else if (currentPrice >= this.state.position.tp) { [48;2;0;96;0mexit = true; exitReason = 'TP_HIT'; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m            } else {[0m
[48;2;63;0;1m                if (currentPrice >= currentSl) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exit = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exitReason = 'SL_HIT'; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                else if (currentPrice <= this.state.position.tp) { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exit = true; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    exitReason = 'TP_HIT'; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                if (currentPrice >= currentSl) { [48;2;0;96;0mexit = true; exitReason = 'SL_HIT'; }[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                else if (currentPrice <= this.state.position.tp) { [48;2;0;96;0mexit = true; exitReason = 'TP_HIT'; }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m            }[0m
[38;2;174;129;255m        }[0m

[38;2;174;129;255m        // 4. ORACLE FLIP CHECK[0m
[38;2;174;129;255m        const signal = await this.oracle.divine(this.book.getAnalysis());[0m
[38;2;174;129;255m        if (!exit && signal.action !== 'HOLD' && signal.action !== side) {[0m
[48;2;63;0;1m            exit = true;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            exitReason = `ORACLE_FLIP_${signal.action}`;[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            [48;2;0;96;0m [48;2;0;40;0mexit = true;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            [48;2;0;96;0m [48;2;0;40;0mexitReason = `ORACLE_FLIP_${signal.action}`;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m        [0m
[38;2;174;129;255m        if (exit) {[0m
[48;2;63;0;1m            logger.warn(`[EXIT] ${exitReason} triggered.`);[0m[48;2;63;0;1m[0K[0m
[38;2;174;129;255m            await this.closePosition(exitReason);[0m
[38;2;174;129;255m        }[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m    [0m
[38;2;174;129;255m    async start() {[0m
[48;2;63;0;1m        if (this.isRunning) [48;2;144;16;17m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn('Leviathan is already running');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            return;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        if (this.isRunning) [48;2;0;96;0mreturn;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        this.isRunning = true;[0m
[38;2;174;129;255m        await this.warmUp();[0m

[48;2;63;0;1m        try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m    [48;2;63;0;1mthis.ws.subscribeV5([[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [48;2;144;16;17m    [48;2;63;0;1m`kline.${CONFIG.intervals.main}.${CONFIG.symbol}`,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [48;2;144;16;17m    [48;2;63;0;1m`orderbook.50.${CONFIG.symbol}`,[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [48;2;144;16;17m    [48;2;63;0;1m`execution.${CONFIG.symbol}`[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m    [48;2;63;0;1m], 'linear');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        [48;2;144;16;17m    [48;2;63;0;1mthis.ws.subscribeV5(['position'], 'private');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`WebSocket subscription failed: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.ws.subscribeV5([[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            `kline.${CONFIG.intervals.main}.${CONFIG.symbol}`,[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            `orderbook.50.${CONFIG.symbol}`,[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            `execution.${CONFIG.symbol}`[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        ], 'linear');[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.ws.subscribeV5(['position'], 'private');[0m[48;2;0;40;0m[0K[0m

[48;2;63;0;1m        // Periodic tasks[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        setInterval(() => this.refreshEquity(), 300000); [48;2;144;16;17m// 5 minutes[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        setInterval(() => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            // Update stats[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            this.state.stats.trades = (this.state.stats.trades || 0) + 1;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.info(`[STATS] Trades: ${this.state.stats.trades}, Equity: $${this.state.equity.toFixed(2)}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        }, 600000); // 10 minutes[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        setInterval(() => this.refreshEquity(), 300000);[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        setInterval(() => {[48;2;0;96;0m /* Stats logging */ }, 600000);[0m[48;2;0;40;0m[0K[0m

[38;2;174;129;255m        this.ws.on('update', async (data) => {[0m
[38;2;174;129;255m            if (!data?.data || !data.topic) return;[0m
[38;2;174;129;255m            [0m
[48;2;63;0;1m            try {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [48;2;144;16;17m    [48;2;63;0;1mif (data.topic === 'execution') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                [48;2;144;16;17m   [48;2;63;0;1m [48;2;144;16;17mif ([48;2;63;0;1mArray.isArray(data.data)[48;2;144;16;17m)[48;2;63;0;1m [48;2;144;16;17m{[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        data.data.forEach(exec => this.tape.processExecution(exec));[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            [48;2;144;16;17m        [48;2;63;0;1m}[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (data.topic === 'execution') {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                data.data.forEach(exec => this.tape.processExecution(exec));[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            }[0m[48;2;0;40;0m[0K[0m
[7;35m            [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (data.topic?.startsWith('orderbook')) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                [48;2;0;96;0mconst frame[48;2;0;40;0m [48;2;0;96;0m= [48;2;0;40;0mArray.isArray(data.data) [48;2;0;96;0m? data.data[0] : data.data;[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const type = data.type ? data.type : (this.book.ready ? 'delta' : 'snapshot');[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                this.updateOrderbook({ type, b: frame.b, a: frame.a });[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            }[0m[48;2;0;40;0m[0K[0m
[7;35m            [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            if (data.topic?.includes(`kline.${CONFIG.intervals.main}.`)) {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const k = data.data[0];[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                if (!k.confirm) return;[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m                [0m
[48;2;63;0;1m                if (data.topic?.startsWith('orderbook')) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const frame = Array.isArray(data.data) ? data.data[0] : data.data;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const type = data.type ? data.type : (this.book.ready ? 'delta' : 'snapshot');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.updateOrderbook({ type, b: frame.b, a: frame.a });[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                this.state.price = parseFloat(k.close);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const metrics = this.book.getAnalysis();[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m                [0m
[48;2;63;0;1m                if (data.topic?.includes(`kline.${CONFIG.intervals.main}.`)) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const k = data.data[0]; [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    if (!k.confirm) return;[0m[48;2;63;0;1m[0K[0m
[48;2;144;16;17m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.state.price = parseFloat(k.close);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const metrics = this.book.getAnalysis();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    process.stdout.write(`\r${C.dim}[v3.5.1 ${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price.toFixed(2)} | Tape:${this.tape.getMetrics().dom} | ${metrics.skew.toFixed(2)} Skew   `);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                [48;2;144;16;17m    [48;2;63;0;1mconst candleContext = { [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        open: D(k.open), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        high: D(k.high), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        low: D(k.low), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        close: D(k.close), [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        volume: D(k.volume || 0),[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [48;2;144;16;17m    [48;2;63;0;1matr: TA.atr([D(k.high)], [D(k.low)], [D(k.close)], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1)[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                [48;2;144;16;17m    [48;2;63;0;1m};[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.oracle.update(candleContext);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const signal = await this.processCandleSignal(k, metrics, this.oracle.klines[this.oracle.klines.length - 1]?.fisher || 0);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    if (signal && signal.action !== 'HOLD') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        await this.placeMakerOrder(signal);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    [0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    await this.checkExitConditions();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                process.stdout.write(`\r${C.dim}[v3.5.1 ${new Date().toLocaleTimeString()}]${C.reset} ${CONFIG.symbol} ${this.state.price.toFixed(2)} | Tape:${this.tape.getMetrics().dom} | ${metrics.skew.toFixed(2)} Skew   `);[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const candleContext = {[0m[7;35m [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                    open: D(k.open), high: D(k.high), low: D(k.low), close: D(k.close), volume: D(k.volume),[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                    atr: TA.atr([D(k.high)], [D(k.low)], [D(k.close)], CONFIG.indicators.atr || 14).slice(-1)[0] || D(1)[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                };[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m                [0m
[48;2;63;0;1m                // Position updates[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                if (data.topic === 'position') {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    const positions = data.data;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    if (positions && positions.length > 0) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        const pos = positions[0];[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        const size = parseFloat(pos.size || '0');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        if (size === 0 && this.state.position.active) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                            // Position closed[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                            this.state.position.active = false;[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                            logger.info('[POSITION] Position closed via Bybit');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                        }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            } catch (error) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                logger.error(`WS update error: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            }[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        });[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                this.oracle.update(candleContext);[0m[48;2;0;40;0m[0K[0m
[7;35m                [0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                const signal = await this.processCandleSignal(k, metrics, this.oracle.klines[this.oracle.klines.length - 1]?.fisher || 0);[0m[48;2;0;40;0m[0K[0m

[48;2;63;0;1m        this.ws.on('close', () => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.warn('WebSocket disconnected, attempting reconnect...');[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            setTimeout(() => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                if (this.isRunning) {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m                    this.start(); // Restart[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                if (signal && signal.action !== 'HOLD') {[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                  await this.placeMakerOrder(signal);[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m                }[0m
[48;2;63;0;1m            }, 5000);[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m                await this.checkExitConditions();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m            }[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m        });[0m

[48;2;63;0;1m        this.ws.on('error', (error) => {[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m            logger.error(`WebSocket error: ${error.message}`);[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        });[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        this.ws.on('error', (error) => [48;2;0;96;0mlogger.error(`WS Error: $[48;2;0;40;0m{[48;2;0;96;0merror.message}`));[0m[48;2;0;40;0m[0K[0m

[38;2;174;129;255m        logger.success(`SHARK MODE ACTIVATED: LEVIATHAN v${VERSION}`);[0m
[38;2;174;129;255m    }[0m

[34m─────────────────────────────[0m[34m┐[0m
[34m766[0m:[38;2;255;255;255m class LeviathanEngine { [0m[34m│[0m
[34m─────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m            this.ws.removeAllListeners();[0m
[38;2;174;129;255m            this.ws.close();[0m
[38;2;174;129;255m        }[0m
[48;2;63;0;1m        await this.master.[48;2;144;16;17mcancelAllOrders[48;2;63;0;1m();[0m[48;2;63;0;1m[0K[0m
[48;2;63;0;1m        logger.info('Leviathan stopped');[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        await this.master.[48;2;0;96;0mclosePositionMarket[48;2;0;40;0m();[0m[48;2;0;40;0m[0K[0m
[48;2;0;40;0;38;2;174;129;255m        logger.info('Leviathan stopped[48;2;0;96;0m gracefully.[48;2;0;40;0m');[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    }[0m
[38;2;255;255;255m}[0m

[38;2;255;255;255m// --- EXECUTION BLOCK ────────────────────────────────────────────────────────[0m
[38;2;255;255;255mif (require.main === module) {[0m
[48;2;0;40;0;38;2;255;255;255m    // Ensure all placeholder logic is removed by ensuring TA/Oracle structure is present above[0m[48;2;0;40;0m[0K[0m
[7;35m    [0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    const engine = new LeviathanEngine();[0m
[38;2;255;255;255m    [0m
[48;2;63;0;1m    // Graceful shutdown[0m[48;2;63;0;1m[0K[0m
[48;2;0;40;0;38;2;174;129;255m    // Graceful shutdown[48;2;0;96;0m handlers[0m[48;2;0;40;0m[0K[0m
[38;2;174;129;255m    process.on('SIGINT', async () => {[0m
[38;2;174;129;255m        logger.info('Received SIGINT, shutting down gracefully...');[0m
[38;2;174;129;255m        await engine.stop();[0m

[34m────────────────────────────────────[0m[34m┐[0m
[34m795[0m:[38;2;255;255;255m if (require.main === module) { [0m[34m│[0m
[34m────────────────────────────────────[0m[34m┘[0m
[38;2;174;129;255m        process.exit(1);[0m
[38;2;174;129;255m    });[0m
[38;2;255;255;255m}[0m
[48;2;63;0;1m[0K[0m
[48;2;63;0;1mmodule.exports = { LeviathanEngine, TA, CONFIG };[0m[48;2;63;0;1m[0K[0m
\ No newline at end of file[m
