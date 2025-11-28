// engine.js
import axios from 'axios';
import chalk from 'chalk';
import { Decimal } from 'decimal.js';
import { delay } from 'timers/promises';
import { config } from './config.js';
import { TA } from './ta.js';
import { EnhancedDataProvider } from './dataProvider.js';
import { TradeLogger } from './logger.js';
import { EnhancedGeminiBrain } from './enhancedGeminiBrain.js';
import { EnhancedPaperExchange } from './enhancedPaperExchange.js';

Decimal.set({ precision: 20, rounding: Decimal.ROUND_HALF_DOWN });

const NEON = {
  GREEN: chalk.hex('#39FF14'),
  RED: chalk.hex('#FF073A'),
  BLUE: chalk.hex('#00AFFF'),
  CYAN: chalk.hex('#00FFFF'),
  PURPLE: chalk.hex('#BC13FE'),
  YELLOW: chalk.hex('#FAED27'),
  GRAY: chalk.hex('#666666'),
  ORANGE: chalk.hex('#FF9F00'),
  BOLD: chalk.bold,
  bg: (text) => chalk.bgHex('#222')(text)
};

class TradingEngine {
  constructor() {
    this.dataProvider = new EnhancedDataProvider();
    this.logger = new TradeLogger();
    this.exchange = new EnhancedPaperExchange(this.logger);
    this.ai = new EnhancedGeminiBrain();
    this.isRunning = true;
    this.lastData = null;
    this.loopCount = 0;
    this.startTime = Date.now();
    this.dashboardClient = axios.create({
      baseURL: `http://localhost:${process.env.PORT || 3000}`,
      timeout: 2000
    });
  }

  async start() {
    console.clear();
    console.log(NEON.bg(NEON.PURPLE(' 🚀 WHALEWAVE TITAN v7.0 STARTING... ')));

    while (this.isRunning) {
      this.loopCount++;
      try {
        const data = await this.dataProvider.fetchAll();
        this.lastData = data;
        if (!data) {
          await delay(config.loop_delay * 1000);
          continue;
        }

        const analysis = await this.performAnalysis(data);
        const context = this.buildContext(data, analysis);
        const signal = await this.ai.analyze(context);

        this.logger.logSignal(signal, context);
        this.exchange.evaluate(data.price, signal);
        await this.pushDashboardData(data, context, signal);

        if (this.loopCount % 100 === 0) {
          const mins = ((Date.now() - this.startTime) / 60000).toFixed(1);
          console.log(
            NEON.GRAY(
              `\n[ENGINE STATS] loops=${this.loopCount}, uptime=${mins}m, balance=$${this.exchange.balance.toFixed(2)}`
            )
          );
        }
      } catch (e) {
        console.error(NEON.RED(`Loop Error: ${e.message}`));
      }
      await delay(config.loop_delay * 1000);
    }
  }

  async performAnalysis(data) {
    const c = data.candles.map(x => x.c);
    const h = data.candles.map(x => x.h);
    const l = data.candles.map(x => x.l);
    const v = data.candles.map(x => x.v);
    const mtfC = data.candlesMTF.map(x => x.c);

    if (c.length < 50) {
      const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);
      return {
        closes: c,
        rsi: TA.safeArr(c.length),
        stoch: { k: TA.safeArr(c.length), d: TA.safeArr(c.length) },
        macd: { line: TA.safeArr(c.length), signal: TA.safeArr(c.length), hist: TA.safeArr(c.length) },
        adx: TA.safeArr(c.length),
        mfi: TA.safeArr(c.length),
        chop: TA.safeArr(c.length),
        reg: { slope: TA.safeArr(c.length), r2: TA.safeArr(c.length) },
        bb: { upper: TA.safeArr(c.length), middle: TA.safeArr(c.length), lower: TA.safeArr(c.length) },
        kc: { upper: TA.safeArr(c.length), middle: TA.safeArr(c.length), lower: TA.safeArr(c.length) },
        atr: TA.safeArr(c.length),
        fvg: null,
        vwap: TA.safeArr(c.length),
        st: { trend: TA.safeArr(c.length), value: TA.safeArr(c.length) },
        ce: { trend: TA.safeArr(c.length), value: TA.safeArr(c.length) },
        cci: TA.safeArr(c.length),
        isSqueeze: false,
        divergence: 'NONE',
        volatility: TA.safeArr(c.length),
        avgVolatilitySeries: TA.safeArr(c.length),
        trendMTF: 'NEUTRAL',
        buyWall: null,
        sellWall: null,
        fibs,
        wss: 0
      };
    }

    const [
      rsi, stoch, macd, adx, mfi, chop,
      reg, bb, kc, atr, vwap, st, ce, cci
    ] = await Promise.all([
      TA.rsi(c, config.indicators.rsi),
      TA.stoch(h, l, c, config.indicators.stoch_period, config.indicators.stoch_k, config.indicators.stoch_d),
      TA.macd(c, config.indicators.macd_fast, config.indicators.macd_slow, config.indicators.macd_sig),
      TA.adx(h, l, c, config.indicators.adx_period),
      TA.mfi(h, l, c, v, config.indicators.mfi),
      TA.chop(h, l, c, config.indicators.chop_period),
      TA.linReg(c, config.indicators.linreg_period),
      TA.bollinger(c, config.indicators.bb_period, config.indicators.bb_std),
      TA.keltner(h, l, c, config.indicators.kc_period, config.indicators.kc_mult),
      TA.atr(h, l, c, config.indicators.atr_period),
      TA.vwap(h, l, c, v, config.indicators.vwap_period),
      TA.superTrend(h, l, c, config.indicators.atr_period, config.indicators.st_factor),
      TA.chandelierExit(h, l, c, config.indicators.ce_period, config.indicators.ce_mult),
      TA.cci(h, l, c, config.indicators.cci_period)
    ]);

    const fvg = TA.findFVG(data.candles);
    const last = c.length - 1;
    const isSqueeze = (bb.upper[last] < kc.upper[last]) && (bb.lower[last] > kc.lower[last]);
    const divergence = TA.detectDivergence(c, rsi);
    const volatility = TA.historicalVolatility(c);
    const avgVolatilitySeries = TA.sma(volatility, 50);
    const mtfSma = TA.sma(mtfC, 20);
    const trendMTF = mtfC[mtfC.length - 1] > mtfSma[mtfSma.length - 1] ? 'BULLISH' : 'BEARISH';
    const fibs = TA.fibPivots(data.daily.h, data.daily.l, data.daily.c);

    const avgBid = data.bids.length ? data.bids.reduce((a, b) => a + b.q, 0) / data.bids.length : 0;
    const buyWall = data.bids.find(b => b.q > avgBid * config.orderbook.wall_threshold)?.p || null;
    const sellWall = data.asks.find(a => a.q > avgBid * config.orderbook.wall_threshold)?.p || null;

    const analysis = {
      closes: c, rsi, stoch, macd, adx, mfi, chop, reg,
      bb, kc, atr, fvg, vwap, st, ce, cci,
      isSqueeze, divergence, volatility, avgVolatilitySeries,
      trendMTF, buyWall, sellWall, fibs
    };
    analysis.wss = calculateWSS(analysis, data.price);
    return analysis;
  }

  buildContext(d, a) {
    const last = a.closes.length - 1;
    const linReg = TA.getFinalValue(a, 'reg');
    const sr = getOrderbookLevels(d.bids, d.asks, d.price, config.orderbook.sr_levels);

    return {
      price: d.price,
      rsi: a.rsi[last] || 50,
      stoch_k: a.stoch.k[last] || 50,
      macd_hist: a.macd.hist[last] || 0,
      adx: a.adx[last] || 0,
      chop: a.chop[last] || 0,
      vwap: a.vwap[last] || d.price,
      trend_angle: linReg,
      trend_mtf: a.trendMTF,
      isSqueeze: a.isSqueeze ? 'YES' : 'NO',
      fvg: a.fvg,
      divergence: a.divergence,
      walls: { buy: a.buyWall, sell: a.sellWall },
      fibs: a.fibs,
      volatility: a.volatility[last] || 0,
      marketRegime: TA.marketRegime(a.closes, a.volatility),
      wss: a.wss,
      sr_levels: `S:[${sr.supportLevels.join(', ')}] R:[${sr.resistanceLevels.join(', ')}]`
    };
  }

  async pushDashboardData(data, context, signal) {
    const p = this.exchange.pos;
    const curPnl = p
      ? (p.side === 'BUY'
          ? new Decimal(data.price).sub(p.entry).mul(p.qty)
          : p.entry.sub(new Decimal(data.price)).mul(p.qty))
      : new Decimal(0);

    const payload = {
      price: data.price.toFixed(4),
      wss: context.wss.toFixed(2),
      wss_action: signal.action,
      wss_confidence: signal.confidence,
      ai_reason: signal.reason,
      acc_balance: this.exchange.balance.toFixed(2),
      daily_pnl: this.exchange.dailyPnL.toFixed(2),
      pos_active: !!p,
      pos_side: p?.side || null,
      pos_entry: p ? p.entry.toFixed(4) : null,
      pos_sl: p ? p.sl.toFixed(4) : null,
      pos_tp: p ? p.tp.toFixed(4) : null,
      pos_pnl: curPnl.toFixed(2),
      indicators: {
        rsi: context.rsi.toFixed(2),
        adx: context.adx.toFixed(2),
        stoch_k: context.stoch_k.toFixed(0),
        chop: context.chop.toFixed(2),
        fvg: context.fvg ? context.fvg.type : 'None',
        trend_mtf: context.trend_mtf,
        regime: context.marketRegime
      }
    };

    try {
      await this.dashboardClient.post('/api/dashboard', payload);
    } catch {
      // Non‑fatal: dashboard may be down or not ready
    }
  }
}

// ---------- Helper: calculateWSS ----------
function calculateWSS(analysis, currentPrice) {
  const w = config.indicators.wss_weights;
  const last = analysis.closes.length - 1;
  if (last < 0) return 0;

  const { rsi, stoch, macd, reg, st, ce, fvg, divergence, buyWall, sellWall, atr } = analysis;
  let score = 0;

  // Trend
  let trendScore = 0;
  trendScore += analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight;
  trendScore += st.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight;
  trendScore += ce.trend[last] === 1 ? w.trend_scalp_weight : -w.trend_scalp_weight;
  trendScore *= reg.r2[last] || 0;
  score += trendScore;

  // Momentum
  let momentumScore = 0;
  const rsiVal = rsi[last] || 50;
  const stochK = stoch.k[last] || 50;
  if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50;
  else momentumScore -= (rsiVal - 50) / 50;

  if (stochK < 50) momentumScore += (50 - stochK) / 50;
  else momentumScore -= (stochK - 50) / 50;

  const macdHist = macd.hist[last] || 0;
  if (macdHist > 0) momentumScore += w.macd_weight;
  else if (macdHist < 0) momentumScore -= w.macd_weight;

  score += momentumScore * w.momentum_normalized_weight;

  // Structure / Liquidity
  let structureScore = 0;
  if (analysis.isSqueeze) {
    structureScore += analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight;
  }
  if (divergence.includes('BULLISH')) structureScore += w.divergence_weight;
  else if (divergence.includes('BEARISH')) structureScore -= w.divergence_weight;

  const price = currentPrice;
  const atrVal = atr[last] || 0;
  if (fvg) {
    if (fvg.type === 'BULLISH' && price > fvg.bottom && price < fvg.top) {
      structureScore += w.liquidity_grab_weight;
    } else if (fvg.type === 'BEARISH' && price < fvg.top && price > fvg.bottom) {
      structureScore -= w.liquidity_grab_weight;
    }
  }
  if (buyWall && atrVal > 0 && price - buyWall < atrVal) {
    structureScore += w.liquidity_grab_weight * 0.5;
  } else if (sellWall && atrVal > 0 && sellWall - price < atrVal) {
    structureScore -= w.liquidity_grab_weight * 0.5;
  }
  score += structureScore;

  // Volatility adjustment
  const volatility = analysis.volatility[analysis.volatility.length - 1] || 0;
  const avgVolatility = analysis.avgVolatilitySeries[analysis.avgVolatilitySeries.length - 1] || 1;
  const volRatio = volatility / avgVolatility;
  let finalScore = score;
  if (volRatio > 1.5) finalScore *= 1 - w.volatility_weight;
  else if (volRatio < 0.5) finalScore *= 1 + w.volatility_weight;

  return parseFloat(finalScore.toFixed(2));
}

// ---------- Helper: Orderbook S/R ----------
function getOrderbookLevels(bids, asks, currentClose, maxLevels) {
  if (!Array.isArray(bids) || !Array.isArray(asks) || !currentClose) {
    return { supportLevels: [], resistanceLevels: [] };
  }
  const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
  const unique = [...new Set(pricePoints)].sort((a, b) => a - b);
  const candidates = [];
  for (const price of unique) {
    const bidVol = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
    const askVol = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
    if (bidVol > askVol * 2) candidates.push({ price, type: 'S' });
    else if (askVol > bidVol * 2) candidates.push({ price, type: 'R' });
  }
  const sorted = candidates.sort((a, b) =>
    Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose)
  );
  const supportLevels = sorted
    .filter(p => p.type === 'S' && p.price < currentClose)
    .slice(0, maxLevels)
    .map(p => p.price.toFixed(2));
  const resistanceLevels = sorted
    .filter(p => p.type === 'R' && p.price > currentClose)
    .slice(0, maxLevels)
    .map(p => p.price.toFixed(2));
  return { supportLevels, resistanceLevels };
}

// ---------- Start Engine ----------
const engine = new TradingEngine();

process.on('SIGINT', () => {
  engine.isRunning = false;
  console.log(NEON.RED('\n🛑 SHUTTING DOWN ENGINE GRACEFULLY...'));
  if (engine.lastData) {
    engine.exchange.handlePositionClose(new Decimal(engine.lastData.price), 'SHUTDOWN');
  }
  process.exit(0);
});

process.on('SIGTERM', () => {
  engine.isRunning = false;
  process.exit(0);
});

engine.start();
