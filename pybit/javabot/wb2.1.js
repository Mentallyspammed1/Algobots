// sleep.js

/**
 * Asynchronous sleep function that pauses execution for a specified duration.
 * 
 * @param {number} ms - The duration in milliseconds to sleep.
 * @returns {Promise<void>} A promise that resolves after the specified duration.
 */
async function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// Export the sleep function for use in other modules
module.exports = sleep;
