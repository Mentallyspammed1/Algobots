import { Candle, Signal } from "../core/types";

/**
 * Interface for a trading strategy.
 * Ensures that any strategy can be plugged into the main bot.
 */
export interface IStrategy {
  readonly name: string;

  /**
   * Update the strategy with the latest market data (a new candle).
   * @param candle The latest candle.
   */
  update(candle: Candle): void;

  /**
   * Check for a new trading signal based on the current state of the strategy.
   * @returns A Signal ('long', 'short', or 'hold').
   */
  getSignal(): Signal;
}