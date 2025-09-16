# MMXCEL v3.1 - Enhanced Bybit Market Making Bot

An advanced cryptocurrency market-making bot for Bybit exchange with enhanced risk management, performance monitoring, and user interface.

## Features

### Core Trading Features
- **Hedge Mode Market Making**: Places buy/sell orders around mid-price
- **Dynamic Spread Adjustment**: Adapts spreads based on market volatility
- **Intelligent Position Sizing**: Calculates optimal order sizes based on available capital
- **Automatic Rebalancing**: Maintains neutral inventory positions
- **Risk Management**: Stop-loss, take-profit, and emergency stop mechanisms

### Enhanced Features (v3.1)
- **Performance Monitoring**: Tracks API latency and order execution times
- **Circuit Breaker**: Automatic trading halt during abnormal market conditions
- **Enhanced Error Handling**: Robust retry mechanisms and error recovery
- **Real-time Dashboard**: Colorful terminal interface with live statistics
- **Configuration Management**: JSON-based configuration with validation
- **Comprehensive Logging**: Rotating log files with detailed error tracking

### Risk Management
- **Emergency Stop Loss**: Configurable maximum loss threshold
- **Position Size Limits**: Maximum position size as percentage of balance
- **Abnormal Market Detection**: Automatic halt during extreme spread conditions
- **Stale Data Protection**: Prevents trading on outdated market data
- **Connection Monitoring**: Tracks WebSocket connection health

## Installation

1. **Install Dependencies**:
\`\`\`bash
pip install pybit python-dotenv colorama
\`\`\`

2. **Configure API Keys**:
   - Copy `.env.example` to `.env`
   - Add your Bybit API credentials
   - Set `USE_TESTNET=true` for testing

3. **Configure Trading Parameters**:
   - Review and modify `config.json`
   - Adjust risk parameters according to your strategy
   - Set appropriate position sizes and spreads

## Configuration

### Key Parameters

- `SYMBOL`: Trading pair (e.g., "BTCUSDT")
- `QUANTITY`: Base order size
- `SPREAD_PERCENTAGE`: Spread around mid-price (0.0005 = 0.05%)
- `MAX_OPEN_ORDERS`: Maximum concurrent orders
- `REBALANCE_THRESHOLD_QTY`: Position imbalance threshold for rebalancing
- `EMERGENCY_STOP_LOSS`: Maximum loss before emergency stop (0.02 = 2%)
- `MAX_POSITION_SIZE`: Maximum position as % of balance (0.1 = 10%)

### Risk Settings

- `STOP_LOSS_PERCENTAGE`: Individual position stop loss
- `PROFIT_PERCENTAGE`: Take profit threshold
- `ABNORMAL_SPREAD_THRESHOLD`: Market halt threshold for wide spreads
- `CAPITAL_ALLOCATION_PERCENTAGE`: Capital per order (0.05 = 5%)

## Usage

### Starting the Bot

\`\`\`bash
python mmxcel_v3_1.py
\`\`\`

### Interactive Commands

While running, use these keyboard commands:
- `q`: Quit the bot gracefully
- `c`: Cancel all open orders
- `r`: Force manual rebalancing
- `s`: Trigger emergency stop

### Dashboard Information

The real-time dashboard displays:
- **Bot Status**: Current operational state
- **Market Data**: Live prices, spreads, and data freshness
- **Account Info**: Available balance and positions
- **Open Orders**: Active orders with age indicators
- **Performance**: Statistics, PnL, and system metrics

## Safety Features

### Automatic Protections
1. **Emergency Stop**: Triggers at configurable loss threshold
2. **Circuit Breaker**: Halts trading during abnormal market conditions
3. **Stale Data Protection**: Prevents trading on old market data
4. **Connection Monitoring**: Alerts on WebSocket disconnections
5. **Order Lifecycle Management**: Automatic cancellation of stale orders

### Manual Controls
- Real-time order cancellation
- Emergency stop activation
- Manual rebalancing triggers
- Graceful shutdown procedures

## Monitoring and Logging

### Log Files
- `mmxcel.log`: Main application log with rotation
- Configurable log levels and retention policies
- Performance metrics and error tracking

### Performance Metrics
- API call latency monitoring
- Order execution time tracking
- Connection health status
- PnL and drawdown tracking

## Troubleshooting

### Common Issues

1. **WebSocket Connection Failures**:
   - Check internet connectivity
   - Verify API credentials
   - Ensure firewall allows connections

2. **Order Placement Errors**:
   - Verify sufficient balance
   - Check minimum order requirements
   - Review symbol configuration

3. **High API Latency**:
   - Monitor network connection
   - Consider VPS deployment
   - Check Bybit server status

### Error Recovery
- Automatic retry mechanisms for API calls
- WebSocket reconnection handling
- Graceful degradation during network issues

## Development

### Code Structure
- **Configuration Management**: Type-safe configuration with validation
- **Market Data Handling**: Real-time WebSocket data processing
- **Trading Logic**: Enhanced market making strategy
- **Risk Management**: Comprehensive safety mechanisms
- **User Interface**: Real-time dashboard and controls

### Extending the Bot
- Modular design allows easy feature additions
- Well-documented API interfaces
- Comprehensive error handling patterns
- Performance monitoring infrastructure

## Disclaimer

This software is for educational and research purposes. Cryptocurrency trading involves substantial risk of loss. Users are responsible for:
- Understanding the risks involved
- Testing thoroughly on testnet before live trading
- Monitoring positions and system health
- Complying with applicable regulations

The authors are not responsible for any financial losses incurred through the use of this software.

## License

This project is provided as-is for educational purposes. Please review and understand the code before using with real funds.
\`\`\`

```python file="requirements.txt"
pybit>=5.6.0
python-dotenv>=1.0.0
colorama>=0.4.6
asyncio
decimal
typing
dataclasses
contextlib
# MMXCEL v3.2 Enhanced - 15 Major Improvements

## Summary of 15 Key Improvements Made:

### 1. **Memory Management & System Monitoring**
- Added `psutil` for comprehensive system resource monitoring
- Implemented automatic memory cleanup with garbage collection
- Real-time tracking of CPU, memory, and network usage
- Periodic maintenance tasks to prevent memory leaks

### 2. **Advanced Rate Limiting**
- Implemented token bucket algorithm for API rate limiting
- Configurable burst limits and cooldown periods
- Prevents API rate limit violations and improves reliability
- Automatic backoff when approaching limits

### 3. **Data Integrity & Validation**
- Added `hashlib` for configuration change detection
- Enhanced input validation and sanitization
- Checksum verification for critical data structures
- Robust error handling for malformed data

### 4. **Enhanced Configuration Management**
- Hot reload capability for configuration changes
- Configuration validation with detailed error messages
- Callback system for configuration updates
- Hash-based change detection without restart

### 5. **WebSocket Reconnection Logic**
- Exponential backoff for reconnection attempts
- Connection quality monitoring and scoring
- Heartbeat mechanism for connection health
- Automatic recovery from connection drops

### 6. **Order Book Depth Analysis**
- Support for deeper order book levels (configurable)
- Market impact calculation before order placement
- Liquidity analysis for better price placement
- Order book imbalance detection

### 7. **Enhanced Error Classification**
- Structured error categorization and tracking
- API error code analysis and appropriate responses
- Error frequency monitoring and alerting
- Automatic error recovery strategies

### 8. **Comprehensive Trade History**
- Detailed trade tracking with slippage analysis
- Price and spread history maintenance
- Performance metrics over time
- Trade execution quality monitoring

### 9. **Advanced Session Statistics**
- Extended metrics including rejection rates
- Volume tracking and analysis
- Connection drop monitoring
- Memory cleanup and config reload tracking

### 10. **Structured Logging System**
- Context-aware logging with structured format
- Enhanced log messages with relevant metadata
- Performance-based log level adjustment
- Comprehensive error tracking and analysis

### 11. **Latency Optimization**
- WebSocket message latency tracking
- API call performance monitoring
- Order execution time measurement
- Performance bottleneck identification

### 12. **Enhanced WebSocket Processing**
- Improved message processing with latency tracking
- Better error handling and recovery
- Connection quality assessment
- Real-time performance monitoring

### 13. **Slippage Protection & Order Fill Tracking**
- Real-time slippage calculation and monitoring
- Configurable slippage thresholds
- Enhanced order fill analysis
- Market impact assessment before trading

### 14. **Advanced Reconnection & Heartbeat**
- Sophisticated reconnection logic with backoff
- Heartbeat mechanism for connection maintenance
- Connection health scoring system
- Automatic connection quality adjustment

### 15. **Market Impact Analysis & Position Sizing**
- Dynamic position sizing based on market conditions
- Market impact calculation using order book depth
- Volatility-adjusted spread calculation
- Enhanced risk management with multiple factors

## Technical Enhancements:

### Performance Improvements:
- Reduced memory footprint through better data structures
- Optimized critical path execution
- Enhanced garbage collection and cleanup
- Better resource utilization monitoring

### Reliability Improvements:
- Robust error handling and recovery
- Enhanced connection management
- Better data validation and integrity checks
- Comprehensive monitoring and alerting

### User Experience Improvements:
- More informative dashboard with additional metrics
- Enhanced keyboard commands and controls
- Better visual indicators and status reporting
- Comprehensive performance statistics

### Risk Management Improvements:
- Advanced slippage protection
- Market impact analysis
- Enhanced emergency stop conditions
- Better position sizing algorithms

All improvements maintain full backward compatibility while significantly enhancing the bot's performance, reliability, and user experience.
