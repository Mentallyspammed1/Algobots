"""
Main entrypoint for the Leviathan Trading Bot.
"""
import asyncio
import logging
from dotenv import load_dotenv
from src.engine import LeviathanEngine

def main():
    """
    Initializes and runs the trading engine.
    """
    # Load environment variables from .env file
    load_dotenv()
    
    logging.info("Initializing Leviathan Engine...")
    engine = LeviathanEngine()
    
    try:
        # Run the asynchronous start method
        asyncio.run(engine.start())
    except KeyboardInterrupt:
        logging.info("Shutdown signal received. Exiting.")
    except Exception as e:
        logging.critical(f"The engine has crashed with a fatal error: {e}", exc_info=True)

if __name__ == "__main__":
    main()
