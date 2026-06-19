# AI Debate Arena

一个面向 AI 智能体开发专项赛的多智能体辩论系统原型。后端使用 FastAPI + LangGraph 编排辩论逻辑，MongoDB 保存论点与历史记录，Redis 做实时会话缓存；前端使用 React 实现现代化辩论界面。

## 功能亮点

- 多智能体辩论：正方、反方、裁判、资料官、策略师、AI 教练。
- LangGraph 工作流：包含 RAG 检索、策略规划、LLM 判断、事实检查、裁判评分、回合路由等 10 个以上节点。
- RAG 与防幻觉：发言绑定来源，事实检查节点会标记缺少来源的内容。
- 多模式 UI：上下文模式、真实辩论模式、上帝模式、限时/不限时回答。
- AI 辅助：用户不会回答时，可获得反驳思路和资料，但不会自动代替用户发言。
- 人机训练增强：可选「自信度摄像头训练」（MediaPipe 姿态/眼神/手势分析），支持首页一键开关。
- 三栏现代界面：左侧设置，中间角色舞台和发言流，右侧 AI 编辑器式输入，底部展示工作流树状图。

## 大模型配置

当前采用 **标准 4 对 4 赛制**（正反各四辩），流程包含：开篇立论 → 质询 → 驳论与对辩 → 盘问与小结 → 自由辩论 → 总结陈词 → 赛后裁决。

模型配置：

- 全流程：`deepseek-v4-flash`（更快响应，适合高频交锋）

```env
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
```

若仍使用历史模型名（如 `deepseek-flash` / `deepseek-chat`），系统会在运行时自动映射到 `deepseek-v4-flash` / `deepseek-v4-pro`。也可在 `.env` 中设置 `DEEPSEEK_FALLBACK_MODELS`（逗号分隔）增加更多备用模型名。

## 改进与路线图

见仓库根目录 [`IMPROVEMENTS.md`](IMPROVEMENTS.md)：记录已落地项（赛程进度、配置横幅、启动恢复自动推进、裁判流程快路径、引用校验等）与后续计划。

## 测试与 CI

```bash
cd backend
pip install -r requirements.txt
pytest tests -q
```

若需启用「自信度摄像头训练」：

```bash
cd backend
pip install -r requirements-confidence.txt
```

集成测试使用内存存储并 Mock LLM，无需 MongoDB/Redis/API Key。管理页：启动后访问 http://127.0.0.1:5173/admin 。

GitHub Actions：推送或 PR 至 `main`/`master` 时运行后端 `pytest` 与前端 `npm run build`（见 `.github/workflows/ci.yml`）。

## 快速启动

便携模式（推荐，U 盘/新机）：

1. 首次：PowerShell 运行 `download-portable.ps1`（下载 `tools/python` 与 `tools/node`）。
2. 首次：双击 `bootstrap.bat`（把 Python/前端依赖装进 `tools`，只需一次）。
3. 复制 `.env.example` 为 `.env` 并填写 `DEEPSEEK_API_KEY`。
4. 日常：双击 `start.bat`（直接用 `tools` 内运行时，**不再创建 backend\.venv、不再每次 pip**）。
5. 关闭时双击 `stop.bat`。

局域网多人：双击 `start-lan.bat`。

可选安装 MongoDB 和 Redis；未启动时后端会使用内存降级，方便先演示 UI。

如果使用 Docker 启动数据库：

```bash
docker run -d --name ai-debate-mongo -p 27017:27017 mongo:7
docker run -d --name ai-debate-redis -p 6379:6379 redis:7
```

## 后端接口

- `POST /api/debates`：创建辩论房间。
- `GET /api/debates/{id}`：获取房间状态。
- `GET /api/debates/{id}/export.md`：导出 Markdown 逐字稿。
- `GET /api/debates/{id}/export.pdf`：由 Markdown 逐字稿转换的 PDF。
- `GET /api/debates/{id}/llm-stats`：本房间 LLM 用量粗统计（内存）。
- `PUT /api/debates/{id}/user-draft`：保存人机模式发言草稿。
- `POST /api/debates/{id}/message`：提交用户发言。
- `POST /api/debates/{id}/speech-to-text`：用户录音上传后调用阿里云一句话识别，返回可编辑文字。
- `POST /api/debates/{id}/assist`：获取 AI 教练建议。
- `POST /api/debates/{id}/assist/draft`：人机模式代拟发言草稿。
- `GET /api/confidence-monitor/status`：查看自信度训练可用性与运行状态。
- `POST /api/confidence-monitor/toggle`：开启/关闭自信度训练摄像头窗口。
- `GET /api/confidence-monitor/metrics`：输出程序性参数统计与固定建议文本。
- `POST /api/confidence-monitor/report`：基于全过程参数生成大模型深度总结评价文本。

### E2E 测试（无需 Node，一键）

1. 双击 **`setup-e2e.bat`**（首次：安装 Python 版 Playwright + Chromium；尽量构建 `frontend/dist`）
2. 双击 **`test-e2e.bat`**（自动起 Mock 后端 + 静态前端，跑浏览器用例）

仅需本机有 Python（或用 `download-portable.ps1` 下载到 `tools/python`）。  
若已有 `frontend/dist`，全程可不装 Node；否则 `setup-e2e.bat` 会尝试用便携 Node 构建一次。

可选：仍可用 Node 版 `frontend/npm run test:e2e`（需自行安装依赖）。
- `POST /api/debates/{id}/step`：推进一次 AI 辩论循环。
- `WS /api/debates/ws/{id}`：实时推送接口。

## 项目结构

```text
backend/
  app/
    api/          FastAPI 路由
    core/         配置
    db/           MongoDB 与 Redis 访问
    services/     RAG 和实时连接管理
    workflow/     LangGraph 辩论状态图
frontend/
  src/
    assets/agents 娘化 AI 角色图
    data/         角色与工作流配置
    styles/       现代化 UI 样式
start.bat         本机启动（tools 便携运行时）
start-lan.bat     局域网启动
bootstrap.bat     首次配置（pip 到 tools/python + npm install）
stop.bat          关闭前后端
scripts/          env.bat / start-core.bat / bootstrap-core.bat 等核心脚本
```

## 比赛展示建议

演示时可以按这个顺序讲解：需求分析、工作流图、多智能体分工、RAG 防幻觉、上下文/上帝模式差异、AI 辅助如何提升人机协同，最后展示 MongoDB/Redis 的持久化和实时缓存设计。
