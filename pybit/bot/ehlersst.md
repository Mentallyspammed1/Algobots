function calculateATR(highs, lows, closes, period) {
  const trs = [];
  for (let i = 1; i < highs.length; i++) {
    const tr1 = highs[i] - lows[i];
    const tr2 = Math.abs(highs[i] - closes[i - 1]);
    const tr3 = Math.abs(lows[i] - closes[i - 1]);
    trs.push(Math.max(tr1, tr2, tr3));
  }

  const atrs = new Array(highs.length).fill(0);
  if (trs.length === 0) return atrs;

  let sumTR = 0;
  for (let i = 0; i < period; i++) {
    sumTR += trs[i];
  }
  atrs[period] = sumTR / period;

  for (let i = period + 1; i < highs.length; i++) {
    atrs[i] = (atrs[i - 1] * (period - 1) + trs[i - 1]) / period;
  }
  return atrs;
}

function calculateSuperSmoother(closes, period) {
  const ssFilter = new Array(closes.length).fill(0);
  if (closes.length === 0 || period <= 0) return ssFilter;

  const radPeriod = Math.PI * Math.sqrt(2) / period;
  const alpha = Math.exp(-radPeriod);
  const beta = 2 * alpha * Math.cos(radPeriod);
  const gamma = alpha * alpha;
  const FIR = (1 - alpha) * (1 - alpha) / 2;

  if (closes.length > 0) ssFilter[0] = closes[0];
  if (closes.length > 1) ssFilter[1] = (closes[0] + closes[1]) / 2;

  for (let i = 2; i < closes.length; i++) {
    const prevSS1 = ssFilter[i - 1] || 0;
    const prevSS2 = ssFilter[i - 2] || 0;
    ssFilter[i] = FIR * (closes[i] + closes[i - 1]) + beta * prevSS1 - gamma * prevSS2;
  }
  return ssFilter;
}

function calculateEhlersSupertrend(highs, lows, closes, ssPeriod, atrPeriod, atrMultiplier) {
  const ssFilteredCloses = calculateSuperSmoother(closes, ssPeriod);
  const atrs = calculateATR(highs, lows, closes, atrPeriod);

  const supertrendData = [];
  let prevSupertrendLine = null;
  let prevTrend = 0;

  for (let i = 0; i < closes.length; i++) {
    const currentClose = closes[i];
    const currentSS = ssFilteredCloses[i];
    const currentATR = atrs[i];

    let upperBand = 0;
    let lowerBand = 0;
    let supertrendLine = 0;
    let trend = 0;

    if (i < atrPeriod || i < ssPeriod) {
      supertrendData.push({
        upperBand: null,
        lowerBand: null,
        supertrendLine: null,
        trend: null
      });
      continue;
    }

    const basicUpperBand = currentSS + (atrMultiplier * currentATR);
    const basicLowerBand = currentSS - (atrMultiplier * currentATR);

    if (prevSupertrendLine === null) {
      upperBand = basicUpperBand;
      lowerBand = basicLowerBand;
      trend = 1;
      supertrendLine = basicLowerBand;
    } else {
      if (prevTrend === 1) { // Previous trend was up
        if (currentClose > supertrendData[i - 1].supertrendLine) {
          trend = 1;
          lowerBand = Math.max(basicLowerBand, supertrendData[i - 1].lowerBand);
          upperBand = basicUpperBand;
        } else { // Price crossed below previous Supertrend line
          trend = -1;
          lowerBand = basicLowerBand;
          upperBand = basicUpperBand;
        }
      } else { // Previous trend was down
        if (currentClose < supertrendData[i - 1].supertrendLine) {
          trend = -1;
          upperBand = Math.min(basicUpperBand, supertrendData[i - 1].upperBand);
          lowerBand = basicLowerBand;
        } else { // Price crossed above previous Supertrend line
          trend = 1;
          upperBand = basicUpperBand;
          lowerBand = basicLowerBand;
        }
      }

      // Determine the Supertrend line based on current trend
      if (trend === 1) {
        supertrendLine = lowerBand;
      } else {
        supertrendLine = upperBand;
      }
    }

    prevSupertrendLine = supertrendLine;
    prevTrend = trend;

    supertrendData.push({
      upperBand: upperBand,
      lowerBand: lowerBand,
      supertrendLine: supertrendLine,
      trend: trend
    });
  }
  return supertrendData;
}


function runEhlersSupertrendStrategy(ohlcvData, ssPeriod, atrPeriod, atrMultiplier, initialCapital = 10000) {
  const highs = ohlcvData.map(d => d.high);
  const lows = ohlcvData.map(d => d.low);
  const closes = ohlcvData.map(d => d.close);

  const supertrendResults = calculateEhlersSupertrend(highs, lows, closes, ssPeriod, atrPeriod, atrMultiplier);

  let capital = initialCapital;
  let position = 0;
  let entryPrice = 0;
  let trades = [];

  for (let i = 0; i < ohlcvData.length; i++) {
    const data = ohlcvData[i];
    const st = supertrendResults[i];

    if (!st.trend || i === 0) continue;

    const prevST = supertrendResults[i - 1];
    const trendChanged = prevST.trend !== st.trend;

    if (trendChanged) {
      if (st.trend === 1) {
        if (position === -1) {
          const pnl = (entryPrice - data.close) * (capital / entryPrice);
          capital += pnl;
          trades.push({
            type: 'exit_short',
            entryPrice: entryPrice,
            exitPrice: data.close,
            pnl: pnl,
            capital: capital,
            timestamp: data.timestamp
          });
          position = 0;
        }
        if (position === 0) {
          entryPrice = data.close;
          position = 1;
        }
      } else if (st.trend === -1) {
        if (position === 1) {
          const pnl = (data.close - entryPrice) * (capital / entryPrice);
          capital += pnl;
          trades.push({
            type: 'exit_long',
            entryPrice: entryPrice,
            exitPrice: data.close,
            pnl: pnl,
            capital: capital,
            timestamp: data.timestamp
          });
          position = 0;
        }
        if (position === 0) {
          entryPrice = data.close;
          position = -1;
        }
      }
    }
  }

  if (position !== 0) {
    const lastData = ohlcvData[ohlcvData.length - 1];
    if (position === 1) {
      const pnl = (lastData.close - entryPrice) * (capital / entryPrice);
      capital += pnl;
      trades.push({
        type: 'exit_long_final',
        entryPrice: entryPrice,
        exitPrice: lastData.close,
        pnl: pnl,
        capital: capital,
        timestamp: lastData.timestamp
      });
    } else if (position === -1) {
      const pnl = (entryPrice - lastData.close) * (capital / entryPrice);
      capital += pnl;
      trades.push({
        type: 'exit_short_final',
        entryPrice: entryPrice,
        exitPrice: lastData.close,
        pnl: pnl,
        capital: capital,
        timestamp: lastData.timestamp
      });
    }
  }

  return {
    finalCapital: capital,
    trades: trades,
    supertrendData: supertrendResults
  };
}
