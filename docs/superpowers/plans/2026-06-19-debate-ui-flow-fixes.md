# Debate UI Flow Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the debate room display, argument bank readability, training entry placement, speaking style, Markdown rendering, sidebar labels, and LAN/public online setup flows.

**Architecture:** Keep the current FastAPI + React structure. Backend changes are limited to argument-bank metadata, tunnel provider behavior, and LLM prompt/style helpers; frontend changes reshape existing pages and components without introducing a new router or state manager.

**Tech Stack:** FastAPI, Pydantic, pytest, React, Vite, lucide-react, react-markdown.

---

### Task 1: Backend Readability And Flow Contracts

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/services/argument_bank.py`
- Modify: `backend/app/workflow/debate_graph.py`
- Test: `backend/tests/test_argument_bank.py`

- [ ] Add a `title` field to `ArgumentBankItem`.
- [ ] Generate short one-line titles from claims in `build_argument_bank_items`.
- [ ] Tighten AI speech prompts to prefer natural paragraphs, no dash separators, and fewer symbol-heavy lists.
- [ ] Run `.\tools\python\python.exe -m pytest backend\tests\test_argument_bank.py -q`.

### Task 2: Root Mode And Training Entry Placement

**Files:**
- Modify: `frontend/src/pages/Welcome.jsx`
- Modify: `frontend/src/pages/Home.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/styles/home.css`

- [ ] Move free debate training and opening training into the root mode cards.
- [ ] Remove the extra training promo area from the personal debate setup page.
- [ ] Keep `/solo`, `/training/opening`, and `/lobby` routes working.

### Task 3: Debate Room Panels

**Files:**
- Modify: `frontend/src/features/debate-room/components/DebateLeftRail.jsx`
- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- Modify: `frontend/src/pages/DebateRoom.jsx`
- Modify: `frontend/src/styles/app.css`

- [ ] Change side dock buttons to icon plus text.
- [ ] Enlarge and scroll the LangGraph workflow panel.
- [ ] Show the current participant/user seat in the debate interface.
- [ ] Render argument-bank title, ID, claim, and source clearly.

### Task 4: Online Setup Cards

**Files:**
- Modify: `frontend/src/components/OnlineSimplePanel.jsx`
- Modify: `frontend/src/components/TunnelProviderPanel.jsx`
- Modify: `frontend/src/styles/home.css`

- [ ] Rework LAN and public setup into step cards.
- [ ] Add Radmin LAN as a third card that creates a normal LAN room after the user connects through Radmin.
- [ ] Reduce extra explanatory copy and keep only setup-critical instructions.

### Task 5: Markdown And Verification

**Files:**
- Modify: `frontend/src/components/MarkdownBody.jsx`
- Modify: `frontend/src/components/CitationMarkdownBody.jsx`
- Modify: relevant display components if plain Markdown leaks remain.

- [ ] Add a shared Markdown sanitizing helper for common unrendered emphasis artifacts.
- [ ] Run focused backend tests.
- [ ] Run `npm run build`.
- [ ] Start services and verify local, LAN-shaped, and public invite routes.

