import axios from 'axios';
import crypto from 'crypto';
import { logger } from './utils.js';
import chalk from 'chalk';

export default class LiveDataFetcher {
  constructor(apiKey, apiSecret, tradingSymbol, options = {}) {
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.tradingSymbol = tradingSymbol;
    
    // Enhanced configuration with defaults
    this.baseUrl = options.baseUrl || 'https://api.bybit.com';
    this.testnetUrl = 'https://api-testnet.bybit.com';
    this.useTestnet = options.useTestnet || false;
    this.category = options.category || 'linear'; // 'spot', 'linear', 'inverse', 'option'
    
    // Enhanced rate limiting
    this.rateLimitInterval = options.rateLimitInterval || 1000;
    this.maxRetries = options.maxRetries || 3;
    this.retryDelay = options.retryDelay || 2000;
    this.requestTimeout = options.requestTimeout || 10000;
    
    // Queue management
    this.requestQueue = [];
    this.isProcessingQueue = false;
    this.lastRequestTime = 0;
    this.requestCount = 0;
    this.errorCount = 0;
    
    // Cache configuration
    this.cacheEnabled = options.cacheEnabled !== false;
    this.cache = new Map();
    this.cacheTTL = options.cacheTTL || 5000; // 5 seconds default
    
    // Circuit breaker
    this.circuitBreakerThreshold = options.circuitBreakerThreshold || 5;
    this.circuitBreakerTimeout = options.circuitBreakerTimeout || 60000;
    this.circuitBreakerFailures = 0;
    this.circuitBreakerOpenedAt = null;
    
    // Performance tracking
    this.metrics = {
      totalRequests: 0,
      successfulRequests: 0,
      failedRequests: 0,
      cacheHits: 0,
      averageResponseTime: 0,
      responseTimes: []
    };
    
    // Axios instance with enhanced configuration
    this.axiosInstance = axios.create({
      baseURL: this.useTestnet ? this.testnetUrl : this.baseUrl,
      timeout: this.requestTimeout,
      headers: {
        'X-Referer': 'trading-bot',
        'Content-Type': 'application/json'
      }
    });
    
    // Add request/response interceptors
    this.setupInterceptors();
  }

  setupInterceptors() {
    // Request interceptor for logging and timing
    this.axiosInstance.interceptors.request.use(
      (config) => {
        config.metadata = { startTime: Date.now() };
        logger.debug(chalk.gray(`[API Request] ${config.method.toUpperCase()} ${config.url}`));
        return config;
      },
      (error) => Promise.reject(error)
    );
    
    // Response interceptor for metrics and error handling
    this.axiosInstance.interceptors.response.use(
      (response) => {
        const duration = Date.now() - response.config.metadata.startTime;
        this.updateMetrics(duration, true);
        logger.debug(chalk.gray(`[API Response] ${response.status} - ${duration}ms`));
        return response;
      },
      (error) => {
        if (error.config && error.config.metadata) {
          const duration = Date.now() - error.config.metadata.startTime;
          this.updateMetrics(duration, false);
        }
        return Promise.reject(error);
      }
    );
  }

  updateMetrics(responseTime, success) {
    this.metrics.totalRequests++;
    if (success) {
      this.metrics.successfulRequests++;
      this.circuitBreakerFailures = 0; // Reset on success
    } else {
      this.metrics.failedRequests++;
      this.circuitBreakerFailures++;
    }
    
    // Track response times (keep last 100)
    this.metrics.responseTimes.push(responseTime);
    if (this.metrics.responseTimes.length > 100) {
      this.metrics.responseTimes.shift();
    }
    
    // Calculate average response time
    this.metrics.averageResponseTime = 
      this.metrics.responseTimes.reduce((a, b) => a + b, 0) / this.metrics.responseTimes.length;
  }

  // Circuit breaker check
  isCircuitOpen() {
    if (this.circuitBreakerFailures >= this.circuitBreakerThreshold) {
      if (!this.circuitBreakerOpenedAt) {
        this.circuitBreakerOpenedAt = Date.now();
        logger.warn(chalk.red(`Circuit breaker opened due to ${this.circuitBreakerFailures} consecutive failures`));
      }
      
      const timeSinceOpen = Date.now() - this.circuitBreakerOpenedAt;
      if (timeSinceOpen < this.circuitBreakerTimeout) {
        return true;
      } else {
        // Reset circuit breaker
        this.circuitBreakerFailures = 0;
        this.circuitBreakerOpenedAt = null;
        logger.info(chalk.green('Circuit breaker reset'));
      }
    }
    return false;
  }

  // Cache management
  getCached(key) {
    if (!this.cacheEnabled) return null;
    
    const cached = this.cache.get(key);
    if (cached && Date.now() - cached.timestamp < this.cacheTTL) {
      this.metrics.cacheHits++;
      logger.debug(chalk.cyan(`Cache hit for key: ${key}`));
      return cached.data;
    }
    return null;
  }

  setCache(key, data) {
    if (!this.cacheEnabled) return;
    
    this.cache.set(key, {
      data: data,
      timestamp: Date.now()
    });
    
    // Clean up old cache entries
    if (this.cache.size > 100) {
      const firstKey = this.cache.keys().next().value;
      this.cache.delete(firstKey);
    }
  }

  // Enhanced queue processor with exponential backoff
  async processQueue() {
    if (this.isProcessingQueue || this.requestQueue.length === 0) {
      return;
    }

    this.isProcessingQueue = true;

    while (this.requestQueue.length > 0) {
      const { resolve, reject, func, retryCount = 0 } = this.requestQueue.shift();

      // Check circuit breaker
      if (this.isCircuitOpen()) {
        reject(new Error('Circuit breaker is open - API temporarily unavailable'));
        continue;
      }

      const now = Date.now();
      const timeSinceLastRequest = now - this.lastRequestTime;
      const delayNeeded = this.rateLimitInterval - timeSinceLastRequest;

      if (delayNeeded > 0) {
        await new Promise(res => setTimeout(res, delayNeeded));
      }

      try {
        const result = await func();
        resolve(result);
        this.errorCount = 0; // Reset error count on success
      } catch (error) {
        this.errorCount++;
        
        // Implement retry logic with exponential backoff
        if (retryCount < this.maxRetries) {
          const backoffDelay = this.retryDelay * Math.pow(2, retryCount);
          logger.warn(chalk.yellow(`Retrying request (${retryCount + 1}/${this.maxRetries}) after ${backoffDelay}ms`));
          
          setTimeout(() => {
            this.requestQueue.unshift({ 
              resolve, 
              reject, 
              func, 
              retryCount: retryCount + 1 
            });
            this.processQueue();
          }, backoffDelay);
        } else {
          reject(error);
        }
      } finally {
        this.lastRequestTime = Date.now();
        this.requestCount++;
      }
    }

    this.isProcessingQueue = false;
  }

  // Generate signature for authenticated requests (if needed)
  generateSignature(params, timestamp) {
    const queryString = Object.keys(params)
      .sort()
      .map(key => `${key}=${params[key]}`)
      .join('&');
    
    const signString = `${timestamp}${this.apiKey}${queryString}`;
    return crypto
      .createHmac('sha256', this.apiSecret)
      .update(signString)
      .digest('hex');
  }

  // Enhanced price fetching with validation
  async fetchCurrentPrice() {
    return new Promise((resolve, reject) => {
      const func = async () => {
        try {
          // Check cache first
          const cacheKey = `price_${this.tradingSymbol}`;
          const cached = this.getCached(cacheKey);
          if (cached) {
            return cached;
          }

          logger.info(chalk.blue(`Fetching live price for ${this.tradingSymbol} from Bybit...`));
          const endpoint = '/v5/market/tickers';

          const params = {
            symbol: this.tradingSymbol,
            category: this.category,
          };

          const response = await this.axiosInstance.get(endpoint, { params });

          if (response.data && response.data.retCode === 0 && response.data.result.list.length > 0) {
            const ticker = response.data.result.list[0];
            const currentPrice = parseFloat(ticker.lastPrice);
            
            // Validate price
            if (isNaN(currentPrice) || currentPrice <= 0) {
              throw new Error(`Invalid price received: ${ticker.lastPrice}`);
            }
            
            const result = { 
              currentPrice, 
              symbol: this.tradingSymbol,
              bid: parseFloat(ticker.bid1Price),
              ask: parseFloat(ticker.ask1Price),
              volume24h: parseFloat(ticker.volume24h),
              turnover24h: parseFloat(ticker.turnover24h),
              prevPrice24h: parseFloat(ticker.prevPrice24h),
              price24hPcnt: parseFloat(ticker.price24hPcnt),
              timestamp: Date.now()
            };
            
            // Cache the result
            this.setCache(cacheKey, result);
            
            logger.info(chalk.green(`Successfully fetched live price: ${currentPrice} (24h: ${ticker.price24hPcnt}%)`));
            return result;
          } else {
            const errorMsg = response.data.retMsg || 'Unknown error';
            logger.warn(chalk.yellow(`Failed to fetch live price: ${errorMsg}`));
            throw new Error(`API Error: ${errorMsg}`);
          }
        } catch (error) {
          logger.error(chalk.red(`Error fetching live price from Bybit: ${error.message}`));
          throw error;
        }
      };
      this.requestQueue.push({ resolve, reject, func });
      this.processQueue();
    });
  }

  // Enhanced kline fetching with validation and transformation
  async fetchKlineData(interval, limit) {
    return new Promise((resolve, reject) => {
      const func = async () => {
        try {
          // Validate inputs
          const validIntervals = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M'];
          if (!validIntervals.includes(String(interval))) {
            throw new Error(`Invalid interval: ${interval}. Valid intervals: ${validIntervals.join(', ')}`);
          }
          
          if (limit < 1 || limit > 1000) {
            throw new Error(`Invalid limit: ${limit}. Must be between 1 and 1000`);
          }

          // Check cache
          const cacheKey = `kline_${this.tradingSymbol}_${interval}_${limit}`;
          const cached = this.getCached(cacheKey);
          if (cached) {
            return cached;
          }

          logger.info(chalk.blue(`Fetching ${limit} ${interval}-minute klines for ${this.tradingSymbol} from Bybit...`));
          const endpoint = '/v5/market/kline';

          const params = {
            symbol: this.tradingSymbol,
            category: this.category,
            interval: String(interval),
            limit: limit,
          };

          const response = await this.axiosInstance.get(endpoint, { params });

          if (response.data && response.data.retCode === 0 && response.data.result.list.length > 0) {
            const klines = response.data.result.list
              .map(kline => {
                const [startTime, open, high, low, close, volume, turnover] = kline;
                
                // Validate kline data
                if (!startTime || !open || !high || !low || !close) {
                  logger.warn(chalk.yellow(`Invalid kline data received: ${JSON.stringify(kline)}`));
                  return null;
                }
                
                return {
                  startTime: parseInt(startTime),
                  open: parseFloat(open),
                  high: parseFloat(high),
                  low: parseFloat(low),
                  close: parseFloat(close),
                  volume: parseFloat(volume || 0),
                  turnover: parseFloat(turnover || 0),
                  // Additional calculated fields
                  change: parseFloat(close) - parseFloat(open),
                  changePercent: ((parseFloat(close) - parseFloat(open)) / parseFloat(open)) * 100,
                  amplitude: ((parseFloat(high) - parseFloat(low)) / parseFloat(low)) * 100
                };
              })
              .filter(k => k !== null)
              .reverse(); // Reverse to get chronological order
            
            // Cache the result
            this.setCache(cacheKey, klines);
            
            logger.info(chalk.green(`Successfully fetched ${klines.length} klines.`));
            return klines;
          } else {
            const errorMsg = response.data.retMsg || 'Unknown error';
            logger.warn(chalk.yellow(`Failed to fetch kline data: ${errorMsg}`));
            throw new Error(`API Error: ${errorMsg}`);
          }
        } catch (error) {
          logger.error(chalk.red(`Error fetching kline data from Bybit: ${error.message}`));
          throw error;
        }
      };
      this.requestQueue.push({ resolve, reject, func });
      this.processQueue();
    });
  }

  // New method: Fetch order book
  async fetchOrderBook(limit = 25) {
    return new Promise((resolve, reject) => {
      const func = async () => {
        try {
          const cacheKey = `orderbook_${this.tradingSymbol}_${limit}`;
          const cached = this.getCached(cacheKey);
          if (cached) {
            return cached;
          }

          logger.info(chalk.blue(`Fetching order book for ${this.tradingSymbol}...`));
          const endpoint = '/v5/market/orderbook';

          const params = {
            symbol: this.tradingSymbol,
            category: this.category,
            limit: limit
          };

          const response = await this.axiosInstance.get(endpoint, { params });

          if (response.data && response.data.retCode === 0) {
            const orderBook = {
              bids: response.data.result.b.map(([price, size]) => ({
                price: parseFloat(price),
                size: parseFloat(size)
              })),
              asks: response.data.result.a.map(([price, size]) => ({
                price: parseFloat(price),
                size: parseFloat(size)
              })),
              timestamp: response.data.result.ts,
              updateId: response.data.result.u
            };

            this.setCache(cacheKey, orderBook);
            logger.info(chalk.green(`Successfully fetched order book`));
            return orderBook;
          } else {
            throw new Error(`API Error: ${response.data.retMsg || 'Unknown error'}`);
          }
        } catch (error) {
          logger.error(chalk.red(`Error fetching order book: ${error.message}`));
          throw error;
        }
      };
      this.requestQueue.push({ resolve, reject, func });
      this.processQueue();
    });
  }

  // New method: Get metrics
  getMetrics() {
    return {
      ...this.metrics,
      cacheSize: this.cache.size,
      queueSize: this.requestQueue.length,
      circuitBreakerStatus: this.isCircuitOpen() ? 'OPEN' : 'CLOSED',
      errorRate: this.metrics.totalRequests > 0 
        ? (this.metrics.failedRequests / this.metrics.totalRequests * 100).toFixed(2) + '%'
        : '0%',
      cacheHitRate: (this.metrics.cacheHits + this.metrics.totalRequests) > 0
        ? (this.metrics.cacheHits / (this.metrics.cacheHits + this.metrics.totalRequests) * 100).toFixed(2) + '%'
        : '0%'
    };
  }

  // New method: Clear cache
  clearCache() {
    this.cache.clear();
    logger.info(chalk.green('Cache cleared'));
  }

  // New method: Reset metrics
  resetMetrics() {
    this.metrics = {
      totalRequests: 0,
      successfulRequests: 0,
      failedRequests: 0,
      cacheHits: 0,
      averageResponseTime: 0,
      responseTimes: []
    };
    logger.info(chalk.green('Metrics reset'));
  }
}
