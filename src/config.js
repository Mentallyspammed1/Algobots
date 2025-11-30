const fs = require('fs');
const path = require('path');
const minimist = require('minimist');
const { log, colors } = require('./utils/logger');

const configPath = './agent.config.js';

const OFFICIAL_MODELS = [
  'gemini-1.5-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash-002', 'gemini-1.5-flash-latest',
  'gemini-1.5-pro', 'gemini-1.5-pro-001', 'gemini-1.5-pro-002', 'gemini-1.5-pro-latest',
  'gemini-1.0-pro', 'gemini-1.0-pro-latest', 'gemini-1.0-pro-001', 'gemini-1.0-pro-vision-latest',
  'gemini-2.5-flash'
];

const defaultConfig = {
  GEMINI_API_KEY: null,
  MODEL: 'gemini-1.5-flash-latest',
  MAX_ITERATIONS: 10,
  DRY_RUN: false,
  CONFIRM_DESTRUCTIVE: false,
  CONFIRM_UNALLOWED_COMMANDS: false,
  LOG_LEVEL: 'info',
  STREAM: true,
  ALLOWED_COMMANDS: [
    'ls', 'pwd', 'cat', 'echo', 'mkdir', 'touch', 'rm', 'cp', 'mv',
    'node', 'python3', 'git', 'npm', 'cd', 'curl', 'wget', 'ps',
    'whoami', 'df', 'du', 'find', 'grep', 'head', 'tail', 'chmod',
    'chown', 'ln', 'stat', 'which', 'tree', 'termux-open',
    'termux-toast', 'termux-vibrate', 'pip', 'apt', 'pkg', 'top', 'htop',
    'history', 'ping', 'netstat', 'ifconfig', 'date', 'cal', 'wc',
    'sort', 'uniq', 'comm', 'diff', 'tar', 'gzip', 'unzip', 'zip',
    'ssh', 'sftp', 'scp', 'rsync', 'tmux', 'screen'
  ],
  MAX_OUTPUT_TOKENS: 8192,
  TEMPERATURE: 0.2,
  TOP_P: 0.95,
  TOP_K: 40,
  STOP_SEQUENCES: ['\n```json', '\n```'],
  COMMAND_TIMEOUT_MS: 60000,
  DESTRUCTIVE_COMMANDS: [
    'rm', 'rmdir', 'mv', 'cp',
    'delete_file', 'delete_directory', 'rename_path', 'copy_path'
  ]
};

function loadConfig() {
  let config = {};
  let configSource = 'defaults';

  try {
    if (fs.existsSync(configPath)) {
      delete require.cache[require.resolve(path.resolve(configPath))];
      config = require(path.resolve(configPath));
      configSource = 'file';
      log('debug', `Channeling config from the ${configPath} ether.`, colors.gray);
    }
  } catch (e) {
    log('warn', `⚠️  Error conjuring config from ${configPath}: ${e.message}`, colors.neonOrange);
    if (e instanceof SyntaxError) {
      log('error', `❌ The configuration scroll ${configPath} is corrupted. Please repair it.`, colors.brightRed);
      process.exit(1);
    }
  }

  const envOverrides = {
    GEMINI_API_KEY: process.env.GEMINI_API_KEY,
    LOG_LEVEL: process.env.LOG_LEVEL,
    DRY_RUN: process.env.DRY_RUN,
    CONFIRM_DESTRUCTIVE: process.env.CONFIRM_DESTRUCTIVE,
    CONFIRM_UNALLOWED_COMMANDS: process.env.CONFIRM_UNALLOWED_COMMANDS,
    STREAM: process.env.STREAM,
    MODEL: process.env.MODEL,
    MAX_ITERATIONS: process.env.MAX_ITERATIONS,
    MAX_OUTPUT_TOKENS: process.env.MAX_OUTPUT_TOKENS,
    TEMPERATURE: process.env.TEMPERATURE,
    TOP_P: process.env.TOP_P,
    TOP_K: process.env.TOP_K,
    COMMAND_TIMEOUT_MS: process.env.COMMAND_TIMEOUT_MS,
  };
  for (let [key, value] of Object.entries(envOverrides)) {
    if (value !== undefined && value !== null && value !== '') {
      if (value === 'true' || value === 'false') {
        config[key] = (value === 'true');
      } else if (typeof defaultConfig[key] === 'number') {
        const numValue = parseFloat(value);
        if (!isNaN(numValue)) {
          config[key] = numValue;
        } else {
          log('warn', `⚠️  Env var ${key} holds an invalid number: "${value}". Ignoring.`, colors.neonOrange);
        }
      } else {
        config[key] = value;
      }
      configSource = configSource.includes('+env') ? configSource : (configSource === 'defaults' ? 'env' : configSource + '+env');
      log('debug', `Overriding incantation with env var ${key}`, colors.gray);
    }
  }

  const argv = minimist(process.argv.slice(2));
  const cliOverrides = {
    'api-key': argv['api-key'] || argv.key,
    model: argv.model,
    'max-iterations': argv['max-iterations'] || argv.iter,
    'dry-run': argv['dry-run'],
    'confirm-destructive': argv['confirm-destructive'],
    'confirm-unallowed': argv['confirm-unallowed'],
    'log-level': argv['log-level'] || argv.log,
    stream: argv.stream,
    'max-tokens': argv['max-tokens'],
    temp: argv.temp,
    'top-p': argv['top-p'],
    'top-k': argv['top-k'],
    'cmd-timeout': argv['cmd-timeout'],
  };
  for (let [key, value] of Object.entries(cliOverrides)) {
    if (value !== undefined && value !== null) {
      const configKey = key.replace(/-([a-z])/g, (g) => g[1].toUpperCase());
      if (['dryRun', 'confirmDestructive', 'confirmUnallowedCommands', 'stream'].includes(configKey)) {
        if (value === true) config[configKey] = true;
        if (value === false) config[configKey] = false;
      } else if (typeof defaultConfig[configKey] === 'number') {
        const numValue = parseFloat(value);
        if (!isNaN(numValue)) {
          config[configKey] = numValue;
        } else {
          log('warn', `⚠️  CLI arg --${key} holds an invalid number: "${value}". Ignoring.`, colors.neonOrange);
        }
      } else {
        config[configKey] = value;
      }
      configSource = configSource.includes('+cli') ? configSource : (configSource === 'defaults' ? 'cli' : (configSource === 'env' ? 'env+cli' : configSource + '+cli'));
      log('debug', `Overriding incantation with CLI arg --${key}`, colors.gray);
    }
  }

  const finalConfig = { ...defaultConfig, ...config };
  finalConfig.configSource = configSource;

  if (!finalConfig.GEMINI_API_KEY) {
    log('error', "❌ GEMINI_API_KEY not found. The mystical energies cannot be channeled without it. Please set it in agent.config.js, as an environment variable, or via --api-key CLI argument.", colors.brightRed);
    process.exit(1);
  }

  if (!OFFICIAL_MODELS.includes(finalConfig.MODEL)) {
    const closest = OFFICIAL_MODELS.find(m => m.includes(finalConfig.MODEL.split('-')[1])) || 'gemini-1.5-flash-latest';
    log('warn', `⚠️  The model "${finalConfig.MODEL}" is not a recognized cosmic entity. Reverting to "${closest}".`, colors.neonOrange);
    finalConfig.MODEL = closest;
  }

  return finalConfig;
}

module.exports = {
    loadConfig,
};
