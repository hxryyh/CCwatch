#!/usr/bin/env python3
"""Claude Code Manager - Desktop GUI v1.1 (Sessions + MCP + Skills)"""

import os
import sys
import json
import time
import shutil
from pathlib import Path
from datetime import datetime

import customtkinter as ctk

# --- Paths ------------------------------------------------------------------

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
HISTORY_DIR = CLAUDE_DIR / "file-history"
SESSION_ENV_DIR = CLAUDE_DIR / "session-env"
TASKS_DIR = CLAUDE_DIR / "tasks"
NAMES_FILE = CLAUDE_DIR / "session-names.txt"
SKILLS_DIR = CLAUDE_DIR / "skills"
MCP_CONFIG = Path.home() / ".mcp.json"
SETTINGS_FILE = CLAUDE_DIR / "settings.json"

# --- Colors -----------------------------------------------------------------

COLORS = {
    "bg": "#1e1e2e",
    "surface": "#2a2a3d",
    "surface2": "#33334d",
    "border": "#3d3d5c",
    "accent": "#e8906a",
    "accent_hover": "#f0a080",
    "text": "#e0e0f0",
    "text_dim": "#8888aa",
    "green": "#7ec699",
    "red": "#e86a6a",
    "yellow": "#e8c86a",
    "blue": "#6a9ee8",
}

FONT = "Microsoft YaHei UI"
MONO = "Cascadia Code"

# --- Data: Sessions ---------------------------------------------------------

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


def format_size(size: int) -> str:
    if size > 1048576:
        return f"{size / 1048576:.1f} MB"
    elif size > 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def iso_to_date(ts: str) -> str:
    return ts.replace("T", " ").split(".")[0]


def project_display_name(dirname: str) -> str:
    return dirname.replace("--", "/").lstrip("/")


def parse_jsonl(filepath: Path) -> list:
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
        "project": filepath.parent.name,
        "timestamp": "",
        "msg_count": 0,
        "first_msg": "（无内容）",
        "size": filepath.stat().st_size,
        "filepath": str(filepath),
    }
    for e in entries:
        ts = e.get("timestamp", "")
        if ts and not info["timestamp"]:
            info["timestamp"] = ts
        if e.get("type") == "user":
            info["msg_count"] += 1
            if info["first_msg"] == "（无内容）":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    msg = " ".join(
                        str(m.get("text", "")) if isinstance(m, dict) else str(m)
                        for m in msg
                    )
                if isinstance(msg, str) and msg.strip():
                    info["first_msg"] = msg.strip().replace("\n", " ")[:120]
    return info


def load_all_sessions() -> list:
    sessions = []
    names = get_session_names()
    if not PROJECTS_DIR.exists():
        return sessions
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl in project_dir.glob("*.jsonl"):
            info = get_session_info(jsonl)
            if info["timestamp"]:
                info["name"] = names.get(info["sid"], "")
                try:
                    info["ts_epoch"] = datetime.fromisoformat(
                        info["timestamp"].replace("Z", "+00:00")
                    ).timestamp()
                except Exception:
                    info["ts_epoch"] = 0
                info["date_str"] = iso_to_date(info["timestamp"])
                sessions.append(info)
    sessions.sort(key=lambda s: s["ts_epoch"], reverse=True)
    return sessions


# --- Data: MCP Servers ------------------------------------------------------

# Known MCP server descriptions (Chinese)
MCP_DESCRIPTIONS = {
    "sequential-thinking": "分步推理工具，引导模型进行结构化思考，支持回溯修正和分支探索",
    "context7": "自动获取第三方库的最新文档，提供上下文相关的代码示例",
    "playwright": "浏览器自动化工具，支持网页操作、截图、表单填写等",
    "github": "GitHub API 集成，管理仓库、Issue、PR 等",
    "gitlab": "GitLab API 集成，管理仓库、Issue、MR 等",
    "linear": "Linear 项目管理工具集成，管理 Issue 和项目",
    "asana": "Asana 任务管理集成",
    "discord": "Discord 消息和频道管理",
    "telegram": "Telegram 消息和频道管理",
    "firebase": "Firebase 服务集成，管理数据库、认证等",
    "terraform": "Terraform 基础设施即代码工具",
    "serena": "代码理解和导航工具",
    "greptile": "代码库搜索和理解工具",
    "laravel-boost": "Laravel 框架增强工具",
    "imessage": "iMessage 消息管理",
}


def load_mcp_servers() -> list:
    """Load MCP servers from .mcp.json and settings.json"""
    servers = []

    def add_server(name, spec, source):
        desc = MCP_DESCRIPTIONS.get(name, "")
        args = spec.get("args", [])
        if not desc and args:
            for a in args:
                if "@" in str(a) and "/" in str(a):
                    desc = f"NPM 包: {a}"
                    break
        servers.append({
            "name": name,
            "source": source,
            "command": spec.get("command", ""),
            "args": args,
            "url": spec.get("url", ""),
            "type": "stdio" if spec.get("command") else "sse",
            "description": desc,
        })

    if MCP_CONFIG.exists():
        try:
            cfg = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
            for name, spec in cfg.get("mcpServers", {}).items():
                add_server(name, spec, "~/.mcp.json")
        except Exception:
            pass

    if SETTINGS_FILE.exists():
        try:
            cfg = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            for name, spec in cfg.get("mcpServers", {}).items():
                add_server(name, spec, "~/.claude/settings.json")
        except Exception:
            pass

    claude_json = CLAUDE_DIR.parent / ".claude.json"
    if claude_json.exists():
        try:
            cfg = json.loads(claude_json.read_text(encoding="utf-8"))
            for proj_path, proj_cfg in cfg.get("projects", {}).items():
                for name, spec in proj_cfg.get("mcpServers", {}).items():
                    add_server(name, spec, f"项目:{Path(proj_path).name}")
        except Exception:
            pass

    return servers


# --- Data: Skills -----------------------------------------------------------

# Known skill descriptions (Chinese)
SKILL_DESCRIPTIONS = {
    "brainstorming": "头脑风暴技能，帮助发散思维和创意生成",
    "browser-act": "浏览器操作技能，通过 Playwright 执行网页交互",
    "dispatching-parallel-agents": "并行代理调度，同时执行多个子任务",
    "executing-plans": "计划执行技能，按步骤实施开发计划",
    "finishing-a-development-branch": "开发分支收尾，完成代码审查和合并",
    "receiving-code-review": "接收代码审查，理解和处理审查反馈",
    "requesting-code-review": "请求代码审查，发起 PR 审查流程",
    "subagent-driven-development": "子代理驱动开发，利用代理完成复杂任务",
    "systematic-debugging": "系统化调试技能，结构化排查问题",
    "test-driven-development": "测试驱动开发，先写测试再实现功能",
    "using-git-worktrees": "Git Worktree 使用，隔离开发环境",
    "using-superpowers": "超级能力技能，解锁高级功能",
    "verification-before-completion": "完成前验证，确保代码质量",
    "writing-plans": "计划编写技能，制定开发计划",
    "writing-skills": "技能编写技能，创建自定义技能",
}


def load_skills() -> list:
    """Load skills from ~/.claude/skills/"""
    skills = []
    if not SKILLS_DIR.exists():
        return skills

    for skill_dir in sorted(SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill = {
            "name": skill_dir.name,
            "path": str(skill_dir),
            "description": SKILL_DESCRIPTIONS.get(skill_dir.name, ""),
            "files": [],
            "source": "~/.claude/skills/",
        }

        for f in skill_dir.iterdir():
            skill["files"].append(f.name)
            # Try to get description from files if not in known list
            if not skill["description"] and f.suffix in (".md", ".txt"):
                try:
                    content = f.read_text(encoding="utf-8")[:300]
                    first_line = content.split("\n")[0].strip("# ").strip()
                    if first_line and len(first_line) > 5:
                        skill["description"] = first_line[:80]
                except Exception:
                    pass

        all_files = list(skill_dir.rglob("*"))
        skill["file_count"] = len([f for f in all_files if f.is_file()])
        skill["total_size"] = sum(f.stat().st_size for f in all_files if f.is_file())

        skills.append(skill)

    return skills


# --- GUI: Sidebar Navigation -----------------------------------------------

class SidebarButton(ctk.CTkButton):
    def __init__(self, master, text, icon_text, **kwargs):
        super().__init__(
            master,
            text=f"  {icon_text}  {text}",
            anchor="w",
            height=40,
            corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=13),
            fg_color="transparent",
            hover_color=COLORS["surface2"],
            text_color=COLORS["text_dim"],
            **kwargs,
        )

    def set_active(self, active: bool):
        if active:
            self.configure(fg_color=COLORS["surface2"], text_color=COLORS["accent"])
        else:
            self.configure(fg_color="transparent", text_color=COLORS["text_dim"])


# --- GUI: Sessions Panel ---------------------------------------------------

class SessionsPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")

        self.sessions = []
        self.selected_session = None
        self.session_rows = []

        self._build_ui()
        self._load_sessions()

    def _build_ui(self):
        # Search bar
        search_frame = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        search_frame.pack(fill="x", padx=0, pady=(0, 10))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._filter_sessions())

        ctk.CTkEntry(
            search_frame,
            placeholder_text="  搜索会话 ID、名称或内容...",
            textvariable=self.search_var,
            font=ctk.CTkFont(family=FONT, size=13),
            height=38, fg_color=COLORS["surface"],
            border_color=COLORS["border"], corner_radius=10,
        ).pack(fill="x")

        # Main content
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # Left: list
        left = ctk.CTkFrame(main, fg_color=COLORS["surface"], corner_radius=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        header = ctk.CTkFrame(left, fg_color=COLORS["surface2"], height=32)
        header.pack(fill="x", padx=1, pady=(1, 0))
        header.pack_propagate(False)
        for text, w in [("ID", 70), ("名称", 115), ("日期", 105), ("消息", 45)]:
            ctk.CTkLabel(header, text=text, width=w, anchor="w",
                         font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                         text_color=COLORS["text_dim"]).pack(side="left", padx=(10, 0))

        self.list_frame = ctk.CTkScrollableFrame(
            left, fg_color=COLORS["surface"],
            scrollbar_button_color=COLORS["border"],
        )
        self.list_frame.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        # Right: detail
        right = ctk.CTkFrame(main, fg_color=COLORS["surface"], corner_radius=12, width=340)
        right.pack(side="right", fill="both", padx=(8, 0))
        right.pack_propagate(False)

        self.detail_title = ctk.CTkLabel(
            right, text="选择一个会话",
            font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
            text_color=COLORS["text"], anchor="w",
        )
        self.detail_title.pack(fill="x", padx=18, pady=(18, 8))

        ctk.CTkFrame(right, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=12, pady=5)

        # Detail fields
        self.detail_frame = ctk.CTkFrame(right, fg_color="transparent")
        self.detail_frame.pack(fill="x", padx=12, pady=5)

        self.detail_labels = {}
        for i, (key, label) in enumerate([
            ("ID", "ID"), ("Project", "项目"), ("Started", "时间"),
            ("Messages", "消息"), ("Size", "大小"), ("Summary", "摘要"),
        ]):
            ctk.CTkLabel(self.detail_frame, text=f"{label}:", anchor="w",
                         font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                         text_color=COLORS["text_dim"], width=55
                         ).grid(row=i, column=0, sticky="nw", padx=(5, 8), pady=(6, 2))
            lbl = ctk.CTkLabel(self.detail_frame, text="", anchor="w",
                               font=ctk.CTkFont(family=FONT, size=13),
                               text_color=COLORS["text"], wraplength=240)
            lbl.grid(row=i, column=1, sticky="w", pady=(6, 2))
            self.detail_labels[key] = lbl

        # Rename section
        ctk.CTkFrame(right, height=1, fg_color=COLORS["border"]).pack(fill="x", padx=12, pady=(10, 5))

        rename_sec = ctk.CTkFrame(right, fg_color="transparent")
        rename_sec.pack(fill="x", padx=12, pady=5)

        ctk.CTkLabel(rename_sec, text="重命名", anchor="w",
                     font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                     text_color=COLORS["text_dim"]).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(rename_sec, fg_color="transparent")
        row.pack(fill="x")

        self.name_entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(family=FONT, size=12),
            fg_color=COLORS["surface2"], border_color=COLORS["border"],
            corner_radius=8, placeholder_text="输入新名称...",
        )
        self.name_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            row, text="确认", width=55, height=30,
            font=ctk.CTkFont(family=FONT, size=13), corner_radius=8,
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._rename_session,
        ).pack(side="right")

        rename_sec.pack_forget()
        self.rename_section = rename_sec

        # Action buttons
        btn_frame = ctk.CTkFrame(right, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(10, 18))

        self.export_btn = ctk.CTkButton(
            btn_frame, text="导出", width=75, height=30, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=13),
            fg_color=COLORS["surface2"], hover_color=COLORS["border"],
            command=self._export_session,
        )
        self.export_btn.pack(side="left", padx=(0, 6))

        self.delete_btn = ctk.CTkButton(
            btn_frame, text="删除", width=75, height=30, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=13),
            fg_color=COLORS["red"], hover_color="#c05050",
            command=self._delete_session,
        )
        self.delete_btn.pack(side="left")

        self.clean_btn = ctk.CTkButton(
            btn_frame, text="清理旧会话", width=95, height=30, corner_radius=8,
            font=ctk.CTkFont(family=FONT, size=13),
            fg_color=COLORS["yellow"], hover_color="#c0a850", text_color="#1e1e2e",
            command=self._clean_old,
        )
        self.clean_btn.pack(side="right")

        for btn in [self.export_btn, self.delete_btn]:
            btn.configure(state="disabled")

    def _load_sessions(self):
        self.sessions = load_all_sessions()
        self._render_list(self.sessions)

    def _filter_sessions(self):
        q = self.search_var.get().strip().lower()
        if not q:
            self._render_list(self.sessions)
            return
        self._render_list([
            s for s in self.sessions
            if q in s["sid"].lower() or q in s.get("name", "").lower()
            or q in s["first_msg"].lower() or q in s["project"].lower()
        ])

    def _render_list(self, sessions):
        for r in self.session_rows:
            r.destroy()
        self.session_rows = []
        for s in sessions:
            row = ctk.CTkFrame(self.list_frame, height=34, fg_color="transparent", corner_radius=6)
            row.pack(fill="x", padx=3, pady=1)
            row.pack_propagate(False)
            name_display = s.get("name", "") or "—"
            ctk.CTkLabel(row, text=s["sid"][:8], width=65, anchor="w",
                         font=ctk.CTkFont(family=MONO, size=13),
                         text_color=COLORS["text_dim"]).pack(side="left", padx=(8, 0))
            ctk.CTkLabel(row, text=name_display[:15], width=110, anchor="w",
                         font=ctk.CTkFont(family=FONT, size=13),
                         text_color=COLORS["accent"] if s.get("name") else COLORS["text_dim"]).pack(side="left")
            ctk.CTkLabel(row, text=s["date_str"][:10], width=100, anchor="w",
                         font=ctk.CTkFont(family=FONT, size=13),
                         text_color=COLORS["text"]).pack(side="left")
            ctk.CTkLabel(row, text=str(s["msg_count"]), width=40, anchor="e",
                         font=ctk.CTkFont(family=FONT, size=13),
                         text_color=COLORS["green"] if s["msg_count"] > 10 else COLORS["text_dim"]).pack(side="left", padx=(0, 8))

            sid = s["sid"]
            def on_enter(e, r=row): r.configure(fg_color=COLORS["surface2"])
            def on_leave(e, r=row, s=s):
                if not self.selected_session or self.selected_session["sid"] != s["sid"]:
                    r.configure(fg_color="transparent")
            row.bind("<Enter>", on_enter)
            row.bind("<Leave>", on_leave)
            row.bind("<Button-1>", lambda e, sid=sid: self._select_session(sid))
            for ch in row.winfo_children():
                ch.bind("<Enter>", on_enter)
                ch.bind("<Leave>", on_leave)
                ch.bind("<Button-1>", lambda e, sid=sid: self._select_session(sid))
            self.session_rows.append(row)

    def _select_session(self, sid):
        if self.selected_session:
            for i, s in enumerate(self.sessions):
                if s["sid"] == self.selected_session["sid"] and i < len(self.session_rows):
                    self.session_rows[i].configure(fg_color="transparent")
        session = next((s for s in self.sessions if s["sid"] == sid), None)
        if not session:
            return
        self.selected_session = session
        idx = next((i for i, s in enumerate(self.sessions) if s["sid"] == sid), -1)
        if 0 <= idx < len(self.session_rows):
            self.session_rows[idx].configure(fg_color=COLORS["surface2"])

        self.detail_title.configure(text=f"会话 {sid[:8]}")
        self.detail_labels["ID"].configure(text=sid)
        self.detail_labels["Project"].configure(text=project_display_name(session["project"]))
        self.detail_labels["Started"].configure(text=session["date_str"])
        self.detail_labels["Messages"].configure(text=f"{session['msg_count']} 条消息")
        self.detail_labels["Size"].configure(text=format_size(session["size"]))
        self.detail_labels["Summary"].configure(text=session["first_msg"][:80])

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, session.get("name", ""))
        self.rename_section.pack(fill="x", padx=12, pady=5)
        for btn in [self.export_btn, self.delete_btn]:
            btn.configure(state="normal")

    def _rename_session(self):
        if not self.selected_session:
            return
        new_name = self.name_entry.get().strip()
        if not new_name:
            return
        set_session_name(self.selected_session["sid"], new_name)
        self.selected_session["name"] = new_name
        self._load_sessions()
        self._select_session(self.selected_session["sid"])

    def _export_session(self):
        if not self.selected_session:
            return
        sid = self.selected_session["sid"]
        filepath = Path(self.selected_session["filepath"])
        output = Path.home() / f"session-{sid[:8]}.md"
        entries = parse_jsonl(filepath)
        lines = ["# Claude Code 会话记录\n", f"- **ID:** {sid}",
                 f"- **项目:** {project_display_name(self.selected_session['project'])}",
                 f"- **时间:** {self.selected_session['date_str']}\n", "---\n"]
        for e in entries:
            t = e.get("type", "")
            if t == "user":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    msg = " ".join(str(m.get("text", "")) if isinstance(m, dict) else str(m) for m in msg)
                if isinstance(msg, str) and msg.strip():
                    lines += ["## 用户\n", f"{msg.strip()}\n"]
            elif t == "assistant":
                msg = e.get("message", {}).get("content", "")
                if isinstance(msg, list):
                    parts = []
                    for m in msg:
                        if isinstance(m, dict):
                            parts.append(m.get("text", "") if m.get("type") == "text" else f"[{m.get('name', '?')}]")
                        elif isinstance(m, str):
                            parts.append(m)
                    msg = " ".join(parts)
                if isinstance(msg, str) and msg.strip():
                    lines += ["## 助手\n", f"{msg.strip()}\n"]
        output.write_text("\n".join(lines), encoding="utf-8")

    def _delete_session(self):
        if not self.selected_session:
            return
        sid = self.selected_session["sid"]
        dlg = ctk.CTkToplevel(self)
        dlg.title("确认删除")
        dlg.geometry("320x140")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(fg_color=COLORS["bg"])
        ctk.CTkLabel(dlg, text=f"确定删除会话 {sid[:8]}？",
                     font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                     text_color=COLORS["text"]).pack(pady=(20, 5))
        ctk.CTkLabel(dlg, text="此操作不可撤销", font=ctk.CTkFont(family=FONT, size=13),
                     text_color=COLORS["text_dim"]).pack()
        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(pady=15)

        def confirm():
            fp = Path(self.selected_session["filepath"])
            sl = self.selected_session["sid"]
            fp.unlink(missing_ok=True)
            for d in [HISTORY_DIR / sl, SESSION_ENV_DIR / sl, TASKS_DIR / sl, fp.parent / sl]:
                if d.exists():
                    shutil.rmtree(d, ignore_errors=True)
            names = get_session_names()
            if sl in names:
                del names[sl]
                lines = [f"{k}|{v}" for k, v in names.items()]
                if lines:
                    NAMES_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
                elif NAMES_FILE.exists():
                    NAMES_FILE.unlink()
            self.selected_session = None
            self.detail_title.configure(text="选择一个会话")
            for lbl in self.detail_labels.values():
                lbl.configure(text="")
            self.rename_section.pack_forget()
            for btn in [self.export_btn, self.delete_btn]:
                btn.configure(state="disabled")
            self._load_sessions()
            dlg.destroy()

        ctk.CTkButton(bf, text="删除", fg_color=COLORS["red"], hover_color="#c05050",
                       command=confirm, width=75, corner_radius=8).pack(side="left", padx=8)
        ctk.CTkButton(bf, text="取消", command=dlg.destroy, width=75, corner_radius=8,
                       fg_color=COLORS["surface2"], hover_color=COLORS["border"]).pack(side="left", padx=8)

    def _clean_old(self):
        dlg = ctk.CTkToplevel(self)
        dlg.title("清理旧会话")
        dlg.geometry("330x180")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        dlg.configure(fg_color=COLORS["bg"])
        ctk.CTkLabel(dlg, text="删除超过以下天数的会话:",
                     font=ctk.CTkFont(family=FONT, size=13),
                     text_color=COLORS["text"]).pack(pady=(20, 8))
        de = ctk.CTkEntry(dlg, width=80, justify="center",
                          font=ctk.CTkFont(family=FONT, size=14),
                          fg_color=COLORS["surface"], border_color=COLORS["border"], corner_radius=8)
        de.insert(0, "14")
        de.pack(pady=5)
        ctk.CTkLabel(dlg, text="天", font=ctk.CTkFont(family=FONT, size=13),
                     text_color=COLORS["text_dim"]).pack()
        bf = ctk.CTkFrame(dlg, fg_color="transparent")
        bf.pack(pady=15)

        def confirm():
            days = int(de.get() or "14")
            cutoff = time.time() - days * 86400
            count = 0
            for s in self.sessions:
                if s["ts_epoch"] < cutoff:
                    fp = Path(s["filepath"])
                    fp.unlink(missing_ok=True)
                    for d in [HISTORY_DIR / s["sid"], SESSION_ENV_DIR / s["sid"],
                              TASKS_DIR / s["sid"], fp.parent / s["sid"]]:
                        if d.exists():
                            shutil.rmtree(d, ignore_errors=True)
                    count += 1
            self._load_sessions()
            dlg.destroy()

        ctk.CTkButton(bf, text="清理", command=confirm, width=75, corner_radius=8,
                       fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"]).pack(side="left", padx=8)
        ctk.CTkButton(bf, text="取消", command=dlg.destroy, width=75, corner_radius=8,
                       fg_color=COLORS["surface2"], hover_color=COLORS["border"]).pack(side="left", padx=8)


# --- GUI: MCP Panel --------------------------------------------------------

class McpPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build_ui()
        self._load()

    def _build_ui(self):
        ctk.CTkLabel(self, text="MCP 服务器", anchor="w",
                     font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
                     text_color=COLORS["text"]).pack(fill="x", padx=5, pady=(0, 10))

        self.card_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
        )
        self.card_frame.pack(fill="both", expand=True)

    def _load(self):
        servers = load_mcp_servers()
        for w in self.card_frame.winfo_children():
            w.destroy()

        if not servers:
            ctk.CTkLabel(self.card_frame, text="未配置 MCP 服务器",
                         font=ctk.CTkFont(family=FONT, size=13),
                         text_color=COLORS["text_dim"]).pack(pady=30)
            return

        for srv in servers:
            card = ctk.CTkFrame(self.card_frame, fg_color=COLORS["surface"], corner_radius=10)
            card.pack(fill="x", padx=3, pady=4)

            # Header row
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=15, pady=(12, 2))

            ctk.CTkLabel(hdr, text=srv["name"],
                         font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                         text_color=COLORS["accent"]).pack(side="left")

            ctk.CTkLabel(hdr, text=srv["type"].upper(),
                         font=ctk.CTkFont(family=MONO, size=11),
                         text_color=COLORS["text_dim"], fg_color=COLORS["surface2"],
                         corner_radius=4, padx=6, pady=2).pack(side="right")

            # Description
            if srv.get("description"):
                ctk.CTkLabel(card, text=srv["description"], anchor="w",
                             font=ctk.CTkFont(family=FONT, size=13),
                             text_color=COLORS["text"], wraplength=450).pack(
                    fill="x", padx=15, pady=(0, 4))

            # Details
            details = ctk.CTkFrame(card, fg_color="transparent")
            details.pack(fill="x", padx=15, pady=(0, 12))

            if srv["command"]:
                cmd_text = f"{srv['command']} {' '.join(srv['args'][:3])}"
                if len(srv['args']) > 3:
                    cmd_text += " ..."
                ctk.CTkLabel(details, text=f"命令: {cmd_text}", anchor="w",
                             font=ctk.CTkFont(family=MONO, size=12),
                             text_color=COLORS["text_dim"], wraplength=450).pack(anchor="w")
            if srv["url"]:
                ctk.CTkLabel(details, text=f"URL: {srv['url']}", anchor="w",
                             font=ctk.CTkFont(family=MONO, size=12),
                             text_color=COLORS["text_dim"]).pack(anchor="w")

            ctk.CTkLabel(details, text=f"配置来源: {srv['source']}", anchor="w",
                         font=ctk.CTkFont(family=FONT, size=12),
                         text_color=COLORS["blue"]).pack(anchor="w", pady=(4, 0))


# --- GUI: Skills Panel -----------------------------------------------------

class SkillsPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color="transparent")
        self._build_ui()
        self._load()

    def _build_ui(self):
        ctk.CTkLabel(self, text="Skills 技能", anchor="w",
                     font=ctk.CTkFont(family=FONT, size=15, weight="bold"),
                     text_color=COLORS["text"]).pack(fill="x", padx=5, pady=(0, 10))

        self.card_frame = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
        )
        self.card_frame.pack(fill="both", expand=True)

    def _load(self):
        skills = load_skills()
        for w in self.card_frame.winfo_children():
            w.destroy()

        if not skills:
            ctk.CTkLabel(self.card_frame, text="未安装任何 Skill",
                         font=ctk.CTkFont(family=FONT, size=13),
                         text_color=COLORS["text_dim"]).pack(pady=30)
            return

        for sk in skills:
            card = ctk.CTkFrame(self.card_frame, fg_color=COLORS["surface"], corner_radius=10)
            card.pack(fill="x", padx=3, pady=4)

            # Header
            hdr = ctk.CTkFrame(card, fg_color="transparent")
            hdr.pack(fill="x", padx=15, pady=(12, 2))

            ctk.CTkLabel(hdr, text=sk["name"].replace("-", " ").title(),
                         font=ctk.CTkFont(family=FONT, size=14, weight="bold"),
                         text_color=COLORS["green"]).pack(side="left")

            ctk.CTkLabel(hdr, text=f"{sk['file_count']} 文件  {format_size(sk['total_size'])}",
                         font=ctk.CTkFont(family=FONT, size=12),
                         text_color=COLORS["text_dim"]).pack(side="right")

            # Description
            if sk["description"]:
                ctk.CTkLabel(card, text=sk["description"][:80], anchor="w",
                             font=ctk.CTkFont(family=FONT, size=13),
                             text_color=COLORS["text"], wraplength=450).pack(
                    fill="x", padx=15, pady=(0, 2))

            # Source and files
            details = ctk.CTkFrame(card, fg_color="transparent")
            details.pack(fill="x", padx=15, pady=(0, 12))

            ctk.CTkLabel(details, text=f"来源: {sk.get('source', '~/.claude/skills/')}", anchor="w",
                         font=ctk.CTkFont(family=FONT, size=12),
                         text_color=COLORS["blue"]).pack(anchor="w")

            files_text = ", ".join(sk["files"][:6])
            if len(sk["files"]) > 6:
                files_text += f" ... +{len(sk['files']) - 6}"
            ctk.CTkLabel(details, text=files_text, anchor="w",
                         font=ctk.CTkFont(family=MONO, size=12),
                         text_color=COLORS["text_dim"], wraplength=450).pack(anchor="w", pady=(4, 0))


# --- GUI: Stats Dialog -----------------------------------------------------

def show_stats_dialog(parent, sessions):
    dlg = ctk.CTkToplevel(parent)
    dlg.title("统计概览")
    dlg.geometry("520x380")
    dlg.transient(parent)
    dlg.grab_set()
    dlg.configure(fg_color=COLORS["bg"])

    txt = ctk.CTkTextbox(dlg, font=ctk.CTkFont(family=MONO, size=12),
                         fg_color=COLORS["surface"], text_color=COLORS["text"],
                         corner_radius=10, border_color=COLORS["border"], border_width=1)
    txt.pack(fill="both", expand=True, padx=15, pady=15)

    projects = {}
    total_size = total_msgs = 0
    for s in sessions:
        p = project_display_name(s["project"])
        if p not in projects:
            projects[p] = {"count": 0, "size": 0, "msgs": 0}
        projects[p]["count"] += 1
        projects[p]["size"] += s["size"]
        projects[p]["msgs"] += s["msg_count"]
        total_size += s["size"]
        total_msgs += s["msg_count"]

    lines = ["  统计概览", "  " + "=" * 48, ""]
    for p, d in sorted(projects.items()):
        lines.append(f"  {p:<42} {d['count']:>3} 会话  {format_size(d['size']):>8}  {d['msgs']:>4} 消息")
    lines += ["", "  " + "-" * 48,
              f"  合计: {len(sessions)} 个会话  |  {total_msgs} 条消息  |  {format_size(total_size)}"]
    if sessions:
        lines += [f"  最旧: {sessions[-1]['date_str']}", f"  最新: {sessions[0]['date_str']}"]

    txt.insert("1.0", "\n".join(lines))
    txt.configure(state="disabled")


# --- GUI: Main App ---------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Claude Code Manager")
        self.geometry("1080x700")
        self.minsize(900, 550)
        self.configure(fg_color=COLORS["bg"])

        ico = CLAUDE_DIR / "claude-session.ico"
        if ico.exists():
            try:
                self.iconbitmap(str(ico))
            except Exception:
                pass

        self.current_tab = None
        self.panels = {}

        self._build_ui()
        self._switch_tab("sessions")

    def _build_ui(self):
        # Top bar
        top = ctk.CTkFrame(self, height=50, fg_color=COLORS["surface"], corner_radius=0)
        top.pack(fill="x")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="Claude", font=ctk.CTkFont(family=FONT, size=20, weight="bold"),
                     text_color=COLORS["accent"]).pack(side="left", padx=(20, 0))
        ctk.CTkLabel(top, text=" Code Manager", font=ctk.CTkFont(family=FONT, size=20),
                     text_color=COLORS["text"]).pack(side="left")

        ctk.CTkButton(top, text="统计", width=70, height=30, corner_radius=8,
                      font=ctk.CTkFont(family=FONT, size=12),
                      fg_color=COLORS["surface2"], hover_color=COLORS["border"],
                      command=lambda: show_stats_dialog(self, self.panels["sessions"].sessions)
                      ).pack(side="right", padx=20, pady=10)

        # Main area with sidebar
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=15, pady=(10, 15))

        # Sidebar
        sidebar = ctk.CTkFrame(body, fg_color=COLORS["surface"], corner_radius=12, width=160)
        sidebar.pack(side="left", fill="y", padx=(0, 10))
        sidebar.pack_propagate(False)

        ctk.CTkLabel(sidebar, text="导航", font=ctk.CTkFont(family=FONT, size=13, weight="bold"),
                     text_color=COLORS["text_dim"]).pack(anchor="w", padx=15, pady=(15, 8))

        self.nav_buttons = {}
        tabs = [("sessions", "会话", "📋"), ("mcp", "MCP", "🔌"), ("skills", "Skills", "⚡")]
        for key, label, icon in tabs:
            btn = SidebarButton(sidebar, label, icon, command=lambda k=key: self._switch_tab(k))
            btn.pack(fill="x", padx=8, pady=2)
            self.nav_buttons[key] = btn

        # Content area
        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="right", fill="both", expand=True)

        # Create panels
        self.panels["sessions"] = SessionsPanel(self.content)
        self.panels["mcp"] = McpPanel(self.content)
        self.panels["skills"] = SkillsPanel(self.content)

    def _switch_tab(self, key):
        if self.current_tab == key:
            return
        self.current_tab = key
        for k, btn in self.nav_buttons.items():
            btn.set_active(k == key)
        for k, panel in self.panels.items():
            panel.pack_forget()
        self.panels[key].pack(fill="both", expand=True)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
