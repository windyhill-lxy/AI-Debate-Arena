export function participantStorageKey(debateId) {
  return `debate-participant-${debateId}`;
}

export function loadStoredParticipant(debateId) {
  if (typeof window === "undefined" || !debateId) return null;
  try {
    const raw = window.localStorage.getItem(participantStorageKey(debateId));
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function saveStoredParticipant(debateId, participant) {
  if (typeof window === "undefined" || !debateId || !participant) return;
  window.localStorage.setItem(participantStorageKey(debateId), JSON.stringify(participant));
}
