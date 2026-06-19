/** 房间可见性：创建前选择，开赛后锁定。 */

export const VISIBILITY_MODES = [
  {
    id: "all_visible",
    label: "全部可见",
    shortLabel: "全部",
    hint: "显示双方队内讨论、AI 策略与全部复盘信息，适合 AI 自主辩论和赛后训练。",
  },
  {
    id: "own_side_only",
    label: "仅己方可见",
    shortLabel: "己方",
    hint: "仅显示公开内容与本方队内讨论，适合人类训练和正式联机。",
  },
];

export function visibilityMode(id) {
  return VISIBILITY_MODES.find((mode) => mode.id === id) || VISIBILITY_MODES[0];
}

export function buildViewerQuery({ viewerSide, participantId, viewerMode } = {}) {
  const params = new URLSearchParams();
  if (viewerSide) params.set("viewer_side", viewerSide);
  if (participantId) params.set("participant_id", participantId);
  if (viewerMode) params.set("viewer_mode", viewerMode);
  const query = params.toString();
  return query ? `?${query}` : "";
}
