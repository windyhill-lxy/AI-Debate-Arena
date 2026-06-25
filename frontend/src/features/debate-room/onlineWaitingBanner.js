export function onlineMatchHasStarted(debate) {
  return Boolean(
    (debate?.schedule_index ?? 0) > 0 ||
      (debate?.turn_index ?? 0) > 0 ||
      (debate?.messages || []).length > 0 ||
      (debate?.phase && debate.phase !== "pre_match"),
  );
}

export function shouldShowOnlineWaitingBanner(debate, connectedDebaters = 0) {
  return Boolean(
    debate?.mode === "online_match" &&
      debate.online_ready &&
      !onlineMatchHasStarted(debate) &&
      !debate.online_has_guest &&
      connectedDebaters < 2,
  );
}
