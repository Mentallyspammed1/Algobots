const config = require('../config');
const NEON = require('../utils/colors');

function getOrderbookLevels(bids, asks, currentClose, maxLevels) {
    const pricePoints = [...bids.map(b => b.p), ...asks.map(a => a.p)];
    const uniquePrices = [...new Set(pricePoints)].sort((a, b) => a - b);
    let potentialSR = [];
    for (const price of uniquePrices) {
        let bidVolAtPrice = bids.filter(b => b.p === price).reduce((s, b) => s + b.q, 0);
        let askVolAtPrice = asks.filter(a => a.p === price).reduce((s, a) => s + a.q, 0);
        if (bidVolAtPrice > askVolAtPrice * 2) potentialSR.push({ price, type: 'S' });
        else if (askVolAtPrice > bidVolAtPrice * 2) potentialSR.push({ price, type: 'R' });
    }
    const sortedByDist = potentialSR.sort((a, b) => Math.abs(a.price - currentClose) - Math.abs(b.price - currentClose));
    const supportLevels = sortedByDist.filter(p => p.type === 'S' && p.price < currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    const resistanceLevels = sortedByDist.filter(p => p.type === 'R' && p.price > currentClose).slice(0, maxLevels).map(p => p.price.toFixed(2));
    return { supportLevels, resistanceLevels };
}

function calculateWSS(analysis, currentPrice) {
    const w = config.indicators.wss_weights;
    let score = 0;
    const last = analysis.closes.length - 1;
    const { rsi, stoch, macd, reg, superTrend, chandelierExit, fvg, divergence, buyWall, sellWall, atr } = analysis;

    // --- 1. TREND COMPONENT (REFINED) ---
    let trendScore = 0;
    trendScore += (analysis.trendMTF === 'BULLISH' ? w.trend_mtf_weight : -w.trend_mtf_weight);
    if (superTrend.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    if (chandelierExit.trend[last] === 1) trendScore += w.trend_scalp_weight; else trendScore -= w.trend_scalp_weight;
    trendScore *= reg.r2[last]; 
    score += trendScore;

    // --- 2. MOMENTUM COMPONENT (NORMALIZED & REFINED) ---
    let momentumScore = 0;
    const rsiVal = rsi[last]; const stochK = stoch.k[last];
    if (rsiVal < 50) momentumScore += (50 - rsiVal) / 50; else momentumScore -= (rsiVal - 50) / 50;
    if (stochK < 50) momentumScore += (50 - stochK) / 50; else momentumScore -= (stochK - 50) / 50;
    const macdHist = macd.hist[last];
    if (macdHist > 0) momentumScore += w.macd_weight; else if (macdHist < 0) momentumScore -= w.macd_weight;
    score += momentumScore * w.momentum_normalized_weight;


    // --- 3. STRUCTURE / LIQUIDITY COMPONENT (REFINED) ---
    let structureScore = 0;
    if (analysis.isSqueeze) structureScore += (analysis.trendMTF === 'BULLISH' ? w.squeeze_vol_weight : -w.squeeze_vol_weight);
    if (divergence.includes('BULLISH')) structureScore += w.divergence_weight;
    else if (divergence.includes('BEARISH')) structureScore -= w.divergence_weight;

    const price = currentPrice;
    const atrVal = atr[last];
    if (fvg) {
        if (fvg.type === 'BULLISH' && price > fvg.bottom && price < fvg.top) structureScore += w.liquidity_grab_weight;
        else if (fvg.type === 'BEARISH' && price < fvg.top && price > fvg.bottom) structureScore -= w.liquidity_grab_weight;
    }
    if (buyWall && (price - buyWall) < atrVal) structureScore += w.liquidity_grab_weight * 0.5; 
    else if (sellWall && (sellWall - price) < atrVal) structureScore -= w.liquidity_grab_weight * 0.5;
    score += structureScore;

    // --- 4. FINAL VOLATILITY ADJUSTMENT ---
    const volatility = analysis.volatility[analysis.volatility.length - 1] || 0;
    const avgVolatility = analysis.avgVolatility[analysis.avgVolatility.length - 1] || 1;
    const volRatio = volatility / avgVolatility;

    let finalScore = score;
    if (volRatio > 1.5) finalScore *= (1 - w.volatility_weight);
    else if (volRatio < 0.5) finalScore *= (1 + w.volatility_weight);
    
    return parseFloat(finalScore.toFixed(2));
}

module.exports = { getOrderbookLevels, calculateWSS };
