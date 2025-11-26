#!/usr/bin/env node

const readline = require('readline');
const { loadConfig } = require('./config');
const { TermuxCodingAgent } = require('./agent');
const { log, setLogLevel, colors, color } = require('./utils/logger');

async function main() {
  const config = loadConfig();
  setLogLevel(config.LOG_LEVEL);

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
        agent.chat = null;
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
        log('debug', e.stack, colors.gray);
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
