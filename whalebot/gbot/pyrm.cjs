#!/usr/bin/env node

// --- PYRMETHUS - THE ULTIMATE TERMUX WIZARD (Consolidated & Optimized v5.2) ---
// Critical Fix: Robust tool call parsing. Added comprehensive toolset.

const fs = require('fs');
const path = require('path');
const { execa } = require('execa');
const { GoogleGenerativeAI } = require('@google/generative-ai');
const readline = require('readline');
const minimist = require('minimist');
const os = require('os');
const crypto = require('crypto');
const { createHash } = crypto;

// =============================================================================
// 1. CORE UTILITIES (Colors, Logging, Spinner, Cache)
// =============================================================================
const colors = {
  reset: '\x1b[0m',
  gray: '\x1b[90m',
  brightRed: '\x1b[91m',
  brightCyan: '\x1b[96m',
  bold: '\x1b[1m',
  neonPink: '\x1b[38;5;198m',
  neonOrange: '\x1b[38;5;208m',
  neonLime: '\x1b[38;5;154m',
  neonBlue: '\x1b[38;5;39m',
  neonMagenta: '\x1b[95m',
  neonYellow: '\x1b[93m',
  neonGreen: '\x1b[38;5;46m',
  neonPurple: '\x1b[38;5;129m',
};

let currentLogLevel = 'info';
let spinnerInterval = null;
const spinnerFrames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏'];
const toolCache = new Map();
const CACHE_TTL_MS = 5 * 60 * 1000;
const sessionVersion = '5.2_ToolFix';

function color(text, colorCode) {
  return `${colorCode}${text}${colors.reset}`;
}

function stopSpinner() {
  if (spinnerInterval) {
    clearInterval(spinnerInterval);
    spinnerInterval = null;
    process.stdout.write(`\r${' '.repeat(process.stdout.columns || 80)}\r`);
  }
}

function log(level, message, colorCode = colors.gray) {
  const levels = { silent: 0, error: 1, warn: 2, info: 3, debug: 4, trace: 5 };
  if (levels[currentLogLevel] >= levels[level]) {
    stopSpinner();
    const now = new Date().toISOString().slice(11, 19);
    console.log(color(`[${now}] [${level.toUpperCase()}] ${message}`, colorCode));
  }
}

function startSpinner(text = 'Working...') {
  if (spinnerInterval || currentLogLevel === 'silent') return;
  let i = 0;
  spinnerInterval = setInterval(() => {
    process.stdout.write(`\r${color(spinnerFrames[i++ % spinnerFrames.length], colors.neonYellow)} ${text}`);
  }, 80);
}

// =============================================================================
// 2. CONFIGURATION & CORE SETUP
// =============================================================================
const getConfigPath = () => {
  const configDir = process.env.XDG_CONFIG_HOME || path.join(os.homedir(), '.config');
  const userConfigPath = path.join(configDir, 'pyrmethus.config.js');
  return fs.existsSync(userConfigPath) ? userConfigPath : './pyrmethus.config.js';
};
const configPath = getConfigPath();

const MODEL_CHAIN = ['gemini-2.0-flash-lite-preview-02-05', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro'];

const defaultConfig = {
  GEMINI_API_KEY: process.env.GEMINI_API_KEY || "YOUR_ACTUAL_GEMINI_API_KEY_HERE",
  MODEL: MODEL_CHAIN[0],
  MAX_ITERATIONS: 12,
  DRY_RUN: false,
  CONFIRM_DESTRUCTIVE: true,
  CONFIRM_UNALLOWED_COMMANDS: false,
  LOG_LEVEL: 'info',
  STREAM: true,
  MAX_OUTPUT_TOKENS: 16384,
  TEMPERATURE: 0.2,
  COMMAND_TIMEOUT_MS: 60000,
  DESTRUCTIVE_COMMANDS: ['rm', 'rmdir', 'mv', 'cp', 'pkill', 'kill', 'chown', 'chmod', 'truncate', 'dd', 'reboot', 'shutdown', 'delete_file', 'delete_directory', 'rename_path', 'copy_path', 'upgrade_packages'],
  ALLOWED_COMMANDS: [
    'cat', 'echo', 'mkdir', 'touch', 'rm', 'cp', 'mv', 'node', 'python3', 'git', 'npm', 'pip', 'apt', 'pkg', 'cd', 'curl', 'wget', 'ps', 'whoami', 'df', 'du', 'find', 'grep', 'head', 'tail', 'chmod', 'chown', 'ln', 'stat', 'which', 'tree', 'termux-open', 'termux-toast', 'termux-vibrate', 'top', 'htop', 'history', 'ping', 'netstat', 'ifconfig', 'date', 'cal', 'wc', 'sort', 'uniq', 'comm', 'diff', 'tar', 'gzip', 'unzip', 'zip', 'ssh', 'sftp', 'scp', 'rsync', 'tmux', 'screen', 'sed', 'awk', 'xargs', 'bash', 'true', 'false', 'test', 'termux-battery-status', 'termux-camera-info', 'termux-clipboard-get', 'termux-clipboard-set', 'termux-location', 'termux-setup-storage', 'pkg_install', 'apt-get', 'pip', 'python3'
  ],
  MAX_FILE_READ_BYTES: 1024 * 1024 * 5,
  MAX_CHAT_HISTORY_LENGTH: 10,
  MAX_TOOL_OUTPUT_LENGTH: 8000,
  SESSION_FILE_PATH: './.pyrmethus_session.json',
  TERMUX_HOME: os.homedir() || '/data/data/com.termux/files/home',
  AUTO_SAVE_ON_CRASH: true,
  PATH_ALIASES: { '~': os.homedir(), '$HOME': os.homedir() },
};

let interactiveCommandHistory = [];
let lastConfigMtime = 0;

async function promptUser(question, defaultAnswer = 'n') {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true });
  return new Promise(resolve => {
    rl.question(color(question, colors.neonOrange), ans => {
      rl.close();
      resolve(ans.toLowerCase().trim() || defaultAnswer.toLowerCase());
    });
  });
}

function sanitizePath(filePath, cwd, termuxHome, aliases = {}) {
  if (!filePath) throw new Error("File path is required");
  for (const [alias, target] of Object.entries(aliases)) {
    if (filePath.startsWith(alias + '/') || filePath === alias) {
      filePath = filePath.replace(alias, target);
    }
  }
  const resolvedPath = path.resolve(cwd, path.normalize(filePath));

  if (!resolvedPath.startsWith(termuxHome)) {
    log('warn', `Path Traversal Blocked: "${resolvedPath}" outside TERMUX_HOME.`, colors.neonOrange);
    throw new Error(`Path traversal detected: Access to "${filePath}" is not allowed.`);
  }
  return resolvedPath;
}

function loadConfig() {
  const argv = minimist(process.argv.slice(2));
  let config = { ...defaultConfig };
  
  try {
    if (fs.existsSync(configPath)) {
      const stats = fs.statSync(configPath);
      if (stats.mtimeMs > lastConfigMtime) {
        log('info', `Config reloaded from ${configPath}`, colors.neonPurple);
        lastConfigMtime = stats.mtimeMs;
        delete require.cache[require.resolve(path.resolve(configPath))];
      }
      const userConfig = require(path.resolve(configPath));
      config = { ...config, ...(userConfig.config || userConfig) };
    }
  } catch (e) { log('warn', `Error loading config: ${e.message}`, colors.neonOrange); }

  if (process.env.GEMINI_API_KEY) config.GEMINI_API_KEY = process.env.GEMINI_API_KEY;

  if (argv.key) config.GEMINI_API_KEY = argv.key;
  if (argv.model) config.MODEL = argv.model;
  if (argv['dry-run']) config.DRY_RUN = true;
  if (argv.logLevel) config.LOG_LEVEL = argv.logLevel;
  
  if (!config.GEMINI_API_KEY || config.GEMINI_API_KEY.includes("YOUR_ACTUAL_GEMINI_API_KEY_HERE")) {
    log('error', "GEMINI_API_KEY not set.", colors.brightRed);
    process.exit(1);
  }
  currentLogLevel = config.LOG_LEVEL;
  return config;
}

async function runShellCommand(commandParts, cwd, config) {
  const [cmd] = commandParts;
  const isDestructive = config.DESTRUCTIVE_COMMANDS.includes(cmd);
  
  if (isDestructive && config.CONFIRM_DESTRUCTIVE) {
    const confirmation = await promptUser(color(`⚠️ Destructive: "${commandParts.join(' ')}"? (y/N): `, colors.neonPink));
    if (!['y', 'yes'].includes(confirmation)) return { success: false, message: `Halted.` };
  }

  if (config.DRY_RUN) return { success: true, message: `[DRY RUN] ${commandParts.join(' ')}` };

  try {
    const { stdout, stderr, exitCode } = await execa(commandParts[0], commandParts.slice(1), {
      cwd, timeout: config.COMMAND_TIMEOUT_MS, shell: true, reject: false
    });
    const output = stdout + (stderr ? `\n[STDERR]: ${stderr}` : '');
    return { success: exitCode === 0, output: output.trim() || "(No output)", message: `Exit: ${exitCode}` };
  } catch (e) {
    return { success: false, message: e.message };
  }
}

// =============================================================================
// 3. TOOL DEFINITIONS
// =============================================================================
class Tool {
  constructor(name, desc, schema, exec, meta = {}) {
    this.name = name; this.desc = desc; this.schema = schema; this.exec = exec; this.meta = meta;
  }
  getFunctionDeclaration() {
    return {
      name: this.name,
      description: this.desc,
      parameters: { type: 'object', properties: this.schema, required: Object.keys(this.schema).filter(k => this.schema[k].required) }
    };
  }
}

const ToolDefinitions = [
  // --- 1. CORE SHELL/FILE OPS ---
  {
    name: 'run_shell',
    desc: 'Executes a shell command (e.g., ls, git, curl). This is the primary command execution tool.',
    schema: { command: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => executeShell(p.command, cwd, cfg)
  },
  {
    name: 'list_directory',
    desc: 'Lists files/dirs in a path (like `ls`).',
    schema: { path: { type: 'STRING', required: false, default: '.' } },
    exec: async (p, cwd, cfg) => {
      try {
        const target = sanitizePath(p.path || '.', cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        const items = fs.readdirSync(target, { withFileTypes: true })
          .map(d => `${d.isDirectory() ? '📂' : '📄'} ${d.name}`).join('\n');
        return { success: true, output: items || '(empty)' };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'read_file',
    desc: 'Reads the full content of a local file.',
    schema: { path: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => {
      try {
        const target = sanitizePath(p.path, cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        return { success: true, output: fs.readFileSync(target, 'utf8') };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'write_file',
    desc: 'Saves content to a file, overwriting it. Use this to **SAVE** files.',
    schema: { path: { type: 'STRING', required: true }, content: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => {
      try {
        const target = sanitizePath(p.path, cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        if (!cfg.DRY_RUN) {
            fs.mkdirSync(path.dirname(target), { recursive: true });
            fs.writeFileSync(target, p.content);
        }
        return { success: true, message: `Saved to ${p.path}` };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'edit_file_advanced',
    desc: 'Surgically edits a file: overwrite, append, or find/replace text.',
    schema: { 
      path: { type: 'STRING', required: true },
      mode: { type: 'STRING', required: true, enum: ['overwrite', 'append', 'replace'] },
      content: { type: 'STRING', description: 'New content for overwrite mode.' },
      target_text: { type: 'STRING', description: 'Text to find (for replace mode).' },
      replacement_text: { type: 'STRING', description: 'Text to insert (for replace mode).' }
    },
    exec: async (p, cwd, cfg) => {
      try {
        const target = sanitizePath(p.path, cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        if (cfg.DRY_RUN) return { success: true, message: `[DRY RUN] ${p.mode} on ${p.path}` };

        let currentContent = fs.existsSync(target) ? fs.readFileSync(target, 'utf8') : '';

        if (p.mode === 'overwrite') {
          fs.writeFileSync(target, p.content);
          return { success: true, message: `Overwrote ${p.path}` };
        } else if (p.mode === 'append') {
          fs.appendFileSync(target, '\n' + p.content);
          return { success: true, message: `Appended to ${p.path}` };
        } else if (p.mode === 'replace') {
          if (!p.target_text || !p.replacement_text) return { success: false, message: "Missing target/replacement text." };
          if (!currentContent.includes(p.target_text)) return { success: false, message: "Target text not found." };
          
          const newContent = currentContent.replace(p.target_text, p.replacement_text);
          fs.writeFileSync(target, newContent);
          return { success: true, message: `Replaced text in ${p.path}` };
        }
        return { success: false, message: "Invalid mode." };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },

  // --- 2. WEB & DOWNLOAD ---
  {
    name: 'read_url',
    desc: 'Fetches and returns text content from a URL.',
    schema: { url: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => {
      try {
        const { stdout } = await execa('curl', ['-s', '-L', '--max-time', '10', p.url]);
        const text = stdout.replace(/<script\b[^>]*>([\s\S]*?)<\/script>/gim, "").replace(/<style\b[^>]*>([\s\S]*?)<\/style>/gim, "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim().substring(0, 20000);
        return { success: true, output: text };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'download_file',
    desc: 'Downloads a file from a URL to local disk (File Upload into Termux).',
    schema: { url: { type: 'STRING', required: true }, outputPath: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => {
      try {
        const target = sanitizePath(p.outputPath, cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        if (!cfg.DRY_RUN) await execa('curl', ['-L', '-o', target, p.url]);
        return { success: true, message: `Downloaded to ${p.outputPath}` };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },

  // --- 3. SYSTEM & PROCESS ---
  {
    name: 'change_directory',
    desc: 'Changes internal working directory.',
    schema: { path: { type: 'STRING', required: true } },
    exec: async (p, cwd, cfg) => {
      try {
        const newCwd = sanitizePath(p.path, cwd, cfg.TERMUX_HOME, cfg.PATH_ALIASES);
        if (!fs.existsSync(newCwd)) return {success:false, message: "Path not found"};
        return { success: true, newCwd, message: `CWD: ${newCwd}` };
      } catch(e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'get_system_stats',
    desc: 'Checks RAM, Disk usage, and Battery status.',
    schema: {},
    exec: async (p, cwd, cfg) => {
      try {
        const mem = (await execa('free', ['-h'])).stdout;
        const disk = (await execa('df', ['-h', '/data'])).stdout;
        let bat = "Unknown";
        try { bat = (await execa('termux-battery-status')).stdout; } catch(e){}
        return { success: true, output: `RAM:\n${mem}\n\nDISK:\n${disk}\n\nBATTERY:\n${bat}` };
      } catch (e) { return { success: false, message: e.message }; }
    }
  },
  {
    name: 'finish_task',
    desc: 'Signals that the user\'s request is fully completed.',
    schema: { summary: { type: 'STRING', required: true } },
    exec: async (p) => ({ success: true, message: p.summary })
  }
];

function initializeTools(cwd, config) {
  return ToolDefinitions.map(def => new Tool(def.name, def.desc, def.schema, def.exec, def.metadata));
}

// =============================================================================
// 4. AGENT LOGIC
// =============================================================================
class Agent {
  constructor(config) {
    this.config = config;
    this.genAI = new GoogleGenerativeAI(config.GEMINI_API_KEY);
    this.tools = initializeTools(this.cwd, this.config);
    this.toolMap = new Map(this.tools.map(tool => [tool.name, tool]));
    this.cwd = process.cwd();
    this.chat = null;
    this.model = null;
  }

  async connect() {
    log('info', `Connecting to model chain...`, colors.neonBlue);
    
    for (const modelName of MODEL_CHAIN) {
      try {
        startSpinner(`Testing ${modelName}...`);
        const m = this.genAI.getGenerativeModel({ model: modelName });
        await m.generateContent({ contents: [{ role: 'user', parts: [{ text: 'Hi' }] }] });
        this.model = m;
        this.config.MODEL = modelName;
        stopSpinner();
        log('info', `✅ Linked with ${modelName}`, colors.neonLime);
        return;
      } catch (e) { stopSpinner(); }
    }
    throw new Error("All models failed connection. Check API Key/Model Name.");
  }

  async startChat() {
    const tools = this.tools.map(t => t.getFunctionDeclaration());
    this.chat = this.model.startChat({
      tools: [{ functionDeclarations: tools }],
      history: [{ 
        role: 'user', 
        parts: [{ text: `You are Pyrmethus, a master Termux Agent. CWD: ${this.cwd}.
**INSTRUCTIONS**: Always use tools for actions. If asked to list files, use \`list_directory\`. If asked to save, use \`write_file\`. If asked to run a command, use \`run_shell\`.
` }] 
      }, { role: 'model', parts: [{ text: "Understood. Ready." }] }
    ]
    });
  }
  
  async process(task) {
    if (!this.chat) await this.startChat();
    
    let complete = false;
    let parts = [{ text: task }];
    let iterations = 0;

    while (!complete && iterations++ < this.config.MAX_ITERATIONS) {
      startSpinner('Thinking...');
      
      try {
        const result = await this.chat.sendMessage(parts);
        const response = result.response;
        stopSpinner();

        const text = response.text();
        if (text) console.log(`\n${color('🤖 Pyrmethus:', colors.neonMagenta)} ${text}`);

        // **CRITICAL FIX**: Robustly extract tool calls from response parts
        const candidates = response.candidates || [];
        const contentParts = candidates[0]?.content?.parts || [];
        const calls = contentParts.filter(p => p.functionCall).map(p => p.functionCall);
        
        if (calls.length > 0) {
            console.log(color(`\n⚡ Executing ${calls.length} actions...`, colors.neonBlue));
            const toolResults = [];
            
            for (const call of calls) {
                const tool = this.tools.find(t => t.name === call.name);
                if (!tool) {
                    toolResults.push({ functionResponse: { name: call.name, response: { error: "Unknown tool" } } });
                    continue;
                }
                
                process.stdout.write(color(`  > ${call.name} `, colors.gray));
                const res = await tool.exec(call.args, this.cwd, this.config);
                
                if (call.name === 'change_directory' && res.success) this.cwd = res.newCwd;
                if (call.name === 'finish_task') complete = true;
                
                console.log(res.success ? color('✔', colors.neonLime) : color('✘', colors.brightRed));
                toolResults.push({ functionResponse: { name: call.name, response: res } });
            }
            parts = toolResults; // Feed results back
        } else {
            complete = true;
        }
      } catch (e) {
        stopSpinner();
        log('error', `Turn failed: ${e.message}`, colors.brightRed);
        break;
      }
    }
  }
}

// =============================================================================
// 5. MAIN
// =============================================================================
async function main() {
  console.log(color(`
   PYRMETHUS v5.2
   Tool Execution Fix
  `, colors.neonMagenta));

  const config = loadConfig();
  const argv = minimist(process.argv.slice(2));
  const task = argv._.join(' ');

  if (!config.GEMINI_API_KEY || config.GEMINI_API_KEY.length < 10) {
    log('error', "API Key missing. Set GEMINI_API_KEY env var or use -k.", colors.brightRed);
    process.exit(1);
  }

  try {
    const agent = new Agent(config);
    await agent.connect();

    if (task) {
        await agent.process(task);
    } else {
        const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
        const loop = () => {
            rl.question(color('\nUser > ', colors.neonGreen), async (input) => {
                if (['exit', 'quit'].includes(input.trim().toLowerCase())) process.exit(0);
                if (input.trim()) await agent.process(input);
                loop();
            });
        };
        log('info', "Interactive Mode. Type 'exit' to quit.", colors.gray);
        loop();
    }
  } catch (e) {
    log('error', e.message, colors.brightRed);
  }
}

main();
