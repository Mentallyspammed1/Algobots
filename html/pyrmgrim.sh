Okay, Master Pyrmethus! Your wish is my command. This bash script will conjure the entire Grimoire project structure, complete with all frontend and backend files, into a new directory.

It uses `mkdir` to create directories and `cat << 'EOF' > filename` to write the content of each file. The `'EOF'` prevents shell variable expansion within the code blocks, ensuring your Python and HTML are written exactly as intended.

---

### **Bash Script: Conjure Grimoire Project**

```bash
#!/bin/bash

# --- Configuration ---
PROJECT_NAME="pyrmethus_grimoire"
BYBIT_API_KEY_PLACEHOLDER="YOUR_BYBIT_API_KEY"
BYBIT_API_SECRET_PLACEHOLDER="YOUR_BYBIT_API_SECRET"
GEMINI_API_KEY_PLACEHOLDER="YOUR_GOOGLE_GEMINI_API_KEY"

# --- Create Project Directory Structure ---
echo "Creating project directory: $PROJECT_NAME"
mkdir -p "$PROJECT_NAME/backend"

# --- Navigate into Project Directory ---
cd "$PROJECT_NAME" || { echo "Failed to enter $PROJECT_NAME directory. Exiting."; exit 1; }

echo "Creating frontend file: index.html"
cat << 'EOF' > index.html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Advanced cryptocurrency trading bot with AI-powered insights" />
  <title>Pyrmethus’s Neon Bybit Bot Grimoire</title>

  <!-- Tailwind v3 CDN with plugins -->
  <script src="https://cdn.tailwindcss.com?plugins=typography,forms"></script>
  <script>
    tailwind.config = {
      safelist: [
        { pattern: /^(bg|text|border|glow|from|to|via)-(red|green|blue|purple|pink|cyan|yellow|fuchsia|slate|indigo|lime|teal|emerald|orange|violet)-(300|400|500|600|700)$/ },
        { pattern: /^animate-(pulse|spin|bounce|ping)$/ }
      ]
    }
  </script>

  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet" />

  <!-- Socket.IO Client -->
  <script src="https://cdn.socket.io/4.0.0/socket.io.min.js"></script>

  <style>
    /* ---------- CSS Variables ---------- */
    :root {
      --c-bg-dark: #020617; --c-text-dark: #E2E8F0;
      --c-bg-light: #F8FAFC; --c-text-light: #1E293B;
      --c-bg-900: #0F172A; --c-bg-800: #1E293B; --c-bg-700: #334155;
      --c-slate-200: #E2E8F0; --c-slate-400: #94A3B8; --c-slate-600: #475569;
      --c-purple: #A855F7; --c-pink: #EC4899; --c-green: #10B981; --c-cyan: #06B6D4;
      --c-red: #EF4444; --c-yellow: #F59E0B; --c-blue: #3B82F6;
    }

    /* Base styles */
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { 
      font-family: 'Inter', system-ui, sans-serif; 
      background: var(--c-bg-dark); 
      color: var(--c-text-dark);
      transition: all 0.3s ease;
      position: relative;
      min-height: 100vh;
    }
    
    /* Light theme */
    [data-theme="light"] body { background: var(--c-bg-light); color: var(--c-text-light); }
    [data-theme="light"] section { background: #FFFFFF; border-color: #E5E7EB; box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1); }
    [data-theme="light"] #logArea { background: #F9FAFB; border-color: #E5E7EB; }
    [data-theme="light"] .input-field { background: #F9FAFB; color: #1F2937; border-color: #D1D5DB; }
    [data-theme="light"] .metric-card { background: #F9FAFB; border-color: #E5E7EB; }
    [data-theme="light"] .connection-status { background: rgba(255,255,255,0.8); border-color: #D1D5DB; color: var(--c-text-light); }
    [data-theme="light"] .toast { background: #FFFFFF; color: var(--c-text-light); border-color: #D1D5DB; }
    [data-theme="light"] .kbd { background: #F3F4F6; border-color: #D1D5DB; color: var(--c-text-light); }
    [data-theme="light"] .modal-content { background: #FFFFFF; border-color: #D1D5DB; color: var(--c-text-light); }


    /* Animated background */
    @keyframes float {
      0%, 100% { transform: translateY(0) rotate(0deg); }
      50% { transform: translateY(-20px) rotate(1deg); }
    }
    
    .bg-particles {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image: 
        radial-gradient(circle at 20% 50%, rgba(168, 85, 247, 0.05) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(236, 72, 153, 0.05) 0%, transparent 50%);
      pointer-events: none;
      z-index: -1;
      animation: float 30s ease-in-out infinite;
    }

    /* Neon effects */
    .neon-text-glow { 
      text-shadow: 0 0 10px currentColor, 0 0 20px currentColor, 0 0 30px currentColor;
      animation: pulse-glow 2s ease-in-out infinite;
    }
    @keyframes pulse-glow {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.8; }
    }

    /* Glow utilities */
    .glow-purple { box-shadow: 0 0 10px var(--c-purple), 0 0 20px var(--c-purple); }
    .glow-pink { box-shadow: 0 0 10px var(--c-pink), 0 0 20px var(--c-pink); }
    .glow-green { box-shadow: 0 0 10px var(--c-green), 0 0 20px var(--c-green); }
    .glow-red { box-shadow: 0 0 10px var(--c-red), 0 0 20px var(--c-red); }

    /* Enhanced buttons */
    .btn {
      position: relative;
      overflow: hidden;
      transition: all 0.3s;
    }
    .btn::before {
      content: '';
      position: absolute;
      top: 50%; left: 50%;
      width: 0; height: 0;
      background: rgba(255, 255, 255, 0.2);
      border-radius: 50%;
      transform: translate(-50%, -50%);
      transition: all 0.6s;
    }
    .btn:active::before {
      width: 300px; height: 300px;
    }

    /* Input styles */
    .input-field {
      background: var(--c-bg-700);
      color: var(--c-text-dark);
      border: 1px solid var(--c-slate-600);
      padding: 0.5rem;
      border-radius: 0.375rem;
      transition: all 0.2s;
      width: 100%;
    }
    .input-field:focus {
      outline: none;
      border-color: var(--c-purple);
      box-shadow: 0 0 0 3px rgba(168, 85, 247, 0.1);
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: var(--c-bg-900); }
    ::-webkit-scrollbar-thumb { 
      background: var(--c-slate-600); 
      border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover { background: var(--c-slate-400); }

    /* Log area */
    .scrollable-log {
      max-height: 400px;
      overflow-y: auto;
      scroll-behavior: smooth;
    }

    /* Log entries */
    .log-entry {
      padding: 4px 12px;
      margin: 2px 0;
      border-left: 3px solid transparent;
      border-radius: 0 4px 4px 0;
      font-variant-numeric: tabular-nums;
      transition: all 0.2s;
      font-size: 0.875rem;
      position: relative;
    }
    .log-entry:hover { 
      background: rgba(255, 255, 255, 0.05); 
      transform: translateX(2px);
    }
    .log-entry.success { border-left-color: #10B981; color: #86EFAC; }
    .log-entry.info { border-left-color: #06B6D4; color: #67E8F9; }
    .log-entry.warning { border-left-color: #F59E0B; color: #FACC15; }
    .log-entry.error { border-left-color: #EF4444; color: #F87171; }
    .log-entry.signal { border-left-color: #EC4899; color: #EC4899; }
    .log-entry.llm { border-left-color: #A855F7; color: #A855F7; }

    /* Spinner */
    @keyframes spin { to { transform: rotate(360deg); } }
    .spinner {
      display: inline-block;
      width: 16px; height: 16px;
      border: 2px solid rgba(255, 255, 255, 0.1);
      border-left-color: var(--c-purple);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-left: 8px;
      vertical-align: middle;
    }

    /* Metric cards */
    .metric-card {
      background: var(--c-bg-900);
      border: 2px solid var(--c-slate-600);
      border-radius: 0.75rem;
      padding: 1rem;
      transition: all 0.3s;
      position: relative;
      overflow: hidden;
    }
    .metric-card::before {
      content: '';
      position: absolute;
      inset: -2px;
      background: linear-gradient(45deg, transparent, var(--glow-color, var(--c-purple)), transparent);
      opacity: 0;
      transition: opacity 0.3s;
      z-index: -1;
      border-radius: 0.75rem;
    }
    .metric-card:hover::before { opacity: 0.2; }
    .metric-card:hover { transform: translateY(-2px); }

    /* Connection status */
    .connection-status {
      position: fixed;
      top: 1rem;
      right: 1rem;
      padding: 0.5rem 1rem;
      border-radius: 2rem;
      font-size: 0.75rem;
      font-weight: 500;
      backdrop-filter: blur(10px);
      transition: all 0.3s;
      z-index: 100;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .connection-status.connected {
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: #10B981;
    }
    .connection-status.polling {
      background: rgba(245, 158, 11, 0.1);
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: #F59E0B;
    }
    .connection-status.disconnected {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: #EF4444;
    }

    /* Toast notifications */
    #toastContainer {
      position: fixed;
      bottom: 2rem;
      right: 2rem;
      z-index: 10000;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      pointer-events: none; /* Allow clicks to pass through */
    }
    .toast {
      background: var(--c-bg-800);
      color: var(--c-text-dark);
      padding: 1rem 1.5rem;
      border-radius: 0.5rem;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
      transform: translateX(100%);
      opacity: 0;
      transition: transform 0.3s ease-out, opacity 0.3s ease-out;
      max-width: 320px;
      border: 1px solid var(--c-slate-600);
      pointer-events: auto; /* Re-enable pointer events for the toast itself */
    }
    .toast.show { transform: translateX(0); opacity: 1; }
    .toast.success { border-color: #10B981; }
    .toast.error { border-color: #EF4444; }
    .toast.warning { border-color: #F59E0B; }
    .toast.info { border-color: #3B82F6; }

    /* Keyboard shortcuts hint */
    .kbd {
      background: var(--c-bg-800);
      border: 1px solid var(--c-slate-600);
      border-radius: 0.25rem;
      padding: 0.125rem 0.375rem;
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
    }

    /* Modal */
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.3s;
    }
    .modal.active {
      opacity: 1;
      pointer-events: auto;
    }
    .modal-content {
      background: var(--c-bg-800);
      border: 1px solid var(--c-slate-600);
      border-radius: 0.75rem;
      padding: 2rem;
      max-width: 500px;
      width: 90%;
      max-height: 90vh;
      overflow-y: auto;
      transform: scale(0.9);
      transition: transform 0.3s;
    }
    .modal.active .modal-content {
      transform: scale(1);
    }

    /* Collapsible sections */
    .collapsible {
      overflow: hidden;
      transition: max-height 0.3s ease;
    }
    .collapsible.collapsed {
      max-height: 0 !important;
    }

    /* Search highlight */
    .highlight {
      background: rgba(250, 204, 21, 0.3);
      border-radius: 2px;
    }

    /* Loading skeleton */
    @keyframes skeleton-loading {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
    .skeleton {
      background: linear-gradient(90deg, var(--c-bg-800) 25%, var(--c-bg-900) 50%, var(--c-bg-800) 75%);
      background-size: 200% 100%;
      animation: skeleton-loading 1.5s infinite;
      border-radius: 0.25rem;
    }

    /* Mobile optimizations */
    @media (max-width: 768px) {
      .metric-card { padding: 0.75rem; }
      .log-entry { font-size: 0.75rem; padding: 2px 8px; }
      .connection-status { top: 0.5rem; right: 0.5rem; font-size: 0.625rem; }
      #toastContainer { bottom: 1rem; right: 1rem; left: 1rem; max-width: none; }
    }

    /* Accessibility */
    @media (prefers-reduced-motion: reduce) {
      *, *::before, *::after {
        animation-duration: 0.01ms !important;
        transition-duration: 0.01ms !important;
      }
    }

    /* Print styles */
    @media print {
      body { background: white; color: black; }
      .no-print { display: none !important; }
      .metric-card { break-inside: avoid; }
    }
  </style>
</head>

<body>
  <div class="bg-particles"></div>
  
  <!-- Connection Status Indicator -->
  <div id="connectionStatus" class="connection-status disconnected no-print">
    <span class="status-icon">●</span>
    <span class="status-text">Disconnected</span>
  </div>

  <main class="max-w-6xl mx-auto p-4 md:p-8 space-y-8">

    <!-- ---------- HEADER ---------- -->
    <header class="text-center space-y-4 mb-8 select-none">
      <h1 class="text-4xl md:text-5xl font-bold text-transparent bg-clip-text
                 bg-gradient-to-r from-purple-500 via-pink-500 to-green-400
                 neon-text-glow">
        Pyrmethus’s Neon Grimoire
      </h1>
      <p class="text-lg text-slate-400">Transcending market chaos through algorithmic sorcery</p>
      
      <!-- Control buttons -->
      <div class="flex flex-wrap justify-center gap-3 mt-4">
        <button id="themeToggle" class="btn px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm"
                aria-label="Toggle theme">
          <span class="theme-icon">🌙</span> <span class="theme-text">Dark Mode</span>
        </button>
        <button id="soundToggle" class="btn px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm"
                aria-label="Toggle sounds">
          <span class="sound-icon">🔊</span> <span class="sound-text">Sounds On</span>
        </button>
        <button id="keyboardShortcuts" class="btn px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm"
                aria-label="Show keyboard shortcuts">
          ⌨️ Shortcuts
        </button>
      </div>
    </header>

    <!-- ---------- CONFIGURATION ---------- -->
    <section class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-purple-600 transition-all">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-2xl font-bold text-purple-400">Configuration</h2>
        <button id="collapseConfig" class="text-slate-400 hover:text-slate-200" aria-label="Toggle section">
          <svg class="w-6 h-6 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
          </svg>
        </button>
      </div>
      
      <div id="configContent" class="collapsible" style="max-height: 1000px;">
        <p class="text-sm text-slate-500 mb-4">
          <strong class="text-red-400">⚠️ WARNING:</strong> API keys are transmitted to the backend. Ensure HTTPS and secure storage.
        </p>
        
        <div class="grid md:grid-cols-2 gap-4">
          <div>
            <label for="symbol" class="block text-sm font-medium mb-1">Trading Symbol</label>
            <select id="symbol" class="input-field">
              <option value="BTCUSDT" selected>BTCUSDT</option>
              <option value="ETHUSDT">ETHUSDT</option>
              <option value="SOLUSDT">SOLUSDT</option>
              <option value="TRUMPUSDT">TRUMPUSDT</option>
              <option value="BNBUSDT">BNBUSDT</option>
              <option value="XRPUSDT">XRPUSDT</option>
            </select>
          </div>
          <div>
            <label for="interval" class="block text-sm font-medium mb-1">Interval</label>
            <select id="interval" class="input-field">
              <option value="1">1 min</option>
              <option value="5">5 min</option>
              <option value="15">15 min</option>
              <option value="30">30 min</option>
              <option value="60" selected>1 hour</option>
              <option value="240">4 hours</option>
              <option value="D">1 day</option>
            </select>
          </div>
        </div>
        
        <div id="numericFields" class="grid md:grid-cols-2 gap-4 mt-4"></div>
        
        <template id="numberInputTemplate">
          <div>
            <label class="block text-sm font-medium mb-1"></label>
            <input type="number" class="input-field" />
          </div>
        </template>
        
        <div class="flex flex-col sm:flex-row gap-4 mt-6">
          <button id="startBot" class="btn flex-1 py-3 rounded-lg bg-gradient-to-r from-purple-500 to-pink-500 glow-purple font-bold transition-transform hover:scale-105" aria-live="polite">
            <span id="buttonText">Start the Bot</span>
          </button>
          <button id="copyConfig" class="btn px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300" title="Copy configuration">
            📋 Copy
          </button>
          <button id="importConfig" class="btn px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300" title="Import configuration">
            📂 Import
          </button>
          <button id="resetConfig" class="btn px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300" title="Reset to defaults">
            🔄 Reset
          </button>
        </div>
      </div>
    </section>

    <!-- ---------- DASHBOARD ---------- -->
    <section class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-green-600 transition-all">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-2xl font-bold text-green-400">Live Dashboard</h2>
        <button id="refreshDashboard" class="text-slate-400 hover:text-slate-200" aria-label="Refresh dashboard">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
      </div>
      
      <div id="metricsGrid" class="grid grid-cols-2 md:grid-cols-4 gap-4 text-center"></div>
      
      <div class="mt-6 flex flex-col sm:flex-row gap-4">
        <button id="askGemini" class="btn flex-1 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-purple-300 font-bold" aria-live="polite">
          ✨ Ask Gemini for Market Insight
        </button>
        <button id="exportLogs" class="btn flex-1 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-blue-300 font-bold">
          📊 Export Trading Logs
        </button>
      </div>
      
      <p class="mt-4 text-xs text-slate-500 text-right">
        Last update: <span id="lastUpdate">—</span>
      </p>
    </section>

    <!-- ---------- LOGS ---------- -->
    <section class="bg-slate-800 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-blue-600 transition-all">
      <div class="flex justify-between items-center mb-4">
        <h2 class="text-2xl font-bold text-blue-400">Ritual Log</h2>
        <div class="flex items-center gap-4">
          <input type="search" id="logSearch" placeholder="Search logs..." 
                 class="input-field text-sm w-48 hidden md:block" />
          <select id="logFilter" class="input-field text-sm w-32">
            <option value="">All Types</option>
            <option value="success">Success</option>
            <option value="info">Info</option>
            <option value="warning">Warning</option>
            <option value="error">Error</option>
            <option value="signal">Signal</option>
            <option value="llm">LLM</option>
          </select>
          <button id="clearLogs" class="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm">
            Clear
          </button>
        </div>
      </div>
      
      <div id="logArea" class="bg-slate-900 p-4 rounded-lg scrollable-log text-xs font-mono" 
           aria-live="polite" aria-atomic="false">
        <div class="log-entry info">Awaiting your command, Master Pyrmethus…</div>
      </div>
      
      <div class="mt-4 flex justify-between items-center text-xs text-slate-500">
        <span>Total logs: <span id="logCount">1</span></span>
        <span>Filtered: <span id="filteredLogCount">1</span></span>
      </div>
    </section>
  </main>

  <!-- ---------- MODALS ---------- -->
  <!-- Keyboard Shortcuts Modal -->
  <div id="shortcutsModal" class="modal">
    <div class="modal-content">
      <h3 class="text-xl font-bold mb-4">Keyboard Shortcuts</h3>
      <div class="space-y-2 text-sm">
        <div class="flex justify-between">
          <span>Start/Stop Bot</span>
          <kbd class="kbd">Ctrl + Enter</kbd>
        </div>
        <div class="flex justify-between">
          <span>Toggle Theme</span>
          <kbd class="kbd">Ctrl + D</kbd>
        </div>
        <div class="flex justify-between">
          <span>Export Logs</span>
          <kbd class="kbd">Ctrl + E</kbd>
        </div>
        <div class="flex justify-between">
          <span>Search Logs</span>
          <kbd class="kbd">Ctrl + F</kbd>
        </div>
        <div class="flex justify-between">
          <span>Copy Config</span>
          <kbd class="kbd">Ctrl + C</kbd>
        </div>
        <div class="flex justify-between">
          <span>Import Config</span>
          <kbd class="kbd">Ctrl + I</kbd>
        </div>
        <div class="flex justify-between">
          <span>Refresh Dashboard</span>
          <kbd class="kbd">F5</kbd>
        </div>
      </div>
      <button class="mt-6 w-full py-2 rounded bg-slate-700 hover:bg-slate-600" onclick="closeModal('shortcutsModal')">
        Close
      </button>
    </div>
  </div>

  <!-- Toast Container -->
  <div id="toastContainer"></div>

  <!-- ---------- AUDIO ---------- -->
  <audio id="notificationSound" preload="auto">
    <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtjMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBi2Gy/DUdw0..." type="audio/wav">
  </audio>

  <script>
    // Enhanced configuration
    const APP_CONFIG = {
      VERSION: '2.0.0',
      SOUNDS_ENABLED_KEY: 'pyrmethus_sounds_enabled',
      THEME_KEY: 'pyrmethus_theme',
      CONFIG_DRAFT_KEY: 'pyrmethus_config_draft',
      RECONNECT_DELAY: 5000,
      MAX_LOG_ENTRIES: 1000,
      NOTIFICATION_DURATION: 5000,
      BACKEND_URL: 'http://127.0.0.1:5000' // Default backend URL
    };

    document.addEventListener('DOMContentLoaded', () => {
      /* ========================= UTILITIES ========================= */
      const $ = (selector, context = document) => context.querySelector(selector);
      const $$ = (selector, context = document) => [...context.querySelectorAll(selector)];
      const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
      const debounce = (func, wait) => {
        let timeout;
        return (...args) => {
          clearTimeout(timeout);
          timeout = setTimeout(() => func.apply(this, args), wait);
        };
      };

      // Sound system
      const SoundManager = {
        enabled: localStorage.getItem(APP_CONFIG.SOUNDS_ENABLED_KEY) !== 'false',
        audio: $('#notificationSound'),
        play(type = 'default') {
          if (this.enabled && this.audio) {
            this.audio.currentTime = 0;
            this.audio.volume = 0.3;
            this.audio.play().catch(() => {});
          }
        },
        toggle() {
          this.enabled = !this.enabled;
          localStorage.setItem(APP_CONFIG.SOUNDS_ENABLED_KEY, this.enabled);
          updateSoundButton();
        }
      };

      // Toast notification system
      const Toast = {
        show(message, type = 'info', duration = APP_CONFIG.NOTIFICATION_DURATION) {
          const toast = document.createElement('div');
          toast.className = `toast ${type}`;
          toast.innerHTML = `
            <div class="flex items-center justify-between">
              <span>${message}</span>
              <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-slate-400 hover:text-slate-200">✕</button>
            </div>
          `;
          $('#toastContainer').appendChild(toast);
          requestAnimationFrame(() => toast.classList.add('show'));
          
          if (type === 'error' || type === 'success') {
            SoundManager.play(type);
          }
          
          setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300);
          }, duration);
        }
      };

      // Enhanced logger (frontend side)
      const log = (() => {
        const area = $('#logArea');
        let logs = []; // Store logs for filtering/search
        let currentLogId = 0; // Unique ID for each log entry

        return (message, type = 'info', timestamp_ms = Date.now(), fromBackend = false) => {
          const timestamp = new Date(timestamp_ms);
          const timeStr = timestamp.toLocaleTimeString();
          
          // Only assign new ID if not from backend (backend logs already have unique timestamps)
          const entryId = fromBackend ? timestamp_ms : ++currentLogId;

          const entry = { message, type, timestamp_ms, id: entryId };
          
          // Check for duplicates if from backend (to avoid adding the same log twice on WS reconnect)
          if (fromBackend && logs.some(l => l.timestamp_ms === timestamp_ms && l.message === message)) {
            return;
          }

          logs.push(entry);
          if (logs.length > APP_CONFIG.MAX_LOG_ENTRIES) {
            logs.shift();
            // Remove the oldest log entry from DOM if it exists
            const oldestDomLog = area.querySelector('.log-entry:first-child');
            if (oldestDomLog) oldestDomLog.remove();
          }
          
          const div = document.createElement('div');
          div.className = `log-entry ${type}`;
          div.dataset.type = type;
          div.dataset.timestamp = timestamp.toISOString();
          div.dataset.originalText = message; // Store original message for search/filter
          div.innerHTML = `<span class="text-slate-500 mr-2">[${timeStr}]</span><span>${escapeHtml(message)}</span>`;
          area.appendChild(div);
          
          requestAnimationFrame(() => {
            area.scrollTop = area.scrollHeight;
            updateLogCounts();
            filterLogs(); // Re-apply filters/search
          });
          
          return entry;
        };
      })();

      // HTML escape function
      function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
      }

      // Abortable fetch with timeout and exponential backoff retry.
      async function fetchWithRetry(url, options = {}, retries = 3, delay = 1000, timeout = 8000) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        for (let i = 0; i < retries; i++) {
          try {
            const response = await fetch(url, { 
              ...options, 
              signal: controller.signal,
              headers: {
                'Content-Type': 'application/json',
                ...options.headers
              }
            });
            clearTimeout(timeoutId);
            
            if (!response.ok) {
              const errorJson = await response.json().catch(() => ({message: response.statusText}));
              throw new Error(`HTTP ${response.status}: ${errorJson.message || response.statusText}`);
            }
            
            return response;
          } catch (error) {
            clearTimeout(timeoutId);
            
            if (i === retries - 1) throw error;
            
            const nextDelay = delay * Math.pow(2, i); // Exponential backoff
            log(`Fetch failed: ${error.message}. Retrying in ${nextDelay}ms...`, 'warning');
            await new Promise(resolve => setTimeout(resolve, nextDelay));
          }
        }
      }

      /* ========================= CONSTANTS ========================= */
      // Allow backend URL override via ?api=, window.BACKEND_URL, or default.
      const BACKEND_URL = new URLSearchParams(window.location.search).get('api') || 
                          window.BACKEND_URL || 
                          APP_CONFIG.BACKEND_URL;

      // Configuration for dynamically generated numeric input fields [id, label, default, min, max, step]
      const NUM_FIELDS = [
        ['leverage', 'Leverage', 10, 1, 100, 1],
        ['riskPct', 'Risk % per Trade', 1, 0.1, 10, 0.1],
        ['stopLossPct', 'Stop Loss %', 2, 0.1, 10, 0.1],
        ['takeProfitPct', 'Take Profit %', 5, 0.1, 20, 0.1],
        ['efPeriod', 'Ehlers-Fisher Period', 10, 1, 50, 1],
        ['macdFastPeriod', 'MACD Fast Period', 12, 2, 100, 1],
        ['macdSlowPeriod', 'MACD Slow Period', 26, 2, 100, 1],
        ['macdSignalPeriod', 'MACD Signal Period', 9, 1, 100, 1],
        ['bbPeriod', 'Bollinger Bands Period', 20, 2, 100, 1],
        ['bbStdDev', 'Bollinger Bands Std Dev', 2, 0.1, 5, 0.1],
      ];

      // Configuration for dynamically generated dashboard metrics [label, id, colorClass, glowColorVar]
      const METRICS = [
        ['Current Price', 'currentPrice', 'text-cyan-400', '--c-cyan'],
        ['Price Change', 'priceChange', 'text-slate-500'],
        ['Supertrend', 'stDirection', 'text-fuchsia-400', '--c-purple'],
        ['ST Value', 'stValue', 'text-slate-500'],
        ['RSI', 'rsiValue', 'text-yellow-400', '--c-yellow'],
        ['RSI Status', 'rsiStatus', 'text-slate-500'],
        ['Position', 'currentPosition', 'text-pink-400', '--c-pink'],
        ['Position PnL', 'positionPnL', 'text-slate-500'],
        ['Balance', 'accountBalance', 'text-blue-400', '--c-blue'],
        ['Ehlers-Fisher', 'fisherValue', 'text-purple-400'],
        ['MACD Line', 'macdLine', 'text-indigo-400'],
        ['MACD Signal', 'macdSignal', 'text-blue-400'],
        ['MACD Hist', 'macdHistogram', 'text-cyan-400'],
        ['BB Middle', 'bbMiddle', 'text-green-400'],
        ['BB Upper', 'bbUpper', 'text-lime-400'],
        ['BB Lower', 'bbLower', 'text-teal-400'],
        ['Total Trades', 'totalTrades', 'text-emerald-400'],
        ['Win Rate', 'winRate', 'text-orange-400'],
        ['Bot Status', 'botStatus', 'text-violet-400'],
      ];

      /* ==================== DYNAMIC DOM CREATION =================== */
      const numericFieldsContainer = $('#numericFields');
      const template = $('#numberInputTemplate').content;
      
      NUM_FIELDS.forEach(([id, label, def, min, max, step]) => {
        const clone = template.cloneNode(true);
        const labelEl = clone.querySelector('label');
        const inputEl = clone.querySelector('input');
        labelEl.htmlFor = id;
        labelEl.textContent = label;
        Object.assign(inputEl, { id, value: def, min, max, step });
        
        // Add input validation
        inputEl.addEventListener('input', (e) => {
          const value = parseFloat(e.target.value);
          if (!isNaN(value)) {
            e.target.value = clamp(value, min, max);
          }
        });
        
        numericFieldsContainer.appendChild(clone);
      });

      // Create metric cards
      const metricsGrid = $('#metricsGrid');
      METRICS.forEach(([label, id, colorClass, glowColorVar]) => {
        const card = document.createElement('div');
        card.className = 'metric-card';
        if (glowColorVar) card.style.setProperty('--glow-color', `var(${glowColorVar})`);
        card.innerHTML = `
          <p class="text-xs sm:text-sm text-slate-400">${label}</p>
          <p id="${id}" class="text-lg sm:text-xl font-bold ${colorClass} mt-1">
            <span class="skeleton" style="display: inline-block; width: 60px; height: 1.5em;"></span>
          </p>
        `;
        metricsGrid.appendChild(card);
      });

      /* ========================= STATE MANAGEMENT ======================== */
      let botRunning = false;
      let socket = null;
      let lastLogTimestamp = 0; // To prevent log duplication from initial fetch

      /* ========================= THEME & UI ======================== */
      const applyTheme = (theme) => {
        document.documentElement.dataset.theme = theme;
        localStorage.setItem(APP_CONFIG.THEME_KEY, theme);
        updateThemeButton(theme);
      };

      const updateThemeButton = (theme) => {
        const icon = $('.theme-icon');
        const text = $('.theme-text');
        if (icon && text) {
          if (theme === 'light') {
            icon.textContent = '☀️';
            text.textContent = 'Light Mode';
          } else {
            icon.textContent = '🌙';
            text.textContent = 'Dark Mode';
          }
        }
      };

      const updateSoundButton = () => {
        const icon = $('.sound-icon');
        const text = $('.sound-text');
        if (icon && text) {
          if (SoundManager.enabled) {
            icon.textContent = '🔊';
            text.textContent = 'Sounds On';
          } else {
            icon.textContent = '🔇';
            text.textContent = 'Sounds Off';
          }
        }
      };

      /* ========================= CONNECTION STATUS ======================== */
      function updateConnectionStatus(status, details = '') {
        const statusEl = $('#connectionStatus');
        const icon = statusEl.querySelector('.status-icon');
        const text = statusEl.querySelector('.status-text');
        
        statusEl.className = 'connection-status no-print'; // Reset classes
        
        switch (status) {
          case 'connected':
            statusEl.classList.add('connected');
            icon.textContent = '●';
            text.textContent = 'Connected (WS)';
            break;
          case 'polling':
            statusEl.classList.add('polling');
            icon.textContent = '◐';
            text.textContent = 'Connected (Polling)';
            break;
          case 'disconnected':
            statusEl.classList.add('disconnected');
            icon.textContent = '○';
            text.textContent = details || 'Disconnected';
            break;
          case 'connecting':
            statusEl.classList.add('polling'); // Use polling style for connecting
            icon.textContent = '...';
            text.textContent = 'Connecting...';
            break;
        }
      }

      /* ========================= CONFIGURATION ======================== */
      function getConfig() {
        const config = {
          symbol: $('#symbol').value.toUpperCase(),
          interval: $('#interval').value,
        };
        
        NUM_FIELDS.forEach(([id, , def, min, max]) => {
          const input = $(`#${id}`);
          const value = parseFloat(input.value);
          config[id] = clamp(isNaN(value) ? parseFloat(input.defaultValue) : value, min, max);
          // Optionally correct invalid input in UI
          if (input.value != config[id]) input.value = config[id];
        });
        
        // Add static config items expected by backend (these are defaults in backend, but good to send)
        Object.assign(config, {
            supertrend_length: 10, 
            supertrend_multiplier: 3.0,
            rsi_length: 14, 
            rsi_overbought: 70, 
            rsi_oversold: 30,
        });
        
        return config;
      }

      function setConfig(config) {
        if (config.symbol) $('#symbol').value = config.symbol;
        if (config.interval) $('#interval').value = config.interval;
        
        NUM_FIELDS.forEach(([id, , def, min, max]) => {
          if (config[id] != null) {
            $(`#${id}`).value = clamp(config[id], min, max);
          }
        });
      }

      function saveDraftConfig() {
        localStorage.setItem(APP_CONFIG.CONFIG_DRAFT_KEY, JSON.stringify(getConfig()));
      }

      function loadDraftConfig() {
        try {
          const draft = localStorage.getItem(APP_CONFIG.CONFIG_DRAFT_KEY);
          if (draft) {
            setConfig(JSON.parse(draft));
            log('Draft configuration restored', 'info');
          }
        } catch (e) {
          console.error('Failed to load draft config:', e);
          Toast.show('Failed to load draft config.', 'error');
        }
      }

      /* ========================= BOT CONTROL ======================== */
      async function handleStartStop() {
        const btn = $('#startBot');
        const originalContent = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = `${botRunning ? 'Stopping...' : 'Starting...'}<span class="spinner"></span>`;

        try {
          if (botRunning) {
            await stopBot();
          } else {
            await startBot();
          }
        } finally {
          btn.disabled = false;
          btn.innerHTML = originalContent;
          updateButtonState();
        }
      }

      async function startBot() {
        try {
          const config = getConfig();
          const res = await fetchWithRetry(`${BACKEND_URL}/api/start`, {
            method: 'POST',
            body: JSON.stringify(config),
          });
          
          const data = await res.json();
          if (data.status === 'success') {
            log('Bot ritual initiated ✔️', 'success');
            Toast.show('Bot started successfully!', 'success');
            setRunningState(true);
            // WebSocket will connect automatically
          } else {
            throw new Error(data.message || 'Failed to start bot');
          }
        } catch (e) {
          log(`Error starting bot: ${e.message}`, 'error');
          Toast.show(`Failed to start bot: ${e.message}`, 'error');
        }
      }

      async function stopBot() {
        try {
          const res = await fetchWithRetry(`${BACKEND_URL}/api/stop`, { method: 'POST' });
          const data = await res.json();
          
          if (data.status === 'success') {
            log('Bot ritual paused ⏸️', 'warning');
            Toast.show('Bot stopped', 'warning');
            setRunningState(false);
          } else {
            throw new Error(data.message || 'Failed to stop bot');
          }
        } catch (e) {
          log(`Error stopping bot: ${e.message}`, 'error');
          Toast.show(`Failed to stop bot: ${e.message}`, 'error');
        }
      }

      function setRunningState(isRunning) {
        if (botRunning === isRunning) return;
        botRunning = isRunning;
        updateButtonState();
        $('#botStatus').textContent = isRunning ? 'Running' : 'Idle';
        
        if (!isRunning) {
          // No need to manually disconnect WS here, backend will handle its state
          // and WS will eventually close or send disconnected status
          updateConnectionStatus('disconnected');
        } else {
          // If starting, try to connect WS immediately
          connectWebSocket();
        }
      }

      function updateButtonState() {
        const btn = $('#startBot');
        const text = $('#buttonText');
        
        text.textContent = botRunning ? 'Stop the Bot' : 'Start the Bot';
        btn.classList.toggle('from-purple-500', !botRunning);
        btn.classList.toggle('to-pink-500', !botRunning);
        btn.classList.toggle('glow-purple', !botRunning);
        btn.classList.toggle('bg-red-600', botRunning);
        btn.classList.toggle('from-red-600', botRunning);
        btn.classList.toggle('to-red-700', botRunning);
        btn.classList.toggle('glow-red', botRunning);
      }

      /* ========================= WEBSOCKET & POLLING ======================== */
      function connectWebSocket() {
        if (socket && socket.connected) {
          return;
        }
        log('Attempting WebSocket connection...', 'info');
        updateConnectionStatus('connecting');

        // Ensure the namespace matches the backend
        socket = io(BACKEND_URL + '/ws/status', {
            reconnectionAttempts: 5,
            reconnectionDelay: 1000,
            reconnectionDelayMax: 5000,
            timeout: 10000
        });

        socket.on('connect', () => {
          log('WebSocket connected 📡', 'success');
          updateConnectionStatus('connected');
        });

        socket.on('disconnect', (reason) => {
          log(`WebSocket disconnected: ${reason}`, 'warning');
          updateConnectionStatus('disconnected', 'WS Disconnected');
          // If bot is supposed to be running, fall back to polling
          if (botRunning) {
            log('Bot is running, attempting to re-fetch status via polling.', 'info');
            fetchDashboardStatus(); // Fetch once, backend will keep sending
          }
        });

        socket.on('connect_error', (error) => {
          log(`WebSocket connection error: ${error.message}`, 'error');
          updateConnectionStatus('disconnected', 'WS Error');
        });

        socket.on('dashboard_update', (data) => {
          updateDashboard(data);
        });

        socket.on('log_entry', (logEntry) => {
          // Only add logs that haven't been added from the initial dashboard_update fetch
          if (logEntry.timestamp > lastLogTimestamp) {
            log(logEntry.message, logEntry.level, logEntry.timestamp, true); // true indicates fromBackend
            lastLogTimestamp = logEntry.timestamp;
          }
        });
      }

      // Fallback for initial status fetch if WS is not yet connected or fails
      async function fetchDashboardStatus() {
        try {
          const res = await fetchWithRetry(`${BACKEND_URL}/api/status`, {}, 1, 1000, 4000);
          const data = await res.json();
          updateDashboard(data);
          updateConnectionStatus('polling'); // Indicate we got data via polling
        } catch (e) {
          log(`Dashboard fetch failed: ${e.message}`, 'error');
          updateConnectionStatus('disconnected', 'Connection Error');
        }
      }

      function updateDashboard(data) {
        const dashboard = data.dashboard || {};
        
        METRICS.forEach(([_, id]) => {
          const el = $(`#${id}`);
          if (el) {
            const value = dashboard[id] ?? '---';
            const skeleton = el.querySelector('.skeleton');
            if (skeleton) skeleton.remove();
            el.textContent = value; // Backend sends pre-formatted values
          }
        });
        
        $('#lastUpdate').textContent = new Date().toLocaleTimeString();

        // Update logs from initial dashboard fetch, only new ones
        if (Array.isArray(data.logs)) {
          data.logs.forEach(logEntry => {
            if (logEntry.timestamp > lastLogTimestamp) {
              log(logEntry.message, logEntry.level, logEntry.timestamp, true); // true indicates fromBackend
              lastLogTimestamp = logEntry.timestamp;
            }
          });
        }

        // Sync bot running state
        if (typeof data.running === 'boolean') {
          setRunningState(data.running);
        }
      }
      
      /* =================== QOL FEATURES =================== */
      async function askGemini() {
        const btn = $('#askGemini');
        btn.disabled = true;
        btn.innerHTML = 'Consulting the Oracle…<span class="spinner"></span>';
        log('Consulting the Gemini Oracle...', 'llm');
        
        const prompt = botRunning ? 
          `Analyze ${$('#symbol').value} with: Price: ${$('#currentPrice').textContent}, Supertrend: ${$('#stDirection').textContent}, RSI: ${$('#rsiValue').textContent}. Provide a concise, neutral analysis (max 150 words).`
          : `Provide a general market outlook for ${$('#symbol').value} based on recent trends. (max 150 words).`;

        try {
          const res = await fetchWithRetry(`${BACKEND_URL}/api/gemini-insight`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt })
          }, 1, 1000, 15000);
          
          const data = await res.json();
          if (data.status === 'success') {
            log(`— Gemini Insight —\n${data.insight}`, 'llm');
            Toast.show('Gemini insight received', 'success');
          } else {
            log(`Gemini error: ${data.message}`, 'error');
            Toast.show('Failed to get Gemini insight', 'error');
          }
        } catch (e) {
          log(`Oracle network error: ${e.message}`, 'error');
          Toast.show('Failed to get Gemini insight', 'error');
        } finally {
          btn.disabled = false;
          btn.innerHTML = '✨ Ask Gemini for Market Insight';
        }
      }

      function exportLogs() {
        const text = $$('#logArea .log-entry').map(el => el.dataset.originalText || el.textContent).join('\n'); // Use original text
        const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `pyrmethus_logs_${new Date().toISOString().slice(0, 10)}.txt`;
        a.click();
        URL.revokeObjectURL(a.href);
        Toast.show('Logs exported.', 'info');
      }
      
      async function copyConfig() {
        try {
          await navigator.clipboard.writeText(JSON.stringify(getConfig(), null, 2));
          log('Config copied to clipboard.', 'success');
          Toast.show('Config copied to clipboard.', 'success');
        } catch (e) {
          log('Could not copy to clipboard. Check permissions.', 'error');
          Toast.show('Could not copy to clipboard.', 'error');
        }
      }

      function importConfig() {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.json,application/json';
        input.onchange = async (e) => {
          const file = e.target.files[0];
          if (!file) return;
          
          try {
            const text = await file.text();
            const config = JSON.parse(text);
            setConfig(config);
            Toast.show('Configuration imported successfully', 'success');
            saveDraftConfig();
          } catch (e) {
            Toast.show('Invalid configuration file', 'error');
            log(`Invalid JSON provided: ${e.message}`, 'error');
          }
        };
        input.click();
      }

      function resetConfig() {
        if (confirm('Reset all settings to defaults?')) {
          // Re-create numeric fields to reset to defaults
          numericFieldsContainer.innerHTML = '';
          NUM_FIELDS.forEach(([id, label, def, min, max, step]) => {
            const clone = template.cloneNode(true);
            const labelEl = clone.querySelector('label');
            const inputEl = clone.querySelector('input');
            labelEl.htmlFor = id;
            labelEl.textContent = label;
            Object.assign(inputEl, { id, value: def, min, max, step });
            inputEl.addEventListener('input', (e) => {
              const value = parseFloat(e.target.value);
              if (!isNaN(value)) { e.target.value = clamp(value, min, max); }
            });
            numericFieldsContainer.appendChild(clone);
          });

          $('#symbol').value = 'BTCUSDT'; // Default symbol
          $('#interval').value = '60'; // Default interval
          Toast.show('Configuration reset to defaults', 'info');
          localStorage.removeItem(APP_CONFIG.CONFIG_DRAFT_KEY);
        }
      }

      // Log controls
      $('#clearLogs').addEventListener('click', () => {
        if (confirm('Clear all logs?')) {
          $('#logArea').innerHTML = '<div class="log-entry info">Logs cleared. Awaiting commands...</div>'; 
          lastLogTimestamp = Date.now(); 
          updateLogCounts();
          Toast.show('Logs cleared', 'info');
        }
      });

      const logSearch = $('#logSearch');
      const logFilter = $('#logFilter');
      
      const filterLogs = debounce(() => {
        const searchTerm = logSearch.value.toLowerCase();
        const filterType = logFilter.value;
        const logs = $$('#logArea .log-entry');
        let visibleCount = 0;
        
        logs.forEach(logEl => {
          const messageSpan = logEl.querySelector('span:last-child');
          const originalText = messageSpan ? (messageSpan.dataset.originalText || messageSpan.textContent) : logEl.textContent;

          const matchesSearch = !searchTerm || originalText.toLowerCase().includes(searchTerm);
          const matchesType = !filterType || logEl.dataset.type === filterType;
          const isVisible = matchesSearch && matchesType;
          
          logEl.style.display = isVisible ? '' : 'none';
          if (isVisible) visibleCount++;
          
          // Highlight search term
          if (messageSpan) {
            if (searchTerm && matchesSearch) {
              const regex = new RegExp(`(${searchTerm})`, 'gi');
              messageSpan.innerHTML = escapeHtml(originalText).replace(regex, '<span class="highlight">$1</span>');
            } else {
              messageSpan.innerHTML = escapeHtml(originalText); // Restore original
            }
          }
        });
        
        $('#filteredLogCount').textContent = visibleCount;
      }, 300);
      
      logSearch.addEventListener('input', filterLogs);
      logFilter.addEventListener('change', filterLogs);

      function updateLogCounts() {
        const total = $$('#logArea .log-entry').length;
        const visible = $$('#logArea .log-entry:not([style*="display: none"])').length;
        $('#logCount').textContent = total;
        $('#filteredLogCount').textContent = visible;
      }

      // Collapsible sections
      $('#collapseConfig').addEventListener('click', () => {
        const content = $('#configContent');
        const icon = $('#collapseConfig svg');
        const isCollapsed = content.classList.toggle('collapsed');
        
        if (isCollapsed) {
          content.style.maxHeight = '0';
          icon.style.transform = 'rotate(-90deg)';
        } else {
          // Set max-height to scrollHeight to allow smooth transition, then to 'none'
          content.style.maxHeight = content.scrollHeight + 'px';
          // After transition, set to 'none' to allow content to grow if needed
          content.addEventListener('transitionend', function handler() {
            if (!content.classList.contains('collapsed')) {
              content.style.maxHeight = 'none';
            }
            content.removeEventListener('transitionend', handler);
          });
          icon.style.transform = 'rotate(0)';
        }
      });

      // Keyboard shortcuts
      $('#keyboardShortcuts').addEventListener('click', () => {
        $('#shortcutsModal').classList.add('active');
      });

      window.closeModal = (modalId) => {
        $(`#${modalId}`).classList.remove('active');
      };

      // Global keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts when typing in inputs
        if (e.target.matches('input, textarea, select')) return;
        
        if (e.ctrlKey || e.metaKey) {
          switch (e.key.toLowerCase()) {
            case 'enter':
              e.preventDefault();
              handleStartStop();
              break;
            case 'd':
              e.preventDefault();
              $('#themeToggle').click();
              break;
            case 'e':
              e.preventDefault();
              exportLogs();
              break;
            case 'f':
              e.preventDefault();
              logSearch.focus();
              break;
            case 'c':
              if (!e.shiftKey) { // Prevent conflict with copy
                e.preventDefault();
                copyConfig();
              }
              break;
            case 'i':
              e.preventDefault();
              importConfig();
              break;
          }
        } else if (e.key === 'F5') {
          e.preventDefault();
          fetchDashboardStatus(); // Refresh dashboard via polling
          const icon = $('#refreshDashboard svg');
          if (icon) {
            icon.style.animation = 'spin 0.5s linear';
            setTimeout(() => icon.style.animation = '', 500);
          }
        }
      });

      /* ========================= INITIALIZATION ======================== */
      // Set initial theme
      const savedTheme = localStorage.getItem(APP_CONFIG.THEME_KEY) || 'dark';
      applyTheme(savedTheme);
      
      // Set initial sound state
      updateSoundButton();
      
      // Load draft config if exists
      loadDraftConfig();
      
      // Auto-save config on changes
      $$('input, select').forEach(el => {
        el.addEventListener('change', debounce(saveDraftConfig, 1000));
      });
      
      // Event Listeners
      $('#startBot').addEventListener('click', handleStartStop);
      $('#askGemini').addEventListener('click', askGemini);
      $('#clearLogs').addEventListener('click', () => { 
        if (confirm('Clear all logs?')) {
          $('#logArea').innerHTML = '<div class="log-entry info">Logs cleared. Awaiting commands...</div>'; 
          lastLogTimestamp = Date.now(); 
          updateLogCounts();
          Toast.show('Logs cleared.', 'info');
        }
      });
      $('#exportLogs').addEventListener('click', exportLogs);
      $('#copyConfig').addEventListener('click', copyConfig);
      $('#importConfig').addEventListener('click', importConfig);
      $('#resetConfig').addEventListener('click', resetConfig);
      $('#refreshDashboard').addEventListener('click', () => {
        fetchDashboardStatus();
        const icon = $('#refreshDashboard svg');
        if (icon) {
          icon.style.animation = 'spin 0.5s linear';
          setTimeout(() => icon.style.animation = '', 500);
        }
      });

      // Initial dashboard fetch (via polling) and WebSocket connection attempt
      fetchDashboardStatus();
      connectWebSocket();
      
      log(`Grimoire v${APP_CONFIG.VERSION} initialized ✨`, 'success');
      Toast.show('Welcome to Pyrmethus\'s Neon Grimoire', 'info', 3000);
      
      // Cleanup on page unload
      window.addEventListener('beforeunload', () => {
        if (socket) {
          socket.disconnect();
        }
        saveDraftConfig();
      });
    });
  </script>
</body>
</html>
EOF

echo "Creating backend/.env"
cat << EOF > backend/.env
BYBIT_API_KEY="${BYBIT_API_KEY_PLACEHOLDER}"
BYBIT_API_SECRET="${BYBIT_API_SECRET_PLACEHOLDER}"
GEMINI_API_KEY="${GEMINI_API_KEY_PLACEHOLDER}"
BYBIT_TESTNET="true"
EOF

echo "Creating backend/requirements.txt"
cat << 'EOF' > backend/requirements.txt
Flask==2.3.3
Flask-Cors==4.0.0
Flask-SocketIO==5.3.0
python-dotenv==1.0.0
pybit==0.3.4
google-generativeai==0.3.0
pandas==2.1.4
numpy==1.26.2
pandas-ta==0.3.14b0
eventlet==0.33.3
EOF

echo "Creating backend/utils.py"
cat << 'EOF' > backend/utils.py
import logging
from datetime import datetime
from flask_socketio import SocketIO, emit
import threading
from typing import Dict, Any, List

class CustomLogger(logging.Handler):
    """
    A custom logging handler that stores logs in memory and can emit them via SocketIO.
    """
    def __init__(self, socketio: SocketIO, max_logs: int = 200): # Increased max_logs
        super().__init__()
        self.logs = []
        self.max_logs = max_logs
        self.socketio = socketio
        self.lock = threading.Lock() # Protects self.logs
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        log_entry = {
            "timestamp": datetime.now().timestamp() * 1000, # Milliseconds for frontend
            "level": record.levelname.lower(),
            "message": self.format(record)
        }
        with self.lock:
            self.logs.append(log_entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)
        
        # Emit log via WebSocket
        try:
            self.socketio.emit('log_entry', log_entry, namespace='/ws/status') # Changed event name to log_entry
        except RuntimeError:
            # This can happen if emit is called outside of a Flask context or during shutdown
            pass 

    def get_recent_logs(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.logs)

# --- Data Formatting Helpers ---
def format_price(value: Any) -> str:
    try:
        if value is None or value == '---': return "---"
        return f"${float(value):,.2f}"
    except (ValueError, TypeError):
        return "---"

def format_percent(value: Any) -> str:
    try:
        if value is None or value == '---': return "---"
        return f"{float(value):.2f}%"
    except (ValueError, TypeError):
        return "---"

def format_num(value: Any) -> str:
    try:
        if value is None or value == '---': return "---"
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return "---"

def format_decimal(value: Any, precision: int = 4) -> str:
    try:
        if value is None or value == '---': return "---"
        return f"{float(value):.{precision}f}"
    except (ValueError, TypeError):
        return "---"

def get_current_timestamp_ms() -> int:
    return int(datetime.now().timestamp() * 1000)

EOF

echo "Creating backend/config.py"
cat << 'EOF' > backend/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
    BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true"

    # Default Trading Parameters (can be overridden by frontend)
    DEFAULT_SYMBOL = "BTCUSDT" # Changed to BTCUSDT for broader data availability
    DEFAULT_INTERVAL = "60" # 1 hour
    DEFAULT_LEVERAGE = 10
    DEFAULT_RISK_PCT = 1.0 # % of equity to risk per trade
    DEFAULT_STOP_LOSS_PCT = 2.0 # % from entry price
    DEFAULT_TAKE_PROFIT_PCT = 5.0 # % from entry price
    
    # Indicator Periods - matching frontend NUM_FIELDS
    DEFAULT_EF_PERIOD = 10
    DEFAULT_MACD_FAST_PERIOD = 12
    DEFAULT_MACD_SLOW_PERIOD = 26
    DEFAULT_MACD_SIGNAL_PERIOD = 9
    DEFAULT_BB_PERIOD = 20
    DEFAULT_BB_STD_DEV = 2.0
    
    # Hardcoded for now, but can be made configurable
    DEFAULT_SUPERTREND_LENGTH = 10
    DEFAULT_SUPERTREND_MULTIPLIER = 3.0
    DEFAULT_RSI_LENGTH = 14
    DEFAULT_RSI_OVERBOUGHT = 70
    DEFAULT_RSI_OVERSOLD = 30

    # Bot operation settings
    POLLING_INTERVAL_SECONDS = 5 # How often the bot loop runs and sends updates
    MARKET_DATA_FETCH_LIMIT = 200 # Max historical klines for indicator calculation
    MAX_LOG_ENTRIES = 200 # Max logs to keep in memory

    # Trading Strategy Settings
    MIN_SIGNAL_STRENGTH = 2 # Minimum number of bullish/bearish indicators for a trade
    ORDER_TYPE = "Market" # "Market" or "Limit"
    TIME_IN_FORCE = "GTC" # "GTC", "IOC", "FOK"
    REDUCE_ONLY = False # For closing positions

    # AI Model
    GEMINI_MODEL = "gemini-1.5-flash" # Or "gemini-pro"

    # Backend API URL for Bybit (for HTTP client)
    BYBIT_API_BASE_URL = "https://api.bybit.com" if not os.getenv("BYBIT_TESTNET", "true").lower() == "true" else "https://api-testnet.bybit.com"
    BYBIT_WS_BASE_URL = "wss://stream.bybit.com/v5/public/linear" if not os.getenv("BYBIT_TESTNET", "true").lower() == "true" else "wss://stream-testnet.bybit.com/v5/public/linear"

EOF

echo "Creating backend/bybit_api_client.py"
cat << 'EOF' > backend/bybit_api_client.py
import logging
from pybit.unified_trading import HTTP
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN, ROUND_UP

class BybitAPIClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool, logger: logging.Logger):
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.logger = logger
        self.category = "linear" # Default category for this bot
        self.instrument_info: Dict[str, Any] = {} # Stores precision info
        self._load_instrument_info()

    def _load_instrument_info(self):
        """Fetches and stores instrument info for all trading pairs."""
        try:
            response = self.session.get_instruments_info(category=self.category)
            if response and response.get('retCode') == 0:
                for item in response['result']['list']:
                    self.instrument_info[item['symbol']] = item
                self.logger.info(f"Loaded instrument info for {len(self.instrument_info)} symbols.")
            else:
                self.logger.error(f"Failed to load instrument info: {response.get('retMsg', 'Unknown error')}")
        except Exception as e:
            self.logger.error(f"Exception loading instrument info: {e}")

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Generic request handler with logging and error checking."""
        try:
            response = getattr(self.session, method)(**kwargs)
            if response and response.get('retCode') == 0:
                return response.get('result')
            else:
                msg = response.get('retMsg', 'Unknown error')
                self.logger.error(f"Bybit API Error ({endpoint}): {msg} - Args: {kwargs}")
                return None
        except Exception as e:
            self.logger.error(f"Bybit API Exception ({endpoint}): {e} - Args: {kwargs}")
            return None

    def get_kline(self, symbol: str, interval: str, limit: int) -> Optional[Dict[str, Any]]:
        return self._request('get_kline', endpoint='/v5/market/kline', category=self.category, symbol=symbol, interval=interval, limit=limit)

    def get_tickers(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('get_tickers', endpoint='/v5/market/tickers', category=self.category, symbol=symbol)

    def get_positions(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('get_positions', endpoint='/v5/position/list', category=self.category, symbol=symbol)

    def get_wallet_balance(self) -> Optional[Dict[str, Any]]:
        return self._request('get_wallet_balance', endpoint='/v5/account/wallet-balance', accountType="UNIFIED")

    def place_order(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self._request('place_order', endpoint='/v5/order/create', category=self.category, **kwargs)

    def cancel_order(self, orderId: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('cancel_order', endpoint='/v5/order/cancel', category=self.category, orderId=orderId, symbol=symbol)

    def set_leverage(self, symbol: str, leverage: int) -> Optional[Dict[str, Any]]:
        return self._request('set_leverage', endpoint='/v5/position/set-leverage', category=self.category, symbol=symbol, buyLeverage=str(leverage), sellLeverage=str(leverage))

    def set_trading_stop(self, symbol: str, stopLoss: float, takeProfit: Optional[float] = None) -> Optional[Dict[str, Any]]:
        params = {'category': self.category, 'symbol': symbol, 'stopLoss': str(stopLoss), 'positionIdx': 0}
        if takeProfit is not None:
            params['takeProfit'] = str(takeProfit)
        return self._request('set_trading_stop', endpoint='/v5/position/trading-stop', **params)

    def close_position(self, symbol: str, side: str, qty: float) -> Optional[Dict[str, Any]]:
        """Closes an open position by placing a market order with reduceOnly=True."""
        opposite_side = "Sell" if side == "Buy" else "Buy"
        return self.place_order(
            symbol=symbol,
            side=opposite_side,
            orderType="Market",
            qty=str(qty),
            reduceOnly=True,
            closeOnTrigger=False # Ensure this is false for market close
        )

    def get_trading_fee_rate(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('get_fee_rate', endpoint='/v5/account/fee-rate', category=self.category, symbol=symbol)

    # --- Precision Handling ---
    def _get_precision_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.instrument_info.get(symbol)

    def round_price(self, symbol: str, price: float) -> float:
        info = self._get_precision_info(symbol)
        if not info:
            self.logger.warning(f"No precision info for {symbol}, falling back to 2 decimal places for price.")
            return round(price, 2) # Fallback
        tick_size = Decimal(info['priceFilter']['tickSize'])
        return float((Decimal(str(price)) / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size)

    def round_qty(self, symbol: str, qty: float) -> float:
        info = self._get_precision_info(symbol)
        if not info:
            self.logger.warning(f"No precision info for {symbol}, falling back to 3 decimal places for quantity.")
            return round(qty, 3) # Fallback
        qty_step = Decimal(info['lotSizeFilter']['qtyStep'])
        return float((Decimal(str(qty)) / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step)

    def get_min_order_qty(self, symbol: str) -> float:
        info = self._get_precision_info(symbol)
        return float(info['lotSizeFilter']['minOrderQty']) if info else 0.001

EOF

echo "Creating backend/gemini_ai_client.py"
cat << 'EOF' > backend/gemini_ai_client.py
import logging
import asyncio
from typing import Dict, Any
from google.generativeai import GenerativeModel, configure

class GeminiAIClient:
    def __init__(self, api_key: str, model_name: str, logger: logging.Logger):
        self.logger = logger
        self.model_name = model_name
        self.model = None
        if api_key:
            try:
                configure(api_key=api_key)
                self.model = GenerativeModel(model_name)
                self.logger.info(f"Gemini AI client initialized with model: {model_name}")
            except Exception as e:
                self.logger.error(f"Failed to configure Gemini AI: {e}. AI features disabled.")
        else:
            self.logger.warning("Gemini API Key not provided. AI features will be disabled.")

    async def generate_insight(self, prompt: str) -> Dict[str, Any]:
        if not self.model:
            return {"status": "error", "message": "Gemini AI is not configured."}
        try:
            response = await self.model.generate_content_async(prompt)
            return {"status": "success", "insight": response.text}
        except Exception as e:
            self.logger.error(f"Gemini AI Generation Error: {e}")
            return {"status": "error", "message": f"Error generating insight: {e}"}

    def build_analysis_prompt(self, dashboard_metrics: Dict[str, Any], config: Dict[str, Any]) -> str:
        """Constructs a detailed prompt for Gemini based on current bot state."""
        prompt = f"""
        You are a highly experienced cryptocurrency trading analyst. Provide a concise, neutral, and actionable market insight based on the provided data.
        Focus on interpreting the indicators and suggesting potential market movements or trading considerations. Avoid explicit financial advice.
        
        **Current Bot Configuration:**
        Symbol: {config.get('symbol')}
        Interval: {config.get('interval')} minutes
        Leverage: {config.get('leverage')}x
        Risk per Trade: {config.get('riskPct')}%
        Stop Loss Target: {config.get('stopLossPct')}%
        Take Profit Target: {config.get('takeProfitPct')}%

        **Live Dashboard Metrics:**
        Current Price: {dashboard_metrics.get('currentPrice')}
        Price Change (Interval): {dashboard_metrics.get('priceChange')}
        Supertrend Direction: {dashboard_metrics.get('stDirection')} (Value: {dashboard_metrics.get('stValue')})
        RSI Value: {dashboard_metrics.get('rsiValue')} (Status: {dashboard_metrics.get('rsiStatus')})
        Ehlers-Fisher Value: {dashboard_metrics.get('fisherValue')}
        MACD Line: {dashboard_metrics.get('macdLine')}
        MACD Signal: {dashboard_metrics.get('macdSignal')}
        MACD Histogram: {dashboard_metrics.get('macdHistogram')}
        Bollinger Bands: Middle={dashboard_metrics.get('bbMiddle')}, Upper={dashboard_metrics.get('bbUpper')}, Lower={dashboard_metrics.get('bbLower')}
        Current Position: {dashboard_metrics.get('currentPosition')} (PnL: {dashboard_metrics.get('positionPnL')})
        Account Balance: {dashboard_metrics.get('accountBalance')}

        **Analysis Focus:**
        - Identify dominant trend based on Supertrend and EMAs (if available).
        - Assess momentum using RSI and MACD.
        - Comment on volatility and potential breakouts/reversals using Bollinger Bands.
        - Consider current position and overall market sentiment.
        - Keep the analysis under 150 words.
        """
        return prompt

EOF

echo "Creating backend/strategy.py"
cat << 'EOF' > backend/strategy.py
import pandas as pd
import pandas_ta as ta
import numpy as np
import logging
from typing import Dict, Any, Tuple, Optional
from enum import Enum

class Signal(Enum):
    STRONG_BUY = 2
    BUY = 1
    NEUTRAL = 0
    SELL = -1
    STRONG_SELL = -2

class TradingStrategy:
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.config: Dict[str, Any] = {} # Will be set by TradingBotCore

    def set_config(self, config: Dict[str, Any]):
        self.config = config

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates all necessary technical indicators using pandas_ta."""
        if df.empty:
            return df

        close_prices = df['close']
        high_prices = df['high']
        low_prices = df['low']
        # volume = df['volume'] # Not all indicators use volume

        # Ensure data is sorted
        df = df.sort_index()

        # --- Trend Indicators ---
        # EMA (Exponential Moving Average) - using MACD periods for consistency
        df[f'EMA_Fast'] = ta.ema(close_prices, length=self.config.get('macdFastPeriod', 12)) 
        df[f'EMA_Slow'] = ta.ema(close_prices, length=self.config.get('macdSlowPeriod', 26)) 

        # MACD
        macd_fast = self.config.get('macdFastPeriod', 12)
        macd_slow = self.config.get('macdSlowPeriod', 26)
        macd_signal = self.config.get('macdSignalPeriod', 9)
        macd_data = ta.macd(close_prices, fast=macd_fast, slow=macd_slow, signal=macd_signal)
        if macd_data is not None and not macd_data.empty:
            df['MACD'] = macd_data[f'MACD_{macd_fast}_{macd_slow}_{macd_signal}']
            df['MACD_Signal'] = macd_data[f'MACDs_{macd_fast}_{macd_slow}_{macd_signal}']
            df['MACD_Hist'] = macd_data[f'MACDh_{macd_fast}_{macd_slow}_{macd_signal}']

        # Supertrend
        st_length = self.config.get('supertrend_length', 10)
        st_multiplier = self.config.get('supertrend_multiplier', 3.0)
        st_data = ta.supertrend(high_prices, low_prices, close_prices, length=st_length, multiplier=st_multiplier)
        if st_data is not None and not st_data.empty:
            df['SUPERT_D'] = st_data[f'SUPERTd_{st_length}_{st_multiplier}.0'] # Direction
            df['SUPERT'] = st_data[f'SUPERT_{st_length}_{st_multiplier}.0'] # Value

        # --- Momentum Indicators ---
        # RSI
        rsi_length = self.config.get('rsi_length', 14)
        df['RSI'] = ta.rsi(close_prices, length=rsi_length)

        # Ehlers-Fisher Transform (using pandas_ta's fisher transform)
        ef_period = self.config.get('efPeriod', 10)
        fisher_data = ta.fisher(high_prices, low_prices, length=ef_period)
        if fisher_data is not None and not fisher_data.empty:
            df['FISHER'] = fisher_data[f'FISHERT_{ef_period}']
            df['FISHER_Signal'] = fisher_data[f'FISHERTs_{ef_period}']

        # --- Volatility Indicators ---
        # Bollinger Bands
        bb_period = self.config.get('bbPeriod', 20)
        bb_std = self.config.get('bbStdDev', 2.0)
        bb_data = ta.bbands(close_prices, length=bb_period, std=bb_std)
        if bb_data is not None and not bb_data.empty:
            df['BBL'] = bb_data[f'BBL_{bb_period}_{bb_std}']
            df['BBM'] = bb_data[f'BBM_{bb_period}_{bb_std}']
            df['BBU'] = bb_data[f'BBU_{bb_period}_{bb_std}']

        # --- Fill NaN values ---
        # Forward fill then fill remaining NaNs with 0 (for indicators that need more data than available)
        df = df.fillna(method='ffill').fillna(0)
        
        self.logger.debug("Technical indicators calculated.")
        return df

    def generate_trading_signal(self, df: pd.DataFrame, current_position_side: Optional[str]) -> Tuple[Signal, str]:
        """
        Generates a trading signal based on a combination of indicators.
        This is a multi-indicator confirmation strategy.
        """
        # Ensure enough data for all indicators plus prev candle
        required_history = max(
            self.config.get('macdSlowPeriod', 26), 
            self.config.get('rsi_length', 14), 
            self.config.get('bbPeriod', 20),
            self.config.get('supertrend_length', 10),
            self.config.get('efPeriod', 10)
        ) + 2 # +2 for current and previous candle after indicator calculation
        
        if df.empty or len(df) < required_history: 
            self.logger.warning(f"Insufficient data ({len(df)} klines) for signal generation. Need at least {required_history}.")
            return Signal.NEUTRAL, "Insufficient data for signal generation."

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        buy_signals = 0
        sell_signals = 0
        reasons = []

        # --- 1. EMA Crossover ---
        if latest['EMA_Fast'] > latest['EMA_Slow'] and prev['EMA_Fast'] <= prev['EMA_Slow']:
            buy_signals += 1
            reasons.append("EMA Bullish Crossover")
        elif latest['EMA_Fast'] < latest['EMA_Slow'] and prev['EMA_Fast'] >= prev['EMA_Slow']:
            sell_signals += 1
            reasons.append("EMA Bearish Crossover")

        # --- 2. RSI ---
        rsi_oversold = self.config.get('rsi_oversold', 30)
        rsi_overbought = self.config.get('rsi_overbought', 70)
        if latest['RSI'] < rsi_oversold:
            buy_signals += 1
            reasons.append(f"RSI ({latest['RSI']:.2f}) Oversold")
        elif latest['RSI'] > rsi_overbought:
            sell_signals += 1
            reasons.append(f"RSI ({latest['RSI']:.2f}) Overbought")

        # --- 3. MACD Crossover ---
        if latest['MACD'] > latest['MACD_Signal'] and prev['MACD'] <= prev['MACD_Signal']:
            buy_signals += 1
            reasons.append("MACD Bullish Crossover")
        elif latest['MACD'] < latest['MACD_Signal'] and prev['MACD'] >= prev['MACD_Signal']:
            sell_signals += 1
            reasons.append("MACD Bearish Crossover")

        # --- 4. Supertrend ---
        if latest['SUPERT_D'] == 1: # Up trend
            buy_signals += 1
            reasons.append("Supertrend Up")
        elif latest['SUPERT_D'] == -1: # Down trend
            sell_signals += 1
            reasons.append("Supertrend Down")

        # --- 5. Bollinger Bands ---
        if latest['close'] < latest['BBL']:
            buy_signals += 1
            reasons.append("Price below BB Lower")
        elif latest['close'] > latest['BBU']:
            sell_signals += 1
            reasons.append("Price above BB Upper")

        # --- 6. Ehlers-Fisher ---
        # Fisher values typically range from -1 to 1. Crossover near extremes is stronger.
        if latest['FISHER'] > latest['FISHER_Signal'] and prev['FISHER'] <= prev['FISHER_Signal'] and latest['FISHER'] < 0.5: # Crossover up from oversold
            buy_signals += 1
            reasons.append("Fisher Bullish Crossover")
        elif latest['FISHER'] < latest['FISHER_Signal'] and prev['FISHER'] >= prev['FISHER_Signal'] and latest['FISHER'] > -0.5: # Crossover down from overbought
            sell_signals += 1
            reasons.append("Fisher Bearish Crossover")
        
        # --- Aggregation and Final Signal ---
        min_strength = self.config.get('MIN_SIGNAL_STRENGTH', 2)

        if buy_signals >= min_strength and current_position_side != "Buy":
            return Signal.BUY, f"Strong BUY ({buy_signals} confirmations): {', '.join(reasons)}"
        elif sell_signals >= min_strength and current_position_side != "Sell":
            return Signal.SELL, f"Strong SELL ({sell_signals} confirmations): {', '.join(reasons)}"
        
        # If already in position, check for reversal or hold
        if current_position_side == "Buy" and sell_signals > buy_signals:
             return Signal.SELL, f"Reversal detected for BUY position ({sell_signals} vs {buy_signals}): {', '.join(reasons)}"
        elif current_position_side == "Sell" and buy_signals > sell_signals:
             return Signal.BUY, f"Reversal detected for SELL position ({buy_signals} vs {sell_signals}): {', '.join(reasons)}"

        return Signal.NEUTRAL, "No strong signal or maintaining position."

EOF

echo "Creating backend/bot_core.py"
cat << 'EOF' > backend/bot_core.py
import threading
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from flask_socketio import SocketIO
from typing import Dict, Any, Optional

from config import Config
from utils import CustomLogger, format_price, format_percent, format_num, format_decimal, get_current_timestamp_ms
from bybit_api_client import BybitAPIClient
from gemini_ai_client import GeminiAIClient
from strategy import TradingStrategy, Signal

class TradingBotCore:
    """
    Core trading bot logic, managing state, data, and interactions.
    """
    def __init__(self, config: Config, socketio: SocketIO, custom_logger: CustomLogger):
        self.config = config
        self.socketio = socketio
        self.logger = logging.getLogger('TradingBot')
        self.logger.addHandler(custom_logger)
        self.logger.setLevel(logging.INFO)

        self.is_running = False
        self.bot_thread: Optional[threading.Thread] = None
        self.current_frontend_config: Dict[str, Any] = {} # Stores config from frontend /api/start
        self.market_data = pd.DataFrame()
        self.dashboard_metrics = self._initialize_dashboard_metrics()
        self.current_position: Optional[Dict[str, Any]] = None
        self.account_balance: Optional[Dict[str, Any]] = None
        self.total_trades = 0
        self.winning_trades = 0
        self.last_update_time: Optional[datetime] = None
        self.session_start_time: Optional[datetime] = None

        self.bybit_client = BybitAPIClient(config.BYBIT_API_KEY, config.BYBIT_API_SECRET, config.BYBIT_TESTNET, self.logger)
        self.gemini_client = GeminiAIClient(config.GEMINI_API_KEY, config.GEMINI_MODEL, self.logger)
        self.trading_strategy = TradingStrategy(self.logger)

        self.logger.info("TradingBotCore initialized.")

    def _initialize_dashboard_metrics(self) -> Dict[str, Any]:
        return {
            'currentPrice': '---', 'priceChange': '---',
            'stDirection': '---', 'stValue': '---',
            'rsiValue': '---', 'rsiStatus': '---',
            'currentPosition': '---', 'positionPnL': '---',
            'accountBalance': '---', 'fisherValue': '---',
            'macdLine': '---', 'macdSignal': '---', 'macdHistogram': '---',
            'bbMiddle': '---', 'bbUpper': '---', 'bbLower': '---',
            'totalTrades': '0', 'winRate': '0%', 'botStatus': 'Idle',
        }

    def get_full_status(self) -> Dict[str, Any]:
        return {
            "dashboard": self.dashboard_metrics,
            "logs": self.logger.handlers[0].get_recent_logs(), # Assuming CustomLogger is the first handler
            "running": self.is_running
        }

    def start(self, frontend_config: Dict[str, Any]) -> Dict[str, str]:
        if self.is_running:
            return {"status": "error", "message": "Bot is already running."}

        # Update internal config with frontend values
        self.current_frontend_config = {
            'symbol': frontend_config.get('symbol', self.config.DEFAULT_SYMBOL),
            'interval': frontend_config.get('interval', self.config.DEFAULT_INTERVAL),
            'leverage': int(frontend_config.get('leverage', self.config.DEFAULT_LEVERAGE)),
            'riskPct': float(frontend_config.get('riskPct', self.config.DEFAULT_RISK_PCT)),
            'stopLossPct': float(frontend_config.get('stopLossPct', self.config.DEFAULT_STOP_LOSS_PCT)),
            'takeProfitPct': float(frontend_config.get('takeProfitPct', self.config.DEFAULT_TAKE_PROFIT_PCT)),
            'efPeriod': int(frontend_config.get('efPeriod', self.config.DEFAULT_EF_PERIOD)),
            'macdFastPeriod': int(frontend_config.get('macdFastPeriod', self.config.DEFAULT_MACD_FAST_PERIOD)),
            'macdSlowPeriod': int(frontend_config.get('macdSlowPeriod', self.config.DEFAULT_MACD_SLOW_PERIOD)),
            'macdSignalPeriod': int(frontend_config.get('macdSignalPeriod', self.config.DEFAULT_MACD_SIGNAL_PERIOD)),
            'bbPeriod': int(frontend_config.get('bbPeriod', self.config.DEFAULT_BB_PERIOD)),
            'bbStdDev': float(frontend_config.get('bbStdDev', self.config.DEFAULT_BB_STD_DEV)),
            'supertrend_length': int(frontend_config.get('supertrend_length', self.config.DEFAULT_SUPERTREND_LENGTH)),
            'supertrend_multiplier': float(frontend_config.get('supertrend_multiplier', self.config.DEFAULT_SUPERTREND_MULTIPLIER)),
            'rsi_length': int(frontend_config.get('rsi_length', self.config.DEFAULT_RSI_LENGTH)),
            'rsi_overbought': float(frontend_config.get('rsi_overbought', self.config.DEFAULT_RSI_OVERBOUGHT)),
            'rsi_oversold': float(frontend_config.get('rsi_oversold', self.config.DEFAULT_RSI_OVERSOLD)),
            'MIN_SIGNAL_STRENGTH': self.config.MIN_SIGNAL_STRENGTH # Use backend default for now
        }
        self.trading_strategy.set_config(self.current_frontend_config)

        # Attempt to set leverage on Bybit
        leverage_set = self.bybit_client.set_leverage(self.current_frontend_config['symbol'], self.current_frontend_config['leverage'])
        if not leverage_set:
            self.logger.error("Failed to set leverage. Bot cannot start.")
            return {"status": "error", "message": "Failed to set leverage on exchange."}

        self.is_running = True
        self.session_start_time = datetime.now()
        self.dashboard_metrics['botStatus'] = 'Running'
        self.bot_thread = threading.Thread(target=self._run_bot_loop)
        self.bot_thread.daemon = True
        self.bot_thread.start()
        self.logger.info(f"Bot started with config: {self.current_frontend_config['symbol']}/{self.current_frontend_config['interval']}")
        return {"status": "success", "message": "Bot ritual initiated ✔️"}

    def stop(self) -> Dict[str, str]:
        if not self.is_running:
            return {"status": "error", "message": "Bot is not running."}
        self.is_running = False
        self.dashboard_metrics['botStatus'] = 'Idle'
        self.logger.warning("Bot ritual paused ⏸️")
        return {"status": "success", "message": "Bot ritual paused ⏸️"}

    def _run_bot_loop(self):
        while self.is_running:
            self.logger.debug("Bot loop iteration...")
            try:
                # 1. Fetch & Process Market Data
                self._fetch_and_process_market_data()
                self.market_data = self.trading_strategy.calculate_all_indicators(self.market_data)

                # 2. Update Account Info
                self._update_account_info()

                # 3. Calculate Dashboard Metrics
                self._calculate_dashboard_metrics()

                # 4. Execute Strategy
                self._execute_trading_strategy()

                # 5. Emit Full Dashboard Update via WebSocket
                self.socketio.emit('dashboard_update', self.get_full_status(), namespace='/ws/status')
                self.last_update_time = datetime.now()

            except Exception as e:
                self.logger.error(f"Error in bot loop: {e}")
                self.dashboard_metrics['botStatus'] = 'Error'
                self.is_running = False # Stop bot on critical error
            finally:
                time.sleep(self.config.POLLING_INTERVAL_SECONDS)
        self.logger.info("Bot loop terminated.")

    def _fetch_and_process_market_data(self):
        symbol = self.current_frontend_config['symbol']
        interval = self.current_frontend_config['interval']
        limit = self.config.MARKET_DATA_FETCH_LIMIT

        klines_data = self.bybit_client.get_kline(symbol, interval, limit)
        if klines_data and klines_data['list']:
            df = pd.DataFrame(klines_data['list'], columns=[
                'start', 'open', 'high', 'low', 'close', 'volume', 'turnover'
            ])
            df['start'] = pd.to_datetime(df['start'].astype(float), unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'turnover']:
                df[col] = pd.to_numeric(df[col])
            df = df.sort_values('start').set_index('start')
            self.market_data = df
            self.logger.debug(f"Fetched {len(df)} klines for {symbol}")
        else:
            self.logger.warning(f"No kline data received for {symbol}.")

    def _update_account_info(self):
        symbol = self.current_frontend_config['symbol']
        # Fetch current position
        positions_data = self.bybit_client.get_positions(symbol)
        if positions_data and positions_data['list']:
            # Find the active position for the current symbol
            active_pos = next((p for p in positions_data['list'] if float(p['size']) > 0 and p['symbol'] == symbol), None)
            self.current_position = active_pos
        else:
            self.current_position = None
        
        # Fetch wallet balance
        balance_data = self.bybit_client.get_wallet_balance()
        if balance_data and balance_data['list']:
            usdt_balance = next((c for c in balance_data['list'][0]['coin'] if c['coin'] == 'USDT'), None)
            self.account_balance = usdt_balance
        else:
            self.account_balance = None
        
        self.logger.debug("Account info updated.")

    def _calculate_dashboard_metrics(self):
        if self.market_data.empty:
            self.dashboard_metrics = self._initialize_dashboard_metrics()
            return

        latest = self.market_data.iloc[-1]
        prev = self.market_data.iloc[-2] if len(self.market_data) > 1 else None

        # Current Price & Change
        current_price = latest['close']
        price_change = ((current_price - prev['close']) / prev['close'] * 100) if prev is not None else 0
        self.dashboard_metrics['currentPrice'] = format_price(current_price)
        self.dashboard_metrics['priceChange'] = format_percent(price_change)

        # Supertrend
        st_direction = latest.get('SUPERT_D')
        st_value = latest.get('SUPERT')
        self.dashboard_metrics['stDirection'] = 'Up' if st_direction == 1 else ('Down' if st_direction == -1 else '---')
        self.dashboard_metrics['stValue'] = format_price(st_value)

        # RSI
        rsi_value = latest.get('RSI')
        rsi_status = '---'
        if rsi_value is not None:
            if rsi_value > self.current_frontend_config.get('rsi_overbought', self.config.DEFAULT_RSI_OVERBOUGHT): rsi_status = 'Overbought'
            elif rsi_value < self.current_frontend_config.get('rsi_oversold', self.config.DEFAULT_RSI_OVERSOLD): rsi_status = 'Oversold'
            else: rsi_status = 'Neutral'
        self.dashboard_metrics['rsiValue'] = format_decimal(rsi_value, 2)
        self.dashboard_metrics['rsiStatus'] = rsi_status

        # Current Position & PnL
        if self.current_position:
            self.dashboard_metrics['currentPosition'] = self.current_position['side']
            unrealized_pnl = float(self.current_position['unrealisedPnl'])
            entry_price = float(self.current_position['avgPrice'])
            position_size = float(self.current_position['size'])
            pnl_percent = (unrealized_pnl / (entry_price * position_size) * 100) if (entry_price * position_size) > 0 else 0
            self.dashboard_metrics['positionPnL'] = format_percent(pnl_percent)
        else:
            self.dashboard_metrics['currentPosition'] = 'None'
            self.dashboard_metrics['positionPnL'] = '---'

        # Account Balance
        if self.account_balance:
            self.dashboard_metrics['accountBalance'] = format_price(self.account_balance['walletBalance'])
        else:
            self.dashboard_metrics['accountBalance'] = '---'

        # Ehlers-Fisher
        fisher_value = latest.get('FISHER')
        self.dashboard_metrics['fisherValue'] = format_decimal(fisher_value, 4)

        # MACD
        macd_line = latest.get('MACD')
        macd_signal = latest.get('MACD_Signal')
        macd_histogram = latest.get('MACD_Hist')
        self.dashboard_metrics['macdLine'] = format_decimal(macd_line, 4)
        self.dashboard_metrics['macdSignal'] = format_decimal(macd_signal, 4)
        self.dashboard_metrics['macdHistogram'] = format_decimal(macd_histogram, 4)

        # Bollinger Bands
        bb_middle = latest.get('BBM')
        bb_upper = latest.get('BBU')
        bb_lower = latest.get('BBL')
        self.dashboard_metrics['bbMiddle'] = format_price(bb_middle)
        self.dashboard_metrics['bbUpper'] = format_price(bb_upper)
        self.dashboard_metrics['bbLower'] = format_price(bb_lower)

        # Simplified Trade Stats (for demo)
        self.dashboard_metrics['totalTrades'] = format_num(self.total_trades)
        self.dashboard_metrics['winRate'] = format_percent(self.winning_trades / self.total_trades * 100 if self.total_trades > 0 else 0)

        self.logger.debug("Dashboard metrics updated.")

    def _execute_trading_strategy(self):
        if self.market_data.empty or not self.is_running:
            return

        current_position_side = self.current_position['side'] if self.current_position else None
        signal, reason = self.trading_strategy.generate_trading_signal(self.market_data, current_position_side)
        self.logger.info(f"Generated signal: {signal.name}. Reason: {reason}")

        latest_price = self.market_data.iloc[-1]['close']
        symbol = self.current_frontend_config['symbol']
        leverage = self.current_frontend_config['leverage']
        risk_pct = self.current_frontend_config['riskPct']
        sl_pct = self.current_frontend_config['stopLossPct']
        tp_pct = self.current_frontend_config['takeProfitPct']

        account_equity = float(self.account_balance['equity']) if self.account_balance else 0

        if account_equity <= 0:
            self.logger.warning("Account equity is zero or negative. Cannot place trades.")
            return

        # --- Handle BUY Signal ---
        if signal == Signal.BUY and not self.current_position:
            self.logger.info(f"Executing BUY signal for {symbol} at {latest_price}.")
            
            # Calculate SL/TP prices
            stop_loss_price = self.bybit_client.round_price(symbol, latest_price * (1 - sl_pct / 100))
            take_profit_price = self.bybit_client.round_price(symbol, latest_price * (1 + tp_pct / 100))
            
            # Calculate position size
            # Simplified risk-based sizing: (Equity * Risk%) / (Price * SL% / Leverage)
            # This is a rough estimation. Real sizing needs to consider contract value, inverse, etc.
            position_size_usdt_value = account_equity * (risk_pct / 100) * (leverage / (sl_pct / 100)) 
            qty = self.bybit_client.round_qty(symbol, position_size_usdt_value / latest_price)
            qty = max(qty, self.bybit_client.get_min_order_qty(symbol)) # Ensure min qty
            
            if qty > 0:
                order_result = self.bybit_client.place_order(
                    symbol=symbol,
                    side="Buy",
                    orderType=self.config.ORDER_TYPE,
                    qty=str(qty),
                    price=str(self.bybit_client.round_price(symbol, latest_price)) if self.config.ORDER_TYPE == "Limit" else None,
                    stopLoss=str(stop_loss_price),
                    takeProfit=str(take_profit_price),
                    timeInForce=self.config.TIME_IN_FORCE,
                    leverage=str(leverage)
                )
                if order_result:
                    self.logger.info(f"BUY order placed: {qty} {symbol} @ {latest_price}. SL:{stop_loss_price}, TP:{take_profit_price}")
                    self.total_trades += 1
                else:
                    self.logger.error("Failed to place BUY order.")
            else:
                self.logger.warning("Calculated BUY quantity is too small or zero.")

        # --- Handle SELL Signal (Close existing position) ---
        elif signal == Signal.SELL and self.current_position and self.current_position['side'] == "Buy":
            self.logger.info(f"Executing SELL signal to close BUY position for {symbol} at {latest_price}.")
            qty_to_close = float(self.current_position['size'])
            order_result = self.bybit_client.close_position(symbol, "Buy", qty_to_close)
            if order_result:
                self.logger.info(f"BUY position closed: {qty_to_close} {symbol} @ {latest_price}.")
                # For demo, simulate win/loss
                if float(self.current_position['unrealisedPnl']) > 0: self.winning_trades += 1
            else:
                self.logger.error("Failed to close BUY position.")
        
        # --- Handle SELL Signal (Open short position) ---
        elif signal == Signal.SELL and not self.current_position:
            self.logger.info(f"Executing SELL signal to open SHORT position for {symbol} at {latest_price}.")
            
            # Calculate SL/TP prices
            stop_loss_price = self.bybit_client.round_price(symbol, latest_price * (1 + sl_pct / 100))
            take_profit_price = self.bybit_client.round_price(symbol, latest_price * (1 - tp_pct / 100))
            
            # Calculate position size
            position_size_usdt_value = account_equity * (risk_pct / 100) * (leverage / (sl_pct / 100))
            qty = self.bybit_client.round_qty(symbol, position_size_usdt_value / latest_price)
            qty = max(qty, self.bybit_client.get_min_order_qty(symbol)) # Ensure min qty

            if qty > 0:
                order_result = self.bybit_client.place_order(
                    symbol=symbol,
                    side="Sell",
                    orderType=self.config.ORDER_TYPE,
                    qty=str(qty),
                    price=str(self.bybit_client.round_price(symbol, latest_price)) if self.config.ORDER_TYPE == "Limit" else None,
                    stopLoss=str(stop_loss_price),
                    takeProfit=str(take_profit_price),
                    timeInForce=self.config.TIME_IN_FORCE,
                    leverage=str(leverage)
                )
                if order_result:
                    self.logger.info(f"SELL order placed: {qty} {symbol} @ {latest_price}. SL:{stop_loss_price}, TP:{take_profit_price}")
                    self.total_trades += 1
                else:
                    self.logger.error("Failed to place SELL order.")
            else:
                self.logger.warning("Calculated SELL quantity is too small or zero.")

        # --- Handle BUY Signal (Close existing short position) ---
        elif signal == Signal.BUY and self.current_position and self.current_position['side'] == "Sell":
            self.logger.info(f"Executing BUY signal to close SELL position for {symbol} at {latest_price}.")
            qty_to_close = float(self.current_position['size'])
            order_result = self.bybit_client.close_position(symbol, "Sell", qty_to_close)
            if order_result:
                self.logger.info(f"SELL position closed: {qty_to_close} {symbol} @ {latest_price}.")
                # For demo, simulate win/loss
                if float(self.current_position['unrealisedPnl']) > 0: self.winning_trades += 1
            else:
                self.logger.error("Failed to close SELL position.")

        # --- Handle HOLD Signal ---
        elif signal == Signal.NEUTRAL:
            self.logger.info("Strategy: HOLD. No action taken.")
        
        # Update trading stops if position exists and SL/TP are defined
        if self.current_position and (sl_pct > 0 or tp_pct > 0):
            current_position_side = self.current_position['side']
            entry_price = float(self.current_position['avgPrice'])
            
            if current_position_side == "Buy":
                new_sl = self.bybit_client.round_price(symbol, entry_price * (1 - sl_pct / 100))
                new_tp = self.bybit_client.round_price(symbol, entry_price * (1 + tp_pct / 100))
            else: # Sell
                new_sl = self.bybit_client.round_price(symbol, entry_price * (1 + sl_pct / 100))
                new_tp = self.bybit_client.round_price(symbol, entry_price * (1 - tp_pct / 100))
            
            self.bybit_client.set_trading_stop(symbol, new_sl, new_tp)
            self.logger.debug(f"Updated SL/TP for {symbol} position: SL={new_sl}, TP={new_tp}")

EOF

echo "Creating backend/app.py"
cat << 'EOF' > backend/app.py
import eventlet
eventlet.monkey_patch() # Must be called before other imports that use standard library sockets

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
import asyncio

from config import Config
from bot_core import TradingBotCore
from utils import CustomLogger

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_for_flask_session' # CHANGE THIS IN PRODUCTION
CORS(app) # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') # Allow all origins for demo

# --- Bot Initialization ---
config = Config()
custom_logger = CustomLogger(socketio, max_logs=config.MAX_LOG_ENTRIES)
bot = TradingBotCore(config, socketio, custom_logger)

# Configure Flask's default logger
app.logger.removeHandler(app.logger.handlers[0]) # Remove default console handler
app.logger.addHandler(custom_logger)
app.logger.setLevel(logging.INFO)


@app.route('/')
def index():
    return "Pyrmethus's Neon Grimoire Backend is running!"

# --- API Endpoints ---

@app.route('/api/start', methods=['POST'])
def start_bot():
    try:
        frontend_config = request.get_json()
        if not frontend_config:
            return jsonify({"status": "error", "message": "No configuration provided."}), 400
        
        response = bot.start(frontend_config)
        return jsonify(response)
    except Exception as e:
        app.logger.error(f"Error starting bot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    try:
        response = bot.stop()
        return jsonify(response)
    except Exception as e:
        app.logger.error(f"Error stopping bot: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_bot_status():
    try:
        status_data = bot.get_full_status()
        return jsonify(status_data)
    except Exception as e:
        app.logger.error(f"Error getting bot status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/gemini-insight', methods=['POST'])
async def get_gemini_insight():
    try:
        data = request.get_json()
        prompt_text = data.get('prompt')
        if not prompt_text:
            return jsonify({"status": "error", "message": "No prompt provided."}), 400
        
        # Use the bot's Gemini client to generate insight
        insight_response = await bot.gemini_client.generate_insight(prompt_text)
        
        if insight_response['status'] == 'error':
            return jsonify(insight_response), 500
        
        return jsonify(insight_response)
    except Exception as e:
        app.logger.error(f"Error getting Gemini insight: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# --- WebSocket Endpoints ---

@socketio.on('connect', namespace='/ws/status')
def handle_connect():
    app.logger.info("Client connected to /ws/status WebSocket.")
    # Send initial status and logs to the newly connected client
    emit('dashboard_update', bot.get_full_status(), namespace='/ws/status')

@socketio.on('disconnect', namespace='/ws/status')
def handle_disconnect():
    app.logger.info("Client disconnected from /ws/status WebSocket.")

# --- Main Execution ---
if __name__ == '__main__':
    # Ensure API keys are loaded
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        app.logger.critical("Bybit API keys are not set in .env. Please configure them.")
        exit(1)
    if not config.GEMINI_API_KEY:
        app.logger.warning("Gemini API key is not set in .env. AI features will be disabled.")
    
    app.logger.info(f"Starting Flask backend on port 5000. Testnet: {config.BYBIT_TESTNET}")
    # Use eventlet for SocketIO server
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

EOF

echo "Project '$PROJECT_NAME' created successfully!"
echo ""
echo "--- Next Steps ---"
echo "1. Navigate into the project directory: cd $PROJECT_NAME"
echo "2. Update 'backend/.env' with your actual BYBIT_API_KEY, BYBIT_API_SECRET, and GEMINI_API_KEY."
echo "3. Install backend dependencies: pip install -r backend/requirements.txt"
echo "4. Run the backend: python backend/app.py"
echo "5. Open 'index.html' in your web browser (e.g., by double-clicking it or using a local web server)."
echo ""
echo "Enjoy your enhanced Pyrmethus's Neon Grimoire!"

```

---

### **How to Use the Bash Script:**

1.  **Save the script**: Copy the entire bash code block above and save it to a file named `create_grimoire.sh` (or any `.sh` extension).
2.  **Make it executable**: Open your terminal, navigate to where you saved the file, and run:
    ```bash
    chmod +x create_grimoire.sh
    ```
3.  **Run the script**: Execute the script from your terminal:
    ```bash
    ./create_grimoire.sh
    ```

This will create a new directory named `pyrmethus_grimoire` (or whatever you set `PROJECT_NAME` to) in your current location, containing all the frontend and backend files.

**Important:** Remember to follow the "Next Steps" print
