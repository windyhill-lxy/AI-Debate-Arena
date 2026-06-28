# Current Work Cleanup Plan

This file records how to turn the current dirty working tree into a clean,
reviewable state without losing useful work.

## Already Cleaned

- Runtime camera session files under `data/confidence_sessions/` are now ignored.
- Auto-appended debate session logs now belong in `data/conversation_sessions.md`,
  not in the tracked product changelog.
- Existing ignored runtime data remains ignored:
  - `data/*.sqlite`
  - `data/*.jsonl`
  - `data/conversation_sessions.md`
  - `*.log`
  - portable runtimes under `tools/node/` and `tools/python/`

## Keep As Source Changes

### Backend Debate Flow

Files:
- `backend/app/api/debates.py`
- `backend/app/models.py`
- `backend/app/workflow/debate_graph.py`
- `backend/app/services/debate_schedule.py`
- `backend/tests/test_debate_mode.py`
- `backend/tests/test_integration_workflow.py`
- `backend/tests/test_online_match.py`
- `backend/tests/test_schedule_meta.py`
- `backend/tests/test_team_discussion.py`
- `backend/tests/test_user_turn_flow.py`

Purpose:
- Formal 4v4 schedule fixes.
- Team-discussion gating and skip behavior.
- Opening evidence and argument-bank flow.
- User-turn and online-room behavior.

Suggested commit:
- `feat: align debate flow with formal 4v4 rules`

### TTS And Audio Playback

Files:
- `backend/app/services/auto_runner.py`
- `backend/app/services/tts.py`
- `backend/app/core/config.py`
- `backend/requirements.txt`
- `backend/tests/test_auto_runner.py`
- `backend/tests/test_tts_qwen.py`
- `backend/tests/test_llm_usage.py`
- `frontend/src/hooks/useAudioQueue.js`
- `frontend/src/hooks/audioQueueControl.js`
- `frontend/src/hooks/audioQueueControl.test.mjs`
- `frontend/src/features/debate-room/ttsControl.js`
- `frontend/src/features/debate-room/ttsControl.test.mjs`

Purpose:
- Realtime DashScope TTS.
- Start TTS as soon as LLM speech output ends.
- Stop/skip queue hardening.

Suggested commit:
- `feat: stream tts immediately after ai speech generation`

### Camera, Speech Input, And User Training

Files:
- `backend/app/services/confidence_monitor.py`
- `backend/tests/test_visual_behavior_analysis.py`
- `frontend/src/components/ConfidenceCameraPreview.jsx`
- `frontend/src/components/confidenceCameraPreview.test.mjs`
- `frontend/src/cameraPerformance.test.mjs`
- `frontend/src/features/debate-room/hooks/useDebateRoom.js`
- `frontend/src/features/debate-room/speechInputAutoSubmit.test.mjs`
- `frontend/src/pages/Home.jsx`
- `frontend/src/pages/DebateRoom.jsx`
- `frontend/src/styles/app.css`
- `frontend/src/styles/home.css`

Purpose:
- Low-frequency camera preview and analysis.
- Move multidimensional scores below the camera image.
- Auto-submit recognized user speech.

Suggested commit:
- `feat: add lightweight camera training and speech auto submit`

### Debate Room UI And Progress

Files:
- `frontend/src/features/debate-room/components/DebateCenterStage.jsx`
- `frontend/src/features/debate-room/headerCollapseButton.test.mjs`
- `frontend/src/features/debate-room/components/DebateLeftRail.jsx`
- `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- `frontend/src/features/debate-room/components/DebateRoomDock.jsx`
- `frontend/src/features/debate-room/components/PublicMessage.jsx`
- `frontend/src/features/debate-room/progressControl.js`
- `frontend/src/features/debate-room/onlineProgressControl.test.mjs`
- `frontend/src/features/debate-room/factBadge.js`
- `frontend/src/features/debate-room/factBadge.test.mjs`
- `frontend/src/features/debate-room/localDebate.js`
- `frontend/src/features/debate-room/utils.js`
- `frontend/package.json`

Purpose:
- Room header icon collapse button.
- Better progress and status controls.
- Citation and fact-badge display fixes.

Suggested commit:
- `feat: refine debate room controls and progress display`

### Public Tunnel And Online Helpers

Files:
- `frontend/src/components/OnlineSimplePanel.jsx`
- `frontend/src/features/debate-room/hooks/useDebateRoomSocket.js`
- `frontend/src/hooks/useDebateSocket.js`
- `frontend/src/hooks/usePublicTunnel.js`
- `frontend/src/hooks/publicTunnelClient.js`
- `frontend/src/hooks/publicTunnelClient.test.mjs`
- `frontend/src/utils/publicInviteTunnel.js`
- `frontend/src/utils/publicInviteTunnel.test.mjs`
- `backend/tests/test_tunnel.py`

Purpose:
- Public invite tunnel flow and socket reliability.

Suggested commit:
- `feat: harden public invite tunnel flow`

## Decide Whether To Keep

### PPT Flow Assets

Files:
- `docs/ppt-effective-flow/**`
- `tools/build_enriched_interview_ppt.py`
- `tools/check_ppt_original_text_preserved.py`
- `tools/generate_ppt_effective_page_flows.mjs`
- `tools/qa_ppt_structure.py`
- `tools/render_svg_png.mjs`

Recommendation:
- Keep if these are part of the project report deliverable.
- Otherwise move them outside the repo or add a narrower ignore rule for generated PNG/SVG outputs.

Suggested commit if kept:
- `docs: add ppt implementation flow assets`

## Usually Do Not Commit

- `data/`
- `*.log`
- auto-appended debate session logs
- temporary rendered previews
- local camera session data
- portable runtimes under `tools/node/` and `tools/python/`

## Verification Commands

Run before committing grouped changes:

```powershell
pytest backend/tests/test_visual_behavior_analysis.py backend/tests/test_schedule_meta.py backend/tests/test_auto_runner.py backend/tests/test_tts_qwen.py backend/tests/test_user_turn_flow.py -q

cd frontend
npm test -- --runInBand
npm run build
```
