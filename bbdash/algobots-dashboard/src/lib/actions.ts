'use server';

import { generateTradingSignal, type GenerateTradingSignalInput, type GenerateTradingSignalOutput } from '@/ai/flows/generate-trading-signal';

/**
 * Server action to generate an AI-powered trading signal.
 * This function calls the Genkit flow and handles its response or errors.
 *
 * @param options - The input options for the trading signal generation.
 * @returns An object containing the success status, the analysis, and an optional error message.
 */
export async function getAiTradingSignal(options: GenerateTradingSignalInput): Promise<{ success: boolean, analysis?: GenerateTradingSignalOutput, error?: string }> {
  try {
    const result = await generateTradingSignal(options);
    if (!result) {
        return { success: false, error: 'AI returned no result.' };
    }
    return { success: true, analysis: result };
  } catch (error) {
    console.error('Error generating AI trading signal:', error);
    const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred.';
    return { success: false, error: errorMessage };
  }
}
