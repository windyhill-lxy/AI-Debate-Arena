export function connectedOnlineDebaterCount(debate) {
  if (typeof debate?.online_connected_debaters === "number") {
    return debate.online_connected_debaters;
  }
  return (debate?.participants || []).filter(
    (p) => p.connected && ["affirmative", "negative"].includes(p.side) && p.position >= 1 && p.position <= 4,
  ).length;
}

export function onlineRoomCanAutoStart(debate) {
  if (debate?.mode !== "online_match") return true;
  return Boolean(debate.online_ready && connectedOnlineDebaterCount(debate) >= 2);
}

export function canResumeDebate({ debate, awaitingUser, speechInputState, isLocal }) {
  if (isLocal || debate?.phase === "finished" || debate?.auto_running) return false;
  if (debate?.mode === "online_match" && !onlineRoomCanAutoStart(debate)) return false;
  if (awaitingUser && speechInputState?.canSubmit) return false;
  return !awaitingUser || Boolean(speechInputState && !speechInputState.canSubmit);
}
