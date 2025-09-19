#!/bin/bash

# ==============================================================================
# Pyrmethus's Neon Grimoire Project Conjuration Script
# This script creates a complete frontend (HTML/JS/CSS) and backend (Python/Flask)
# project structure for the Pyrmethus's Neon Grimoire bot.
#
# Usage:
#   ./create_grimoire.sh                     # Creates project with default name and placeholders
#   ./create_grimoire.sh my_bot_project      # Creates project with custom name
#   ./create_grimoire.sh --clean             # Removes the default project directory
#   ./create_grimoire.sh my_bot_project --bybit-key YOUR_KEY --bybit-secret YOUR_SECRET --gemini-key YOUR_GEMINI_KEY
# ==============================================================================

# --- Configuration & Defaults ---
PROJECT_NAME="pyrmethus_grimoire"
BYBIT_API_KEY_PLACEHOLDER="YOUR_BYBIT_API_KEY"
BYBIT_API_SECRET_PLACEHOLDER="YOUR_BYBIT_API_SECRET"
GEMINI_API_KEY_PLACEHOLDER="YOUR_GOOGLE_GEMINI_API_KEY"
INSTALL_VENV_AUTO=true # Set to false to skip automatic venv creation/installation

# --- Argument Parsing ---
for arg in "$@"; do
  case $arg in
    --clean)
      CLEANUP=true
      shift # Remove --clean from processing
      ;;
    --bybit-key=*)
      BYBIT_API_KEY="${arg#*=}"
      shift
      ;;
    --bybit-secret=*)
      BYBIT_API_SECRET="${arg#*=}"
      shift
      ;;
    --gemini-key=*)
      GEMINI_API_KEY="${arg#*=}"
      shift
      ;;
    *)
      if [[ ! "$arg" =~ ^-- ]]; then # If it's not a --flag, it's the project name
        PROJECT_NAME="$arg"
      fi
      shift
      ;;
  esac
done

# If specific keys are provided, overwrite placeholders
BYBIT_API_KEY=${BYBIT_API_KEY:-$BYBIT_API_KEY_PLACEHOLDER}
BYBIT_API_SECRET=${BYBIT_API_SECRET:-$BYBIT_API_SECRET_PLACEHOLDER}
GEMINI_API_KEY=${GEMINI_API_KEY:-$GEMINI_API_KEY_PLACEHOLDER}

# --- Cleanup Function ---
if [ "$CLEANUP" = true ]; then
  if [ -d "$PROJECT_NAME" ]; then
    echo "Cleaning up existing project directory: $PROJECT_NAME..."
    rm -rf "$PROJECT_NAME"
    echo "Directory '$PROJECT_NAME' removed."
  else
    echo "Project directory '$PROJECT_NAME' not found. Nothing to clean."
  fi
  exit 0
fi

# --- Pre-requisite Checks ---
check_command() {
  if ! command -v "$1" &> /dev/null; then
    echo "Error: '$1' command not found. Please install it."
    exit 1
  fi
}

check_python_version() {
  PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
  if (( $(echo "$PYTHON_VERSION < 3.8" | bc -l) )); then
    echo "Error: Python 3.8 or higher is required. Found Python $PYTHON_VERSION."
    exit 1
  fi
}

check_command "python3"
check_command "pip3"
check_python_version

# --- Create Project Directory Structure ---
echo "Conjuring Pyrmethus's Neon Grimoire project: $PROJECT_NAME"
mkdir -p "$PROJECT_NAME/backend" "$PROJECT_NAME/frontend"

# --- Navigate into Project Directory ---
cd "$PROJECT_NAME" || { echo "Failed to enter $PROJECT_NAME directory. Exiting."; exit 1; }

# --- Create Frontend Files ---
echo "Creating frontend/index.html"
cat << 'EOF' > frontend/index.html
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Advanced cryptocurrency trading bot with AI-powered insights" />
  <meta name="keywords" content="cryptocurrency, trading bot, AI, Gemini, Bybit, Python, Flask, TailwindCSS, Socket.IO" />
  <meta name="author" content="Pyrmethus" />
  <title>Pyrmethus’s Neon Grimoire</title>

  <!-- Favicon (optional, add your own) -->
  <!-- <link rel="icon" href="/favicon.ico" type="image/x-icon"> -->

  <!-- Tailwind v3 CDN with plugins -->
  <script src="https://cdn.tailwindcss.com?plugins=typography,forms"></script>
  <script>
    // TailwindCSS config to safely include dynamic classes for glows, text colors, etc.
    tailwind.config = {
      darkMode: '[data-theme="dark"]', // Enable dark mode based on data-theme attribute
      safelist: [
        { pattern: /^(bg|text|border|glow|from|to|via)-(red|green|blue|purple|pink|cyan|yellow|fuchsia|slate|indigo|lime|teal|emerald|orange|violet)-(300|400|500|600|700)$/ },
        { pattern: /^animate-(pulse|spin|bounce|ping)$/ },
        { pattern: /^shadow-/, variants: ['hover'] }
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
    /* ---------- CSS Variables (Semantic Naming) ---------- */
    :root {
      /* Dark Theme */
      --c-bg-app: #020617; /* slate-950 */
      --c-bg-section: #0F172A; /* slate-900 */
      --c-bg-card: #1E293B; /* slate-800 */
      --c-bg-input: #334155; /* slate-700 */
      --c-border-dark: #334155; /* slate-700 */
      --c-text-primary: #E2E8F0; /* slate-200 */
      --c-text-secondary: #94A3B8; /* slate-400 */
      --c-text-tertiary: #475569; /* slate-600 */
      
      /* Accent Colors */
      --c-purple: #A855F7; /* purple-500 */
      --c-pink: #EC4899; /* pink-500 */
      --c-green: #10B981; /* green-500 */
      --c-cyan: #06B6D4; /* cyan-500 */
      --c-red: #EF4444; /* red-500 */
      --c-yellow: #F59E0B; /* yellow-500 */
      --c-blue: #3B82F6; /* blue-500 */

      /* Light Theme Overrides */
      --c-bg-app-light: #F8FAFC; /* slate-50 */
      --c-bg-section-light: #FFFFFF; /* white */
      --c-bg-card-light: #F9FAFB; /* slate-50 */
      --c-bg-input-light: #F9FAFB; /* slate-50 */
      --c-border-light: #E5E7EB; /* slate-200 */
      --c-text-primary-light: #1E293B; /* slate-800 */
      --c-text-secondary-light: #64748B; /* slate-600 */
    }

    /* Base styles */
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { 
      font-family: 'Inter', system-ui, sans-serif; 
      background: var(--c-bg-app); 
      color: var(--c-text-primary);
      transition: all 0.3s ease;
      position: relative;
      min-height: 100vh;
    }
    
    /* Light theme overrides */
    [data-theme="light"] body { background: var(--c-bg-app-light); color: var(--c-text-primary-light); }
    [data-theme="light"] section { background: var(--c-bg-section-light); border-color: var(--c-border-light); box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1); }
    [data-theme="light"] #logArea { background: var(--c-bg-card-light); border-color: var(--c-border-light); }
    [data-theme="light"] .input-field { background: var(--c-bg-input-light); color: var(--c-text-primary-light); border-color: var(--c-border-light); }
    [data-theme="light"] .metric-card { background: var(--c-bg-card-light); border-color: var(--c-border-light); }
    [data-theme="light"] .connection-status { background: rgba(255,255,255,0.8); border-color: var(--c-border-light); color: var(--c-text-primary-light); }
    [data-theme="light"] .toast { background: var(--c-bg-section-light); color: var(--c-text-primary-light); border-color: var(--c-border-light); }
    [data-theme="light"] .kbd { background: var(--c-bg-card-light); border-color: var(--c-border-light); color: var(--c-text-primary-light); }
    [data-theme="light"] .modal-content { background: var(--c-bg-section-light); border-color: var(--c-border-light); color: var(--c-text-primary-light); }
    [data-theme="light"] ::-webkit-scrollbar-track { background: var(--c-bg-card-light); }
    [data-theme="light"] ::-webkit-scrollbar-thumb { background: var(--c-slate-400); }


    /* Animated background */
    @keyframes float {
      0%, 100% { transform: translateY(0) rotate(0deg); }
      50% { transform: translateY(-20px) rotate(1deg); }
    }
    
    .bg-particles {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background-image: 
        radial-gradient(circle at 20% 50%, rgba(168, 85, 247, 0.05) 0%, transparent 50%), /* purple */
        radial-gradient(circle at 80% 80%, rgba(236, 72, 153, 0.05) 0%, transparent 50%), /* pink */
        radial-gradient(circle at 50% 10%, rgba(16, 185, 129, 0.03) 0%, transparent 50%); /* green */
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

    /* Glow utilities (subtler) */
    .glow-purple { box-shadow: 0 0 8px var(--c-purple); }
    .glow-pink { box-shadow: 0 0 8px var(--c-pink); }
    .glow-green { box-shadow: 0 0 8px var(--c-green); }
    .glow-red { box-shadow: 0 0 8px var(--c-red); }

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
      z-index: 1;
    }
    .btn:active::before {
      width: 300px; height: 300px;
    }
    .btn span { position: relative; z-index: 2; } /* Ensure text is above ripple */

    /* Input styles */
    .input-field {
      background: var(--c-bg-input);
      color: var(--c-text-primary);
      border: 1px solid var(--c-border-dark);
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
    ::-webkit-scrollbar-track { background: var(--c-bg-card); }
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
    .log-entry.success { border-left-color: var(--c-green); color: #86EFAC; } /* green-300 */
    .log-entry.info { border-left-color: var(--c-cyan); color: #67E8F9; } /* cyan-300 */
    .log-entry.warning { border-left-color: var(--c-yellow); color: #FACC15; } /* yellow-300 */
    .log-entry.error { border-left-color: var(--c-red); color: #F87171; } /* red-300 */
    .log-entry.signal { border-left-color: var(--c-pink); color: var(--c-pink); }
    .log-entry.llm { border-left-color: var(--c-purple); color: var(--c-purple); }

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
      background: var(--c-bg-card);
      border: 2px solid var(--c-border-dark);
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
    .metric-card:hover { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(0,0,0,0.2); }

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
      background: rgba(47, 60, 80, 0.7); /* Custom slate-700 with alpha */
      border: 1px solid var(--c-slate-600);
      color: var(--c-slate-200);
    }
    [data-theme="light"] .connection-status {
      background: rgba(249, 250, 251, 0.7); /* Custom slate-50 with alpha */
    }
    .connection-status.connected {
      background: rgba(16, 185, 129, 0.1); /* green-500 with alpha */
      border: 1px solid rgba(16, 185, 129, 0.3);
      color: var(--c-green);
    }
    .connection-status.polling {
      background: rgba(245, 158, 11, 0.1); /* yellow-500 with alpha */
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: var(--c-yellow);
    }
    .connection-status.disconnected {
      background: rgba(239, 68, 68, 0.1); /* red-500 with alpha */
      border: 1px solid rgba(239, 68, 68, 0.3);
      color: var(--c-red);
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
      background: var(--c-bg-card);
      color: var(--c-text-primary);
      padding: 1rem 1.5rem;
      border-radius: 0.5rem;
      box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
      transform: translateX(100%);
      opacity: 0;
      transition: transform 0.3s ease-out, opacity 0.3s ease-out;
      max-width: 320px;
      border: 1px solid var(--c-border-dark);
      pointer-events: auto; /* Re-enable pointer events for the toast itself */
      will-change: transform, opacity; /* Hint to browser for animation performance */
    }
    .toast.show { transform: translateX(0); opacity: 1; }
    .toast.success { border-color: var(--c-green); }
    .toast.error { border-color: var(--c-red); }
    .toast.warning { border-color: var(--c-yellow); }
    .toast.info { border-color: var(--c-blue); }

    /* Keyboard shortcuts hint */
    .kbd {
      background: var(--c-bg-card);
      border: 1px solid var(--c-border-dark);
      border-radius: 0.25rem;
      padding: 0.125rem 0.375rem;
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      color: var(--c-text-secondary);
    }

    /* Modal */
    .modal {
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.7); /* Darker overlay */
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.3s ease-in-out;
    }
    .modal.active {
      opacity: 1;
      pointer-events: auto;
    }
    .modal-content {
      background: var(--c-bg-card);
      border: 1px solid var(--c-border-dark);
      border-radius: 0.75rem;
      padding: 2rem;
      max-width: 500px;
      width: 90%;
      max-height: 90vh;
      overflow-y: auto;
      transform: scale(0.9);
      opacity: 0;
      transition: transform 0.3s ease-in-out, opacity 0.3s ease-in-out;
    }
    .modal.active .modal-content {
      transform: scale(1);
      opacity: 1;
    }

    /* Collapsible sections */
    .collapsible {
      overflow: hidden;
      transition: max-height 0.3s ease-in-out;
    }
    .collapsible.collapsed {
      max-height: 0 !important;
    }

    /* Search highlight */
    .highlight {
      background: rgba(250, 204, 21, 0.3); /* yellow-400 with alpha */
      border-radius: 2px;
      padding: 0 2px;
    }

    /* Loading skeleton */
    @keyframes skeleton-loading {
      0% { background-position: 200% 0; }
      100% { background-position: -200% 0; }
    }
    .skeleton {
      background: linear-gradient(90deg, var(--c-bg-card) 25%, var(--c-bg-section) 50%, var(--c-bg-card) 75%);
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
  <div id="connectionStatus" class="connection-status disconnected no-print" role="status" aria-live="polite">
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
        <div class="flex items-center space-x-2">
            <label for="backendUrl" class="text-sm text-slate-400">Backend:</label>
            <input type="text" id="backendUrl" class="input-field w-40 text-sm" placeholder="http://127.0.0.1:5000" title="Set custom backend URL" />
        </div>
      </div>
    </header>

    <!-- ---------- CONFIGURATION ---------- -->
    <section class="bg-slate-900 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-purple-600 transition-all">
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
            <span>📋 Copy</span>
          </button>
          <button id="importConfig" class="btn px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300" title="Import configuration">
            <span>📂 Import</span>
          </button>
          <button id="resetConfig" class="btn px-4 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-slate-300" title="Reset to defaults">
            <span>🔄 Reset</span>
          </button>
        </div>
      </div>
    </section>

    <!-- ---------- DASHBOARD ---------- -->
    <section class="bg-slate-900 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-green-600 transition-all">
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
          <span>✨ Ask Gemini for Market Insight</span>
        </button>
        <button id="exportLogs" class="btn flex-1 py-3 rounded-lg bg-slate-700 hover:bg-slate-600 text-blue-300 font-bold">
          <span>📊 Export Trading Logs</span>
        </button>
      </div>
      
      <p class="mt-4 text-xs text-slate-500 text-right">
        Last update: <span id="lastUpdate">—</span>
      </p>
    </section>

    <!-- ---------- LOGS ---------- -->
    <section class="bg-slate-900 p-6 rounded-xl shadow-lg border-2 border-slate-700 hover:border-blue-600 transition-all">
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
            <span>Clear</span>
          </button>
        </div>
      </div>
      
      <div id="logArea" class="bg-slate-800 p-4 rounded-lg scrollable-log text-xs font-mono" 
           aria-live="polite" aria-atomic="false">
        <div class="log-entry info" data-type="info">
          <span class="text-slate-500 mr-2">[00:00:00]</span><span>Awaiting your command, Master Pyrmethus…</span>
        </div>
      </div>
      
      <div class="mt-4 flex justify-between items-center text-xs text-slate-500">
        <span>Total logs: <span id="logCount">1</span></span>
        <span>Filtered: <span id="filteredLogCount">1</span></span>
      </div>
    </section>
  </main>

  <!-- ---------- MODALS ---------- -->
  <!-- Keyboard Shortcuts Modal -->
  <div id="shortcutsModal" class="modal" role="dialog" aria-modal="true" aria-labelledby="shortcutsModalTitle">
    <div class="modal-content">
      <h3 id="shortcutsModalTitle" class="text-xl font-bold mb-4">Keyboard Shortcuts</h3>
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
  <div id="toastContainer" aria-live="polite" aria-atomic="true"></div>

  <!-- ---------- AUDIO ---------- -->
  <audio id="notificationSound" preload="auto">
    <source src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2/LDciUFLIHO8tiJNwgZaLvt559NEAxQp+PwtjMcBjiR1/LMeSwFJHfH8N2QQAoUXrTp66hVFApGn+DyvmwhBi2Gy/DUdw0..." type="audio/wav">
  </audio>

  <script>
    // Enhanced configuration
    const APP_CONFIG = {
      VERSION: '2.1.0',
      SOUNDS_ENABLED_KEY: 'pyrmethus_sounds_enabled',
      THEME_KEY: 'pyrmethus_theme',
      CONFIG_DRAFT_KEY: 'pyrmethus_config_draft',
      BACKEND_URL_KEY: 'pyrmethus_backend_url',
      RECONNECT_DELAY: 5000, // For Socket.IO & polling
      MAX_LOG_ENTRIES: 1000,
      NOTIFICATION_DURATION: 5000,
      DEFAULT_BACKEND_URL: 'http://127.0.0.1:5000'
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
            this.audio.volume = 0.3; // Prevent jarring sounds
            this.audio.play().catch(() => {}); // Prevent DOMException if not user-initiated
          }
        },
        toggle() {
          this.enabled = !this.enabled;
          localStorage.setItem(APP_CONFIG.SOUNDS_ENABLED_KEY, this.enabled);
          updateSoundButton();
          Toast.show(`Sounds ${this.enabled ? 'On' : 'Off'}`, 'info', 2000);
        }
      };

      // Toast notification system
      const Toast = {
        show(message, type = 'info', duration = APP_CONFIG.NOTIFICATION_DURATION) {
          const toast = document.createElement('div');
          toast.className = `toast ${type}`;
          toast.innerHTML = `
            <div class="flex items-center justify-between">
              <span>${escapeHtml(message)}</span>
              <button onclick="this.parentElement.parentElement.remove()" class="ml-4 text-slate-400 hover:text-slate-200" aria-label="Close notification">✕</button>
            </div>
          `;
          $('#toastContainer').appendChild(toast);
          requestAnimationFrame(() => toast.classList.add('show'));
          
          if (type === 'error' || type === 'success' || type === 'warning') {
            SoundManager.play(type);
          }
          
          setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => toast.remove(), 300); // Remove after fade-out transition
          }, duration);
        }
      };

      // Enhanced logger (frontend side)
      const log = (() => {
        const area = $('#logArea');
        let logsData = []; // Store log data objects for filtering/search
        let currentLogId = 0; // Unique ID for each log entry if not from backend

        return (message, type = 'info', timestamp_ms = Date.now(), fromBackend = false) => {
          const timestamp = new Date(timestamp_ms);
          const timeStr = timestamp.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
          
          // Only assign new ID if not from backend (backend logs already have unique timestamps)
          const entryId = fromBackend ? timestamp_ms : ++currentLogId;

          const entry = { message, type, timestamp_ms, id: entryId };
          
          // Check for duplicates if from backend (to avoid adding the same log twice on WS reconnect or initial fetch)
          if (fromBackend && logsData.some(l => l.timestamp_ms === timestamp_ms && l.message === message)) {
            return;
          }

          logsData.push(entry);
          if (logsData.length > APP_CONFIG.MAX_LOG_ENTRIES) {
            logsData.shift();
            // Remove the oldest log entry from DOM if it exists and matches
            const oldestDomLog = area.querySelector('.log-entry:first-child');
            if (oldestDomLog && oldestDomLog.dataset.entryId == logsData[0]?.id) {
              oldestDomLog.remove();
            }
          }
          
          const div = document.createElement('div');
          div.className = `log-entry ${type}`;
          div.dataset.type = type;
          div.dataset.timestamp = timestamp.toISOString();
          div.dataset.originalText = message; // Store original message for search/filter
          div.dataset.entryId = entryId;
          div.innerHTML = `<span class="text-slate-500 mr-2">[${timeStr}]</span><span>${escapeHtml(message)}</span>`;
          area.appendChild(div);
          
          requestAnimationFrame(() => {
            area.scrollTop = area.scrollHeight; // Auto-scroll to bottom
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
        let timeoutId;
        
        for (let i = 0; i < retries; i++) {
          try {
            timeoutId = setTimeout(() => controller.abort(), timeout); // Set timeout for each attempt
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
              const errorText = await response.text();
              let errorMessage = response.statusText;
              try {
                const errorJson = JSON.parse(errorText);
                errorMessage = errorJson.message || errorJson.error || errorMessage;
              } catch {
                errorMessage = errorText || errorMessage;
              }
              throw new Error(`HTTP ${response.status}: ${errorMessage}`);
            }
            
            return response;
          } catch (error) {
            clearTimeout(timeoutId);
            // Don't retry if it's an abort from timeout, just rethrow
            if (error.name === 'AbortError' && i === retries -1) {
                throw new Error(`Request timed out after ${timeout}ms.`);
            }
            
            if (i === retries - 1) throw error; // If last retry, rethrow original error
            
            const nextDelay = delay * Math.pow(2, i); // Exponential backoff
            log(`Fetch failed: ${error.message}. Retrying in ${nextDelay}ms...`, 'warning');
            await new Promise(resolve => setTimeout(resolve, nextDelay));
          }
        }
      }

      /* ========================= CONSTANTS ========================= */
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
      
      // Function to generate numeric inputs based on NUM_FIELDS
      const createNumericInputs = () => {
        numericFieldsContainer.innerHTML = ''; // Clear existing
        NUM_FIELDS.forEach(([id, label, def, min, max, step]) => {
          const clone = template.cloneNode(true);
          const labelEl = clone.querySelector('label');
          const inputEl = clone.querySelector('input');
          labelEl.htmlFor = id;
          labelEl.textContent = label;
          Object.assign(inputEl, { id, value: def, min, max, step });
          
          inputEl.addEventListener('input', (e) => {
            const value = parseFloat(e.target.value);
            if (!isNaN(value)) {
              e.target.value = clamp(value, min, max);
            }
            saveDraftConfig(); // Save draft on input change
          });
          numericFieldsContainer.appendChild(clone);
        });
      };
      createNumericInputs(); // Initial creation

      // Create metric cards
      const metricsGrid = $('#metricsGrid');
      METRICS.forEach(([label, id, colorClass, glowColorVar]) => {
        const card = document.createElement('div');
        card.className = 'metric-card';
        if (glowColorVar) card.style.setProperty('--glow-color', `var(${glowColorVar})`);
        card.innerHTML = `
          <p class="text-xs sm:text-sm text-slate-400">${label}</p>
          <p id="${id}" class="text-lg sm:text-xl font-bold ${colorClass} mt-1" aria-live="polite">
            <span class="skeleton" style="display: inline-block; width: 60px; height: 1.5em;"></span>
          </p>
        `;
        metricsGrid.appendChild(card);
      });

      /* ========================= STATE MANAGEMENT ======================== */
      let botRunning = false;
      let socket = null;
      let lastLogTimestamp = 0; // To prevent log duplication from initial fetch/reconnects
      let backendUrl = localStorage.getItem(APP_CONFIG.BACKEND_URL_KEY) || APP_CONFIG.DEFAULT_BACKEND_URL;
      const backendUrlInput = $('#backendUrl');
      backendUrlInput.value = backendUrl;

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
          const res = await fetchWithRetry(`${backendUrl}/api/start`, {
            method: 'POST',
            body: JSON.stringify(config),
          });
          
          const data = await res.json();
          if (data.status === 'success') {
            log('Bot ritual initiated ✔️', 'success');
            Toast.show('Bot started successfully!', 'success');
            setRunningState(true);
            connectWebSocket(); // Attempt to connect WS, polling will happen until WS is established
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
          const res = await fetchWithRetry(`${backendUrl}/api/stop`, { method: 'POST' });
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
        
        if (!isRunning && socket && socket.connected) {
          socket.disconnect(); // Explicitly disconnect WS if bot stops
        } else if (isRunning && !socket?.connected) {
          connectWebSocket(); // If bot starts, ensure WS is connected
        }
        updateConnectionStatus(isRunning ? (socket?.connected ? 'connected' : 'polling') : 'disconnected');
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
      let reconnectAttempts = 0;
      let reconnectTimeoutId = null;

      function connectWebSocket() {
        if (!backendUrl) {
            log("Backend URL is not set. Cannot establish WebSocket connection.", "error");
            updateConnectionStatus('disconnected', 'No Backend URL');
            return;
        }

        if (socket && socket.connected) {
          log('WebSocket already connected.', 'info');
          updateConnectionStatus('connected');
          return;
        }
        if (socket && socket.io.readyState === 'opening') { // Check if connection is in progress
            log('WebSocket connection already in progress.', 'info');
            updateConnectionStatus('connecting');
            return;
        }
        
        log('Attempting WebSocket connection...', 'info');
        updateConnectionStatus('connecting');

        // Ensure the namespace matches the backend (Flask-SocketIO)
        // Note: `io()` without a namespace connects to the root. If the backend uses '/ws/status', it must be specified.
        socket = io(backendUrl + '/ws/status', {
            reconnection: true, // Let client handle reconnection attempts
            reconnectionAttempts: Infinity, // Unlimited reconnection attempts
            reconnectionDelay: 1000, // Initial delay
            reconnectionDelayMax: APP_CONFIG.RECONNECT_DELAY * 2, // Max delay
            timeout: 10000,
            autoConnect: false // Explicitly connect later
        });

        socket.on('connect', () => {
          log('WebSocket connected 📡', 'success');
          updateConnectionStatus('connected');
          reconnectAttempts = 0; // Reset attempts on successful connect
          clearTimeout(reconnectTimeoutId);
        });

        socket.on('disconnect', (reason) => {
          log(`WebSocket disconnected: ${reason}`, 'warning');
          updateConnectionStatus('disconnected', 'WS Disconnected');
          // If bot is supposed to be running, fall back to polling logic
          if (botRunning) {
            log('Bot is running, attempting to re-fetch status via polling.', 'info');
            // Start polling if WS disconnects while bot is running
            // Polling will then periodically emit 'dashboard_update' via HTTP
            fetchDashboardStatus(); 
          }
        });

        socket.on('connect_error', (error) => {
          log(`WebSocket connection error: ${error.message}`, 'error');
          updateConnectionStatus('disconnected', 'WS Error');
          // Fall back to polling only if bot is running and WS failed
          if (botRunning) {
            log('WS error, falling back to polling for updates...', 'warning');
            fetchDashboardStatus();
          }
        });

        socket.on('dashboard_update', (data) => {
          updateDashboard(data);
          updateConnectionStatus('connected'); // Confirm WS is active
        });

        socket.on('log_entry', (logEntry) => {
          // Only add logs that haven't been added from the initial dashboard_update fetch
          if (logEntry.timestamp > lastLogTimestamp) {
            log(logEntry.message, logEntry.level, logEntry.timestamp, true); // true indicates fromBackend
            lastLogTimestamp = logEntry.timestamp;
          }
        });
        socket.connect(); // Initiate connection
      }

      // Fallback for initial status fetch and periodic polling if WS fails
      async function fetchDashboardStatus() {
        clearTimeout(reconnectTimeoutId); // Clear any pending polling timeouts
        try {
          const res = await fetchWithRetry(`${backendUrl}/api/status`, {}, 1, 1000, 4000); // Short timeout for polling
          const data = await res.json();
          updateDashboard(data);
          // Only update status to polling if WS is not connected and bot is running
          if (!socket?.connected && botRunning) {
            updateConnectionStatus('polling'); 
          }
        } catch (e) {
          log(`Dashboard fetch failed: ${e.message}`, 'error');
          updateConnectionStatus('disconnected', 'Connection Error');
        } finally {
          // Schedule next poll only if bot is running and WS is not connected
          if (botRunning && !socket?.connected) {
            reconnectTimeoutId = setTimeout(fetchDashboardStatus, APP_CONFIG.RECONNECT_DELAY);
          }
        }
      }

      function updateDashboard(data) {
        const dashboard = data.dashboard || {};
        
        METRICS.forEach(([_, id]) => {
          const el = $(`#${id}`);
          if (el) {
            const value = dashboard[id] ?? '---';
            const skeleton = el.querySelector('.skeleton');
            if (skeleton) skeleton.remove(); // Remove skeleton once data is received
            el.textContent = value; // Backend sends pre-formatted values
            // Add dynamic class for price change
            if (id === 'priceChange' && value !== '---') {
                el.classList.remove('text-green-500', 'text-red-500');
                if (parseFloat(value) > 0) el.classList.add('text-green-500');
                else if (parseFloat(value) < 0) el.classList.add('text-red-500');
                else el.classList.add('text-slate-500'); // Neutral
            }
            // Add dynamic class for PnL
            if (id === 'positionPnL' && value !== '---') {
                el.classList.remove('text-green-500', 'text-red-500');
                if (parseFloat(value) > 0) el.classList.add('text-green-500');
                else if (parseFloat(value) < 0) el.classList.add('text-red-500');
            }
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
        if (!backendUrl) {
            Toast.show("Backend URL not set. Cannot ask Gemini.", "error");
            return;
        }

        const btn = $('#askGemini');
        btn.disabled = true;
        btn.innerHTML = '<span>Consulting the Oracle…<span class="spinner"></span></span>';
        log('Consulting the Gemini Oracle...', 'llm');
        
        const prompt = botRunning ? 
          `Analyze ${$('#symbol').value} with: Price: ${$('#currentPrice').textContent}, Supertrend: ${$('#stDirection').textContent}, RSI: ${$('#rsiValue').textContent}. Provide a concise, neutral analysis (max 150 words).`
          : `Provide a general market outlook for ${$('#symbol').value} based on recent trends. (max 150 words).`;

        try {
          const res = await fetchWithRetry(`${backendUrl}/api/gemini-insight`, {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt })
          }, 1, 1000, 15000);
          
          const data = await res.json();
          if (data.status === 'success') {
            log(`— Gemini Insight —\n${data.insight}`, 'llm');
            Toast.show('Gemini insight received', 'success');
          } else {
            log(`Gemini error: ${data.message}`, 'error');
            Toast.show(`Failed to get Gemini insight: ${data.message}`, 'error');
          }
        } catch (e) {
          log(`Oracle network error: ${e.message}`, 'error');
          Toast.show(`Failed to get Gemini insight: ${e.message}`, 'error');
        } finally {
          btn.disabled = false;
          btn.innerHTML = '<span>✨ Ask Gemini for Market Insight</span>';
        }
      }

      function exportLogs() {
        const text = $$('#logArea .log-entry').map(el => {
          const timestamp = new Date(el.dataset.timestamp).toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
          return `[${timestamp}] ${el.dataset.originalText || el.textContent}`; // Use original text
        }).join('\n');
        const blob = new Blob([text], {type: 'text/plain;charset=utf-8'});
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `pyrmethus_logs_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(a); // Required for Firefox
        a.click();
        document.body.removeChild(a); // Clean up
        URL.revokeObjectURL(a.href);
        Toast.show('Logs exported.', 'info');
      }
      
      async function copyConfig() {
        try {
          await navigator.clipboard.writeText(JSON.stringify(getConfig(), null, 2));
          log('Config copied to clipboard.', 'success');
          Toast.show('Config copied to clipboard.', 'success');
        } catch (e) {
          log('Could not copy to clipboard. Check permissions or try manually.', 'error');
          Toast.show('Could not copy to clipboard. Try manually.', 'error');
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
            Toast.show('Invalid configuration file: ' + e.message, 'error');
            log(`Invalid JSON provided: ${e.message}`, 'error');
          }
        };
        input.click();
      }

      function resetConfig() {
        if (confirm('Reset all settings to defaults? This cannot be undone.')) {
          createNumericInputs(); // Re-create numeric fields to reset to defaults
          $('#symbol').value = 'BTCUSDT'; // Default symbol
          $('#interval').value = '60'; // Default interval
          Toast.show('Configuration reset to defaults', 'info');
          localStorage.removeItem(APP_CONFIG.CONFIG_DRAFT_KEY);
        }
      }

      // Log controls
      const logSearch = $('#logSearch');
      const logFilter = $('#logFilter');
      
      const filterLogs = debounce(() => {
        const searchTerm = logSearch.value.toLowerCase().trim();
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
        // The filterLogs function already updates filteredLogCount correctly based on display style
        // So we only need to update total here if filterLogs is called separately.
        $('#logCount').textContent = total;
        // Re-call filterLogs just in case total count changes without filter/search changes
        filterLogs();
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
          // A short delay might be needed if scrollHeight is not immediately accurate
          setTimeout(() => {
            if (!content.classList.contains('collapsed')) {
              content.style.maxHeight = 'none';
            }
          }, 300); // Match CSS transition duration
          icon.style.transform = 'rotate(0)';
        }
      });

      // Keyboard shortcuts modal
      $('#keyboardShortcuts').addEventListener('click', () => {
        $('#shortcutsModal').classList.add('active');
        $('#shortcutsModal').focus(); // Focus modal for accessibility
      });

      window.closeModal = (modalId) => {
        $(`#${modalId}`).classList.remove('active');
      };

      // Close modal on escape key
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          const activeModal = $('.modal.active');
          if (activeModal) {
            closeModal(activeModal.id);
          }
        }
      });

      // Global keyboard shortcuts
      document.addEventListener('keydown', (e) => {
        // Don't trigger shortcuts when typing in inputs or modals are open
        if (e.target.matches('input, textarea, select') || $('.modal.active')) return;
        
        if (e.ctrlKey || e.metaKey) { // Ctrl for Windows/Linux, Cmd for macOS
          switch (e.key.toLowerCase()) {
            case 'enter':
              e.preventDefault();
              handleStartStop();
              break;
            case 'd':
              e.preventDefault();
              SoundManager.toggle();
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
          e.preventDefault(); // Prevent browser refresh
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
      // These are added dynamically in createNumericInputs
      $('#symbol').addEventListener('change', debounce(saveDraftConfig, 500));
      $('#interval').addEventListener('change', debounce(saveDraftConfig, 500));
      
      // Event Listeners
      $('#startBot').addEventListener('click', handleStartStop);
      $('#askGemini').addEventListener('click', askGemini);
      $('#clearLogs').addEventListener('click', () => { 
        if (confirm('Clear all logs? This will not affect backend logs stored in memory.')) {
          $('#logArea').innerHTML = '<div class="log-entry info" data-type="info"><span class="text-slate-500 mr-2">[00:00:00]</span><span>Logs cleared. Awaiting commands...</span></div>'; 
          logsData = []; // Clear frontend log data
          lastLogTimestamp = Date.now(); // Reset timestamp for new logs
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
      $('#themeToggle').addEventListener('click', () => {
        const currentTheme = document.documentElement.dataset.theme;
        applyTheme(currentTheme === 'light' ? 'dark' : 'light');
      });
      $('#soundToggle').addEventListener('click', () => SoundManager.toggle());

      // Backend URL input handling
      backendUrlInput.addEventListener('change', () => {
        const newUrl = backendUrlInput.value.trim();
        if (newUrl && newUrl !== backendUrl) {
            backendUrl = newUrl;
            localStorage.setItem(APP_CONFIG.BACKEND_URL_KEY, newUrl);
            log(`Backend URL updated to: ${newUrl}`, 'info');
            Toast.show(`Backend URL set to ${newUrl}. Attempting reconnect.`, 'info');
            // Reconnect WebSocket with new URL
            if (socket) {
                socket.disconnect();
                socket = null; // Clear old socket
            }
            if (botRunning) {
                connectWebSocket();
            } else {
                fetchDashboardStatus(); // Just fetch status
            }
        } else if (!newUrl) {
            backendUrl = APP_CONFIG.DEFAULT_BACKEND_URL;
            backendUrlInput.value = backendUrl;
            localStorage.setItem(APP_CONFIG.BACKEND_URL_KEY, backendUrl);
            log(`Backend URL reset to default: ${backendUrl}`, 'warning');
            Toast.show(`Backend URL reset to default.`, 'warning');
            if (socket) {
                socket.disconnect();
                socket = null;
            }
            if (botRunning) {
                connectWebSocket();
            } else {
                fetchDashboardStatus();
            }
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
# No quotes around EOF for .env so that variables can be substituted directly if needed,
# but we are filling with placeholders, so it's safe.
cat << EOF > backend/.env
BYBIT_API_KEY="${BYBIT_API_KEY}"
BYBIT_API_SECRET="${BYBIT_API_SECRET}"
GEMINI_API_KEY="${GEMINI_API_KEY}"
BYBIT_TESTNET="true"
# FLASK_APP=app.py
# FLASK_DEBUG=1
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
gunicorn==21.2.0 # For production deployment
EOF

echo "Creating backend/utils.py"
cat << 'EOF' > backend/utils.py
import logging
from datetime import datetime
from flask_socketio import SocketIO, emit
import threading
from typing import Dict, Any, List, Optional

class CustomLogger(logging.Handler):
    """
    A custom logging handler that stores logs in memory and can emit them via SocketIO.
    """
    def __init__(self, socketio: SocketIO, max_logs: int = 200):
        super().__init__()
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = max_logs
        self.socketio = socketio
        self.lock = threading.Lock() # Protects self.logs
        # Format for logs stored in memory (raw message) vs emitted (formatted message)
        self.setFormatter(logging.Formatter('%(message)s')) 
        self.original_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')


    def emit(self, record):
        # Format for internal storage (without timestamp prefix)
        formatted_message = self.format(record) 
        
        # Format for display (with timestamp prefix)
        display_message = self.original_formatter.format(record)

        log_entry = {
            "timestamp": datetime.now().timestamp() * 1000, # Milliseconds for frontend
            "level": record.levelname.lower(),
            "message": display_message, # Store formatted message for sending to frontend
            "raw_message": formatted_message # Store raw for potential re-use or internal processing
        }
        with self.lock:
            self.logs.append(log_entry)
            if len(self.logs) > self.max_logs:
                self.logs.pop(0)
        
        # Emit log via WebSocket
        try:
            self.socketio.emit('log_entry', log_entry, namespace='/ws/status')
        except RuntimeError:
            # This can happen if emit is called outside of a Flask context or during shutdown
            # In a production setup, consider a queue for logs during high load or shutdown
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

def format_percent(value: Any, include_sign: bool = True) -> str:
    try:
        if value is None or value == '---': return "---"
        sign = "+" if include_sign and float(value) > 0 else ""
        return f"{sign}{float(value):.2f}%"
    except (ValueError, TypeError):
        return "---"

def format_num(value: Any) -> str:
    try:
        if value is None or value == '---': return "---"
        # Check if it's an integer for cleaner display
        if float(value).is_integer():
            return f"{int(value):,}"
        return f"{float(value):,.2f}" # Default to 2 decimal places for floats
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
    BYBIT_TESTNET = os.getenv("BYBIT_TESTNET", "true").lower() == "true" # Default to testnet if not specified

    # Default Trading Parameters (can be overridden by frontend)
    DEFAULT_SYMBOL = "BTCUSDT"
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
    
    # Hardcoded indicator parameters (less likely to be changed frequently)
    DEFAULT_SUPERTREND_LENGTH = 10
    DEFAULT_SUPERTREND_MULTIPLIER = 3.0
    DEFAULT_RSI_LENGTH = 14
    DEFAULT_RSI_OVERBOUGHT = 70
    DEFAULT_RSI_OVERSOLD = 30

    # Bot operation settings
    POLLING_INTERVAL_SECONDS = 5 # How often the bot loop runs and sends updates
    MARKET_DATA_FETCH_LIMIT = 200 # Max historical klines for indicator calculation
    MAX_LOG_ENTRIES = 200 # Max logs to keep in memory in CustomLogger

    # Trading Strategy Settings
    MIN_SIGNAL_STRENGTH = 2 # Minimum number of bullish/bearish indicators for a trade
    ORDER_TYPE = "Market" # "Market" or "Limit" - Market is simpler for demo
    TIME_IN_FORCE = "GTC" # Good-Till-Canceled
    REDUCE_ONLY = False # Not directly used in place_order, but important for close_position logic

    # AI Model
    GEMINI_MODEL = "gemini-1.5-flash-latest" # Or "gemini-pro"
    GEMINI_MAX_TOKENS = 150 # Max tokens for AI response

    # Backend API URL for Bybit (for HTTP client)
    # Corrected URLs based on testnet status
    if BYBIT_TESTNET:
        BYBIT_API_BASE_URL = "https://api-testnet.bybit.com"
        BYBIT_WS_BASE_URL = "wss://stream-testnet.bybit.com/v5/public/linear"
    else:
        BYBIT_API_BASE_URL = "https://api.bybit.com"
        BYBIT_WS_BASE_URL = "wss://stream.bybit.com/v5/public/linear"

EOF

echo "Creating backend/bybit_api_client.py"
cat << 'EOF' > backend/bybit_api_client.py
import logging
from pybit.unified_trading import HTTP
from typing import Dict, Any, Optional
from decimal import Decimal, ROUND_DOWN, ROUND_UP, InvalidOperation

class BybitAPIClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool, logger: logging.Logger):
        self.session = HTTP(testnet=testnet, api_key=api_key, api_secret=api_secret)
        self.logger = logger
        self.category = "linear" # Default category for this bot (e.g., USDT perpetuals)
        self.instrument_info: Dict[str, Any] = {} # Stores precision info
        self.is_initialized = False
        self._load_instrument_info()

    def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Generic request handler with logging and error checking."""
        if not self.session.api_key or not self.session.api_secret:
            self.logger.error(f"Bybit API keys not configured. Cannot make request to {endpoint}.")
            return None
        try:
            response = getattr(self.session, method)(**kwargs)
            if response and response.get('retCode') == 0:
                return response.get('result')
            else:
                msg = response.get('retMsg', 'Unknown error')
                self.logger.error(f"Bybit API Error ({endpoint}): {msg} (Code: {response.get('retCode')}) - Args: {kwargs}")
                return None
        except Exception as e:
            self.logger.error(f"Bybit API Exception ({endpoint}): {e} - Args: {kwargs}")
            return None

    def _load_instrument_info(self):
        """Fetches and stores instrument info for all trading pairs."""
        try:
            response = self.session.get_instruments_info(category=self.category)
            if response and response.get('retCode') == 0:
                for item in response['result']['list']:
                    self.instrument_info[item['symbol']] = item
                self.logger.info(f"Loaded instrument info for {len(self.instrument_info)} symbols.")
                self.is_initialized = True
            else:
                self.logger.error(f"Failed to load instrument info: {response.get('retMsg', 'Unknown error')}")
                self.is_initialized = False
        except Exception as e:
            self.logger.error(f"Exception loading instrument info: {e}")
            self.is_initialized = False

    def get_kline(self, symbol: str, interval: str, limit: int) -> Optional[Dict[str, Any]]:
        return self._request('get_kline', endpoint='/v5/market/kline', category=self.category, symbol=symbol, interval=interval, limit=limit)

    def get_tickers(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('get_tickers', endpoint='/v5/market/tickers', category=self.category, symbol=symbol)

    def get_positions(self, symbol: str) -> Optional[Dict[str, Any]]:
        # positionIdx: 0 for one-way mode, 1 for Buy, 2 for Sell in hedge mode
        # Assuming one-way mode for simplicity (positionIdx=0)
        return self._request('get_positions', endpoint='/v5/position/list', category=self.category, symbol=symbol)

    def get_wallet_balance(self) -> Optional[Dict[str, Any]]:
        return self._request('get_wallet_balance', endpoint='/v5/account/wallet-balance', accountType="UNIFIED")

    def place_order(self, **kwargs) -> Optional[Dict[str, Any]]:
        return self._request('place_order', endpoint='/v5/order/create', category=self.category, **kwargs)

    def cancel_order(self, orderId: str, symbol: str) -> Optional[Dict[str, Any]]:
        return self._request('cancel_order', endpoint='/v5/order/cancel', category=self.category, orderId=orderId, symbol=symbol)

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        response = self._request('set_leverage', endpoint='/v5/position/set-leverage', category=self.category, symbol=symbol, buyLeverage=str(leverage), sellLeverage=str(leverage))
        if response:
            self.logger.info(f"Leverage set to {leverage}x for {symbol}.")
            return True
        return False

    def set_trading_stop(self, symbol: str, stopLoss: float, takeProfit: Optional[float] = None) -> bool:
        # positionIdx=0 for one-way mode
        params = {'category': self.category, 'symbol': symbol, 'stopLoss': str(stopLoss), 'positionIdx': 0}
        if takeProfit is not None:
            params['takeProfit'] = str(takeProfit)
        
        response = self._request('set_trading_stop', endpoint='/v5/position/trading-stop', **params)
        if response:
            self.logger.info(f"Trading stops updated for {symbol}: SL={stopLoss}, TP={takeProfit if takeProfit else 'N/A'}")
            return True
        return False

    def close_position(self, symbol: str, side: str, qty: float) -> Optional[Dict[str, Any]]:
        """Closes an open position by placing a market order with reduceOnly=True."""
        # For closing a 'Buy' position, we need to 'Sell'. For 'Sell', we need to 'Buy'.
        opposite_side = "Sell" if side == "Buy" else "Buy"
        
        # Ensure quantity is formatted correctly
        rounded_qty = self.round_qty(symbol, qty)
        if rounded_qty <= 0:
            self.logger.warning(f"Attempted to close position with non-positive quantity: {qty}")
            return None

        self.logger.info(f"Attempting to close {side} position of {rounded_qty} {symbol} by placing a {opposite_side} market order.")
        return self.place_order(
            symbol=symbol,
            side=opposite_side,
            orderType="Market",
            qty=str(rounded_qty),
            reduceOnly=True,
            # closeOnTrigger=False is for conditional orders, not market orders
        )

    # --- Precision Handling ---
    def _get_precision_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.is_initialized:
            self.logger.warning("BybitAPIClient not fully initialized, instrument info missing. Attempting to reload.")
            self._load_instrument_info() # Try to reload
        return self.instrument_info.get(symbol)

    def round_price(self, symbol: str, price: float) -> float:
        info = self._get_precision_info(symbol)
        if not info or 'priceFilter' not in info:
            self.logger.warning(f"No priceFilter info for {symbol}, falling back to 2 decimal places for price.")
            return round(price, 2)
        
        try:
            tick_size = Decimal(info['priceFilter']['tickSize'])
            # Use Decimal for calculations to avoid floating point inaccuracies
            rounded_price = (Decimal(str(price)) / tick_size).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_size
            return float(rounded_price)
        except (InvalidOperation, KeyError) as e:
            self.logger.error(f"Error rounding price for {symbol} with info {info}: {e}. Falling back to 2 decimal places.")
            return round(price, 2)

    def round_qty(self, symbol: str, qty: float) -> float:
        info = self._get_precision_info(symbol)
        if not info or 'lotSizeFilter' not in info:
            self.logger.warning(f"No lotSizeFilter info for {symbol}, falling back to 3 decimal places for quantity.")
            return round(qty, 3)
        
        try:
            qty_step = Decimal(info['lotSizeFilter']['qtyStep'])
            # Use Decimal for calculations
            rounded_qty = (Decimal(str(qty)) / qty_step).quantize(Decimal('1'), rounding=ROUND_DOWN) * qty_step
            return float(rounded_qty)
        except (InvalidOperation, KeyError) as e:
            self.logger.error(f"Error rounding quantity for {symbol} with info {info}: {e}. Falling back to 3 decimal places.")
            return round(qty, 3)

    def get_min_order_qty(self, symbol: str) -> float:
        info = self._get_precision_info(symbol)
        if info and 'lotSizeFilter' in info:
            try:
                return float(info['lotSizeFilter']['minOrderQty'])
            except (ValueError, KeyError):
                self.logger.error(f"Could not parse minOrderQty for {symbol}. Defaulting to 0.001.")
                return 0.001 # Fallback if parsing fails
        return 0.001 # General fallback

EOF

echo "Creating backend/gemini_ai_client.py"
cat << 'EOF' > backend/gemini_ai_client.py
import logging
import asyncio
from typing import Dict, Any
from google.generativeai import GenerativeModel, configure, types
from google.api_core.exceptions import GoogleAPIError

class GeminiAIClient:
    def __init__(self, api_key: Optional[str], model_name: str, logger: logging.Logger, max_tokens: int = 150):
        self.logger = logger
        self.model_name = model_name
        self.max_tokens = max_tokens
        self.model = None
        self.configured = False

        if api_key:
            try:
                configure(api_key=api_key)
                self.model = GenerativeModel(model_name)
                self.configured = True
                self.logger.info(f"Gemini AI client initialized with model: {model_name}")
            except Exception as e:
                self.logger.error(f"Failed to configure Gemini AI with provided API key: {e}. AI features disabled.")
        else:
            self.logger.warning("Gemini API Key not provided. AI features will be disabled.")

    async def generate_insight(self, prompt: str) -> Dict[str, Any]:
        if not self.configured or not self.model:
            return {"status": "error", "message": "Gemini AI is not configured or initialized correctly."}
        try:
            # Set generation configuration for concise output
            generation_config = types.GenerationConfig(
                max_output_tokens=self.max_tokens,
                temperature=0.7, # Slightly creative but still factual
                top_p=0.95,
                top_k=40
            )
            response = await self.model.generate_content_async(prompt, generation_config=generation_config)
            
            # Check if response has content
            if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                return {"status": "success", "insight": response.text.strip()}
            else:
                self.logger.warning(f"Gemini AI generated no content for prompt: {prompt[:100]}...")
                return {"status": "error", "message": "Gemini AI generated an empty response."}
        except GoogleAPIError as e:
            self.logger.error(f"Gemini API Error: {e}")
            return {"status": "error", "message": f"Gemini API error: {e.args[0] if e.args else 'Unknown API Error'}"}
        except Exception as e:
            self.logger.error(f"Gemini AI Generation Error: {e}")
            return {"status": "error", "message": f"Error generating insight: {e}"}

    def build_analysis_prompt(self, dashboard_metrics: Dict[str, Any], config: Dict[str, Any]) -> str:
        """Constructs a detailed prompt for Gemini based on current bot state."""
        # Ensure values are present, or use a placeholder for the AI
        get_metric = lambda key: dashboard_metrics.get(key, 'N/A')
        get_config = lambda key: config.get(key, 'N/A')

        prompt = f"""
        You are a highly experienced cryptocurrency trading analyst. Provide a concise, neutral, and actionable market insight based on the provided live trading data.
        Focus on interpreting the indicators and suggesting potential market movements or trading considerations. Avoid explicit financial advice.
        Keep the analysis under {self.max_tokens} words.

        **Current Bot Configuration:**
        Symbol: {get_config('symbol')}
        Interval: {get_config('interval')} minutes (or 'D' for daily)
        Leverage: {get_config('leverage')}x
        Risk per Trade: {get_config('riskPct')}%
        Stop Loss Target: {get_config('stopLossPct')}%
        Take Profit Target: {get_config('takeProfitPct')}%

        **Live Dashboard Metrics:**
        Current Price: {get_metric('currentPrice')}
        Price Change (Interval): {get_metric('priceChange')}
        Supertrend Direction: {get_metric('stDirection')} (Value: {get_metric('stValue')})
        RSI Value: {get_metric('rsiValue')} (Status: {get_metric('rsiStatus')})
        Ehlers-Fisher Value: {get_metric('fisherValue')}
        MACD Line: {get_metric('macdLine')}
        MACD Signal: {get_metric('macdSignal')}
        MACD Histogram: {get_metric('macdHistogram')}
        Bollinger Bands: Middle={get_metric('bbMiddle')}, Upper={get_metric('bbUpper')}, Lower={get_metric('bbLower')}
        Current Position: {get_metric('currentPosition')} (PnL: {get_metric('positionPnL')})
        Account Balance: {get_metric('accountBalance')}
        Bot Status: {get_metric('botStatus')}

        **Analysis Focus:**
        - Summarize the current trend and momentum.
        - Comment on volatility and any potential breakouts or reversals.
        - Highlight any conflicting signals.
        - Give a brief, neutral outlook.
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
        self.logger.debug(f"Strategy config updated: {config}")

    def calculate_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculates all necessary technical indicators using pandas_ta."""
        if df.empty or len(df) < 2: # Need at least 2 candles for most indicators
            self.logger.debug("DataFrame too small for indicator calculation.")
            return df

        # Ensure numeric types and sorted index
        df = df.astype({'open': float, 'high': float, 'low': float, 'close': float, 'volume': float})
        df = df.sort_index()

        close_prices = df['close']
        high_prices = df['high']
        low_prices = df['low']
        # volume = df['volume'] # Not all indicators use volume

        # --- Trend Indicators ---
        # EMA (Exponential Moving Average) - using MACD periods for consistency
        df[f'EMA_Fast'] = ta.ema(close_prices, length=self.config.get('macdFastPeriod', 12)) 
        df[f'EMA_Slow'] = ta.ema(close_prices, length=self.config.get('macdSlowPeriod', 26)) 

        # MACD
        macd_fast = self.config.get('macdFastPeriod', 12)
        macd_slow = self.config.get('macdSlowPeriod', 26)
        macd_signal = self.config.get('macdSignalPeriod', 9)
        macd_data = ta.macd(close_prices, fast=macd_fast, slow=macd_slow, signal=macd_signal, append=False)
        if macd_data is not None and not macd_data.empty:
            df['MACD'] = macd_data[f'MACD_{macd_fast}_{macd_slow}_{macd_signal}']
            df['MACD_Signal'] = macd_data[f'MACDs_{macd_fast}_{macd_slow}_{macd_signal}']
            df['MACD_Hist'] = macd_data[f'MACDh_{macd_fast}_{macd_slow}_{macd_signal}']
        else:
            self.logger.warning("MACD calculation failed or returned empty data.")

        # Supertrend
        st_length = self.config.get('supertrend_length', 10)
        st_multiplier = self.config.get('supertrend_multiplier', 3.0)
        st_data = ta.supertrend(high_prices, low_prices, close_prices, length=st_length, multiplier=st_multiplier, append=False)
        if st_data is not None and not st_data.empty:
            df['SUPERT_D'] = st_data[f'SUPERTd_{st_length}_{st_multiplier}.0'] # Direction
            df['SUPERT'] = st_data[f'SUPERT_{st_length}_{st_multiplier}.0'] # Value
        else:
            self.logger.warning("Supertrend calculation failed or returned empty data.")

        # --- Momentum Indicators ---
        # RSI
        rsi_length = self.config.get('rsi_length', 14)
        df['RSI'] = ta.rsi(close_prices, length=rsi_length, append=False)
        if df['RSI'].isnull().all():
             self.logger.warning("RSI calculation resulted in all NaNs.")


        # Ehlers-Fisher Transform (using pandas_ta's fisher transform)
        ef_period = self.config.get('efPeriod', 10)
        fisher_data = ta.fisher(high_prices, low_prices, length=ef_period, append=False)
        if fisher_data is not None and not fisher_data.empty:
            df['FISHER'] = fisher_data[f'FISHERT_{ef_period}']
            df['FISHER_Signal'] = fisher_data[f'FISHERTs_{ef_period}']
        else:
            self.logger.warning("Ehlers-Fisher calculation failed or returned empty data.")

        # --- Volatility Indicators ---
        # Bollinger Bands
        bb_period = self.config.get('bbPeriod', 20)
        bb_std = self.config.get('bbStdDev', 2.0)
        bb_data = ta.bbands(close_prices, length=bb_period, std=bb_std, append=False)
        if bb_data is not None and not bb_data.empty:
            df['BBL'] = bb_data[f'BBL_{bb_period}_{bb_std}']
            df['BBM'] = bb_data[f'BBM_{bb_period}_{bb_std}']
            df['BBU'] = bb_data[f'BBU_{bb_period}_{bb_std}']
        else:
            self.logger.warning("Bollinger Bands calculation failed or returned empty data.")

        # --- Fill NaN values ---
        # Forward fill then fill remaining NaNs with 0 (for indicators that need more data than available)
        # Using 0 can be misleading, safer to use a sentinel or omit if not enough data.
        # For simplicity in demo, we'll fill, but for robustness, handle `NaN` explicitly in `generate_trading_signal`.
        df = df.fillna(method='ffill').fillna(0)
        
        self.logger.debug(f"Technical indicators calculated. DataFrame last row: \n{df.iloc[-1]}")
        return df

    def generate_trading_signal(self, df: pd.DataFrame, current_position_side: Optional[str]) -> Tuple[Signal, str]:
        """
        Generates a trading signal based on a combination of indicators.
        This is a multi-indicator confirmation strategy.
        """
        # Ensure enough data for all indicators plus prev candle
        # Minimum data required for indicators
        required_history = max(
            self.config.get('macdSlowPeriod', 26), 
            self.config.get('rsi_length', 14), 
            self.config.get('bbPeriod', 20),
            self.config.get('supertrend_length', 10),
            self.config.get('efPeriod', 10)
        ) + 1 # +1 for the last complete candle after indicator calculation
        
        if df.empty or len(df) <= required_history: 
            self.logger.warning(f"Insufficient data ({len(df)} klines) for signal generation. Need at least {required_history}.")
            return Signal.NEUTRAL, "Insufficient data for signal generation."

        # Ensure latest and previous candles exist after NaNs are handled (or omitted)
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
        # Check for NaN before comparison
        if not np.isnan(latest['RSI']):
            if latest['RSI'] < rsi_oversold and prev['RSI'] >= rsi_oversold: # Crossing into oversold
                buy_signals += 1
                reasons.append(f"RSI ({latest['RSI']:.2f}) entering Oversold")
            elif latest['RSI'] > rsi_overbought and prev['RSI'] <= rsi_overbought: # Crossing into overbought
                sell_signals += 1
                reasons.append(f"RSI ({latest['RSI']:.2f}) entering Overbought")

        # --- 3. MACD Crossover ---
        # Check for NaN before comparison
        if not (np.isnan(latest['MACD']) or np.isnan(latest['MACD_Signal']) or np.isnan(prev['MACD']) or np.isnan(prev['MACD_Signal'])):
            if latest['MACD'] > latest['MACD_Signal'] and prev['MACD'] <= prev['MACD_Signal']:
                buy_signals += 1
                reasons.append("MACD Bullish Crossover")
            elif latest['MACD'] < latest['MACD_Signal'] and prev['MACD'] >= prev['MACD_Signal']:
                sell_signals += 1
                reasons.append("MACD Bearish Crossover")

        # --- 4. Supertrend ---
        if not np.isnan(latest['SUPERT_D']):
            if latest['SUPERT_D'] == 1: # Up trend
                buy_signals += 1
                reasons.append("Supertrend Up")
            elif latest['SUPERT_D'] == -1: # Down trend
                sell_signals += 1
                reasons.append("Supertrend Down")

        # --- 5. Bollinger Bands ---
        # Check for NaN before comparison
        if not (np.isnan(latest['close']) or np.isnan(latest['BBL']) or np.isnan(latest['BBU'])):
            if latest['close'] < latest['BBL']:
                buy_signals += 1
                reasons.append("Price below BB Lower")
            elif latest['close'] > latest['BBU']:
                sell_signals += 1
                reasons.append("Price above BB Upper")

        # --- 6. Ehlers-Fisher ---
        # Fisher values typically range from -1 to 1. Crossover near extremes is stronger.
        # Check for NaN before comparison
        if not (np.isnan(latest['FISHER']) or np.isnan(latest['FISHER_Signal']) or np.isnan(prev['FISHER']) or np.isnan(prev['FISHER_Signal'])):
            if latest['FISHER'] > latest['FISHER_Signal'] and prev['FISHER'] <= prev['FISHER_Signal'] and latest['FISHER'] < 0.5: # Crossover up from oversold region
                buy_signals += 1
                reasons.append("Fisher Bullish Crossover from below 0.5")
            elif latest['FISHER'] < latest['FISHER_Signal'] and prev['FISHER'] >= prev['FISHER_Signal'] and latest['FISHER'] > -0.5: # Crossover down from overbought region
                sell_signals += 1
                reasons.append("Fisher Bearish Crossover from above -0.5")
        
        # --- Aggregation and Final Signal ---
        min_strength = self.config.get('MIN_SIGNAL_STRENGTH', 2)

        if buy_signals >= min_strength and current_position_side != "Buy":
            return Signal.BUY, f"Strong BUY ({buy_signals} confirmations): {', '.join(reasons)}"
        elif sell_signals >= min_strength and current_position_side != "Sell":
            return Signal.SELL, f"Strong SELL ({sell_signals} confirmations): {', '.join(reasons)}"
        
        # If already in position, check for reversal or take profit/stop loss signals
        if current_position_side == "Buy" and sell_signals > (buy_signals + 1): # Require stronger sell signals to reverse
             return Signal.SELL, f"Potential BUY position reversal ({sell_signals} vs {buy_signals} opposing signals): {', '.join(reasons)}"
        elif current_position_side == "Sell" and buy_signals > (sell_signals + 1): # Require stronger buy signals to reverse
             return Signal.BUY, f"Potential SELL position reversal ({buy_signals} vs {sell_signals} opposing signals): {', '.join(reasons)}"

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
        # Remove any default handlers added by Flask/root logger to avoid duplicate logs
        if self.logger.handlers:
            self.logger.handlers = [] 
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
        self.gemini_client = GeminiAIClient(config.GEMINI_API_KEY, config.GEMINI_MODEL, self.logger, config.GEMINI_MAX_TOKENS)
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

        # Check API key configuration first
        if not self.config.BYBIT_API_KEY or not self.config.BYBIT_API_SECRET:
            self.logger.critical("Bybit API keys are not set in .env. Bot cannot start.")
            return {"status": "error", "message": "Bybit API keys are not configured."}
        if not self.bybit_client.is_initialized:
            self.logger.error("Bybit client not initialized properly. Cannot start bot.")
            return {"status": "error", "message": "Bybit client not initialized. Check API keys and connectivity."}

        # Update internal config with frontend values
        self.current_frontend_config = {
            'symbol': frontend_config.get('symbol', self.config.DEFAULT_SYMBOL).upper(),
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
            self.logger.error(f"Failed to set leverage to {self.current_frontend_config['leverage']}x for {self.current_frontend_config['symbol']}. Bot cannot start.")
            return {"status": "error", "message": "Failed to set leverage on exchange. Check symbol or API permissions."}

        self.is_running = True
        self.session_start_time = datetime.now()
        self.dashboard_metrics['botStatus'] = 'Running'
        self.bot_thread = threading.Thread(target=self._run_bot_loop, name="TradingBotLoop")
        self.bot_thread.daemon = True # Allow main program to exit even if thread is running
        self.bot_thread.start()
        self.logger.info(f"Bot started with config: {self.current_frontend_config['symbol']}/{self.current_frontend_config['interval']}")
        return {"status": "success", "message": "Bot ritual initiated ✔️"}

    def stop(self) -> Dict[str, str]:
        if not self.is_running:
            return {"status": "error", "message": "Bot is not running."}
        self.is_running = False
        # The thread will naturally terminate after its current loop iteration
        # Optionally, one could use a join with a timeout if needed to wait for thread completion.
        self.dashboard_metrics['botStatus'] = 'Stopping...' # Indicate transitional state
        self.logger.warning("Bot ritual pausing ⏸️")
        return {"status": "success", "message": "Bot ritual pausing ⏸️"}

    def _run_bot_loop(self):
        self.logger.info(f"Bot loop started for {self.current_frontend_config['symbol']} at interval {self.current_frontend_config['interval']}.")
        while self.is_running:
            try:
                # 1. Fetch & Process Market Data
                self._fetch_and_process_market_data()
                
                # Only proceed if we have valid market data
                if not self.market_data.empty and len(self.market_data) > 2: # Ensure enough data for indicators
                    self.market_data = self.trading_strategy.calculate_all_indicators(self.market_data)

                    # 2. Update Account Info
                    self._update_account_info()

                    # 3. Calculate Dashboard Metrics
                    self._calculate_dashboard_metrics()

                    # 4. Execute Strategy
                    self._execute_trading_strategy()
                else:
                    self.logger.warning("Not enough market data to perform full bot cycle. Skipping strategy execution.")
                    self._update_account_info() # Still try to get account balance
                    self._calculate_dashboard_metrics() # Still update price/balance

                # 5. Emit Full Dashboard Update via WebSocket
                self.socketio.emit('dashboard_update', self.get_full_status(), namespace='/ws/status')
                self.last_update_time = datetime.now()

            except Exception as e:
                self.logger.exception("Critical error in bot loop, stopping bot:") # Logs traceback
                self.dashboard_metrics['botStatus'] = 'Error'
                self.is_running = False # Stop bot on critical error
            finally:
                time.sleep(self.config.POLLING_INTERVAL_SECONDS)
        
        # Once loop exits, ensure status is reflected
        self.dashboard_metrics['botStatus'] = 'Idle'
        self.socketio.emit('dashboard_update', self.get_full_status(), namespace='/ws/status')
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
                df[col] = pd.to_numeric(df[col], errors='coerce') # Coerce errors to NaN
            df = df.dropna(subset=['close']).sort_values('start').set_index('start') # Drop rows with invalid close prices
            self.market_data = df
            self.logger.debug(f"Fetched {len(df)} klines for {symbol}")
        else:
            self.logger.warning(f"No kline data received for {symbol}.")
            self.market_data = pd.DataFrame() # Ensure empty dataframe on failure

    def _update_account_info(self):
        symbol = self.current_frontend_config['symbol']
        # Fetch current position
        positions_data = self.bybit_client.get_positions(symbol)
        if positions_data and positions_data['list']:
            # Find the active position for the current symbol (size > 0 for open positions)
            active_pos = next((p for p in positions_data['list'] if float(p['size']) > 0 and p['symbol'] == symbol), None)
            self.current_position = active_pos
        else:
            self.current_position = None # No open position
        
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
            self.logger.debug("Market data empty, dashboard metrics reset.")
            return

        latest = self.market_data.iloc[-1]
        prev = self.market_data.iloc[-2] if len(self.market_data) > 1 else None

        # Current Price & Change
        current_price = latest['close']
        price_change_value = 0
        if prev is not None and not np.isnan(prev['close']) and prev['close'] != 0:
             price_change_value = ((current_price - prev['close']) / prev['close'] * 100)
        
        self.dashboard_metrics['currentPrice'] = format_price(current_price)
        self.dashboard_metrics['priceChange'] = format_percent(price_change_value)

        # Supertrend
        st_direction = latest.get('SUPERT_D')
        st_value = latest.get('SUPERT')
        self.dashboard_metrics['stDirection'] = 'Up' if st_direction == 1 else ('Down' if st_direction == -1 else '---')
        self.dashboard_metrics['stValue'] = format_price(st_value)

        # RSI
        rsi_value = latest.get('RSI')
        rsi_status = '---'
        if not np.isnan(rsi_value):
            if rsi_value > self.current_frontend_config.get('rsi_overbought', self.config.DEFAULT_RSI_OVERBOUGHT): rsi_status = 'Overbought'
            elif rsi_value < self.current_frontend_config.get('rsi_oversold', self.config.DEFAULT_RSI_OVERSOLD): rsi_status = 'Oversold'
            else: rsi_status = 'Neutral'
        self.dashboard_metrics['rsiValue'] = format_decimal(rsi_value, 2)
        self.dashboard_metrics['rsiStatus'] = rsi_status

        # Current Position & PnL
        if self.current_position:
            self.dashboard_metrics['currentPosition'] = self.current_position['side']
            unrealized_pnl = float(self.current_position.get('unrealisedPnl', 0))
            entry_price = float(self.current_position.get('avgPrice', current_price))
            position_size = float(self.current_position.get('size', 0))
            
            pnl_percent_value = 0
            if entry_price > 0 and position_size > 0:
                pnl_percent_value = (unrealized_pnl / (entry_price * position_size) * 100)
            
            self.dashboard_metrics['positionPnL'] = format_percent(pnl_percent_value)
        else:
            self.dashboard_metrics['currentPosition'] = 'None'
            self.dashboard_metrics['positionPnL'] = '---'

        # Account Balance
        if self.account_balance:
            self.dashboard_metrics['accountBalance'] = format_price(self.account_balance.get('walletBalance'))
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

        self.dashboard_metrics['botStatus'] = 'Running' if self.is_running else 'Idle' # Re-confirm status
        self.logger.debug("Dashboard metrics updated.")

    def _execute_trading_strategy(self):
        if self.market_data.empty or not self.is_running or len(self.market_data) < 2:
            self.logger.debug("Skipping strategy execution due to missing data or bot not running.")
            return

        current_position_side = self.current_position['side'] if self.current_position else None
        signal, reason = self.trading_strategy.generate_trading_signal(self.market_data, current_position_side)
        self.logger.info(f"Signal: {signal.name}. Reason: {reason}", extra={'level': 'signal'})

        latest_price = self.market_data.iloc[-1]['close']
        symbol = self.current_frontend_config['symbol']
        leverage = self.current_frontend_config['leverage']
        risk_pct = self.current_frontend_config['riskPct']
        sl_pct = self.current_frontend_config['stopLossPct']
        tp_pct = self.current_frontend_config['takeProfitPct']

        account_equity = float(self.account_balance.get('equity', 0)) if self.account_balance else 0

        if account_equity <= 0:
            self.logger.warning("Account equity is zero or negative. Cannot place trades.")
            return

        # --- Handle BUY Signal ---
        if signal == Signal.BUY and current_position_side != "Buy":
            # If currently short, first close short position
            if current_position_side == "Sell":
                self.logger.info(f"Reversal detected: Closing existing SELL position before opening BUY for {symbol}.")
                qty_to_close = float(self.current_position.get('size', 0))
                if qty_to_close > 0 and self.bybit_client.close_position(symbol, "Sell", qty_to_close):
                    self.logger.info(f"SELL position closed. PnL: {float(self.current_position.get('unrealisedPnl', 0)):.2f}")
                    if float(self.current_position.get('unrealisedPnl', 0)) > 0: self.winning_trades += 1
                    self.current_position = None # Clear position after closing
                    time.sleep(1) # Give exchange some time to process
                else:
                    self.logger.error("Failed to close existing SELL position. Aborting BUY order.")
                    return

            self.logger.info(f"Executing BUY signal for {symbol} at {latest_price}.")
            
            # Calculate SL/TP prices
            # Stop loss always below entry for Buy, Take profit above
            stop_loss_price_raw = latest_price * (1 - sl_pct / 100)
            take_profit_price_raw = latest_price * (1 + tp_pct / 100)
            
            stop_loss_price = self.bybit_client.round_price(symbol, stop_loss_price_raw)
            take_profit_price = self.bybit_client.round_price(symbol, take_profit_price_raw)
            
            # Calculate position size
            # Simplified risk-based sizing: (Equity * Risk%) / (Price * SL% / Leverage)
            # This is a rough estimation. Real sizing needs to consider contract value, inverse, etc.
            # Using current price for initial quantity calculation
            risk_amount = account_equity * (risk_pct / 100)
            # Value of 1 contract in USD for a given SL percentage
            if sl_pct > 0:
                position_size_usdt_value = risk_amount / (sl_pct / 100)
            else:
                # If SL is 0, define a max position size or use a default risk amount
                self.logger.warning("Stop Loss % is 0, using fixed risk amount for position sizing.")
                position_size_usdt_value = account_equity * 0.01 # Example: 1% of equity if no SL
            
            qty = self.bybit_client.round_qty(symbol, position_size_usdt_value / latest_price)
            qty = max(qty, self.bybit_client.get_min_order_qty(symbol)) # Ensure min qty
            
            if qty > 0:
                order_result = self.bybit_client.place_order(
                    symbol=symbol,
                    side="Buy",
                    orderType=self.config.ORDER_TYPE,
                    qty=str(qty),
                    # price=str(self.bybit_client.round_price(symbol, latest_price)) if self.config.ORDER_TYPE == "Limit" else None,
                    stopLoss=str(stop_loss_price) if sl_pct > 0 else None,
                    takeProfit=str(take_profit_price) if tp_pct > 0 else None,
                    timeInForce=self.config.TIME_IN_FORCE,
                    leverage=str(leverage)
                )
                if order_result:
                    self.logger.info(f"BUY order placed: {qty} {symbol} @ {latest_price}. SL:{stop_loss_price}, TP:{take_profit_price}")
                    self.total_trades += 1
                else:
                    self.logger.error(f"Failed to place BUY order for {qty} {symbol}.")
            else:
                self.logger.warning(f"Calculated BUY quantity ({qty}) is too small or zero for {symbol}.")

        # --- Handle SELL Signal (Open short position) ---
        elif signal == Signal.SELL and current_position_side != "Sell":
            # If currently long, first close long position
            if current_position_side == "Buy":
                self.logger.info(f"Reversal detected: Closing existing BUY position before opening SELL for {symbol}.")
                qty_to_close = float(self.current_position.get('size', 0))
                if qty_to_close > 0 and self.bybit_client.close_position(symbol, "Buy", qty_to_close):
                    self.logger.info(f"BUY position closed. PnL: {float(self.current_position.get('unrealisedPnl', 0)):.2f}")
                    if float(self.current_position.get('unrealisedPnl', 0)) > 0: self.winning_trades += 1
                    self.current_position = None # Clear position after closing
                    time.sleep(1) # Give exchange some time to process
                else:
                    self.logger.error("Failed to close existing BUY position. Aborting SELL order.")
                    return

            self.logger.info(f"Executing SELL signal to open SHORT position for {symbol} at {latest_price}.")
            
            # Calculate SL/TP prices
            # Stop loss always above entry for Sell, Take profit below
            stop_loss_price_raw = latest_price * (1 + sl_pct / 100)
            take_profit_price_raw = latest_price * (1 - tp_pct / 100)

            stop_loss_price = self.bybit_client.round_price(symbol, stop_loss_price_raw)
            take_profit_price = self.bybit_client.round_price(symbol, take_profit_price_raw)
            
            # Calculate position size (same logic as BUY but for short)
            risk_amount = account_equity * (risk_pct / 100)
            if sl_pct > 0:
                position_size_usdt_value = risk_amount / (sl_pct / 100)
            else:
                self.logger.warning("Stop Loss % is 0, using fixed risk amount for position sizing.")
                position_size_usdt_value = account_equity * 0.01 # Example: 1% of equity if no SL
            
            qty = self.bybit_client.round_qty(symbol, position_size_usdt_value / latest_price)
            qty = max(qty, self.bybit_client.get_min_order_qty(symbol)) # Ensure min qty

            if qty > 0:
                order_result = self.bybit_client.place_order(
                    symbol=symbol,
                    side="Sell",
                    orderType=self.config.ORDER_TYPE,
                    qty=str(qty),
                    # price=str(self.bybit_client.round_price(symbol, latest_price)) if self.config.ORDER_TYPE == "Limit" else None,
                    stopLoss=str(stop_loss_price) if sl_pct > 0 else None,
                    takeProfit=str(take_profit_price) if tp_pct > 0 else None,
                    timeInForce=self.config.TIME_IN_FORCE,
                    leverage=str(leverage)
                )
                if order_result:
                    self.logger.info(f"SELL order placed: {qty} {symbol} @ {latest_price}. SL:{stop_loss_price}, TP:{take_profit_price}")
                    self.total_trades += 1
                else:
                    self.logger.error(f"Failed to place SELL order for {qty} {symbol}.")
            else:
                self.logger.warning(f"Calculated SELL quantity ({qty}) is too small or zero for {symbol}.")

        # --- Handle HOLD Signal ---
        elif signal == Signal.NEUTRAL:
            self.logger.info("Strategy: HOLD. No action taken.")
        
        # Update trading stops if position exists and SL/TP are defined (dynamic trailing stop can be added here)
        if self.current_position and (sl_pct > 0 or tp_pct > 0):
            current_position_side = self.current_position['side']
            entry_price = float(self.current_position.get('avgPrice', latest_price))
            
            new_sl = None
            new_tp = None

            if current_position_side == "Buy":
                new_sl = self.bybit_client.round_price(symbol, entry_price * (1 - sl_pct / 100))
                new_tp = self.bybit_client.round_price(symbol, entry_price * (1 + tp_pct / 100))
            elif current_position_side == "Sell": # Short
                new_sl = self.bybit_client.round_price(symbol, entry_price * (1 + sl_pct / 100))
                new_tp = self.bybit_client.round_price(symbol, entry_price * (1 - tp_pct / 100))
            
            if new_sl is not None or new_tp is not None:
                if self.bybit_client.set_trading_stop(symbol, new_sl, new_tp):
                    self.logger.debug(f"Updated SL/TP for {symbol} position: SL={new_sl}, TP={new_tp}")
                else:
                    self.logger.error(f"Failed to update SL/TP for {symbol} position.")

EOF

echo "Creating backend/app.py"
cat << 'EOF' > backend/app.py
import eventlet
eventlet.monkey_patch() # Must be called before other imports that use standard library sockets

from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging
import asyncio # For async Gemini calls

from config import Config
from bot_core import TradingBotCore
from utils import CustomLogger

# --- Flask App Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_and_random_key_for_flask_session_security_CHANGE_THIS_IN_PRODUCTION' # CHANGE THIS IN PRODUCTION
CORS(app) # Enable CORS for all routes
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet') # Allow all origins for demo, use specific in production

# --- Bot Initialization ---
config = Config()
# Set up a dedicated logger for the bot that uses CustomLogger
bot_logger = logging.getLogger('TradingBot')
bot_logger.setLevel(logging.INFO) # Set default level for bot-specific logs
custom_logger_instance = CustomLogger(socketio, max_logs=config.MAX_LOG_ENTRIES)
bot_logger.addHandler(custom_logger_instance)
bot_logger.propagate = False # Prevent logs from going to root logger which might re-print to console

# Configure Flask's default logger to also use CustomLogger
app.logger.removeHandler(app.logger.handlers[0]) # Remove default console handler
app.logger.addHandler(custom_logger_instance)
app.logger.setLevel(logging.INFO) # Set default level for Flask app logs

bot = TradingBotCore(config, socketio, custom_logger_instance) # Pass the custom_logger instance to bot

# --- API Endpoints ---

@app.route('/')
def index():
    return "Pyrmethus's Neon Grimoire Backend is running!"

@app.route('/api/start', methods=['POST'])
def start_bot_endpoint():
    try:
        frontend_config = request.get_json()
        if not frontend_config:
            return jsonify({"status": "error", "message": "No configuration provided."}), 400
        
        response = bot.start(frontend_config)
        return jsonify(response)
    except Exception as e:
        app.logger.error(f"Error starting bot: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/stop', methods=['POST'])
def stop_bot_endpoint():
    try:
        response = bot.stop()
        return jsonify(response)
    except Exception as e:
        app.logger.error(f"Error stopping bot: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_bot_status_endpoint():
    try:
        status_data = bot.get_full_status()
        return jsonify(status_data)
    except Exception as e:
        app.logger.error(f"Error getting bot status: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/gemini-insight', methods=['POST'])
async def get_gemini_insight_endpoint():
    try:
        data = request.get_json()
        prompt_text = data.get('prompt')
        if not prompt_text:
            return jsonify({"status": "error", "message": "No prompt provided."}), 400
        
        # Use the bot's Gemini client to generate insight
        insight_response = await bot.gemini_client.generate_insight(prompt_text)
        
        if insight_response['status'] == 'error':
            app.logger.error(f"Gemini insight error: {insight_response['message']}")
            return jsonify(insight_response), 500
        
        app.logger.info("Gemini insight successfully generated.", extra={'level': 'llm'})
        return jsonify(insight_response)
    except Exception as e:
        app.logger.error(f"Error getting Gemini insight: {e}", exc_info=True)
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
    app.logger.info(f"Flask backend starting. Testnet: {config.BYBIT_TESTNET}")
    
    # Check API keys before running
    if not config.BYBIT_API_KEY or not config.BYBIT_API_SECRET:
        app.logger.critical("Bybit API keys are not set in .env. Please configure them.")
        # Do not exit immediately, allow app to run so user can see logs
    if not config.GEMINI_API_KEY:
        app.logger.warning("Gemini API key is not set in .env. AI features will be disabled.")
    
    # Use eventlet for SocketIO server. Host 0.0.0.0 makes it accessible externally.
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

EOF

echo "Creating backend/start_backend.sh"
cat << EOF > backend/start_backend.sh
#!/bin/bash

# Navigate to the backend directory
SCRIPT_DIR="\$( cd "\$( dirname "\${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cd "\$SCRIPT_DIR" || { echo "Failed to navigate to backend directory."; exit 1; }

echo "Starting Pyrmethus's Neon Grimoire Backend..."

# Check for virtual environment and activate it
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
elif [ -d ".venv" ]; then
    echo "Activating virtual environment..."
    source .venv/bin/activate
else
    echo "Warning: Virtual environment not found. Running with global Python installation."
    echo "It's recommended to create and activate a virtual environment first:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r requirements.txt"
fi

# Run the Flask app with gunicorn for robustness, or directly with Python for debugging
# Using gunicorn as it's in requirements.txt and is better for production/robustness
# For simple development, you could use 'python app.py'
if command -v gunicorn &> /dev/null; then
    echo "Starting with Gunicorn..."
    gunicorn -w 1 -b 0.0.0.0:5000 'app:app' --log-level info
else
    echo "Gunicorn not found or activated. Falling back to 'python app.py' for development."
    echo "Consider installing gunicorn: pip install gunicorn"
    python app.py
fi

# Deactivate virtual environment (if it was activated by this script)
if [[ "\$VIRTUAL_ENV" != "" ]]; then
    echo "Deactivating virtual environment."
    deactivate
fi
EOF
chmod +x backend/start_backend.sh

# --- Automatic Virtual Environment Setup and Installation ---
if [ "$INSTALL_VENV_AUTO" = true ]; then
  echo ""
  echo "--- Setting up Backend Virtual Environment ---"
  
  # Check if venv already exists
  if [ -d "backend/venv" ] || [ -d "backend/.venv" ]; then
    echo "Virtual environment already exists in backend/. Skipping creation."
  else
    echo "Creating virtual environment in backend/venv..."
    python3 -m venv backend/venv || { echo "Failed to create virtual environment. Please check your Python installation."; exit 1; }
  fi

  # Activate and install requirements
  # Use different activation script based on OS (bash/zsh vs fish vs csh)
  if [ -f "backend/venv/bin/activate" ]; then
    source backend/venv/bin/activate || { echo "Failed to activate virtual environment."; exit 1; }
  elif [ -f "backend/.venv/bin/activate" ]; then
    source backend/.venv/bin/activate || { echo "Failed to activate virtual environment."; exit 1; }
  else
    echo "Could not find virtual environment activation script. Skipping automatic package installation."
    echo "Please activate manually and run 'pip install -r requirements.txt'."
    MANUAL_INSTALL_NEEDED=true
  fi

  if [ "$MANUAL_INSTALL_NEEDED" != true ]; then
    echo "Installing backend dependencies from requirements.txt..."
    pip install -r backend/requirements.txt || { echo "Failed to install backend dependencies. Please check requirements.txt and your internet connection."; exit 1; }
    echo "Backend dependencies installed successfully."
    deactivate # Deactivate after installation
  fi
else
  echo "Skipping automatic virtual environment setup and installation."
fi

echo ""
echo "Project '$PROJECT_NAME' conjured successfully, Master Pyrmethus!"
echo ""
echo "--- Next Steps ---"
echo "1. Navigate into the project directory: cd $PROJECT_NAME"
echo "2. Backend Configuration: Edit 'backend/.env' with your actual BYBIT_API_KEY, BYBIT_API_SECRET, and GEMINI_API_KEY."
echo "   (Set BYBIT_TESTNET to 'false' if you want to trade with real funds.)"
echo "3. Run the Backend:"
echo "   cd backend"
echo "   ./start_backend.sh"
echo "   (This script will activate the virtual environment and start the Flask server.)"
echo "4. Open the Frontend: Double-click 'frontend/index.html' in your web browser."
echo "   Alternatively, for robust local serving (especially if you encounter CORS issues or want HTTPS):"
echo "   a. Install a simple Python HTTP server: pip install --user http.server (Python 3.7+)"
echo "   b. Navigate to the frontend directory: cd frontend"
echo "   c. Run the server: python3 -m http.server 8000"
echo "   d. Open your browser to: http://localhost:8000"
echo ""
echo "May your trades be ever in your favor!"
