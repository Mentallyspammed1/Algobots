class Tool {
    constructor(name, description, schema, execute) {
        this.name = name;
        this.description = description;
        this.schema = schema;
        this.execute = execute;
    }

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

module.exports = {
    Tool,
};
