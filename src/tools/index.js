const fs = require('fs');
const path = require('path');
const { Tool } = require('../utils/tool');
const aliases = require('./aliases');

const tools = [];
const toolMap = new Map();

const toolFiles = fs.readdirSync(__dirname).filter(file => file.endsWith('.js') && !['index.js', 'aliases.js'].includes(file));

for (const file of toolFiles) {
    const toolDefinitions = require(path.join(__dirname, file));
    for (const toolDef of toolDefinitions) {
        const tool = new Tool(toolDef.name, toolDef.description, toolDef.schema, toolDef.execute);
        tools.push(tool);
        toolMap.set(tool.name, tool);
    }
}

for (const alias of aliases) {
    const targetTool = toolMap.get(alias.target);
    if (targetTool) {
        const aliasTool = new Tool(alias.name, targetTool.description, targetTool.schema, targetTool.execute);
        tools.push(aliasTool);
        toolMap.set(alias.name, aliasTool);
    }
}

module.exports = {
    tools,
    toolMap,
};
