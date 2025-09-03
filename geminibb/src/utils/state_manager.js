import { promises as fs } from 'fs';
import path from 'path';
import logger from './logger.js';

const stateFilePath = path.resolve('trading_state.json');
export const defaultState = {
    inPosition: false,
    positionSide: null,
    entryPrice: 0,
    quantity: 0,
    orderId: null,
};

export async function loadState() {
    try {
        const data = await fs.readFile(stateFilePath, 'utf-8');
        return JSON.parse(data);
    } catch (error) {
        if (error.code === 'ENOENT') {
            logger.info("No state file found, creating a new one.");
            await saveState(defaultState);
            return { ...defaultState };
        }
        logger.exception(error);
        return { ...defaultState };
    }
}

export async function saveState(state) {
    try {
        await fs.writeFile(stateFilePath, JSON.stringify(state, null, 2));
        logger.info("Trading state has been saved.");
    } catch (error) {
        logger.exception(error);
    }
}