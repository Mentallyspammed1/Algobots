import fs from 'fs';
import { TradingEngine, ConfigManager } from './whalewave_for_optimizer.js';
import { Decimal } from 'decimal.js';

// 1. Define the parameter space for optimization
const parameterSpace = {
    'indicators.rsi': { type: 'int', low: 8, high: 20 },
    'indicators.macd_fast': { type: 'int', low: 10, high: 15 },
    'indicators.wss_weights.trend_mtf_weight': { type: 'float', low: 1.5, high: 3.0, precision: 2 },
    'indicators.wss_weights.momentum_normalized_weight': { type: 'float', low: 1.0, high: 2.5, precision: 2 },
};

const N_TRIALS = 30; // Number of different parameter combinations to test
const SIMULATION_ITERATIONS = 100; // Number of loops for each simulation

/**
 * Generates a random set of parameters based on the defined space.
 * @param {object} space - The parameter space definition.
 * @returns {object} A set of randomly generated parameters.
 */
function generateRandomParams(space) {
    const params = {};
    for (const key in space) {
        const def = space[key];
        let value;
        if (def.type === 'int') {
            value = Math.floor(Math.random() * (def.high - def.low + 1)) + def.low;
        } else if (def.type === 'float') {
            const rawValue = Math.random() * (def.high - def.low) + def.low;
            value = parseFloat(rawValue.toFixed(def.precision || 4));
        }
        
        const keys = key.split('.');
        let current = params;
        for (let i = 0; i < keys.length - 1; i++) {
            current[keys[i]] = current[keys[i]] || {};
            current = current[keys[i]];
        }
        current[keys[keys.length - 1]] = value;
    }
    return params;
}

/**
 * Runs a trading simulation with a given set of parameters.
 * @param {object} params - The parameters to test.
 * @returns {Promise<number>} The final balance after the simulation.
 */
async function runSimulation(params) {
    const config = ConfigManager.load();
    // Ensure mock_data is true for optimization runs
    const mergedConfig = ConfigManager.deepMerge(config, { ...params, mock_data: true });
    
    const engine = new TradingEngine(mergedConfig);
    
    // Modify the engine to run for a fixed number of iterations
    let iterations = 0;
    engine.isRunning = true;
    while (engine.isRunning && iterations < SIMULATION_ITERATIONS) {
        try {
            const data = await engine.dataProvider.fetchAll();
            if (!data) {
                await new Promise(resolve => setTimeout(resolve, mergedConfig.loop_delay * 1000));
                continue;
            }

            const analysis = await engine.performAnalysis(data);
            const context = engine.buildContext(data, analysis);
            const signal = await engine.ai.analyze(context);

            // Suppress dashboard output for cleaner optimization logs
            // engine.displayDashboard(data, context, signal);
            engine.exchange.evaluate(data.price, signal);

        } catch (e) {
            console.error(`Loop Critical Error: ${e.message}`);
        }
        iterations++;
    }
    
    return engine.exchange.balance.toNumber();
}


/**
 * Main optimization function.
 */
async function optimize() {
    console.log("🌊 Starting WhaleWave Profit Optimization...");
    console.log(`Running ${N_TRIALS} trials...`);

    let bestParams = {};
    let bestScore = -Infinity;

    for (let i = 0; i < N_TRIALS; i++) {
        const params = generateRandomParams(parameterSpace);
        
        console.log(`\n[Trial ${i + 1}/${N_TRIALS}]`);
        console.log('Testing parameters:', JSON.stringify(params, null, 2));

        const score = await runSimulation(params);
        console.log(`Trial Score (Final Balance): ${score.toFixed(2)}`);

        if (score > bestScore) {
            bestScore = score;
            bestParams = params;
            console.log(`🚀 New best parameters found!`);
        }
    }

    console.log('\n\n✅ Optimization Finished!');
    console.log('------------------------------------');
    console.log('🏆 Best Parameters Found:');
    console.log(JSON.stringify(bestParams, null, 2));
    console.log(`\n💰 Best Score (Final Balance): ${bestScore.toFixed(2)}`);
    console.log('------------------------------------');
    console.log('You can now update your config.json with these new parameters.');
}

// --- Start the optimization ---
optimize();
