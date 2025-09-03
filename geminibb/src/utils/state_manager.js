// src/utils/state_manager.js
import fs from 'fs/promises';
import path from 'path';
import logger from './logger.js';

const stateFilePath = path.resolve('bot_state.json');
const tempStateFilePath = path.resolve('bot_state.json.tmp');

export const defaultState = {
    inPosition: false,
    positionSide: null, // 'Buy' or 'Sell'
    entryPrice: 0,
    quantity: 0,
    orderId: null,
    lastTradeTimestamp: 0, // NEW: Timestamp of the last closed trade
};

// NEW: Atomic write operation for state safety
export async function saveState(state) {
    try {
        await fs.writeFile(tempStateFilePath, JSON.stringify(state, null, 2));
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
        // Merge with default state to ensure new fields are present
        return { ...defaultState, ...JSON.parse(data) };
    } catch (error) {
        logger.warn("No state file found or failed to read. Using default state.");
        return { ...defaultState };
    }
}