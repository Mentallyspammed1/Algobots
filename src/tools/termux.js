const { execa } = require('execa');
const { log, colors } = require('../utils/logger');

module.exports = [
    {
        name: 'termux_toast',
        description: 'Displays a short message (toast) on the Android screen.',
        schema: {
            message: { type: 'STRING', required: true, description: 'The message to display.' },
            long: { type: 'BOOLEAN', required: false, default: false, description: 'If true, displays a longer toast message.' }
        },
        execute: async (params, { dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would project a message into the astral plane: "${params.message}"` };
            try {
                const command = ['termux-toast'];
                if (params.long) command.push('-l');
                command.push(params.message);
                log('info', `> Projecting: ${command.join(' ')}`, colors.brightCyan);
                await execa(command[0], command.slice(1), { shell: true });
                return { success: true, message: `✅ Message projected: "${params.message}"` };
            } catch (e) {
                log('error', `Projection ritual failed: ${e.message}`, colors.brightRed);
                return { success: false, message: `Projection ritual failed: ${e.message}` };
            }
        }
    },
    {
        name: 'termux_vibrate',
        description: 'Vibrates the device for a specified duration.',
        schema: {
            duration: { type: 'NUMBER', required: false, default: 500, description: 'Duration in milliseconds (ms). Max 5000ms.' }
        },
        execute: async (params, { dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would summon a tremor for ${params.duration}ms` };
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
        }
    },
    {
        name: 'termux_clipboard_get',
        description: 'Gets the current clipboard content.',
        schema: {},
        execute: async (params, { dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would read the runic script from the clipboard.` };
            try {
                const { stdout } = await execa('termux-clipboard-get', { shell: true });
                log('debug', `Runic script retrieved from the clipboard.`, colors.gray);
                return { success: true, content: stdout, message: '✅ Runic script retrieved from the clipboard.' };
            } catch (e) {
                log('error', `Failed to read runic script from clipboard: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to read runic script from clipboard: ${e.message}` };
            }
        }
    },
    {
        name: 'termux_clipboard_set',
        description: 'Sets the clipboard content.',
        schema: {
            content: { type: 'STRING', required: true, description: 'The content to set to the clipboard.' }
        },
        execute: async (params, { dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would etch a runic script onto the clipboard.` };
            try {
                const command = ['termux-clipboard-set', params.content];
                log('info', `> Etching a runic script onto the clipboard.`, colors.brightCyan);
                await execa(command[0], command.slice(1), { shell: true });
                return { success: true, message: `✅ Runic script etched onto the clipboard.` };
            } catch (e) {
                log('error', `Failed to etch runic script onto clipboard: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to etch runic script onto clipboard: ${e.message}` };
            }
        }
    }
];
