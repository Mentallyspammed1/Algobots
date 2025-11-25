# 🌊 WHALEWAVE PRO - TITAN EDITION v7.0

> **Professional Cryptocurrency Trading Bot with AI-Powered Analysis**

[![Version](https://img.shields.io/badge/version-7.0.0-blue.svg)](https://github.com/yourusername/whalewave-titan)
[![Node.js](https://img.shields.io/badge/node-%3E%3D18.0.0-brightgreen.svg)](https://nodejs.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Paper Trading](https://img.shields.io/badge/trading-paper--trading-orange.svg)](#)

A sophisticated, institutional-grade cryptocurrency trading bot featuring:

- 🤖 **AI-Powered Analysis** using Google Gemini
- 📊 **25+ Technical Indicators** with optimized algorithms
- ⚖️ **Advanced Risk Management** with position sizing
- 🎨 **Real-time Dashboard** with color-coded metrics
- 🔧 **Modular Architecture** for easy customization
- 🛡️ **Production-Ready** with comprehensive error handling

---

## 🚀 Quick Start

### Automated Setup (Recommended)

```bash
# Clone or download the project
cd whalewave-titan-refactored

# Run the setup script
node setup.js
```

The setup script will:
- ✅ Check system requirements
- 📦 Install dependencies
- ⚙️ Create configuration files
- 🔐 Set up environment templates
- 🚀 Optionally start the bot

### Manual Setup

1. **Install Dependencies**
```bash
npm install
```

2. **Environment Configuration**
```bash
# Copy template and edit
cp .env.example .env
# Add your GEMINI_API_KEY to .env
```

3. **Start Trading**
```bash
npm start
```

---

## 📋 Requirements

### System Requirements
- **Node.js**: 18.0.0 or higher
- **Memory**: 512MB minimum (1GB recommended)
- **Network**: Stable internet connection for API access

### API Keys
- **Google Gemini AI**: Get free key at [AI Studio](https://makersuite.google.com/app/apikey)

### Exchanges
- Currently supports **Bybit** (additional exchanges coming soon)

---

## ⚙️ Configuration

### Basic Configuration (`config.json`)

```json
{
  "symbol": "BTCUSDT",
  "intervals": { "main": "3", "trend": "15" },
  "risk": {
    "initialBalance": 1000.00,
    "riskPercent": 2.0,
    "maxDrawdown": 10.0
  },
  "ai": {
    "minConfidence": 0.75
  }
}
```

### Environment Variables (`.env`)

```env
# Required
GEMINI_API_KEY=your_api_key_here

# Optional
NODE_ENV=development
LOG_LEVEL=info
```

### Advanced Settings

#### Trading Parameters
- `symbol`: Trading pair (e.g., BTCUSDT, ETHUSDT)
- `intervals.main`: Primary chart timeframe (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d)
- `intervals.trend`: Higher timeframe for trend analysis
- `limits.kline`: Number of candles to fetch (100-1000)

#### Risk Management
- `risk.initialBalance`: Starting balance for paper trading
- `risk.riskPercent`: Risk per trade as percentage of balance
- `risk.maxDrawdown`: Maximum allowable drawdown before stopping
- `risk.dailyLossLimit`: Daily loss limit as percentage

#### AI Configuration
- `ai.minConfidence`: Minimum AI confidence to execute trades
- `ai.model`: Gemini model name (default: gemini-1.5-flash)

---

## 🎯 Trading Strategies

### 1. **TREND_FOLLOWING**
- **Entry**: Pullback to VWAP/EMA in trend direction
- **Best For**: Strong trending markets
- **WSS Threshold**: > 1.5

### 2. **BREAKOUT_TRADING**
- **Entry**: Volatility expansion after squeeze
- **Best For**: Range-bound markets breaking out
- **WSS Threshold**: > 1.0 with squeeze active

### 3. **MEAN_REVERSION**
- **Entry**: Fade extreme RSI/Stochastic readings
- **Best For**: Choppy, ranging markets
- **WSS Threshold**: |WSS| > 2.0 with high choppiness

### 4. **LIQUIDITY_GRAB**
- **Entry**: Trade retests of FVG/liquidity zones
- **Best For**: Markets with clear institutional levels
- **WSS Threshold**: Variable based on structure

### 5. **DIVERGENCE_REVERSAL**
- **Entry**: Reversal trades on strong divergences
- **Best For**: End of trends or major swings
- **WSS Threshold**: Strong divergence required

---

## 📊 Dashboard Features

### Real-time Metrics
```
┌─────────────────────────────────────────────────────────────┐
│  WHALEWAVE TITAN v7.0 | BTCUSDT | $43,245.67               │
├─────────────────────────────────────────────────────────────┤
│  WSS: +2.34 | Strategy: TREND_FOLLOWING | Signal: BUY (85%) │
│  Reason: Strong uptrend with pullback to VWAP               │
├─────────────────────────────────────────────────────────────┤
│  Regime: NORMAL_VOLATILITY | Squeeze: OFF                  │
│  MTF Trend: BULLISH | Slope: +0.000123 | ADX: 28.5         │
├─────────────────────────────────────────────────────────────┤
│  RSI: 45.2 | Stoch: 38 | MACD: +0.000045 | Chop: 42.1      │
│  Divergence: NONE | FVG: BULLISH | VWAP: $43,198.45        │
├─────────────────────────────────────────────────────────────┤
│  Balance: $1,247.83 | Daily P&L: +$47.15 | Win Rate: 68%   │
│  OPEN POS: BUY @ $43,201.45 | PnL: +$23.67                 │
└─────────────────────────────────────────────────────────────┘
```

### Color Coding
- 🟢 **Green**: Bullish signals, profits, positive values
- 🔴 **Red**: Bearish signals, losses, negative values  
- 🟡 **Yellow**: Neutral values, warnings
- 🔵 **Blue**: Information, strategies, positions
- 🟠 **Orange**: Important alerts, high volatility
- ⚫ **Gray**: Labels, metadata, neutral information

---

## 🔧 Technical Indicators

### Core Indicators
- **RSI (10)**: Relative Strength Index for momentum
- **Stochastic (10,3,3)**: Oscillator for overbought/oversold
- **MACD (12,26,9)**: Trend and momentum confirmation
- **ATR (14)**: Volatility measurement for position sizing

### Advanced Indicators
- **Bollinger Bands (20,2.0)**: Volatility bands for mean reversion
- **Keltner Channels (20,1.5)**: Trend-following bands
- **SuperTrend (14,2.5)**: Dynamic support/resistance
- **Chandelier Exit (22,3.0)**: Trailing stop system

### Custom Indicators
- **Fair Value Gaps (FVG)**: Market structure analysis
- **Order Book Analysis**: Liquidity zone identification
- **Multi-timeframe Analysis**: 3m and 15m trend alignment
- **Divergence Detection**: Price vs. momentum divergences

---

## 🧮 WSS (Weighted Sentiment Score)

The **WSS** is our proprietary scoring system that combines multiple indicators:

### Score Components
1. **Trend (40%)**: Multi-timeframe trend alignment
2. **Momentum (30%)**: RSI, Stochastic, MACD confirmation
3. **Structure (20%)**: FVG, divergence, liquidity zones
4. **Volatility (10%)**: Market regime adjustment

### Score Interpretation
- **WSS > +2.0**: Strong bullish signal
- **WSS +1.0 to +2.0**: Bullish bias
- **WSS -1.0 to +1.0**: Neutral/uncertain
- **WSS -2.0 to -1.0**: Bearish bias  
- **WSS < -2.0**: Strong bearish signal

### Trading Rules
- **BUY**: WSS ≥ +2.0 and confidence ≥ 75%
- **SELL**: WSS ≤ -2.0 and confidence ≥ 75%
- **HOLD**: WSS between -2.0 and +2.0 or low confidence

---

## 💰 Risk Management

### Position Sizing
```javascript
// Example: $1,000 balance, 2% risk, $100 risk per trade
const riskAmount = balance × (riskPercent / 100)
const stopDistance = |entry - stopLoss|
const positionSize = riskAmount / stopDistance
```

### Risk Controls
- **Maximum Drawdown**: 10% of starting balance
- **Daily Loss Limit**: 5% of starting balance
- **Maximum Positions**: 1 concurrent position
- **Minimum RR Ratio**: 1:1.5 risk-reward

### Stop Loss & Take Profit
- **Stop Loss**: Based on technical levels (ATR, support/resistance)
- **Take Profit**: 1.5x stop loss distance minimum
- **Trailing Stops**: Dynamic stop adjustment
- **Time Stops**: Exit after maximum holding period

---

## 📈 Performance Monitoring

### Key Metrics
- **Total Return**: Overall percentage gain/loss
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit ÷ gross loss
- **Maximum Drawdown**: Largest peak-to-trough decline
- **Sharpe Ratio**: Risk-adjusted returns
- **Trade Frequency**: Trades per day/week

### Real-time Statistics
```
Performance Dashboard:
├── Total Trades: 47
├── Winning Trades: 32 (68.1%)
├── Losing Trades: 15 (31.9%)
├── Profit Factor: 1.84
├── Max Drawdown: -3.2%
├── Total Return: +24.7%
└── Average Trade: +$5.27
```

---

## 🐛 Troubleshooting

### Common Issues

#### 1. **"Missing GEMINI_API_KEY"**
```bash
# Solution: Add your API key to .env file
GEMINI_API_KEY=your_actual_key_here
```

#### 2. **"Config Error"**
```bash
# Solution: Regenerate config.json
rm config.json
node setup.js
```

#### 3. **"Data Fetch Fail"**
- Check internet connection
- Verify Bybit API is accessible
- Ensure symbol is actively trading

#### 4. **"High Memory Usage"**
- Reduce `limits.kline` in config
- Restart the application periodically
- Monitor system resources

#### 5. **"AI Analysis Failed"**
- Verify Gemini API key is valid
- Check API quota limits
- Review error logs for details

### Debug Mode
```bash
# Enable debug logging
LOG_LEVEL=debug npm start
```

### Performance Issues
- **Slow Indicators**: Reduce data period in config
- **High CPU**: Close other resource-intensive applications
- **Memory Leaks**: Restart application every 24 hours

---

## 🔄 API Reference

### TradingEngine
```javascript
const engine = new TradingEngine(config);
await engine.start(); // Begin trading loop
engine.isRunning = false; // Graceful shutdown
```

### Configuration
```javascript
const config = await ConfigManager.load();
```

### Market Analysis
```javascript
const analysis = await MarketAnalyzer.analyze(marketData, config);
const wss = WeightedSentimentCalculator.calculate(analysis, price, weights);
```

---

## 🧪 Testing

### Unit Tests
```bash
# Test individual components
npm test
```

### Paper Trading
- All trading is simulated in paper mode
- No real money is at risk
- Full trade history and statistics

### Backtesting (Coming Soon)
- Historical strategy validation
- Walk-forward analysis
- Monte Carlo simulations

---

## 🚀 Deployment

### Local Development
```bash
npm run dev  # Watch mode with auto-restart
```

### Production Deployment
```bash
# Set production environment
NODE_ENV=production
LOG_LEVEL=warn

# Use PM2 for process management
pm2 start whalewave_titan_refactored.js --name "whalewave-titan"
```

### Docker (Coming Soon)
```dockerfile
FROM node:18-alpine
WORKDIR /app
COPY . .
RUN npm ci --only=production
CMD ["npm", "start"]
```

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
```bash
git clone https://github.com/yourusername/whalewave-titan.git
cd whalewave-titan
npm install
npm run dev
```

### Coding Standards
- Use ESLint configuration provided
- Write JSDoc comments for all functions
- Follow existing code patterns
- Add tests for new features

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **Bybit API**: For providing reliable market data
- **Google Gemini**: For AI-powered analysis capabilities
- **Technical Analysis Community**: For indicator algorithms and best practices
- **Open Source Contributors**: For the excellent libraries used

---

## 📞 Support

- **Documentation**: Check this README and inline code comments
- **Issues**: Open a GitHub issue for bugs or feature requests
- **Discussions**: Use GitHub Discussions for questions and ideas

---

## 🗺️ Roadmap

### v7.1 (Coming Soon)
- [ ] Multiple exchange support (Binance, OKX)
- [ ] WebSocket real-time data
- [ ] Mobile push notifications
- [ ] Advanced backtesting

### v8.0 (Future)
- [ ] Live trading capabilities
- [ ] Multi-strategy portfolio
- [ ] Machine learning optimization
- [ ] Social trading features

---

**⚠️ Disclaimer**: This software is for educational purposes only. Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results. Never trade with money you cannot afford to lose.

---

**Built with ❤️ by MiniMax Agent**

*Empowering traders with professional-grade tools and AI-driven insights.*