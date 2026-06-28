from datetime import datetime
from pathlib import Path

from app.core.config import get_settings

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
CHANGELOG_FILE = _PROJECT_ROOT / "CHANGELOG_CONVERSATIONS.md"
SESSION_LOG_FILE = _PROJECT_ROOT / "data" / "conversation_sessions.md"
INDEX_FILE = _PROJECT_ROOT / "PROJECT_INDEX.md"


def _now_label() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_changelog(title: str, body: str) -> None:
    line = f"\n## {_now_label()} · {title}\n\n{body.strip()}\n"
    SESSION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SESSION_LOG_FILE.exists():
        SESSION_LOG_FILE.write_text(SESSION_LOG_FILE.read_text(encoding="utf-8") + line, encoding="utf-8")
    else:
        SESSION_LOG_FILE.write_text(
            "# 本地辩论会话记录\n\n本文件由后端自动追加，仅作为本机运行日志，不提交到 Git。\n" + line,
            encoding="utf-8",
        )


def ensure_project_index() -> None:
    if INDEX_FILE.exists():
        return
    settings = get_settings()
    INDEX_FILE.write_text(
        f"""# AI 辩论场 · 项目索引

> 自动生成于 { _now_label() }

## 概览

- **项目名称**：{settings.app_name}
- **技术栈**：FastAPI + LangGraph + React + MongoDB + Redis + DeepSeek
- **默认辩题**：人工智能是否会提升青少年的综合学习能力

## 目录结构

| 路径 | 说明 |
|------|------|
| `backend/app/main.py` | FastAPI 入口 |
| `backend/app/api/debates.py` | 辩论 REST / WebSocket API |
| `backend/app/workflow/debate_graph.py` | LangGraph 多智能体工作流 |
| `backend/app/services/llm.py` | DeepSeek 同步/流式调用 |
| `backend/app/services/auto_runner.py` | AI 回合自动推进 |
| `backend/app/services/changelog.py` | 更新日志写入 |
| `frontend/src/pages/Home.jsx` | 首页（模式选择） |
| `frontend/src/pages/DebateRoom.jsx` | 辩论室 |
| `CHANGELOG_CONVERSATIONS.md` | 人工维护的产品更新记录 |
| `data/conversation_sessions.md` | 本地自动追加的辩论会话记录（不提交） |

## 辩论模式

1. **AI 自主辩论** — 全自动，无用户输入
2. **用户加入正方** — 正方发言轮次等待用户输入
3. **用户加入反方** — 反方发言轮次等待用户输入

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/debates` | 创建房间（含 `mode`） |
| GET | `/api/debates/{{id}}` | 获取状态 |
| POST | `/api/debates/{{id}}/message` | 用户发言（仅人机模式） |
| POST | `/api/debates/{{id}}/resume` | 用户发言后恢复自动推进 |
| WS | `/api/debates/ws/{{id}}` | 流式事件与状态推送 |

## 启动

```bash
# 见 start.bat 或分别启动 backend / frontend
```
""",
        encoding="utf-8",
    )
