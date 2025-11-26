const fs = require('fs');
const path = require('path');
const { sanitizePath } = require('../utils/sanitizer');
const { log, colors, color } = require('../utils/logger');
const { promptUser } = require('../utils/prompt');

module.exports = [
    {
        name: 'read_file',
        description: 'Reads the entire content of a file.',
        schema: {
            filePath: { type: 'STRING', required: true, description: 'The path to the file to read, relative to the current working directory.' }
        },
        execute: async (params, { cwd }) => {
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
        }
    },
    {
        name: 'write_file',
        description: 'Writes content to a file, creating parent directories as needed. Overwrites if file exists.',
        schema: {
            filePath: { type: 'STRING', required: true, description: 'The path to the file to write to.' },
            content: { type: 'STRING', required: true, description: 'The content to write into the file.' }
        },
        execute: async (params, { cwd, dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would forge a new scroll at ${params.filePath}` };
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
        }
    },
    {
        name: 'append_file',
        description: 'Appends content to an existing file. Creates the file if it does not exist.',
        schema: {
            filePath: { type: 'STRING', required: true, description: 'The path to the file to append to.' },
            content: { type: 'STRING', required: true, description: 'The content to append to the file.' }
        },
        execute: async (params, { cwd, dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would append to the ancient scroll at ${params.filePath}` };
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
        }
    },
    {
        name: 'list_directory',
        description: 'Lists files and directories in a specified path. Defaults to current directory.',
        schema: {
            path: { type: 'STRING', required: false, default: '.', description: 'The directory path to list. Defaults to current working directory.' },
        },
        execute: async (params, { cwd }) => {
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
                    else info = color(info, colors.gray);
                    return info;
                });
                const message = files.length > 0 ? files.join('\n') : '(This astral plane is empty)';
                log('debug', `Unveiled the contents of directory: ${fullPath}`, colors.gray);
                return { success: true, files: dirents.map(d => d.name), message };
            } catch (e) {
                log('error', `Failed to unveil the astral plane of ${fullPath}: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to unveil directory: ${e.message}` };
            }
        }
    },
    {
        name: 'delete_file',
        description: 'Deletes a specified file. Use with caution.',
        schema: {
            filePath: { type: 'STRING', required: true, description: 'The path to the file to delete.' }
        },
        execute: async (params, { cwd, dryRun, confirmDestructive }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would banish the scroll: ${params.filePath}` };
            const fullPath = sanitizePath(params.filePath, cwd);
            if (!fs.existsSync(fullPath)) return { success: false, message: `The scroll to be banished was not found in the ether: ${params.filePath}` };
            if (fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `This is a directory, not a scroll. Use 'delete_directory' for this rite.` };

            if (confirmDestructive) {
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
        }
    },
    {
        name: 'delete_directory',
        description: 'Deletes an empty directory. Use with caution for non-empty directories with `recursive: true`.',
        schema: {
            dirPath: { type: 'STRING', required: true, description: 'The path to the directory to delete.' },
            recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, deletes the directory and its contents recursively.' }
        },
        execute: async (params, { cwd, dryRun, confirmDestructive }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would collapse the astral plane: ${params.dirPath}` };
            const fullPath = sanitizePath(params.dirPath, cwd);
            if (!fs.existsSync(fullPath)) return { success: false, message: `The astral plane to be collapsed was not found: ${params.dirPath}` };
            if (!fs.lstatSync(fullPath).isDirectory()) return { success: false, message: `This is not an astral plane (directory): ${params.dirPath}` };

            if (confirmDestructive || params.recursive) {
                const confirmation = await promptUser(color(`⚠️ Confirm the collapse of this astral plane ${params.recursive ? '(recursively)' : ''}: ${params.dirPath}? (y/N): `, colors.neonPink));
                if (!['y', 'yes'].includes(confirmation)) {
                    log('warn', `🚫 The ritual of collapse was blocked by the wizard's will: ${params.dirPath}`, colors.neonPink);
                    return { success: false, message: `🚫 The ritual of collapse was halted.` };
                }
            }

            try {
                fs.rmSync(fullPath, { recursive: params.recursive || false, force: true });
                log('info', `✅ The astral plane has been collapsed: ${fullPath}`, colors.neonLime);
                return { success: true, message: `✅ The astral plane has been collapsed: ${fullPath}` };
            } catch (e) {
                log('error', `Failed to collapse the astral plane ${fullPath}: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to collapse the astral plane: ${e.message}` };
            }
        }
    },
    {
        name: 'make_directory',
        description: 'Creates a new directory, including any necessary parent directories.',
        schema: {
            dirPath: { type: 'STRING', required: true, description: 'The path of the directory to create.' }
        },
        execute: async (params, { cwd, dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would forge a new astral plane: ${params.dirPath}` };
            const fullPath = sanitizePath(params.dirPath, cwd);
            try {
                fs.mkdirSync(fullPath, { recursive: true });
                log('info', `✅ A new astral plane has been forged: ${fullPath}`, colors.neonLime);
                return { success: true, message: `✅ Forged a new astral plane: ${fullPath}` };
            } catch (e) {
                log('error', `Failed to forge a new astral plane at ${fullPath}: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to forge a new astral plane: ${e.message}` };
            }
        }
    },
    {
        name: 'touch_file',
        description: 'Creates an empty file at the specified path.',
        schema: {
            filePath: { type: 'STRING', required: true, description: 'The path of the file to create.' }
        },
        execute: async (params, { cwd, dryRun }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would conjure an empty scroll: ${params.filePath}` };
            const fullPath = sanitizePath(params.filePath, cwd);
            try {
                fs.writeFileSync(fullPath, '', { flag: 'a' });
                log('info', `✅ An empty scroll has been conjured: ${fullPath}`, colors.neonLime);
                return { success: true, message: `✅ Conjured an empty scroll: ${fullPath}` };
            } catch (e) {
                log('error', `Failed to conjure an empty scroll at ${fullPath}: ${e.message}`, colors.brightRed);
                return { success: false, message: `Failed to conjure an empty scroll: ${e.message}` };
            }
        }
    },
    {
        name: 'rename_path',
        description: 'Renames or moves a file or directory.',
        schema: {
            oldPath: { type: 'STRING', required: true, description: 'The current path of the file or directory.' },
            newPath: { type: 'STRING', required: true, description: 'The new path for the file or directory.' }
        },
        execute: async (params, { cwd, dryRun, confirmDestructive }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would transmute ${params.oldPath} to ${params.newPath}` };
            const oldFullPath = sanitizePath(params.oldPath, cwd);
            const newFullPath = sanitizePath(params.newPath, cwd);
            if (!fs.existsSync(oldFullPath)) return { success: false, message: `The source path for transmutation was not found: ${params.oldPath}` };

            if (confirmDestructive) {
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
        }
    },
    {
        name: 'copy_path',
        description: 'Copies a file or directory.',
        schema: {
            sourcePath: { type: 'STRING', required: true, description: 'The path of the file or directory to copy.' },
            destinationPath: { type: 'STRING', required: true, description: 'The destination path for the copy.' },
            recursive: { type: 'BOOLEAN', required: false, default: false, description: 'If true, copies directories recursively.' }
        },
        execute: async (params, { cwd, dryRun, confirmDestructive }) => {
            if (dryRun) return { success: true, message: `[DRY RUN] Would clone the essence of ${params.sourcePath}` };
            const sourceFullPath = sanitizePath(params.sourcePath, cwd);
            const destinationFullPath = sanitizePath(params.destinationPath, cwd);
            if (!fs.existsSync(sourceFullPath)) return { success: false, message: `The source essence to be cloned was not found: ${params.sourcePath}` };

            if (confirmDestructive && (fs.lstatSync(sourceFullPath).isDirectory() || fs.existsSync(destinationFullPath))) {
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
        }
    },
    {
        name: 'get_current_working_directory',
        description: 'Returns the current working directory of the agent.',
        schema: {},
        execute: async (params, { cwd }) => {
            log('debug', `The current location in the ether is: ${cwd}`, colors.gray);
            return { success: true, cwd: cwd, message: `Current working directory: ${cwd}` };
        }
    },
];
