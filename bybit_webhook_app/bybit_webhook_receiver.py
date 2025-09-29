# bybit_webhook_receiver.py

# This application creates a web server to receive and display Bybit V5 webhook notifications.
# It uses Flask for the web server and Flask-SocketIO for real-time communication with the browser.

# --- 1. Import necessary libraries ---
import logging

from dotenv import load_dotenv
from flask import Flask
from flask_socketio import SocketIO

# --- 2. Basic Setup ---
# Load environment variables from .env file
load_dotenv()

# Initialize Flask app and SocketIO
app = Flask(__name__)
# It's recommended to set a secret key for session management, though not strictly required for this simple app.
app.config["SECRET_KEY"] = "your_very_secret_key_here!"
socketio = SocketIO(app)

# --- 3. Configure Logging ---
# Disable Flask's default logging to avoid duplicate messages.
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

# Set up a custom logger for our application.
app.logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)
app.logger.addHandler(handler)


# --- 4. HTML & JavaScript Frontend ---
# We embed the HTML, CSS (via TailwindCDN), and JavaScript directly into this file for simplicity.
# This creates a single, self-contained application.
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bybit Webhook Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.2/socket.io.js"></script>
    <style>
        /* Simple scrollbar styling for a better look */
        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-track { background: #1f2937; }
        ::-webkit-scrollbar-thumb { background: #4b5563; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #6b7280; }
        body { font-family: 'Inter', sans-serif; }
    </style>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Roboto+Mono&display=swap" rel="stylesheet">
</head>
<body class="bg-gray-900 text-gray-200">
    <div class="container mx-auto p-4 md:p-8">
        <header class="text-center mb-8">
            <h1 class="text-3xl md:text-4xl font-bold text-cyan-400">Bybit Real-Time Webhook Dashboard</h1>
            <p class="text-gray-400 mt-2">Listening for V5 API notifications...</p>
        </header>

        <!-- Setup Instructions -->
        <div class="bg-gray-800 border border-gray-700 rounded-lg p-6 mb-8">
            <h2 class="text-xl font-semibold mb-3 text-white">Setup Instructions</h2>
            <ol class="list-decimal list-inside space-y-2 text-gray-300">
                <li>Run this Python script on your machine.</li>
                <li>Expose this server to the internet using a tool like <a href="https://ngrok.com/" target="_blank" class="text-cyan-400 hover:underline">ngrok</a>: <code class="bg-gray-700 px-2 py-1 rounded-md text-sm">ngrok http 5000</code></li>
                <li>Copy the public URL provided by ngrok (e.g., <code class="bg-gray-700 px-2 py-1 rounded-md text-sm">https://random-string.ngrok-free.app</code>).</li>
                <li>
                    <div class="flex items-center flex-wrap gap-2">
                        <span>Your full webhook URL is:</span>
                        <input id="webhook-url" type="text" readonly class="bg-gray-900 border border-gray-600 rounded-md px-3 py-1.5 text-gray-200 flex-grow" value="https://<your-ngrok-url>/webhook">
                        <button onclick="copyUrl()" class="bg-cyan-500 hover:bg-cyan-600 text-white font-bold py-2 px-4 rounded-md transition-colors">Copy</button>
                    </div>
                </li>
                <li>Go to your <a href="https://www.bybit.com/app/user/api-management" target="_blank" class="text-cyan-400 hover:underline">Bybit API Management</a> page, find your V5 API key, and click "Edit".</li>
                <li>Paste the URL into the "Webhook URL" field and select the events you want to subscribe to (e.g., Order, Position).</li>
            </ol>
        </div>

        <!-- Real-time Log Display -->
        <div class="bg-gray-800 rounded-lg shadow-lg">
            <div class="flex justify-between items-center bg-gray-700 p-4 rounded-t-lg border-b border-gray-600">
                <h2 class="text-lg font-semibold text-white">Live Webhook Log</h2>
                <div class="flex items-center gap-4">
                    <div id="status-indicator" class="w-4 h-4 rounded-full bg-red-500" title="Disconnected"></div>
                    <button id="clear-log" class="bg-gray-600 hover:bg-red-700 text-white font-semibold py-1 px-3 rounded-md text-sm transition-colors">Clear Log</button>
                </div>
            </div>
            <div id="log-container" class="p-4 h-96 overflow-y-auto font-mono text-sm" style="font-family: 'Roboto Mono', monospace;">
                <!-- Webhook data will be inserted here -->
            </div>
        </div>
    </div>

    <script>
        // --- 5. JavaScript for Socket.IO connection and UI updates ---
        const logContainer = document.getElementById('log-container');
        const clearLogBtn = document.getElementById('clear-log');
        const statusIndicator = document.getElementById('status-indicator');
        const webhookUrlInput = document.getElementById('webhook-url');

        // Update the placeholder URL with the actual ngrok URL if available
        // In a real app, you might fetch this from the server. For now, it's a manual copy/paste guide.
        
        function copyUrl() {
            const url = webhookUrlInput.value;
            if (url.includes('<your-ngrok-url>')) {
                alert('Please replace "<your-ngrok-url>" with your actual ngrok URL first!');
                return;
            }
            navigator.clipboard.writeText(url).then(() => {
                alert('Webhook URL copied to clipboard!');
            }).catch(err => {
                alert('Failed to copy URL.');
                console.error('Clipboard copy failed:', err);
            });
        }

        // Connect to the Socket.IO server
        const socket = io();

        socket.on('connect', () => {
            console.log('Connected to server!');
            statusIndicator.classList.remove('bg-red-500');
            statusIndicator.classList.add('bg-green-500');
            statusIndicator.title = 'Connected';
            addLogMessage({ status: 'Connected to server via WebSocket.' }, 'status-connect');
        });

        socket.on('disconnect', () => {
            console.log('Disconnected from server.');
            statusIndicator.classList.remove('bg-green-500');
            statusIndicator.classList.add('bg-red-500');
            statusIndicator.title = 'Disconnected';
            addLogMessage({ status: 'Disconnected from server.' }, 'status-disconnect');
        });

        // Listen for new webhook data from the server
        socket.on('webhook_data', function(data) {
            console.log('Received webhook data:', data);
            addLogMessage(data, 'webhook');
        });
        
        // Listen for initial connection message
        socket.on('server_status', function(data) {
            console.log('Server status:', data);
            addLogMessage(data, 'status-info');
        });

        clearLogBtn.addEventListener('click', () => {
            logContainer.innerHTML = '';
            addLogMessage({ status: 'Log cleared.' }, 'status-info');
        });

        function addLogMessage(data, type) {
            const logEntry = document.createElement('div');
            const timestamp = new Date().toISOString();
            
            let contentHtml = '';
            let borderColor = 'border-gray-600';

            if (type === 'webhook') {
                borderColor = 'border-cyan-500';
                contentHtml = `<pre class="whitespace-pre-wrap break-all">${JSON.stringify(data, null, 2)}</pre>`;
            } else if (type === 'status-connect') {
                borderColor = 'border-green-500';
                contentHtml = `<p class="text-green-400">${data.status}</p>`;
            } else if (type === 'status-disconnect') {
                borderColor = 'border-red-500';
                contentHtml = `<p class="text-red-400">${data.status}</p>`;
            } else {
                borderColor = 'border-yellow-500';
                contentHtml = `<p class="text-yellow-400">${data.status}</p>`;
            }

            logEntry.className = `bg-gray-800 p-3 mb-3 rounded-md border-l-4 ${borderColor}`;
            logEntry.innerHTML = `
                <div class="text-xs text-gray-500 mb-2">${timestamp}</div>
                ${contentHtml}
            `;
            
            logContainer.prepend(logEntry);
        }
    </script>
</body>
</html>
"""
