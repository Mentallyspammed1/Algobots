const { execa } = require('execa');
const { log, colors, color } = require('../utils/logger');
const { promptUser } = require('../utils/prompt');

async function runShellCommand(commandParts, cwd, config) {
  const { dryRun, confirmDestructive, confirmUnallowedCommands, allowedCommands, destructiveCommands, commandTimeoutMs } = config;

  if (!commandParts || commandParts.length === 0) {
    log('error', "runShellCommand received an empty command.", colors.brightRed);
    return { success: false, message: "Invalid command: No command provided." };
  }

  const command = commandParts[0];
  const args = commandParts.slice(1);

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

module.exports = [
    {
        name: 'run_command',
        description: 'Executes a restricted shell command. Use with caution.',
        schema: {
            command: { type: 'STRING', required: true, description: 'The shell command to execute, including arguments.' }
        },
        execute: async (params, context) => {
            const commandParts = params.command.match(/"[^"]*"|\S+/g)
                ?.map(p => p.startsWith('"') && p.endsWith('"') ? p.slice(1, -1) : p)
                .filter(Boolean) || [];

            if (commandParts.length === 0) {
                log('error', "run_command tool received an empty or invalid command string.", colors.brightRed);
                return { success: false, message: "Invalid command format provided." };
            }
            return await runShellCommand(commandParts, context.cwd, context);
        }
    }
];
