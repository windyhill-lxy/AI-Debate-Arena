# 2026-06-25 多人联机、PDF、回合图标与队内讨论修复计划

## 背景

用户反馈四类问题：

1. 导出 PDF 失败：
   `PDF 生成失败: Not enough horizontal space to render a single character`
2. 左侧“回合”图标头像太小，需要放大，但不能遮挡“回合”文字。
3. 多人联机总是弹出“辩论回合异常”，宾客发言被 AI 替代。
4. 队内讨论中正方一辩发言了两次，应只发言一次。
5. 新增要求：自由辩论前取消队内讨论环节。
6. 新增要求：总结陈词前也取消队内讨论环节。

本计划先说明根因，再给出可执行修复步骤和验证清单。

## 根因判断

### 1. PDF 生成失败

相关文件：

- `backend/app/services/export_pdf.py`
- `backend/app/api/debates.py`
- `backend/tests/test_rag_and_export.py`

根因：

- `export_pdf.py` 里的 `write_table_row()` 使用固定第一列宽度：
  - `self.cell(42, 7, label, border=1, fill=True)`
  - `self.multi_cell(0, 7, value, border=1, fill=True)`
- 当导出的 Markdown 表格第一列出现长标题、长编号、连续英文、URL、超长中文串等不可断开的内容时，fpdf2 会尝试把文本塞进 `42mm` 的 `cell`。
- fpdf2 遇到无法在当前可用宽度中渲染的字符时会抛出：
  `Not enough horizontal space to render a single character`
- 当前测试只覆盖了普通段落和项目符号，没有覆盖长表格单元格、长 URL、长连续文本，所以问题漏掉了。

修复方向：

- 不再用 `cell()` 渲染可能很长的表格第一列。
- 表格行改成“标签 + 内容”的块状段落，或使用可自动换行的 `multi_cell()`。
- 对连续长串做软断行预处理。
- PDF 导出接口保留错误弹窗，但应尽量避免把排版异常变成 500。

### 2. “回合”图标头像太小

相关文件：

- `frontend/src/features/debate-room/components/DebateLeftRail.jsx`
- `frontend/src/styles/app.css`
- `frontend/src/features/debate-room/currentRoundSpeaker.js`

根因：

- 左侧栏“回合”按钮已经使用当前发言人的头像：
  `img className="dock-btn__avatar"`
- 头像样式固定为 `23px * 23px`：
  - `.dock-btn__avatar { width: 23px; height: 23px; flex: 0 0 23px; }`
- 按钮高度是 `min-height: 58px`，文字字号是 `11px`。
- 头像小到不容易识别；如果只把头像直接放大，又可能压到“回合”文字。

修复方向：

- 把头像放大到约 `30px-34px`。
- 同时把 `.dock-btn` 的 `min-height` 增加到约 `66px-70px`。
- 保持 `flex-direction: column`、稳定 gap，文字不遮挡。
- 为“回合”按钮加专属 class，例如 `dock-btn--round`，避免影响其他 dock 图标。

### 3. 多人联机“宾客发言被 AI 替代”

相关文件：

- `backend/app/api/debates.py`
- `backend/app/services/auto_runner.py`
- `backend/app/services/debate_mode.py`
- `backend/app/services/user_turn_flow.py`
- `frontend/src/features/debate-room/hooks/useDebateRoomSocket.js`

根因链路：

- 自动推进器 `_auto_loop()` 每轮读取当前房间，然后调用 `needs_user_turn(debate)`。
- `needs_user_turn()` 在多人联机模式里有副作用：
  - 在队内讨论时会直接修改 `debate.active_speaker_id`。
  - 它既是“判断函数”，又在改变状态。
- `post_user_message()`、`join_debate_participant()`、`mark_online_ready()`、`kick_participant()`、`host_control_debate()` 当前没有统一房间级锁。
- 因此可能发生这些竞态：
  - 自动 runner 正在判断是否等待真人；
  - 宾客刚加入或提交发言；
  - 主持端或房主端触发 resume/ready；
  - 多个请求读取同一个旧状态，各自写回不同版本。
- 结果可能是：
  - 系统没有稳定停在 `awaiting_user=True`；
  - `active_speaker_id` 被自动 runner 或判断函数改写；
  - 自动 runner 继续走 `debate_graph.run_turn_streaming()`，于是 AI 代替宾客席位生成发言。
- 前端收到后端 `error` 事件后，在 `useDebateRoomSocket.js` 中弹出“辩论回合异常”，来源是：
  `DebateRoom.socket.error`。

修复方向：

- 给多人联机房间引入统一 room lock。
- 所有会改房间状态或推进流程的接口必须串行：
  - 加入席位
  - 标记 ready
  - 踢人
  - WebSocket 上线恢复/离线
  - 用户提交发言
  - 主持控制 pause/resume/next
- 拆分 `needs_user_turn()`：
  - 只读版本只判断，不改状态。
  - 写状态的逻辑放到明确命名的函数里，例如 `prepare_next_online_user_turn()`。
- 自动 runner 在检测到需要真人时，只做：
  - 设置 `awaiting_user=True`
  - 停止 `auto_running`
  - 广播 `awaiting_user`
  - 不再继续生成 AI 发言。
- `post_user_message()` 在同一把 room lock 内重新读取最新状态，再校验发言人，避免旧状态提交。

### 4. 队内讨论正方一辩发言两次

相关文件：

- `backend/app/services/team_discussion.py`
- `backend/app/services/debate_mode.py`
- `backend/app/services/user_turn_flow.py`
- `backend/app/workflow/debate_graph.py`
- `backend/tests/test_team_discussion.py`
- `backend/tests/test_debate_mode.py`
- `backend/tests/test_user_turn_flow.py`

根因链路：

- `team_discussion_speakers()` 通过当前 `segment_label` 统计已发言席位。
- 它会跳过：
  - 当前队内讨论段已经发言的 position；
  - 已声明为真人的 position。
- 但是“任务分配”与“队内讨论”是不同 `segment_label`：
  - `立论前准备 · 一辩任务分配`
  - `立论前准备 · 正方队内讨论(立论)`
- 现有测试 `test_online_match_opening_discussion_still_waits_first_debater_after_task_assign` 明确要求：
  - 正方一辩即使已经做过任务分配，到了正方队内讨论仍要再发言。
- 这与用户现在的期望冲突：队内讨论阶段每人只发言一次，且一辩不应因为“任务分配”再在紧接着的队内讨论重复发言。
- 另外，`_team_discussion_generate()` 会对所有 `team_discussion_speakers()` 返回的 AI 队友循环生成；如果一辩不是真人，且当前讨论段没记录一辩发言，它就会再次生成一辩发言。

修复方向：

- 明确规则：
  - 立论前“一辩任务分配”视为一辩已经完成本轮队内发言。
  - 后续“正方/反方队内讨论(立论)”只让二、三、四辩补充。
  - 如果二/三/四辩是真人席位，则等真人；否则 AI 补齐。
- 修改 `positions_spoken_in_team_segment()` 或新增 `positions_spoken_in_prep_block()`：
  - 立论前队内讨论统计应包含同一方的一辩任务分配消息。
  - 不能误伤自由辩论前或总结前准备。
- 更新现有冲突测试：
  - 删除或改写 `test_online_match_opening_discussion_still_waits_first_debater_after_task_assign`。
  - 新增测试：一辩任务分配后，队内讨论不再等待/生成一辩。

### 5. 自由辩论前、总结陈词前取消队内讨论

相关文件：

- `backend/app/services/debate_schedule.py`
- `frontend/src/data/agents.js`
- `docs/ai-debate-project-flow.mmd`
- 可能涉及 `backend/app/workflow/debate_graph.py` 节点映射

根因/现状：

- 当前赛程中自由辩论前有两个队内讨论节点：
  - `aff_free_team_discussion`
  - `neg_free_team_discussion`
- 当前赛程中总结陈词前也有两个队内讨论节点：
  - `aff_closing_discussion`
  - `neg_closing_discussion`
- 用户要求取消这些节点。

修复方向：

- 从正式赛程 `FORMAL_SCHEDULE` 中移除：
  - `自由辩论前准备 · 正方队内讨论(自由辩)`
  - `自由辩论前准备 · 反方队内讨论(自由辩)`
  - `总结陈词前准备 · 正方队内讨论(总结)`
  - `总结陈词前准备 · 反方队内讨论(总结)`
- 前端静态流程数据同步删除这两个节点。
- Mermaid 项目流程图同步删除或标注为已取消。
- 保留自由辩论前的：
  - 暂停计时
  - RAG 检索对方论点预测
  - 攻防策略调整
  - 攻防案例库
  - 策略可行性判断
  - 角色临时分工
  - 准备就绪
- 保留总结陈词前的：
  - 四辩接收汇总
  - RAG 检索全场知识点
  - 总结框架确认

## 具体执行步骤

### A. 修复 PDF 导出

1. 修改 `backend/app/services/export_pdf.py`。
2. 增加文本清洗函数：
   - 去 Markdown 标记。
   - 给长 URL、长英文串、超长编号插入软空格或零宽空格。
   - 对单元格内容做最大长度保护。
3. 重写 `write_table_row()`：
   - 不使用 `cell(42, ...)` 渲染长 label。
   - 使用两个连续 `multi_cell()`：
     - 第一行：小号加粗/深色 label。
     - 第二行：正常内容。
   - 或直接退化为普通段落：
     `标签：内容`
4. 添加测试：
   - Markdown 表格第一列超长中文。
   - Markdown 表格第一列长 URL。
   - 论据库导出常见表格。
5. 确保 `/api/debates/{id}/export.pdf` 返回 `%PDF`，不再 500。

### B. 调整“回合”头像图标

1. 修改 `DebateLeftRail.jsx`：
   - 给回合按钮加 class：`dock-btn--round`。
2. 修改 `frontend/src/styles/app.css`：
   - `.dock-btn--round { min-height: 68px; }`
   - `.dock-btn--round .dock-btn__avatar { width: 32px; height: 32px; flex-basis: 32px; }`
   - `.dock-btn--round span { line-height: 1.1; }`
3. 在窄屏和普通桌面都检查：
   - 头像清晰。
   - “回合”两个字不被遮挡。
   - 其他按钮不受影响。

### C. 修复多人联机状态竞态

1. 在 `backend/app/api/debates.py` 增加房间级锁：
   - `_online_room_locks: dict[str, asyncio.Lock]`
   - `_online_room_lock(debate_id)`
2. 用同一把锁包住这些函数的读改写：
   - `join_debate_participant`
   - `mark_online_ready`
   - `kick_participant`
   - `_restore_participant_on_ws_connect`
   - `_mark_participant_offline`
   - `post_user_message`
   - `host_control_debate`
3. 避免锁内执行长期后台动作：
   - `resume_auto()` 可以在锁外调用，但必须基于锁内决定好的状态。
   - 如果 `host-control next` 会跑 LLM，应评估是否改为短锁设置状态 + 后台任务推进，避免长时间占锁。
4. 拆分 `needs_user_turn()`：
   - 新增无副作用函数，例如 `peek_user_turn_required(debate, participant=None)`。
   - 保留需要写 `active_speaker_id` 的函数，但名称必须体现会改状态。
5. 修改自动 runner：
   - 用明确函数准备真人发言状态。
   - 如果需要真人，立即保存并广播 `awaiting_user`，不进入 AI 生成。
6. 修改用户提交：
   - 在 room lock 内读取最新状态。
   - 校验 `participant_id`、席位、`active_speaker_id`、`awaiting_user`。
   - 写入消息后，如果仍有下一位真人队友需要发言，则不 `resume_auto()`。

### D. 修复队内讨论一辩重复

1. 修改 `team_discussion.py` 或 `debate_mode.py` 的发言统计。
2. 新规则：
   - 对 `opening_prep` 的正反方队内讨论，统计同方“一辩任务分配”消息为一辩已发言。
3. 修改 `team_discussion_speakers()`：
   - 立论队内讨论不返回一辩。
   - 如果用户是二辩/三辩/四辩，则 AI 不代替该真人席位。
4. 修改 `next_online_participant_for_team_discussion()`：
   - 同样应用“一辩任务分配算一辩已发言”的规则。
5. 更新测试：
   - 一辩任务分配后，正方队内讨论等待二辩而不是一辩。
   - AI 队友生成列表不包含已任务分配的一辩。
   - 每个席位在同一队内讨论段只出现一次。

### E. 取消自由辩论前、总结陈词前队内讨论

1. 修改 `backend/app/services/debate_schedule.py`：
   - 删除 `aff_free_team_discussion`
   - 删除 `neg_free_team_discussion`
   - 删除 `aff_closing_discussion`
   - 删除 `neg_closing_discussion`
2. 修改 `frontend/src/data/agents.js`：
   - 删除对应静态 timeline 节点。
3. 修改 `docs/ai-debate-project-flow.mmd`：
   - 自由辩论前准备不再展示队内讨论。
   - 总结陈词前准备不再展示队内讨论。
4. 检查 `debate_graph.py` 中对 `free_prep` 的映射：
   - `("strategy_plan", "free_prep"): "team_free_discussion"` 这类显示节点要改成更合适的节点，例如 `free_strategy_check` 或 `free_temp_roles`。
5. 检查 `debate_graph.py` 中对 `closing_prep` 的映射：
   - `("strategy_plan", "closing_prep"): "team_closing_discussion"` 这类显示节点要改成 `closing_frame` 或更合适的总结框架节点。
6. 更新测试：
   - 正式赛程中不包含 `aff_free_team_discussion` / `neg_free_team_discussion`。
   - 正式赛程中不包含 `aff_closing_discussion` / `neg_closing_discussion`。
   - 自由辩论前准备可顺利推进到 `free_debate_pool`。
   - 总结陈词前准备可顺利推进到 `closing_neg4`。

## 验证清单

### 后端测试

运行：

```powershell
D:\Project\AI辩论项目\tools\python\python.exe -m pytest backend/tests/test_rag_and_export.py backend/tests/test_debate_mode.py backend/tests/test_team_discussion.py backend/tests/test_user_turn_flow.py backend/tests/test_online_match.py backend/tests/test_online_presence.py backend/tests/test_online_session_flow.py backend/tests/test_integration_websocket.py -q
```

必须新增或调整的用例：

- PDF 表格长文本不崩。
- 多人联机同一席位抢占返回 409。
- 宾客轮到发言时 `auto_running=False` 且 `awaiting_user=True`。
- 宾客发言提交后消息 speaker_id 等于对应席位，例如 `aff_2`，不能变成 AI 自动生成。
- 队内讨论一辩任务分配后不再重复等待/生成一辩。
- 自由辩论前赛程不再包含队内讨论。
- 总结陈词前赛程不再包含队内讨论。

### 前端验证

运行：

```powershell
cd D:\Project\AI辩论项目\frontend
npm.cmd run build
```

手动检查：

- “回合”头像变大，文字不被遮挡。
- 联机房间中宾客轮到发言时，下方输入框可用。
- 宾客发言提交后，主舞台显示宾客本人席位发言。
- 不再频繁弹出“辩论回合异常”。
- 自由辩论前不显示“正方/反方队内讨论(自由辩)”。
- 总结陈词前不显示“正方/反方队内讨论(总结)”。
- PDF 导出成功打开。

## 风险与顺序

建议按以下顺序执行：

1. 先修 PDF，风险独立，容易验证。
2. 再修 UI 头像，风险低。
3. 再修自由辩论前、总结陈词前取消队内讨论，因为它会影响赛程和前端静态展示。
4. 最后修多人联机锁与真人发言接管，这是核心风险最高的部分。
5. 最后修一辩重复发言并调整冲突测试。

注意：

- 多人联机锁和自动 runner 的改动必须配套测试，否则容易把“AI 替代真人”改成“流程卡住不动”。
- `needs_user_turn()` 当前有副作用，修复时必须全面查调用点，不能只改一个调用方。
- 队内讨论规则变更会导致现有部分测试预期反转，要同步修改测试名称和断言。
