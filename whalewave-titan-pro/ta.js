// ta.js
export class TA {
  static safeArr(len) {
    return new Array(Math.max(0, len | 0)).fill(0);
  }

  static getFinalValue(data, key) {
    const closes = data.closes || [];
    const last = closes.length - 1;
    if (last < 0) return 0;
    const value = data[key];
    if (Array.isArray(value)) return value[last] ?? 0;
    if (typeof value === 'object' && value !== null) {
      if (Array.isArray(value.k)) return value.k[last] ?? 0;
      if (Array.isArray(value.hist)) return value.hist[last] ?? 0;
      if (Array.isArray(value.slope) && Array.isArray(value.r2)) {
        return { slope: value.slope[last] ?? 0, r2: value.r2[last] ?? 0 };
      }
    }
    return 0;
  }

  static wilders(data, period) {
    const len = (data || []).length;
    if (!Array.isArray(data) || len === 0 || period <= 0) return TA.safeArr(len);
    if (len < period) return TA.safeArr(len);
    const res = TA.safeArr(len);
    let sum = 0;
    for (let i = 0; i < period; i++) sum += data[i];
    res[period - 1] = sum / period;
    const alpha = 1 / period;
    for (let i = period; i < len; i++) {
      res[i] = data[i] * alpha + res[i - 1] * (1 - alpha);
    }
    return res;
  }

  static sma(data, period) {
    const len = (data || []).length;
    if (!Array.isArray(data) || len === 0 || period <= 0) return TA.safeArr(len);
    if (len < period) return TA.safeArr(len);
    const out = [];
    let sum = 0;
    for (let i = 0; i < period; i++) sum += data[i];
    out.push(sum / period);
    for (let i = period; i < len; i++) {
      sum += data[i] - data[i - period];
      out.push(sum / period);
    }
    return TA.safeArr(period - 1).concat(out);
  }

  static ema(data, period) {
    const len = (data || []).length;
    if (!Array.isArray(data) || len === 0 || period <= 0) return TA.safeArr(len);
    const res = TA.safeArr(len);
    const k = 2 / (period + 1);
    res[0] = data[0];
    for (let i = 1; i < len; i++) res[i] = data[i] * k + res[i - 1] * (1 - k);
    return res;
  }

  static atr(highs, lows, closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0) {
      return TA.safeArr(len);
    }
    const tr = [Math.max(highs[0] - lows[0], 0)];
    for (let i = 1; i < len; i++) {
      const r1 = highs[i] - lows[i];
      const r2 = Math.abs(highs[i] - closes[i - 1]);
      const r3 = Math.abs(lows[i] - closes[i - 1]);
      tr.push(Math.max(r1, r2, r3));
    }
    return TA.wilders(tr, period);
  }

  static rsi(closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || len === 0 || period <= 0) return TA.safeArr(len);
    const gains = [0], losses = [0];
    for (let i = 1; i < len; i++) {
      const diff = closes[i] - closes[i - 1];
      gains.push(diff > 0 ? diff : 0);
      losses.push(diff < 0 ? -diff : 0);
    }
    const avgGain = TA.wilders(gains, period);
    const avgLoss = TA.wilders(losses, period);
    const out = TA.safeArr(len);
    for (let i = 0; i < len; i++) {
      if (avgLoss[i] === 0) out[i] = avgGain[i] === 0 ? 50 : 100;
      else {
        const rs = avgGain[i] / avgLoss[i];
        out[i] = 100 - 100 / (1 + rs);
      }
    }
    return out;
  }

  static stoch(highs, lows, closes, period, kP, dP) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0) {
      return { k: TA.safeArr(len), d: TA.safeArr(len) };
    }
    const raw = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      const hi = highs.slice(i - period + 1, i + 1);
      const lo = lows.slice(i - period + 1, i + 1);
      const maxH = Math.max(...hi);
      const minL = Math.min(...lo);
      const denom = maxH - minL;
      raw[i] = denom === 0 ? 50 : 100 * ((closes[i] - minL) / denom);
    }
    const k = TA.sma(raw, kP);
    const d = TA.sma(k, dP);
    return { k, d };
  }

  static macd(closes, fast, slow, sig) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || len === 0) {
      return {
        line: TA.safeArr(len),
        signal: TA.safeArr(len),
        hist: TA.safeArr(len)
      };
    }
    const emaFast = TA.ema(closes, fast);
    const emaSlow = TA.ema(closes, slow);
    const line = TA.safeArr(len);
    for (let i = 0; i < len; i++) line[i] = emaFast[i] - emaSlow[i];
    const signal = TA.ema(line, sig);
    const hist = TA.safeArr(len);
    for (let i = 0; i < len; i++) hist[i] = line[i] - signal[i];
    return { line, signal, hist };
  }

  static adx(highs, lows, closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0) {
      return TA.safeArr(len);
    }
    const plusDM = [0], minusDM = [0];
    for (let i = 1; i < len; i++) {
      const up = highs[i] - highs[i - 1];
      const down = lows[i - 1] - lows[i];
      plusDM.push(up > down && up > 0 ? up : 0);
      minusDM.push(down > up && down > 0 ? down : 0);
    }
    const tr = [Math.max(highs[0] - lows[0], 0)];
    for (let i = 1; i < len; i++) {
      const r1 = highs[i] - lows[i];
      const r2 = Math.abs(highs[i] - closes[i - 1]);
      const r3 = Math.abs(lows[i] - closes[i - 1]);
      tr.push(Math.max(r1, r2, r3));
    }
    const atr = TA.wilders(tr, period);
    const sPlus = TA.wilders(plusDM, period);
    const sMinus = TA.wilders(minusDM, period);
    const dx = TA.safeArr(len);
    for (let i = 0; i < len; i++) {
      if (atr[i] === 0) { dx[i] = 0; continue; }
      const pDI = (sPlus[i] / atr[i]) * 100;
      const mDI = (sMinus[i] / atr[i]) * 100;
      const sum = pDI + mDI;
      dx[i] = sum === 0 ? 0 : (Math.abs(pDI - mDI) / sum) * 100;
    }
    return TA.wilders(dx, period);
  }

  static mfi(highs, lows, closes, volumes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes) || len === 0) {
      return TA.safeArr(len);
    }
    const posFlow = [], negFlow = [];
    for (let i = 0; i < len; i++) {
      if (i === 0) { posFlow.push(0); negFlow.push(0); continue; }
      const tp = (highs[i] + lows[i] + closes[i]) / 3;
      const prevTp = (highs[i - 1] + lows[i - 1] + closes[i - 1]) / 3;
      const raw = tp * volumes[i];
      if (tp > prevTp) { posFlow.push(raw); negFlow.push(0); }
      else if (tp < prevTp) { posFlow.push(0); negFlow.push(raw); }
      else { posFlow.push(0); negFlow.push(0); }
    }
    const out = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      let pSum = 0, nSum = 0;
      for (let j = 0; j < period; j++) {
        pSum += posFlow[i - j];
        nSum += negFlow[i - j];
      }
      if (nSum === 0) out[i] = 100;
      else {
        const mr = pSum / nSum;
        out[i] = 100 - 100 / (1 + mr);
      }
    }
    return out;
  }

  static chop(highs, lows, closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0) {
      return TA.safeArr(len);
    }
    const tr = [Math.max(highs[0] - lows[0], 0)];
    for (let i = 1; i < len; i++) {
      const r1 = highs[i] - lows[i];
      const r2 = Math.abs(highs[i] - closes[i - 1]);
      const r3 = Math.abs(lows[i] - closes[i - 1]);
      tr.push(Math.max(r1, r2, r3));
    }
    const out = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      let sumTr = 0, maxHi = -Infinity, minLo = Infinity;
      for (let j = 0; j < period; j++) {
        const idx = i - j;
        sumTr += tr[idx];
        if (highs[idx] > maxHi) maxHi = highs[idx];
        if (lows[idx] < minLo) minLo = lows[idx];
      }
      const range = maxHi - minLo;
      if (range === 0 || sumTr === 0) out[i] = 50;
      else out[i] = 100 * (Math.log10(sumTr / range) / Math.log10(period));
    }
    return out;
  }

  static cci(highs, lows, closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0) {
      return TA.safeArr(len);
    }
    const tp = highs.map((h, i) => (h + lows[i] + closes[i]) / 3);
    const smaTp = TA.sma(tp, period);
    const out = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      let meanDev = 0;
      for (let j = 0; j < period; j++) {
        meanDev += Math.abs(tp[i - j] - smaTp[i]);
      }
      meanDev /= period;
      out[i] = meanDev === 0 ? 0 : (tp[i] - smaTp[i]) / (0.015 * meanDev);
    }
    return out;
  }

  static linReg(closes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || len === 0 || period <= 1) {
      return { slope: TA.safeArr(len), r2: TA.safeArr(len) };
    }
    const slopes = TA.safeArr(len);
    const r2s = TA.safeArr(len);
    let sumX = 0, sumX2 = 0;
    for (let i = 0; i < period; i++) {
      sumX += i;
      sumX2 += i * i;
    }
    const n = period;
    for (let i = period - 1; i < len; i++) {
      let sumY = 0, sumXY = 0;
      const ySlice = [];
      for (let j = 0; j < period; j++) {
        const idx = i - (period - 1) + j;
        const val = closes[idx];
        ySlice.push(val);
        sumY += val;
        sumXY += j * val;
      }
      const num = n * sumXY - sumX * sumY;
      const den = n * sumX2 - sumX * sumX;
      const slope = den === 0 ? 0 : num / den;
      const intercept = (sumY - slope * sumX) / n;
      let ssTot = 0, ssRes = 0;
      const yMean = sumY / n;
      for (let j = 0; j < period; j++) {
        const y = ySlice[j];
        const yPred = slope * j + intercept;
        ssTot += (y - yMean) ** 2;
        ssRes += (y - yPred) ** 2;
      }
      slopes[i] = slope;
      r2s[i] = ssTot === 0 ? 0 : 1 - ssRes / ssTot;
    }
    return { slope: slopes, r2: r2s };
  }

  static bollinger(closes, period, stdDev) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || len === 0 || period <= 1) {
      return { upper: TA.safeArr(len), middle: TA.safeArr(len), lower: TA.safeArr(len) };
    }
    const middle = TA.sma(closes, period);
    const upper = TA.safeArr(len);
    const lower = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      let sumSq = 0;
      for (let j = 0; j < period; j++) {
        const idx = i - j;
        sumSq += (closes[idx] - middle[i]) ** 2;
      }
      const std = Math.sqrt(sumSq / period);
      upper[i] = middle[i] + stdDev * std;
      lower[i] = middle[i] - stdDev * std;
    }
    return { upper, middle, lower };
  }

  static keltner(highs, lows, closes, period, mult) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0 || period <= 0) {
      return { upper: TA.safeArr(len), middle: TA.safeArr(len), lower: TA.safeArr(len) };
    }
    const middle = TA.ema(closes, period);
    const atr = TA.atr(highs, lows, closes, period);
    const upper = TA.safeArr(len);
    const lower = TA.safeArr(len);
    for (let i = 0; i < len; i++) {
      upper[i] = middle[i] + atr[i] * mult;
      lower[i] = middle[i] - atr[i] * mult;
    }
    return { upper, middle, lower };
  }

  static superTrend(highs, lows, closes, period, factor) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0 || period <= 0) {
      return { trend: TA.safeArr(len), value: TA.safeArr(len) };
    }
    const atr = TA.atr(highs, lows, closes, period);
    const st = TA.safeArr(len);
    const trend = TA.safeArr(len).map(() => 1);
    for (let i = period; i < len; i++) {
      let up = (highs[i] + lows[i]) / 2 + factor * atr[i];
      let dn = (highs[i] + lows[i]) / 2 - factor * atr[i];
      if (i > 0) {
        const prevST = st[i - 1];
        if (trend[i - 1] === 1) {
          dn = Math.max(dn, prevST);
        } else {
          up = Math.min(up, prevST);
        }
      }
      if (closes[i] > up) trend[i] = 1;
      else if (closes[i] < dn) trend[i] = -1;
      else trend[i] = trend[i - 1];
      st[i] = trend[i] === 1 ? dn : up;
    }
    return { trend, value: st };
  }

  static chandelierExit(highs, lows, closes, period, mult) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || len === 0 || period <= 0) {
      return { trend: TA.safeArr(len), value: TA.safeArr(len) };
    }
    const atr = TA.atr(highs, lows, closes, period);
    const longStop = TA.safeArr(len);
    const shortStop = TA.safeArr(len);
    const trend = TA.safeArr(len).map(() => 1);
    for (let i = period; i < len; i++) {
      const hi = highs.slice(i - period + 1, i + 1);
      const lo = lows.slice(i - period + 1, i + 1);
      const maxHigh = Math.max(...hi);
      const minLow = Math.min(...lo);
      longStop[i] = maxHigh - atr[i] * mult;
      shortStop[i] = minLow + atr[i] * mult;
      if (closes[i] > shortStop[i]) trend[i] = 1;
      else if (closes[i] < longStop[i]) trend[i] = -1;
      else trend[i] = trend[i - 1];
    }
    const value = trend.map((t, i) => (t === 1 ? longStop[i] : shortStop[i]));
    return { trend, value };
  }

  static vwap(highs, lows, closes, volumes, period) {
    const len = (closes || []).length;
    if (!Array.isArray(highs) || !Array.isArray(lows) || !Array.isArray(closes) || !Array.isArray(volumes) || len === 0 || period <= 0) {
      return TA.safeArr(len);
    }
    const vwap = TA.safeArr(len);
    for (let i = period - 1; i < len; i++) {
      let sumPV = 0, sumV = 0;
      for (let j = 0; j < period; j++) {
        const idx = i - j;
        const tp = (highs[idx] + lows[idx] + closes[idx]) / 3;
        const vol = volumes[idx];
        sumPV += tp * vol;
        sumV += vol;
      }
      vwap[i] = sumV === 0 ? closes[i] : sumPV / sumV;
    }
    return vwap;
  }

  static findFVG(candles) {
    const len = (candles || []).length;
    if (!Array.isArray(candles) || len < 5) return null;
    const c1 = candles[len - 4];
    const c2 = candles[len - 3];
    const c3 = candles[len - 2];
    if (!c1 || !c2 || !c3) return null;
    if (c2.c > c2.o && c3.l > c1.h) {
      const top = c3.l, bottom = c1.h;
      return { type: 'BULLISH', top, bottom, price: (top + bottom) / 2 };
    }
    if (c2.c < c2.o && c3.h < c1.l) {
      const top = c1.l, bottom = c3.h;
      return { type: 'BEARISH', top, bottom, price: (top + bottom) / 2 };
    }
    return null;
  }

  static detectDivergence(closes, rsi, period = 5) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || !Array.isArray(rsi) || len < period * 2) return 'NONE';
    const curStart = len - period;
    const prevStart = len - period * 2;
    const curCloses = closes.slice(curStart);
    const curRsi = rsi.slice(curStart);
    const prevCloses = closes.slice(prevStart, curStart);
    const prevRsi = rsi.slice(prevStart, curStart);

    const priceHigh = Math.max(...curCloses);
    const rsiHigh = Math.max(...curRsi);
    const prevPriceHigh = Math.max(...prevCloses);
    const prevRsiHigh = Math.max(...prevRsi);
    if (priceHigh > prevPriceHigh && rsiHigh < prevRsiHigh) return 'BEARISH_REGULAR';

    const priceLow = Math.min(...curCloses);
    const rsiLow = Math.min(...curRsi);
    const prevPriceLow = Math.min(...prevCloses);
    const prevRsiLow = Math.min(...prevRsi);
    if (priceLow < prevPriceLow && rsiLow > prevRsiLow) return 'BULLISH_REGULAR';

    return 'NONE';
  }

  static historicalVolatility(closes, period = 20) {
    const len = (closes || []).length;
    if (!Array.isArray(closes) || len < 2 || period <= 1) return TA.safeArr(len);
    const returns = [];
    for (let i = 1; i < len; i++) {
      const r = Math.log(closes[i] / closes[i - 1]);
      returns.push(Number.isFinite(r) ? r : 0);
    }
    const out = TA.safeArr(len);
    for (let i = period; i < len; i++) {
      const slice = returns.slice(i - period, i);
      const mean = slice.reduce((a, b) => a + b, 0) / slice.length;
      const variance = slice.reduce((a, b) => a + (b - mean) ** 2, 0) / slice.length;
      const std = Math.sqrt(variance);
      out[i] = std * Math.sqrt(365);
    }
    return out;
  }

  static marketRegime(closes, volatility, period = 50) {
    const volArr = Array.isArray(volatility) ? volatility : TA.safeArr((closes || []).length);
    const avgVol = TA.sma(volArr, period);
    const len = volArr.length;
    if (len === 0) return 'UNKNOWN';
    const currentVol = volArr[len - 1] || 0;
    const avgVolValue = avgVol[len - 1] || (currentVol || 1);
    if (currentVol > avgVolValue * 1.5) return 'HIGH_VOLATILITY';
    if (currentVol < avgVolValue * 0.5) return 'LOW_VOLATILITY';
    return 'NORMAL_VOLATILITY';
  }

  static fibPivots(h, l, c) {
    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(c)) {
      return { P: 0, R1: 0, R2: 0, S1: 0, S2: 0 };
    }
    const P = (h + l + c) / 3;
    const R = h - l;
    return {
      P,
      R1: P + 0.382 * R,
      R2: P + 0.618 * R,
      S1: P - 0.382 * R,
      S2: P - 0.618 * R
    };
  }
}
