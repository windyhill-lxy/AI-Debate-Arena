# Error Popup And Workflow Reliability Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every user-visible failure surface through a consistent error popup, remove silent error swallowing from critical paths, and fix/verify WebSocket workflow streaming reliability while preserving the workflow graph and argument-bank fixes.

**Architecture:** Add a frontend error notification layer mounted above all routes, standardize backend/frontend API error envelopes with request IDs, then route HTTP, WebSocket, SSE, media, and background-job failures through one deduped popup center. Treat noisy background failures as errors too, but show them through throttled modal/toast entries rather than raw `alert()` spam.

**Tech Stack:** React, Vite, FastAPI, Starlette middleware/exception handlers, pytest, Playwright.

---

## Current Audit Findings

### Finding 1: Most frontend errors do not show a popup

Severity: P1

Evidence:
- `frontend/src/main.jsx` only renders `<App />`; no global error provider or boundary is mounted.
- `frontend/src/App.jsx` wraps routes with `BrowserRouter` and `TunnelGuestGuard`, but no global dialog/toast layer exists.
- `frontend/src/features/debate-room/hooks/useDebateRoom.js` writes failures into local status text at resume, message submit, ASR, material upload, draft generation, and TTS stop paths.
- `frontend/src/pages/Admin.jsx`, `frontend/src/pages/OpeningTraining.jsx`, `frontend/src/components/RuntimeSettingsPanel.jsx`, `frontend/src/components/OnlineSimplePanel.jsx`, and tunnel/network panels follow the same local-hint pattern.

Impact: The user's requirement "所有报错都要有报错窗口弹出" is not met. Many failures can be missed because they appear only in small inline text, status bars, or not at all.

### Finding 2: Critical async paths silently swallow failures

Severity: P1

Evidence:
- `frontend/src/hooks/useDebateSocket.js` ignores snapshot sync failure and malformed WebSocket payloads.
- `frontend/src/features/debate-room/hooks/useDebateRoom.js` ignores malformed SSE frames and transient remote polling errors.
- `frontend/src/features/debate-room/hooks/useDebateRoom.js` falls back to canned assist text when streaming assist fails, without surfacing the real error.
- Several polling/setup paths in `Home.jsx`, `GuestJoinFlow.jsx`, `TunnelProviderPanel.jsx`, and `OnlineNetworkDiag.jsx` use empty `catch` blocks.

Impact: Real backend, WebSocket, SSE, and parsing errors can disappear completely. This makes both debugging and user recovery unreliable.

### Finding 3: Backend errors are not standardized for frontend popups

Severity: P1

Evidence:
- `backend/app/main.py` mounts middleware and routers but has no global `HTTPException`, validation, or generic exception handlers.
- `backend/app/core/middleware_request_id.py` adds `X-Request-ID`, but response bodies do not consistently include the request ID.
- `frontend/src/features/debate-room/api.js` only parses FastAPI's `detail` field and throws a plain `Error`, losing status, request ID, code, and raw payload.

Impact: Even if the frontend adds a popup, it cannot consistently show actionable messages such as "HTTP 429", request ID, backend code, or validation details.

### Finding 4: WebSocket speech streaming regression is present

Severity: P1

Evidence:
- Command run on 2026-06-21 08:01 +08:00:

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_websocket.py -q
```

Result:

```text
FAILED backend\tests\test_integration_websocket.py::test_websocket_speech_stream_events
AssertionError: {'speech_start', 'speech_chunk', 'speech_end'} was not a subset of {'debate_stepped'}
1 failed, 5 passed
```

Impact: The test expects live `speech_start`, `speech_chunk`, and `speech_end` events, but the client only received `debate_stepped`. This can break the frontend's live streaming display.

### Finding 5: Some integration tests hang or run too long

Severity: P2

Evidence:
- Combined backend command with `test_integration_api.py` and `test_integration_websocket.py` exceeded 90 seconds and had to be stopped.
- `backend/tests/test_integration_api.py -q` showed 6 passing dots then continued beyond 80 seconds and had to be stopped.
- `backend/tests/test_integration_api.py --collect-only -q` collected 15 tests quickly, so the hang is runtime behavior, not collection.

Impact: The suite is not a reliable regression gate. A long-running API test may hide deadlocks, background runner leakage, or missing timeout controls.

### Finding 6: Workflow graph and argument-bank changes are partially verified, but should stay in regression coverage

Severity: P2

Evidence:
- `npm run build` in `frontend` passes, with only Vite chunk-size warnings.
- `tools\python\python.exe -m pytest backend\tests\test_argument_bank.py backend\tests\test_integration_workflow.py -q` passes: 20 passed.
- Existing E2E includes workflow graph overlap/zoom and argument-bank title/content checks.

Impact: The prior graph and argument-bank fixes appear healthy in targeted tests, but they should remain part of the final verification because the user has repeatedly reported graph overlap and broken large view.

---

## Root Cause Summary

The root cause is not a single missing `alert()`. The project has no cross-cutting error presentation contract. Each page and hook owns its own failure text, while background paths often suppress errors to avoid noisy UI. The backend also returns mixed default FastAPI errors without a stable envelope. A correct fix needs a global error center with severity, source, request ID, dedupe, and throttling, then every existing catch path must report into it.

The WebSocket streaming issue is a separate reliability bug. Backend code emits `speech_*` events during `debate_graph.run_turn_streaming`, and `/api/debates/{id}/step` passes an `on_event` broadcaster, but the failing test only receives `debate_stepped`. The implementation task must reproduce that test and trace whether the active segment is non-streaming, the event broadcaster is filtering/sending too late, or the sync TestClient request/WS receive ordering is losing events.

---

## Files To Modify

- Create: `frontend/src/components/ErrorDialogProvider.jsx`
  - Own global error queue, modal dialog, dedupe/throttle logic, and `useErrorDialog()`.

- Modify: `frontend/src/main.jsx`
  - Mount `ErrorDialogProvider` and a React error boundary above `<App />`.

- Modify: `frontend/src/App.jsx`
  - Keep routing unchanged, but ensure global provider is outside route pages.

- Modify: `frontend/src/features/debate-room/api.js`
  - Add `ApiError`, richer `parseApiError`, and optional notification metadata.

- Modify: `frontend/src/utils/apiBase.js` or create `frontend/src/utils/httpError.js`
  - Centralize request ID/status/body parsing for non-debate API calls.

- Modify: `frontend/src/hooks/useDebateSocket.js`
  - Report WebSocket connection errors, malformed payloads, and snapshot sync failures through the global error center with throttling.

- Modify: `frontend/src/features/debate-room/hooks/useDebateRoom.js`
  - Convert resume, submit, ASR, material upload, SSE assist/draft, polling, and TTS-stop failures to popup + inline status.

- Modify: `frontend/src/pages/Home.jsx`
  - Replace `alert()` and local-only hints with the global popup API.

- Modify: `frontend/src/pages/Admin.jsx`
  - Report load/save/reset/action failures via popup.

- Modify: `frontend/src/pages/OpeningTraining.jsx`
  - Report analyze/polish/AI-loop stream failures via popup.

- Modify: `frontend/src/components/RuntimeSettingsPanel.jsx`
  - Report load/save failures via popup.

- Modify: `frontend/src/components/OnlineSimplePanel.jsx`
  - Report public-link, room-create, and copy failures via popup.

- Modify: `frontend/src/components/TunnelProviderPanel.jsx`
  - Report provider/token save failures via popup.

- Modify: `frontend/src/components/OnlineNetworkDiag.jsx`
  - Report diagnostics/proxy-save failures via popup.

- Modify: `frontend/src/components/CopyShareLinkButton.jsx`
  - Report clipboard failure via popup while preserving inline fallback text.

- Modify: `frontend/src/components/ConfidenceCameraPreview.jsx`
  - Report camera open/status errors through a deduped background error channel.

- Modify: `frontend/src/hooks/useLocalCamera.js`
  - Either return typed camera errors for callers to show, or accept an optional reporter callback.

- Create: `backend/app/core/error_handlers.py`
  - Add structured JSON error responses for HTTPException, validation errors, and unexpected exceptions.

- Modify: `backend/app/main.py`
  - Register global exception handlers.

- Modify: `backend/app/services/auto_runner.py`
  - Include stable error codes/source in broadcast `error` events.

- Modify: `backend/app/services/realtime.py`
  - Consider broadcasting structured connection failure metadata where appropriate, while avoiding leaking sensitive internals.

- Modify: `backend/app/api/debates.py`
  - Keep HTTPException messages, but allow global handlers to wrap them consistently.

- Modify: `backend/tests/test_integration_websocket.py`
  - Keep failing stream event test and add root-cause regression once fixed.

- Modify: `backend/tests/test_integration_api.py`
  - Add timeouts or isolate the hanging case after identifying it.

- Modify: `frontend/e2e/debate-flow.spec.js`
  - Add popup assertions for HTTP failure, WebSocket error event, SSE error event, and unhandled frontend error.

---

## Task 1: Build A Global Error Dialog Layer

**Files:**
- Create: `frontend/src/components/ErrorDialogProvider.jsx`
- Modify: `frontend/src/main.jsx`
- Modify: `frontend/src/styles/app.css`

- [ ] **Step 1: Create the provider and hook**

Create `frontend/src/components/ErrorDialogProvider.jsx`:

```jsx
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

const ErrorDialogContext = createContext(null);

function normalizeError(input, fallback = "发生错误，请稍后重试") {
  if (!input) return { message: fallback };
  if (typeof input === "string") return { message: input };
  return {
    title: input.title || "操作失败",
    message: input.message || input.detail || fallback,
    details: input.details || input.stack || "",
    source: input.source || "",
    code: input.code || input.status || "",
    requestId: input.requestId || input.request_id || "",
    severity: input.severity || "error",
  };
}

export function ErrorDialogProvider({ children }) {
  const [items, setItems] = useState([]);
  const recentRef = useRef(new Map());

  const reportError = useCallback((input, options = {}) => {
    const error = normalizeError(input, options.fallback);
    const dedupeKey = options.dedupeKey || `${error.source}:${error.code}:${error.message}`;
    const now = Date.now();
    const throttleMs = options.throttleMs ?? 3000;
    const last = recentRef.current.get(dedupeKey) || 0;
    if (now - last < throttleMs) return;
    recentRef.current.set(dedupeKey, now);
    setItems((current) => [...current, { ...error, id: `${now}-${Math.random().toString(16).slice(2)}` }]);
  }, []);

  const dismiss = useCallback((id) => {
    setItems((current) => current.filter((item) => item.id !== id));
  }, []);

  const value = useMemo(() => ({ reportError }), [reportError]);
  const active = items[0];

  useEffect(() => {
    const onError = (event) => {
      reportError({
        title: "页面运行错误",
        message: event.message || "页面脚本执行失败",
        details: event.error?.stack || "",
        source: "window.onerror",
      }, { dedupeKey: `window:${event.message}` });
    };
    const onUnhandledRejection = (event) => {
      const reason = event.reason;
      reportError({
        title: "异步任务失败",
        message: reason?.message || String(reason || "未处理的异步错误"),
        details: reason?.stack || "",
        source: "unhandledrejection",
      }, { dedupeKey: `promise:${reason?.message || reason}` });
    };
    window.addEventListener("error", onError);
    window.addEventListener("unhandledrejection", onUnhandledRejection);
    return () => {
      window.removeEventListener("error", onError);
      window.removeEventListener("unhandledrejection", onUnhandledRejection);
    };
  }, [reportError]);

  return (
    <ErrorDialogContext.Provider value={value}>
      {children}
      {active && (
        <div className="error-dialog-backdrop" role="presentation">
          <section className="error-dialog" role="alertdialog" aria-modal="true" aria-label={active.title || "错误提示"}>
            <header>
              <strong>{active.title || "操作失败"}</strong>
              <button type="button" onClick={() => dismiss(active.id)} aria-label="关闭错误提示">×</button>
            </header>
            <p>{active.message}</p>
            {(active.code || active.requestId || active.source) && (
              <small>
                {active.code ? `代码：${active.code} ` : ""}
                {active.requestId ? `请求ID：${active.requestId} ` : ""}
                {active.source ? `来源：${active.source}` : ""}
              </small>
            )}
            {active.details && <pre>{active.details}</pre>}
          </section>
        </div>
      )}
    </ErrorDialogContext.Provider>
  );
}

export function useErrorDialog() {
  const context = useContext(ErrorDialogContext);
  if (!context) {
    return { reportError: () => undefined };
  }
  return context;
}
```

- [ ] **Step 2: Mount the provider**

Modify `frontend/src/main.jsx`:

```jsx
import { ErrorDialogProvider } from "./components/ErrorDialogProvider.jsx";
```

Wrap the app:

```jsx
createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ErrorDialogProvider>
      <App />
    </ErrorDialogProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 3: Add dialog styles**

Add to `frontend/src/styles/app.css`:

```css
.error-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(24, 20, 18, 0.28);
}

.error-dialog {
  width: min(560px, 100%);
  max-height: min(80vh, 620px);
  overflow: auto;
  border: 1px solid rgba(142, 45, 45, 0.22);
  border-radius: 10px;
  background: #fffaf7;
  box-shadow: 0 24px 80px rgba(26, 18, 14, 0.28);
  padding: 18px;
  color: #2f2420;
}

.error-dialog header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.error-dialog button {
  width: 32px;
  height: 32px;
  border: 1px solid rgba(86, 62, 48, 0.18);
  border-radius: 999px;
  background: #fff;
  cursor: pointer;
}

.error-dialog pre {
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow: auto;
  padding: 10px;
  border-radius: 8px;
  background: rgba(42, 30, 23, 0.06);
}
```

- [ ] **Step 4: Add a minimal Playwright check**

Add a test that triggers `window.dispatchEvent(new ErrorEvent("error", ...))` and asserts `role="alertdialog"` is visible.

---

## Task 2: Standardize Backend Error Responses

**Files:**
- Create: `backend/app/core/error_handlers.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_integration_api.py`

- [ ] **Step 1: Add structured handlers**

Create `backend/app/core/error_handlers.py`:

```python
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "") or request.headers.get("x-request-id", ""))


def _payload(*, message: str, code: str, request: Request, status_code: int, details=None) -> dict:
    return {
        "error": {
            "message": message,
            "code": code,
            "status": status_code,
            "request_id": _request_id(request),
            "details": details,
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "请求失败"
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(message=message, code="http_error", request=request, status_code=exc.status_code, details=exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_payload(message="请求参数无效", code="validation_error", request=request, status_code=422, details=exc.errors()),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("unhandled request error rid=%s", _request_id(request))
        return JSONResponse(
            status_code=500,
            content=_payload(message="服务器内部错误，请查看日志", code="internal_error", request=request, status_code=500),
        )
```

- [ ] **Step 2: Register handlers**

Modify `backend/app/main.py`:

```python
from app.core.error_handlers import register_error_handlers
```

After creating `app` and before routers:

```python
register_error_handlers(app)
```

- [ ] **Step 3: Test error envelope**

Add tests:

```python
@pytest.mark.asyncio
async def test_http_error_has_popup_ready_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/debates/not-found")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["message"] == "Debate not found"
    assert data["error"]["status"] == 404
    assert data["error"]["request_id"]
```

Run:

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_http_error_has_popup_ready_envelope -q
```

---

## Task 3: Add Rich Frontend API Errors

**Files:**
- Modify: `frontend/src/features/debate-room/api.js`
- Create or modify: `frontend/src/utils/httpError.js`

- [ ] **Step 1: Add `ApiError`**

```js
export class ApiError extends Error {
  constructor(message, meta = {}) {
    super(message);
    this.name = "ApiError";
    this.status = meta.status;
    this.code = meta.code;
    this.requestId = meta.requestId;
    this.details = meta.details;
    this.raw = meta.raw;
  }
}
```

- [ ] **Step 2: Parse both old and new envelopes**

```js
export function parseApiErrorBody(text, response) {
  const fallback = "请求失败，请稍后重试";
  if (!text) {
    return new ApiError(fallback, { status: response?.status, requestId: response?.headers?.get("x-request-id") });
  }
  try {
    const data = JSON.parse(text);
    if (data?.error) {
      return new ApiError(data.error.message || fallback, {
        status: data.error.status || response?.status,
        code: data.error.code,
        requestId: data.error.request_id || response?.headers?.get("x-request-id"),
        details: data.error.details,
        raw: data,
      });
    }
    if (typeof data?.detail === "string") {
      return new ApiError(ERROR_HINTS[data.detail] || data.detail, {
        status: response?.status,
        requestId: response?.headers?.get("x-request-id"),
        raw: data,
      });
    }
    if (Array.isArray(data?.detail)) {
      return new ApiError(data.detail.map((item) => item?.msg || String(item)).join("；"), {
        status: response?.status,
        requestId: response?.headers?.get("x-request-id"),
        details: data.detail,
        raw: data,
      });
    }
  } catch {
    // Keep plain-text backend failures readable.
  }
  const message = text.trim().length > 200 ? `${text.trim().slice(0, 200)}…` : text.trim();
  return new ApiError(message || fallback, { status: response?.status, requestId: response?.headers?.get("x-request-id"), raw: text });
}
```

- [ ] **Step 3: Throw `ApiError` from `debateRequest`**

```js
if (!response.ok) throw parseApiErrorBody(await response.text(), response);
```

---

## Task 4: Wire Popups Into User-Action Failures

**Files:**
- Modify the frontend pages/components listed above.

- [ ] **Step 1: Add a helper pattern**

In each component with catches:

```jsx
const { reportError } = useErrorDialog();
```

Then in a catch:

```jsx
catch (error) {
  const message = error.message || "操作失败";
  setHint(`保存失败：${message}`);
  reportError({
    title: "保存失败",
    message,
    code: error.code || error.status,
    requestId: error.requestId,
    details: error.details,
    source: "RuntimeSettingsPanel.save",
  });
}
```

- [ ] **Step 2: Replace `alert()` in `Home.jsx`**

Current create-room failure uses `alert(...)`. Replace with:

```jsx
reportError({
  title: "创建房间失败",
  message: error.message || "请确认后端已启动并填写 API Key",
  code: error.code || error.status,
  requestId: error.requestId,
  details: error.details,
  source: "Home.createDebate",
});
```

Keep `setLoading(false)`.

- [ ] **Step 3: Preserve inline status as secondary feedback**

Do not delete `setHint`, `setStatus`, `setSpeechStatus`, or `setMaterialStatus`. The popup is required, but inline status still helps users understand local context after dismissing the dialog.

- [ ] **Step 4: Add E2E for failed room creation**

Mock `/api/debates` to return 500 and assert:

```js
await expect(page.getByRole("alertdialog")).toContainText("创建房间失败");
await expect(page.getByRole("alertdialog")).toContainText("服务器内部错误");
```

---

## Task 5: Wire Popups Into Background And Streaming Failures

**Files:**
- Modify: `frontend/src/hooks/useDebateSocket.js`
- Modify: `frontend/src/features/debate-room/hooks/useDebateRoomSocket.js`
- Modify: `frontend/src/features/debate-room/hooks/useDebateRoom.js`

- [ ] **Step 1: Pass an error reporter into socket hooks**

Extend `useDebateRoomSocket` args with `reportError`, store it in `handlers.current`, and pass it into `useDebateSocket` handlers.

- [ ] **Step 2: Report WebSocket connection errors**

In `socket.onerror`:

```js
handlersRef.current.onTransportError?.({
  title: "WebSocket 连接异常",
  message: "实时连接异常，系统将尝试自动重连。",
  source: "useDebateSocket.onerror",
  code: "websocket_error",
});
```

Use `throttleMs: 10000` in the reporter call.

- [ ] **Step 3: Report malformed WebSocket payloads**

Replace empty `catch` around `JSON.parse` with:

```js
catch (error) {
  handlersRef.current.onTransportError?.({
    title: "实时消息解析失败",
    message: "收到无法解析的实时消息，已跳过本条。",
    details: error.message,
    source: "useDebateSocket.onmessage",
    code: "websocket_payload_parse",
  });
}
```

- [ ] **Step 4: Report backend `error` events**

In `useDebateRoomSocket.onError`, after setting status:

```js
h.reportError?.({
  title: "辩论回合异常",
  message: msg,
  source: "debate.websocket.error",
  code: data.code || "debate_turn_error",
  requestId: data.request_id,
});
```

- [ ] **Step 5: Report SSE frame and event errors**

Change `streamSseJson` to accept `onMalformedFrame`, call it when JSON parse fails, and report SSE `event.type === "error"` through popup in assist/draft/training flows.

- [ ] **Step 6: Use throttling for polling**

Remote snapshot polling failures should call:

```js
reportError(error, {
  dedupeKey: `remote-poll:${routeId}`,
  throttleMs: 15000,
  fallback: "同步房间状态失败，正在重试。",
});
```

This satisfies "所有报错弹窗" without opening dozens of identical dialogs per minute.

---

## Task 6: Fix WebSocket Speech Stream Regression

**Files:**
- Modify: `backend/tests/test_integration_websocket.py`
- Modify as needed: `backend/app/api/debates.py`, `backend/app/services/realtime.py`, `backend/app/workflow/debate_graph.py`

- [ ] **Step 1: Reproduce the failing test**

Run:

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_websocket.py::test_websocket_speech_stream_events -q -vv
```

Expected current result: fail because only `debate_stepped` is received.

- [ ] **Step 2: Instrument the test locally**

Temporarily print the debate state immediately before the final step:

```python
doc = sync_client.get(f"/api/debates/{debate_id}").json()
print(doc["phase"], doc["segment_label"], doc["active_speaker_id"])
```

If the active segment is procedural or still in evidence/team preparation, adjust `_advance_to_speaker_turn` to wait for a true public speech segment, not merely any `aff_`/`neg_` speaker.

- [ ] **Step 3: Verify backend emits before final broadcast**

Add a temporary `on_event` spy in a unit/integration test around `debate_graph.run_turn_streaming`:

```python
events = []

async def on_event(evt):
    events.append(evt.get("type") or evt.get("event"))

await debate_graph.run_turn_streaming(debate, on_event=on_event)
assert {"speech_start", "speech_chunk", "speech_end"}.issubset(set(events))
```

If this passes, the issue is broadcast/test-client timing or filtering. If it fails, the issue is workflow segment routing.

- [ ] **Step 4: Fix the identified cause**

Likely fixes:
- If `_advance_to_speaker_turn` stops too early, require `phase` not in preparation phases and `segment_label` not containing `队内讨论`, `真实论据入库`, or `任务分配`.
- If broadcast filtering drops stream events, inspect `streaming_event_visible` and connection metadata defaults.
- If TestClient ordering loses events because `sync_client.post` blocks until after `/step`, adjust test to receive while the request is running in a background thread, or change endpoint/broadcast manager to buffer recent `speech_*` events until `debate_stepped`.

- [ ] **Step 5: Keep the regression test**

Do not weaken `test_websocket_speech_stream_events`. It protects the exact frontend behavior the user sees.

---

## Task 7: Diagnose Hanging API Integration Tests

**Files:**
- Modify: `backend/tests/test_integration_api.py`
- Modify implementation only after identifying the hanging test.

- [ ] **Step 1: Run tests one by one**

Use the collected test names:

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_health -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_create_and_get_debate -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_create_debate_materials_immediately_populate_argument_bank -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_create_user_affirmative_mode -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_create_user_mode_renames_configured_seat_only -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_user_mode_message_then_resume -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_user_message_uses_configured_debater_seat -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_public_low_information_user_message_triggers_judge_warning -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_internal_low_information_user_message_triggers_teammate_reminder -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_user_can_post_once_during_team_discussion_segment -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_get_debate_filters_opponent_internal_discussion -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_admin_overview_and_list -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_admin_detail_and_resume_controls -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_export_markdown -q
tools\python\python.exe -m pytest backend\tests\test_integration_api.py::test_confidence_monitor_status_and_toggle -q
```

- [ ] **Step 2: Add per-test timeout if supported**

If `pytest-timeout` is available, add a timeout marker to the hanging test. If not, keep the test focused and remove unbounded polling/waits from the implementation or fixture.

- [ ] **Step 3: Check background runner cleanup**

If the hang happens after tests finish but before process exit, inspect fixtures in `backend/tests/conftest.py` and background tasks from `auto_runner`, `presence`, confidence monitor, and WebSocket manager. Ensure tests stop auto runners and pending tasks.

---

## Task 8: Final Regression Verification

**Files:**
- No new implementation unless a verification step fails.

- [ ] **Step 1: Backend targeted tests**

```powershell
tools\python\python.exe -m pytest backend\tests\test_argument_bank.py backend\tests\test_integration_workflow.py -q
```

Expected: pass.

- [ ] **Step 2: WebSocket regression**

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_websocket.py -q
```

Expected: pass, including `test_websocket_speech_stream_events`.

- [ ] **Step 3: API integration**

```powershell
tools\python\python.exe -m pytest backend\tests\test_integration_api.py -q
```

Expected: pass without hanging.

- [ ] **Step 4: Frontend build**

```powershell
cd frontend
npm run build
```

Expected: build succeeds. Existing chunk-size warning can remain.

- [ ] **Step 5: Error popup E2E**

```powershell
cd frontend
npm run test:e2e:node -- --grep "错误弹窗|error dialog|创建房间失败|WebSocket"
```

Expected: HTTP failures, WebSocket error events, SSE failures, and unhandled frontend errors all show `role="alertdialog"`.

- [ ] **Step 6: Workflow graph and argument bank E2E**

```powershell
cd frontend
npm run test:e2e:node -- --grep "流程图|论据库|大图"
```

Expected: graph modal is top-layer, nodes do not overlap, zoom controls change transform, and argument bank displays title plus content for both sides.

---

## Acceptance Criteria

- Every user-action failure shows a popup and keeps useful inline status where it already exists.
- Background, polling, WebSocket, SSE, media, and unhandled JS errors also report to the global error center with dedupe/throttle.
- No critical path uses empty `catch` without either a popup report or a documented non-error reason.
- Backend HTTP errors return a stable `{ error: { message, code, status, request_id, details } }` envelope.
- Frontend API errors preserve status, code, request ID, details, and raw message for the popup.
- WebSocket `speech_start`, `speech_chunk`, and `speech_end` events are received by the integration test.
- `backend/tests/test_integration_api.py` finishes without hanging.
- Prior workflow graph and argument-bank regressions remain covered by E2E tests.
