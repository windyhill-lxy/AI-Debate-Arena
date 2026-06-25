# 改进项落地清单

本文档跟踪「项目改进建议」的实施状态。可分多轮迭代，核心能力已接入代码。

## 已落地（本轮）

| 项 | 说明 |
|----|------|
| 启动恢复 auto_runner | 后端 `lifespan` 调用 `recover_auto_runners()`，恢复 `auto_running` 且未结束的房间 |
| 裁判流程快路径 | `is_procedural_segment`：RAG/判断类裁判环节跳过 LLM 长发言，直接推进赛程 |
| 引用校验 | `sanitize_citations` 移除未入库的资料编号 `[id]` |
| 分环节模型 | `resolve_model`：`closing`/`post_match` 用 `DEEPSEEK_MODEL`，其余用 flash |
| 健康检查增强 | `/health` 返回 storage、mongo/redis、TTS 开关 |
| CORS 可配置 | `CORS_ORIGINS` 环境变量 |
| 时间戳 | 统一 `utc_now()`，替代废弃的 `utcnow()` |
| 首页/辩论室配置横幅 | `SystemConfigBanner`：API Key、内存模式、TTS 关闭提示 |
| 赛程进度条 | `DebateProgressBar`：当前步 / 总步、百分比 |
| 环节倒计时 | `useTurnTimer`：限时模式下显示剩余秒数 |
| TTS 超时 | 前端合成等待由 65s 降为 28s（关闭 TTS 时 15s） |
| 单元测试 | `test_citations`、`test_schedule_meta` 等 |
| 集成测试 | `tests/conftest.py`、`test_integration_api.py`、`test_integration_workflow.py`（25 项） |
| 管理页 | `/admin` + `/api/admin/*` 概览、列表、诊断、停止/恢复推进 |
| DebateRoom 拆分 | 已完成：`features/debate-room/`（hook + 左/中/右栏组件） |
| WebSocket E2E | ✅ `tests/test_integration_websocket.py`（snapshot / speech_* / debate_stepped） |
| 回放分享 | ✅ `/share/:id` 只读回放 + 「复制分享链接」 |
| PDF 导出 | ✅ `GET /export.pdf`（fpdf2，同源 `export.md`） |
| 引用点击跳转 | ✅ 主舞台 `[kb-x]` 点击展示 `CitationDetailPanel` |
| 人机模式增强 | ✅ 发言预览 + `POST /assist/draft` 代拟草稿 |
| E2E | ✅ `test-e2e.bat`（Python Playwright，无需 Node；`setup-e2e.bat` 一键安装） |

## 使用提示

- **持久化**：学校/机房请将项目放 U 盘并配置 `.env`；需要保留历史请启动 MongoDB。
- **配置**：复制 `.env.example` 后填写 `DEEPSEEK_API_KEY`；可选 `CORS_ORIGINS`、`DEEPSEEK_PRO_PHASES`。
