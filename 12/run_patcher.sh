#!/bin/bash
# Gemini File Patcher - Interactive Script with Auto-Apply
#
# Enhanced version with improved error handling, backup functionality, and logging
#
# This script uses aichat to perform file patching operations.
# It will prompt for the file and instructions, then ask for confirmation to apply the patch.

# --- Configuration ---
# Default model (can be overridden with environment variable)
MODEL="${GEMINI_PATCHER_MODEL:-gemini:gemini-2.5-flash}"

# Default backup directory (can be overridden with environment variable)
BACKUP_DIR="${GEMINI_PATCHER_BACKUP_DIR:-./backups}"

# Default log file (can be overridden with environment variable)
LOG_FILE="${GEMINI_PATCHER_LOG_FILE:-./patcher.log}"

# Agent instructions
AGENT_INSTRUCTIONS="
You are an expert AI assistant specializing in file patching and code maintenance.
Your primary directives are:
1.  **Analyze Code:** Carefully read and understand the provided file(s) to identify the target for patching.
2.  **Generate Patches:** Create precise, efficient, and correct code patches in the standard 'diff' format. Output ONLY the diff content inside a markdown code block like this:
    \`\`\`diff
    ... your diff content here ...
    \`\`\`
3.  **Clarity:** Do not include any text outside of the markdown code block.
"

# --- Color Definitions ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# --- Helper Functions ---
# Function to print colored output
print_color() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to log messages
log_message() {
    local message=$1
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $message" >> "$LOG_FILE"
}

# Function to create backup
create_backup() {
    local file=$1
    local timestamp=$(date '+%Y%m%d%H%M%S')
    local backup_file="${BACKUP_DIR}/$(basename "$file").${timestamp}.bak"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        mkdir -p "$BACKUP_DIR" || {
            print_color $RED "Error: Could not create backup directory '$BACKUP_DIR'."
            return 1
        }
    fi
    
    cp "$file" "$backup_file" || {
        print_color $RED "Error: Could not create backup of '$file'."
        return 1
    }
    
    print_color $GREEN "Backup created: $backup_file"
    log_message "Backup created: $backup_file"
    return 0
}

# --- Main Execution ---
# Initialize log file
touch "$LOG_FILE" 2>/dev/null || {
    print_color $RED "Warning: Could not create log file '$LOG_FILE'. Logging disabled."
    LOG_FILE="/dev/null"
}

# Prompt for the file to patch
echo "Which file would you like to patch?"
read -r FILE_TO_PATCH

# Check if the file exists
if [ ! -f "$FILE_TO_PATCH" ]; then
    print_color $RED "Error: File '$FILE_TO_PATCH' not found."
    log_message "Error: File '$FILE_TO_PATCH' not found."
    exit 1
fi

# Prompt for the patching instructions
echo "What changes would you like to make?"
read -r PATCH_INSTRUCTIONS

# Check if instructions were provided
if [ -z "$PATCH_INSTRUCTIONS" ]; then
    print_color $RED "Error: No patch instructions provided."
    log_message "Error: No patch instructions provided."
    exit 1
fi

echo
print_color $BLUE "--- Gemini File Patcher ---"
echo "Target File: $FILE_TO_PATCH"
echo "Instructions: $PATCH_INSTRUCTIONS"
echo "Model: $MODEL"
print_color $BLUE "---------------------------"
echo

# Log the operation
log_message "Starting patch operation on file: $FILE_TO_PATCH"
log_message "Instructions: $PATCH_INSTRUCTIONS"

# Create backup before proceeding
if ! create_backup "$FILE_TO_PATCH"; then
    print_color $RED "Backup creation failed. Aborting patch operation."
    log_message "Backup creation failed. Aborting patch operation."
    exit 1
fi

echo "Generating patch..."
# Generate the patch and store it in a variable
AI_RESPONSE=$(aichat -m "$MODEL" \
    --prompt "$AGENT_INSTRUCTIONS" \
    -f "$FILE_TO_PATCH" \
    "Apply the following change: $PATCH_INSTRUCTIONS" 2>&1)

# Check if aichat command succeeded
if [ $? -ne 0 ]; then
    print_color $RED "Error: Failed to generate patch using aichat."
    print_color $RED "Response: $AI_RESPONSE"
    log_message "Error: Failed to generate patch using aichat. Response: $AI_RESPONSE"
    exit 1
fi

# Extract the diff content from the markdown block
PATCH_CONTENT=$(echo "$AI_RESPONSE" | sed -n '/```diff/,/```/p' | sed '1d;$d')

if [ -z "$PATCH_CONTENT" ]; then
    print_color $RED "Error: Could not find a valid patch in the AI's response."
    print_color $RED "Full response:"
    echo "$AI_RESPONSE"
    log_message "Error: Could not find a valid patch in the AI's response. Full response: $AI_RESPONSE"
    exit 1
fi

# Display the proposed patch
print_color $BLUE "The following patch has been generated:"
print_color $BLUE "---------------------------------------"
echo "$PATCH_CONTENT"
print_color $BLUE "---------------------------------------"
echo

# Ask for confirmation to apply the patch
read -p "Apply this patch? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Apply the patch
    echo "$PATCH_CONTENT" | patch "$FILE_TO_PATCH"
    if [ $? -eq 0 ]; then
        print_color $GREEN "Patch applied successfully."
        log_message "Patch applied successfully to $FILE_TO_PATCH"
    else
        print_color $RED "Error applying patch."
        log_message "Error applying patch to $FILE_TO_PATCH"
        exit 1
    fi
else
    print_color $YELLOW "Patch aborted."
    log_message "Patch aborted by user"
fi

print_color $GREEN "Operation completed."
exit 0