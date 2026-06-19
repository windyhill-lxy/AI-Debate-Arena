export function hostTokenStorageKey(debateId) {
  return `debate-host-token-${debateId}`;
}

export function saveHostToken(debateId, token) {
  if (typeof window === "undefined" || !debateId || !token) return;
  window.localStorage.setItem(hostTokenStorageKey(debateId), token);
}

export function loadHostToken(debateId) {
  if (typeof window === "undefined" || !debateId) return "";
  return window.localStorage.getItem(hostTokenStorageKey(debateId)) || "";
}

export function hostTokenHeaders(debateId) {
  const token = loadHostToken(debateId);
  return token ? { "X-Host-Token": token } : {};
}
