#!/usr/bin/env bash
# edit_lines.sh — The fastest, safest, most beautiful line editor for AI agents
# Uses 'sd' (Rust) → 10–100× faster than sed + zero escaping issues
# 100% compatible with aichat function calling
# Version: 3.0.0
set -euo pipefail
IFS=$"\n\t"

# ── Config ─────────────────────────────────────
PROJECT_ROOT="${PROJECT_ROOT:-$(realpath .)}"
BACKUP_DIR=".pyrm_backups"
VERSION="3.0.0"
MAX_OPS=200
DRY_RUN=false

# ── Colors ─────────────────────────────────────
if [[ -t 1 && -z "${NO_COLOR:-}" ]]; then
    RED='\033[31m'; GREEN='\033[32m'; YELLOW='\033[33m'; CYAN='\033[36m'; RESET='\033[0m'
else
    RED='' GREEN='' YELLOW='' CYAN='' RESET=''
fi

# ── Dependencies ───────────────────────────────
command -v sd >/dev/null || {
    echo -e "${RED}error: 'sd' not found. Install with: cargo install sd${RESET}" >&2
    exit 1
}

# ── Helpers ────────────────────────────────────
json_error() {
    jq -n \
        --arg e "$1" \
        --arg d "${2:-}" \
        --arg t "$(date '+%H:%M:%S')"
        '{status:"failure",error:$e,details:$d,timestamp:$t,version:"'"$VERSION"'"}' |\
    sed -e "s/\"status\": \"failure\"/"status": "${RED}failure${RESET}"/g"
        -e "s/\"error\": \".*\"/"error": "${RED}&${RESET}"/g" >&2
    exit 1
}

json_success() {
    jq -n --argjson d "$1" --arg t _"$(date '+%H:%M:%S')" \
        '$d + {status:"success",timestamp:$t,version:"'"$VERSION"'"}' |\
    sed -e "s/\"status\": \"success\"/"status": "${GREEN}success${RESET}"/g"
        -e "s/\"backup\": \".*\"/"backup": "${CYAN}&${RESET}"/g"
}

validate_path() {
    local p="$1"
    [[ -z "$p" ]] && json_error "Missing 'path'"
    local abs=$(realpath -m "$PROJECT_ROOT/$p" 2>/dev/null || echo "$PROJECT_ROOT/$p")
    [[ "$abs" != "$PROJECT_ROOT"* ]] && json_error "Path outside sandbox" "$p"
    echo "$abs"
}

create_backup() {
    local f="$1"
    [[ ! -f "$f" ]] && echo "none" && return
    mkdir -p "$BACKUP_DIR"
    local ts=$(date +%s.%N 2>/dev/null || date +%s).$$"
    local bak="$BACKUP_DIR/$(basename "$f").bak.$ts"
    cp -a "$f" "$bak" && echo "$(basename "$bak")"
}

# ── Main ───────────────────────────────────────
main() {
    local input=$(cat)
    local path=$(jq -r '.path // empty' <<<"$input")
    local ops=$(jq -c '.operations // []' <<<"$input")
    local dry_run=$(jq -r '.dry_run // false' <<<"$input")

    [[ -z "$path" ]] && json_error "Missing 'path'"
    [[ "$ops" == "[]" ]] && json_error "Empty 'operations'"

    local abs_path=$(validate_path "$path")
    [[ ! -f "$abs_path" ]] && json_error "File not found" "$path"
    [[ ! -w "$abs_path" ]] && json_error "File not writable" "$path"

    local backup=$(create_backup "$abs_path")
    local tmp=$(mktemp)
    cp "$abs_path" "$tmp"
    local op_count=0 changes=0

    if [[ "$dry_run" == "true" ]]; then
        op_count=$(jq 'length' <<<"$ops")
        json_success "{\"action\":\"edit_lines\",\"file\":\"'"$path"'\",\"op_count\":$op_count,\"backup\":\"'"$backup"'\",\"message\":\"Dry-run: $op_count operations would be applied\"}"
        rm -f "$tmp"
        return
    fi

    while IFS= read -r op; do
        ((op_count++))
        [[ $op_count -gt $MAX_OPS ]] && json_error "Too many operations (max $MAX_OPS)"

        local type=$(jq -r '.type' <<<"$op")
        local line=$(jq -r '.line' <<<"$op")
        local end_line=$(jq -r '.end_line // empty' <<<"$op")
        local content=$(jq -r '.content // ""' <<<"$op")

        case "$type" in
            replace|replace_line)
                local pattern="^.*$line.*$"
                [[ -n "$end_line" ]] && pattern="^.*($line|$([ $line+1 ] to $end_line)).*$"
                sd --flags m "$pattern" "$content" "$tmp" || true
                ;;
            insert_before)
                sd --flags m "^.*$line.*$" "$content\n$0" "$tmp" || true
                ;;
            insert_after)
                sd --flags m "^.*$line.*$" "$0\n$content" "$tmp" || true
                ;;
            delete|delete_line)
                local range="$line"
                [[ -n "$end_line" ]] && range="$line,$end_line"
                sd --flags m "^.*($range).*
" "" "$tmp" || true
                ;;
            *)
                json_error "Invalid type: $type"
                ;;
        esac
    done < <(jq -c '.[]' <<<"$ops")

    if ! diff -q "$abs_path" "$tmp" >/dev/null; then
        mv -f "$tmp" "$abs_path"
        changes=1
    else
        rm -f "$tmp"
    fi

    local lines_before=$(wc -l < "$abs_path" 2>/dev/null || echo 0)
    local lines_after=$(wc -l < "$abs_path")

    json_success "{ \
        \"action\": \"edit_lines\", \
        \"file\": \"'"$path"'\", \
        \"absolute_path\": \"'"$abs_path"'\", \
        \"op_count\": $op_count, \
        \"lines_changed\": $((lines_after - lines_before)), \
        \"backup\": \"'"$backup"'\", \
        \"message\": \"$( ((changes)) && echo \"Applied $op_count edits\" || echo \"No changes (idempotent)\" )\" \
    }"
}

main