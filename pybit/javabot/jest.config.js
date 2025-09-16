/** @type {import('jest').Config} */
const config = {
  verbose: true,
  testEnvironment: 'node',
  transform: {
    '^.+\.js$': 'babel-jest',
  },
  // Allow Jest to transform ESM packages in node_modules
  transformIgnorePatterns: [],

  testMatch: ['**/tests/**/*.test.js'],
  // Automatically clear mock calls, instances and results before every test
  clearMocks: true,

  // The directory where Jest should output its coverage files
  coverageDirectory: 'coverage',

  // A list of paths to directories that Jest should use to search for files in
  roots: ['<rootDir>'],

  // A map from regular expressions to module names or to arrays of module names that allow to stub out resources with a single module
  moduleNameMapper: {
    // Mock logger to prevent console output during tests
    '^../logger.js$': '<rootDir>/tests/mocks/logger.mock.js',
    // Add other mocks here as needed
  },

  // Indicates which provider should be used to instrument code for coverage
  coverageProvider: 'v8',

  // A list of reporter names that Jest uses when writing coverage reports
  coverageReporters: [
    'json',
    'text',
    'lcov',
    'clover'
  ],
};

export default config;