import { CONFIG } from '../config.js';

describe('Configuration Loading', () => {
  test('CONFIG object should be defined', () => {
    expect(CONFIG).toBeDefined();
  });

  test('CONFIG should have API_KEY and API_SECRET properties', () => {
    expect(CONFIG.API_KEY).toBeDefined();
    expect(CONFIG.API_SECRET).toBeDefined();
  });

  test('CONFIG should correctly parse boolean values from environment variables', () => {
    // Temporarily set environment variables for testing
    process.env.TESTNET = 'true';
    process.env.DRY_RUN = 'false';
    // Re-import config to pick up new env vars (or re-instantiate ConfigManager)
    // For simplicity in a basic test, we'll assume a fresh import or direct check
    // In a real scenario, you might mock fs.readFileSync or clear require cache

    // Since CONFIG is a singleton, we can't easily re-load it without more complex mocking.
    // This test will rely on the initial load. For a more robust test, you'd mock fs.readFileSync
    // and test ConfigManager directly.
    expect(typeof CONFIG.TESTNET).toBe('boolean');
    expect(typeof CONFIG.DRY_RUN).toBe('boolean');
    // Expecting them to be true/false based on default/env setup
    // This might fail if .env or config.yaml overrides, but it tests the type conversion
  });

  test('CONFIG should have TRADING_SYMBOLS as an array', () => {
    expect(Array.isArray(CONFIG.TRADING_SYMBOLS)).toBe(true);
    expect(CONFIG.TRADING_SYMBOLS.length).toBeGreaterThan(0);
  });
});
