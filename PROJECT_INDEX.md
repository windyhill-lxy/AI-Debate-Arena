# AI 辩论场 · 项目索引

## 概览

多智能体 AI 辩论系统：首页选择模式 → 进入辩论室 → AI 回合**自动推进**，发言以 **Markdown 流式**输出，并在流式过程中为下一位辩手**预热检索**。

| 项目 | 说明 |
|------|------|
| 后端 | FastAPI + LangGraph + DeepSeek + MongoDB + Redis |
| 前端 | React + Vite + react-router-dom + react-markdown |
| 语音 | 阿里云百炼 DashScope Qwen3-TTS-Instruct + 智能语音交互一句话识别 |
| 默认端口 | 后端 `9000`（`.env` 中 `BACKEND_PORT`），前端 `5173` |

## 辩论模式

| 模式 ID | 名称 | 用户输入 |
|---------|------|----------|
| `ai_autonomous` | AI 自主辩论 | 否 |
| `user_affirmative` | 用户加入正方 | 正方发言轮次 |
| `user_negative` | 用户加入反方 | 反方发言轮次 |

## 目录结构

```
AI辩论项目/
├── PROJECT_INDEX.md          # 本文件：项目索引
├── CHANGELOG_CONVERSATIONS.md # 每次对话/会话更新记录
├── backend/
│   └── app/
│       ├── main.py
│       ├── api/debates.py
│       ├── models.py
│       ├── workflow/debate_graph.py
│       └── services/
│           ├── llm.py              # 同步/流式 DeepSeek
│           ├── auto_runner.py      # 自动推进循环
│           ├── debate_mode.py      # 模式与用户轮次判断
│           ├── tts.py              # 阿里云 TTS 音色与合成
│           └── changelog.py        # 写入更新日志
├── frontend/
│   └── src/
│       ├── pages/Home.jsx          # 首页（类 Claude 选模式）
│       ├── pages/DebateRoom.jsx    # 辩论室（薄入口）
│       ├── features/debate-room/   # 辩论室逻辑与组件拆分
│       │   ├── hooks/useDebateRoom.js
│       │   └── components/         # 左栏 / 中栏 / 右栏等
│       ├── hooks/useDebateSocket.js
│       └── components/MarkdownBody.jsx
├── start.bat / stop.bat          # 根目录保留常用入口
├── school-start.bat              # 学校机快速入口（内部调用 scripts/school）
├── setup-e2e.bat / test-e2e.bat  # E2E 入口（内部调用 scripts/e2e）
├── scripts/                      # 便携环境、venv、学校机与 E2E 辅助脚本
└── README.md
```

## API 速查

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/debates` | 创建房间（body 含 `mode`） |
| GET | `/api/debates/{id}` | 获取状态 |
| POST | `/api/debates/{id}/message` | 用户发言（仅人机模式） |
| POST | `/api/debates/{id}/speech-to-text` | 上传用户录音，调用阿里云一句话识别转文字 |
| POST | `/api/debates/{id}/resume` | 恢复自动推进 |
| GET | `/api/debates/{id}/export.md` | 导出全场 Markdown 逐字稿（含资料编号） |
| GET | `/api/debates/{id}/export.pdf` | 由 export.md 同源内容生成 PDF |
| POST | `/api/debates/{id}/assist/draft` | 人机模式代拟发言草稿 |
| GET | `/api/confidence-monitor/status` | 自信度训练状态（可用性/运行中） |
| POST | `/api/confidence-monitor/toggle` | 开关自信度摄像头训练 |
| GET | `/api/confidence-monitor/metrics` | 程序性参数统计与固定建议 |
| POST | `/api/confidence-monitor/report` | 全过程参数 + 大模型深度总结 |
| GET | `/api/debates/{id}/llm-stats` | 本房间 LLM 调用与 token 粗统计（内存） |
| GET | `/api/admin/overview` | 管理端：存储/房间统计/活跃 runner |
| GET | `/api/admin/debates` | 管理端：房间列表摘要 |
| GET | `/api/admin/debates/{id}` | 管理端：单房间诊断 + LLM 统计 |
| POST | `/api/admin/debates/{id}/stop-auto` | 管理端：停止自动推进 |
| POST | `/api/admin/debates/{id}/resume-auto` | 管理端：恢复自动推进 |
| PUT | `/api/debates/{id}/user-draft` | 保存人机模式发言框草稿（限流） |
| WS | `/api/debates/ws/{id}` | 流式 chunk / 状态推送 |

## WebSocket 事件

| event | 说明 |
|-------|------|
| `snapshot` | 连接后首包：当前房间完整状态 |
| `debate_created` | 房间创建 |
| `speech_start` | 开始流式发言 |
| `speech_chunk` | Markdown 增量 |
| `speech_end` | 发言结束 |
| `speech_audio_start` | 开始调用阿里云 TTS |
| `speech_audio` | 语音合成完成，返回音频 URL |
| `speech_audio_error` | 语音合成失败 |
| `speech_audio_progress` | TTS 分段合成进度 |
| `pipeline_prep` | 下一位辩手预热 |
| `reflection_done` | 非自由辩「草稿→定稿」反思结束（字符数统计） |
| `awaiting_user` | 等待用户输入 |
| `debate_stepped` | 完成一个 AI 回合 |
| `message_added` | 用户提交发言 |
| `debate_finished` | 比赛结束 |
| `error` | 自动推进等异常（如模型不可用） |
| `stream` | 兼容旧版：未显式设置 `event` 时的流式负载（少见） |

完整字段契约见仓库根目录 [`docs/websocket-events.schema.json`](docs/websocket-events.schema.json)。

## 阿里云 TTS 配置

```env
DASHSCOPE_API_KEY=你的百炼API-Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/api/v1
ALIYUN_TTS_ENABLED=true
ALIYUN_TTS_MODEL=qwen3-tts-instruct-flash
ALIYUN_TTS_LANGUAGE_TYPE=Chinese
```

当前内置音色映射在 `backend/app/services/tts.py`，每位 AI 辩手有独立 voice、情感与角色指令。

## 阿里云 ASR 配置

语音录入按钮会在浏览器端录制 16k 单声道 WAV，上传到后端 `/speech-to-text`，后端使用 AccessKey 换取临时 Token 后调用智能语音交互 RESTful 一句话识别。真实密钥只放 `.env`：

```env
ALIYUN_ASR_ENABLED=true
ALIYUN_AK_ID=你的 AccessKey ID
ALIYUN_AK_SECRET=你的 AccessKey Secret
ALIYUN_ISI_APPKEY=你的智能语音交互 AppKey
```

## 启动

```bat
start.bat
```

或分别启动 backend / frontend，详见 `README.md`。

## 学校机房开发（关机重置）

机房电脑 C 盘会清空，推荐：

| 做法 | 说明 |
|------|------|
| **整个项目放 U 盘** | `backend\.venv`、`frontend\node_modules`、`.env` 都保存在 U 盘，关机不丢 |
| **首次** `school-bootstrap.bat` | 安装依赖到 U 盘 |
| **每次** `school-start.bat` | 启动前后端（可不装 MongoDB/Redis） |
| **便携运行时** | 已内置 `tools/node`、`tools/python`；启动脚本自动优先调用。重装运行 `download-portable.ps1` |
| **代码同步** | Git（Gitee/GitHub）家里 push、学校 pull；或与 U 盘并用 |

密钥只放在 U 盘上的 `.env`，不要写进 `.env.example` 或提交 Git。

## 常见错误 WinError 10013

若后端启动报「以一种访问权限不允许的方式做了一个访问套接字」，多半是 **8000 端口被 Windows 保留**（Hyper-V 排除端口段 `7905–8004`）。本项目默认已改为 **9000**，可在 `.env` 修改 `BACKEND_PORT`。

## 持续集成与可观测性

- **CI**：`.github/workflows/ci.yml`（后端 `pytest`、前端 `npm run build`）。
- **请求追踪**：HTTP 响应头 `X-Request-ID`；日志格式含 `[rid=…]`。
- **限流**：创建房间与写类接口按 IP 滑动窗口限流（`.env` 中 `API_RATE_LIMIT_*`）。
- **WebSocket 契约**：`docs/websocket-events.schema.json`。
