# TODO

This file tracks the remaining TODOs in the project.

## Whalebot

*   [x] Implement CCXT call to update stop loss on the exchange in `whalebot/Backups/wb2.1.1.py.20250901_233609.bak` (L872, L883, L889)
*   [ ] Refactor `whalebot.py` to use limit orders for entry instead of market orders, and manage stop-loss and take-profit orders as separate, post-only orders after the entry order is filled.

## General Improvements

*   [ ] Codebase Cleanup: Review and remove any unused or commented-out code, redundant files, and old backup files (e.g., those in `whalebot/Backups/` and `htmlbackup/`).
*   [ ] Dependency Management: Create a `requirements.txt` file for all Python projects and a `package.json` for all Node.js projects, ensuring all dependencies are explicitly listed and up-to-date.
*   [ ] Documentation Enhancement: Improve existing documentation (e.g., `README.md` files) for clarity, completeness, and accuracy, especially for setup, configuration, and usage instructions. Add a `CONTRIBUTING.md` file.
*   [ ] Error Handling Improvement: Implement more robust error handling and logging mechanisms across all bots to ensure graceful degradation and better debugging.

## Third-Party Libraries

*   The `bybit/psutil-7.0.0` directory contains a third-party library with its own set of TODOs. These are not related to the project and will be ignored.