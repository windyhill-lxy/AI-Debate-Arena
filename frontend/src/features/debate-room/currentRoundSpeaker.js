export function resolveCurrentRoundSpeaker(debate = {}, activeAgent = null) {
  const agents = debate.agents || [];
  const activeId = debate.active_speaker_id;
  if (activeId) {
    const exact = agents.find((agent) => agent.id === activeId);
    if (exact) return exact;
  }
  if (activeAgent?.id) return activeAgent;
  return agents.find((agent) => agent.side === "judge") || null;
}
