# Debate Training Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add free debate training and first-speaker opening training while preserving existing autonomous, human, local, and public invite debate flows.

**Architecture:** Reuse the existing debate room for multi-turn free debate training, because it already owns streaming messages, scoring, argument bank display, visibility rules, export, and WebSocket updates. Add a lightweight training service for first-speaker draft analysis, because that workflow is a focused critique task rather than a full scheduled debate.

**Tech Stack:** FastAPI, Pydantic models, existing RAG/vector store, existing LLM gateway, DashScope Qwen3-TTS HTTP API, React/Vite, Playwright-oriented UI testability.

---

### Task 1: Backend Rule Tests

**Files:**
- Modify: `backend/tests/test_training_rules.py`
- Modify: `backend/tests/test_user_message_scoring.py`
- Modify: `backend/tests/test_argument_bank.py`

- [ ] Add failing tests for AI autonomous rooms forcing `all_visible`, disabling human timing penalty, and ignoring camera confidence when no camera is actually running.
- [ ] Add failing tests for extracting and locking positive/negative argument bank items after AI-generated claims.
- [ ] Run the targeted tests and confirm they fail because the behavior is missing.

### Task 2: Backend Training API Tests

**Files:**
- Create: `backend/tests/test_training_api.py`

- [ ] Add failing tests for `POST /api/debates/free-training/prepare`.
- [ ] Add failing tests for `POST /api/debates/opening-training/analyze`.
- [ ] Verify the tests fail with 404 before implementation.

### Task 3: Backend Implementation

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/api/debates.py`
- Modify: `backend/app/services/argument_bank.py`
- Create: `backend/app/services/training.py`
- Modify: `backend/app/services/user_message_scoring.py`
- Modify: `backend/app/services/camera_speech_scoring.py`
- Modify: `backend/app/services/auto_runner.py`
- Modify: `backend/app/services/tts.py`

- [ ] Add request/response models for free training preparation and opening analysis.
- [ ] Implement argument-bank generation and parsing with deterministic fallback IDs.
- [ ] Implement opening analysis using RAG sources, structural scoring, hallucination risk, and model critique fallback.
- [ ] Enforce no camera score when monitor is stopped, unavailable, or has no usable sample.
- [ ] Replace MiniMax TTS with DashScope Qwen3-TTS while preserving existing frontend audio payload shape.
- [ ] Make AI autonomous auto-runner wait by TTS estimated playback time, bounded to avoid stalled demos.

### Task 4: Frontend Training UI

**Files:**
- Modify: `frontend/src/pages/Home.jsx`
- Create: `frontend/src/pages/OpeningTraining.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/RuntimeSettingsPanel.jsx`
- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- Modify: `frontend/src/styles/home.css`
- Modify: `frontend/src/styles/app.css`

- [ ] Add two homepage training cards.
- [ ] Add free debate training preparation state: topic, side, rounds, generated argument bank.
- [ ] Create a first-speaker training page with topic, side, draft, analysis result, score, RAG checks, and revision advice.
- [ ] Group runtime settings into speech input, TTS, and LLM sections.
- [ ] Disable camera/timing controls for AI autonomous mode and explain the locked state in UI copy.
- [ ] Keep visibility options limited to all visible and own-side only.

### Task 5: Role Portrait Assets

**Files:**
- Replace: `frontend/src/assets/agents/*.png`
- Modify: `frontend/src/data/agents.js`
- Modify: `backend/app/models.py`

- [ ] Crop the two supplied composite images into exactly nine individual project-local PNG assets.
- [ ] Map eight debaters and one judge to the new assets.
- [ ] Verify the frontend can import all assets.

### Task 6: Local And Public Invite Link Safety

**Files:**
- Modify only if needed: `frontend/src/pages/OnlineLobby.jsx`, `frontend/src/components/OnlineSimplePanel.jsx`, `frontend/src/pages/JoinRoom.jsx`, `frontend/src/components/JoinWizardSteps.jsx`

- [ ] Confirm existing local and public invite links still create/join normal online rooms.
- [ ] Keep training modes out of invite room creation unless deliberately started from the local solo page.
- [ ] Ensure guest join camera debugging remains available for online human rooms.

### Task 7: Verification

**Commands:**
- `python -m pytest backend/tests/test_training_rules.py backend/tests/test_user_message_scoring.py backend/tests/test_argument_bank.py backend/tests/test_training_api.py -q`
- `python -m pytest backend/tests -q`
- `npm run build --prefix frontend`
- Start the app and check homepage, free training, opening training, autonomous room, human room, and online invite creation.

