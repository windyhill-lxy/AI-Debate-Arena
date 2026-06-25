# Debate Workflow Graph And Argument Bank Root Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the debate workflow graph readable, zoomable, and free of overlap, while making opening evidence collection a hard workflow contract: both sides collect about 10 visible argument-bank items before team discussion, and each AI debater speaks once in later strategy discussion.

**Architecture:** Treat this as two connected fixes. The frontend graph must stop rendering a fake single-row chain and instead render a deterministic stage-grouped graph with explicit edges, a top-layer portal modal, and automated overlap checks. The backend must promote opening evidence retrieval from "best effort" to a workflow invariant: seed argument banks to a target count per side, broadcast the bank before discussion, and constrain team discussion prompts/tests to use the bank.

**Tech Stack:** React, @xyflow/react, dagre or manual stage layout, Playwright, FastAPI/Pydantic backend, LangGraph-compatible workflow runner, pytest.

---

## Root Cause Summary

### 1. Graph data is semantically wrong before layout starts

Current `frontend/src/features/debate-room/components/WorkflowGraph.jsx` uses `flattenWorkflow(columns)` and then creates edges with:

```js
for (let index = 0; index < flat.length - 1; index += 1) {
  graph.setEdge(flat[index].id, flat[index + 1].id);
}
```

This means every workflow node is forced into one artificial chain. Router/check/judge nodes then receive synthetic `yes`/`no` labels from `edgeLabelFor(source, index)`, even when the backend has not supplied real branch semantics. The graph therefore looks like a real decision flow while actually representing a long serial list. That produces confusing crossing/obscuring labels and makes the graph impossible to reason about.

### 2. Layout strategy guarantees a huge horizontal strip

The current dagre config uses `rankdir: "LR"` with approximately 40 workflow nodes. A left-to-right serial chain inside a right sidebar creates a graph thousands of pixels wide. The small panel then uses centering/fit logic that either shows only a sliver or shrinks the whole graph so labels become unreadable. This is why "can zoom" exists technically but the user's actual graph remains hard to use.

### 3. Large graph modal is below other UI layers

`frontend/src/styles/app.css` currently gives the graph panel container `z-index: 140`, bottom debate dock `z-index: 120`, and `.workflow-modal` only `z-index: 80`. The "large graph" can render but still sit behind the dock or right-side panel. That is a direct root cause of the perceived "大图功能失效".

### 4. The minimap and edge labels can cover content

The minimap is always rendered in `WorkflowGraphCanvas`, including the small sidebar graph. In the screenshot it occupies the lower-right content area. Edge labels are small text on long horizontal lines and can sit over nodes or be hidden by zoom. These are content collisions, not just aesthetics.

### 5. Existing tests prove controls exist, not that the graph is usable

`frontend/e2e/debate-flow.spec.js` currently checks React Flow controls/minimap visibility and a single node visibility. It does not check:

- whether the large modal is on top of the dock,
- whether graph nodes overlap each other,
- whether the minimap overlaps visible nodes,
- whether graph labels are clipped,
- whether zoom controls actually change viewport scale.

The test can pass while the screenshot remains broken.

### 6. Backend evidence workflow exists but is not contractual enough

`backend/app/services/debate_schedule.py` already has `opening_evidence_bank` before `aff_opening_discussion` and `neg_opening_discussion`, and `backend/app/workflow/debate_graph.py` has `_opening_evidence_retrieve`. However, `_opening_evidence_retrieve` calls one AI search and one local retrieval per side, then accepts whatever passes filters. There is no guarantee of about 10 items per side, no retry loop until target count, and no test that discussion cannot begin with an underfilled bank.

### 7. Team discussion has the right direction but incomplete guarantees

`_team_discussion_generate` already loops positions 1-4 and calls `chat_completion` per teammate. But opening discussion may mark first debater as already spoken after task assignment, which conflicts with the user's latest requirement: in team discussion every AI debater should speak once. The prompt mentions argument-bank IDs but tests do not assert each debater's message uses or plans around argument-bank items.

---

## Files To Modify

- Modify: `frontend/src/features/debate-room/components/WorkflowGraph.jsx`
  - Build a stage-grouped graph model with explicit deterministic edges.
  - Add compact and modal rendering modes.
  - Remove fake yes/no labels unless a real branch label exists.
  - Hide or relocate minimap in compact mode.

- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
  - Render the large graph modal through a portal attached to `document.body`.
  - Keep graph header actions but ensure modal is outside sidebar stacking contexts.

- Modify: `frontend/src/styles/app.css`
  - Raise `.workflow-modal` above dock/sidebar layers.
  - Give modal a full opaque surface and stable viewport constraints.
  - Add compact graph styling that cannot spill behind the center stage.

- Modify: `frontend/e2e/debate-flow.spec.js`
  - Add geometry assertions for modal z-order, graph node overlap, and zoom.
  - Keep existing argument bank title/content check.

- Modify: `frontend/src/data/agents.js`
  - Align local demo workflow labels with backend `workflow_template`.
  - Add optional `edges` metadata only if the component needs it for deterministic rendering.

- Modify: `frontend/src/features/debate-room/localDebate.js`
  - Seed demo argument banks with 10 affirmative and 10 negative items so the UI exercises the real density.

- Modify: `backend/app/workflow/debate_graph.py`
  - Add an `OPENING_ARGUMENT_TARGET_PER_SIDE = 10` constant.
  - Make opening retrieval repeat one or more AI calls until each side has target items or bounded attempts are exhausted.
  - Emit an event that includes full side counts after seeding.
  - Ensure opening team discussion includes every position 1-4 once.

- Modify: `backend/app/services/argument_bank.py`
  - Add a small helper for side counts and target checks if this keeps `debate_graph.py` focused.
  - Keep existing filtering, dedupe, and title generation.

- Modify: `backend/tests/test_argument_bank.py`
  - Add tests for target count helper and dedupe behavior when repeated AI batches overlap.

- Modify: `backend/tests/test_integration_workflow.py`
  - Add tests that opening evidence seeding reaches 10 per side with multiple AI calls.
  - Add tests that opening discussion publishes four messages per side and each position appears once.

---

## Task 1: Capture The Current Failure As Tests

**Files:**
- Modify: `frontend/e2e/debate-flow.spec.js`

- [ ] **Step 1: Add graph geometry helper functions**

Add these helper functions near the top of `frontend/e2e/debate-flow.spec.js`:

```js
async function visibleBoxes(locator) {
  const handles = await locator.elementHandles();
  const boxes = [];
  for (const handle of handles) {
    const box = await handle.boundingBox();
    if (box && box.width > 1 && box.height > 1) boxes.push(box);
  }
  return boxes;
}

function overlapArea(a, b) {
  const x = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const y = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  return x * y;
}

function maxOverlapRatio(boxes) {
  let max = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const area = overlapArea(boxes[i], boxes[j]);
      const smaller = Math.min(boxes[i].width * boxes[i].height, boxes[j].width * boxes[j].height);
      if (smaller > 0) max = Math.max(max, area / smaller);
    }
  }
  return max;
}
```

- [ ] **Step 2: Add failing modal z-order and overlap test**

Add this test after the existing local demo test:

```js
test("本地演示流程图大图位于最上层且节点不互相遮挡", async ({ page }) => {
  await page.goto("/room/demo");
  await page.getByTitle("LangGraph 工作流").click();
  await page.getByTitle("打开大图").click();

  const modal = page.locator(".workflow-modal");
  await expect(modal).toBeVisible();

  const modalBox = await modal.boundingBox();
  const dockBox = await page.locator(".debate-dock").boundingBox();
  expect(modalBox).toBeTruthy();
  expect(dockBox).toBeTruthy();
  expect(modalBox.y + modalBox.height).toBeGreaterThan(dockBox.y + dockBox.height - 4);

  const topElementClass = await page.evaluate(() => {
    const el = document.elementFromPoint(window.innerWidth / 2, window.innerHeight - 24);
    return el?.closest(".workflow-modal, .debate-dock")?.className || "";
  });
  expect(topElementClass).toContain("workflow-modal");

  const nodeBoxes = await visibleBoxes(page.locator(".workflow-modal .workflow-flow-node"));
  expect(nodeBoxes.length).toBeGreaterThan(20);
  expect(maxOverlapRatio(nodeBoxes)).toBeLessThan(0.02);
});
```

- [ ] **Step 3: Add failing zoom behavior test**

Add this test:

```js
test("流程图缩放按钮会改变视口比例", async ({ page }) => {
  await page.goto("/room/demo");
  await page.getByTitle("LangGraph 工作流").click();
  await page.getByTitle("打开大图").click();

  const viewport = page.locator(".workflow-modal .react-flow__viewport");
  await expect(viewport).toBeVisible();
  const before = await viewport.evaluate((el) => getComputedStyle(el).transform);

  await page.locator(".workflow-modal .react-flow__controls-zoomin").click();
  await page.waitForTimeout(250);

  const after = await viewport.evaluate((el) => getComputedStyle(el).transform);
  expect(after).not.toBe(before);
});
```

- [ ] **Step 4: Run the targeted frontend test and verify it fails now**

Run from `frontend`:

```powershell
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:5174'
$env:PLAYWRIGHT_SKIP_WEBSERVER='1'
npm run test:e2e:node -- --grep "流程图"
```

Expected before fixes: at least one failure caused by `.workflow-modal` not being the top element or node overlap exceeding the threshold.

---

## Task 2: Replace Fake Linear Graph With Stage-Grouped Layout

**Files:**
- Modify: `frontend/src/features/debate-room/components/WorkflowGraph.jsx`
- Modify: `frontend/src/data/agents.js` if local demo edge metadata is needed

- [ ] **Step 1: Remove synthetic branch labels**

In `WorkflowGraph.jsx`, replace `edgeLabelFor(source, index)` with a function that reads real edge metadata only:

```js
function edgeLabelFor(edge) {
  return edge?.label || "";
}
```

The implementation should not invent `yes`/`no` from array indexes.

- [ ] **Step 2: Add deterministic stage rows**

Replace the single dagre `rankdir: "LR"` chain with a stage-grouped model:

```js
const STAGE_LAYOUT = {
  "赛前准备": { row: 0, color: "input" },
  "立论前准备": { row: 1, color: "action" },
  "立论/驳论/总结": { row: 2, color: "llm" },
  "自由辩论前准备": { row: 3, color: "retrieval" },
  "自由辩论环节": { row: 4, color: "llm" },
  "总结陈词前准备": { row: 5, color: "action" },
  "总结陈词环节": { row: 6, color: "judge" },
  "裁判最终裁决": { row: 7, color: "judge" },
};

const COLUMN_GAP = 250;
const ROW_GAP = 152;
const LEFT_PAD = 72;
const TOP_PAD = 64;
```

Each stage row places its nodes left-to-right using the node's existing stage order. This makes the graph a readable swimlane-like process instead of one thousands-of-pixels-long row.

- [ ] **Step 3: Create explicit edges between neighboring nodes inside a stage and stage handoff edges**

Build edges as:

```js
function buildStageEdges(groupedNodes) {
  const edges = [];
  for (const group of groupedNodes) {
    for (let i = 0; i < group.nodes.length - 1; i += 1) {
      edges.push({ source: group.nodes[i].id, target: group.nodes[i + 1].id });
    }
  }
  for (let i = 0; i < groupedNodes.length - 1; i += 1) {
    const source = groupedNodes[i].nodes[groupedNodes[i].nodes.length - 1];
    const target = groupedNodes[i + 1].nodes[0];
    if (source && target) edges.push({ source: source.id, target: target.id, label: "下一阶段" });
  }
  return edges;
}
```

The exact function can be named differently, but it must encode stage semantics rather than global `flat[index] -> flat[index + 1]`.

- [ ] **Step 4: Use side-specific handle positions for row handoffs**

For nodes in the same row, use right-to-left handles. For stage handoff edges, use bottom-to-top handles or smoothstep edges with enough offset. If React Flow per-edge handle IDs are too heavy for this pass, use `type: "smoothstep"` and `pathOptions: { borderRadius: 16 }` with vertical row spacing so handoff edges travel through blank space.

- [ ] **Step 5: Keep the compact graph focused**

In compact mode, fit only the current stage plus one neighboring stage:

```js
const visibleFocusNodes = nodes.filter((node) => {
  const running = nodes.find((item) => item.data.status === "running");
  if (!running) return node.data.stage === nodes[0]?.data.stage;
  return Math.abs((node.data.row || 0) - (running.data.row || 0)) <= 1;
});
```

Use `flow.fitView({ nodes: visibleFocusNodes, padding: 0.22, maxZoom: 1 })`.

- [ ] **Step 6: Keep the modal graph complete**

In interactive/modal mode, fit all nodes with `padding: 0.12` and `maxZoom: 1.1`, and let users pan/zoom from there. The modal should not crop the graph on first open.

- [ ] **Step 7: Run frontend test and expect graph overlap failure to improve**

Run from `frontend`:

```powershell
npm run test:e2e:node -- --grep "流程图"
```

Expected after this task: the node overlap assertion passes or fails only because of modal z-order, which Task 3 fixes.

---

## Task 3: Make Large Graph A True Top-Level Modal

**Files:**
- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Render modal with React portal**

In `DebateRightRail.jsx`, import `createPortal`:

```js
import { createPortal } from "react-dom";
```

Render:

```jsx
{graphOpen &&
  createPortal(
    <WorkflowGraphModal columns={workflowColumns} topic={debate?.topic} onClose={() => setGraphOpen(false)} />,
    document.body,
  )}
```

This removes the modal from the sidebar stacking context.

- [ ] **Step 2: Raise modal above every app surface**

In `app.css`, change `.workflow-modal` to:

```css
.workflow-modal {
  position: fixed;
  inset: 12px;
  z-index: 1000;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid rgba(72, 54, 41, 0.14);
  border-radius: 16px;
  background: #fffaf2;
  box-shadow: 0 30px 90px rgba(28, 22, 18, 0.32);
}
```

The exact background can match the existing palette, but it must be opaque enough that center-stage text never bleeds through.

- [ ] **Step 3: Add modal-safe graph sizing**

Add:

```css
.workflow-modal .workflow-flow {
  height: 100%;
  min-height: 0;
  border: 0;
  border-radius: 0;
}
```

- [ ] **Step 4: Hide minimap in compact mode and keep it in modal only**

In `WorkflowGraphCanvas`, render minimap only when `interactive` is true:

```jsx
{interactive && <MiniMap pannable zoomable nodeStrokeWidth={2} />}
```

This removes the minimap collision from the small sidebar panel.

- [ ] **Step 5: Run targeted Playwright verification**

Run:

```powershell
npm run test:e2e:node -- --grep "大图|流程图"
```

Expected: modal z-order assertion passes and zoom transform changes after clicking zoom-in.

---

## Task 4: Make Argument Bank Seeding Reach The Target Count

**Files:**
- Modify: `backend/app/workflow/debate_graph.py`
- Modify: `backend/app/services/argument_bank.py`
- Modify: `backend/tests/test_argument_bank.py`
- Modify: `backend/tests/test_integration_workflow.py`

- [ ] **Step 1: Add target constants**

In `debate_graph.py`, near the top-level constants:

```python
OPENING_ARGUMENT_TARGET_PER_SIDE = 10
OPENING_ARGUMENT_MAX_AI_CALLS_PER_SIDE = 3
```

- [ ] **Step 2: Add count helper**

In `argument_bank.py`:

```python
def argument_count_for_side(debate: DebateState, side: str) -> int:
    if side not in {"affirmative", "negative"}:
        return 0
    return len(debate.argument_bank.get(side, []))
```

Import it in `debate_graph.py`.

- [ ] **Step 3: Make AI retrieval request more items per call**

Change `_search_real_evidence_with_ai` user prompt from "3 到 5 条" to "6 到 8 条". Keep JSON format. This reduces calls while still allowing multiple calls when filters remove weak items.

- [ ] **Step 4: Loop until target or bounded attempts**

In `_opening_evidence_retrieve`, for each side:

```python
attempts = 0
while argument_count_for_side(debate, side) < OPENING_ARGUMENT_TARGET_PER_SIDE and attempts < OPENING_ARGUMENT_MAX_AI_CALLS_PER_SIDE:
    attempts += 1
    ai_sources = await self._search_real_evidence_with_ai(debate, side)
    local_sources = retrieve_sources(debate.topic, query, debate_id=debate.id)
    sources = [*ai_sources, *local_sources]
    all_sources.extend(sources)
    added = add_sources_to_argument_bank_for_side(
        debate,
        side,
        sources,
        source_label="AI 检索真实论据入库",
    )
    total_added[side] += added
    if added == 0 and not ai_sources:
        break
```

The loop should avoid infinite retries and preserve dedupe/filtering.

- [ ] **Step 5: Broadcast final bank counts**

Change the emitted event payload to include:

```python
"affirmative_count": argument_count_for_side(debate, "affirmative"),
"negative_count": argument_count_for_side(debate, "negative"),
"target_per_side": OPENING_ARGUMENT_TARGET_PER_SIDE,
```

This gives the frontend a reliable signal that the bank is ready to show before team discussion.

- [ ] **Step 6: Add pytest for multiple calls to target**

In `backend/tests/test_integration_workflow.py`, add a test that monkeypatches `_search_real_evidence_with_ai` or `chat_completion` to return two batches per side and asserts each side reaches 10.

Expected assertions:

```python
assert len(result.argument_bank["affirmative"]) >= 10
assert len(result.argument_bank["negative"]) >= 10
assert result.argument_bank_locked is True
```

- [ ] **Step 7: Run backend tests**

Run:

```powershell
tools\python\python.exe -m pytest backend\tests\test_argument_bank.py backend\tests\test_integration_workflow.py -q
```

Expected: all selected tests pass.

---

## Task 5: Ensure Team Discussion Uses The Bank And Every Debater Speaks Once

**Files:**
- Modify: `backend/app/workflow/debate_graph.py`
- Modify: `backend/tests/test_integration_workflow.py`

- [ ] **Step 1: Stop skipping first debater for team discussion**

In `_team_discussion_generate`, remove or narrow this block:

```python
if _first_debater_already_assigned(debate, agent.side):
    spoken.add(1)
```

The latest requirement says each AI debater must speak once in team discussion. Task assignment is a different segment and should not count as the team-discussion turn.

- [ ] **Step 2: Include bank IDs in every teammate prompt**

In `_single_teammate_discussion_prompt`, add the side's available IDs to the system content:

```python
ids = _argument_ids_for_prompt(debate, agent.side)
```

Then include:

```python
f"本方可用论据 ID：{ids}。你的发言必须至少提到一个论据 ID，或明确说明你负责如何使用其中一组论据。"
```

- [ ] **Step 3: Add fallback messages with IDs when bank exists**

If the AI call fails and the side has bank IDs, fallback should reference the first available ID:

```python
ids = sorted(argument_ids_for_side(debate, teammate.side))
first_id = ids[0] if ids else ""
content = f"我负责把 {first_id} 接到本轮战场里，先讲事实，再讲它为什么能支撑我们的判断标准。"
```

Keep role-specific fallback text but include an ID when possible.

- [ ] **Step 4: Test every position speaks once in opening discussion**

In `backend/tests/test_integration_workflow.py`, add or strengthen assertions:

```python
added = result.messages[-4:]
assert [m.speaker_id for m in added] == ["aff_1", "aff_2", "aff_3", "aff_4"]
assert len({m.speaker_id for m in added}) == 4
assert all(m.phase == "opening_prep" for m in added)
assert all("AFF-" in m.content for m in added)
```

Mirror for the negative side using `NEG-`.

- [ ] **Step 5: Run backend workflow tests**

Run:

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_workflow.py -q
```

Expected: tests pass and prove task assignment no longer suppresses first debater's team-discussion contribution.

---

## Task 6: Make Argument Bank Visible And Dense In The UI

**Files:**
- Modify: `frontend/src/features/debate-room/localDebate.js`
- Modify: `frontend/src/features/debate-room/components/DebateRightRail.jsx`
- Modify: `frontend/src/styles/app.css`
- Modify: `frontend/e2e/debate-flow.spec.js`

- [ ] **Step 1: Seed 10 demo items per side**

In `localDebate.js`, expand `argument_bank.affirmative` and `argument_bank.negative` to 10 items each. Each item must include:

```js
{
  id: "AFF-1",
  side: "affirmative",
  title: "AI作业批改订正率提升",
  claim: "2024年某省重点中学引入 AI 作业批改系统后，学生错题订正率提升近30%。这支持正方关于即时反馈能帮助学生发现知识漏洞、提升复盘效率的论证。",
  source: "本地演示论据库",
}
```

Use distinct IDs and concise titles for all 20 items.

- [ ] **Step 2: Add side count display**

In `DebateRightRail.jsx`, change each side header to include the count:

```jsx
<h4>{side === "affirmative" ? "正方论据" : "反方论据"} <span>{items.length}</span></h4>
```

Style the count as a small badge.

- [ ] **Step 3: Update empty copy**

Replace the argument empty message with:

```jsx
{items.length === 0 && <p className="empty-note">裁判完成论据分配后，AI 会先检索并录入本方论据，再进入队内讨论。</p>}
```

- [ ] **Step 4: Add E2E density assertion**

In `frontend/e2e/debate-flow.spec.js`, extend the local demo argument-bank test:

```js
await expect(page.locator(".argument-bank-side.affirmative .argument-bank-item")).toHaveCount(10);
await expect(page.locator(".argument-bank-side.negative .argument-bank-item")).toHaveCount(10);
```

- [ ] **Step 5: Run frontend test**

Run:

```powershell
npm run test:e2e:node -- --grep "论据库"
```

Expected: local demo shows 10 items for each side and each card shows title plus content.

---

## Task 7: Final Verification

**Files:**
- No code changes unless verification finds a regression.

- [ ] **Step 1: Run backend target tests**

```powershell
tools\python\python.exe -m pytest backend\tests\test_argument_bank.py backend\tests\test_integration_workflow.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run frontend build**

```powershell
cd frontend
npm run build
```

Expected: Vite build succeeds. Existing chunk-size warnings are acceptable if unchanged.

- [ ] **Step 3: Run targeted E2E tests**

```powershell
cd frontend
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:5174'
$env:PLAYWRIGHT_SKIP_WEBSERVER='1'
npm run test:e2e:node -- --grep "流程图|论据库|大图"
```

Expected: graph overlap, modal z-order, zoom, and argument-bank tests pass.

- [ ] **Step 4: Manual screenshot inspection**

Capture two screenshots:

```powershell
node -e "const { chromium } = require('@playwright/test'); (async()=>{ const browser=await chromium.launch(); const page=await browser.newPage({viewport:{width:1280,height:720}}); await page.goto('http://127.0.0.1:5174/room/demo'); await page.getByTitle('LangGraph 工作流').click(); await page.screenshot({path:'C:/tmp/debate-workflow-compact-final.png', fullPage:false}); await page.getByTitle('打开大图').click(); await page.screenshot({path:'C:/tmp/debate-workflow-modal-final.png', fullPage:false}); await page.getByTitle('论据库').click(); await page.screenshot({path:'C:/tmp/debate-arguments-final.png', fullPage:false}); await browser.close(); })();"
```

Expected: compact graph is readable and not hidden behind other panels; modal covers the dock; nodes do not overlap; argument bank shows titles and content.

---

## Acceptance Criteria

- The workflow graph no longer uses synthetic global sequential edges as its only structure.
- Graph compact view is readable and focused on the current stage.
- Graph large view opens above the dock/sidebar and supports visible zoom/pan.
- Automated Playwright tests assert modal z-order, zoom transform changes, and node overlap ratio.
- The argument bank is filled before opening team discussion.
- Each side has at least 10 opening argument-bank items when enough evidence is returned.
- Both affirmative and negative discussion steps call each AI debater separately and publish four internal messages per side.
- Team discussion focuses on using argument IDs and strategy instead of collecting evidence.
- Argument bank UI displays count, concise title, full claim/content, and source.

