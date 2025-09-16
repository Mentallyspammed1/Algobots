import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Sanitizes a symbol string to prevent injection attacks.
 * Allows only uppercase letters and numbers.
 * @param symbol The raw symbol string.
 * @returns A sanitized symbol string.
 */
export function sanitizeSymbol(symbol: string): string {
    return symbol.replace(/[^A-Z0-9]/g, '');
}
