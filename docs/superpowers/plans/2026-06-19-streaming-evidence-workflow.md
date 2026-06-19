# Streaming Evidence Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix opening-training streaming, replace the hand-drawn workflow map with a real interactive flow renderer, and make the argument bank accept only factual evidence.

**Architecture:** Backend evidence ingestion will use a strict factual gate before adding any item to the argument bank. Opening training will expose writer and reviewer as separate streamed phases. The frontend will render graph data through React Flow with Dagre layout instead of absolute-position SVG nodes.

**Tech Stack:** FastAPI, pytest, React, Vite, React Flow, Dagre, Playwright-compatible DOM behavior.

---

### Task 1: Opening Training Streaming

**Files:**
- Modify: `backend/app/services/training.py`
- Modify: `backend/tests/test_training_api.py`
- Modify: `frontend/src/pages/OpeningTraining.jsx`
- Modify: `frontend/src/styles/home.css`

- [x] Add a failing backend test that expects `review_delta` events between `review_start` and `review`.
- [x] Implement streamed review generation in `training.py`.
- [x] Ensure event order is `draft_start`, `draft_delta`, `draft`, `review_start`, `review_delta`, `review`, then next round.
- [x] Change the frontend stream reader to render `review_delta` into the current reviewer message immediately.
- [x] Add a small client-side queue so large chunks still appear progressively.
- [x] Run `pytest backend/tests/test_training_api.py -q`.

### Task 2: Factual Evidence Gate

**Files:**
- Modify: `backend/app/services/argument_bank.py`
- Modify: `backend/tests/test_argument_bank.py`
- Modify: `backend/tests/test_integration_workflow.py`

- [x] Add failing tests proving role assignments, tactics, pure opinions, and empty "specific evidence" phrases do not enter the argument bank.
- [x] Add tests proving concrete facts with years, numbers, organizations, policies, reports, or named cases enter the correct side.
- [x] Implement an `EvidenceCandidate` style internal classifier without changing public API unless needed.
- [x] Split formal evidence from rejected candidates.
- [x] Keep RAG factual sources entering the bank, but keep unsupported AI invented facts out unless they contain verifiable markers.
- [x] Run argument-bank and workflow tests.

### Task 3: React Flow Workflow Graph

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json` if npm creates it
- Create: `frontend/src/features/debate-room/components/WorkflowGraph.jsx`
- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- Modify: `frontend/src/styles/app.css`

- [x] Install `@xyflow/react` and `dagre`.
- [x] Replace `WorkflowMindMap` with a React Flow graph using Dagre top-to-bottom layout.
- [x] Use custom node classes for start, action, retrieval, llm, judge, and terminal nodes.
- [x] Support mouse wheel zoom, drag pan, controls, fit view, minimap, and export.
- [x] Remove the old hand-drawn absolute-position node CSS from active use.
- [x] Run frontend build.

### Task 4: Verification and Commit

**Files:**
- Check all changed files with `git diff --stat`.

- [x] Run backend target tests.
- [x] Run frontend build.
- [x] Restart backend if needed.
- [x] Check health endpoint.
- [x] Commit only project code and plan files, excluding runtime conversation logs.
