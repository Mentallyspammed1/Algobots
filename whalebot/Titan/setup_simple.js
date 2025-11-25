#!/usr/bin/env node

/**
 * WHALEWAVE TITAN v7.0 Setup Script (Simplified)
 * ===============================================
 * Standalone setup without external dependencies
 */

import fs from 'fs/promises';
import path from 'path';
import { execSync } from 'child_process';

// Simple color functions (no external dependencies)
const colors = {
    info: (text) => `🔵 ${text}`,
    success: (text) => `✅ ${text}`,
    warning: (text) => `⚠️ ${text}`,
    error: (text) => `❌ ${text}`,
    bold: (text) => `\x1b[1m${text}\x1b[0m`,
    cyan: (text) => `\x1b[36m${text}\x1b[0m`
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
        risk: {
            maxDailyLoss: 0.05,
            maxDrawdown: 0.10,
            positionSize: 0.02,
            stopLossPercent: 0.02,
            takeProfitPercent: 0.06
        },
        signals: {
            minIndicators: 3,
            aiWeight: 0.4,
            techWeight: 0.6,
            trendWeight: 0.8,
            volumeWeight: 0.7
        }
    }
};

// ANSI color codes for better terminal output
const ansi = {
    reset: '\x1b[0m',
    bright: '\x1b[1m',
    dim: '\x1b[2m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m'
};

/**
 * Enhanced logging with colors
 */
function log(level, message) {
    const colorMap = {
        info: ansi.blue,
        success: ansi.green,
        warning: ansi.yellow,
        error: ansi.red
    };
    
    const color = colorMap[level] || ansi.reset;
    console.log(`${color}${message}${ansi.reset}`);
}

/**
 * Get Node.js version
 */
function getNodeVersion() {
    try {
        return process.version;
    } catch (error) {
        return 'unknown';
    }
}

/**
 * Check Node.js version
 */
function checkNodeVersion() {
    log('info', '🔍 Checking Node.js version...');
    
    const currentVersion = getNodeVersion();
    const requiredVersion = setupConfig.requiredNodeVersion;
    
    // Simple version comparison
    const current = parseFloat(currentVersion.replace('v', ''));
    const required = parseFloat(requiredVersion);
    
    if (current < required) {
        log('error', `❌ Node.js ${requiredVersion}+ required. Current: ${currentVersion}`);
        log('info', '💡 Update Node.js: https://nodejs.org/');
        return false;
    }
    
    log('success', `✅ Node.js version: ${currentVersion}`);
    return true;
}

/**
 * Check if required files exist
 */
async function checkRequiredFiles() {
    log('info', '🔍 Checking required files...');
    
    let allFilesExist = true;
    
    for (const file of setupConfig.requiredFiles) {
        try {
            await fs.access(file);
            log('success', `✅ ${file} found`);
        } catch (error) {
            log('error', `❌ ${file} missing`);
            allFilesExist = false;
        }
    }
    
    return allFilesExist;
}

/**
 * Check environment variables
 */
function checkEnvironmentVariables() {
    log('info', '🔍 Checking environment variables...');
    
    let allVarsSet = true;
    
    // Check required variables
    for (const envVar of setupConfig.requiredEnvVars) {
        if (!process.env[envVar]) {
            log('error', `❌ ${envVar} not set`);
            allVarsSet = false;
        } else {
            log('success', `✅ ${envVar} configured`);
        }
    }
    
    // Check optional variables
    for (const envVar of setupConfig.optionalEnvVars) {
        if (process.env[envVar]) {
            log('info', `ℹ️ ${envVar}: ${process.env[envVar]}`);
        }
    }
    
    return allVarsSet;
}

/**
 * Install dependencies
 */
function installDependencies() {
    log('info', '📦 Installing dependencies...');
    
    try {
        // Try npm install with local configuration
        execSync('npm install --prefix ./npm-local', { stdio: 'inherit' });
        log('success', '✅ Dependencies installed successfully');
        return true;
    } catch (error) {
        log('warning', '⚠️ npm install failed, dependencies may need manual installation');
        log('info', '💡 Run: npm install');
        return false;
    }
}

/**
 * Create configuration file
 */
async function createConfigFile() {
    log('info', '⚙️ Setting up configuration...');
    
    try {
        const configExists = await fs.access('config.json').then(() => true).catch(() => false);
        
        if (configExists) {
            log('warning', '⚠️ config.json already exists');
            log('info', 'ℹ️ Keeping existing configuration');
            return true;
        }
        
        const config = JSON.stringify(setupConfig.defaultConfig, null, 2);
        await fs.writeFile('config.json', config);
        log('success', '✅ Configuration file created');
        log('info', '💡 Edit config.json to customize settings');
        return true;
    } catch (error) {
        log('error', `❌ Failed to create config.json: ${error.message}`);
        return false;
    }
}

/**
 * Create environment file template
 */
async function createEnvFile() {
    log('info', '🔐 Setting up environment...');
    
    try {
        const envExists = await fs.access('.env').then(() => true).catch(() => false);
        
        if (envExists) {
            log('warning', '⚠️ .env file already exists');
            log('info', 'ℹ️ Keeping existing environment configuration');
            return true;
        }
        
        const envTemplate = `# WHALEWAVE TITAN Environment Configuration
# =====================================

# Required: Gemini AI API Key (get from https://makersuite.google.com/)
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: Development settings
NODE_ENV=development

# Optional: Logging level
LOG_LEVEL=info
`;
        
        await fs.writeFile('.env', envTemplate);
        log('success', '✅ Environment template created');
        log('warning', '⚠️ Please edit .env and add your GEMINI_API_KEY');
        return true;
    } catch (error) {
        log('error', `❌ Failed to create .env: ${error.message}`);
        return false;
    }
}

/**
 * System checks
 */
async function runSystemChecks() {
    log('bold', '\n🧪 Running system checks...');
    
    const checks = [
        {
            name: 'Node.js Version',
            check: checkNodeVersion
        },
        {
            name: 'Required Files',
            check: checkRequiredFiles
        },
        {
            name: 'Environment Variables',
            check: checkEnvironmentVariables
        }
    ];
    
    let allPassed = true;
    
    for (const check of checks) {
        try {
            const result = await check.check();
            if (!result) allPassed = false;
        } catch (error) {
            console.log(`❌ ${check.name}: Failed - ${error.message}`);
            allPassed = false;
        }
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
        // Run system checks first
        const systemChecksPassed = await runSystemChecks();
        
        if (!systemChecksPassed) {
            console.log('\n⚠️ Some system checks failed, but continuing with setup...');
        }
        
        // Continue with setup regardless of system checks
        
        // Install dependencies
        const depsInstalled = installDependencies();
        
        // Create configuration
        const configCreated = await createConfigFile();
        
        // Create environment file
        const envCreated = await createEnvFile();
        
        if (depsInstalled && configCreated && envCreated) {
                console.log(colors.bold(colors.success(`
                
    🎉 SETUP COMPLETED SUCCESSFULLY!
    =================================
    
    ✅ All dependencies installed
    ✅ Configuration files created
    ✅ Environment template ready
    
    📋 Next Steps:
    1. Edit .env and add your GEMINI_API_KEY
    2. Edit config.json to customize settings
    3. Run: npm start
    
    🚀 Happy Trading!
    `)));
                
                // Optionally start the bot
                const rl = await import('readline').then(m => m.createInterface({
                    input: process.stdin,
                    output: process.stdout
                }));
                
                const answer = await new Promise(resolve => {
                    rl.question('❓ Would you like to start WHALEWAVE TITAN now? (y/N): ', resolve);
                });
                
                rl.close();
                
                if (answer.toLowerCase() === 'y' || answer.toLowerCase() === 'yes') {
                    console.log(colors.info('🚀 Starting WHALEWAVE TITAN...'));
                    try {
                        execSync('npm start', { stdio: 'inherit' });
                    } catch (error) {
                        console.log(colors.error('Failed to start the bot'));
                    }
                }
            } else {
                setupSuccessful = false;
            }
        
        if (!setupSuccessful) {
            console.log(colors.bold(colors.error(`
            
    ⚠️ Setup completed with warnings
    ================================
    
    Some issues were encountered during setup.
    Please review the messages above and resolve any issues.
    
    You can try running setup again with: node setup_simple.js
    `)));
        }
        
    } catch (error) {
        console.error(colors.error(`Setup failed: ${error.message}`));
        console.error(colors.info('Please check your permissions and try again.'));
        setupSuccessful = false;
    }
    
    process.exit(setupSuccessful ? 0 : 1);
}

// Run the setup
main().catch(console.error);