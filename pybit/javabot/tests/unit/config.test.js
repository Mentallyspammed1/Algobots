import { jest } from '@jest/globals';

// Mock the fs module before any imports
jest.mock('fs', async () => { // Make the factory async
  const { jest } = await import('@jest/globals'); // Import jest inside the factory
  return {
    existsSync: jest.fn(),
    readFileSync: jest.fn(),
  };
});

describe('Config Singleton', () => {
  const originalEnv = process.env;
  let fs;

  beforeEach(async () => {
    // Reset modules before each test to ensure a fresh import of the config singleton
    jest.resetModules();
    // Mock environment
    process.env = { ...originalEnv };
    // Import the mocked fs module so we can manipulate its mock functions
    fs = await import('fs');
  });

  afterAll(() => {
    // Restore original environment
    process.env = originalEnv;
  });

  it('should load default values when no config file is found', async () => {
    fs.existsSync.mockReturnValue(false);
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
    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(yamlContent);

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
    fs.existsSync.mockReturnValue(true);
    fs.readFileSync.mockReturnValue(yamlContent);

    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.TESTNET).toBe(false);
    expect(CONFIG.DRY_RUN).toBe(true);
    expect(CONFIG.LOOP_WAIT_TIME_SECONDS).toBe('42');
  });

  it('should set LOG_LEVEL to debug when DEBUG_MODE is true', async () => {
    process.env.DEBUG_MODE = 'true';
    fs.existsSync.mockReturnValue(false);

    const { CONFIG } = await import('../../config.js');

    expect(CONFIG.DEBUG_MODE).toBe(true);
    expect(CONFIG.LOG_LEVEL).toBe('debug');
  });

  it('should exit process if API keys are missing and not in dry_run mode', async () => {
    const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {});
    
    process.env.DRY_RUN = 'false';
    delete process.env.BYBIT_API_KEY;
    delete process.env.BYBIT_API_SECRET;

    fs.existsSync.mockReturnValue(false);
    await import('../../config.js');

    expect(mockExit).toHaveBeenCalledWith(1);
    mockExit.mockRestore();
  });

  it('should NOT exit process if API keys are missing but in dry_run mode', async () => {
    const mockExit = jest.spyOn(process, 'exit').mockImplementation(() => {});
    
    process.env.DRY_RUN = 'true';
    delete process.env.BYBIT_API_KEY;
    delete process.env.BYBIT_API_SECRET;

    fs.existsSync.mockReturnValue(false);
    await import('../../config.js');

    expect(mockExit).not.toHaveBeenCalled();
    mockExit.mockRestore();
  });
});