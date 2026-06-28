export function requirePublicTunnelForInvite(primaryState, fallbackState = null) {
  const tunnelState = primaryState?.running && primaryState?.url ? primaryState : fallbackState;
  if (!tunnelState?.running || !tunnelState?.url) {
    throw new Error(tunnelState?.error || "公网隧道正在启动，请稍候再点击复制公网邀请链接。");
  }
  if (!tunnelState.healthy && tunnelState.error) {
    throw new Error(tunnelState.error);
  }
  return tunnelState;
}
