# CCwatch - Claude Code Session Manager

> Claude Code 会话管理工具 — 命令行 + 图形界面双版本

> ⚠️ **非官方社区工具**，与 Anthropic 无关联。

## 功能

- **会话列表** — 按项目分组显示所有会话，按时间排序
- **搜索** — 按项目名或会话 ID 模糊搜索
- **重命名** — 给会话起个好记的名字
- **详情查看** — 显示消息数、时间、文件路径、操作菜单
- **导出** — 单条或批量导出会话为 `.jsonl` 文件
- **清理** — 删除 7 天前的旧会话（含确认提示）
- **统计** — 按项目维度显示会话数量、大小、时间分布
- **MCP 服务器** — 显示已配置的 MCP 服务器及中文说明（GUI）
- **Skills** — 显示已安装的 Skills 及中文说明（GUI）

## 版本

| 版本 | 文件 | 说明 |
|------|------|------|
| Bash CLI | `claude-session-manager.sh` | 原始脚本，需 Git Bash |
| Python CLI | `claude_session_manager.py` | 跨平台，支持交互菜单 |
| GUI | `claude_session_gui.py` | CustomTkinter 图形界面 |

## 使用

### 命令行

```bash
# 列出会话
python claude_session_manager.py list

# 搜索
python claude_session_manager.py search keyword

# 重命名
python claude_session_manager.py rename <id> "新名字"

# 查看详情
python claude_session_manager.py info <id>

# 统计
python claude_session_manager.py stats

# 导出
python claude_session_manager.py export <id> -o output.jsonl

# 清理旧会话
python claude_session_manager.py clean

# 交互菜单（双击 exe 或无参数运行）
python claude_session_manager.py
```

### 图形界面

```bash
python claude_session_gui.py
```

或直接双击 `claude-session-gui.exe`。

## 构建 exe

```bash
pip install pyinstaller

# CLI 版本
pyinstaller --onefile --name claude-session claude_session_manager.py

# GUI 版本
pyinstaller --onefile --windowed --name claude-session-gui --icon claude-session.ico claude_session_gui.py
```

## 项目结构

```
~/.claude/
├── projects/           # Claude Code 会话数据（JSONL）
├── session-names.txt   # 自定义会话名称
└── .mcp.json           # MCP 服务器配置
```

## 系统要求

- **CLI**: Python 3.8+
- **GUI**: Python 3.8+，CustomTkinter（`pip install customtkinter`）
- **Bash 版**: Git Bash (Windows) 或 bash (Linux/Mac)
- **exe 版**: 无依赖，直接运行

## License

MIT
