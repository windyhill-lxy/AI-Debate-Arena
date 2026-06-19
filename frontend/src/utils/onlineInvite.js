export function isLoopbackHost(host) {
  if (!host) return true;
  const h = host.toLowerCase();
  return h === "localhost" || h === "127.0.0.1" || h === "[::1]";
}

export function parseJoinInput(raw) {
  const target = parseJoinTarget(raw);
  return target?.id || "";
}

export function parseJoinTarget(raw) {
  const text = (raw || "").trim();
  if (!text) return null;
  const session = text.match(/\/join\/session\/([^/?#]+)/i)?.[1];
  if (session) return { kind: "session", id: session };
  const debate = text.match(/\/(?:join|room)\/([^/?#]+)/i)?.[1];
  if (debate) return { kind: "debate", id: debate };
  return { kind: "debate", id: text };
}

export function buildSessionInviteLink(sessionId, tunnelUrl) {
  const base = resolveInviteBase(tunnelUrl);
  if (!sessionId || !base) return "";
  return `${base}/join/session/${sessionId}`;
}

export function resolveInviteBase(tunnelUrl) {
  if (typeof window === "undefined") return "";
  const tunnel = (tunnelUrl || window.__DEBATE_TUNNEL_URL__ || "").replace(/\/$/, "");
  if (tunnel) return tunnel;
  const origin = window.location.origin;
  if (!isLoopbackHost(window.location.hostname)) return origin;
  return "";
}

export function buildInviteLink(debateId, tunnelUrl) {
  const base = resolveInviteBase(tunnelUrl);
  if (!debateId || !base) return "";
  return `${base}/join/${debateId}`;
}

export function inviteStatusLabel(tunnelRunning, hostname) {
  if (tunnelRunning) return "远程可加入";
  if (!isLoopbackHost(hostname)) return "局域网可加入";
  return "待分享";
}
