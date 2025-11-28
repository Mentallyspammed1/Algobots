// server.js
import express from 'express';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import dotenv from 'dotenv';
import { exec } from 'child_process';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 3000;
const __dirname = dirname(fileURLToPath(import.meta.url));

let latestDashboardData = {};
let engineProcess = null;

app.use(express.json());
app.use(express.static(__dirname));

// --- Dashboard push from engine ---
app.post('/api/dashboard', (req, res) => {
  latestDashboardData = req.body || {};
  if (latestDashboardData.price) {
    console.log(
      `[SERVER] Engine update: Price=${latestDashboardData.price}, WSS=${latestDashboardData.wss}, Action=${latestDashboardData.wss_action}`
    );
  }
  res.status(200).json({ status: 'OK' });
});

app.get('/api/dashboard', (req, res) => {
  res.json(latestDashboardData);
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'OK',
    engineRunning: !!engineProcess && !engineProcess.killed,
    hasData: Object.keys(latestDashboardData).length > 0,
    timestamp: Date.now()
  });
});

app.get('/', (req, res) => {
  res.sendFile(join(__dirname, 'index.html'));
});

// --- Engine startup ---
function startEngine() {
  console.log('🚀 Starting Trading Engine (npm run trade)...');
  engineProcess = exec('npm run trade', (error, stdout, stderr) => {
    if (error) {
      console.error(`[ENGINE ERROR] ${error.message}`);
      return;
    }
    if (stderr) console.error(`[ENGINE STDERR]\n${stderr}`);
    if (stdout) console.log(`[ENGINE STDOUT}\n${stdout}`);
  });

  if (engineProcess && engineProcess.pid) {
    console.log(`📈 Trading Engine PID: ${engineProcess.pid}`);
  }
}

// --- Graceful shutdown ---
process.on('SIGINT', () => {
  console.log('\n[SERVER] SIGINT received. Shutting down...');
  if (engineProcess && !engineProcess.killed) engineProcess.kill('SIGINT');
  process.exit(0);
});

process.on('SIGTERM', () => {
  console.log('[SERVER] SIGTERM received. Shutting down...');
  if (engineProcess && !engineProcess.killed) engineProcess.kill('SIGTERM');
  process.exit(0);
});

// --- Start everything ---
app.listen(PORT, () => {
  console.log(`\n\n🚀 SERVER STARTED on http://localhost:${PORT}`);
  console.log('-----------------------------------------');
  console.log('📃 Open your browser to the link above.');
  console.log('🚀 Engine will start in 5 seconds...');
  setTimeout(startEngine, 5000);
});
