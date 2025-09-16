import { jest } from '@jest/globals';

// Mock the logger functions
export const logger = {
  info: jest.fn(),
  warn: jest.fn(),
  error: jest.fn(),
  debug: jest.fn(),
  critical: jest.fn(),
};

// Mock the neon color functions
const identity = (str) => str;
export const neon = {
  header: identity,
  info: identity,
  success: identity,
  warn: identity,
  error: identity,
  critical: identity,
  dim: identity,
  price: identity,
  pnl: identity,
  bid: identity,
  ask: identity,
  blue: identity,
  purple: identity,
  cyan: identity,
  magenta: identity,
};
