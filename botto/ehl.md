class ChandelierEhlersSuperTrendStrategy(Strategy):
    """
    Chandelier Exit Ehlers SuperTrend Cross Strategy
    
    This strategy combines two powerful indicators:
    1. Chandelier Exit - A volatility-based indicator used for setting trailing stop-loss levels
    2. Ehlers SuperTrend - A trend-following indicator created by John Ehlers
    
    Signals are generated when these indicators cross each other:
    - Buy signal: When price crosses above the SuperTrend and Chandelier Exit confirms the trend
    - Sell signal: When price crosses below the SuperTrend and Chandelier Exit confirms the trend
    """
    
    def __init__(self, config: BotConfig, bot):
        """Initialize strategy."""
        super().__init__(config, bot)
        self.name = "ChandelierEhlersSuperTrend"
        
        # Strategy parameters
        self.chandelier_period = config.get('chandelier_period', 22)
        self.chandelier_multiplier = config.get('chandelier_multiplier', 3.0)
        self.supertrend_period = config.get('supertrend_period', 10)
        self.supertrend_multiplier = config.get('supertrend_multiplier', 3.0)
        
        # Data cache
        self.data_cache = {}
        
    def generate_signals(self) -> List[Signal]:
        """Generate trading signals based on Chandelier Exit and Ehlers SuperTrend crossover."""
        signals = []
        
        try:
            for symbol in self.config.symbols:
                # Get historical data
                df = self._get_historical_data(symbol)
                
                if df.empty or len(df) < max(self.chandelier_period, self.supertrend_period) * 2:
                    continue
                
                # Calculate indicators
                df = self._calculate_indicators(df)
                
                # Generate signals based on indicator crossovers
                signal = self._generate_signal_from_crossover(df, symbol)
                
                if signal:
                    signals.append(signal)
            
            return signals
            
        except Exception as e:
            self.logger.error(f"Error generating signals: {str(e)}")
            return []
    
    def _get_historical_data(self, symbol: str, limit: int = 200) -> pd.DataFrame:
        """Get historical data for a symbol."""
        try:
            response = self.bot.session.get_kline(
                category=self.config.category,
                symbol=symbol,
                interval=self.config.timeframe,
                limit=limit
            )
            
            if response['retCode'] != 0:
                self.logger.error(f"Error fetching kline data: {response['retMsg']}")
                return pd.DataFrame()
            
            kline_data = response['result']['list']
            
            # Convert to DataFrame
            df = pd.DataFrame(kline_data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            
            # Convert to numeric types
            df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = df[col].astype(float)
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error getting historical data: {str(e)}")
            return pd.DataFrame()
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Chandelier Exit and Ehlers SuperTrend indicators."""
        if df.empty:
            return df
        
        try:
            # Calculate ATR (Average True Range) for Chandelier Exit
            df['tr'] = np.maximum(
                df['high'] - df['low'],
                np.maximum(
                    abs(df['high'] - df['close'].shift(1)),
                    abs(df['low'] - df['close'].shift(1))
                )
            )
            df['atr'] = df['tr'].rolling(window=self.chandelier_period).mean()
            
            # Calculate Chandelier Exit (long and short)
            df['chandelier_long'] = df['high'].rolling(window=self.chandelier_period).max() - self.chandelier_multiplier * df['atr']
            df['chandelier_short'] = df['low'].rolling(window=self.chandelier_period).min() + self.chandelier_multiplier * df['atr']
            
            # Determine current Chandelier Exit value based on trend
            # We'll use SuperTrend to determine the trend direction
            df['supertrend'] = self._calculate_supertrend(df)
            
            # Set Chandelier Exit based on trend direction
            df['chandelier_exit'] = np.where(
                df['supertrend'] < df['close'],
                df['chandelier_long'],
                df['chandelier_short']
            )
            
            return df
            
        except Exception as e:
            self.logger.error(f"Error calculating indicators: {str(e)}")
            return df
    
    def _calculate_supertrend(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Ehlers SuperTrend indicator."""
        try:
            # Calculate Ehlers' SuperTrend
            # First, compute the typical price
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            
            # Compute Ehlers' cyclic component using a roofing filter
            # Roofing filter is a high-pass filter followed by a SuperSmoother
            alpha1 = (np.cos(2 * np.pi / self.supertrend_period) + np.sin(2 * np.pi / self.supertrend_period) - 1) / np.cos(2 * np.pi / self.supertrend_period)
            hp = pd.Series(index=df.index, dtype=float)
            
            for i in range(1, len(df)):
                if i == 1:
                    hp.iloc[i] = 0.5 * (1 + alpha1) * (typical_price.iloc[i] - typical_price.iloc[i-1])
                else:
                    hp.iloc[i] = 0.5 * (1 + alpha1) * (typical_price.iloc[i] - typical_price.iloc[i-1]) + alpha1 * hp.iloc[i-1]
            
            # Apply SuperSmoother to the high-pass filter output
            a1 = np.exp(-1.414 * np.pi / self.supertrend_period)
            b1 = 2 * a1 * np.cos(1.414 * np.pi / self.supertrend_period)
            c2 = b1
            c3 = -a1 * a1
            c1 = 1 - c2 - c3
            
            ss = pd.Series(index=df.index, dtype=float)
            
            for i in range(2, len(df)):
                if i == 2:
                    ss.iloc[i] = c1 * (hp.iloc[i] + hp.iloc[i-1]) / 2 + c2 * ss.iloc[i-1] + c3 * ss.iloc[i-2]
                else:
                    ss.iloc[i] = c1 * (hp.iloc[i] + hp.iloc[i-1]) / 2 + c2 * ss.iloc[i-1] + c3 * ss.iloc[i-2]
            
            # Calculate ATR for SuperTrend
            atr = df['tr'].rolling(window=self.supertrend_period).mean()
            
            # Calculate SuperTrend
            supertrend = pd.Series(index=df.index, dtype=float)
            
            for i in range(self.supertrend_period, len(df)):
                if typical_price.iloc[i] > typical_price.iloc[i-self.supertrend_period]:
                    # Uptrend
                    supertrend.iloc[i] = typical_price.iloc[i] - self.supertrend_multiplier * atr.iloc[i]
                else:
                    # Downtrend
                    supertrend.iloc[i] = typical_price.iloc[i] + self.supertrend_multiplier * atr.iloc[i]
            
            return supertrend
            
        except Exception as e:
            self.logger.error(f"Error calculating SuperTrend: {str(e)}")
            return pd.Series(index=df.index, dtype=float)
    
    def _generate_signal_from_crossover(self, df: pd.DataFrame, symbol: str) -> Signal:
        """Generate a signal from Chandelier Exit and SuperTrend crossover."""
        if df.empty or len(df) < 3:
            return None
        
        try:
            last_row = df.iloc[-1]
            prev_row = df.iloc[-2]
            prev_prev_row = df.iloc[-3]
            
            current_price = last_row['close']
            current_supertrend = last_row['supertrend']
            prev_supertrend = prev_row['supertrend']
            current_chandelier = last_row['chandelier_exit']
            prev_chandelier = prev_row['chandelier_exit']
            
            # Buy signal conditions:
            # 1. Price crosses above SuperTrend
            # 2. SuperTrend is below Chandelier Exit (confirming the trend)
            # 3. Previous candle was below SuperTrend (confirming crossover)
            
            if (current_price > current_supertrend and 
                prev_row['close'] <= prev_supertrend and
                current_supertrend < current_chandelier):
                
                # Calculate signal strength based on distance between indicators
                strength = min(1.0, abs(current_supertrend - current_chandelier) / current_price * 10)
                
                # Calculate confidence based on recent trend consistency
                trend_consistency = 0
                for i in range(min(5, len(df) - 1)):
                    if df.iloc[-(i+1)]['close'] > df.iloc[-(i+1)]['supertrend']:
                        trend_consistency += 1
                
                confidence = min(1.0, trend_consistency / 5)
                
                return Signal(
                    type=SignalType.BUY,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reasons=[
                        "Price crossed above SuperTrend",
                        "SuperTrend below Chandelier Exit (trend confirmation)"
                    ],
                    indicators={
                        "supertrend": current_supertrend,
                        "chandelier_exit": current_chandelier,
                        "atr": last_row['atr'],
                        "price": current_price
                    },
                    symbol=symbol,
                    strategy=self.name,
                    confidence=confidence
                )
            
            # Sell signal conditions:
            # 1. Price crosses below SuperTrend
            # 2. SuperTrend is above Chandelier Exit (confirming the trend)
            # 3. Previous candle was above SuperTrend (confirming crossover)
            
            elif (current_price < current_supertrend and 
                  prev_row['close'] >= prev_supertrend and
                  current_supertrend > current_chandelier):
                
                # Calculate signal strength based on distance between indicators
                strength = min(1.0, abs(current_supertrend - current_chandelier) / current_price * 10)
                
                # Calculate confidence based on recent trend consistency
                trend_consistency = 0
                for i in range(min(5, len(df) - 1)):
                    if df.iloc[-(i+1)]['close'] < df.iloc[-(i+1)]['supertrend']:
                        trend_consistency += 1
                
                confidence = min(1.0, trend_consistency / 5)
                
                return Signal(
                    type=SignalType.SELL,
                    strength=strength,
                    price=current_price,
                    timestamp=datetime.now(),
                    reasons=[
                        "Price crossed below SuperTrend",
                        "SuperTrend above Chandelier Exit (trend confirmation)"
                    ],
                    indicators={
                        "supertrend": current_supertrend,
                        "chandelier_exit": current_chandelier,
                        "atr": last_row['atr'],
                        "price": current_price
                    },
                    symbol=symbol,
                    strategy=self.name,
                    confidence=confidence
                )
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error generating signal from crossover: {str(e)}")
            return None
