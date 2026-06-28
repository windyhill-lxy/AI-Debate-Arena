export function canStartQueuedAudio({ playing, disabled, paused, hasActiveAudio }) {
  if (disabled || paused) return false;
  if (playing || hasActiveAudio) return false;
  return true;
}
