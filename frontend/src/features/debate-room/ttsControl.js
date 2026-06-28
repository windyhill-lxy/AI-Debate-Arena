export function effectiveTtsEnabled(remoteTtsEnabled, locallyStopped = false) {
  if (locallyStopped) return false;
  return remoteTtsEnabled !== false;
}

export function shouldAcceptIncomingTts({ remoteTtsEnabled, locallyStopped, audioUrl }) {
  if (!audioUrl) return false;
  return effectiveTtsEnabled(remoteTtsEnabled, locallyStopped);
}
