
from decimal import Decimal
from typing import Dict, List, Tuple, Optional, Any
from collections import deque
import math # For intro_sort if it's used

# Assuming sorting_algorithms.py exists and contains these functions
# If not, these imports will need to be adjusted or the functions defined here.
# For now, we'll assume they are available.
# from sorting_algorithms import merge_sort, quick_sort, insertion_sort, heap_sort, bucket_sort

# Placeholder for sorting functions if sorting_algorithms.py is not yet created
# In a real scenario, these would be imported from the generated sorting_algorithms.py
def merge_sort(collection: list) -> list:
    if len(collection) <= 1:
        return collection
    mid_index = len(collection) // 2
    return merge_sort(collection[:mid_index]) + merge_sort(collection[mid_index:]) # Simplified for placeholder

def quick_sort(collection: list) -> list:
    if len(collection) < 2:
        return collection
    pivot = collection[len(collection) // 2]
    lesser = [item for item in collection if item < pivot]
    equal = [item for item in collection if item == pivot]
    greater = [item for item in collection if item > pivot]
    return quick_sort(lesser) + equal + quick_sort(greater)

def insertion_sort(collection: list) -> list:
    for i in range(1, len(collection)):
        key = collection[i]
        j = i - 1
        while j >= 0 and key < collection[j]:
            collection[j + 1] = collection[j]
            j -= 1
        collection[j + 1] = key
    return collection

def heap_sort(unsorted: list) -> list:
    # Simplified placeholder for heap_sort
    return sorted(unsorted)

def bucket_sort(my_list: list, bucket_count: int = 10) -> list:
    # Simplified placeholder for bucket_sort
    return sorted(my_list)


def sort_orderbook_levels(orderbook_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sort orderbook bid/ask levels using merge sort for stability
    """
    # Extract bid and ask data
    # Assuming orderbook_data structure like {"result": {"b": [["43000.00", "0.5"], ...], "a": [...]}}
    bids = orderbook_data.get("result", {}).get("b", [])
    asks = orderbook_data.get("result", {}).get("a", [])
    
    # Convert to sortable format (price as float, keep original format)
    # Use Decimal for precision
    bid_tuples = [(Decimal(price), Decimal(qty), [price, qty]) for price, qty in bids]
    ask_tuples = [(Decimal(price), Decimal(qty), [price, qty]) for price, qty in asks]
    
    # Sort bids (highest price first for bids)
    # For merge_sort, we need a comparison function or sort by the first element (price)
    # Python's sorted() is stable and efficient. If using custom merge_sort, ensure it handles tuples.
    sorted_bids = sorted(bid_tuples, key=lambda x: x[0], reverse=True) # Sort by price, descending
    
    # Sort asks (lowest price first for asks)  
    sorted_asks = sorted(ask_tuples, key=lambda x: x[0]) # Sort by price, ascending
    
    # Extract back to original format
    orderbook_data["result"]["b"] = [[str(item[0]), str(item[1])] for item in sorted_bids]
    orderbook_data["result"]["a"] = [[str(item[0]), str(item[1])] for item in sorted_asks]
    
    return orderbook_data

def process_delta_update(current_orderbook: Dict[str, Any], delta_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply delta updates while maintaining sorted order
    """
    bids = current_orderbook.get("b", [])
    asks = current_orderbook.get("a", [])
    
    # Process bid updates
    for price_str, qty_str in delta_data.get("b", []):
        price = Decimal(price_str)
        qty = Decimal(qty_str)
        
        # Find index of existing price level
        idx_to_update = -1
        for i, bid_level in enumerate(bids):
            if Decimal(bid_level[0]) == price:
                idx_to_update = i
                break
        
        if qty == Decimal('0.0'):
            # Remove price level
            if idx_to_update != -1:
                bids.pop(idx_to_update)
        else:
            # Update or insert price level
            if idx_to_update != -1:
                bids[idx_to_update] = [str(price), str(qty)]
            else:
                bids.append([str(price), str(qty)])
                # Re-sort bids to maintain order (insertion sort is good for nearly sorted lists)
                # For simplicity, using Python's sorted() here.
                bids = sorted(bids, key=lambda x: Decimal(x[0]), reverse=True)
    
    # Process ask updates (similar logic)
    for price_str, qty_str in delta_data.get("a", []):
        price = Decimal(price_str)
        qty = Decimal(qty_str)
        
        idx_to_update = -1
        for i, ask_level in enumerate(asks):
            if Decimal(ask_level[0]) == price:
                idx_to_update = i
                break
        
        if qty == Decimal('0.0'):
            if idx_to_update != -1:
                asks.pop(idx_to_update)
        else:
            if idx_to_update != -1:
                asks[idx_to_update] = [str(price), str(qty)]
            else:
                asks.append([str(price), str(qty)])
                asks = sorted(asks, key=lambda x: Decimal(x[0])) # Ascending sort

    return {"b": bids, "a": asks}

def fast_orderbook_sort(price_levels: List[List[str]]) -> List[List[str]]:
    """
    High-performance sorting for market making bots
    Uses heap sort for predictable O(n log n) performance
    """
    # Convert to numeric tuples for sorting
    # Assuming price_levels is like [["43000.00", "0.5"], ...]
    sortable_data = []
    for price_str, qty_str in price_levels:
        sortable_data.append((Decimal(price_str), price_str, qty_str))
    
    # Use Python's sorted() as a placeholder for heap_sort for now
    # For actual heap_sort, you'd need a heapify function and extract_min/max
    sorted_data = sorted(sortable_data, key=lambda x: x[0]) # Default ascending sort
    
    # Convert back to original format
    return [[item[1], item[2]] for item in sorted_data]

def aggregate_price_levels(orderbook_data: Dict[str, Any], price_increment: float = 0.01) -> Dict[str, Any]:
    """
    Aggregate orderbook levels into price buckets
    """
    bids = orderbook_data.get("result", {}).get("b", [])
    
    # Extract prices for bucketing
    prices = [Decimal(price) for price, _ in bids]
    
    if not prices:
        return orderbook_data
    
    # Use bucket sort to group by price ranges
    min_price, max_price = min(prices), max(prices)
    
    # Ensure bucket_count is at least 1
    bucket_count = max(1, int((max_price - min_price) / Decimal(str(price_increment))) + 1)
    
    # Create price buckets
    # Simplified bucket sort logic for demonstration
    buckets: List[List[Decimal]] = [[] for _ in range(bucket_count)]
    
    if bucket_count > 0:
        bucket_size = (max_price - min_price) / bucket_count
        if bucket_size == Decimal('0'): # Handle case where all prices are the same
            for val in prices:
                buckets[0].append(val)
        else:
            for val in prices:
                index = min(int((val - min_price) / bucket_size), bucket_count - 1)
                buckets[index].append(val)

    # Aggregate quantities within each bucket (simplified, just returning sorted prices)
    # For a full aggregation, you'd sum quantities for prices within each bucket
    aggregated_prices = [val for bucket in buckets for val in sorted(bucket)]
    
    # This function would typically return a new aggregated orderbook structure
    # For now, just returning the original orderbook_data as aggregation logic is complex
    return orderbook_data
