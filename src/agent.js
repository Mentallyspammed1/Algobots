const { GoogleGenerativeAI } = require('@google/generative-ai');
const { log, colors, color } = require('./utils/logger');
const { tools, toolMap } = require('./tools');

class TermuxCodingAgent {
  constructor(config) {
    this.config = config;
    this.genAI = new GoogleGenerativeAI(config.GEMINI_API_KEY);
    this.modelName = config.MODEL;
    this.cwd = process.cwd();
    this.tools = tools;
    this.toolMap = toolMap;

    this.model = this.genAI.getGenerativeModel({
      model: this.modelName,
      generationConfig: {
        maxOutputTokens: config.MAX_OUTPUT_TOKENS,
        temperature: config.TEMPERATURE,
        topP: config.TOP_P,
        topK: config.TOP_K,
        stopSequences: config.STOP_SEQUENCES,
      },
      tools: [{ functionDeclarations: this.tools.map(tool => tool.getFunctionDeclaration()) }]
    });

    this.chat = null;
  }

  async validateModel() {
    try {
      const testModel = this.genAI.getGenerativeModel({ model: this.modelName });
      await testModel.countTokens("Unveiling the path...");
      log('info', `✅ The cosmic link to "${this.modelName}" has been forged.`, colors.neonLime);
      return true;
    } catch (e) {
      log('error', `❌ Failed to forge the cosmic link to "${this.modelName}": ${e.message}`, colors.brightRed);
      log('info', `👉 Check your API key, model name, network connection, or celestial quota.`, colors.neonOrange);
      process.exit(1);
    }
  }

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

  async processTask(task) {
    if (!this.chat) {
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
    let currentInput = task;
    const MAX_RETRIES_429 = 3;

    while (iterations < this.config.MAX_ITERATIONS) {
      iterations++;
      log('info', color(`--- Iteration ${iterations}/${this.config.MAX_ITERATIONS} ---`, colors.bold));

      let modelResponseText = '';
      let toolCalls = [];
      let response;
      let retries = 0;

      try {
        if (this.config.STREAM) {
          process.stdout.write(color(`💬 Pyrmethus > `, colors.brightCyan));
          let streamedText = '';
          const streamResult = await this.chat.sendMessageStream(currentInput);
          for await (const chunk of streamResult.stream) {
            streamedText += chunk.text();
            process.stdout.write(chunk.text());
          }
          console.log('');
          modelResponseText = streamedText;
          response = await this.chat.sendMessage(currentInput);
          toolCalls = response.response.functionCalls();

        } else {
          response = await this.chat.sendMessage(currentInput);
          modelResponseText = response.response.text();
          toolCalls = response.response.functionCalls();
          log('info', `💬 Pyrmethus > ${modelResponseText}`, colors.brightCyan);
        }

      } catch (error) {
        if (error.message.includes('[429 Too Many Requests]')) {
          log('warn', `⚠️  Rate limit hit (429 Too Many Requests). Retrying...`, colors.neonOrange);
          retries++;
          if (retries <= MAX_RETRIES_429) {
            const retryMatch = error.message.match(/Please retry in (\d+(\.\d+)?)s/);
            const delay = retryMatch ? parseFloat(retryMatch[1]) * 1000 : 5000;
            await new Promise(resolve => setTimeout(resolve, delay));
            continue;
          } else {
            log('error', `❌ Max retries (${MAX_RETRIES_429}) for 429 error reached. Aborting this turn.`, colors.brightRed);
            break;
          }
        } else {
          log('error', `A disturbance in the cosmic ether prevented communication: ${error.message}`, colors.brightRed);
          break;
        }
      }

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

            const toolResult = await tool.execute(call.args, { cwd: this.cwd, ...this.config });
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

        currentInput = toolResultsParts;
      } else {
        if (modelResponseText.toLowerCase().includes("task is complete") || modelResponseText.toLowerCase().includes("incantation complete")) {
          log('info', `✅ The task has been completed in ${iterations} steps.`, colors.neonLime);
        } else {
          log('info', `✨ The oracle has spoken. Continuing dialogue if necessary, or task may be paused.`, colors.neonBlue);
        }
        break;
      }
    }

    if (iterations >= this.config.MAX_ITERATIONS && currentInput && currentInput.length > 0 && Array.isArray(currentInput) && currentInput.some(item => item.functionResponse)) {
      log('warn', `⚠️  Maximum incantations (${this.config.MAX_ITERATIONS}) reached. The task may be incomplete or requires further refinement.`, colors.neonOrange);
    }
  }
}

module.exports = {
    TermuxCodingAgent,
};
