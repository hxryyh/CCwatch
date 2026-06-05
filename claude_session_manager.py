#!/usr/bin/env python3
"""Claude Code Session Manager - CLI tool for managing Claude Code sessions."""

import os
import sys
import json
import glob
import time
from pathlib import Path
from datetime import datetime, timedelta

# --- Paths -----------------------------------------------------------------

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_DIR = CLAUDE_DIR / "file-history"
SESSION_ENV_DIR = CLAUDE_DIR / "session-env"
TASKS_DIR = CLAUDE_DIR / "tasks"
NAMES_FILE = CLAUDE_DIR / "session-names.txt"

# --- Colors ----------------------------------------------------------------

class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    DIM = '\033[2m'
    BOLD = '\033[1m'
    NC = '\033[0m'

    @staticmethod
    def disable():
        for attr in ['RED', 'GREEN', 'YELLOW', 'BLUE', 'CYAN', 'DIM', 'BOLD', 'NC']:
            setattr(C, attr, '')

# --- Helpers ---------------------------------------------------------------

def project_display_name(dirname: str) -> str:
    return dirname.replace("--", "/").lstrip("/")

def iso_to_date(ts: str) -> str:
    return ts.replace("T", " ").split(".")[0]

def format_size(size: int) -> str:
    if size > 1048576:
        return f"{size/1048576:.1f}MB"
    elif size > 1024:
        return f"{size/1024:.1f}KB"
    return f"{size}B"

def get_session_names() -> dict:
    names = {}
    if NAMES_FILE.exists():
        for line in NAMES_FILE.read_text(encoding="utf-8").splitlines():
            if "|" in line:
                sid, name = line.split("|", 1)
                names[sid.strip()] = name.strip()
    return names

def set_session_name(sid: str, name: str):
    names = get_session_names()
    names[sid] = name
    lines = [f"{k}|{v}" for k, v in names.items()]
    NAMES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

def resolve_session_id(partial: str) -> str | None:
    matches = []
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for f in project_dir.glob(f"{partial}*.jsonl"):
            matches.append(f.stem)
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"{C.RED}Ambiguous ID '{partial}' matches {len(matches)} sessions.{C.NC}")
        return None
    else:
        print(f"{C.RED}No session matching '{partial}'{C.NC}")
        return None

def parse_jsonl(filepath: Path) -> list[dict]:
    entries = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        pass
    return entries

def get_session_info(filepath: Path) -> dict:
    entries = parse_jsonl(filepath)
    info = {
        "sid": filepath.stem,
        "timestamp": "",
        "msg_count": 0,
        "first_msg": "(no content)",
        "size": filepath.stat().st_size,
    }
    for e in entries:
        ts = e.get("timestamp", "")
        if ts and not info["timestamp"]:
            info["timestamp"] = ts
        if e.get("type") == "user":
            info["msg_count"] += 1
            if info["first_msg"] == "(no content)":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    msg = " ".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in msg)
                if isinstance(msg, str) and msg.strip():
                    info["first_msg"] = msg.strip().replace("\n", " ")[:120]
    return info

# --- Commands --------------------------------------------------------------

def cmd_list(args: list[str]):
    filter_project = args[0] if len(args) > 0 else ""
    filter_days = int(args[1]) if len(args) > 1 else 0

    cutoff = 0
    if filter_days:
        cutoff = time.time() - filter_days * 86400

    names = get_session_names()
    sessions = []

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        pname = project_dir.name
        if filter_project and filter_project not in pname:
            continue
        for jsonl in sorted(project_dir.glob("*.jsonl")):
            info = get_session_info(jsonl)
            if not info["timestamp"]:
                continue
            ts_epoch = 0
            try:
                ts_epoch = datetime.fromisoformat(info["timestamp"].replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
            if cutoff and ts_epoch > cutoff:
                continue
            info["project"] = project_dir.name
            info["ts_epoch"] = ts_epoch
            info["name"] = names.get(info["sid"], "")
            sessions.append(info)

    print(f"{C.BOLD}{C.CYAN}Claude Code Sessions{C.NC}")
    print(f"{C.DIM}{'-' * 90}{C.NC}")
    print(f"{C.BOLD}{'ID':<12}  {'NAME':<24}  {'DATE':<18}  {'MSGS':<6}  {'SIZE':<10}  FIRST MESSAGE{C.NC}")
    print(f"{C.DIM}{'-' * 90}{C.NC}")

    for s in sessions:
        sid_short = s["sid"][:12]
        name = s["name"] if s["name"] else f"{C.DIM}—{C.NC}"
        date_str = iso_to_date(s["timestamp"])
        age_days = int((time.time() - s["ts_epoch"]) / 86400) if s["ts_epoch"] else 999

        if age_days > 14:
            dc = C.RED
        elif age_days > 7:
            dc = C.YELLOW
        else:
            dc = C.GREEN

        summary = s["first_msg"][:50] + "..." if len(s["first_msg"]) > 50 else s["first_msg"]

        print(f"{sid_short:<12}  {name:<33}  {dc}{date_str:<18}{C.NC}  {s['msg_count']:<6}  {format_size(s['size']):<10}  {C.DIM}{summary}{C.NC}")

    print(f"{C.DIM}{'-' * 90}{C.NC}")
    print(f"Total: {C.BOLD}{len(sessions)}{C.NC} sessions")

def cmd_rename(args: list[str]):
    if len(args) < 2:
        print(f"{C.RED}Usage: claude-session rename <session-id> <name>{C.NC}")
        return
    partial, name = args[0], " ".join(args[1:])
    sid = resolve_session_id(partial)
    if sid:
        set_session_name(sid, name)
        print(f"{C.GREEN}Renamed{C.NC} {C.BOLD}{sid[:8]}{C.NC} → {C.CYAN}{name}{C.NC}")

def cmd_names(args: list[str]):
    names = get_session_names()
    print(f"{C.BOLD}{C.CYAN}Named Sessions{C.NC}")
    print(f"{C.DIM}{'-' * 60}{C.NC}")
    if not names:
        print(f"{C.DIM}  No named sessions yet.{C.NC}")
        print(f"{C.DIM}  Use: claude-session rename <session-id> <name>{C.NC}")
        return
    for sid, name in names.items():
        # Find project
        project = ""
        for project_dir in PROJECTS_DIR.iterdir():
            if project_dir.is_dir() and (project_dir / f"{sid}.jsonl").exists():
                project = project_display_name(project_dir.name)
                break
        print(f"  {C.BOLD}{sid[:12]}{C.NC}  {C.CYAN}{name:<30}{C.NC}  {C.DIM}{project}{C.NC}")

def cmd_search(args: list[str]):
    if not args:
        print(f"{C.RED}Usage: claude-session search <keyword>{C.NC}")
        return
    keyword = args[0]
    names = get_session_names()
    print(f"{C.BOLD}{C.CYAN}Searching for: {C.YELLOW}{keyword}{C.NC}")
    print(f"{C.DIM}{'-' * 60}{C.NC}")

    count = 0
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            try:
                content = jsonl.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            matches = content.lower().count(keyword.lower())
            if matches > 0:
                info = get_session_info(jsonl)
                sid = info["sid"]
                cname = names.get(sid, "")
                date_str = iso_to_date(info["timestamp"]) if info["timestamp"] else "unknown"

                print(f"{C.GREEN}[{date_str}]{C.NC} {C.BOLD}{sid}{C.NC} ({C.CYAN}{matches} matches{C.NC})")
                if cname:
                    print(f"  {C.BOLD}Name:{C.NC} {C.CYAN}{cname}{C.NC}")
                print(f"  {C.DIM}Project: {project_display_name(project_dir.name)}{C.NC}")
                print(f"  {C.DIM}Summary: {info['first_msg'][:100]}{C.NC}")
                print()
                count += 1

    print(f"{C.DIM}{'-' * 60}{C.NC}")
    print(f"Found: {C.BOLD}{count}{C.NC} sessions containing '{keyword}'")

def cmd_info(args: list[str]):
    if not args:
        print(f"{C.RED}Usage: claude-session info <session-id>{C.NC}")
        return
    sid = resolve_session_id(args[0])
    if not sid:
        return

    names = get_session_names()
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl = project_dir / f"{sid}.jsonl"
        if not jsonl.exists():
            continue
        info = get_session_info(jsonl)
        cname = names.get(sid, "")
        has_history = (HISTORY_DIR / sid).is_dir()
        has_env = (SESSION_ENV_DIR / sid).is_dir()
        has_tasks = (TASKS_DIR / sid).is_dir()

        print(f"{C.BOLD}{C.CYAN}Session Details{C.NC}")
        print(f"{C.DIM}{'-' * 60}{C.NC}")
        print(f"{C.BOLD}ID:{C.NC}        {sid}")
        if cname:
            print(f"{C.BOLD}Name:{C.NC}      {C.CYAN}{cname}{C.NC}")
        print(f"{C.BOLD}Project:{C.NC}   {project_display_name(project_dir.name)}")
        print(f"{C.BOLD}Started:{C.NC}   {iso_to_date(info['timestamp'])}")
        print(f"{C.BOLD}Messages:{C.NC}  {info['msg_count']} user messages")
        print(f"{C.BOLD}Size:{C.NC}      {format_size(info['size'])}")
        print(f"{C.BOLD}Summary:{C.NC}   {info['first_msg']}")
        print()
        if has_history:
            print(f"{C.GREEN}+{C.NC} File history available")
        if has_env:
            print(f"{C.GREEN}+{C.NC} Session environment saved")
        if has_tasks:
            print(f"{C.GREEN}+{C.NC} Task data available")
        return

    print(f"{C.RED}Session not found: {sid}{C.NC}")

def cmd_clean(args: list[str]):
    if not args:
        print(f"{C.RED}Usage: claude-session clean <days> [project]{C.NC}")
        return
    days = int(args[0])
    filter_project = args[1] if len(args) > 1 else ""
    cutoff = time.time() - days * 86400

    to_delete = []
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        pname = project_dir.name
        if filter_project and filter_project not in pname:
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            info = get_session_info(jsonl)
            ts_epoch = 0
            try:
                ts_epoch = datetime.fromisoformat(info["timestamp"].replace("Z", "+00:00")).timestamp()
            except Exception:
                continue
            if ts_epoch < cutoff:
                to_delete.append((jsonl, info["sid"]))

    if not to_delete:
        print(f"{C.GREEN}No sessions older than {days} days found.{C.NC}")
        return

    print(f"{C.YELLOW}Found {len(to_delete)} sessions older than {days} days:{C.NC}")
    for _, sid in to_delete:
        print(f"  {C.DIM}{sid}{C.NC}")

    confirm = input(f"\n{C.YELLOW}Delete these sessions? [y/N]: {C.NC}")
    if confirm.lower() == "y":
        for jsonl, sid in to_delete:
            jsonl.unlink(missing_ok=True)
            for d in [HISTORY_DIR / sid, SESSION_ENV_DIR / sid, TASKS_DIR / sid, jsonl.parent / sid]:
                if d.exists():
                    import shutil
                    shutil.rmtree(d, ignore_errors=True)
        print(f"{C.GREEN}Deleted {len(to_delete)} sessions and associated data.{C.NC}")
    else:
        print(f"{C.DIM}Cancelled.{C.NC}")

def cmd_clean_all(args: list[str]):
    print(f"{C.RED}{C.BOLD}WARNING: This will delete ALL session transcripts!{C.NC}")
    confirm = input(f"{C.YELLOW}Type 'yes' to confirm: {C.NC}")
    if confirm != "yes":
        print(f"{C.DIM}Cancelled.{C.NC}")
        return

    import shutil
    count = 0
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            sid = jsonl.stem
            jsonl.unlink(missing_ok=True)
            for d in [HISTORY_DIR / sid, SESSION_ENV_DIR / sid, TASKS_DIR / sid, jsonl.parent / sid]:
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
            count += 1
    print(f"{C.GREEN}Deleted {count} sessions.{C.NC}")

def cmd_export(args: list[str]):
    if not args:
        print(f"{C.RED}Usage: claude-session export <session-id> [output]{C.NC}")
        return
    sid = resolve_session_id(args[0])
    if not sid:
        return
    output = Path(args[1]) if len(args) > 1 else Path.home() / f"session-{sid[:8]}.md"

    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        jsonl = project_dir / f"{sid}.jsonl"
        if not jsonl.exists():
            continue
        entries = parse_jsonl(jsonl)
        info = get_session_info(jsonl)
        pname = project_display_name(project_dir.name)

        lines = [
            "# Claude Code Session\n",
            f"- **ID:** {sid}",
            f"- **Project:** {pname}",
            f"- **Date:** {iso_to_date(info['timestamp'])}\n",
            "---\n",
        ]

        for e in entries:
            t = e.get("type", "")
            if t == "user":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    msg = " ".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in msg)
                if isinstance(msg, str) and msg.strip():
                    lines.append("## User\n")
                    lines.append(f"{msg.strip()}\n")
            elif t == "assistant":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    parts = []
                    for m in msg:
                        if isinstance(m, dict):
                            if m.get("type") == "text":
                                parts.append(m.get("text", ""))
                            elif m.get("type") == "tool_use":
                                parts.append(f"[Tool: {m.get('name', 'unknown')}]")
                        elif isinstance(m, str):
                            parts.append(m)
                    msg = " ".join(parts)
                if isinstance(msg, str) and msg.strip():
                    lines.append("## Assistant\n")
                    lines.append(f"{msg.strip()}\n")

        output.write_text("\n".join(lines), encoding="utf-8")
        print(f"{C.GREEN}Exported to: {output}{C.NC}")
        return

    print(f"{C.RED}Session not found: {sid}{C.NC}")

def cmd_stats(args: list[str]):
    print(f"{C.BOLD}{C.CYAN}Claude Code Session Statistics{C.NC}")
    print(f"{C.DIM}{'-' * 70}{C.NC}")

    total_sessions = 0
    total_size = 0
    total_msgs = 0
    oldest = ""
    newest = ""

    print(f"\n{C.BOLD}Per-Project Breakdown:{C.NC}\n")

    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue
        pname = project_display_name(project_dir.name)
        p_count = 0
        p_size = 0
        p_msgs = 0

        for jsonl in project_dir.glob("*.jsonl"):
            info = get_session_info(jsonl)
            p_count += 1
            p_size += info["size"]
            p_msgs += info["msg_count"]
            ts = info["timestamp"]
            if ts:
                if not oldest or ts < oldest:
                    oldest = ts
                if not newest or ts > newest:
                    newest = ts

        if p_count > 0:
            print(f"  {C.BOLD}{pname:<50}{C.NC}  {p_count:>3} sessions  {format_size(p_size):>8}  {p_msgs:>4} msgs")
            total_sessions += p_count
            total_size += p_size
            total_msgs += p_msgs

    print(f"{C.DIM}{'-' * 70}{C.NC}")
    print(f"\n{C.BOLD}Summary:{C.NC}")
    print(f"  Total sessions:    {C.BOLD}{total_sessions}{C.NC}")
    print(f"  Total messages:    {C.BOLD}{total_msgs}{C.NC}")
    print(f"  Total size:        {C.BOLD}{format_size(total_size)}{C.NC}")
    if oldest:
        print(f"  Oldest session:    {C.DIM}{iso_to_date(oldest)}{C.NC}")
    if newest:
        print(f"  Newest session:    {C.DIM}{iso_to_date(newest)}{C.NC}")
    print()

def cmd_help(args: list[str]):
    print(f"""{C.BOLD}{C.CYAN}Claude Code Session Manager{C.NC} {C.DIM}v2.0{C.NC}

{C.BOLD}Usage:{C.NC} claude-session <command> [options]

{C.BOLD}Commands:{C.NC}
  {C.GREEN}list{C.NC}    [project] [days]   List sessions (filter by project name or age)
  {C.GREEN}rename{C.NC}  <id> <name>        Give a session a custom name (supports partial ID)
  {C.GREEN}names{C.NC}                      List all named sessions
  {C.GREEN}search{C.NC}  <keyword>          Search session content
  {C.GREEN}info{C.NC}    <session-id>       Show session details
  {C.GREEN}clean{C.NC}   <days> [project]   Delete sessions older than N days
  {C.GREEN}clean-all{C.NC}                  Delete ALL sessions (with confirmation)
  {C.GREEN}export{C.NC}  <session-id> [out] Export session as markdown
  {C.GREEN}stats{C.NC}                      Show session statistics

{C.BOLD}Examples:{C.NC}
  claude-session list                    # List all sessions
  claude-session rename abc123 简历优化    # Name a session
  claude-session names                   # Show all named sessions
  claude-session search 'authentication' # Search for keyword
  claude-session clean 14                # Clean sessions older than 14 days
  claude-session export abc123           # Export session to markdown
""")

def cmd_interactive(args: list[str]):
    """Interactive menu mode for double-click usage."""
    while True:
        print(f"\n{C.BOLD}{C.CYAN}=== Claude Code Session Manager ==={C.NC}\n")
        print(f"  {C.GREEN}1{C.NC}  List sessions")
        print(f"  {C.GREEN}2{C.NC}  Search sessions")
        print(f"  {C.GREEN}3{C.NC}  View session info")
        print(f"  {C.GREEN}4{C.NC}  Rename session")
        print(f"  {C.GREEN}5{C.NC}  Show named sessions")
        print(f"  {C.GREEN}6{C.NC}  Clean old sessions")
        print(f"  {C.GREEN}7{C.NC}  Export session")
        print(f"  {C.GREEN}8{C.NC}  Statistics")
        print(f"  {C.GREEN}0{C.NC}  Exit\n")

        choice = input(f"{C.BOLD}Select [0-8]: {C.NC}").strip()

        if choice == "0":
            print(f"{C.DIM}Bye!{C.NC}")
            break
        elif choice == "1":
            cmd_list([])
        elif choice == "2":
            kw = input("Keyword: ").strip()
            if kw:
                cmd_search([kw])
        elif choice == "3":
            sid = input("Session ID (or prefix): ").strip()
            if sid:
                cmd_info([sid])
        elif choice == "4":
            sid = input("Session ID (or prefix): ").strip()
            name = input("New name: ").strip()
            if sid and name:
                cmd_rename([sid, name])
        elif choice == "5":
            cmd_names([])
        elif choice == "6":
            days = input("Delete sessions older than N days: ").strip()
            if days.isdigit():
                cmd_clean([days])
        elif choice == "7":
            sid = input("Session ID (or prefix): ").strip()
            if sid:
                cmd_export([sid])
        elif choice == "8":
            cmd_stats([])
        else:
            print(f"{C.RED}Invalid choice{C.NC}")

        print()  # blank line between operations

# --- Main ------------------------------------------------------------------

COMMANDS = {
    "list": cmd_list, "ls": cmd_list,
    "rename": cmd_rename, "rn": cmd_rename,
    "names": cmd_names,
    "search": cmd_search, "grep": cmd_search,
    "info": cmd_info, "show": cmd_info,
    "clean": cmd_clean,
    "clean-all": cmd_clean_all,
    "export": cmd_export,
    "stats": cmd_stats,
    "help": cmd_help, "--help": cmd_help, "-h": cmd_help,
    "interactive": cmd_interactive,
}

def main():
    # Disable colors if not a terminal
    if not sys.stdout.isatty():
        C.disable()

    args = sys.argv[1:]
    cmd = args[0] if args else "interactive"
    rest = args[1:] if len(args) > 1 else []

    if cmd in COMMANDS:
        COMMANDS[cmd](rest)
    else:
        print(f"{C.RED}Unknown command: {cmd}{C.NC}")
        print("Run 'claude-session help' for usage.")
        sys.exit(1)

if __name__ == "__main__":
    main()
