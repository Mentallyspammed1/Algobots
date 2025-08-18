
import sys
try:
    import pandas_ta as ta
    import numpy as np
    print("Successfully imported pandas_ta and numpy")
    print(f"numpy version: {np.__version__}")
except ImportError as e:
    print(f"CRITICAL ERROR: Missing package '{e.name}'. Please install it with: pip install \"{e.name}\"")
    sys.exit(1)
