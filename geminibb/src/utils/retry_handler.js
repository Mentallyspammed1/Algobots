// src/utils/retry_handler.js
import { Constants } from './constants.js';
import { Logger } from './logger.js';

const { RETRY_DEFAULTS } = Constants;
const logger = new Logger('RETRY_HANDLER');

/**
 * Checks if an error is retryable.
 * @param {Error} error - The error to check.
 * @returns {boolean} - True if the error is retryable, false otherwise.
 */
function isRetryableError(error) {
    // Example: Add logic to check HTTP status codes (e.g., 429, 5xx) or specific error messages
    if (error.name === 'AbortError' || error.message.includes('network')) { // Network related errors
        return true;
    }
    // For fetch errors, check status if available
    if (error.response && (error.response.status === 429 || error.response.status >= 500)) {
        return true;
    }
    return false;
}

/**
 * A higher-order function to add retry logic to an async function.
 * @param {function} func - The async function to wrap.
 * @param {object} options - Retry options.
 * @param {number} options.maxAttempts - Maximum number of retry attempts.
 * @param {number} options.initialDelayMs - Initial delay before first retry in milliseconds.
 * @param {number} options.maxDelayMs - Maximum delay between retries in milliseconds.
 * @param {number} options.jitterFactor - Factor for adding random jitter to delay.
 * @returns {function} - The wrapped async function with retry logic.
 */
export function withRetry(func, options = {}) {
    const {
        maxAttempts = RETRY_DEFAULTS.MAX_ATTEMPTS,
        initialDelayMs = RETRY_DEFAULTS.INITIAL_DELAY_MS,
        maxDelayMs = RETRY_DEFAULTS.MAX_DELAY_MS,
        jitterFactor = RETRY_DEFAULTS.JITTER_FACTOR
    } = options;

    return async (...args) => {
        let attempts = 0;
        let delay = initialDelayMs;

        while (attempts < maxAttempts) {
            try {
                return await func(...args);
            } catch (error) {
                attempts++;
                if (attempts >= maxAttempts || !isRetryableError(error)) {
                    logger.error(`Failed after ${attempts} attempts. Last error: ${error.message}`);
                    throw error;
                }

                const jitter = Math.random() * jitterFactor * delay;
                const sleepTime = Math.min(maxDelayMs, delay + jitter);
                logger.warn(`Attempt ${attempts} failed for ${func.name}. Retrying in ${sleepTime.toFixed(2)}ms... Error: ${error.message}`);

                await new Promise(resolve => setTimeout(resolve, sleepTime));
                delay *= 2; // Exponential backoff
            }
        }
    };
}