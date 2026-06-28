import assert from "node:assert/strict";
import { TUNNEL_START_TIMEOUT_MS, normalizeTunnelFetchError } from "./publicTunnelClient.js";

const abort = new DOMException("signal is aborted without reason", "AbortError");
const normalized = normalizeTunnelFetchError(abort, "start");

assert.equal(normalized.name, "ApiError");
assert.match(normalized.message, /公网隧道启动超时/);
assert.match(String(normalized.details), /ngrok|Cloudflare/);
assert.notEqual(normalized.message, "signal is aborted without reason");
assert.ok(TUNNEL_START_TIMEOUT_MS >= 70000, "start timeout should cover ngrok plus Cloudflare fallback");
