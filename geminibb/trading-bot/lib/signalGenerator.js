import chalk from 'chalk';
import { logger } from './utils.js';

// Custom Error Class for Signal Generation
class SignalError extends Error {
  constructor(message, details = {}) {
    super(message);
    this.name = 'SignalError';
    this.details = details;
  }
}

export default class SignalGenerator {
  constructor(tradingSymbol, options = {}) {
    this.tradingSymbol = tradingSymbol;
    
    // Enhanced configuration with backward compatibility
    this.config = {
      riskPercentage: parseFloat(process.env.RISK_PERCENTAGE) || options.riskPercentage || 1,
      minConfidence: options.minConfidence || 60,
      maxConfidence: options.maxConfidence || 95,
      defaultRiskReward: options.defaultRiskReward || 2,
      maxRiskPerTrade: options.maxRiskPerTrade || 2,
      accountBalance: parseFloat(process.env.ACCOUNT_BALANCE) || options.accountBalance || 1000,
      leverage: options.leverage || 1,
      useKellyFormula: options.useKellyFormula || false,
      useTrailingStop: options.useTrailingStop || false,
      trailingStopDistance: options.trailingStopDistance || 0.5,
      partialTakeProfits: options.partialTakeProfits !== false,
      debugMode: options.debugMode || false,
      ...options
    };
    
    // Backward compatibility
    this.riskPercentage = this.config.riskPercentage;
    this.minConfidence = this.config.minConfidence;
    this.defaultRiskReward = this.config.defaultRiskReward;
    
    // Signal history for pattern analysis
    this.signalHistory = [];
    this.maxHistorySize = options.maxHistorySize || 100;
    
    // Performance tracking
    this.metrics = {
      totalSignals: 0,
      buySignals: 0,
      sellSignals: 0,
      holdSignals: 0,
      averageConfidence: 0,
      signalAccuracy: [],
      lastSignalTime: null
    };
    
    // Market regime detection
    this.marketRegimes = {
      TRENDING_UP: { slMultiplier: 0.8, tpMultiplier: 1.5 },
      TRENDING_DOWN: { slMultiplier: 0.8, tpMultiplier: 1.5 },
      RANGING: { slMultiplier: 1.2, tpMultiplier: 0.8 },
      HIGH_VOLATILITY: { slMultiplier: 1.5, tpMultiplier: 1.2 },
      LOW_VOLATILITY: { slMultiplier: 0.7, tpMultiplier: 1.0 }
    };
    
    // Price precision mapping
    this.pricePrecision = {
      BTC: 2,
      ETH: 2,
      default: 4
    };
  }

  async generateSignals(marketData, aiAnalysis) {
    const startTime = Date.now();
    this.metrics.totalSignals++;
    
    try {
      const symbol = this.tradingSymbol;
      const currentPrice = marketData.currentPrice;
      
      if (!currentPrice || isNaN(currentPrice)) {
        throw new Error('Invalid current price in market data');
      }
      
      logger.info(chalk.hex('#00FFFF').bold('🎯 Generating trading signals...'));
      
      // Validate AI analysis
      const validatedAnalysis = this.validateAIAnalysis(aiAnalysis);
      
      // Detect market regime
      const marketRegime = this.detectMarketRegime(marketData);
      
      // Determine action with advanced filtering
      let action = this.determineAction(validatedAnalysis, marketData, marketRegime);
      const confidence = validatedAnalysis.confidence;
      
      // Apply confidence threshold
      if (confidence < this.minConfidence && action !== 'HOLD') {
        logger.warn(chalk.hex('#FFFF00').bold(`Confidence too low (${confidence}%), changing to HOLD`));
        action = 'HOLD';
      }
      
      // Check for signal conflicts
      const conflictCheck = this.checkSignalConflicts(action, marketData);
      if (conflictCheck.hasConflict) {
        logger.warn(chalk.yellow(`Signal conflict detected: ${conflictCheck.reason}`));
        if (conflictCheck.override) {
          action = 'HOLD';
        }
      }

      // Build base signal
      let signal = {
        symbol,
        currentPrice: this.roundPrice(currentPrice),
        action,
        confidence,
        adjustedConfidence: this.adjustConfidence(confidence, marketRegime),
        reasoning: validatedAnalysis.reasoning,
        confidenceReasoning: validatedAnalysis.confidenceReasoning,
        keyFactors: validatedAnalysis.keyFactors,
        riskLevel: validatedAnalysis.riskLevel,
        trend: validatedAnalysis.trend,
        trendStrength: validatedAnalysis.strength || validatedAnalysis.trendStrength,
        marketRegime,
        timestamp: new Date().toISOString(),
        processingTime: Date.now() - startTime
      };

      // Add trade setup for actionable signals
      if (action === 'BUY' || action === 'SELL') {
        const tradeSetup = this.calculateAdvancedTradeSetup(
          currentPrice,
          action,
          marketData,
          validatedAnalysis,
          marketRegime
        );
        signal = { ...signal, ...tradeSetup };
        
        // Update metrics
        action === 'BUY' ? this.metrics.buySignals++ : this.metrics.sellSignals++;
      } else {
        this.metrics.holdSignals++;
      }
      
      // Calculate signal quality score
      signal.qualityScore = this.calculateSignalQuality(signal, marketData);
      
      // Add to history
      this.addToHistory(signal);
      
      // Update metrics
      this.updateMetrics(signal);
      
      // Log summary if not in quiet mode
      if (!this.config.quietMode) {
        this.logSignalSummary(signal);
      }
      
      return signal;
      
    } catch (error) {
      logger.error(chalk.hex('#FF00FF').bold('Error generating signals:'), error);
      return this.getDefaultSignal(marketData);
    }
  }

  validateAIAnalysis(aiAnalysis) {
    // Ensure all required fields exist
    return {
      action: aiAnalysis.action || 'HOLD',
      confidence: this.clamp(aiAnalysis.confidence || 0, 0, 100),
      reasoning: aiAnalysis.reasoning || 'No reasoning provided',
      confidenceReasoning: aiAnalysis.confidenceReasoning || '',
      keyFactors: Array.isArray(aiAnalysis.keyFactors) ? aiAnalysis.keyFactors : [],
      riskLevel: aiAnalysis.riskLevel || 'MEDIUM',
      trend: aiAnalysis.trend || 'NEUTRAL',
      strength: aiAnalysis.strength || aiAnalysis.trendStrength || 50,
      entryStrategy: aiAnalysis.entryStrategy || '',
      exitStrategy: aiAnalysis.exitStrategy || '',
      stopLoss: aiAnalysis.stopLoss,
      takeProfit: aiAnalysis.takeProfit,
      indicatorAlignment: aiAnalysis.indicatorAlignment || {}
    };
  }

  detectMarketRegime(marketData) {
    const { adx, atr, bb_upper, bb_lower, currentPrice, volatilityIndex } = marketData;
    
    // Calculate volatility metrics
    const bbWidth = bb_upper && bb_lower ? bb_upper - bb_lower : 0;
    const bbWidthPercent = currentPrice ? (bbWidth / currentPrice) * 100 : 0;
    const volatility = volatilityIndex || (atr / currentPrice) * 100;
    
    // Determine regime based on indicators
    if (adx > 40 && marketData.trend === 'BULLISH') {
      return 'TRENDING_UP';
    } else if (adx > 40 && marketData.trend === 'BEARISH') {
      return 'TRENDING_DOWN';
    } else if (volatility > 2 || bbWidthPercent > 3) {
      return 'HIGH_VOLATILITY';
    } else if (volatility < 0.5 || bbWidthPercent < 1) {
      return 'LOW_VOLATILITY';
    } else {
      return 'RANGING';
    }
  }

  determineAction(aiAnalysis, marketData, marketRegime) {
    let action = aiAnalysis.action;
    
    // Apply regime-based adjustments
    if (marketRegime === 'HIGH_VOLATILITY' && aiAnalysis.confidence < 70) {
      logger.info(chalk.yellow('High volatility detected with low confidence - reducing position'));
      // Don't change action but will adjust position size later
    }
    
    // Check for divergences
    const divergence = this.checkDivergences(marketData);
    if (divergence.exists) {
      logger.warn(chalk.yellow(`${divergence.type} divergence detected`));
      if (divergence.strength > 0.7 && action !== 'HOLD') {
        aiAnalysis.confidence *= 0.8; // Reduce confidence
      }
    }
    
    return action;
  }

  checkDivergences(marketData) {
    const divergence = { exists: false, type: null, strength: 0 };
    
    // RSI divergence
    if (marketData.rsi && marketData.priceChangePercent) {
      const priceUp = marketData.priceChangePercent > 0;
      const rsiOverbought = marketData.rsi > 70;
      const rsiOversold = marketData.rsi < 30;
      
      if (priceUp && rsiOverbought) {
        divergence.exists = true;
        divergence.type = 'BEARISH_RSI';
        divergence.strength = (marketData.rsi - 70) / 30;
      } else if (!priceUp && rsiOversold) {
        divergence.exists = true;
        divergence.type = 'BULLISH_RSI';
        divergence.strength = (30 - marketData.rsi) / 30;
      }
    }
    
    // MACD divergence
    if (marketData.macd_hist && marketData.macd_signal) {
      const macdBullish = marketData.macd_hist > 0;
      const priceTrend = marketData.ema_short > marketData.ema_long;
      
      if (macdBullish !== priceTrend) {
        divergence.exists = true;
        divergence.type = macdBullish ? 'BULLISH_MACD' : 'BEARISH_MACD';
        divergence.strength = Math.min(Math.abs(marketData.macd_hist) * 1000, 1);
      }
    }
    
    return divergence;
  }

  checkSignalConflicts(action, marketData) {
    const conflicts = { hasConflict: false, reason: '', override: false };
    
    // Check if action conflicts with major indicators
    if (action === 'BUY') {
      if (marketData.rsi > 80) {
        conflicts.hasConflict = true;
        conflicts.reason = 'RSI extremely overbought';
        conflicts.override = marketData.rsi > 85;
      }
      if (marketData.currentPrice > marketData.bb_upper * 1.02) {
        conflicts.hasConflict = true;
        conflicts.reason = 'Price far above Bollinger Band';
      }
    } else if (action === 'SELL') {
      if (marketData.rsi < 20) {
        conflicts.hasConflict = true;
        conflicts.reason = 'RSI extremely oversold';
        conflicts.override = marketData.rsi < 15;
      }
      if (marketData.currentPrice < marketData.bb_lower * 0.98) {
        conflicts.hasConflict = true;
        conflicts.reason = 'Price far below Bollinger Band';
      }
    }
    
    return conflicts;
  }

  calculateAdvancedTradeSetup(currentPrice, action, marketData, aiAnalysis, marketRegime) {
    const atr = this.validateATR(marketData.atr, currentPrice);
    const regimeConfig = this.marketRegimes[marketRegime] || this.marketRegimes.RANGING;
    const riskReward = this.calculateDynamicRiskReward(aiAnalysis.confidence, marketRegime);
    
    let entry, stopLoss, takeProfits;
    
    // Calculate entry with potential improvement
    entry = this.calculateImprovedEntry(currentPrice, action, marketData);
    
    // Calculate stop loss with regime adjustment
    stopLoss = this.calculateAdvancedStopLoss(
      entry, 
      atr, 
      action, 
      marketData, 
      regimeConfig.slMultiplier
    );
    
    // Calculate multiple take profit levels
    if (this.config.partialTakeProfits) {
      takeProfits = this.calculateMultipleTakeProfits(
        entry,
        stopLoss,
        riskReward,
        action,
        regimeConfig.tpMultiplier
      );
    } else {
      // Single take profit for backward compatibility
      const tp = this.calculateTakeProfit(entry, stopLoss, riskReward, action);
      takeProfits = [{ level: tp, percentage: 100 }];
    }
    
    // Calculate position size with Kelly criterion if enabled
    const positionSize = this.config.useKellyFormula 
      ? this.calculateKellyPosition(entry, stopLoss, aiAnalysis.confidence)
      : this.calculatePositionSize(entry, stopLoss);
    
    // Calculate percentages and risk metrics
    const slPercentage = Math.abs((stopLoss - entry) / entry * 100);
    const tpPercentages = takeProfits.map(tp => ({
      level: tp.level,
      percentage: tp.percentage,
      returnPercent: Math.abs((tp.level - entry) / entry * 100)
    }));
    
    // Build trade setup
    const setup = {
      entry: this.roundPrice(entry),
      stopLoss: this.roundPrice(stopLoss),
      takeProfit: this.roundPrice(takeProfits.level), // Primary TP for compatibility
      takeProfits: takeProfits.map(tp => ({
        ...tp,
        level: this.roundPrice(tp.level)
      })),
      riskReward: riskReward.toFixed(2),
      slPercentage: slPercentage.toFixed(2),
      tpPercentage: tpPercentages.returnPercent.toFixed(2),
      tpPercentages,
      positionSize,
      entryStrategy: this.enhanceEntryStrategy(aiAnalysis.entryStrategy, marketData),
      exitStrategy: this.enhanceExitStrategy(aiAnalysis.exitStrategy, marketData),
      maxRisk: this.calculateMaxRisk(entry, stopLoss, positionSize.units),
      expectedReturn: this.calculateExpectedReturn(
        entry, 
        takeProfits,
        aiAnalysis.confidence
      )
    };
    
    // Add trailing stop if enabled
    if (this.config.useTrailingStop) {
      setup.trailingStop = {
        enabled: true,
        distance: atr * this.config.trailingStopDistance,
        activationLevel: entry + (action === 'BUY' ? atr : -atr)
      };
    }
    
    return setup;
  }

  calculateImprovedEntry(currentPrice, action, marketData) {
    let entry = currentPrice;
    
    // Try to get better entry using VWAP or moving averages
    if (marketData.vwap && !isNaN(marketData.vwap)) {
      const vwapDiff = Math.abs(currentPrice - marketData.vwap) / currentPrice;
      
      if (vwapDiff < 0.005) { // Within 0.5% of VWAP
        entry = marketData.vwap;
      } else if (action === 'BUY' && currentPrice > marketData.vwap) {
        entry = currentPrice * 0.998; // Slightly below current for better entry
      } else if (action === 'SELL' && currentPrice < marketData.vwap) {
        entry = currentPrice * 1.002; // Slightly above current for better entry
      }
    }
    
    return entry;
  }

  calculateAdvancedStopLoss(entry, atr, action, marketData, multiplier = 1) {
    const safeAtr = this.validateATR(atr, entry);
    let stopDistance = safeAtr * 1.5 * multiplier;
    
    // Dynamic adjustment based on multiple factors
    const factors = [];
    
    // ADX-based adjustment
    if (marketData.adx && !isNaN(marketData.adx)) {
      if (marketData.adx > 40) {
        stopDistance *= 1.2;
        factors.push('strong_trend');
      } else if (marketData.adx < 20) {
        stopDistance *= 0.8;
        factors.push('weak_trend');
      }
    }
    
    // Volatility-based adjustment
    if (marketData.volatilityIndex && !isNaN(marketData.volatilityIndex)) {
      const volMultiplier = 1 + (marketData.volatilityIndex - 1) * 0.3;
      stopDistance *= Math.max(0.7, Math.min(1.5, volMultiplier));
      factors.push('volatility_adjusted');
    }
    
    // Support/Resistance levels
    let structuralStop = null;
    
    if (action === 'BUY') {
      // Check key support levels
      const supports = [
        marketData.s1,
        marketData.s2,
        marketData.bb_lower,
        marketData.ema_long
      ].filter(s => s && !isNaN(s) && s < entry);
      
      if (supports.length > 0) {
        structuralStop = Math.max(...supports) * 0.998; // Just below support
      }
    } else { // action === 'SELL'
      // Check key resistance levels
      const resistances = [
        marketData.r1,
        marketData.r2,
        marketData.bb_upper,
        marketData.ema_long
      ].filter(r => r && !isNaN(r) && r > entry);
      
      if (resistances.length > 0) {
        structuralStop = Math.min(...resistances) * 1.002; // Just above resistance
      }
    }
    
    // Calculate final stop
    const atrStop = action === 'BUY' ? entry - stopDistance : entry + stopDistance;
    
    if (structuralStop) {
      // Use tighter of the two stops
      if (action === 'BUY') {
        return Math.max(atrStop, structuralStop);
      } else { // action === 'SELL'
        return Math.min(atrStop, structuralStop);
      }
    }
    
    return atrStop;
  }

  calculateMultipleTakeProfits(entry, stopLoss, baseRiskReward, action, multiplier = 1) {
    const risk = Math.abs(entry - stopLoss);
    const takeProfits = [];
    
    // TP1: Conservative (50% position)
    const tp1Distance = risk * baseRiskReward * 0.75 * multiplier;
    takeProfits.push({
      level: action === 'BUY' ? entry + tp1Distance : entry - tp1Distance,
      percentage: 50,
      riskReward: (baseRiskReward * 0.75).toFixed(2)
    });
    
    // TP2: Target (30% position)
    const tp2Distance = risk * baseRiskReward * multiplier;
    takeProfits.push({
      level: action === 'BUY' ? entry + tp2Distance : entry - tp2Distance,
      percentage: 30,
      riskReward: baseRiskReward.toFixed(2)
    });
    
    // TP3: Extended (20% position)
    const tp3Distance = risk * baseRiskReward * 1.5 * multiplier;
    takeProfits.push({
      level: action === 'BUY' ? entry + tp3Distance : entry - tp3Distance,
      percentage: 20,
      riskReward: (baseRiskReward * 1.5).toFixed(2)
    });
    
    return takeProfits;
  }

  calculateDynamicRiskReward(confidence, marketRegime) {
    let baseRR = this.defaultRiskReward;
    
    // Confidence-based adjustment
    if (confidence >= 85) baseRR = 3.5;
    else if (confidence >= 75) baseRR = 2.8;
    else if (confidence >= 65) baseRR = 2.2;
    else if (confidence >= 55) baseRR = 1.8;
    else baseRR = 1.5;
    
    // Regime-based adjustment
    const regimeMultipliers = {
      'TRENDING_UP': 1.2,
      'TRENDING_DOWN': 1.2,
      'RANGING': 0.8,
      'HIGH_VOLATILITY': 0.9,
      'LOW_VOLATILITY': 1.1
    };
    
    baseRR *= regimeMultipliers[marketRegime] || 1;
    
    return Math.max(1.2, Math.min(5, baseRR)); // Clamp between 1.2 and 5
  }

  calculateKellyPosition(entry, stopLoss, confidence) {
    // Kelly Criterion: f = (p * b - q) / b
    // where f = fraction to bet, p = probability of win, b = odds, q = probability of loss
    
    const winProbability = confidence / 100;
    const lossProbability = 1 - winProbability;
    const winAmount = Math.abs(this.calculateTakeProfit(entry, stopLoss, 2, 'BUY') - entry); // Assuming a base RR of 2 for win amount calculation
    const lossAmount = Math.abs(stopLoss - entry);
    const odds = winAmount / lossAmount;
    
    let kellyFraction = (winProbability * odds - lossProbability) / odds;
    
    // Apply Kelly fraction cap (never risk more than 25% even with perfect setup)
    kellyFraction = Math.max(0, Math.min(0.25, kellyFraction));
    
    // Calculate position size
    const accountBalance = this.config.accountBalance;
    const riskAmount = accountBalance * kellyFraction;
    const positionSize = riskAmount / lossAmount;
    
    return {
      units: this.roundSize(positionSize),
      riskAmount: riskAmount.toFixed(2),
      notionalValue: (positionSize * entry).toFixed(2),
      kellyFraction: (kellyFraction * 100).toFixed(2) + '%'
    };
  }

  calculateTakeProfit(entry, stopLoss, riskReward, action) {
    const risk = Math.abs(entry - stopLoss);
    const reward = risk * riskReward;
    return action === 'BUY' ? entry + reward : entry - reward;
  }

  calculatePositionSize(entry, stopLoss) {
    const accountBalance = this.config.accountBalance;
    const riskAmount = accountBalance * (this.riskPercentage / 100);
    
    // Apply max risk cap
    const maxRiskAmount = accountBalance * (this.config.maxRiskPerTrade / 100);
    const finalRiskAmount = Math.min(riskAmount, maxRiskAmount);
    
    const stopLossDistance = Math.abs(entry - stopLoss);
    const positionSize = finalRiskAmount / stopLossDistance;
    
    // Apply leverage if configured
    const leveragedPosition = positionSize * this.config.leverage;
    
    return {
      units: this.roundSize(leveragedPosition),
      riskAmount: finalRiskAmount.toFixed(2),
      notionalValue: (leveragedPosition * entry).toFixed(2),
      leverage: this.config.leverage
    };
  }

  calculateMaxRisk(entry, stopLoss, units) {
    const stopDistance = Math.abs(entry - stopLoss);
    return (stopDistance * units).toFixed(2);
  }

  calculateExpectedReturn(entry, takeProfits, confidence) {
    const winProbability = confidence / 100;
    let expectedReturn = 0;
    
    for (const tp of takeProfits) {
      const profit = Math.abs(tp.level - entry);
      const positionPercent = tp.percentage / 100;
      expectedReturn += profit * positionPercent * winProbability;
    }
    
    return expectedReturn.toFixed(4);
  }

  enhanceEntryStrategy(baseStrategy, marketData) {
    const strategies = [];
    
    if (baseStrategy) strategies.push(baseStrategy);
    
    // Add technical entry conditions
    if (marketData.rsi < 30) {
      strategies.push('RSI oversold bounce');
    } else if (marketData.rsi > 70) {
      strategies.push('RSI overbought reversal');
    }
    
    if (marketData.currentPrice <= marketData.bb_lower) {
      strategies.push('Bollinger Band squeeze entry');
    }
    
    if (marketData.macd_hist > 0 && marketData.macd_signal > 0) {
      strategies.push('MACD bullish crossover');
    }
    
    return strategies.join('; ') || 'Market order at current price';
  }

  enhanceExitStrategy(baseStrategy, marketData) {
    const strategies = [];
    
    if (baseStrategy) strategies.push(baseStrategy);
    
    // Add dynamic exit conditions
    strategies.push('Partial profits at multiple targets');
    
    if (this.config.useTrailingStop) {
      strategies.push('Trailing stop activation after first target');
    }
    
    if (marketData.volatilityIndex > 2) {
      strategies.push('Tighten stops in high volatility');
    }
    
    return strategies.join('; ') || 'Fixed stop loss and take profit';
  }

  validateATR(atr, currentPrice) {
    if (typeof atr === 'number' && !isNaN(atr) && atr > 0) {
      return atr;
    }
    // Default to 0.2% of current price if ATR is invalid
    return currentPrice * 0.002;
  }

  adjustConfidence(baseConfidence, marketRegime) {
    let adjusted = baseConfidence;
    
    // Regime-based adjustments
    const adjustments = {
      'HIGH_VOLATILITY': -10,
      'LOW_VOLATILITY': +5,
      'TRENDING_UP': +5,
      'TRENDING_DOWN': +5,
      'RANGING': -5
    };
    
    adjusted += adjustments[marketRegime] || 0;
    
    return this.clamp(adjusted, 0, 100);
  }

  calculateSignalQuality(signal, marketData) {
    let quality = 0;
    const weights = {
      confidence: 0.3,
      riskReward: 0.2,
      trendAlignment: 0.2,
      volumeConfirmation: 0.15,
      indicatorConfluence: 0.15
    };
    
    // Confidence component
    quality += (signal.confidence / 100) * weights.confidence;
    
    // Risk/Reward component
    const rrScore = Math.min(parseFloat(signal.riskReward) / 3, 1);
    quality += rrScore * weights.riskReward;
    
    // Trend alignment
    const trendAligned = 
      (signal.action === 'BUY' && signal.trend === 'BULLISH') ||
      (signal.action === 'SELL' && signal.trend === 'BEARISH');
    quality += (trendAligned ? 1 : 0.5) * weights.trendAlignment;
    
    // Volume confirmation
    const volumeConfirms = marketData.obv > marketData.obv_ema;
    quality += (volumeConfirms ? 1 : 0.5) * weights.volumeConfirmation;
    
    // Indicator confluence (simplified)
    const indicators = signal.keyFactors || [];
    const confluenceScore = Math.min(indicators.length / 5, 1);
    quality += confluenceScore * weights.indicatorConfluence;
    
    return Math.round(quality * 100);
  }

  roundPrice(price) {
    if (typeof price !== 'number' || isNaN(price)) return 0;
    
    // Get precision for specific symbol or use default
    const symbolBase = this.tradingSymbol?.replace('USDT', '').replace('USD', '');
    const precision = this.pricePrecision[symbolBase] || this.pricePrecision.default;
    
    if (price < 0.0001) return parseFloat(price.toFixed(8));
    if (price < 0.001) return parseFloat(price.toFixed(6));
    if (price < 1) return parseFloat(price.toFixed(precision));
    if (price < 10) return parseFloat(price.toFixed(Math.max(precision - 1, 2)));
    if (price < 100) return parseFloat(price.toFixed(Math.max(precision - 2, 2)));
    return parseFloat(price.toFixed(2));
  }

  roundSize(size) {
    if (typeof size !== 'number' || isNaN(size)) return 0;
    
    if (size < 0.0001) return parseFloat(size.toFixed(8));
    if (size < 1) return parseFloat(size.toFixed(4));
    if (size < 10) return parseFloat(size.toFixed(2));
    if (size < 100) return parseFloat(size.toFixed(1));
    return Math.round(size);
  }

  getDefaultSignal(marketData) {
    return {
      symbol: this.tradingSymbol || marketData.symbol || 'UNKNOWN',
      currentPrice: marketData.currentPrice || 0,
      action: 'HOLD',
      confidence: 0,
      adjustedConfidence: 0,
      reasoning: 'Unable to generate signal due to insufficient data or error',
      confidenceReasoning: 'No confidence analysis available',
      keyFactors: ['Error in signal generation', 'Manual review recommended'],
      riskLevel: 'HIGH',
      trend: 'UNKNOWN',
      trendStrength: 0,
      marketRegime: 'UNKNOWN',
      qualityScore: 0,
      timestamp: new Date().toISOString()
    };
  }

  getConfidenceBar(confidence) {
    const clampedConfidence = this.clamp(confidence, 0, 100);
    const filledBars = Math.round(clampedConfidence / 10);
    const emptyBars = 10 - filledBars;
    
    let bar = '';
    let color;
    
    if (clampedConfidence >= 80) {
      color = chalk.hex('#00FF00'); // Neon green
    } else if (clampedConfidence >= 60) {
      color = chalk.hex('#FFFF00'); // Neon yellow
    } else if (clampedConfidence >= 40) {
      color = chalk.hex('#FFA500'); // Neon orange
    } else {
      color = chalk.hex('#FF00FF'); // Neon pink
    }
    
    bar += color('█'.repeat(filledBars));
    bar += chalk.gray('░'.repeat(emptyBars));
    bar += ` ${clampedConfidence}%`;
    
    return bar;
  }

  logSignalSummary(signal) {
    // Neon colors
    const neonGreen = chalk.hex('#00FF00');
    const neonBlue = chalk.hex('#00FFFF');
    const neonPink = chalk.hex('#FF00FF');
    const neonYellow = chalk.hex('#FFFF00');
    const neonOrange = chalk.hex('#FFA500');
    const darkGray = chalk.hex('#555555');
    const white = chalk.white;

    console.log(neonBlue('\n' + '═'.repeat(60)));
    console.log(neonPink.bold('📊 TRADING SIGNAL SUMMARY'));
    console.log(neonBlue('═'.repeat(60)));

    const actionColor = signal.action === 'BUY' ? neonGreen :
                       signal.action === 'SELL' ? neonPink :
                       neonYellow;

    // Basic Information
    console.log(white(`Symbol: ${neonYellow.bold(this.tradingSymbol || 'N/A')}`));
    console.log(white(`Action: ${actionColor.bold(signal.action || 'N/A')}`));
    console.log(white(`Market Regime: ${neonBlue.bold(signal.marketRegime || 'UNKNOWN')}`));
    console.log(white(`Current Price: ${neonGreen.bold(`$${signal.currentPrice?.toFixed?.(4) || 'N/A'}`)}`));

    // Trade Setup (if not HOLD)
    if (signal.action !== 'HOLD') {
      console.log(neonBlue('\n--- Trade Setup ---'));
      console.log(white(`Entry: ${neonGreen.bold(`$${signal.entry?.toFixed?.(4) || 'N/A'}`)}`));
      
      // Multiple take profits if available
      if (signal.takeProfits && signal.takeProfits.length > 0) {
        console.log(white('Take Profits:'));
        signal.takeProfits.forEach((tp, index) => {
          const tpReturn = ((tp.level - signal.entry) / signal.entry * 100).toFixed(2);
          console.log(neonGreen(`  TP${index + 1}: $${tp.level.toFixed(4)} (${tp.percentage}% position, +${tpReturn}%)`));
        });
      } else {
        console.log(neonGreen(`Take Profit: ${neonGreen.bold(`$${signal.takeProfit?.toFixed?.(4) || 'N/A'}`)} (+${signal.tpPercentage || 'N/A'}%)`));
      }
      
      console.log(neonPink(`Stop Loss: ${neonPink.bold(`$${signal.stopLoss?.toFixed?.(4) || 'N/A'}`)} (-${signal.slPercentage || 'N/A'}%)`));
      console.log(white(`Risk/Reward: ${neonOrange.bold(signal.riskReward || 'N/A')}`));
      
      // Position sizing
      if (signal.positionSize) {
        console.log(neonBlue('\n--- Position Sizing ---'));
        console.log(white(`Units: ${signal.positionSize.units}`));
        console.log(white(`Risk Amount: $${signal.positionSize.riskAmount}`));
        console.log(white(`Notional Value: $${signal.positionSize.notionalValue}`));
        if (signal.positionSize.kellyFraction) {
          console.log(white(`Kelly Fraction: ${signal.positionSize.kellyFraction}`));
        }
      }
      
      // Trailing stop if enabled
      if (signal.trailingStop) {
        console.log(neonBlue('\n--- Trailing Stop ---'));
        console.log(white(`Activation: $${signal.trailingStop.activationLevel?.toFixed?.(4) || 'N/A'}`));
        console.log(white(`Distance: $${signal.trailingStop.distance?.toFixed?.(4) || 'N/A'}`));
      }
    }

    // Analysis
    console.log(neonBlue('\n--- Analysis ---'));
    console.log(white(`Confidence: ${this.getConfidenceBar(signal.confidence || 0)}`));
    console.log(white(`Quality Score: ${this.getConfidenceBar(signal.qualityScore || 0)}`));
    console.log(white(`Risk Level: ${signal.riskLevel === 'HIGH' ? neonPink.bold(signal.riskLevel) :
                                     signal.riskLevel === 'MEDIUM' ? neonYellow.bold(signal.riskLevel) :
                                     neonGreen.bold(signal.riskLevel || 'UNKNOWN')}`));
    console.log(white(`Trend: ${signal.trend} (Strength: ${signal.trendStrength || 0})`));
    
    // Reasoning
    if (signal.confidenceReasoning) {
      console.log(darkGray(`\nConfidence Reasoning: ${signal.confidenceReasoning}`));
    }
    
    if (signal.reasoning) {
      console.log(darkGray(`Signal Reasoning: ${signal.reasoning}`));
    }
    
    // Key Factors
    if (signal.keyFactors && signal.keyFactors.length > 0) {
      console.log(neonBlue('\n--- Key Factors ---'));
      signal.keyFactors.forEach((factor, index) => {
        console.log(darkGray(`  ${index + 1}. ${factor}`));
      });
    }
    
    // Entry/Exit Strategies
    if (signal.entryStrategy || signal.exitStrategy) {
      console.log(neonBlue('\n--- Strategy ---'));
      if (signal.entryStrategy) {
        console.log(white(`Entry: ${signal.entryStrategy}`));
      }
      if (signal.exitStrategy) {
        console.log(white(`Exit: ${signal.exitStrategy}`));
      }
    }

    console.log(neonBlue('═'.repeat(60) + '\n'));
  }

  // History and metrics methods
  addToHistory(signal) {
    this.signalHistory.push({
      timestamp: signal.timestamp,
      symbol: signal.symbol,
      action: signal.action,
      confidence: signal.confidence,
      price: signal.currentPrice,
      qualityScore: signal.qualityScore
    });
    
    // Limit history size
    if (this.signalHistory.length > this.maxHistorySize) {
      this.signalHistory.shift();
    }
  }

  updateMetrics(signal) {
    // Update average confidence
    const allConfidences = this.signalHistory.map(s => s.confidence);
    this.metrics.averageConfidence = allConfidences.length > 0
      ? allConfidences.reduce((a, b) => a + b, 0) / allConfidences.length
      : 0;
    
    this.metrics.lastSignalTime = new Date().toISOString();
  }

  getMetrics() {
    return {
      ...this.metrics,
      signalDistribution: {
        buy: ((this.metrics.buySignals / this.metrics.totalSignals) * 100).toFixed(1) + '%',
        sell: ((this.metrics.sellSignals / this.metrics.totalSignals) * 100).toFixed(1) + '%',
        hold: ((this.metrics.holdSignals / this.metrics.totalSignals) * 100).toFixed(1) + '%'
      },
      historySize: this.signalHistory.length
    };
  }

  getRecentSignals(count = 10) {
    return this.signalHistory.slice(-count);
  }

  // Utility methods
  clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  clearHistory() {
    this.signalHistory = [];
    logger.info(chalk.green('Signal history cleared'));
  }
}
