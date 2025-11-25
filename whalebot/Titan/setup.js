#!/usr/bin/env node

/**
 * WHALEWAVE TITAN v7.0 Setup Script
 * ================================
 * Automated setup and configuration utility
 */

import fs from 'fs/promises';
import path from 'path';
import chalk from 'chalk';

const colors = {
    info: chalk.blue,
    success: chalk.green,
    warning: chalk.yellow,
    error: chalk.red,
    bold: chalk.bold,
    cyan: chalk.cyan
};

// Setup configuration
const setupConfig = {
    requiredNodeVersion: '18.0.0',
    requiredFiles: ['whalewave_titan_refactored.js', 'package.json'],
    requiredEnvVars: ['GEMINI_API_KEY'],
    optionalEnvVars: ['NODE_ENV'],
    defaultConfig: {
        symbol: 'BTCUSDT',
        intervals: { main: '3', trend: '15', daily: 'D' },
        limits: { kline: 300, trendKline: 100, orderbook: 50 },
        delays: { loop: 4000, retry: 1000 },
        ai: { model: 'gemini-1.5-flash', minConfidence: 0.75 },
        risk: {
            maxDrawdown: 10.0,
            dailyLossLimit: 5.0,
            maxPositions: 1,
            initialBalance: 1000.00,
            riskPercent: 2.0,
            leverageCap: 10,
            fee: 0.00055,
            slippage: 0.0001
        },
        indicators: {
            periods: {
                rsi: 10, stoch: 10, cci: 10, adx: 14,
                mfi: 10, chop: 14, linreg: 15, vwap: 20,
                bb: 20, keltner: 20, atr: 14, stFactor: 22,
                supertrend: 14
            },
            settings: {
                stochK: 3, stochD: 3, bbStd: 2.0, keltnerMult: 1.5,
                ceMult: 3.0
            },
            weights: {
                trendMTF: 2.2, trendScalp: 1.2, momentum: 1.8,
                macd: 1.0, regime: 0.8, squeeze: 1.0,
                liquidity: 1.5, divergence: 2.5, volatility: 0.5,
                actionThreshold: 2.0
            }
        },
        orderbook: { wallThreshold: 3.0, srLevels: 5 },
        api: { timeout: 8000, retries: 3, backoffFactor: 2 }
    }
};

/**
 * Check Node.js version
 */
async function checkNodeVersion() {
    console.log(colors.info('🔍 Checking Node.js version...'));
    
    const nodeVersion = process.version;
    const requiredVersion = setupConfig.requiredNodeVersion;
    
    if (nodeVersion < requiredVersion) {
        console.error(colors.error(`❌ Node.js ${requiredVersion}+ required. Current: ${nodeVersion}`));
        console.error(colors.info('💡 Update Node.js: https://nodejs.org/'));
        return false;
    }
    
    console.log(colors.success(`✅ Node.js version: ${nodeVersion}`));
    return true;
}

/**
 * Check required files
 */
async function checkRequiredFiles() {
    console.log(colors.info('🔍 Checking required files...'));
    
    for (const file of setupConfig.requiredFiles) {
        try {
            await fs.access(file);
            console.log(colors.success(`✅ ${file} found`));
        } catch {
            console.error(colors.error(`❌ ${file} missing`));
            return false;
        }
    }
    
    return true;
}

/**
 * Check environment variables
 */
async function checkEnvironment() {
    console.log(colors.info('🔍 Checking environment variables...'));
    
    // Check required variables
    let allValid = true;
    for (const envVar of setupConfig.requiredEnvVars) {
        if (!process.env[envVar]) {
            console.error(colors.error(`❌ ${envVar} not set`));
            allValid = false;
        } else {
            console.log(colors.success(`✅ ${envVar} configured`));
        }
    }
    
    // Check optional variables
    for (const envVar of setupConfig.optionalEnvVars) {
        if (process.env[envVar]) {
            console.log(colors.info(`ℹ️ ${envVar}: ${process.env[envVar]}`));
        }
    }
    
    return allValid;
}

/**
 * Install dependencies
 */
async function installDependencies() {
    console.log(colors.info('📦 Installing dependencies...'));
    
    try {
        const { execSync } = await import('child_process');
        
        // Try npm ci first, then npm install
        try {
            execSync('npm ci --silent', { stdio: 'inherit' });
        } catch {
            console.log(colors.warning('⚠️ npm ci failed, trying npm install...'));
            execSync('npm install --silent', { stdio: 'inherit' });
        }
        
        console.log(colors.success('✅ Dependencies installed successfully'));
        return true;
    } catch (error) {
        console.error(colors.error(`❌ Failed to install dependencies: ${error.message}`));
        console.error(colors.info('💡 Try running: npm install'));
        return false;
    }
}

/**
 * Create configuration file
 */
async function createConfigFile() {
    console.log(colors.info('⚙️ Setting up configuration...'));
    
    const configPath = 'config.json';
    
    try {
        await fs.access(configPath);
        console.log(colors.warning('⚠️ config.json already exists'));
        const overwrite = await askQuestion('Do you want to overwrite it? (y/N): ');
        
        if (overwrite.toLowerCase() !== 'y') {
            console.log(colors.info('ℹ️ Keeping existing configuration'));
            return true;
        }
    } catch {
        // File doesn't exist, create it
    }
    
    try {
        await fs.writeFile(configPath, JSON.stringify(setupConfig.defaultConfig, null, 2));
        console.log(colors.success('✅ Configuration file created'));
        console.log(colors.info('💡 Edit config.json to customize settings'));
        return true;
    } catch (error) {
        console.error(colors.error(`❌ Failed to create config.json: ${error.message}`));
        return false;
    }
}

/**
 * Create .env template
 */
async function createEnvTemplate() {
    console.log(colors.info('🔐 Setting up environment...'));
    
    const envPath = '.env';
    const envTemplate = `# WHALEWAVE TITAN Environment Configuration
# Copy this file and set your actual values

# Required: Google Gemini AI API Key
# Get your key from: https://makersuite.google.com/app/apikey
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Environment (development/production)
NODE_ENV=development

# Optional: Custom log level (error/warn/info/debug)
LOG_LEVEL=info
`;
    
    try {
        await fs.access(envPath);
        console.log(colors.warning('⚠️ .env file already exists'));
        return true;
    } catch {
        try {
            await fs.writeFile(envPath, envTemplate);
            console.log(colors.success('✅ Environment template created'));
            console.log(colors.warning('⚠️ Please edit .env and add your GEMINI_API_KEY'));
            return true;
        } catch (error) {
            console.error(colors.error(`❌ Failed to create .env: ${error.message}`));
            return false;
        }
    }
}

/**
 * Ask user question
 */
async function askQuestion(question) {
    return new Promise((resolve) => {
        process.stdout.write(question);
        process.stdin.resume();
        process.stdin.setEncoding('utf8');
        
        process.stdin.on('data', (data) => {
            process.stdin.pause();
            resolve(data.trim());
        });
    });
}

/**
 * Run system check
 */
async function runSystemCheck() {
    console.log(colors.bold('\n🧪 Running system checks...'));
    
    const checks = [
        { name: 'Node.js Version', fn: checkNodeVersion },
        { name: 'Required Files', fn: checkRequiredFiles },
        { name: 'Environment', fn: checkEnvironment }
    ];
    
    let allPassed = true;
    
    for (const check of checks) {
        console.log(`\n${colors.bold(check.name)}:`);
        const result = await check.fn();
        if (!result) allPassed = false;
    }
    
    return allPassed;
}

/**
 * Main setup function
 */
async function main() {
    console.log(colors.bold(colors.cyan(`
    🚀 WHALEWAVE TITAN v7.0 SETUP
    ==============================
    Professional Trading Bot Setup Utility
    `)));
    
    let setupSuccessful = true;
    
    try {
        // Check system requirements
        if (!await runSystemCheck()) {
            console.error(colors.error('\n❌ System check failed. Please fix the issues above.'));
            setupSuccessful = false;
        }
        
        // Setup configuration
        if (setupSuccessful && !await createConfigFile()) {
            setupSuccessful = false;
        }
        
        // Setup environment
        if (setupSuccessful && !await createEnvTemplate()) {
            setupSuccessful = false;
        }
        
        // Install dependencies
        if (setupSuccessful && !await installDependencies()) {
            setupSuccessful = false;
        }
        
        // Final status
        if (setupSuccessful) {
            console.log(colors.bold(colors.success(`
    ✅ SETUP COMPLETED SUCCESSFULLY!
    ============================
    
    Next steps:
    1. Edit .env and add your GEMINI_API_KEY
    2. Customize config.json if needed
    3. Run: npm start
    
    🎉 You're ready to trade!
    `)));
            
            // Check if user wants to start the bot
            const start = await askQuestion('\nStart the trading bot now? (y/N): ');
            if (start.toLowerCase() === 'y') {
                console.log(colors.info('🚀 Starting WHALEWAVE TITAN...'));
                const { execSync } = await import('child_process');
                execSync('node whalewave_titan_refactored.js', { stdio: 'inherit' });
            }
        } else {
            console.error(colors.bold(colors.error(`
    ❌ SETUP FAILED
    ===============
    Please fix the errors above and run setup again.
    `)));
        }
        
    } catch (error) {
        console.error(colors.error(`Setup failed: ${error.message}`));
        setupSuccessful = false;
    }
    
    process.exit(setupSuccessful ? 0 : 1);
}

// Run setup if called directly
if (import.meta.url === `file://${process.argv[1]}`) {
    main();
}

export { main as setup }; 