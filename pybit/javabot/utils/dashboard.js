import express from 'express';
import http from 'http';
import { Server as SocketIoServer } from 'socket.io';
import path from 'path';
import { logger } from '../logger.js';

class Dashboard {
    constructor(config) {
        this.config = config.dashboard;
        if (!this.config.enabled) return;

        this.app = express();
        this.server = http.createServer(this.app);
        this.io = new SocketIoServer(this.server);
        this.port = this.config.port;
    }

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

    update(data) {
        if (this.config.enabled) {
            this.io.emit('update', data);
        }
    }
}

export default Dashboard;
