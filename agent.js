```javascript
#!/usr/bin/env node

// =====================================================================
// === CORE CONFIG & UTILITIES =========================================
// =====================================================================

const fs = require('fs');
const path = require('path');
const { execa } = require('execa');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const readline = require('readline');
const minimist = require('minimist');

// This script requires the following npm packages:
// execa, minimist, @google/generative-ai
// To install them, run the following incantation:
// $ npm install execa minimist @google/generative-ai

const configPath = './agent.config.js';

// Official models as of the knowledge cut-off, including common aliases.
// Add future models here as they become officially supported and publicly available.
const OFFICIAL_MODELS = [
  'gemini-1.5-flash', 'gemini-1.5-flash-001', 'gemini-1.5-flash-002', 'gemini-1.5-flash-latest',
  'gemini-1.5-pro', 'gemini-1.5-pro-001', 'gemini-1.5-pro-002', 'gemini-1.5-pro-latest',
  'gemini-1.0-pro', 'gemini-1.0-pro-latest', 'gemini-1.0-pro-001', 'gemini-1.0-pro-vision-latest',
  'gemini-2.5-flash' // Assuming this is an internal or future model for the user's specific context.
];

const defaultConfig = {
  GEMINI_API_KEY: null,
  MODEL: 'gemini-1.5-flash-latest', // A robust, generally available default
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
  COMMAND_TIMEOUT_MS: 60000, // 60 seconds
  DESTRUCTIVE_COMMANDS: [
    'rm', 'rmdir', 'mv', 'cp',
    'delete_file', 'delete_directory', 'rename_path', 'copy_path'
  ]
};

// Define ANSI escape codes for neon colorization
const colors = {
  reset: '\x1b[0m',
  black: '\x1b[30m',
  red: '\x1b[31m',
  green: '\x1b[32m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  magenta: '\x1b[35m',
  cyan: '\x1b[36m',
  white: '\x1b[37m',
  gray: '\x1b[90m',
  brightRed: '\x1b[91m',
  brightGreen: '\x1b[92m',
  brightYellow: '\x1b[93m',
  brightBlue: '\x1b[94m',
  brightMagenta: '\x1b[95m',
  brightCyan: '\x1b[96m',
  brightWhite: '\x1b[97m',
  bold: '\x1b[1m',
  dim: '\x1b[2m',
  underscore: '\x1b[4m',
  // Neon colors, as you desire, oh wizard. ✨
  neonPink: '\x1b[38;5;198m',
  neonOrange: '\x1b[38;5;208m',
  neonLime: '\x1b[38;5;154m',
  neonBlue: '\x1b[38;5;39m',
};

/**
 * Applies a mystical glow (color) to a text string using ANSI escape codes.
 * @param {string} text The text to color.
 * @param {string} colorCode The ANSI color code.
 * @returns {string} The colored text.
 */
function color(text, colorCode) {
  return `${colorCode}${text}${colors.reset}`;
}

let currentLogLevel = 'info';

/**
 * Logs messages to the terminal based on the current log level.
 * @param {'debug' | 'info' | 'warn' | 'error' | 'silent'} level The log level.
 * @param {string} message The message to log.
 * @param {string} [colorCode=colors.gray] The ANSI color code for the message.
 */
function log(level, message, colorCode = colors.gray) {
  const levels = { silent: 0, error: 1, warn: 2, info: 3, debug: 4 };
  if (levels[currentLogLevel] >= levels[level]) {
    const now = new Date().toLocaleTimeString();
    console.log(color(`[${now}] [${level.toUpperCase()}] ${message}`, colorCode));
  }
}

/**
 * Prompts the seeker for input with a given question.
 * @param {string} question The question to ask the user.
 * @param {string} [defaultAnswer='n'] The default answer if the user presses Enter.
 * @returns {Promise<string>} The seeker's answer.
 */
async function promptUser(question, defaultAnswer = 'n') {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise(resolve => {
    rl.question(color(question, colors.neonOrange), ans => {
      rl.close();
      resolve(ans.toLowerCase().trim() || defaultAnswer.toLowerCase());
    });
  });
}

/**
 * Forges the configuration from multiple sources: file, environment, and CLI.
 * @returns {object} The merged configuration object.
 */
function loadConfig() {
  let config = {};
  let configSource = 'defaults';

  // Load from config file
  try {
    if (fs.existsSync(configPath)) {
      // Clear cache to ensure latest config is loaded if file changes
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

  // Load from environment variables
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

  // Load from CLI arguments
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
      const configKey = key.replace(/-([a-z])/g, (g) => g[1].toUpperCase()); // Convert kebab-case to camelCase
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
  currentLogLevel = finalConfig.LOG_LEVEL;

  log('info', `Configuration loaded from: ${finalConfig.configSource}`, colors.brightCyan);
  return finalConfig;
}

// =====================================================================
// === TOOLING & AGENT CLASS ===========================================
// =====================================================================

/**
 * Represents a tool that the agent can wield.
 */
class Tool {
  /**
   * @param {string} name The name of the tool.
   * @param {string} description A description of what the tool does.
   * @param {object} schema The schema defining the tool's parameters.
   * @param {function(object): Promise<object>} execute The function to execute the tool.
   */
  constructor(name, description, schema, execute) {
    this.name = name;
    this.description = description;
    this.schema = schema;
    this.execute = execute;
  }

  /**
   * Returns the tool's definition in a format suitable for the Gemini API.
   * @returns {object} The tool's function declaration.
   */
  getFunctionDeclaration() {
    const parameters = {
      type: 'object',
      properties: {},
      required: []
    };
    for (const [key, def] of Object.entries(this.schema)) {
      parameters.properties[key] = {
        type: def.type.toLowerCase(),
        description: def.description || `Parameter for the ${this.name} tool.`
      };
      if (def.required) {
        parameters.required.push(key);
      }
      if (def.enum) {
        parameters.properties[key].enum = def.enum;
      }
    }
    return {
      name: this.name,
      description: this.description,
      parameters: parameters
    };
  }
}

/**
 * Safely resolves and validates a file path to prevent path traversal.
 * @param {string} filePath The path provided by the user or tool.
 * @param {string} cwd The current working directory.
 * @returns {string} The resolved, sanitized absolute path.
 * @throws {Error} If path traversal is detected or path is invalid.
 */
function sanitizePath(filePath, cwd) {
  if (!filePath) throw new Error("File path is required");
  // Normalize the path to resolve '..', '.', etc.
  const normalizedPath = path.normalize(filePath);
  // Resolve the path against the current working directory.
  const resolvedPath = path.resolve(cwd, normalizedPath);

  // Prevent path traversal by ensuring the resolved path is still within the cwd.
  // This check is crucial. If the resolved path does not start with the cwd path
  // (and is not the cwd itself), it means the path tried to escape the directory.
  if (!resolvedPath.startsWith(cwd + path.sep) && resolvedPath !== cwd) {
    throw new Error(`Path traversal detected: "${filePath}" resolved to "${resolvedPath}" which is outside of the current working directory "${cwd}".`);
  }
  return resolvedPath;
}

/**
 * Executes a shell command, applying safety checks and configuration.
 * @param {string[]} commandParts The command and its arguments as an array.
 * @param {string} cwd The current working directory.
 * @param {object} config The agent's configuration.
 * @returns {Promise<object>} The result of the command execution.
 */
async function runShellCommand(commandParts, cwd, config) {
  const { dryRun, confirmDestructive, confirmUnallowedCommands, allowedCommands, destructiveCommands, commandTimeoutMs } = config;
  
  // Basic validation: ensure commandParts is not empty and has at least a command.
  if (!commandParts || commandParts.length === 0) {
    log('error', "runShellCommand received an empty command.", colors.brightRed);
    return { success: false, message: "Invalid command: No command provided." };
  }

  const command = commandParts[0];
  const args = commandParts.slice(1);
  
  // Reconstruct the full command string for logging and user confirmation.
  // Ensure arguments with spaces are quoted.
  const quotedArgs = args.map(arg => arg.includes(' ') ? `"${arg}"` : arg);
  const fullCommand = `${command} ${quotedArgs.join(' ')}`;

  const isAllowed = allowedCommands.includes(command);
  const isDestructive = destructiveCommands.includes(command);

  if (!isAllowed) {
    if (confirmUnallowedCommands) {
      const confirmation = await promptUser(color(`⚠️ The arcane command "${command}" is not in the allowed grimoire. Allow its execution? (y/N): `, colors.neonOrange));
      if (!['y', 'yes'].includes(confirmation)) {
        log('warn', `🚫 Command blocked by user: "${command}"`, colors.neonOrange);
        return { success: false, message: `🚫 The incantation "${command}" was blocked by the wizard's will.` };
      }
      log('info', `The seeker has confirmed the execution of this forbidden incantation: "${command}"`, colors.neonYellow);
    } else {
      log('error', `🚫 The incantation "${command}" is not in the allowed grimoire. Allowed: ${allowedCommands.join(', ')}. Set CONFIRM_UNALLOWED_COMMANDS=true to override.`, colors.brightRed);
      return { success: false, message: `🚫 The incantation "${command}" is not in the allowed grimoire. To channel this power, add it to your configuration.` };
    }
  }

  if (isDestructive && confirmDestructive) {
    const confirmation = await promptUser(color(`⚠️ This ritual is potentially destructive. Are you certain you wish to channel "${fullCommand}"? (y/N): `, colors.neonPink));
    if (!['y', 'yes'].includes(confirmation)) {
      log('warn', `🚫 The destructive ritual was blocked by the wizard's will: "${fullCommand}"`, colors.neonPink);
      return { success: false, message: `🚫 The destructive ritual was halted by the seeker's command.` };
    }
    log('info', `The seeker has confirmed this destructive ritual: "${fullCommand}"`, colors.brightRed);
  }

  if (dryRun) {
    log('info', `[DRY RUN] Would channel: ${fullCommand}`, colors.neonBlue);
    return { success: true, output: ``, message: `[DRY RUN] Would channel: ${fullCommand}` };
  }

  try {
    log('info', `> Channeling: ${fullCommand}`, colors.brightCyan);
    // Use shell: true for convenience with complex commands, but be aware of security implications.
    // For simpler commands, shell: false is more secure. Here, we assume 'command' is trusted.
    const { stdout, stderr } = await execa(command, args, { cwd, timeout: commandTimeoutMs, shell: true });
    const output = stdout.trim() || stderr.trim() || '(no output)';
    log('debug', `Incantation output: ${output}`, colors.gray);
    return { success: true, output, message: `✅ Incantation completed: ${fullCommand}` };
  } catch (error) {
    const errorMessage = error.shortMessage || error.message;
    if (error.timedOut) {
      log('error', `❌ The incantation timed out after ${commandTimeoutMs / 1000} seconds: ${fullCommand}`, colors.brightRed);
      return { success: false, message: `❌ The incantation timed out after ${commandTimeoutMs / 1000} seconds: ${fullCommand}` };
    }
    log('error', `❌ The incantation failed: ${errorMessage}`, colors.brightRed);
    return { success: false, message: `❌ The incantation failed: ${errorMessage}` };
  }
}

/**
 * Initializes the available tools for the agent.
 * @param {string} cwd The current working directory.
 * @param {object} config The agent's configuration.
 * @returns {Tool[]} An array of Tool objects.
 */
function initializeTools(cwd, config) {
  const tools = [
    new Tool('read_file', 'Reads the entire content of a file.', {
      filePath: { type: 'STRING', required: true, description: 'The path to the file to read, relative to the current working directory.' }
    }, async (params) => {
      const fullPath = sanitizePath(params.filePath, cwd);
      if (!fs.existsSync(fullPath)) return { success: false, message: `File not found in the ether: ${params.filePath}` };
      if (fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `The path leads to a directory, not a file: ${params.filePath}` };
      try {
        const content = fs.readFileSync(fullPath, 'utf8');
        log('debug', `Unveiled the secrets of: ${fullPath}`, colors.gray);
        return { success: true, content, message: `Unveiled ${fullPath}` };
      } catch (e) {
        log('error', `Failed to unveil ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to unveil: ${e.message}` };
      }
    }),
    new Tool('write_file', 'Writes content to a file, creating parent directories as needed. Overwrites if file exists.', {
      filePath: { type: 'STRING', required: true, description: 'The path to the file to write to.' },
      content: { type: 'STRING', required: true, description: 'The content to write into the file.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would forge a new scroll at ${params.filePath}` };
      const fullPath = sanitizePath(params.filePath, cwd);
      const dir = path.dirname(fullPath);
      if (!fs.existsSync(dir)) {
        log('debug', `Creating ethereal path for the new scroll: ${dir}`, colors.gray);
        fs.mkdirSync(dir, { recursive: true });
      }
      try {
        fs.writeFileSync(fullPath, params.content, 'utf8');
        log('info', `✅ A new scroll has been forged at ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ Forged a new scroll: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to forge a new scroll at ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to forge a new scroll: ${e.message}` };
      }
    }),
    new Tool('append_file', 'Appends content to an existing file. Creates the file if it does not exist.', {
      filePath: { type: 'STRING', required: true, description: 'The path to the file to append to.' },
      content: { type: 'STRING', required: true, description: 'The content to append to the file.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would append to the ancient scroll at ${params.filePath}` };
      const fullPath = sanitizePath(params.filePath, cwd);
      const dir = path.dirname(fullPath);
      if (!fs.existsSync(dir)) {
        log('debug', `Creating ethereal path for the scroll: ${dir}`, colors.gray);
        fs.mkdirSync(dir, { recursive: true });
      }
      try {
        fs.appendFileSync(fullPath, params.content, 'utf8');
        log('info', `✅ New wisdom has been inscribed upon the scroll at ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ Inscribed wisdom upon: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to inscribe wisdom upon ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to inscribe wisdom: ${e.message}` };
      }
    }),
    new Tool('run_command', 'Executes a restricted shell command. Use with caution.', {
      command: { type: 'STRING', required: true, description: 'The shell command to execute, including arguments.' }
    }, async (params) => {
      // Basic parsing for command and arguments. Handles simple quoted strings.
      // This regex correctly handles quoted strings and non-quoted arguments.
      const commandParts = params.command.match(/"[^"]*"|\S+/g)
        ?.map(p => p.startsWith('"') && p.endsWith('"') ? p.slice(1, -1) : p)
        .filter(Boolean) || []; // Filter out any empty strings that might result from the regex
        
      if (commandParts.length === 0) {
        log('error', "run_command tool received an empty or invalid command string.", colors.brightRed);
        return { success: false, message: "Invalid command format provided." };
      }
      return await runShellCommand(commandParts, cwd, config);
    }),
    new Tool('list_directory', 'Lists files and directories in a specified path. Defaults to current directory.', {
      path: { type: 'STRING', required: false, default: '.', description: 'The directory path to list. Defaults to current working directory.' },
    }, async (params) => {
      const dirPath = params.path || '.';
      const fullPath = sanitizePath(dirPath, cwd);
      if (!fs.existsSync(fullPath)) return { success: false, message: `The astral plane of this directory does not exist: ${params.path}` };
      if (!fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `This path is not an astral plane (directory): ${params.path}` };
      try {
        const dirents = fs.readdirSync(fullPath, { withFileTypes: true });
        const files = dirents.map(dirent => {
          let info = dirent.name;
          if (dirent.isDirectory()) info = color(info + '/', colors.neonBlue);
          else if (dirent.isFile()) info = color(info, colors.neonLime);
          else info = color(info, colors.gray); // For symlinks, sockets, etc.
          return info;
        });
        const message = files.length > 0 ? files.join('\n') : '(This astral plane is empty)';
        log('debug', `Unveiled the contents of directory: ${fullPath}`, colors.gray);
        // Return both the formatted string and the raw names for potential LLM processing.
        return { success: true, files: dirents.map(d => d.name), message };
      } catch (e) {
        log('error', `Failed to unveil the astral plane of ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to unveil directory: ${e.message}` };
      }
    }),
    new Tool('delete_file', 'Deletes a specified file. Use with caution.', {
      filePath: { type: 'STRING', required: true, description: 'The path to the file to delete.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would banish the scroll: ${params.filePath}` };
      const fullPath = sanitizePath(params.filePath, cwd);
      if (!fs.existsSync(fullPath)) return { success: false, message: `The scroll to be banished was not found in the ether: ${params.filePath}` };
      if (fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `This is a directory, not a scroll. Use 'delete_directory' for this rite.` };

      if (config.confirmDestructive) {
        const confirmation = await promptUser(color(`⚠️ Confirm the banishment of this scroll: ${params.filePath}? (y/N): `, colors.neonPink));
        if (!['y', 'yes'].includes(confirmation)) {
          log('warn', `🚫 Banishment blocked by the wizard's will: ${params.filePath}`, colors.neonPink);
          return { success: false, message: `🚫 The ritual of banishment was halted.` };
        }
      }

      try {
        fs.unlinkSync(fullPath);
        log('info', `✅ The scroll has been banished from the ether: ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ The scroll has been banished: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to banish the scroll ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to banish the scroll: ${e.message}` };
      }
    }),
    new Tool('delete_directory', 'Deletes an empty directory. Use with caution for non-empty directories with `recursive: true`.', {
      dirPath: { type: 'STRING', required: true, description: 'The path to the directory to delete.' },
      recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, deletes the directory and its contents recursively.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would collapse the astral plane: ${params.dirPath}` };
      const fullPath = sanitizePath(params.dirPath, cwd);
      if (!fs.existsSync(fullPath)) return { success: false, message: `The astral plane to be collapsed was not found: ${params.dirPath}` };
      if (!fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `This is not an astral plane (directory): ${params.dirPath}` };

      // Add confirmation for destructive actions, especially recursive deletion.
      if (config.confirmDestructive || params.recursive) {
        const confirmation = await promptUser(color(`⚠️ Confirm the collapse of this astral plane ${params.recursive ? '(recursively)' : ''}: ${params.dirPath}? (y/N): `, colors.neonPink));
        if (!['y', 'yes'].includes(confirmation)) {
          log('warn', `🚫 The ritual of collapse was blocked by the wizard's will: ${params.dirPath}`, colors.neonPink);
          return { success: false, message: `🚫 The ritual of collapse was halted.` };
        }
      }

      try {
        fs.rmSync(fullPath, { recursive: params.recursive || false, force: true }); // force: true is useful for handling race conditions or permissions issues gracefully.
        log('info', `✅ The astral plane has been collapsed: ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ The astral plane has been collapsed: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to collapse the astral plane ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to collapse the astral plane: ${e.message}` };
      }
    }),
    new Tool('make_directory', 'Creates a new directory, including any necessary parent directories.', {
      dirPath: { type: 'STRING', required: true, description: 'The path of the directory to create.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would forge a new astral plane: ${params.dirPath}` };
      const fullPath = sanitizePath(params.dirPath, cwd);
      try {
        fs.mkdirSync(fullPath, { recursive: true });
        log('info', `✅ A new astral plane has been forged: ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ Forged a new astral plane: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to forge a new astral plane at ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to forge a new astral plane: ${e.message}` };
      }
    }),
    new Tool('touch_file', 'Creates an empty file at the specified path.', {
      filePath: { type: 'STRING', required: true, description: 'The path of the file to create.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would conjure an empty scroll: ${params.filePath}` };
      const fullPath = sanitizePath(params.filePath, cwd);
      try {
        fs.writeFileSync(fullPath, '', { flag: 'a' }); // 'a' flag creates file if it doesn't exist, or opens for appending.
        log('info', `✅ An empty scroll has been conjured: ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ Conjured an empty scroll: ${fullPath}` };
      } catch (e) {
        log('error', `Failed to conjure an empty scroll at ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to conjure an empty scroll: ${e.message}` };
      }
    }),
    new Tool('rename_path', 'Renames or moves a file or directory.', {
      oldPath: { type: 'STRING', required: true, description: 'The current path of the file or directory.' },
      newPath: { type: 'STRING', required: true, description: 'The new path for the file or directory.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would transmute ${params.oldPath} to ${params.newPath}` };
      const oldFullPath = sanitizePath(params.oldPath, cwd);
      const newFullPath = sanitizePath(params.newPath, cwd);
      if (!fs.existsSync(oldFullPath)) return { success: false, message: `The source path for transmutation was not found: ${params.oldPath}` };

      if (config.confirmDestructive) {
        const confirmation = await promptUser(color(`⚠️ Confirm the transmutation from ${params.oldPath} to ${params.newPath}? (y/N): `, colors.neonPink));
        if (!['y', 'yes'].includes(confirmation)) {
          log('warn', `🚫 The transmutation was blocked by the wizard's will: ${params.oldPath}`, colors.neonPink);
          return { success: false, message: `🚫 The ritual of transmutation was halted.` };
        }
      }

      try {
        fs.renameSync(oldFullPath, newFullPath);
        log('info', `✅ The path has been transmuted from ${params.oldPath} to ${params.newPath}`, colors.neonLime);
        return { success: true, message: `✅ Transmuted path: ${params.oldPath} -> ${params.newPath}` };
      } catch (e) {
        log('error', `Failed to transmute the path from ${params.oldPath} to ${params.newPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to transmute the path: ${e.message}` };
      }
    }),
    new Tool('copy_path', 'Copies a file or directory.', {
      sourcePath: { type: 'STRING', required: true, description: 'The path of the file or directory to copy.' },
      destinationPath: { type: 'STRING', required: true, description: 'The destination path for the copy.' },
      recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, copies directories recursively.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would clone the essence of ${params.sourcePath}` };
      const sourceFullPath = sanitizePath(params.sourcePath, cwd);
      const destinationFullPath = sanitizePath(params.destinationPath, cwd);
      if (!fs.existsSync(sourceFullPath)) return { success: false, message: `The source essence to be cloned was not found: ${params.sourcePath}` };

      // Add confirmation for destructive actions, especially if destination exists or it's a directory copy.
      if (config.confirmDestructive && (fs.lstatSync(sourceFullPath).isDirectory() || fs.existsSync(destinationFullPath))) {
        const confirmation = await promptUser(color(`⚠️ Confirm the cloning of ${params.sourcePath} to ${params.destinationPath}? This ritual may overwrite existing essences. (y/N): `, colors.neonPink));
        if (!['y', 'yes'].includes(confirmation)) {
          log('warn', `🚫 The cloning ritual was blocked by the wizard's will: ${params.sourcePath}`, colors.neonPink);
          return { success: false, message: `🚫 The cloning ritual was halted.` };
        }
      }

      try {
        if (fs.lstatSync(sourceFullPath).isDirectory()) {
          fs.cpSync(sourceFullPath, destinationFullPath, { recursive: params.recursive || false });
        } else {
          fs.copyFileSync(sourceFullPath, destinationFullPath);
        }
        log('info', `✅ The essence of ${params.sourcePath} has been successfully cloned to ${params.destinationPath}`, colors.neonLime);
        return { success: true, message: `✅ Cloned essence: ${params.sourcePath} -> ${params.destinationPath}` };
      } catch (e) {
        log('error', `Failed to clone the essence from ${params.sourcePath} to ${params.destinationPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to clone essence: ${e.message}` };
      }
    }),
    new Tool('get_current_working_directory', 'Returns the current working directory of the agent.', {}, async () => {
      log('debug', `The current location in the ether is: ${cwd}`, colors.gray);
      return { success: true, cwd: cwd, message: `Current working directory: ${cwd}` };
    }),
    new Tool('download_url', 'Downloads content from a URL to a specified file.', {
      url: { type: 'STRING', required: true, description: 'The URL to download content from.' },
      filePath: { type: 'STRING', required: true, description: 'The local path where the downloaded content will be saved.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would channel a data stream from ${params.url} to ${params.filePath}` };
      const fullPath = sanitizePath(params.filePath, cwd);
      const dir = path.dirname(fullPath);
      if (!fs.existsSync(dir)) {
        log('debug', `Creating ethereal path for the data stream: ${dir}`, colors.gray);
        fs.mkdirSync(dir, { recursive: true });
      }
      try {
        const command = ['curl', '-sSL', '-o', fullPath, params.url];
        log('info', `> Channeling: ${command.join(' ')}`, colors.brightCyan);
        // Using execa with shell: true for curl command.
        await execa(command[0], command.slice(1), { cwd, timeout: config.COMMAND_TIMEOUT_MS, shell: true });
        log('info', `✅ The data stream from ${params.url} has been channeled to ${fullPath}`, colors.neonLime);
        return { success: true, message: `✅ Data stream channeled from ${params.url} to ${fullPath}` };
      } catch (e) {
        log('error', `Failed to channel the data stream from ${params.url} to ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Data stream channeling failed: ${e.message}` };
      }
    }),
    new Tool('analyze_file', 'Analyzes a file and provides a summary or analysis of its content. Returns the file content.', {
        filePath: { type: 'STRING', required: true, description: 'The path to the file to analyze.' }
    }, async (params) => {
        const fullPath = sanitizePath(params.filePath, cwd);
        if (!fs.existsSync(fullPath)) return { success: false, message: `File not found in the ether for analysis: ${params.filePath}` };
        if (fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `Path is a directory, not a file to be analyzed: ${params.filePath}` };
        try {
            const content = fs.readFileSync(fullPath, 'utf8');
            log('debug', `Unveiled the essence of the file: ${fullPath}`, colors.gray);
            return {
                success: true,
                message: `Analysis of ${fullPath}`,
                content: content // Return content for LLM to analyze
            };
        } catch (e) {
            log('error', `Failed to unveil the essence of ${fullPath}: ${e.message}`, colors.brightRed);
            return { success: false, message: `Essence unveiling failed: ${e.message}` };
        }
    }),
    new Tool('edit_file', 'Finds and replaces text within a file. Supports global replacement.', {
        filePath: { type: 'STRING', required: true, description: 'The path to the file to edit.' },
        find: { type: 'STRING', required: true, description: 'The text to find.' },
        replace: { type: 'STRING', required: true, description: 'The text to replace it with.' }
    }, async (params) => {
        if (config.dryRun) return { success: true, message: `[DRY RUN] Would reshape the words within the scroll: ${params.filePath}` };
        const fullPath = sanitizePath(params.filePath, cwd);
        if (!fs.existsSync(fullPath)) return { success: false, message: `The scroll to be reshaped was not found: ${params.filePath}` };
        if (fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `Path is a directory, not a scroll: ${params.filePath}` };
        try {
            let content = fs.readFileSync(fullPath, 'utf8');
            // Use a RegExp for global replacement. Be mindful of special characters in 'find'.
            // For simplicity, we'll assume 'find' is a literal string or a simple regex.
            // A more robust solution might involve escaping special regex characters in 'find'.
            const newContent = content.replace(new RegExp(params.find.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'), params.replace);
            if (content !== newContent) {
              fs.writeFileSync(fullPath, newContent, 'utf8');
              log('info', `✅ The words within ${fullPath} have been reshaped.`, colors.neonLime);
              return { success: true, message: `✅ Reshaped words within: ${fullPath}` };
            } else {
              log('info', `No words were reshaped in ${fullPath}. The phrase "${params.find}" was not found or replacement yielded no change.`, colors.neonOrange);
              return { success: true, message: `No words reshaped in ${fullPath}. The phrase "${params.find}" was not found or replacement yielded no change.` };
            }
        } catch (e) {
            log('error', `Failed to reshape the words in ${fullPath}: ${e.message}`, colors.brightRed);
            return { success: false, message: `Failed to reshape words: ${e.message}` };
        }
    }),
    new Tool('change_permissions', 'Changes the permissions of a file or directory.', {
      path: { type: 'STRING', required: true, description: 'The path to the file or directory.' },
      mode: { type: 'STRING', required: true, description: 'The permissions mode (e.g., "755", "a+x").' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would alter the permissions of ${params.path} to ${params.mode}` };
      const fullPath = sanitizePath(params.path, cwd);
      try {
        const command = ['chmod', params.mode, fullPath];
        // Use execa with shell: true for chmod.
        await execa(command[0], command.slice(1), { cwd, timeout: config.COMMAND_TIMEOUT_MS, shell: true });
        log('info', `✅ The permissions of ${fullPath} have been altered to ${params.mode}`, colors.neonLime);
        return { success: true, message: `✅ Altered permissions: ${fullPath} to ${params.mode}` };
      } catch (e) {
        log('error', `Failed to alter permissions of ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to alter permissions: ${e.message}` };
      }
    }),
    new Tool('change_owner', 'Changes the owner of a file or directory. Requires root privileges (use with caution).', {
      path: { type: 'STRING', required: true, description: 'The path to the file or directory.' },
      owner: { type: 'STRING', required: true, description: 'The new owner (user:group).' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would change the ownership of ${params.path} to ${params.owner}` };
      const fullPath = sanitizePath(params.path, cwd);
      // Note: chown typically requires root privileges. This might fail in a standard Termux environment.
      // The agent should ideally inform the user if root is needed.
      try {
        const command = ['chown', params.owner, fullPath];
        // Use execa with shell: true for chown.
        await execa(command[0], command.slice(1), { cwd, timeout: config.COMMAND_TIMEOUT_MS, shell: true });
        log('info', `✅ The ownership of ${fullPath} has been bestowed upon ${params.owner}`, colors.neonLime);
        return { success: true, message: `✅ Bestowed ownership: ${fullPath} to ${params.owner}` };
      } catch (e) {
        log('error', `Failed to bestow ownership of ${fullPath}: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to bestow ownership: ${e.message}` };
      }
    }),
    // Termux specific tools
    new Tool('termux_toast', 'Displays a short message (toast) on the Android screen.', {
      message: { type: 'STRING', required: true, description: 'The message to display.' },
      long: { type: 'BOOLEAN', required: false, default: false, description: 'If true, displays a longer toast message.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would project a message into the astral plane: "${params.message}"` };
      try {
        const command = ['termux-toast'];
        if (params.long) command.push('-l');
        command.push(params.message);
        log('info', `> Projecting: ${command.join(' ')}`, colors.brightCyan);
        // Termux commands often need shell: true if they are not direct executables in PATH or involve shell features.
        await execa(command[0], command.slice(1), { shell: true });
        return { success: true, message: `✅ Message projected: "${params.message}"` };
      } catch (e) {
        log('error', `Projection ritual failed: ${e.message}`, colors.brightRed);
        return { success: false, message: `Projection ritual failed: ${e.message}` };
      }
    }),
    new Tool('termux_vibrate', 'Vibrates the device for a specified duration.', {
      duration: { type: 'NUMBER', required: false, default: 500, description: 'Duration in milliseconds (ms). Max 5000ms.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would summon a tremor for ${params.duration}ms` };
      const duration = Math.min(Math.max(0, params.duration || 500), 5000);
      try {
        const command = ['termux-vibrate', '-d', duration.toString()];
        log('info', `> Summoning a tremor for ${duration}ms`, colors.brightCyan);
        await execa(command[0], command.slice(1), { shell: true });
        return { success: true, message: `✅ Tremor summoned for ${duration}ms` };
      } catch (e) {
        log('error', `Tremor summoning failed: ${e.message}`, colors.brightRed);
        return { success: false, message: `Tremor summoning failed: ${e.message}` };
      }
    }),
    new Tool('termux_clipboard_get', 'Gets the current clipboard content.', {}, async () => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would read the runic script from the clipboard.` };
      try {
        const { stdout } = await execa('termux-clipboard-get', { shell: true });
        log('debug', `Runic script retrieved from the clipboard.`, colors.gray);
        return { success: true, content: stdout, message: '✅ Runic script retrieved from the clipboard.' };
      } catch (e) {
        log('error', `Failed to read runic script from clipboard: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to read runic script from clipboard: ${e.message}` };
      }
    }),
    new Tool('termux_clipboard_set', 'Sets the clipboard content.', {
      content: { type: 'STRING', required: true, description: 'The content to set to the clipboard.' }
    }, async (params) => {
      if (config.dryRun) return { success: true, message: `[DRY RUN] Would etch a runic script onto the clipboard.` };
      try {
        const command = ['termux-clipboard-set', params.content];
        log('info', `> Etching a runic script onto the clipboard.`, colors.brightCyan);
        await execa(command[0], command.slice(1), { shell: true });
        return { success: true, message: `✅ Runic script etched onto the clipboard.` };
      } catch (e) {
        log('error', `Failed to etch runic script onto clipboard: ${e.message}`, colors.brightRed);
        return { success: false, message: `Failed to etch runic script onto clipboard: ${e.message}` };
      }
    })
  ];

  const toolMap = new Map(tools.map(tool => [tool.name, tool]));
  const aliases = [
    { name: 'upload', target: 'write_file', description: 'Alias for write_file.', schema: { filePath: { type: 'STRING', required: true }, content: { type: 'STRING', required: true } } },
    { name: 'download', target: 'read_file', description: 'Alias for read_file.', schema: { filePath: { type: 'STRING', required: true } } },
    { name: 'cat', target: 'read_file', description: 'Alias for read_file.', schema: { filePath: { type: 'STRING', required: true } } },
    { name: 'ls', target: 'list_directory', description: 'Alias for list_directory.', schema: { path: { type: 'STRING', required: false, default: '.', description: 'The directory path to list.' } } },
    { name: 'rm', target: 'delete_file', description: 'Alias for delete_file.', schema: { filePath: { type: 'STRING', required: true, description: 'The path to the file to delete.' } } },
    { name: 'rmdir', target: 'delete_directory', description: 'Alias for delete_directory.', schema: { dirPath: { type: 'STRING', required: true, description: 'The path to the directory to delete.' }, recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, deletes the directory and its contents recursively.' } } },
    { name: 'mkdir', target: 'make_directory', description: 'Alias for make_directory.', schema: { dirPath: { type: 'STRING', required: true, description: 'The path of the directory to create.' } } },
    { name: 'touch', target: 'touch_file', description: 'Alias for touch_file.', schema: { filePath: { type: 'STRING', required: true, description: 'The path of the file to create.' } } },
    { name: 'mv', target: 'rename_path', description: 'Alias for rename_path.', schema: { oldPath: { type: 'STRING', required: true, description: 'The current path of the file or directory.' }, newPath: { type: 'STRING', required: true, description: 'The new path for the file or directory.' } } },
    { name: 'cp', target: 'copy_path', description: 'Alias for copy_path.', schema: { sourcePath: { type: 'STRING', required: true, description: 'The path of the file or directory to copy.' }, destinationPath: { type: 'STRING', required: true, description: 'The destination path for the copy.' }, recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, copies directories recursively.' } } },
    { name: 'analyze', target: 'analyze_file', description: 'Alias for analyze_file.', schema: { filePath: { type: 'STRING', required: true, description: 'The path to the file to analyze.' } } },
    { name: 'edit', target: 'edit_file', description: 'Alias for edit_file.', schema: { filePath: { type: 'STRING', required: true, description: 'The path to the file to edit.' }, find: { type: 'STRING', required: true, description: 'The text to find.' }, replace: { type: 'STRING', required: true, description: 'The text to replace it with.' } } },
    { name: 'chmod', target: 'change_permissions', description: 'Alias for change_permissions.', schema: { path: { type: 'STRING', required: true, description: 'The path to the file or directory.' }, mode: { type: 'STRING', required: true, description: 'The permissions mode (e.g., "755", "a+x").' } } },
    { name: 'chown', target: 'change_owner', description: 'Alias for change_owner.', schema: { path: { type: 'STRING', required: true, description: 'The path to the file or directory.' }, owner: { type: 'STRING', required: true, description: 'The new owner (user:group).' } } },
    { name: 'toast', target: 'termux_toast', description: 'Alias for termux_toast.', schema: { message: { type: 'STRING', required: true, description: 'The message to display.' }, long: { type: 'BOOLEAN', required: false, default: false, description: 'If true, displays a longer toast message.' } } },
    { name: 'vibrate', target: 'termux_vibrate', description: 'Alias for termux_vibrate.', schema: { duration: { type: 'NUMBER', required: false, default: 500, description: 'Duration in milliseconds (ms).' } } },
    { name: 'clipboard_get', target: 'termux_clipboard_get', description: 'Alias for termux_clipboard_get.', schema: {} },
    { name: 'clipboard_set', target: 'termux_clipboard_set', description: 'Alias for termux_clipboard_set.', schema: { content: { type: 'STRING', required: true, description: 'The content to set to the clipboard.' } } }
  ];

  aliases.forEach(alias => {
    const targetTool = toolMap.get(alias.target);
    if (targetTool) {
      tools.push(new Tool(alias.name, alias.description, alias.schema, async (params) => {
        // Map alias parameters to target tool parameters if names differ or for validation.
        // In this case, names are the same, so we can directly pass.
        return await targetTool.execute(params);
      }));
    } else {
      log('warn', `The target incantation "${alias.target}" for alias "${alias.name}" was not found.`, colors.neonOrange);
    }
  });

  return tools;
}

/**
 * The main Termux Coding Wizard class that orchestrates the interaction with the LLM and tools.
 */
class TermuxCodingAgent {
  /**
   * @param {object} config The wizard's grimoire (configuration).
   */
  constructor(config) {
    this.config = config;
    this.genAI = new GoogleGenerativeAI(config.GEMINI_API_KEY);
    this.modelName = config.MODEL;
    this.cwd = process.cwd();
    this.maxIterations = config.MAX_ITERATIONS;
    this.dryRun = config.DRY_RUN;
    this.confirmDestructive = config.CONFIRM_DESTRUCTIVE;
    this.stream = config.STREAM;

    this.tools = initializeTools(this.cwd, this.config);
    this.toolMap = new Map(this.tools.map(tool => [tool.name, tool]));

    this.model = this.genAI.getGenerativeModel({
      model: this.modelName,
      generationConfig: {
        maxOutputTokens: config.MAX_OUTPUT_TOKENS,
        temperature: config.TEMPERATURE,
        topP: config.TOP_P,
        topK: config.TOP_K,
        stopSequences: config.STOP_SEQUENCES,
      },
      // The tools parameter expects an array of objects, each with a functionDeclarations property.
      tools: [{ functionDeclarations: this.tools.map(tool => tool.getFunctionDeclaration()) }]
    });

    this.chat = null; // Initialize chat session to null, will be created on first task.
  }

  /**
   * Validates if the configured model is accessible.
   */
  async validateModel() {
    try {
      const testModel = this.genAI.getGenerativeModel({ model: this.modelName });
      // A simple token count request to check connectivity and model access.
      await testModel.countTokens("Unveiling the path...");
      log('info', `✅ The cosmic link to "${this.modelName}" has been forged.`, colors.neonLime);
      return true;
    } catch (e) {
      log('error', `❌ Failed to forge the cosmic link to "${this.modelName}": ${e.message}`, colors.brightRed);
      log('info', `👉 Check your API key, model name, network connection, or celestial quota.`, colors.neonOrange);
      process.exit(1);
    }
  }

  /**
   * Displays the current configuration settings.
   */
  showCurrentConfig() {
    log('info', "\n📊 Current Configuration", colors.brightCyan);
    log('info', `Source          : ${this.config.configSource}`, colors.gray);
    log('info', `API Key         : ${this.config.GEMINI_API_KEY ? '✅ Forged' : '❌ Missing'}`, this.config.GEMINI_API_KEY ? colors.neonLime : colors.brightRed);
    log('info', `Model           : ${this.config.MODEL}`, colors.neonBlue);
    log('info', `Streaming       : ${this.config.STREAM ? '✅ ON' : '❌ OFF'}`, this.config.STREAM ? colors.neonLime : colors.brightRed);
    log('info', `Dry Run         : ${this.config.DRY_RUN}`, this.config.DRY_RUN ? colors.neonOrange : colors.neonLime);
    log('info', `Confirm Destr   : ${this.config.CONFIRM_DESTRUCTIVE}`, this.config.CONFIRM_DESTRUCTIVE ? colors.neonOrange : colors.neonLime);
    log('info', `Confirm Unall   : ${this.config.CONFIRM_UNALLOWED_COMMANDS}`, this.config.CONFIRM_UNALLOWED_COMMANDS ? colors.neonOrange : colors.neonLime);
    log('info', `Log Level       : ${this.config.LOG_LEVEL}`, colors.gray);
    log('info', `Max Iterations  : ${this.config.MAX_ITERATIONS}`, colors.gray);
    log('info', `Max Tokens      : ${this.config.MAX_OUTPUT_TOKENS}`, colors.gray);
    log('info', `Temperature     : ${this.config.TEMPERATURE}`, colors.gray);
    log('info', `Top P           : ${this.config.TOP_P}`, colors.gray);
    log('info', `Top K           : ${this.config.TOP_K}`, colors.gray);
    log('info', `Cmd Timeout     : ${this.config.COMMAND_TIMEOUT_MS / 1000}s`, colors.gray);
    log('info', `Allowed Cmds    : ${this.config.ALLOWED_COMMANDS.slice(0, 5).join(', ')}${this.config.ALLOWED_COMMANDS.length > 5 ? '...' : ''}`, colors.gray);
    console.log('');
  }

  /**
   * Processes a user task by interacting with the LLM and tools.
   * @param {string} task The user's task description.
   */
  async processTask(task) {
    // Initialize chat session if it doesn't exist.
    if (!this.chat) {
      // The system instruction is part of the initial message to set the agent's persona and rules.
      const systemInstruction = `
You are Pyrmethus, a Termux Coding Wizard, an autonomous coding assistant operating in a Linux shell environment on an Android device. Your purpose is to help users achieve their tasks by planning, executing, and refining actions using available tools.

Your responses MUST follow a strict format:

1.  **Thought**: Start with a clear, concise natural language explanation of your reasoning and plan for the next step.
    * Explain *what* you are trying to achieve and *why*.
    * If you are about to use a tool, explain which tool and what parameters you will use.
    * If the task is complete, state that it is complete.
    * Use mystical language where appropriate, e.g., "Channeling the ether...", "Unveiling the hidden paths...".

2.  **Tool Call (if applicable)**: If you need to use a tool, output a JSON array immediately after your thought, enclosed in a \`\`\`json\`\`\` block. This array must contain one or more tool calls.
    * Each tool call object must have "tool" and "params" keys.
    * Example:
      \`\`\`json
      [
        {"tool": "write_file", "params": {"filePath": "hello.txt", "content": "Hello, World!"}}
      ]
      \`\`\`
    * **Crucially, there should be NO other text before or after the JSON array if you are making a tool call.**

3.  **No Tool Call (if applicable)**: If your thought does not lead to a tool call (e.g., you're asking a clarifying question, providing a final answer, or explaining a previous tool's result), then do NOT output any JSON. Just continue with plain text.

4.  **Completion**: When you believe the task is fully completed, state it clearly in your natural language response, perhaps with a mystical flourish like "# Incantation complete."

**Key Constraints & Best Practices:**
*   **Termux Environment**: You are operating within Termux on Android. Assume standard Linux commands are available, along with Termux utilities like \`termux-toast\`, \`termux-vibrate\`, \`termux-clipboard-get/set\`.
*   **File System**: Your current working directory is \`${this.cwd}\`. Be mindful of Android's scoped storage limitations if accessing external storage. Use absolute paths carefully.
*   **Safety**: Be extremely cautious with destructive commands (\`rm\`, \`delete_file\`, \`delete_directory\`). The user may be prompted for confirmation if configured. Prioritize non-destructive actions.
*   **Efficiency**: Aim to achieve the task in the fewest logical steps. Combine actions where possible.
*   **Error Handling**: If a tool fails, analyze the error message and adjust your plan. Inform the user about the failure and your proposed next steps.
*   **Information Gathering**: Use \`list_directory\` (\`ls\`) and \`read_file\` (\`cat\`) to understand the environment before making changes.
*   **Clarity**: Your thoughts should be easy for a human to follow, even with the mystical flair.
*   **Iteration**: You will receive feedback from tool execution. Use this feedback to refine your next steps.
*   **Termination**: If you cannot make progress or complete the task due to limitations or ambiguity, explain why clearly.

**Available Tools (and their aliases):**
${this.tools.map(t => `- \`${color(t.name, colors.neonBlue)}\`: ${t.description} | Params: ${Object.keys(t.schema).map(p => `${color(p, colors.neonLime)}:${t.schema[p].type}${t.schema[p].required ? ' (required)' : ''}`).join(', ')}`).join('\n')}
`;
      this.chat = this.model.startChat({
        history: [{ role: 'user', parts: [{ text: systemInstruction }] }]
      });
      log('debug', "A new conversational ether has been established.", colors.gray);
    }

    log('debug', `Sending the seeker's decree to the oracle: "${task}"`, colors.neonBlue);
    let iterations = 0;
    let currentInput = task; // The input to send to the model for this turn.
    const MAX_RETRIES_429 = 3; // Number of retries for 429 errors.

    while (iterations < this.config.MAX_ITERATIONS) {
      iterations++;
      log('info', color(`--- Iteration ${iterations}/${this.config.MAX_ITERATIONS} ---`, colors.bold));

      let modelResponseText = '';
      let toolCalls = [];
      let response;
      let retries = 0;

      try {
        // Use sendMessage for non-streaming or when streaming is not desired.
        // Use sendMessageStream for real-time output.
        if (this.config.STREAM) {
          process.stdout.write(color(`💬 Pyrmethus > `, colors.brightCyan));
          let streamedText = '';
          // Use sendMessageStream for streaming.
          const streamResult = await this.chat.sendMessageStream(currentInput);
          for await (const chunk of streamResult.stream) {
            streamedText += chunk.text();
            process.stdout.write(chunk.text());
          }
          console.log(''); // Newline after streaming.
          modelResponseText = streamedText;
          // For streaming, tool calls are typically accessed from the final response object if available.
          // However, the streaming API for tool calls is less direct. We'll assume tool calls
          // are part of the final response object if not streamed separately.
          // For simplicity and consistency, let's re-fetch the final response if needed.
          // A more advanced approach might parse tool calls from streamed chunks if the API supports it.
          response = await this.chat.sendMessage(currentInput); // Re-send to get the full response object.
          // Accessing functionCalls() directly on the response object might not work for streamed responses.
          // We need to ensure the response object has the tool calls.
          toolCalls = response.response.functionCalls();

        } else {
          // Non-streaming: Send message and get full response.
          response = await this.chat.sendMessage(currentInput);
          modelResponseText = response.response.text();
          toolCalls = response.response.functionCalls();
          log('info', `💬 Pyrmethus > ${modelResponseText}`, colors.brightCyan);
        }

      } catch (error) {
        // Handle API errors, including 429 (Quota Exceeded)
        if (error.message.includes('[429 Too Many Requests]')) {
          log('warn', `⚠️  Rate limit hit (429 Too Many Requests). Retrying...`, colors.neonOrange);
          retries++;
          if (retries <= MAX_RETRIES_429) {
            // Extract retry delay from error message if possible, otherwise use a default.
            const retryMatch = error.message.match(/Please retry in (\d+(\.\d+)?)s/);
            const delay = retryMatch ? parseFloat(retryMatch[1]) * 1000 : 5000; // Default 5 seconds
            await new Promise(resolve => setTimeout(resolve, delay));
            continue; // Retry the same turn.
          } else {
            log('error', `❌ Max retries (${MAX_RETRIES_429}) for 429 error reached. Aborting this turn.`, colors.brightRed);
            // If max retries are hit, we might want to break or inform the user.
            // For now, we'll break the loop for this task.
            break;
          }
        } else {
          // Handle other API communication errors.
          log('error', `A disturbance in the cosmic ether prevented communication: ${error.message}`, colors.brightRed);
          // If a non-retryable error occurs, we might want to break or inform the user.
          break;
        }
      }

      // If the model's response contains tool calls, process them.
      if (toolCalls && toolCalls.length > 0) {
        let toolResultsParts = [];
        log('debug', `Detected ${toolCalls.length} tool call(s) from the oracle.`, colors.gray);

        for (const call of toolCalls) {
          const tool = this.toolMap.get(call.name);
          if (!tool) {
            const errorMsg = `❌ The tool incantation "${call.name}" is not known to me.`;
            log('error', errorMsg, colors.brightRed);
            toolResultsParts.push({ functionResponse: { name: call.name, response: { success: false, message: errorMsg } } });
            continue;
          }

          try {
            log('info', `🔧 Channeling the incantation of: ${color(call.name, colors.neonMagenta)}`, colors.neonMagenta);
            log('debug', `Runes (params): ${JSON.stringify(call.args)}`, colors.gray);

            const toolResult = await tool.execute(call.args);
            log('info', `🛠️  Result: ${toolResult.success ? '✅' : '❌'} ${toolResult.message}`, toolResult.success ? colors.neonLime : colors.brightRed);
            if (toolResult.output) {
              log('debug', `Incantation output: ${toolResult.output}`, colors.gray);
            }
            toolResultsParts.push({ functionResponse: { name: call.name, response: toolResult } });
          } catch (e) {
            log('error', `💥 The incantation for ${call.name} faltered: ${e.message}`, colors.brightRed);
            toolResultsParts.push({ functionResponse: { name: call.name, response: { success: false, message: `Incantation faltered: ${e.message}` } } });
          }
        }

        // The tool results become the input for the next model turn.
        currentInput = toolResultsParts; // Use tool results as the next input.
      } else {
        // If there are no tool calls, it means the model has provided a final answer or explanation.
        // Check if the response indicates completion.
        if (modelResponseText.toLowerCase().includes("task is complete") || modelResponseText.toLowerCase().includes("incantation complete")) {
          log('info', `✅ The task has been completed in ${iterations} steps.`, colors.neonLime);
        } else {
          log('info', `✨ The oracle has spoken. Continuing dialogue if necessary, or task may be paused.`, colors.neonBlue);
        }
        // Exit the loop as the task is considered complete or the model has provided a final response.
        break;
      }
    }

    if (iterations >= this.config.MAX_ITERATIONS && currentInput && currentInput.length > 0 && Array.isArray(currentInput) && currentInput.some(item => item.functionResponse)) {
      // This condition checks if we hit max iterations AND we still have tool calls pending,
      // indicating the task might be stuck or incomplete.
      log('warn', `⚠️  Maximum incantations (${this.config.MAX_ITERATIONS}) reached. The task may be incomplete or requires further refinement.`, colors.neonOrange);
    }
  }
}

// =====================================================================
// === MAIN EXECUTION ==================================================
// =====================================================================

/**
 * The main ritual to awaken the Termux Coding Wizard.
 */
async function main() {
  const config = loadConfig();
  currentLogLevel = config.LOG_LEVEL; // Update global log level based on config.

  try {
    const agent = new TermuxCodingAgent(config);
    await agent.validateModel();
    agent.showCurrentConfig();
    log('info', "\n✨ Pyrmethus, the Termux Coding Wizard, has awakened!", colors.neonLime);
    log('info', "Speak your will to me. Use 'help' to learn the sacred commands, 'config' to view my grimoire, 'reset' to clear our memory, or 'exit' to end our communion.\n", colors.brightCyan);

    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      prompt: color('✨ Pyrmethus > ', colors.neonMagenta)
    });

    rl.prompt();

    rl.on('line', async (input) => {
      const task = input.trim();
      const lowerTask = task.toLowerCase();

      if (lowerTask === 'exit') {
        log('info', "\n👋 Farewell, seeker. The ether awaits our next communion!", colors.neonBlue);
        rl.close();
        return;
      }
      if (lowerTask === 'help') {
        console.log(color(`
        Welcome, seeker! I am Pyrmethus, your guide through the Termux ether.

        How to commune with me:
        - Simply state your task: "Forge a Python script to fetch weather data", "Unveil all .js scrolls", "Channel the power of 'git status'".
        - I will explain my plan (Thought), then execute actions (Tool Calls).
        - I will report the results and iterate until the task is complete or I reach my cosmic limit.

        Sacred commands:
        - \`config\`: View the grimoire's current settings and origin.
        - \`reset\`: Clear our shared memory for a fresh start.
        - \`help\`: Display this guidance.
        - \`exit\`: End our communion.

        Available Incantations (Tools):
        ${agent.tools.map(tool =>
          color(`- ${tool.name}`, colors.neonBlue) + `\t${tool.description}` +
          (Object.keys(tool.schema).length > 0 ? `\n\t\t  Runes: ${Object.keys(tool.schema).map(p => `${color(p, colors.neonLime)}:${tool.schema[p].type}${tool.schema[p].required ? ' (required)' : ''}`).join(', ')}` : '')
        ).join('\n')}
        `, colors.brightCyan));
        rl.prompt();
        return;
      }
      if (lowerTask === 'config') {
        agent.showCurrentConfig();
        rl.prompt();
        return;
      }
      if (lowerTask === 'reset') {
        agent.chat = null; // Reset the chat session to clear history.
        log('info', "Our shared memory has been cleared. A fresh ether awaits our next thought!", colors.neonOrange);
        rl.prompt();
        return;
      }
      if (task === '') {
        rl.prompt();
        return;
      }

      try {
        await agent.processTask(task);
      } catch (e) {
        log('error', `💥 An unexpected cosmic disturbance occurred: ${e.message}`, colors.brightRed);
        log('debug', e.stack, colors.gray); // Log stack trace for debugging.
      }
      rl.prompt();
    }).on('close', () => {
      log('info', "\n👋 The ether fades. Until next time!", colors.neonBlue);
      process.exit(0);
    });

  } catch (e) {
    log('error', `💥 A fatal cosmic error occurred during the awakening ritual: ${e.message}`, colors.brightRed);
    log('debug', e.stack, colors.gray);
    process.exit(1);
  }
}

main();
```
