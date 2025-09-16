// To run this code you need to install the following dependencies:
// npm install @google/genai mime
// npm install -D @types/node

import { GoogleGenAI } from '@google/genai';
import { createInterface } from 'readline';
import * as fs from 'fs';
import 'dotenv/config';

async function main() {
  // Check for the API key from environment variables
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    console.error('GEMINI_API_KEY is not set. Please set it in your environment or .env file.');
    process.exit(1);
  }

  // Create a readline interface for user input
  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: '> ',
  });

  // Initialize the Gemini AI client
  const ai = new GoogleGenAI({ apiKey });
  const model = 'gemini-2.5-pro';

  // Define tools for the model to use
  const tools = [
    {
      functionDeclarations: [
        {
          name: 'writeFile',
          description: 'Write content to a file.',
          parameters: {
            type: 'OBJECT',
            properties: {
              filePath: {
                type: 'STRING',
                description: 'The path of the file to write to.',
              },
              content: {
                type: 'STRING',
                description: 'The content to write to the file.',
              },
            },
            required: ['filePath', 'content'],
          },
        },
      ],
    },
  ];

  // Configure the model with tools
  const config = {
    tools,
  };

  console.log('Welcome! I can now write files. Type "exit" to quit.');
  rl.prompt();

  // Start an interactive loop for continuous conversation
  for await (const userInput of rl) {
    if (userInput.toLowerCase() === 'exit') {
      console.log('Goodbye!');
      break;
    }

    try {
      const contents = [
        {
          role: 'user',
          parts: [{ text: userInput }],
        },
      ];

      let response = await ai.models.generateContentStream({
        model,
        config,
        contents,
      });

      let text = '';
      for await (const chunk of response) {
        const chunkText = chunk.text;
        if (chunkText) {
          text += chunkText;
          process.stdout.write(chunkText);
        }

        if (chunk.functionCalls) {
          for (const call of chunk.functionCalls) {
            if (call.name === 'writeFile') {
              const { filePath, content } = call.args;
              fs.writeFileSync(filePath, content);
              console.log(`
[File written to ${filePath}]`);

              // Send the result back to the model
              contents.push({
                role: 'model',
                parts: [{ functionCall: call }],
              });
              contents.push({
                role: 'function',
                parts: [
                  {
                    functionResponse: {
                      name: 'writeFile',
                      response: { success: true },
                    },
                  },
                ],
              });

              response = await ai.models.generateContentStream({
                model,
                config,
                contents,
              });

              for await (const newChunk of response) {
                const newChunkText = newChunk.text;
                if (newChunkText) {
                  text += newChunkText;
                  process.stdout.write(newChunkText);
                }
              }
            }
          }
        }
      }
      process.stdout.write('\n');
      rl.prompt();
    } catch (error) {
      console.error('An error occurred:', error);
      rl.prompt();
    }
  }
}

main().catch((err) => {
  console.error('An unhandled error occurred:', err);
  process.exit(1);
});
