import logging

from rich.console import Console
from rich.logging import RichHandler


class ContextFilter(logging.Filter):
    """A logging filter to inject a symbol into log records."""

    _symbol = "SYSTEM"  # Class attribute as a default

    @classmethod
    def set_symbol(cls, symbol: str):
        cls._symbol = symbol

    def filter(self, record):
        # Ensure 'symbol' attribute is always present
        if not hasattr(record, "symbol"):
            record.symbol = self._symbol
        return True


def setup_logging():
    console = Console()

    # Rich logging handler configuration
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] %(filename)s:%(lineno)d %(message)s",
        handlers=[
            RichHandler(
                console=console,
                show_time=True,
                show_level=True,
                show_path=True,
                enable_link_path=True,
            ),
            logging.FileHandler("marketmaker.log"),
        ],
    )
    # Get the logger named "rich" which is configured by RichHandler
    logger = logging.getLogger("rich")
    logger.addFilter(ContextFilter())
    return logger  # Return the configured logger
