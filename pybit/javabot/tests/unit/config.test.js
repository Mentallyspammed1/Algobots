import { jest } from '@jest/globals';

// Define the mock implementation we can control throughout the tests
const mockFs = {
  existsSync: jest.fn(),
  readFileSync: jest.fn(),
};

// Use the modern unstable_mockModule API
jest.unstable_mockModule('fs', () => ({
  default: mockFs, // Mock the default export
  ...mockFs,      // Mock named exports like existsSync, readFileSync
}));

describe('Config Singleton', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    // Reset modules before each test to ensure a fresh import of the config singleton
    jest.resetModules();
    // Clear mock history and reset implementations
    mockFs.existsSync.mockClear();
    mockFs.readFileSync.mockClear();
    // Restore environment variables
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    // Restore original environment after all tests in this file
    process.env = originalEnv;
  });

  it('should load default values when no config file is found', async () => {
    mockFs.existsSync.mockReturnValue(false);
    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.TESTNET).toBe(false);
    expect(CONFIG.LOOP_WAIT_TIME_SECONDS).toBe(5);
    expect(CONFIG.STRATEGIES.ehlst.enabled).toBe(false);
  });

  it('should load and override defaults from a YAML file', async () => {
    const yamlContent = `
      TESTNET: true
      LOOP_WAIT_TIME_SECONDS: 15
      STRATEGIES:
        ehlst:
          enabled: true
          LEVERAGE: 25
    `;
    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(yamlContent);

    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.TESTNET).toBe(true);
    expect(CONFIG.LOOP_WAIT_TIME_SECONDS).toBe(15);
    expect(CONFIG.STRATEGIES.ehlst.enabled).toBe(true);
    expect(CONFIG.STRATEGIES.ehlst.LEVERAGE).toBe(25);
    expect(CONFIG.MAX_POSITIONS).toBe(1); // A default value
  });

  it('should allow environment variables to override YAML and defaults', async () => {
    process.env.TESTNET = 'false';
    process.env.DRY_RUN = 'true';
    process.env.LOOP_WAIT_TIME_SECONDS = '42';

    const yamlContent = `
      TESTNET: true
      LOOP_WAIT_TIME_SECONDS: 15
    `;
    mockFs.existsSync.mockReturnValue(true);
    mockFs.readFileSync.mockReturnValue(yamlContent);

    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.TESTNET).toBe(false);
    expect(CONFIG.DRY_RUN).toBe(true);
    expect(CONFIG.LOOP_WAIT_TIME_SECONDS).toBe('42');
  });

  it('should set LOG_LEVEL to debug when DEBUG_MODE is true', async () => {
    process.env.DEBUG_MODE = 'true';
    mockFs.existsSync.mockReturnValue(false);

    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.DEBUG_MODE).toBe(true);
    expect(CONFIG.LOG_LEVEL).toBe('debug');
  });

  it('should throw an error if API keys are missing and not in dry_run mode', async () => {
    process.env.DRY_RUN = 'false';
    delete process.env.BYBIT_API_KEY;
    delete process.env.BYBIT_API_SECRET;

    mockFs.existsSync.mockReturnValue(false);

    // We expect the import itself to throw an error
    await expect(import('../../config.js')).rejects.toThrow(
      'ERROR: API_KEY and API_SECRET must be provided in .env or config.yaml for live trading.'
    );
  });

  it('should NOT throw an error if API keys are missing but in dry_run mode', async () => {
    process.env.DRY_RUN = 'true';
    delete process.env.BYBIT_API_KEY;
    delete process.env.BYBIT_API_SECRET;

    mockFs.existsSync.mockReturnValue(false);

    // We expect the import to succeed without throwing
    await expect(import('../../config.js')).resolves.toBeDefined();
  });
});
