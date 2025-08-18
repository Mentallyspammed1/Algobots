#!/usr/bin/env bash

# Worldguidex Jules VM Setup Script
# Purpose: Configure Jules VM, generate project files, install system/Python dependencies.
# The repository cloning functionality has been removed as per user request.
# Date: 2025-06-20 (Updated to remove repo cloning)
# Author: Gemini (based on user's requirements and script)

# --- Strict Mode & Error Handling ---
# Exit immediately if a command exits with a non-zero status.
# Relaxed from 'euo pipefail' to 'e' only, as 'u' (nounset) and 'o pipefail' might conflict with VM environment internals.
set -e

# Removed IFS=$'\n\t' as it might conflict with VM environment internals.

# Trap for catching errors and displaying a simple, robust exit message.
# This is simplified to reduce potential conflicts with the VM's shell environment.
trap 'EXIT_CODE=$? ; if [[ $EXIT_CODE -ne 0 ]]; then echo -e "\033[1;31m✗ ERROR: Script terminated unexpectedly with exit code ${EXIT_CODE}.\033[0m For full details, check: \033[4m${LOG_FILE}\033[0m" >&2; fi' EXIT

# --- Configuration Constants ---
readonly PROJECT_DIR_NAME="jules_worldguidex_project"
readonly PROJECT_DIR="${HOME}/${PROJECT_DIR_NAME}"
readonly APP_DIR="${PROJECT_DIR}/app" # This directory will now be where your app files are expected to reside if not cloned.
readonly CONFIG_DIR="${PROJECT_DIR}/config" # Added for potential future configs
readonly LOGS_DIR="${PROJECT_DIR}/logs"
readonly VENV_DIR="${PROJECT_DIR}/venv"
# Removed REPO_URL as cloning is no longer part of this script.
readonly PYTHON_PACKAGES=(
    "pandas"
    "pandas-ta"
    "numpy"
    "requests"
    "ccxt"
    "python-dotenv"
    "pytest"
    "pytest-cov"
    "matplotlib" # Added for chart generation
    "websocket-client"
    "colorama"
    "pybit"
)
readonly MIN_PYTHON_MAJOR=3
readonly MIN_PYTHON_MINOR=8
readonly MIN_DISK_GB=2          # Minimum required disk space in GB
readonly DEBUG_MODE=${DEBUG_MODE:-false} # Set to true for verbose debugging

# --- ANSI Colors for Enhanced Output (Corrected Declaration and Usage) ---
# Declare associative array
declare -A COLORS
COLORS[NC]='\033[0m'       # No Color
COLORS[BOLD]='\033[1m'
COLORS[RED]='\033[1;31m'
COLORS[GREEN]='\033[1;32m'
COLORS[YELLOW]='\033[1;33m'
COLORS[BLUE]='\033[1;34m'
COLORS[MAGENTA]='\033[1;35m'
COLORS[CYAN]='\033[1;36m'
COLORS[WHITE]='\033[1;37m'
COLORS[UNDERLINE]='\033[4m'

# --- Logging Functions ---
# Create logs directory early. This *must* be writable by the user within HOME.
mkdir -p "${LOGS_DIR}" || { echo "ERROR: Could not create logs directory at ${LOGS_DIR}. Permissions issue or invalid path?"; exit 1; }
readonly LOG_FILE="${LOGS_DIR}/jules_setup_$(date +'%Y%m%d_%H%M%S').log"

_log() {
    local level="$1"
    shift
    local message="$@"
    local timestamp="$(date +'%Y-%m-%d %H:%M:%S')"
    printf "%s [%s] %b\n" "$timestamp" "$level" "$message" | tee -a "${LOG_FILE}" >&2
}

log_info() { _log "INFO" "${COLORS[CYAN]}$1${COLORS[NC]}"; }
log_success() { _log "SUCCESS" "${COLORS[GREEN]}${COLORS[BOLD]}✓${COLORS[NC]} ${COLORS[GREEN]}$1${COLORS[NC]}"; }
log_warn() { _log "WARNING" "${COLORS[YELLOW]}⚠️ $1${COLORS[NC]}"; }
log_error() { _log "ERROR" "${COLORS[RED]}${COLORS[BOLD]}✗ ERROR:${COLORS[NC]}${COLORS[RED]} $1${COLORS[NC]}"; exit 1; } # Exits script on error

# --- Helper Functions ---

# Function to check for required system commands
check_command() {
    local cmd="$1"
    log_info "Checking for command: ${cmd}..."
    if ! command -v "${cmd}" &> /dev/null; then
        log_error "${cmd} is not installed or not in PATH. This tool is required for setup."
    fi
    log_success "${cmd} found."
}

# Function to check current Python version
check_python_version() {
    log_info "Verifying Python version (required: >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR})..."
    local python_version
    # Ensure python3 command exists before trying to get version
    if ! command -v python3 &> /dev/null; then
        log_error "python3 command not found. Python 3 is essential for this setup."
    fi

    # Using a subshell to capture output without affecting set -e
    python_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    local python_major=$(echo "${python_version}" | cut -d'.' -f1)
    local python_minor=$(echo "${python_version}" | cut -d'.' -f2)

    if [[ "${python_major}" -lt "${MIN_PYTHON_MAJOR}" || ( "${python_major}" -eq "${MIN_PYTHON_MAJOR}" && "${python_minor}" -lt "${MIN_PYTHON_MINOR}" ) ]]; then
        log_error "Python ${python_version} found. Minimum Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} is required. Please ensure the VM environment has an adequate Python version."
    else
        log_success "Python ${python_version} (meets >= ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR} requirement) found."
    fi
}

# Function to check available disk space
check_disk_space() {
    log_info "Checking available disk space in ${HOME} (required: >= ${MIN_DISK_GB} GB)..."
    # df -k . gets space on current filesystem in KB
    local available_space_kb=$(df -k "${HOME}" | awk 'NR==2 {print $4}')
    local available_space_gb=$((available_space_kb / (1024 * 1024)))

    if [[ "${available_space_gb}" -lt "${MIN_DISK_GB}" ]]; then
        log_error "Only ${available_space_gb} GB of disk space available. Minimum ${MIN_DISK_GB} GB recommended. VM might run out of space during dependency installation or operations."
    else
        log_success "${available_space_gb} GB of disk space available (meets >= ${MIN_DISK_GB} GB requirement)."
    fi
}

# --- Setup Functions ---

setup_directories() {
    log_info "Creating project directories under ${PROJECT_DIR}..."
    local dirs=("${PROJECT_DIR}" "${APP_DIR}" "${CONFIG_DIR}" "${LOGS_DIR}" "${VENV_DIR}")
    for dir in "${dirs[@]}"; do
        if [ ! -d "${dir}" ]; then
            log_info "Creating directory: ${dir}..."
            mkdir -p "${dir}" || log_error "Failed to create directory: ${dir}. Check permissions and path."
        else
            log_warn "Directory already exists: ${dir}. Skipping creation to ensure idempotency."
        fi
    done
    log_success "All project directories are in place."
}

generate_requirements_file() {
    log_info "Generating/Updating requirements.txt at ${APP_DIR}/requirements.txt..."
    local req_file="${APP_DIR}/requirements.txt"
    # Overwrite if exists to ensure it's up-to-date with current PYTHON_PACKAGES
    printf "%s\n" "${PYTHON_PACKAGES[@]}" > "${req_file}" || log_error "Failed to generate requirements.txt."
    log_success "requirements.txt generated with ${#PYTHON_PACKAGES[@]} packages listed."
}

setup_python_environment() {
    log_info "Setting up Python virtual environment at ${VENV_DIR}..."

    # Check if venv directory exists AND if activate script exists.
    # If directory exists but activate script is missing (corrupted venv), recreate it.
    if [ ! -d "${VENV_DIR}" ] || [ ! -f "${VENV_DIR}/bin/activate" ]; then
        if [ -d "${VENV_DIR}" ]; then # Venv dir exists but activate script doesn't
            log_warn "Virtual environment directory exists at ${VENV_DIR} but '${VENV_DIR}/bin/activate' is missing. Removing corrupted venv and recreating..."
            rm -rf "${VENV_DIR}" || log_error "Failed to remove corrupted virtual environment at ${VENV_DIR}. Manual cleanup may be needed."
        fi
        log_info "Creating new virtual environment..."
        python3 -m venv "${VENV_DIR}" || log_error "Failed to create virtual environment. Ensure 'python3-venv' is installed."
        log_success "Virtual environment created."
    else
        log_warn "Virtual environment already exists and appears valid at ${VENV_DIR}. Skipping creation."
    fi

    log_info "Activating virtual environment and installing/upgrading Python dependencies..."
    # Execute within a subshell to ensure activation/deactivation doesn't affect the main script's environment
    (
        source "${VENV_DIR}/bin/activate" || log_error "Failed to activate virtual environment at ${VENV_DIR}. This is critical for dependency installation."

        log_info "Upgrading pip, setuptools, and wheel within venv..."
        # Using 2>/dev/null to suppress non-critical warnings from pip
        python -m pip install --upgrade pip setuptools wheel 2>/dev/null || log_warn "Failed to upgrade pip tools. This might not be critical, continuing anyway."

        log_info "Installing Python dependencies from requirements.txt..."
        python -m pip install --no-cache-dir -r "${APP_DIR}/requirements.txt" || log_error "Failed to install Python dependencies from ${APP_DIR}/requirements.txt. Check internet connection or package names."

        deactivate || log_warn "Failed to deactivate virtual environment. This should not impact script execution."
    )
    log_success "Python dependencies installed/updated in virtual environment."
}

# clone_repository function removed as per user request.

# --- Main Execution Flow ---
main() {
    log_info "${COLORS[BOLD]}${COLORS[MAGENTA]}Starting Jules VM setup for Worldguidex project...${COLORS[NC]}"
    log_info "Full setup log available at: ${LOG_FILE}"

    # Step 1: Perform initial system checks
    log_info "Performing pre-setup system checks..."
    check_command "git" # Keeping git check as it might be useful for other operations or user's manual cloning
    check_command "python3"
    check_python_version
    check_disk_space
    log_success "Pre-setup system checks complete."

    # Step 2: Set up project directories
    setup_directories

    # Step 3: Generate requirements file
    generate_requirements_file

    # Step 4: Set up Python virtual environment and install dependencies
    setup_python_environment

    # Removed: Step 5: Clone/Update the application repository

    log_success "${COLORS[BOLD]}${COLORS[GREEN]}Jules VM setup for Worldguidex completed successfully!${COLORS[NC]}"
    log_info "Project root: ${PROJECT_DIR}"
    log_info "Application code (expected here if cloned automatically or manually): ${APP_DIR}"
    log_info "Virtual environment: ${VENV_DIR}"
    log_info "You can now navigate to ${APP_DIR} and run your Python applications."
    log_info "To activate the virtual environment manually: source ${VENV_DIR}/bin/activate"
}

# Execute the main function
main "$@"
