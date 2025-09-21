# base_strategy.py

class Strategy:
    """Base class for all trading strategies."""

    def __init__(self, client, config):
        self.client = client
        self.config = config

    def generate_signals(self, df):
        """Generate trading signals from a DataFrame."""
        raise NotImplementedError("generate_signals method not implemented")
