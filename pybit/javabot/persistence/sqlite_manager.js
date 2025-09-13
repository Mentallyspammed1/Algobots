const sqlite3 = require('sqlite3');
const { open } = require('sqlite');
const { Decimal } = require('decimal.js');

/**
 * Manages SQLite database interactions for persisting trade and position data.
 */
class SQLiteManager {
    /**
     * Creates an instance of SQLiteManager.
     * @param {string} dbFilePath - The path to the SQLite database file.
     * @param {object} logger - The logger instance for logging messages.
     */
    constructor(dbFilePath, logger) {
        this.dbFilePath = dbFilePath;
        this.logger = logger;
        this.db = null;
    }

    /**
     * Initializes the SQLite database, creates the 'trades' table if it doesn't exist.
     * @returns {Promise<void>} A promise that resolves when the database is initialized.
     */
    async initialize() {
        try {
            this.db = await open({
                filename: this.dbFilePath,
                driver: sqlite3.Database
            });

            await this.db.exec(`
                CREATE TABLE IF NOT EXISTS trades(
                    id TEXT PRIMARY KEY,
                    order_id TEXT,
                    symbol TEXT,
                    side TEXT,
                    qty REAL,
                    entry_time TEXT,
                    entry_price REAL,
                    sl REAL,
                    tp REAL,
                    status TEXT DEFAULT 'OPEN',
                    exit_time TEXT,
                    exit_price REAL,
                    pnl REAL
                )
            `);
            this.logger.info(`Database initialized: ${this.dbFilePath}`);
        } catch (e) {
            this.logger.critical(`Failed to initialize database: ${e.message}`);
            process.exit(1);
        }
    }

    /**
     * Adds a new trade record to the database.
     * @param {Trade} trade - The Trade object to add.
     * @returns {Promise<void>} A promise that resolves when the trade is added.
     */
    async addTrade(trade) {
        try {
            await this.db.run(
                "INSERT INTO trades(id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [
                    trade.id,
                    trade.order_id,
                    trade.symbol,
                    trade.side,
                    trade.qty.toNumber(),
                    trade.entry_time,
                    trade.entry_price.toNumber(),
                    trade.sl.toNumber(),
                    trade.tp.toNumber(),
                    trade.status,
                    trade.exit_time,
                    trade.exit_price,
                    trade.pnl
                ]
            );
            this.logger.debug(`Trade added: ${trade.id}`);
        } catch (e) {
            this.logger.error(`Failed to add trade ${trade.id}: ${e.message}`);
        }
    }

    /**
     * Retrieves all open trade records from the database.
     * @returns {Promise<Array<Trade>>} An array of Trade objects with status 'OPEN'.
     */
    async getOpenTrades() {
        try {
            const rows = await this.db.all("SELECT id, order_id, symbol, side, qty, entry_time, entry_price, sl, tp, status, exit_time, exit_price, pnl FROM trades WHERE status = 'OPEN'");
            return rows.map(row => ({
                id: row.id,
                order_id: row.order_id,
                symbol: row.symbol,
                side: row.side,
                qty: new Decimal(row.qty),
                entry_time: row.entry_time,
                entry_price: new Decimal(row.entry_price),
                sl: new Decimal(row.sl),
                tp: new Decimal(row.tp),
                status: row.status,
                exit_time: row.exit_time,
                exit_price: row.exit_price ? new Decimal(row.exit_price) : null,
                pnl: row.pnl ? new Decimal(row.pnl) : null,
            }));
        } catch (e) {
            this.logger.error(`Failed to get open trades: ${e.message}`);
            return [];
        }
    }

    /**
     * Updates the status of a trade record in the database.
     * @param {string} id - The ID of the trade to update.
     * @param {string} status - The new status of the trade (e.g., 'CLOSED').
     * @param {string|null} [exitTime=null] - The exit time in ISO string format.
     * @param {Decimal|null} [exitPrice=null] - The exit price.
     * @param {Decimal|null} [pnl=null] - The profit and loss for the trade.
     * @returns {Promise<void>} A promise that resolves when the trade status is updated.
     */
    async updateTradeStatus(id, status, exitTime = null, exitPrice = null, pnl = null) {
        try {
            await this.db.run(
                "UPDATE trades SET status = ?, exit_time = ?, exit_price = ?, pnl = ? WHERE id = ?",
                [
                    status,
                    exitTime,
                    exitPrice ? exitPrice.toNumber() : null,
                    pnl ? pnl.toNumber() : null,
                    id
                ]
            );
            this.logger.debug(`Trade ${id} updated to ${status}`);
        } catch (e) {
            this.logger.error(`Failed to update trade ${id}: ${e.message}`);
        }
    }

    /**
     * Closes the database connection.
     * @returns {Promise<void>} A promise that resolves when the connection is closed.
     */
    async close() {
        if (this.db) {
            await this.db.close();
            this.logger.info('Database connection closed.');
        }
    }
}

module.exports = SQLiteManager;
