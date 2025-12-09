/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (Main Entry Point)
 * ======================================================
 * This is the main script that initializes and runs the trading bot.
 * It orchestrates all the refactored components.
 * 
 * To run this bot:
 * 1. Ensure you have Node.js installed.
 * 2. Install dependencies: `npm install` (if you have a package.json) or manually install required packages (axios, decimal.js, chalk, @google/generative-ai, dotenv).
 * 3. Set environment variables: BYBIT_API_KEY, GEMINI_API_KEY (e.g., using a .env file).
 * 4. Customize config.json with your preferred settings.
 * 5. Run the script: `node main.js`
 * 
 * For JSON output instead of HUD, set OUTPUT_MODE=JSON environment variable:
 * `OUTPUT_MODE=JSON node main.js`
 */

// Import core modules
import { TradingEngine } from './src/trading-engine.js';
import { ConfigManager } from './src/config.js';
import { NEON } from './src/ui.js'; // For console coloring

// --- MAIN EXECUTION ---
(async () => {
    try {
        // Load configuration first to ensure all settings are available
        const config = await ConfigManager.load();
        
        // Instantiate the Trading Engine with the loaded configuration
        const engine = new TradingEngine(config);
        
        // Initialize engine components (like API connections, data fetching)
        await engine.initialize();
        // Start the main trading loop
        await engine.start(); 
        
    } catch (e) {
        // Handle critical initialization errors that prevent the bot from starting
        console.error(NEON.RED(`[FATAL] Failed to initialize Leviathan: ${e.message}`));
        if (e.stack) console.error(e.stack); // Log stack trace for debugging
        process.exit(1); // Exit with an error code
    }
})();