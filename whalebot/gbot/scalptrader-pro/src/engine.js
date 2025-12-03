const config = require('./config');
const { EnhancedGeminiBrain } = require('./services/gemini');
const { sendSMS } = require('./services/alert'); // sendSMS is used in new engine, formatSMS might not be directly
const { EnhancedDataProvider } = require('./services/data-provider');
const { EnhancedPaperExchange } = require('./services/exchange');
const NEON = require('./utils/colors');
const { Decimal } = require('decimal.js');
const { getOrderbookLevels, calculateWSS } = require('./utils/analysis');
const TA = require('./indicators'); // Import all TA functions as an object

// Global Decimal settings, needs to be done once
Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

class TradingEngine {
    constructor() { // Reverted constructor
        this.dataProvider = new EnhancedDataProvider();
        this.exchange = new EnhancedPaperExchange();
        this.ai = new EnhancedGeminiBrain();
        this.isRunning = true;
    }

    async start() {
        console.clear();
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` 🚀 WHALEWAVE TITAN v6.1 STARTING... `))));
        
        while (this.isRunning) {
            try {
                const data = await this.dataProvider.fetchAll();
                if (!data) { await new Promise(r => setTimeout(r, config.loop_delay * 1000)); continue; }

                const analysis = await this.performAnalysis(data);
                const context = this.buildContext(data, analysis);
                const signal = await this.ai.analyze(context);

                this.displayDashboard(data, context, signal);
                this.exchange.evaluate(data.price, signal);

            } catch (e) {
                console.error(NEON.RED(`Loop Critical Error: ${e.message}`));
            }
            await new Promise(r => setTimeout(r, config.loop_delay * 1000)); // Reverted delay
        }
    }

    async performAnalysis(data) {
        const c = data.candles.map(x => x.c); const h = data.candles.map(x => x.h);
        const l = data.candles.map(x => x.l); const v = data.candles.map(x => x.v);
        const mtfC = data.candlesMTF.map(x => x.c);

        const [rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci] = await Promise.all([
            TA.rsi(c, config.indicators.rsi), TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
            TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig), TA.adx(h, l, c, config.indicators.adx_period),
            TA.mfi(h, l, c, v, config.indicators.mfi), TA.chop(h, l, c, config.indicators.chop_period),
            TA.linReg(c, config.indicators.linreg_period), TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
            TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult), TA.atr(h, l, c, config.indicators.atr_period),
            TA.findFVG(data.candles), TA.vwap(h, l, c, v, config.indicators.vwap_period),
            TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
            TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult), TA.cci(h, l, c, config.indicators.cci_period)
        ]);

        const last = c.length - 1;
        // Ensure that c.length is at least 1 before accessing c[last]
        // This check is important as indicators can return arrays that are shorter than config.limit
        // leading to 'undefined' access if not careful.
        // For example, if c is an empty array, last would be -1.
        if (last < 0) { // Handle case where candles array is empty or too short
            // Potentially log an error or return a default analysis object
            // For now, let's return a minimal analysis to prevent immediate crashes
            return {
                closes: c, rsi: [], stoch: {k:[],d:[]}, macd: {line:[],signal:[],hist:[]}, adx: [], mfi: [], chop: [], reg: {slope:[],r2:[]}, 
                bb: {upper:[],middle:[],lower:[]}, kc: {upper:[],middle:[],lower:[]}, atr: [], fvg: null, vwap: [], st: {trend:[],value:[]}, 
                ce: {trend:[],value:[]}, cci: [], isSqueeze: false, divergence: 'NONE', volatility: [], avgVolatility: [], 
                trendMTF: 'NONE', buyWall: undefined, sellWall: undefined, fibs: {}
            };
        }

        const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
        const divergence = TA.detectDivergence(c, rsi);
        const volatility = TA.historicalVolatility(c);
        const avgVolatility = TA.sma(volatility, 50);
        const mtfSma = TA.sma(mtfC, 20);
        const trendMTF = mtfC[mtfC.length-1] > mtfSma[mtfSma.length-1] ? "BULLISH" : "BEARISH";
        const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);
        const avgBid = data.bids.reduce((a,b)=>a+b.q,0)/data.bids.length;
        const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p;
        const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p;

        const analysis = { 
            closes: c, rsi, stoch, macd, adx, mfi, chop, reg, bb, kc, atr, fvg, vwap, st, ce, cci,
            isSqueeze, divergence, volatility, avgVolatility, trendMTF, buyWall, sellWall, fibs
        };
        analysis.wss = calculateWSS(analysis, data.price);
        analysis.avgVolatility = avgVolatility;
        return analysis;
    }

    buildContext(d, a) {
        const last = a.closes.length - 1;
        // Defensive check for 'last' index in analysis results
        if (last < 0 || a.rsi.length <= last || a.stoch.k.length <= last || a.macd.hist.length <= last ||
            a.adx.length <= last || a.chop.length <= last || a.vwap.length <= last ||
            a.volatility.length <= last || a.reg.slope.length <= last) {
            // Return a default context or throw an error if analysis data is insufficient
            return {
                price: d.price, rsi: 0, stoch_k: 0, macd_hist: 0, adx: 0, chop: 0, vwap: 0,
                trend_angle: 0, trend_mtf: 'NONE', isSqueeze: 'NO', fvg: null, divergence: 'NONE',
                walls: { buy: undefined, sell: undefined }, fibs: {}, volatility: 0, marketRegime: 'NORMAL',
                wss: 0, sr_levels: 'S:[] R:[]'
            };
        }
        
        const linReg = TA.linReg(a.closes, config.indicators.linreg_period); // Recalculate as TA.reg is slope/r2 object
        const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

        return {
            price: d.price, rsi: a.rsi[last], stoch_k: a.stoch.k[last], macd_hist: (a.macd.hist[last] || 0),
            adx: a.adx[last], chop: a.chop[last], vwap: a.vwap[last],
            trend_angle: linReg.slope[last], trend_mtf: a.trendMTF, isSqueeze: a.isSqueeze ? 'YES' : 'NO', fvg: a.fvg, divergence: a.divergence,
            walls: { buy: a.buyWall, sell: a.sellWall }, fibs: a.fibs,
            volatility: a.volatility[last], marketRegime: TA.marketRegime(a.closes, a.volatility),
            wss: a.wss, sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`
        };
    }

    colorizeValue(value, key) {
        if (typeof value !== 'number') return NEON.GRAY(value);
        const v = parseFloat(value);
        if (key === 'rsi' || key === 'mfi') {
            if (v > 70) return NEON.RED(v.toFixed(2));
            if (v < 30) return NEON.GREEN(v.toFixed(2));
            return NEON.YELLOW(v.toFixed(2));
        }
        if (key === 'stoch_k') {
            if (v > 80) return NEON.RED(v.toFixed(0));
            if (v < 20) return NEON.GREEN(v.toFixed(0));
            return NEON.YELLOW(v.toFixed(0));
        }
        if (key === 'macd_hist' || key === 'trend_angle') {
            if (v > 0) return NEON.GREEN(v.toFixed(4));
            if (v < 0) return NEON.RED(v.toFixed(4));
            return NEON.GRAY(v.toFixed(4));
        }
        if (key === 'adx') {
            if (v > 25) return NEON.ORANGE(v.toFixed(2));
            return NEON.GRAY(v.toFixed(2));
        }
        if (key === 'chop') {
            if (v > 60) return NEON.BLUE(v.toFixed(2));
            if (v < 40) return NEON.ORANGE(v.toFixed(2));
            return NEON.GRAY(v.toFixed(2));
        }
        if (key === 'vwap') {
             return NEON.CYAN(v.toFixed(4));
        }
        return NEON.CYAN(v.toFixed(2));
    }

    displayDashboard(d, ctx, sig) {
        // Defensive check for ctx.wss and ctx.marketRegime
        const wss = ctx.wss !== undefined ? ctx.wss : 0;
        const marketRegime = ctx.marketRegime || 'NORMAL';
        const trendMTF = ctx.trend_mtf || 'NONE';
        const isSqueeze = ctx.isSqueeze || 'NO';
        const divergence = ctx.divergence || 'NONE';
        const fvg = ctx.fvg;
        const vwap = ctx.vwap;


        console.clear();
        const border = NEON.GRAY('─'.repeat(80));
        console.log(border);
        console.log(NEON.bg(NEON.BOLD(NEON.PURPLE(` WHALEWAVE TITAN v6.1 | ${config.symbol} | $${d.price.toFixed(4)} `).padEnd(80))));
        console.log(border);

        const sigColor = sig.action === 'BUY' ? NEON.GREEN : sig.action === 'SELL' ? NEON.RED : NEON.GRAY;
        const wssColor = wss >= config.indicators.wss_weights.action_threshold ? NEON.GREEN : wss <= -config.indicators.wss_weights.action_threshold ? NEON.RED : NEON.YELLOW;
        console.log(`WSS: ${wssColor(wss)} | Strategy: ${NEON.BLUE(sig.strategy || 'SEARCHING')} | Signal: ${sigColor(sig.action)} (${(sig.confidence*100).toFixed(0)}%)`);
        console.log(NEON.GRAY(`Reason: ${sig.reason}`));
        console.log(border);

        const regimeCol = marketRegime.includes('HIGH') ? NEON.RED : marketRegime.includes('LOW') ? NEON.GREEN : NEON.YELLOW;
        const trendCol = trendMTF === 'BULLISH' ? NEON.GREEN : NEON.RED;
        console.log(`Regime: ${regimeCol(marketRegime)} | Vol: ${this.colorizeValue(ctx.volatility, 'volatility')} | Squeeze: ${isSqueeze === 'YES' ? NEON.ORANGE('ACTIVE') : 'OFF'}`);
        console.log(`MTF Trend: ${trendCol(trendMTF)} | Slope: ${this.colorizeValue(ctx.trend_angle, 'trend_angle')} | ADX: ${this.colorizeValue(ctx.adx, 'adx')}`);
        console.log(border);

        console.log(`RSI: ${this.colorizeValue(ctx.rsi, 'rsi')} | Stoch: ${this.colorizeValue(ctx.stoch_k, 'stoch_k')} | MACD Hist: ${this.colorizeValue(ctx.macd_hist, 'macd_hist')} | Chop: ${this.colorizeValue(ctx.chop, 'chop')}`);
        const divCol = divergence.includes('BULLISH') ? NEON.GREEN : divergence.includes('BEARISH') ? NEON.RED : NEON.GRAY;
        console.log(`Divergence: ${divCol(divergence)} | FVG: ${fvg ? NEON.YELLOW(fvg.type) : 'None'} | VWAP: ${this.colorizeValue(vwap, 'vwap')}`);
        console.log(`${NEON.GRAY('Key Levels:')} P=${NEON.YELLOW(ctx.fibs.P.toFixed(2))} S1=${NEON.GREEN(ctx.fibs.S1.toFixed(2))} R1=${NEON.RED(ctx.fibs.R1.toFixed(2))}`);
        console.log(border);

        const pnlCol = this.exchange.dailyPnL.gte(0) ? NEON.GREEN : NEON.RED;
        console.log(`Balance: ${NEON.GREEN('$' + this.exchange.balance.toFixed(2))} | Daily PnL: ${pnlCol('$' + this.exchange.dailyPnL.toFixed(2))}`);
        
        if (this.exchange.pos) {
            const p = this.exchange.pos;
            const curPnl = p.side === 'BUY' ? new Decimal(d.price).sub(p.entry).mul(p.qty) : p.entry.sub(d.price).mul(p.qty);
            const posCol = curPnl.gte(0) ? NEON.GREEN : NEON.RED;
            console.log(NEON.BLUE(`OPEN POS: ${p.side} @ ${p.entry.toFixed(4)} | SL: ${p.sl.toFixed(4)} | TP: ${p.tp.toFixed(4)} | PnL: ${posCol(curPnl.toFixed(2))}`));
        }
        console.log(border);
    }
}

module.exports = { TradingEngine };
