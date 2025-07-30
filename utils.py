# utils.py
from decimal import Decimal, ROUND_HALF_UP

def round_decimal(value: float, precision: int) -> Decimal:
    """
    Rounds a float value to a specified decimal precision using Decimal for accuracy.

    Args:
        value (float): The float value to round.
        precision (int): The number of decimal places to round to.

    Returns:
        Decimal: The rounded value as a Decimal object.
    """
    if not isinstance(value, (float, int)):
        raise TypeError("Value must be a float or integer.")
    if not isinstance(precision, int) or precision < 0:
        raise ValueError("Precision must be a non-negative integer.")

    # Create a Decimal object for the value
    decimal_value = Decimal(str(value))

    # Create a rounding context based on the desired precision
    # e.g., '0.001' for 3 decimal places
    rounding_context = Decimal(10) ** -precision

    # Round using ROUND_HALF_UP (standard rounding)
    return decimal_value.quantize(rounding_context, rounding=ROUND_HALF_UP)

def calculate_order_quantity(usdt_amount: float, current_price: float, min_qty: float, qty_step: float) -> float:
    """
    Calculates the appropriate order quantity based on a USDT amount, current price,
    and symbol-specific minimum quantity and quantity step.

    Args:
        usdt_amount (float): The desired amount in USDT to trade.
        current_price (float): The current price of the asset.
        min_qty (float): The minimum order quantity for the symbol.
        qty_step (float): The quantity step (increment) for the symbol.

    Returns:
        float: The calculated and adjusted order quantity.
    """
    if usdt_amount <= 0 or current_price <= 0 or min_qty <= 0 or qty_step <= 0:
        raise ValueError("All input values must be positive.")

    # Convert inputs to Decimal for precise calculations
    dec_usdt_amount = Decimal(str(usdt_amount))
    dec_current_price = Decimal(str(current_price))
    dec_min_qty = Decimal(str(min_qty))
    dec_qty_step = Decimal(str(qty_step))

    # Calculate raw quantity
    raw_qty = dec_usdt_amount / dec_current_price

    # Adjust quantity to be a multiple of qty_step
    # Determine the precision for rounding based on qty_step
    qty_step_str = str(qty_step)
    if '.' in qty_step_str:
        precision = len(qty_step_str.split('.')[1])
    else:
        precision = 0
    
    # Round raw_qty down to the nearest multiple of qty_step
    # This ensures we don't exceed the USDT amount and adhere to step size
    adjusted_qty = (raw_qty // dec_qty_step) * dec_qty_step

    # Ensure the quantity meets the minimum requirement
    if adjusted_qty < dec_min_qty:
        adjusted_qty = dec_min_qty
    
    # Convert back to float for return, using round_decimal for final precision
    # The precision here should match the qty_step precision to avoid floating point issues
    return float(round_decimal(float(adjusted_qty), precision))