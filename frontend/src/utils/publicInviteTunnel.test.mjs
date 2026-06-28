import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { requirePublicTunnelForInvite } from "./publicInviteTunnel.js";

const startedState = {
  running: true,
  url: "https://demo.trycloudflare.com",
  provider: "cloudflare-quick",
  healthy: false,
  error: null,
};

assert.equal(requirePublicTunnelForInvite(null, startedState), startedState);
assert.equal(requirePublicTunnelForInvite({ ...startedState, healthy: true }, startedState).healthy, true);
assert.throws(
  () => requirePublicTunnelForInvite(null, { running: false, url: null, error: null }),
  /正在启动/,
);
assert.throws(
  () => requirePublicTunnelForInvite({ ...startedState, error: "公网地址暂未响应" }, startedState),
  /公网地址暂未响应/,
);

const onlineSimplePanel = readFileSync(resolve(import.meta.dirname, "../components/OnlineSimplePanel.jsx"), "utf8");
assert.match(onlineSimplePanel, /requirePublicTunnelForInvite/);
assert.doesNotMatch(onlineSimplePanel, /function assertPublicTunnelReady/);
