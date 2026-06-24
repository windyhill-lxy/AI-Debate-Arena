# AI 辩论场

AI 辩论场是一个面向课堂训练、社团演示和多智能体协作展示的辩论系统。项目用 FastAPI 承载辩论流程、用户发言、论据库和导出接口，用 React 呈现辩论室、队内讨论、回放和报告导出体验。

## 核心能力

- 标准 4 对 4 辩论流程：开场准备、立论、质询、驳论、自由辩论、总结陈词和赛后裁判报告。
- 人机与多人联机：支持 AI 自主、人机训练、正反方用户席位、多人房间加入与回放分享。
- 队内讨论与论据库：开场论据搜索先于队内讨论完成，队内讨论阶段区分真人席位和 AI 席位。
- RAG 引用约束：公开发言可绑定论据来源，导出报告保留资料 ID、标题和摘录。
- 回放与导出：回放页支持字幕式播放，后端可导出 Markdown 和 PDF 复盘报告，前端可导出本地 Markdown 纪要。
- 自信度训练可选项：摄像头训练作为可选功能，不使用摄像头时不应弹出摄像头错误。
- 项目流程图：辩论室内可查看按项目代码整理的自然语言流程图。

## 技术栈

- 后端：FastAPI、Pydantic、LangGraph 风格流程编排、MongoDB/Redis 可选降级。
- 前端：React、Vite、React Router、Lucide Icons、Mermaid。
- 测试：pytest、Node 原生断言、Playwright E2E 可选。
- 导出：Markdown 文本报告、fpdf2 PDF 报告。

## 快速启动

便携模式推荐用于演示机和新电脑：

```powershell
.\download-portable.ps1
.\bootstrap.bat
```

复制 `.env.example` 为 `.env`，填写大模型密钥：

```env
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_FLASH_MODEL=deepseek-v4-flash
```

日常启动：

```powershell
.\start.bat
```

局域网多人联机：

```powershell
.\start-lan.bat
```

停止服务：

```powershell
.\stop.bat
```

MongoDB 和 Redis 是可选项。未启动时，后端会使用内存降级，便于先演示核心 UI 与流程。

## 常用命令

后端重点测试：

```powershell
tools\python\python.exe -m pytest backend\tests\test_rag_and_export.py -q
tools\python\python.exe -m pytest backend\tests\test_integration_workflow.py -q
```

前端测试与构建：

```powershell
cd frontend
npm.cmd test
npm.cmd run build
```

E2E 测试首次准备：

```powershell
.\setup-e2e.bat
.\test-e2e.bat
```

## 导出与回放

- `GET /api/debates/{id}/export.md`：导出 Markdown 复盘报告。
- `GET /api/debates/{id}/export.pdf`：导出 PDF 复盘报告。
- 回放页右上角只保留“导出回放”，分享链接显示在只读分享提示区。
- 报告包含摘要、关键指标、阵容、赛程、发言纪要、引用资料和裁判报告，适合直接给用户阅读。

## 项目结构

```text
backend/
  app/
    api/          FastAPI 路由与导出接口
    services/     队内讨论、论据库、联机房间、用户发言、PDF 导出等服务
    workflow/     辩论流程推进
  tests/          后端单元与集成测试
frontend/
  src/
    components/   通用组件与流程图查看器
    features/     辩论室业务组件与 hooks
    pages/        首页、辩论室、回放、管理页
    utils/        展示文本、下载、分享链接等工具
project-report-template-ppt/
project-report-ppt-optimized/
docs/
  github-upload-guide.md
```

## GitHub 上传

完整步骤见 [docs/github-upload-guide.md](docs/github-upload-guide.md)。上传前请确认 `.env`、便携运行时、依赖目录、构建产物和本地缓存没有进入暂存区。
