import express from 'express';
import http from 'http';
import { Server as SocketIoServer } from 'socket.io';
import path from 'path';
import { logger } from '../logger.js';

/**
 * @class Dashboard
 * @description Manages a web-based dashboard for real-time bot monitoring.
 * It sets up an Express server to serve static files and a Socket.IO server for data updates.
 */
class Dashboard {
    /**
     * @constructor
     * @description Initializes the Dashboard, setting up Express and Socket.IO servers.
     * @param {Object} config - The configuration object, specifically `config.dashboard`.
     */
    constructor(config) {
        this.config = config.dashboard;
        if (!this.config.enabled) return;

        this.app = express();
        this.server = http.createServer(this.app);
        this.io = new SocketIoServer(this.server);
        this.port = this.config.port;
    }

    /**
     * @method start
     * @description Starts the Express and Socket.IO servers, serving the dashboard HTML and listening for connections.
     * @returns {void}
     */
    start() {
        if (!this.config.enabled) return;

        // Serve static files from the 'public' directory relative to the project root
        // Assuming 'public' is at the same level as 'utils'
        const publicPath = path.resolve(process.cwd(), 'public');
        this.app.use(express.static(publicPath));
        
        this.app.get('/', (req, res) => {
            res.sendFile(path.join(publicPath, 'dashboard.html'));
        });

        this.io.on('connection', (socket) => {
            logger.info('Dashboard client connected');
            socket.on('disconnect', () => {
                logger.info('Dashboard client disconnected');
            });
        });

        this.server.listen(this.port, () => {
            logger.info(`Dashboard running on http://localhost:${this.port}`);
        });
    }

    /**
     * @method update
     * @description Emits data to all connected dashboard clients via Socket.IO.
     * @param {Object} data - The data object to send to the dashboard.
     * @returns {void}
     */
    update(data) {
        if (this.config.enabled) {
            this.io.emit('update', data);
        }
    }
}

export default Dashboard;