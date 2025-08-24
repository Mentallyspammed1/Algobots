#!/usr/bin/env bash
# pyrm_setup_v3.sh — Termux aichat + pyrm agent setup with safe logging
set -euo pipefail

# ---------- Early paths (create before logging) ----------
HOME_DIR="${HOME}"
XDG_CACHE_HOME="${XDG_CACHE_HOME:-$HOME_DIR/.cache}"
CFG_DIR="${HOME_DIR}/.config/aichat"
TOOLS_DIR="${CFG_DIR}/toolkits/web-tools"
PLUGINS_DIR="${CFG_DIR}/plugins"
LOCAL_BIN="${HOME_DIR}/.local/bin"
CACHE_DIR="${XDG_CACHE_HOME}/aichat"
LOG_DIR="${CACHE_DIR}/logs"
SESS_DIR="${CACHE_DIR}/sessions"

mkdir -p "$LOG_DIR" "$SESS_DIR" "$CFG_DIR" "$LOCAL_BIN"

# ---------- Logging (attach after dirs exist) ----------
TS="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="${LOG_DIR}/setup_${TS}.log"
if touch "$LOG_FILE" 2>/dev/null; then
  exec > >(tee -a "$LOG_FILE") 2>&1
  echo "[i] Logging to: $LOG_FILE"
else
  echo "[!] Could not open $LOG_FILE for writing; proceeding without file logging." >&2
fi

umask 077

# ---------- UI helpers ----------
GREEN='\033[1;32m'; YELLOW='\033[1;33m'; RED='\033[1;31m'; CYAN='\033[1;36m'; NC='\033[0m'
info(){ printf "${CYAN}[i]${NC} %s\n" "$*"; }
ok(){ printf "${GREEN}[✓]${NC} %s\n" "$*"; }
warn(){ printf "${YELLOW}[!]${NC} %s\n" "$*"; }
err(){ printf "${RED}[x]${NC} %s\n" "$*" >&2; }

trap 'rc=$?; if [ $rc -eq 0 ]; then ok "Setup finished."; else err "Setup failed (exit $rc). See $LOG_FILE"; fi' EXIT

backup() { [ -f "$1" ] && cp -f "$1" "$1.bak.$(date +%Y%m%d-%H%M%S)" && info "Backed up $1"; }

# ---------- Ensure remaining dirs ----------
ensure_dirs() {
  mkdir -p "$TOOLS_DIR" "$PLUGINS_DIR" "$HOME_DIR/tools"
  ok "Directories ready"
}

# ---------- Termux deps ----------
install_termux_deps() {
  info "Installing Termux packages…"
  pkg update -y
  pkg install -y curl jq python git
  if ! command -v aichat >/dev/null 2>&1; then
    pkg install -y golang
    if ! grep -q 'export GOPATH=' "${HOME_DIR}/.bashrc" 2>/dev/null; then
      echo 'export GOPATH="$HOME/go"' >> "${HOME_DIR}/.bashrc"
      echo 'export PATH="$PATH:$GOPATH/bin"' >> "${HOME_DIR}/.bashrc"
    fi
    # shellcheck source=/dev/null
    [ -f "${HOME_DIR}/.bashrc" ] && . "${HOME_DIR}/.bashrc"
    GO111MODULE=on go install github.com/sigoden/aichat@latest
    export PATH="$PATH:${HOME_DIR}/go/bin"
    ok "Installed aichat via go install"
  else
    ok "aichat already installed"
  fi
  python - <<'PY' >/dev/null 2>&1 || pip install --no-cache-dir --upgrade duckduckgo_search >/dev/null
try:
  import duckduckgo_search  # noqa: F401
  print("ok")
except Exception:
  raise SystemExit(1)
PY
  ok "Python deps ok"
}

# ---------- Write config.yaml ----------
write_config() {
  local cfg="${CFG_DIR}/config.yaml"
  backup "$cfg"
  cat > "$cfg" <<'YAML'
# aichat global configuration — Termux friendly, secrets-safe
model: gemini:gemini-2.5-flash-lite
clients:
  - type: gemini
    api_key: ${GEMINI_API_KEY}
    extra:
      retry_count: 3
      timeout_ms: 60000

serve_addr: 127.0.0.1:8080
user_agent: 'aichat/2.0-pyrmethus-termux-enchantment'
save_shell_history: true
syncModelsURL: https://raw.githubusercontent.com/sigoden/aichat/main/models.yaml

temperature: 0.6
top_p: 0.95
max_output_tokens: 65536
max_input_tokens: 128000

stream: true
save: true
keybinding: nano
editor: vim

wrap_code: true
highlight: true
save_session: true
compress_threshold: 150000
copy_to_clipboard: true
light_theme: false

function_calling: true
use_tools: true

mapping_tools:
  web-tools: 'web_search'
  sys-tools: 'sys_find_files,sys_disk_usage,sys_mem_usage,sys_cpu_usage,sys_env,sys_which,sys_date'
  dev-tools: 'py_create_venv,py_install_reqs,py_run_tests,py_lint_file,archive_create,archive_extract,proc_list,proc_kill,net_curl'
  edit-tools: 'read_file,write_file,apply_patch,diff_paths,search_in_files,show_tree'
  fs: 'fs_cat,fs_ls,fs_mkdir,fs_rm,fs_write'
  py-tools: 'py_create_project,py_run_script,py_add_dep,py_format_file'
  git-tools: 'git_clone,git_status,git_log,git_diff,git_add,git_commit,git_push,git_pull,git_branch,git_checkout,git_init'
  fs-plus-tools: 'fs_zip.sh,fs_tree.sh,fs_sed.sh'
  data-tools: 'data_jq.sh,data_base64.sh'
  net-tools: 'net_my_ip.sh,net_download.sh,web_search.sh'
  fs_patch: 'fs_patch_apply,fs_patch_create,fs_patch_validate'
  general: 'web_search,get_current_time,calculate_expression,get_env_var,set_env_var,encode_base64,decode_base64,hash_string,generate_uuid,convert_units,generate_passcode'
  code_analysis: 'lint_code,format_code,check_syntax,count_lines_of_code,find_text_in_files,compare_files,analyze_python_code,analyze_javascript_code,generate_code_documentation'
  pkg_mgmt: 'install_package,list_dependencies,update_packages,remove_package,check_package_version,search_termux_packages,install_python_package,install_npm_package'
  code_exec: 'execute_code,run_tests,run_script,run_python_script,run_javascript_script,run_bash_script'
  debug: 'check_port_availability,ping_host,view_process_list,kill_process,check_port_status,trace_network_route'
  api_data: 'make_http_request,parse_json_string,get_crypto_price,simulate_bybit_trade,fetch_rss_feed'
  project_docs: 'generate_boilerplate,read_man_page,search_docs,generate_readme,create_project_structure'
  plugins: 'weather_plugin'

tools:
  enabled: true
  paths:
    - /data/data/com.termux/files/home/.config/aichat/tools
    - /data/data/com.termux/files/home/.config/aichat/toolkits
    - /data/data/com.termux/files/home/.config/aichat/plugins
    - /data/data/com.termux/files/home/tools

agents:
  pyrm:
    description: "Codewiz, the Coding Alchemist — Termux-optimized developer agent with web search."
    model: gemini:gemini-2.5-flash-lite
    use_tools: true
    function_calling: true
    prelude: |
      system: |
        name: "Codewiz, the Coding Alchemist"
        description: "A digital sage specializing in elegant, robust code."
        duties:
          - title: "Operate within the Termux Environment"
            description: "Use 'pkg'; avoid 'brew'/'apt-get'."
          - title: "Deliver Complete Solutions"
            description: "Runnable code with dependencies and usage."
          - title: "Scry the Aether"
            description: "Use web_search when external info is needed."
      summarize_prompt: 'Distill this session into a concise log.'

rag_embedding_model: gemini:text-embedding-004
rag_top_k: 8
rag_chunk_size: 1024
rag_chunk_overlap: 256
rag_template: |
  From the ancient scrolls of knowledge:
  __CONTEXT__

  Answer with wisdom and precision:
  __INPUT__

debug_mode: false
log_file: /data/data/com.termux/files/home/.config/aichat/aichat.log
log_level: info

plugins:
  - name: weather
    script: /data/data/com.termux/files/home/.config/aichat/plugins/weather_plugin.sh

suggestionsEnabled: true
multiModalEnabled: false
offlineMode: false
cacheFile: /data/data/com.termux/files/home/.config/aichat/cache.db
serverAddress: "127.0.0.1:8080"

themes:
  default:
    prompt_color: "\033[1;96m"
    response_color: "\033[1;92m"
    error_color: "\033[1;91m"
    code_color: "\033[1;93m"
    success_color: "\033[1;95m"
YAML
  chmod 600 "$cfg"
  ok "Wrote $cfg"
}

# ---------- .env for API key ----------
write_env() {
  local envf="${CFG_DIR}/.env"
  if [ ! -f "$envf" ]; then
    cat > "$envf" <<'ENV'
# ~/.config/aichat/.env
# Put your Gemini key here, e.g.:
# GEMINI_API_KEY="YOUR_KEY_HERE"
ENV
    chmod 600 "$envf"
    ok "Created $envf"
  else
    info "$envf exists; keeping"
  fi
}

# ---------- web_search.sh ----------
write_web_search() {
  mkdir -p "$TOOLS_DIR"
  local f="${TOOLS_DIR}/web_search.sh"
  cat > "$f" <<'BASH'
#!/usr/bin/env bash
# web_search.sh — DuckDuckGo HTML search (no API keys), TSV/JSON output
set -euo pipefail
FORMAT="tsv"
LIMIT=10
SLEEP_BASE=1
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
DDG_HTML="https://html.duckduckgo.com/html"
print_help(){ cat <<EOF
Usage: $(basename "$0") [options] "query"
  -n N    Max results (10)
  -f fmt  tsv|json (tsv)
  -h      Help
EOF
}
while getopts ":n:f:h" opt; do
  case "$opt" in
    n) LIMIT="${OPTARG}" ;;
    f) FORMAT="${OPTARG}" ;;
    h) print_help; exit 0 ;;
    \?) echo "Unknown option: -$OPTARG" >&2; exit 2 ;;
    :) echo "Option -$OPTARG requires an argument." >&2; exit 2 ;;
  esac
done
shift $((OPTIND - 1))
QUERY="${*:-latest AI news}"
ENC_QUERY="$(printf '%s' "$QUERY" | sed 's/ \+/+/g')"
URL="${DDG_HTML}/?q=${ENC_QUERY}"
attempt_fetch(){
  local tries=0 max=4 html=""
  while :; do
    if html="$(curl -sSL --compressed -A "$UA" "$URL")"; then
      if grep -q 'class="result__a"' <<<"$html"; then
        printf '%s' "$html"; return 0
      fi
    fi
    tries=$((tries+1)); [ "$tries" -ge "$max" ] && { printf '%s' "$html"; return 0; }
    sleep $((SLEEP_BASE * tries))
  done
}
HTML="$(attempt_fetch)"
parse_tsv(){
  printf '%s' "$HTML" \
  | tr '\n' ' ' \
  | sed -n 's/.*<a[^>]*class="result__a"[^>]*href="\([^"]\+\)".*?>\([^<]\{1,\}\)<\/a>.*/\2\t\1/p' \
  | sed 's/<[^>]*>//g' \
  | head -n "$LIMIT"
}
tsv_to_json(){
  awk -v limit="$LIMIT" '
    BEGIN{print "["}
    {
      gsub(/\\/,"\\\\",$1); gsub(/"/,"\\\"",$1)
      gsub(/\\/,"\\\\",$2); gsub(/"/,"\\\"",$2)
      printf "  {\"title\":\"%s\",\"url\":\"%s\"}", $1, $2
      i++; if (i<limit) {print ","} else {print ""}
    }
    END{print "]"}' <(cat)
}
RESULTS="$(parse_tsv)"
if [ -z "$RESULTS" ]; then
  ALT_URL="https://duckduckgo.com/html/?q=${ENC_QUERY}"
  HTML="$(curl -sSL --compressed -A "$UA" "$ALT_URL" || true)"
  RESULTS="$(printf '%s' "$HTML" | tr '\n' ' ' \
    | sed -n 's/.*<a[^>]*class="result__a"[^>]*href="\([^"]\+\)".*?>\([^<]\{1,\}\)<\/a>.*/\2\t\1/p' \
    | sed 's/<[^>]*>//g' | head -n "$LIMIT")"
fi
if [ "$FORMAT" = "json" ]; then printf '%s\n' "$RESULTS" | tsv_to_json; else printf '%s\n' "$RESULTS"; fi
BASH
  chmod +x "$f"
  ok "Wrote $f"
}

# ---------- weather_plugin.sh ----------
write_weather_plugin() {
  local f="${PLUGINS_DIR}/weather_plugin.sh"
  cat > "$f" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
CITY="${1:-New York}"
FORMAT="${2:-tsv}"
if [ "$FORMAT" = "json" ]; then
  curl -s "https://wttr.in/${CITY// /%20}?format=j1"
else
  curl -s "https://wttr.in/${CITY// /%20}?format=3"
fi
BASH
  chmod +x "$f"
  ok "Wrote $f"
}

# ---------- wrapper ----------
write_wrapper() {
  local f="${LOCAL_BIN}/aichat-pyrm"
  cat > "$f" <<'BASH'
#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="$HOME/.config/aichat/.env"
[ -f "$ENV_FILE" ] && . "$ENV_FILE"
if [ -z "${GEMINI_API_KEY:-}" ]; then
  echo "GEMINI_API_KEY not set. Edit $ENV_FILE and set it, then re-run." >&2
  exit 1
fi
exec aichat -a pyrm "$@"
BASH
  chmod +x "$f"
  case ":$PATH:" in *":$LOCAL_BIN:"*) :;; *) echo 'export PATH="$HOME/.local/bin:$PATH"' >> "${HOME_DIR}/.bashrc";; esac
  ok "Wrote $f"
}

# ---------- Post checks ----------
post_checks() {
  info "Verifying executables…"
  chmod +x "${TOOLS_DIR}/web_search.sh" "${PLUGINS_DIR}/weather_plugin.sh" || true
  curl -A "Mozilla/5.0" -sSL --compressed https://duckduckgo.com/?q=ping >/dev/null && ok "Network OK"
  echo
  echo "Next steps:"
  echo "  1) Put your key in ${CFG_DIR}/.env (chmod 600 is set):"
  echo '       GEMINI_API_KEY="YOUR_KEY_HERE"'
  echo "  2) Test web tool:"
  echo "       ${TOOLS_DIR}/web_search.sh -n 5 -f json \"latest AI news\""
  echo "  3) Launch agent:"
  echo "       aichat-pyrm \"Use web_search to list 3 links on 'open source LLMs' in JSON.\""
  echo "  4) Weather tool:"
  echo "       ${PLUGINS_DIR}/weather_plugin.sh \"New York\""
  echo
}

main() {
  info "Initializing directory structure…"
  ensure_dirs
  install_termux_deps
  write_config
  write_env
  write_web_search
  write_weather_plugin
  write_wrapper
  post_checks
}
main "$@"
