import logger from './logger.js';
import express from 'express';
import { dirname } from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { spawn } from 'child_process';
import net from 'net'; // Import the net module

dotenv.config();

const app = express();
const __dirname = dirname(fileURLToPath(import.meta.url));

let latestDashboardData = {};
let engineProcess = null;

// Function to check if a port is available
function portIsAvailable(port) {
    return new Promise((resolve) => {
        const server = net.createServer();
        server.once('error', (err) => {
            if (err.code === 'EADDRINUSE') {
                resolve(false); // Port is in use
            } else {
                resolve(true); // Other error, assume available for now
            }
        });
        server.once('listening', () => {
            server.close(() => resolve(true)); // Port is available
        });
        server.listen(port);
    });
}

// Function to find a free port
async function findFreePort(startPort = 3000, endPort = 3100) {
    for (let port = startPort; port <= endPort; port++) {
        if (await portIsAvailable(port)) {
            return port;
        }
    }
    throw new Error(`No free port found between ${startPort} and ${endPort}`);
}

app.use(express.json());
app.use(express.static(__dirname));

app.post('/api/dashboard', (req, res) => {
    latestDashboardData = req.body;
    console.log(`[SERVER] Received update from Engine. Price: ${latestDashboardData.price}`);
    res.status(200).send({ status: 'OK' });
});

app.get('/api/dashboard', (req, res) => {
    res.json(latestDashboardData);
});

app.get('/', (req, res) => {
    res.sendFile(__dirname + '/index.html');
});

function startEngine(portToUse) {
    if (engineProcess) {
        console.log("Engine already running.");
        return;
    }

    console.log(`🚀 Starting Trading Engine (node engine.js) targeting port ${portToUse}...`);

    // Pass the chosen port to the engine if it needs it (e.g., for its API client)
    // Ensure engine.js is updated to use this port if necessary
    engineProcess = spawn('node', ['engine.js'], {
        stdio: ['inherit', 'pipe', 'pipe'],
        env: { ...process.env, PORT: portToUse.toString() } // Pass PORT to engine's environment
    });

    engineProcess.stdout.on('data', (data) => {
        process.stdout.write(`[ENGINE] ${data}`);
    });

    engineProcess.stderr.on('data', (data) => {
        process.stderr.write(`[ENGINE ERROR] ${data}`);
    });

    engineProcess.on('close', (code) => {
        console.log(`[SERVER] Trading Engine exited with code ${code}`);
        engineProcess = null;
    });

    engineProcess.on('error', (err) => {
        console.error(`[SERVER] Failed to start engine: ${err.message}`);
        engineProcess = null;
    });
}

function stopEngine() {
    if (engineProcess) {
        console.log("[SERVER] Stopping Trading Engine...");
        engineProcess.kill('SIGINT');
        engineProcess = null; // Reset engineProcess to null after killing
    }
}

// --- Server Startup ---
async function startServer() {
    try {
        const dynamicPort = await findFreePort();
        app.listen(dynamicPort, () => {
            console.log(`\n\n🚀 SERVER STARTED on http://localhost:${dynamicPort}`);
            console.log("-----------------------------------------");
            console.log("📃 Open your browser to the link above.");

            // Start engine, passing the determined port
            startEngine(dynamicPort);
        });
    } catch (error) {
        console.error(`[SERVER] Failed to start server: ${error.message}`);
        process.exit(1);
    }
}

startServer();

// Handle graceful shutdown
process.on('SIGINT', () => {
    console.log("\n[SERVER] SIGINT received. Shutting down...");
    stopEngine();
    // Optionally, you might want to close the Express server too, but typically SIGINT exits the process.
    process.exit(0);
});

process.on('SIGTERM', () => {
    console.log("\n[SERVER] SIGTERM received. Shutting down...");
    stopEngine();
    process.exit(0);
});
