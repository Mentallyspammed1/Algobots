# strategies.py

import importlib
import inspect
import os

# Dictionary to hold all discovered strategy classes
STRATEGIES = {}


def load_strategies():
    """Dynamically load all strategy classes from the 'strategies' directory."""
    strategies_dir = os.path.join(os.path.dirname(__file__), "strategies")
    for filename in os.listdir(strategies_dir):
        if filename.endswith(".py") and not filename.startswith("__"):
            module_name = f"strategies.{filename[:-3]}"
            try:
                module = importlib.import_module(module_name)
                for name, obj in inspect.getmembers(module, inspect.isclass):
                    # Assuming strategy classes have 'Strategy' in their name
                    # and are not the base Strategy class if one exists.
                    if "Strategy" in name and name != "Strategy":
                        STRATEGIES[name] = obj
            except ImportError as e:
                print(f"Error importing strategy from {filename}: {e}")


# Load strategies on module import
load_strategies()
