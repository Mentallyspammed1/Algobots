import logging
import threading
import time

from live_simulator import LiveSimulator

from config import Config
from live_data_generator import LiveDataGenerator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for the live trading simulation using generated data."""
    config: Config = Config()
    data_generator: LiveDataGenerator = LiveDataGenerator(symbol=config.SYMBOL)
    simulator: LiveSimulator = LiveSimulator(
        config=config, data_generator=data_generator.data_generator()
    )

    # Run the simulation in a separate thread
    simulation_thread = threading.Thread(target=simulator.run_simulation)
    simulation_thread.start()

    # Periodically print results
    while simulation_thread.is_alive():
        time.sleep(30)
        simulator.calculate_and_print_results()


if __name__ == "__main__":
    main()
