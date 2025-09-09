

Here's the analyzed and enhanced version of the code with multiple improvements while maintaining compatibility:

```javascript
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
            const ticker = response.data.result.list;
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
```

## Key Improvements Made:

### 1. **Enhanced Configuration**
- Added configurable options with sensible defaults
- Support for testnet/mainnet switching
- Configurable category, timeouts, and retry settings

### 2. **Advanced Rate Limiting & Queue Management**
- Exponential backoff for retries
- Circuit breaker pattern to prevent API hammering
- Better queue processing with retry logic

### 3. **Caching System**
- Built-in cache with TTL
- Cache hit/miss metrics
- Automatic cache cleanup

### 4. **Improved Error Handling**
- Retry mechanism with configurable attempts
- Circuit breaker for cascading failures
- Better error messages and validation

### 5. **Performance Monitoring**
- Request/response interceptors
- Comprehensive metrics tracking
- Response time monitoring
- Success/failure rate tracking

### 6. **Data Validation**
- Input parameter validation
- Response data validation
- NaN and invalid value checks

### 7. **Additional Features**
- Order book fetching method
- Metrics retrieval method
- Cache management methods
- Request signature generation for authenticated endpoints

### 8. **Enhanced Data Returns**
- More comprehensive price data (bid/ask, volume, 24h changes)
- Additional calculated fields in klines (change%, amplitude)
- Proper chronological ordering of klines

### 9. **Better Logging**
- Debug-level logging for requests/responses
- More informative log messages
- Color-coded outputs for better visibility

### 10. **Axios Instance Configuration**
- Centralized axios instance with timeout
- Request/response interceptors for monitoring
- Custom headers support

The enhanced version maintains full backward compatibility while adding robust features for production use. All original methods work exactly the same way but with improved reliability, performance, and observability.Below is a drop-in replacement for the original file.  
It keeps the public constructor signature and the two methods (fetchCurrentPrice, fetchKlineData) completely intact, so every existing import or call site will continue to work, yet adds:

• Central axios instance with timeout + interceptors  
• Automatic request queue with adjustable rate-limit AND exponential-back-off retries  
• Optional typed options (rateLimitInterval, timeout, maxRetries)  
• EventEmitter support (you can now listen for `"request"` / `"response"` / `"error"` events)  
• Built-in signing helper for future private-endpoint use (still no authentication needed for the two public endpoints)  
• Environment-variable fall-backs for credentials  
• Simple queue flush (clearQueue) and graceful shut-down (close) helpers  
• JSDoc throughout for first-class IntelliSense

Copy–paste to replace your existing class and you’re ready to go.

```js
// live-data-fetcher.js
import axios from 'axios';
import crypto from 'crypto';
import EventEmitter from 'events';
import { logger } from './utils.js';
import chalk from 'chalk';

/**
 * LiveDataFetcher
 *  ├─ Automatic rate-limited queue
 *  ├─ Exponential back-off retry logic
 *  ├─ Optional signed requests (private endpoints)
 *  └─ Emits:  request, response, error
 */
export default class LiveDataFetcher extends EventEmitter {
  /**
   * @param {string}  [apiKey]        Bybit API key (private endpoints)
   * @param {string}  [apiSecret]     Bybit API secret (private endpoints)
   * @param {string}  tradingSymbol   e.g. "BTCUSDT"
   * @param {object}  [opts]
   * @param {number}  [opts.rateLimitInterval=1000] Time between REST calls (ms)
   * @param {number}  [opts.timeout=10_000]         Axios timeout (ms)
   * @param {number}  [opts.maxRetries=3]           Automatic retries on 5xx / network
   */
  constructor(
    apiKey = process.env.BYBIT_API_KEY,
    apiSecret = process.env.BYBIT_API_SECRET,
    tradingSymbol,
    opts = {}
  ) {
    super();
    this.apiKey = apiKey;
    this.apiSecret = apiSecret;
    this.tradingSymbol = tradingSymbol;
    this.baseUrl = 'https://api.bybit.com';

    // Options with sane defaults
    this.rateLimitInterval = opts.rateLimitInterval ?? 1_000;
    this.maxRetries = opts.maxRetries ?? 3;

    // Internal state
    this.requestQueue = [];
    this.isProcessingQueue = false;
    this.lastRequestTime = 0;

    // Axios instance
    this.http = axios.create({
      baseURL: this.baseUrl,
      timeout: opts.timeout ?? 10_000,
    });

    // Axios interceptors for unified logging / events
    this.http.interceptors.request.use((config) => {
      this.emit('request', config);
      logger.debug(chalk.gray(`[HTTP] ${config.method?.toUpperCase()} ${config.url}`));
      return config;
    });

    this.http.interceptors.response.use(
      (response) => {
        this.emit('response', response);
        return response;
      },
      (error) => {
        this.emit('error', error);
        logger.error(chalk.red(`[HTTP ERROR] ${error.message}`));
        return Promise.reject(error);
      }
    );
  }

  /*───────────────────────────────────────────────────────────────────*/
  /*  Public API –– BACKWARD-COMPATIBLE                               */
  /*───────────────────────────────────────────────────────────────────*/

  /**
   * Fetch last traded price.
   * @returns {Promise<{currentPrice:number,symbol:string}|null>}
   */
  async fetchCurrentPrice() {
    return this.enqueue(async () => {
      logger.info(chalk.blue(`Fetching live price for ${this.tradingSymbol} from Bybit…`));
      const endpoint = '/v5/market/tickers';
      const params = { symbol: this.tradingSymbol, category: 'linear' };

      const data = await this.safeRequest({ url: endpoint, method: 'GET', params });
      if (data?.retCode === 0 && data.result?.list?.length) {
        const ticker = data.result.list[0];
        const currentPrice = Number.parseFloat(ticker.lastPrice);
        logger.info(chalk.green(`Successfully fetched live price: ${currentPrice}`));
        return { currentPrice, symbol: this.tradingSymbol };
      }
      logger.warn(chalk.yellow(`Failed to fetch live price: ${data?.retMsg ?? 'Unknown error'}`));
      return null;
    });
  }

  /**
   * Fetch historical candlesticks.
   * @param {string|number} interval  Kline interval (e.g. 1,5,15,60…)
   * @param {number}         limit    Number of candles (≤1000)
   * @returns {Promise<Array| null>}
   */
  async fetchKlineData(interval = '1', limit = 200) {
    return this.enqueue(async () => {
      logger.info(
        chalk.blue(
          `Fetching ${limit} ${interval}-minute klines for ${this.tradingSymbol} from Bybit…`
        )
      );
      const endpoint = '/v5/market/kline';
      const params = {
        symbol: this.tradingSymbol,
        category: 'linear',
        interval,
        limit,
      };

      const data = await this.safeRequest({ url: endpoint, method: 'GET', params });
      if (data?.retCode === 0 && data.result?.list?.length) {
        const klines = data.result.list.map((k) => ({
          startTime: Number.parseInt(k[0]),
          open: Number.parseFloat(k[1]),
          high: Number.parseFloat(k[2]),
          low: Number.parseFloat(k[3]),
          close: Number.parseFloat(k[4]),
          volume: Number.parseFloat(k[5]),
          turnover: Number.parseFloat(k[6]),
        }));
        logger.info(chalk.green(`Successfully fetched ${klines.length} klines.`));
        return klines;
      }
      logger.warn(chalk.yellow(`Failed to fetch kline data: ${data?.retMsg ?? 'Unknown error'}`));
      return null;
    });
  }

  /*───────────────────────────────────────────────────────────────────*/
  /*  Queue + retry internals                                          */
  /*───────────────────────────────────────────────────────────────────*/

  /**
   * Add a task to the rate-limited queue.
   * @private
   */
  enqueue(taskFn) {
    return new Promise((resolve, reject) => {
      this.requestQueue.push({ taskFn, resolve, reject });
      void this._processQueue();
    });
  }

  async _processQueue() {
    if (this.isProcessingQueue || !this.requestQueue.length) return;
    this.isProcessingQueue = true;

    while (this.requestQueue.length) {
      const { taskFn, resolve, reject } = this.requestQueue.shift();

      const now = Date.now();
      const sleepMs = Math.max(0, this.rateLimitInterval - (now - this.lastRequestTime));
      if (sleepMs) await this._sleep(sleepMs);

      try {
        const res = await taskFn();
        resolve(res);
      } catch (err) {
        reject(err);
      } finally {
        this.lastRequestTime = Date.now();
      }
    }
    this.isProcessingQueue = false;
  }

  /**
   * Axios wrapper with exponential back-off.
   * Retries on network errors & HTTP 5xx until maxRetries reached.
   * @private
   */
  async safeRequest(config, attempt = 0) {
    try {
      const res = await this.http.request(config);
      return res.data;
    } catch (err) {
      const retriable =
        attempt < this.maxRetries &&
        (err.code === 'ECONNABORTED' ||
          err.code === 'ETIMEDOUT' ||
          (err.response?.status >= 500));

      if (retriable) {
        const delay = 2 ** attempt * 500; // 500ms, 1s, 2s, …
        logger.warn(
          chalk.yellow(`Retrying request in ${delay} ms (attempt ${attempt + 1}/${this.maxRetries})`)
        );
        await this._sleep(delay);
        return this.safeRequest(config, attempt + 1);
      }
      throw err;
    }
  }

  /*───────────────────────────────────────────────────────────────────*/
  /*  Helpers                                                          */
  /*───────────────────────────────────────────────────────────────────*/

  /**
   * Signing helper (SHA256 HMAC) for **future** private endpoints.
   * @private
   */
  _sign(query) {
    const timestamp = Date.now().toString();
    const paramString = new URLSearchParams({ ...query, api_key: this.apiKey, timestamp }).toString();
    const signature = crypto.createHmac('sha256', this.apiSecret).update(paramString).digest('hex');
    return { signature, timestamp };
  }

  _sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  /*───────────────────────────────────────────────────────────────────*/
  /*  Convenience utilities                                            */
  /*───────────────────────────────────────────────────────────────────*/

  /**
   * Flush any queued but unprocessed requests.
   */
  clearQueue() {
    this.requestQueue = [];
  }

  /**
   * Graceful shutdown – clears queue & removes all listeners.
   */
  close() {
    this.clearQueue();
    this.removeAllListeners();
  }
}
```

Usage remains the same:

```js
import LiveDataFetcher from './live-data-fetcher.js';

const ldf = new LiveDataFetcher(null, null, 'BTCUSDT');
const price = await ldf.fetchCurrentPrice();
console.log(price);
```


Here are 5 targeted improvements with code snippets that enhance the original **Bybit** data fetching logic while maintaining backward compatibility:

#### 1. Add Axios Retry Interceptor with Exponential Backoff
```js
// Add this inside the constructor after `this.http = axios.create(...)`
this.http.interceptors.response.use(undefined, (error) => {
  const config = error.config;
  if (!config || !config.retryCount) return Promise.reject(error);
  
  const maxRetries = 3;
  const retryDelay = Math.min(1000 * Math.pow(2, config.retryCount), 8000);
  
  return new Promise((resolve) => {
    setTimeout(() => {
      config.retryCount++;
      logger.warn(
        chalk.yellow(
          `Retry ${config.retryCount}/${maxRetries} in ${retryDelay}ms for ${config.url}`
        )
      );
      resolve(this.http(config));
    }, retryDelay);
  });
});
```
This implements **exponential backoff**, a recommended practice for resilient API clients .

#### 2. Implement Request Throttling Using Promises
```js
// Replace the current `processQueue` method with this enhanced version
async processQueue() {
  if (this.isProcessingQueue || this.requestQueue.length === 0) return;

  this.isProcessingQueue = true;
  const queue = [...this.requestQueue]; // Prevent external mutations
  this.requestQueue = [];

  for (const item of queue) {
    const now = Date.now();
    const timeSinceLast = now - this.lastRequestTime;
    const delay = Math.max(0, this.rateLimitInterval - timeSinceLast);

    if (delay > 0) {
      await new Promise((r) => setTimeout(r, delay));
    }

    try {
      const result = await item.func();
      item.resolve(result);
    } catch (error) {
      item.reject(error);
    } finally {
      this.lastRequestTime = Date.now();
      this.emit('requestProcessed', { success: true });
    }
  }

  this.isProcessingQueue = false;
}
```
This ensures atomic queue processing and emits lifecycle events for observability.

#### 3. Validate and Sanitize API Responses Early
```js
// Wrap the response check in a utility function
const isValidApiResponse = (data) => {
  return data?.retCode === 0 && Array.isArray(data.result?.list) && data.result.list.length > 0;
};

// Replace the condition in both `fetchCurrentPrice` and `fetchKlineData`:
if (isValidApiResponse(data)) { ... }
```
Early validation prevents downstream errors from malformed data and aligns with **code review** best practices for defect detection .

#### 4. Add Environment-Based Credential Fallback
```js
// Update the constructor parameter defaults
constructor(
  apiKey = process.env.BYBIT_API_KEY || null,
  apiSecret = process.env.BYBIT_API_SECRET || null,
  tradingSymbol,
  opts = {}
) {
  super();
  // ... rest unchanged
}
```
This follows secure **Node.js** patterns by preferring environment variables over hardcoded credentials .

#### 5. Introduce Typed Options with Defaults
```js
// Enhance constructor with structured options
constructor(
  apiKey,
  apiSecret,
  tradingSymbol,
  {
    rateLimitInterval = 1000,
    timeout = 10_000,
    maxRetries = 3,
    maxQueueSize = 100,
  } = {}
) {
  super();
  this.apiKey = apiKey;
  this.apiSecret = apiSecret;
  this.tradingSymbol = tradingSymbol;
  this.baseUrl = 'https://api.bybit.com';
  this.rateLimitInterval = rateLimitInterval;
  this.maxRetries = maxRetries;
  this.maxQueueSize = maxQueueSize;
  this.timeout = timeout;
  // ... rest unchanged
}
```
This improves **developer experience** through clear defaults and bounds, reducing configuration errors.

These improvements maintain the public API surface while adding resilience, observability, and security—key goals in modern **JavaScript** development .Below, I've selected 5 key improvements from the enhanced code I provided earlier. Each snippet includes a brief description of the improvement, why it's beneficial, and the relevant code excerpt. These snippets are modular and can be integrated into the original code if needed, but they align with the overall enhanced version. I've kept them focused on specific parts of the class for clarity.

### 1. **Enhanced Configuration with Options**
   This improvement adds flexibility by allowing users to pass an options object to the constructor, supporting features like testnet mode, custom rate limits, and category selection. It makes the class more adaptable without changing the core format.

   ```javascript
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
     
     // ... (other initializations)
     
     // Axios instance with enhanced configuration
     this.axiosInstance = axios.create({
       baseURL: this.useTestnet ? this.testnetUrl : this.baseUrl,
       timeout: this.requestTimeout,
       headers: {
         'X-Referer': 'trading-bot',
         'Content-Type': 'application/json'
       }
     });
   }
   ```

### 2. **Caching System for API Responses**
   This adds a simple in-memory cache with TTL (time-to-live) to reduce API calls for repeated requests, improving performance and respecting rate limits. It includes cache hit tracking for metrics.

   ```javascript
   // Cache configuration (in constructor)
   this.cacheEnabled = options.cacheEnabled !== false;
   this.cache = new Map();
   this.cacheTTL = options.cacheTTL || 5000; // 5 seconds default

   // Cache management methods
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

   // Example usage in fetchCurrentPrice
   const cacheKey = `price_${this.tradingSymbol}`;
   const cached = this.getCached(cacheKey);
   if (cached) {
     return cached;
   }
   // ... (fetch logic)
   this.setCache(cacheKey, result);
   ```

### 3. **Circuit Breaker for Failure Handling**
   This implements a circuit breaker pattern to temporarily halt requests during repeated failures, preventing API overload and cascading errors. It auto-resets after a timeout.

   ```javascript
   // Circuit breaker configuration (in constructor)
   this.circuitBreakerThreshold = options.circuitBreakerThreshold || 5;
   this.circuitBreakerTimeout = options.circuitBreakerTimeout || 60000;
   this.circuitBreakerFailures = 0;
   this.circuitBreakerOpenedAt = null;

   // Circuit breaker check method
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

   // Usage in processQueue
   if (this.isCircuitOpen()) {
     reject(new Error('Circuit breaker is open - API temporarily unavailable'));
     continue;
   }
   ```

### 4. **Retry Logic with Exponential Backoff**
   This enhances error resilience by automatically retrying failed requests with increasing delays (exponential backoff), reducing the chance of permanent failures due to transient issues.

   ```javascript
   // In processQueue (excerpt)
   while (this.requestQueue.length > 0) {
     const { resolve, reject, func, retryCount = 0 } = this.requestQueue.shift();

     // ... (rate limit delay)

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
   ```

### 5. **Performance Metrics Tracking**
   This adds monitoring of key metrics like request success rates, response times, and cache hits, helping with debugging and optimization. It includes a method to retrieve metrics.

   ```javascript
   // Metrics initialization (in constructor)
   this.metrics = {
     totalRequests: 0,
     successfulRequests: 0,
     failedRequests: 0,
     cacheHits: 0,
     averageResponseTime: 0,
     responseTimes: []
   };

   // Update metrics method
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

   // Get metrics method
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

   // Usage in interceptors (excerpt)
   const duration = Date.now() - response.config.metadata.startTime;
   this.updateMetrics(duration, true);
   ```


Here are 5 targeted improvements with code snippets that enhance the original `LiveDataFetcher` class while preserving its interface and compatibility:

---

#### 1. **Axios Instance with Retry Interceptor**

Add a robust Axios instance with exponential backoff for network resilience. This replaces raw `axios.get()` calls with a configured instance that retries on failure.

```js
// Replace the plain axios import and usage with:
this.http = axios.create({
  baseURL: this.baseUrl,
  timeout: 10_000,
});

this.http.interceptors.response.use(undefined, async (error) => {
  const config = error.config;
  if (!config || !config.retryCount) return Promise.reject(error);

  const maxRetries = 3;
  const retryDelay = Math.min(1000, 2 ** config.retryCount * 500);
  logger.warn(
    chalk.yellow(
      `Request failed (${error.response?.status || error.code}), retrying in ${retryDelay}ms (attempt ${config.retryCount}/${maxRetries})`
    )
  );

  await new Promise((r) => setTimeout(r, retryDelay));
  config.retryCount++;
  return this.http(config);
});
```

> This implements **exponential backoff** and avoids infinite retries, aligning with best practices for API resilience .

---

#### 2. **Typed Error Handling with `instanceof`**

Improve error differentiation by checking for specific error types, such as Axios errors vs. system errors.

```js
} catch (error) {
  if (axios.isAxiosError(error)) {
    logger.error(
      chalk.red(
        `Axios Error: ${error.response?.data?.retMsg || error.message}`
      )
    );
  } else if (error instanceof Error) {
    logger.error(chalk.red(`JavaScript Error: ${error.message}`));
  } else {
    logger.error(chalk.red(`Unknown error type: ${JSON.stringify(error)}`));
  }
  return null;
}
```

> Use `axios.isAxiosError()` to safely distinguish HTTP-related errors from runtime exceptions .

---

#### 3. **Promise Chain Finalizer with `.finally()`**

Ensure cleanup or logging always occurs after `.then()` chains, even on rejection.

```js
new Promise(tetheredGetNumber)
  .then(determineParity)
  .then(promiseGetWord)
  .catch((reason) => {
    if (reason.cause) {
      console.error("Had previously handled error");
    } else {
      console.error(`Trouble: ${reason}`);
    }
  })
  .finally(() => console.log("All done"));
```

> The `finally()` block guarantees execution, useful for logging or state reset after API calls .

---

#### 4. **Custom Error Subclass for API Failures**

Define a dedicated error type for Bybit API failures to enable precise catching.

```js
class BybitAPIError extends Error {
  constructor(message, code, data) {
    super(message);
    this.name = "BybitAPIError";
    this.code = code;
    this.data = data;
  }
}

// In fetch logic:
if (response.data?.retCode !== 0) {
  throw new BybitAPIError(response.data?.retMsg, response.data?.retCode, response.data);
}
```

> Subclassing `Error` allows clean `instanceof` checks and better debugging .

---

#### 5. **Queue Processing with Throttling and Backpressure**

Refine the request queue to enforce strict rate limits and prevent overload.

```js
async _processQueue() {
  if (this.isProcessingQueue || !this.requestQueue.length) return;
  this.isProcessingQueue = true;

  while (this.requestQueue.length) {
    const { taskFn, resolve, reject } = this.requestQueue.shift();
    const now = Date.now();
    const timeSinceLast = now - this.lastRequestTime;

    if (timeSinceLast < this.rateLimitInterval) {
      await new Promise((r) => setTimeout(r, this.rateLimitInterval - timeSinceLast));
    }

    try {
      const result = await taskFn();
      resolve(result);
    } catch (err) {
      reject(err);
    } finally {
      this.lastRequestTime = Date.now();
    }
  }
  this.isProcessingQueue = false;
}
```

> This enforces a minimum interval between requests, critical when hitting rate-limited APIs like Bybit .
Below, I've selected 5 key improvements from the enhanced `LiveDataFetcher` class I provided in the previous response. Each snippet includes:

- **Description**: A brief explanation of the improvement, why it's beneficial, and how it enhances the original code (e.g., reliability, performance, or usability) while maintaining compatibility.
- **Code Snippet**: A focused, self-contained excerpt of the improved code. These can be directly integrated into the class if needed.

These snippets highlight modular enhancements that build on the original structure without breaking existing functionality.

### 1. **Caching System**
   **Description**: Adds a simple in-memory cache with TTL (time-to-live) to reduce API calls for repeated requests (e.g., fetching the same price multiple times). This improves performance and reduces rate-limiting risks. Cache hits are tracked in metrics for monitoring. It's optional and configurable via constructor options.

   ```javascript
   // Cache configuration (in constructor)
   this.cacheEnabled = options.cacheEnabled !== false;
   this.cache = new Map();
   this.cacheTTL = options.cacheTTL || 5000; // 5 seconds default

   // Cache management methods
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

   // Example usage in fetchCurrentPrice
   const cacheKey = `price_${this.tradingSymbol}`;
   const cached = this.getCached(cacheKey);
   if (cached) return cached;
   // ... (API call)
   this.setCache(cacheKey, result);
   ```

### 2. **Circuit Breaker Pattern**
   **Description**: Implements a circuit breaker to temporarily halt requests after a threshold of consecutive failures, preventing API overload during outages. This enhances reliability and resilience, with automatic reset after a timeout. It integrates seamlessly with the queue processor.

   ```javascript
   // Circuit breaker config (in constructor)
   this.circuitBreakerThreshold = options.circuitBreakerThreshold || 5;
   this.circuitBreakerTimeout = options.circuitBreakerTimeout || 60000;
   this.circuitBreakerFailures = 0;
   this.circuitBreakerOpenedAt = null;

   // Circuit breaker check method
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

   // Integration in processQueue
   while (this.requestQueue.length > 0) {
     const { resolve, reject, func, retryCount = 0 } = this.requestQueue.shift();
     if (this.isCircuitOpen()) {
       reject(new Error('Circuit breaker is open - API temporarily unavailable'));
       continue;
     }
     // ... (rest of queue processing)
   }
   ```

### 3. **Retry Logic with Exponential Backoff**
   **Description**: Adds automatic retries for failed requests with exponential backoff delays, reducing the impact of transient errors (e.g., network issues). This improves robustness without changing the original queue-based request handling. Configurable via constructor options.

   ```javascript
   // Retry config (in constructor)
   this.maxRetries = options.maxRetries || 3;
   this.retryDelay = options.retryDelay || 2000;

   // In processQueue (try-catch block)
   try {
     const result = await func();
     resolve(result);
     this.errorCount = 0; // Reset error count on success
   } catch (error) {
     this.errorCount++;
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
   ```

### 4. **Performance Metrics Tracking**
   **Description**: Introduces metrics collection for requests (e.g., success rate, average response time, cache hits) using Axios interceptors. This provides observability for debugging and optimization, with a `getMetrics()` method for easy access. It doesn't alter core functionality but adds valuable insights.

   ```javascript
   // Metrics init (in constructor)
   this.metrics = {
     totalRequests: 0,
     successfulRequests: 0,
     failedRequests: 0,
     cacheHits: 0,
     averageResponseTime: 0,
     responseTimes: []
   };

   // Update metrics method
   updateMetrics(responseTime, success) {
     this.metrics.totalRequests++;
     if (success) {
       this.metrics.successfulRequests++;
       this.circuitBreakerFailures = 0;
     } else {
       this.metrics.failedRequests++;
       this.circuitBreakerFailures++;
     }
     this.metrics.responseTimes.push(responseTime);
     if (this.metrics.responseTimes.length > 100) {
       this.metrics.responseTimes.shift();
     }
     this.metrics.averageResponseTime = 
       this.metrics.responseTimes.reduce((a, b) => a + b, 0) / this.metrics.responseTimes.length;
   }

   // getMetrics method
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

   // Example: Call in interceptors to update metrics
   ```

### 5. **Enhanced Data Validation in fetchKlineData**
   **Description**: Adds input validation for intervals and limits, plus response data validation to filter invalid klines. This prevents errors from bad inputs or API responses, improving data quality and reliability. Calculated fields (e.g., change percent) are added for richer insights without changing the method signature.

   ```javascript
   // In fetchKlineData func
   try {
     // Validate inputs
     const validIntervals = ['1', '3', '5', '15', '30', '60', '120', '240', '360', '720', 'D', 'W', 'M'];
     if (!validIntervals.includes(String(interval))) {
       throw new Error(`Invalid interval: ${interval}. Valid intervals: ${validIntervals.join(', ')}`);
     }
     if (limit < 1 || limit > 1000) {
       throw new Error(`Invalid limit: ${limit}. Must be between 1 and 1000`);
     }

     // ... (API call)

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

     // ... (caching and return)
   } catch (error) {
     // ... (error handling)
   }
   ```
