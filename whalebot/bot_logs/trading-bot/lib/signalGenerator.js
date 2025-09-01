import chalk from 'chalk';
import { logger } from './utils.js';

export default class SignalGenerator {
  constructor() {
    this.riskPercentage = parseFloat(process.env.RISK_PERCENTAGE) || 1;
    this.minConfidence = 60;
    this.defaultRiskReward = 2;
  }

  async generateSignals(marketData, aiAnalysis) {
    try {
      const symbol = marketData.symbol || 'TRUMPUSDT';
      const currentPrice = marketData.currentPrice;
      
      logger.info(chalk.blue('🎯 Generating trading signals...'));
      
      // Determine action based on AI analysis and confidence
      let action = aiAnalysis.action;
      const confidence = aiAnalysis.confidence;
      
      // Override to HOLD if confidence is too low
      if (confidence < this.minConfidence && action !== 'HOLD') {
        logger.warn(chalk.yellow(`Confidence too low (${confidence}%), changing to HOLD`));
        action = 'HOLD';
      }

      // Generate signal based on action
      let signal = {
        symbol,
        currentPrice,
        action,
        confidence,
        reasoning: aiAnalysis.reasoning,
        keyFactors: aiAnalysis.keyFactors,
        riskLevel: aiAnalysis.riskLevel,
        trend: aiAnalysis.trend,
        trendStrength: aiAnalysis.strength
      };

      // Add entry, SL, TP for BUY/SELL signals
      if (action === 'BUY' || action === 'SELL') {
        const tradeSetup = this.calculateTradeSetup(
          currentPrice,
          action,
          marketData,
          aiAnalysis
        );
        signal = { ...signal, ...tradeSetup };
      }

      return signal;
      
    } catch (error) {
      logger.error(chalk.red('Error generating signals:', error));
      return this.getDefaultSignal(marketData);
    }
  }

  calculateTradeSetup(currentPrice, action, marketData, aiAnalysis) {
    const atr = marketData.atr || currentPrice * 0.002; // Default 0.2% if no ATR
    const riskReward = this.calculateRiskReward(aiAnalysis.confidence);
    
    let entry, stopLoss, takeProfit;
    
    if (action === 'BUY') {
      // For BUY signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'BUY', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'BUY');
      
    } else if (action === 'SELL') {
      // For SELL signals
      entry = currentPrice;
      stopLoss = this.calculateStopLoss(entry, atr, 'SELL', marketData);
      takeProfit = this.calculateTakeProfit(entry, stopLoss, riskReward, 'SELL');
    }

    // Calculate percentages
    const slPercentage = Math.abs((stopLoss - entry) / entry * 100);
    const tpPercentage = Math.abs((takeProfit - entry) / entry * 100);
    
    return {
      entry: this.roundPrice(entry),
      stopLoss: this.roundPrice(stopLoss),
      takeProfit: this.roundPrice(takeProfit),
      riskReward: riskReward.toFixed(2),
      slPercentage: slPercentage,
      tpPercentage: tpPercentage,
      positionSize: this.calculatePositionSize(entry, stopLoss),
      entryStrategy: aiAnalysis.entryStrategy,
      exitStrategy: aiAnalysis.exitStrategy
    };
  }

  calculateStopLoss(entry, atr, action, marketData) {
    // Ensure atr is a valid number, default to 0.2% of currentPrice if not
    const safeAtr = (typeof atr === 'number' && !isNaN(atr)) ? atr : (entry * 0.002);
    let stopDistance = safeAtr * 1.5; // 1.5x ATR as base

    // Adjust based on volatility, ensure marketData.adx is a number
    const adxValue = (typeof marketData.adx === 'number' && !isNaN(marketData.adx)) ? marketData.adx : 0;
    if (adxValue > 40) {
      stopDistance *= 1.2; // Wider stop for strong trends
    }

    // Consider Bollinger Bands, ensure bb_lower and bb_upper are numbers
    const bbLower = (typeof marketData.bb_lower === 'number' && !isNaN(marketData.bb_lower)) ? marketData.bb_lower : undefined;
    const bbUpper = (typeof marketData.bb_upper === 'number' && !isNaN(marketData.bb_upper)) ? marketData.bb_upper : undefined;

    if (action === 'BUY' && bbLower !== undefined) {
      const bbStop = entry - (entry - bbLower) * 0.5;
      return Math.min(entry - stopDistance, bbStop);
    } else if (action === 'SELL' && bbUpper !== undefined) {
      const bbStop = entry + (bbUpper - entry) * 0.5;
      return Math.max(entry + stopDistance, bbStop);
    }

    return action === 'BUY' ? entry - stopDistance : entry + stopDistance;
  }

  calculateTakeProfit(entry, stopLoss, riskReward, action) {
    const risk = Math.abs(entry - stopLoss);
    const reward = risk * riskReward;
    
    return action === 'BUY' ? entry + reward : entry - reward;
  }

  calculateRiskReward(confidence) {
    // Higher confidence = higher risk/reward ratio
    if (confidence >= 80) return 3;
    if (confidence >= 70) return 2.5;
    if (confidence >= 60) return 2;
    return 1.5;
  }

  calculatePositionSize(entry, stopLoss) {
    // Calculate position size based on risk percentage
    const accountBalance = 1000; // Default account balance
    const riskAmount = accountBalance * (this.riskPercentage / 100);
    const stopLossDistance = Math.abs(entry - stopLoss);
    const positionSize = riskAmount / stopLossDistance;
    
    return {
      units: this.roundSize(positionSize),
      riskAmount: riskAmount.toFixed(2),
      notionalValue: (positionSize * entry).toFixed(2)
    };
  }

  roundPrice(price) {
    // Round to appropriate decimal places based on price level
    if (price < 1) return parseFloat(price.toFixed(4));
    if (price < 10) return parseFloat(price.toFixed(3));
    if (price < 100) return parseFloat(price.toFixed(2));
    return parseFloat(price.toFixed(1));
  }

  roundSize(size) {
    if (size < 1) return parseFloat(size.toFixed(4));
    if (size < 10) return parseFloat(size.toFixed(2));
    return Math.round(size);
  }

  getDefaultSignal(marketData) {
    return {
      symbol: marketData.symbol || 'UNKNOWN',
      currentPrice: marketData.currentPrice || 0,
      action: 'HOLD',
      confidence: 0,
      reasoning: 'Unable to generate signal due to insufficient data',
      keyFactors: ['Error in signal generation'],
      riskLevel: 'HIGH',
      trend: 'UNKNOWN',
      trendStrength: 0
    };
  }

  logSignalSummary(signal) {
    console.log(chalk.cyan('\n' + '='.repeat(50)));
    console.log(chalk.white.bold('📊 SIGNAL SUMMARY'));
    console.log(chalk.cyan('='.repeat(50)));

    const actionColor = signal.action === 'BUY' ? chalk.green :
                       signal.action === 'SELL' ? chalk.red :
                       chalk.yellow;

    console.log(chalk.white(`Symbol: ${chalk.bold(signal.symbol || 'N/A')}`));
    console.log(chalk.white(`Action: ${actionColor.bold(signal.action || 'N/A')}`));
    console.log(chalk.white(`Current Price: ${chalk.bold(`$${typeof signal.currentPrice === 'number' && !isNaN(signal.currentPrice) ? signal.currentPrice.toFixed(2) : 'N/A'}`)}`));

    if (signal.action !== 'HOLD') {
      console.log(chalk.white(`Entry: ${chalk.bold(`$${typeof signal.entry === 'number' && !isNaN(signal.entry) ? signal.entry.toFixed(2) : 'N/A'}`)}`));
      console.log(chalk.green(`Take Profit: ${chalk.bold(`$${typeof signal.takeProfit === 'number' && !isNaN(signal.takeProfit) ? signal.takeProfit.toFixed(2) : 'N/A'}`)} (${typeof signal.tpPercentage === 'number' && !isNaN(signal.tpPercentage) ? signal.tpPercentage.toFixed(2) : 'N/A'}%)`));
      console.log(chalk.red(`Stop Loss: ${chalk.bold(`$${typeof signal.stopLoss === 'number' && !isNaN(signal.stopLoss) ? signal.stopLoss.toFixed(2) : 'N/A'}`)} (${typeof signal.slPercentage === 'number' && !isNaN(signal.slPercentage) ? signal.slPercentage.toFixed(2) : 'N/A'}%)`));
      console.log(chalk.white(`Risk/Reward: ${chalk.bold(signal.riskReward || 'N/A')}`));
    }

    console.log(chalk.white(`Confidence: ${this.getConfidenceBar(signal.confidence || 0)}`));
    console.log(chalk.white(`Reasoning: ${signal.reasoning || 'No specific reasoning provided.'}`));
    console.log(chalk.cyan('='.repeat(50) + '\n'));
  }
}