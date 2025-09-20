module.exports = {
  testEnvironment: 'node',
  transform: {
    '^.+.js$': '<rootDir>/node_modules/babel-jest'
  },
  testMatch: [
    '**/__tests__/**/*.test.js',
    '**/tests/**/*.test.js'
  ],
  testRunner: 'jest-circus',
  setupFiles: ['<rootDir>/tests/jest.setup.js'],
};
