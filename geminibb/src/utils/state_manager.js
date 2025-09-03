// src/utils/state_manager.js
import fs from 'fs/promises';
import path from 'path';
import logger from './logger.js';
import Decimal from 'decimal.js'; // IMPROVEMENT 15: Use Decimal for financial state values

const stateFilePath = path.resolve('bot_state.json');
const tempStateFilePath = path.resolve('bot_state.json.tmp');

export const defaultState = {
    _version: 1, // IMPROVEMENT 16: State versioning
    inPosition: false,
    positionSide: null, // 'Buy' or 'Sell'
    entryPrice: new Decimal(0).toString(), // IMPROVEMENT 15: Store as string for Decimal.js
    quantity: new Decimal(0).toString(), // IMPROVEMENT 15: Store as string for Decimal.js
    orderId: null,
    lastTradeTimestamp: 0,
    // IMPROVEMENT 18: Fields for daily loss tracking
    dailyLoss: new Decimal(0).toString(), // Total loss for the current day
    dailyPnlResetDate: new Date().toISOString().split('T')[0], // YYYY-MM-DD
    initialBalance: new Decimal(0).toString(), // Initial balance at start, for daily loss calc
    openPositionsCount: 0, // IMPROVEMENT 18: Track number of open positions (for future multi-position)
    openOrders: [], // IMPROVEMENT 19: Track open TP/SL orders or other pending orders
    isHalted: false, // IMPROVEMENT 20: New flag to indicate if bot is halted
    haltReason: null, // IMPROVEMENT 20: Reason for halting
};

// IMPROVEMENT 18: Helper to convert state values to Decimal for calculations
export function getDecimalState(state) {
    return {
        ...state,
        entryPrice: new Decimal(state.entryPrice),
        quantity: new Decimal(state.quantity),
        dailyLoss: new Decimal(state.dailyLoss),
        initialBalance: new Decimal(state.initialBalance),
    };
}

// IMPROVEMENT 18: Helper to convert Decimal back to string for saving
export function toSerializableState(state) {
    const serializable = { ...state };
    if (serializable.entryPrice instanceof Decimal) serializable.entryPrice = serializable.entryPrice.toString();
    if (serializable.quantity instanceof Decimal) serializable.quantity = serializable.quantity.toString();
    if (serializable.dailyLoss instanceof Decimal) serializable.dailyLoss = serializable.dailyLoss.toString();
    if (serializable.initialBalance instanceof Decimal) serializable.initialBalance = serializable.initialBalance.toString();
    return serializable;
}

export async function saveState(state) {
    try {
        const serializableState = toSerializableState(state); // Convert Decimals to string
        await fs.writeFile(tempStateFilePath, JSON.stringify(serializableState, null, 2));
        await fs.rename(tempStateFilePath, stateFilePath);
        logger.info("Successfully saved state.");
    } catch (error) {
        logger.error("Failed to save state to file.", error);
    }
}

export async function loadState() {
    try {
        await fs.access(stateFilePath);
        const data = await fs.readFile(stateFilePath, 'utf8');
        logger.info("Successfully loaded state from file.");
        const loaded = JSON.parse(data);
        // Merge with default state to ensure new fields are present
        // and convert financial strings back to Decimal objects for active use
        const mergedState = { ...defaultState, ...loaded };
        return getDecimalState(mergedState);
    } catch (error) {
        logger.warn("No state file found or failed to read. Using default state.");
        // Return default state with Decimal values initialized
        return getDecimalState(defaultState);
    }
}