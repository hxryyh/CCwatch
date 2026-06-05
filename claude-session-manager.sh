#!/usr/bin/env bash
# Claude Code Session Manager
# Usage: claude-session <command> [options]
#
# Commands:
#   list    [project] [days]   - List sessions (optionally filter by project/age)
#   search  <keyword>          - Search session content
#   info    <session-id>       - Show session details
#   clean   <days> [project]   - Delete sessions older than N days
#   clean-all                  - Delete ALL sessions (with confirmation)
#   export  <session-id>       - Export session as readable markdown
#   stats                      - Show session statistics

set -uo pipefail

CLAUDE_DIR="$HOME/.claude"
PROJECTS_DIR="$CLAUDE_DIR/projects"
HISTORY_DIR="$CLAUDE_DIR/file-history"
SESSION_ENV_DIR="$CLAUDE_DIR/session-env"
TASKS_DIR="$CLAUDE_DIR/tasks"
NAMES_FILE="$CLAUDE_DIR/session-names.txt"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

# ─── Helpers ───────────────────────────────────────────────────────────────

project_display_name() {
  # Convert C--Users-Dell back to readable form
  echo "$1" | sed 's|--|/|g; s|^/||'
}

timestamp_to_date() {
  if [[ "$(uname)" == "Darwin" ]]; then
    date -r "$1" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "$1"
  else
    date -d "@$1" "+%Y-%m-%d %H:%M" 2>/dev/null || date -d "@$(echo "$1" | cut -c1-10)" "+%Y-%m-%d %H:%M" 2>/dev/null || echo "$1"
  fi
}

iso_to_date() {
  echo "$1" | sed 's/T/ /; s/\..*//'
}

# Get first user message from a JSONL file (as session summary)
get_first_user_msg() {
  local file="$1"
  local line
  line=$(grep '"type":"user"' "$file" 2>/dev/null | head -1)
  [[ -z "$line" ]] && { echo "(no content)"; return; }

  # Extract content between "content":" and the next " that's not escaped
  # Handle both string content and array content
  local msg
  msg=$(echo "$line" | sed -n 's/.*"content":"\([^"]*\)".*/\1/p' | head -1)
  if [[ -z "$msg" ]]; then
    # Might be array content - just show a placeholder
    msg=$(echo "$line" | sed -n 's/.*"content":\[\(.*\)\].*/[complex content]/p' | head -1)
  fi
  [[ -z "$msg" ]] && msg="(no content)"

  # Truncate and clean up
  msg="${msg:0:120}"
  msg="${msg//\\n/ }"
  echo "$msg"
}

# Get session start time from JSONL
get_session_time() {
  local file="$1"
  grep -o '"timestamp":"[^"]*"' "$file" 2>/dev/null | head -1 | \
    sed 's/"timestamp":"//; s/"//'
}

# Get session message count
get_msg_count() {
  local file="$1"
  grep -c '"type":"user"' "$file" 2>/dev/null || echo "0"
}

# Get session file size
get_file_size() {
  local file="$1"
  if [[ "$(uname)" == "Darwin" ]]; then
    wc -c < "$file" | tr -d ' '
  else
    stat --printf="%s" "$file" 2>/dev/null || wc -c < "$file" | tr -d ' '
  fi
}

format_size() {
  local size=$1
  if (( size > 1048576 )); then
    local val=$(( size * 10 / 1048576 ))
    echo "${val:0:-1}.${val: -1}MB"
  elif (( size > 1024 )); then
    local val=$(( size * 10 / 1024 ))
    echo "${val:0:-1}.${val: -1}KB"
  else
    echo "${size}B"
  fi
}

# ─── Session Names ─────────────────────────────────────────────────────────

# Get custom name for a session ID (supports partial match)
get_session_name() {
  local sid="$1"
  [[ -f "$NAMES_FILE" ]] || return
  local match
  match=$(grep "^${sid}" "$NAMES_FILE" 2>/dev/null | head -1)
  [[ -n "$match" ]] && echo "${match#*|}"
}

# Resolve partial session ID to full ID
resolve_session_id() {
  local partial="$1"
  # If it's already a full 36-char UUID, return as-is
  if [[ ${#partial} -eq 36 ]] && [[ "$partial" =~ ^[0-9a-f]{8}- ]]; then
    echo "$partial"
    return
  fi
  # Search for partial match
  local found=""
  local count=0
  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    for jsonl in "$project_dir"${partial}*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)
      found="$sid"
      ((count++))
    done
  done
  if [[ $count -eq 1 ]]; then
    echo "$found"
  elif [[ $count -gt 1 ]]; then
    echo -e "${RED}Ambiguous ID '$partial' matches $count sessions. Use more characters.${NC}" >&2
    return 1
  else
    echo -e "${RED}No session matching '$partial'${NC}" >&2
    return 1
  fi
}

# Set custom name for a session
set_session_name() {
  local sid="$1"
  local name="$2"
  # Remove existing entry if any
  if [[ -f "$NAMES_FILE" ]]; then
    grep -v "^${sid}|" "$NAMES_FILE" > "$NAMES_FILE.tmp" 2>/dev/null || true
    mv "$NAMES_FILE.tmp" "$NAMES_FILE"
  fi
  # Append new entry
  echo "${sid}|${name}" >> "$NAMES_FILE"
}

# ─── Commands ──────────────────────────────────────────────────────────────

cmd_rename() {
  local partial="${1:?Usage: claude-session rename <session-id> <name>}"
  local name="${2:?Usage: claude-session rename <session-id> <name>}"

  local sid
  sid=$(resolve_session_id "$partial") || return 1

  set_session_name "$sid" "$name"
  echo -e "${GREEN}Renamed${NC} ${BOLD}${sid:0:8}${NC} → ${CYAN}$name${NC}"
}

cmd_names() {
  echo -e "${BOLD}${CYAN}Named Sessions${NC}"
  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"

  if [[ ! -f "$NAMES_FILE" ]] || [[ ! -s "$NAMES_FILE" ]]; then
    echo -e "${DIM}  No named sessions yet.${NC}"
    echo -e "${DIM}  Use: claude-session rename <session-id> <name>${NC}"
    return
  fi

  while IFS='|' read -r sid name; do
    [[ -z "$sid" ]] && continue
    # Find project for this session
    local project=""
    for project_dir in "$PROJECTS_DIR"/*/; do
      [[ -d "$project_dir" ]] || continue
      if [[ -f "$project_dir${sid}.jsonl" ]]; then
        project=$(project_display_name "$(basename "$project_dir")")
        break
      fi
    done
    printf "  ${BOLD}%-12s${NC}  ${CYAN}%-30s${NC}  ${DIM}%s${NC}\n" "${sid:0:12}" "$name" "$project"
  done < "$NAMES_FILE"
}

cmd_list() {
  local filter_project="${1:-}"
  local filter_days="${2:-}"

  local cutoff_ts=""
  if [[ -n "$filter_days" ]]; then
    cutoff_ts=$(date -d "now - ${filter_days} days" +%s 2>/dev/null || date -v-${filter_days}d +%s 2>/dev/null || echo "")
  fi

  echo -e "${BOLD}${CYAN}Claude Code Sessions${NC}"
  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
  printf "${BOLD}%-12s  %-24s  %-16s  %-7s  %-10s  %s${NC}\n" "ID" "NAME" "DATE" "MSGS" "SIZE" "FIRST MESSAGE"
  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"

  local count=0
  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local project_name
    project_name=$(basename "$project_dir")

    if [[ -n "$filter_project" ]] && [[ "$project_name" != *"$filter_project"* ]]; then
      continue
    fi

    for jsonl in "$project_dir"*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)

      local ts
      ts=$(get_session_time "$jsonl")
      [[ -z "$ts" ]] && continue

      local ts_epoch
      ts_epoch=$(date -d "$ts" +%s 2>/dev/null || date -jf "%Y-%m-%dT%H:%M:%S" "$ts" +%s 2>/dev/null || echo "0")

      if [[ -n "$cutoff_ts" ]] && (( ts_epoch > cutoff_ts )); then
        continue
      fi

      local date_str
      date_str=$(iso_to_date "$ts")
      local msg_count
      msg_count=$(get_msg_count "$jsonl")
      local fsize
      fsize=$(format_size "$(get_file_size "$jsonl")")
      local summary
      summary=$(get_first_user_msg "$jsonl")

      # Truncate summary for display
      if [[ ${#summary} -gt 50 ]]; then
        summary="${summary:0:47}..."
      fi

      # Color-code by age
      local age_days=$(( ($(date +%s) - ts_epoch) / 86400 ))
      local date_color="$NC"
      if (( age_days > 14 )); then
        date_color="$RED"
      elif (( age_days > 7 )); then
        date_color="$YELLOW"
      else
        date_color="$GREEN"
      fi

      local display_name
      display_name=$(get_session_name "$sid")
      if [[ -n "$display_name" ]]; then
        display_name="${CYAN}${display_name}${NC}"
      else
        display_name="${DIM}—${NC}"
      fi

      printf "%-12s  %b  ${date_color}%-16s${NC}  %-7s  %-10s  ${DIM}%s${NC}\n" \
        "${sid:0:12}" "$display_name" "$date_str" "$msg_count" "$fsize" "$summary"
      ((count++))
    done
  done

  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
  echo -e "Total: ${BOLD}$count${NC} sessions"
}

cmd_search() {
  local keyword="${1:?Usage: claude-session search <keyword>}"
  echo -e "${BOLD}${CYAN}Searching for: ${YELLOW}$keyword${NC}"
  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"

  local count=0
  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local project_name
    project_name=$(basename "$project_dir")

    for jsonl in "$project_dir"*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)

      local matches
      matches=$(grep -ic "$keyword" "$jsonl" 2>/dev/null || echo "0")
      matches="${matches//[$'\r\n\t ']}"
      [[ -z "$matches" ]] && matches="0"
      if (( matches > 0 )); then
        local ts
        ts=$(get_session_time "$jsonl")
        local date_str
        date_str=$(iso_to_date "$ts")
        local summary
        summary=$(get_first_user_msg "$jsonl")

        local custom_name
        custom_name=$(get_session_name "$sid")

        echo -e "${GREEN}[$date_str]${NC} ${BOLD}$sid${NC} (${CYAN}$matches matches${NC})"
        [[ -n "$custom_name" ]] && echo -e "  ${BOLD}Name:${NC} ${CYAN}$custom_name${NC}"
        echo -e "  ${DIM}Project: $(project_display_name "$project_name")${NC}"
        echo -e "  ${DIM}Summary: $summary${NC}"

        # Show first matching line
        local context
        context=$(grep -i "$keyword" "$jsonl" 2>/dev/null | head -1 | \
          python3 -c "
import sys, json
try:
    line = sys.stdin.readline()
    if line:
        d = json.loads(line)
        msg = d.get('message', {}).get('content', '')
        if isinstance(msg, list):
            msg = ' '.join(str(m.get('text', '')) if isinstance(m, dict) else str(m) for m in msg)
        msg = msg.replace('\n', ' ').strip()[:150]
        if msg: print(f'  Context: {msg}')
except: pass
" 2>/dev/null)
        [[ -n "$context" ]] && echo -e "  ${DIM}$context${NC}"
        echo ""
        ((count++))
      fi
    done
  done

  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
  echo -e "Found: ${BOLD}$count${NC} sessions containing '$keyword'"
}

cmd_info() {
  local partial="${1:?Usage: claude-session info <session-id>}"
  local sid
  sid=$(resolve_session_id "$partial") || return 1
  local found=0

  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local jsonl="$project_dir${sid}.jsonl"
    [[ -f "$jsonl" ]] || continue

    found=1
    local project_name
    project_name=$(project_display_name "$(basename "$project_dir")")
    local ts
    ts=$(get_session_time "$jsonl")
    local msg_count
    msg_count=$(get_msg_count "$jsonl")
    local fsize
    fsize=$(format_size "$(get_file_size "$jsonl")")
    local summary
    summary=$(get_first_user_msg "$jsonl")

    local custom_name
    custom_name=$(get_session_name "$sid")

    echo -e "${BOLD}${CYAN}Session Details${NC}"
    echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
    echo -e "${BOLD}ID:${NC}        $sid"
    [[ -n "$custom_name" ]] && echo -e "${BOLD}Name:${NC}      ${CYAN}$custom_name${NC}"
    echo -e "${BOLD}Project:${NC}   $project_name"
    echo -e "${BOLD}Started:${NC}   $(iso_to_date "$ts")"
    echo -e "${BOLD}Messages:${NC}  $msg_count user messages"
    echo -e "${BOLD}Size:${NC}      $fsize"
    echo -e "${BOLD}Summary:${NC}   $summary"
    echo ""

    # Check for related data
    [[ -d "$HISTORY_DIR/$sid" ]] && echo -e "${GREEN}✓${NC} File history available"
    [[ -d "$SESSION_ENV_DIR/$sid" ]] && echo -e "${GREEN}✓${NC} Session environment saved"
    [[ -d "$TASKS_DIR/$sid" ]] && echo -e "${GREEN}✓${NC} Task data available"
    break
  done

  if (( ! found )); then
    echo -e "${RED}Session not found: $sid${NC}"
    return 1
  fi
}

cmd_clean() {
  local days="${1:?Usage: claude-session clean <days> [project]}"
  local filter_project="${2:-}"

  local cutoff_ts
  cutoff_ts=$(date -d "now - ${days} days" +%s 2>/dev/null || date -v-${days}d +%s 2>/dev/null)
  [[ -z "$cutoff_ts" ]] && { echo -e "${RED}Cannot compute cutoff date${NC}"; return 1; }

  local to_delete=()

  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local project_name
    project_name=$(basename "$project_dir")

    if [[ -n "$filter_project" ]] && [[ "$project_name" != *"$filter_project"* ]]; then
      continue
    fi

    for jsonl in "$project_dir"*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)

      local ts
      ts=$(get_session_time "$jsonl")
      [[ -z "$ts" ]] && continue

      local ts_epoch
      ts_epoch=$(date -d "$ts" +%s 2>/dev/null || echo "0")

      if (( ts_epoch < cutoff_ts )); then
        to_delete+=("$jsonl|$sid|$project_name")
      fi
    done
  done

  if [[ ${#to_delete[@]} -eq 0 ]]; then
    echo -e "${GREEN}No sessions older than $days days found.${NC}"
    return 0
  fi

  echo -e "${YELLOW}Found ${#to_delete[@]} sessions older than $days days:${NC}"
  for entry in "${to_delete[@]}"; do
    local sid="${entry#*|}"
    sid="${sid%|*}"
    echo -e "  ${DIM}$sid${NC}"
  done

  echo ""
  read -p "$(echo -e ${YELLOW}Delete these sessions? [y/N]: ${NC})" confirm
  if [[ "$confirm" =~ ^[yY]$ ]]; then
    local deleted=0
    for entry in "${to_delete[@]}"; do
      local jsonl="${entry%%|*}"
      local sid="${entry#*|}"
      sid="${sid%|*}"

      rm -f "$jsonl"
      rm -rf "$HISTORY_DIR/$sid"
      rm -rf "$SESSION_ENV_DIR/$sid"
      rm -rf "$TASKS_DIR/$sid"
      # Also remove session subdirectory if exists
      rm -rf "$(dirname "$jsonl")/$sid"
      ((deleted++))
    done
    echo -e "${GREEN}Deleted $deleted sessions and associated data.${NC}"
  else
    echo -e "${DIM}Cancelled.${NC}"
  fi
}

cmd_clean_all() {
  echo -e "${RED}${BOLD}WARNING: This will delete ALL session transcripts!${NC}"
  read -p "$(echo -e ${YELLOW}Type 'yes' to confirm: ${NC})" confirm
  if [[ "$confirm" != "yes" ]]; then
    echo -e "${DIM}Cancelled.${NC}"
    return 0
  fi

  local count=0
  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    for jsonl in "$project_dir"*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)
      rm -f "$jsonl"
      rm -rf "$HISTORY_DIR/$sid"
      rm -rf "$SESSION_ENV_DIR/$sid"
      rm -rf "$TASKS_DIR/$sid"
      rm -rf "$(dirname "$jsonl")/$sid"
      ((count++))
    done
  done

  echo -e "${GREEN}Deleted $count sessions.${NC}"
}

cmd_export() {
  local partial="${1:?Usage: claude-session export <session-id>}"
  local sid
  sid=$(resolve_session_id "$partial") || return 1
  local output="${2:-$HOME/session-${sid:0:8}.md}"
  local found=0

  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local jsonl="$project_dir${sid}.jsonl"
    [[ -f "$jsonl" ]] || continue

    found=1
    local project_name
    project_name=$(project_display_name "$(basename "$project_dir")")
    local ts
    ts=$(get_session_time "$jsonl")

    {
      echo "# Claude Code Session"
      echo ""
      echo "- **ID:** $sid"
      echo "- **Project:** $project_name"
      echo "- **Date:** $(iso_to_date "$ts")"
      echo ""
      echo "---"
      echo ""

      python3 -c "
import sys, json

with open('$jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        try:
            d = json.loads(line.strip())
        except:
            continue

        t = d.get('type', '')
        ts = d.get('timestamp', '')

        if t == 'user':
            msg = d.get('message', {}).get('content', '')
            if isinstance(msg, list):
                msg = ' '.join(str(m.get('text', '')) if isinstance(m, dict) else str(m) for m in msg)
            msg = msg.strip()
            if msg:
                print(f'## User\n')
                print(f'{msg}\n')

        elif t == 'assistant':
            msg = d.get('message', {}).get('content', '')
            if isinstance(msg, list):
                parts = []
                for m in msg:
                    if isinstance(m, dict):
                        if m.get('type') == 'text':
                            parts.append(m.get('text', ''))
                        elif m.get('type') == 'tool_use':
                            parts.append(f'[Tool: {m.get(\"name\", \"unknown\")}]')
                    elif isinstance(m, str):
                        parts.append(m)
                msg = ' '.join(parts)
            msg = msg.strip()
            if msg:
                print(f'## Assistant\n')
                print(f'{msg}\n')
" 2>/dev/null
    } > "$output"

    echo -e "${GREEN}Exported to: $output${NC}"
    break
  done

  if (( ! found )); then
    echo -e "${RED}Session not found: $sid${NC}"
    return 1
  fi
}

cmd_stats() {
  echo -e "${BOLD}${CYAN}Claude Code Session Statistics${NC}"
  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"

  local total_sessions=0
  local total_size=0
  local total_msgs=0
  local oldest=""
  local newest=""

  echo -e "\n${BOLD}Per-Project Breakdown:${NC}\n"

  for project_dir in "$PROJECTS_DIR"/*/; do
    [[ -d "$project_dir" ]] || continue
    local project_name
    project_name=$(project_display_name "$(basename "$project_dir")")
    local p_count=0
    local p_size=0
    local p_msgs=0

    for jsonl in "$project_dir"*.jsonl; do
      [[ -f "$jsonl" ]] || continue
      local sid
      sid=$(basename "$jsonl" .jsonl)
      local ts
      ts=$(get_session_time "$jsonl")

      local fsize
      fsize=$(get_file_size "$jsonl")
      local mc
      mc=$(get_msg_count "$jsonl")

      ((p_count++))
      ((p_size += fsize))
      ((p_msgs += mc))

      if [[ -z "$oldest" ]] || [[ "$ts" < "$oldest" ]]; then
        oldest="$ts"
      fi
      if [[ -z "$newest" ]] || [[ "$ts" > "$newest" ]]; then
        newest="$ts"
      fi
    done

    if (( p_count > 0 )); then
      printf "  ${BOLD}%-50s${NC}  %3d sessions  %8s  %4d msgs\n" \
        "$project_name" "$p_count" "$(format_size $p_size)" "$p_msgs"
      ((total_sessions += p_count))
      ((total_size += p_size))
      ((total_msgs += p_msgs))
    fi
  done

  echo -e "${DIM}────────────────────────────────────────────────────────────────${NC}"
  echo -e "\n${BOLD}Summary:${NC}"
  echo -e "  Total sessions:    ${BOLD}$total_sessions${NC}"
  echo -e "  Total messages:    ${BOLD}$total_msgs${NC}"
  echo -e "  Total size:        ${BOLD}$(format_size $total_size)${NC}"
  [[ -n "$oldest" ]] && echo -e "  Oldest session:    ${DIM}$(iso_to_date "$oldest")${NC}"
  [[ -n "$newest" ]] && echo -e "  Newest session:    ${DIM}$(iso_to_date "$newest")${NC}"
  echo ""

  # Disk usage of related dirs
  local history_size=0
  local env_size=0
  local tasks_size=0
  [[ -d "$HISTORY_DIR" ]] && history_size=$(du -sh "$HISTORY_DIR" 2>/dev/null | cut -f1)
  [[ -d "$SESSION_ENV_DIR" ]] && env_size=$(du -sh "$SESSION_ENV_DIR" 2>/dev/null | cut -f1)
  [[ -d "$TASKS_DIR" ]] && tasks_size=$(du -sh "$TASKS_DIR" 2>/dev/null | cut -f1)

  echo -e "${BOLD}Related Data:${NC}"
  echo -e "  File history:      ${DIM}$history_size${NC}"
  echo -e "  Session env:       ${DIM}$env_size${NC}"
  echo -e "  Tasks:             ${DIM}$tasks_size${NC}"
}

# ─── Main ──────────────────────────────────────────────────────────────────

cmd="${1:-help}"
shift 2>/dev/null || true

case "$cmd" in
  list|ls)    cmd_list "$@" ;;
  search|grep) cmd_search "$@" ;;
  info|show)  cmd_info "$@" ;;
  rename|rn)  cmd_rename "$@" ;;
  names)      cmd_names ;;
  clean)      cmd_clean "$@" ;;
  clean-all)  cmd_clean_all ;;
  export)     cmd_export "$@" ;;
  stats)      cmd_stats ;;
  help|--help|-h)
    echo -e "${BOLD}${CYAN}Claude Code Session Manager${NC}"
    echo ""
    echo "Usage: claude-session <command> [options]"
    echo ""
    echo "Commands:"
    echo "  list    [project] [days]   List sessions (filter by project name or age)"
    echo "  rename  <id> <name>        Give a session a custom name (supports partial ID)"
    echo "  names                      List all named sessions"
    echo "  search  <keyword>          Search session content"
    echo "  info    <session-id>       Show session details"
    echo "  clean   <days> [project]   Delete sessions older than N days"
    echo "  clean-all                  Delete ALL sessions (with confirmation)"
    echo "  export  <session-id> [out] Export session as markdown"
    echo "  stats                      Show session statistics"
    echo ""
    echo "Examples:"
    echo "  claude-session list                    # List all sessions"
    echo "  claude-session rename abc123 简历优化    # Name a session"
    echo "  claude-session names                   # Show all named sessions"
    echo "  claude-session search 'authentication' # Search for keyword"
    echo "  claude-session clean 14                # Clean sessions older than 14 days"
    echo "  claude-session export abc123           # Export session to markdown"
    ;;
  *)
    echo -e "${RED}Unknown command: $cmd${NC}"
    echo "Run 'claude-session help' for usage."
    exit 1
    ;;
esac
