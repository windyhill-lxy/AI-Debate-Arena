# Opening Evidence Flow Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move opening evidence collection ahead of first-debater task assignment and keep the flow clean when topics/rooms are prepared.

**Architecture:** Use one focused warmup service for opening evidence collection. Debate schedule keeps a single evidence wait/confirmation node before task assignment; team discussion and later turns only depend on the argument-bank ready predicate.

**Tech Stack:** FastAPI backend, Pydantic models, pytest, YAML schedule config, Mermaid documentation.

---

### Task 1: Lock Desired Schedule And Warmup Behavior

**Files:**
- Modify: `backend/tests/test_debate_mode.py`
- Create: `backend/tests/test_opening_evidence_warmup.py`

- [ ] Write tests that assert `opening_evidence_bank` appears before `opening_task_assign` and `neg_opening_task_assign`.
- [ ] Write tests that assert stale warmup results are ignored when the persisted debate topic changes.
- [ ] Run the focused tests and confirm they fail before implementation.

### Task 2: Implement Clean Opening Evidence Warmup

**Files:**
- Create: `backend/app/services/opening_evidence_warmup.py`
- Modify: `backend/app/api/debates.py`
- Delete: `backend/app/services/online_opening_warmup.py`
- Delete: `backend/app/services/online_room_locks.py`

- [ ] Add a warmup service with per-debate task tracking, start/cancel helpers, topic snapshot validation, and minimal merge-only persistence.
- [ ] Trigger warmup from debate creation for all modes after the debate is saved.
- [ ] Stop triggering warmup from participant join and online-ready.
- [ ] Remove room-wide lock usage from participant, ready, kick, presence, message, and host-control handlers.
- [ ] Run focused warmup tests and confirm they pass.

### Task 3: Move Evidence Before Task Assignment

**Files:**
- Modify: `backend/config/schedules/formal_4v4.yaml`
- Modify: `frontend/src/data/agents.js`

- [ ] Reorder the formal schedule so `opening_evidence_bank` is before first-debater task assignment.
- [ ] Update frontend preview data to match the backend order.
- [ ] Run schedule and mode tests.

### Task 4: Flow Documentation And Verification

**Files:**
- Modify: `docs/ai-debate-project-flow.mmd`

- [ ] Replace the flow chart with a low-crossing Mermaid diagram centered on setup, evidence warmup, wait gate, team discussion, public debate, and post-match.
- [ ] Run py_compile on changed backend modules.
- [ ] Run focused pytest suites for schedule, debate mode, team discussion, user turn flow, online session flow, and integration workflow.
