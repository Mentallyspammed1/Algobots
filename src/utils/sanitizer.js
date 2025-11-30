const path = require('path');

function sanitizePath(filePath, cwd) {
  if (!filePath) throw new Error("File path is required");

  const normalizedPath = path.normalize(filePath);
  const resolvedPath = path.resolve(cwd, normalizedPath);

  if (!resolvedPath.startsWith(cwd + path.sep) && resolvedPath !== cwd) {
    throw new Error(`Path traversal detected: "${filePath}" resolved to "${resolvedPath}" which is outside of the current working directory "${cwd}".`);
  }
  return resolvedPath;
}

module.exports = {
    sanitizePath,
};
