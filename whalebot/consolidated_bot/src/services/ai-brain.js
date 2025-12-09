/**
 * 🌊 WHALEWAVE PRO - LEVIATHAN CORE (AI Brain Module)
 * ======================================================
 * Handles interaction with the Gemini AI model for generating trading signals.
 */

import axios from 'axios';
import { Decimal } from 'decimal.js';
import { GoogleGenerativeAI } from '@google/generative-ai';
import dotenv from 'dotenv';
import fs from 'fs';
import path from 'path';
import Ajv from 'ajv'; // For validating AI response schema

import { ConfigManager } from '../config.js'; // Access bot configuration
import { TA } from '../technical-analysis.js'; // For technical indicator data
import * as Utils from '../utils.js';       // For utility functions (context building, formatting)
import logger from '../logger.js';         // Use configured logger
import { NEON } from '../ui.js';           // For console coloring

dotenv.config(); // Load environment variables

// Resolve __dirname in ES module context if needed
const __filename = new URL(import.meta.url).pathname;
const __dirname = path.dirname(__filename);

// --- AI BRAIN ─────────────────────────────────────────────────────────────
// Handles interaction with the Gemini AI model for signal generation.
export class AIBrain {
    constructor(config) {
        this.config = config;
        const key = process.env.GEMINI_API_KEY;
        if (!key) {
            // Critical error if API key is missing
            throw new Error("GEMINI_API_KEY not found in environment variables. Cannot initialize AI Brain.");
        }
        this.model = new GoogleGenerativeAI(key).getGenerativeModel({ model: this.config.ai.model });
        this.conversationContext = []; // Stores chat history for context
        this.maxContextLength = 10; // Limit conversation history to manage token usage
    }

    // Adds a message to the conversation history, maintaining context limit.
    addToContext(role, content) {
        this.conversationContext.push({ role, content });
        if (this.conversationContext.length > this.maxContextLength) {
            this.conversationContext.shift(); // Remove oldest message if history exceeds limit
        }
    }

    // Builds the comprehensive prompt for the AI, including market context, risk parameters, and decision rules.
    buildPrompt(ctx) {
        // Format conversation history for the prompt
        const contextStr = this.conversationContext.map(entry => `${entry.role}: ${entry.content}`).join('\n');

        // Construct the detailed prompt string with all relevant market and risk information
        return `
        ${contextStr}

        Act as an Institutional Algorithmic Scalper focused on high-probability reversals and breakouts.
        
        MARKET CONTEXT:
        - Current Price: ${ctx.price}
        - Market Regime: ${ctx.marketRegime}
        - Volatility: ${ctx.volatility} (Annualized)
        - Scalp (3m) Metrics: RSI=${ctx.rsi}, MFI=${ctx.mfi}, Chop=${ctx.chop}
        - Trend Strength: LinReg Slope=${ctx.trend_angle}, R2=${ctx.trend_quality} | ADX=${ctx.adx}
        - Momentum Detail: Stoch K/D=${ctx.stoch_k}/${ctx.stoch_d}, CCI=${ctx.cci}, MACD Hist=${ctx.macd_hist}
        - Structure: MTF Trend=${ctx.trend_mtf}, FVG=${ctx.fvg ? ctx.fvg.type + ' @ ' + ctx.fvg.price.toFixed(2) : 'NONE'}
        - Volatility Check: Squeeze Active? ${ctx.squeeze ? 'YES (Explosion Imminent)' : 'NO'}
        - **Trend Confirmation:** Chandelier=${ctx.chandelierExit}, ST=${ctx.superTrend}
        - Order Flow: Approaching Buy Wall @ ${ctx.walls.buy || 'N/A'} | Approaching Sell Wall @ ${ctx.walls.sell || 'N/A'}
        - **Key Levels:** FibPivots: P=${ctx.fibs.P}, S1=${ctx.fibs.S1}, R1=${ctx.fibs.R1} | Orderbook S/R: ${ctx.sr_levels}
        - **Quantitative Bias Score (WSS):** ${ctx.wss} (Positive = Bullish, Negative = Bearish)

        RISK MANAGEMENT CONTEXT:
        - Current Volatility Regime: ${ctx.marketRegime}
        - Volatility Level: ${ctx.volatility}
        - Adjust position sizing and stop losses based on volatility conditions.

        DECISION REGIME (Must choose one based on Chop/ADX):
        1. MOMENTUM: Chop < 40 AND ADX > 25. Strategy: Trade in direction of WSS. Use FVG/Chande SL/TP.
        2. MEAN REVERSION: Chop > 60 OR ADX < 20. Strategy: Trade in direction of WSS ONLY if WSS >= 3.0 (Bullish) or WSS <= -3.0 (Bearish). Fade extreme RSI/Stoch/CCI levels using Fibs/Walls as entry/exit.
        3. NOISE/WAIT: Chop 40-60 OR WSS near zero. Strategy: HOLD.

        CRITICAL RULE: WSS score must align with the attempted trade action. (i.e., WSS >= 1.0 for BUY).

        OUTPUT VALID JSON ONLY: { "action": "BUY"|"SELL"|"HOLD", "confidence": 0.0-1.0, "entry": number, "sl": number, "tp": number, "reason": "string" }
        `;
    }

    // Analyzes market context and returns a trading signal { action, confidence, entry, sl, tp, reason }.
    async analyze(ctx) {
        const prompt = this.buildPrompt(ctx); // Build the prompt for the AI
        
        try {
            const res = await this.model.generateContent(prompt); // Generate content from Gemini
            let text = res.response.text();
            
            // Attempt to parse JSON response, handling potential formatting issues
            const firstBrace = text.indexOf('{');
            const lastBrace = text.lastIndexOf('}');
            if (firstBrace >= 0 && lastBrace > firstBrace) {
                text = text.substring(firstBrace, lastBrace + 1); // Extract JSON part
            }

            const parsed = JSON.parse(text); // Parse the response
            const validated = this.validateSignal(parsed, ctx); // Validate the parsed signal
            this.addToContext('assistant', JSON.stringify(validated)); // Add AI's response to conversation context
            
            return validated; // Return the validated signal
        } catch (e) {
            logger.error(`AI Analysis Error: ${e.message}`);
            this.addToContext('system', `Error: ${e.message}`); // Log error to context
            // Return a HOLD signal on any error during AI interaction or parsing
            return { action: "HOLD", confidence: 0, reason: `AI Communication Failure: ${e.message}` };
        }
    }

    // Validates the AI's generated signal against defined rules (parameters, R/R, WSS).
    validateSignal(signal, ctx) {
        const WSS_THRESHOLD = this.config.indicators.wss_weights.action_threshold; // Get threshold from config

        // Enforce Critical Rule: WSS must align with BUY/SELL actions
        if (signal.action === 'BUY' && signal.confidence > 0 && ctx.wss < WSS_THRESHOLD) {
            return { action: "HOLD", confidence: 0, reason: `WSS (${ctx.wss}) did not meet minimum threshold (${WSS_THRESHOLD}) for BUY action.` };
        }
        if (signal.action === 'SELL' && signal.confidence > 0 && ctx.wss > -WSS_THRESHOLD) {
            return { action: "HOLD", confidence: 0, reason: `WSS (${ctx.wss}) did not meet minimum threshold (-${WSS_THRESHOLD}) for SELL action.` };
        }

        // Validate trade parameters if an action (BUY/SELL) is proposed
        if (signal.action !== 'HOLD') {
            // Check if entry, SL, and TP are valid numbers
            if (typeof signal.entry !== 'number' || typeof signal.sl !== 'number' || typeof signal.tp !== 'number') {
                return { action: "HOLD", confidence: 0, reason: "AI returned non-numeric SL/TP/Entry." };
            }

            // Calculate Risk/Reward ratio
            const risk = Math.abs(signal.entry - signal.sl);
            const reward = Math.abs(signal.tp - signal.entry);
            const rrRatio = reward / risk;

            // Ensure Risk/Reward ratio is favorable (e.g., at least 1:1)
            if (rrRatio < 1.0) {
                return { action: "HOLD", confidence: 0, reason: `Risk/Reward ratio too low: ${rrRatio.toFixed(2)}` };
            }
        }
        return signal; // Return the validated signal if all checks pass
    }
}