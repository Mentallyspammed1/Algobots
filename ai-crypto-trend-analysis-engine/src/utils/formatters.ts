
/**
 * Formats a price with dynamic precision based on its value.
 * This ensures that low-value assets are displayed with enough precision
 * without cluttering the UI for high-value assets.
 *
 * @param price - The numerical price or a string representation of it.
 * @returns A formatted price string (e.g., "$65,123.45", "$0.1234", "$0.00001234").
 */
export const formatPrice = (price: number | string | null | undefined): string => {
    if (price === null || price === undefined || price === '') return '$...';
    
    const numericPrice = typeof price === 'string' ? parseFloat(price) : price;
    if (isNaN(numericPrice)) return '$...';

    let options: Intl.NumberFormatOptions;

    if (numericPrice === 0) {
        options = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    } else if (Math.abs(numericPrice) < 0.01) {
        // For prices under 1 cent, show higher precision
        options = { minimumFractionDigits: 4, maximumFractionDigits: 8 };
    } else if (Math.abs(numericPrice) < 1) {
        // For coins under $1 but over 1 cent
        options = { minimumFractionDigits: 4, maximumFractionDigits: 4 };
    } else { // For prices >= 1
        options = { minimumFractionDigits: 2, maximumFractionDigits: 2 };
    }
    
    // Using 'en-US' locale for consistent formatting regardless of user's system locale
    return `$${numericPrice.toLocaleString('en-US', options)}`;
};
