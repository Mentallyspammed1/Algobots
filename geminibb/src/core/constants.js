// src/core/constants.js

export const ACTIONS = Object.freeze({
    PROPOSE_TRADE: 'proposeTrade',
    PROPOSE_EXIT: 'proposeExit',
    HOLD: 'hold',
    HALT: 'halt', // IMPROVEMENT 18: New action for severe risk policy breaches
});

export const SIDES = Object.freeze({
    BUY: 'Buy',
    SELL: 'Sell',
});