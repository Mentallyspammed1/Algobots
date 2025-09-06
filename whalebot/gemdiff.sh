#!/usr/bin/env bash
# A powerful, enhanced script to merge code files using the Gemini API.
# Upgraded with advanced prompt engineering, robust error handling, and more.
# Version 3.0 ✨

# --- Configuration ---
CONFIG_FILE="$HOME/.gemini-merge.conf"
DEFAULT_MODEL="gemini-1.5-flash-latest" # Or "gemini-1.5-pro-latest"
# Default colors (can be overridden in config file)
C_ERROR='\e[1;31m'
C_SUCCESS='\e[1;32m'
C_WARN='\e[1;33m'
C_INFO='\e[1;35m'
C_INPUT='\e[1;36m'
C_NC='\e[0m'

# --- Variables ---
API_KEY=""
API_MODEL="$DEFAULT_MODEL"
OUTPUT_FILE=""
NON_INTERACTIVE=false
SPINNER_PID=""

# --- Functions ---
# Print usage information
print_usage() {
    echo -e "${C_INFO}Gemini Code Merger v3.0${C_NC}"
    echo "Usage: $0 [options] <file1> <file2>"
    echo "Merges two code files using the Gemini API, applying best practices from both."
    echo ""
    echo -e "${C_INFO}Options:${C_NC}"
    echo "  -o <file>   Specify the output file."
    echo "  -y          Non-interactive mode (assumes 'yes' to all prompts)."
    echo "  -h          Display this help message."
    echo ""
    echo -e "${C_INFO}Prerequisites:${C_NC}"
    echo "  - An API key must be set in your environment or in the config file: $CONFIG_FILE"
    echo "  - Required commands: curl, jq, diff"
}

# Log an informational message
log_info() {
    if [ -t 1 ]; then
        echo -e "${C_INFO}$1${C_NC}"
    else
        echo "$1"
    fi
}

# Log an error message
log_error() {
    if [ -t 1 ]; then
        echo -e "${C_ERROR}Error: $1${C_NC}" >&2
    else
        echo "Error: $1" >&2
    fi
}

# Show a spinner while a command is running
show_spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='_.-`'
    while ps -p $pid >/dev/null; do
        local temp=${spinstr#?}
        printf " [%c] " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "      \b\b\b\b\b\b"
}

# Call the Gemini API
call_gemini_api() {
    local prompt_text="$1"
    local json_payload
    json_payload=$(jq -n \
        --arg prompt "$prompt_text" \
        '{ "contents": [ { "parts": [ { "text": $prompt } ] } ], "generationConfig": { "temperature": 0.4 }, "safetySettings": [ {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}, {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}, {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}, {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"} ] }')

    # API call with robust error handling for common issues
    local api_url="https://generativelanguage.googleapis.com/v1beta/models/${API_MODEL}:generateContent?key=${API_KEY}"
    local response
    response=$(curl -sS -H "Content-Type: application/json" -d "$json_payload" "$api_url")

    # Check for specific API errors
    if echo "$response" | grep -q "404 Not Found"; then
        log_error "API returned 404. Model '${API_MODEL}' might be invalid. Please check your model name in the config file."
        exit 1
    fi
    if echo "$response" | jq -e '.error' >/dev/null; then
        log_error "API call failed. Reason: $(echo "$response" | jq -r '.error.message')"
        exit 1
    fi

    echo "$response"
}

# Cleanup function to kill spinner on exit
cleanup() {
    if [ -n "$SPINNER_PID" ]; then
        kill "$SPINNER_PID" 2>/dev/null
    fi
}

# Main script logic
main() {
    # Set trap for robust cleanup on exit
    trap cleanup EXIT
    trap 'trap - INT; kill $SPINNER_PID 2>/dev/null; exit 1' INT

    # --- Initial Checks & Configuration ---
    # Source config file if it exists
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
    fi

    # Check for required tools
    for cmd in curl jq diff; do
        if ! command -v "$cmd" &>/dev/null; then
            log_error "Missing required command: $cmd"
            exit 1
        fi
done

    # Get API key from environment or config
    if [ -z "$API_KEY" ]; then
        API_KEY="$GEMINI_API_KEY"
    fi
    if [ -z "$API_KEY" ]; then
        log_error "GEMINI_API_KEY is not set."
        exit 1
    fi

    # --- Argument Parsing ---
    local file1=""
    local file2=""
    while getopts ":o:yh" opt; do
        case $opt in
            o) OUTPUT_FILE="$OPTARG" ;; 
            y) NON_INTERACTIVE=true ;; 
            h) print_usage; exit 0 ;; 
            \?) log_error "Invalid option: -$OPTARG"; print_usage; exit 1 ;; 
        esac
    done
    shift $((OPTIND - 1))
    file1="$1"
    file2="$2"

    # --- File Input and Validation ---
    if [ -z "$file1" ] || [ -z "$file2" ]; then
        if [ "$NON_INTERACTIVE" = true ]; then
            log_error "Two file paths are required as arguments in non-interactive mode."
            print_usage; exit 1
        fi
        echo -e "${C_INFO}Enter the paths to the two files you want to merge.${C_NC}"
        read -e -p " ${C_INPUT}File 1 path: ${C_NC}" file1
        read -e -p " ${C_INPUT}File 2 path: ${C_NC}" file2
    fi

    for f in "$file1" "$file2"; do
        if [ ! -f "$f" ]; then
            log_error "File '$f' not found."
            exit 1
        fi
    done

    # --- Diff and API Interaction ---
    log_info "\nAnalyzing files and generating diff... ✨"
    diff_output=$(diff -u "$file1" "$file2")
    if [ $? -eq 0 ]; then
        log_info "Files are identical. No merge needed. 💫"
        if [ "$NON_INTERACTIVE" = true ]; then exit 0; fi
        read -p "Copy one file to an output file? (y/n): " choice
        if [[ "$choice" =~ ^[Yy]$ ]]; then
            local merged_code=$(cat "$file1")
            local default_name="merged_$(basename "$file1")"
            local output_file_to_use="${OUTPUT_FILE:-$default_name}"
            echo "$merged_code" > "$output_file_to_use"
            log_info "File copied to '$output_file_to_use'. 💾"
        fi
        exit 0
    fi

    # Construct the prompt with advanced instructions
    local prompt_text=$(cat <<EOM
You are an expert code reviewer. Analyze the two code files and their unified diff. Produce a single, complete, and merged version of the code that incorporates the best coding practices. Explain your primary merge decision in a single-line comment at the very top of the output.

File 1:
---
$(cat "$file1")
---

File 2:
---
$(cat "$file2")
---

Diff:
---
$diff_output
---

Output only the final merged code. Do not include any other explanations or introductory text.
EOM
)

    # Call the API with the spinner
    log_info "Summoning Gemini to merge the code... 🔮"
    call_gemini_api "$prompt_text" & 
    SPINNER_PID=$!
    show_spinner $SPINNER_PID
    wait $SPINNER_PID
    local response=$(< /dev/stdin)

    # Process the response
    local merged_code
    merged_code=$(echo "$response" | jq -r '.candidates[0].content.parts[0].text // ""')

    if [ -z "$merged_code" ]; then
        log_error "Gemini returned an empty response. This could be due to safety settings."
        exit 1
    fi

    # Display the result
    echo -e "\n${C_SUCCESS}--- Merged Code (Generated by Gemini) ---${C_NC}"
    echo -e "${C_INPUT}${merged_code}${C_NC}"
    echo -e "${C_SUCCESS}----------------------------------------${C_NC}"

    # Save to file
    local save_choice="n"
    if [ -n "$OUTPUT_FILE" ]; then
        save_choice="y"
    elif [ "$NON_INTERACTIVE" = false ]; then
        read -p "Save merged code to a file? (y/n): " save_choice
    fi

    if [[ "$save_choice" =~ ^[Yy]$ ]]; then
        if [ -z "$OUTPUT_FILE" ]; then
            local base1; base1=$(basename -- "$file1")
            local base2; base2=$(basename -- "$file2")
            OUTPUT_FILE="merged_$(basename "$base1")_$(basename "$base2")"
        fi

        if [ -f "$OUTPUT_FILE" ] && [ "$NON_INTERACTIVE" = false ]; then
            read -p "File '$OUTPUT_FILE' exists. Overwrite? (y/n): " overwrite_choice
            if [[ ! "$overwrite_choice" =~ ^[Yy]$ ]]; then
                log_info "Save cancelled."
                exit 0
            fi
        fi
        # Strip markdown fences and save
        local cleaned_code
        cleaned_code=$(echo "$merged_code" | sed 's/^```[a-zA-Z0-9]*//;s/```$//' | sed '/^```/d')
        echo "$cleaned_code" > "$OUTPUT_FILE"
        log_info "Merged code saved to '$OUTPUT_FILE'. 💾"
    fi
}

main "$@"
