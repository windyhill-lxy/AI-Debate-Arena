import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import FloatingConfidenceCamera from "../components/FloatingConfidenceCamera.jsx";
import FloatingOnlineCamera from "../components/FloatingOnlineCamera.jsx";
import { useOnlinePeerCamera } from "../hooks/useOnlinePeerCamera.js";
import DebateCenterStage from "../features/debate-room/components/DebateCenterStage.jsx";
import DebateLeftRail from "../features/debate-room/components/DebateLeftRail.jsx";
import DebateRightRail from "../features/debate-room/components/DebateRightRail.jsx";
import DebateRoomDock from "../features/debate-room/components/DebateRoomDock.jsx";
import { useDebateRoom } from "../features/debate-room/hooks/useDebateRoom.js";
import { isTeamDiscussionSegment } from "../features/debate-room/utils.js";
import { useDebateLeaveGuard } from "../hooks/useDebateLeaveGuard.js";
import BrowserNavBar from "../components/BrowserNavBar.jsx";
import { isCompactViewport, isGuestWeb } from "../utils/visitContext.js";
import "../styles/guest-mobile.css";

function isOnlineDebater(participant) {
  return (
    participant &&
    (participant.side === "affirmative" || participant.side === "negative") &&
    participant.position
  );
}

function countConnectedDebaters(participants = []) {
  return participants.filter(
    (p) => p.connected && (p.side === "affirmative" || p.side === "negative"),
  ).length;
}

function seatLabelFromRoom(room) {
  const participant = room.participant;
  if (participant?.side && participant.side !== "spectator" && participant.position) {
    return `${participant.side === "affirmative" ? "正方" : "反方"}${participant.position} 辩 · ${participant.name || "我"}`;
  }
  const side = room.userSide || room.debate?.user_side;
  if (side && room.mode !== "ai_autonomous") {
    return `${side === "affirmative" ? "正方" : "反方"}${room.debate?.user_position || 1} 辩 · ${room.debate?.user_name || "用户辩手"}`;
  }
  return "";
}

export default function DebateRoom({ leaveGuardRef }) {
  const navigate = useNavigate();
  const room = useDebateRoom();
  const [leftTab, setLeftTab] = useState(null);
  const [rightTab, setRightTab] = useState(null);
  const [compactViewport, setCompactViewport] = useState(() => isCompactViewport());
  const autoTeamSegmentRef = useRef(null);
  const showConfidenceCamera =
    room.debate.mode !== "ai_autonomous" && room.debate.mode !== "online_match";
  const showOnlineCamera =
    !room.isLocal && room.mode === "online_match" && isOnlineDebater(room.participant);
  const peerParticipantIds = useMemo(
    () =>
      (room.debate.participants || [])
        .filter((p) => p.connected && p.id && p.id !== room.participant?.id)
        .map((p) => p.id),
    [room.debate.participants, room.participant?.id],
  );
  const onlineCamera = useOnlinePeerCamera({
    debateId: room.debate?.id,
    participantId: room.participant?.id,
    enabled: showOnlineCamera,
    sendSignal: room.sendWebRtcSignal,
    subscribeWebRtcSignal: room.subscribeWebRtcSignal,
  });
  const onlineCameraBundle = { ...onlineCamera, participantIds: peerParticipantIds };

  const connectedDebaters = countConnectedDebaters(room.debate.participants);
  const waitingForGuests =
    !room.isLocal &&
    room.mode === "online_match" &&
    room.debate.online_ready &&
    connectedDebaters < 2;
  const ownSeatLabel = seatLabelFromRoom(room);

  const shouldGuardLeave = !room.isLocal && room.debate?.phase !== "finished";
  const confirmLeave = useDebateLeaveGuard(
    shouldGuardLeave,
    "确定要离开辩论室吗？进行中的辩论或联机进度可能中断。",
  );

  useEffect(() => {
    function sync() {
      const compact = isCompactViewport();
      setCompactViewport(compact);
      document.documentElement.classList.toggle("debate-compact", compact);
      document.documentElement.classList.remove("guest-mobile");
    }
    sync();
    const mq = window.matchMedia("(max-width: 900px)");
    mq.addEventListener("change", sync);
    return () => {
      mq.removeEventListener("change", sync);
      document.documentElement.classList.remove("debate-compact");
    };
  }, []);

  useEffect(() => {
    if (leaveGuardRef) leaveGuardRef.current = confirmLeave;
    return () => {
      if (leaveGuardRef) leaveGuardRef.current = null;
    };
  }, [confirmLeave, leaveGuardRef]);

  useEffect(() => {
    if (room.hydrating || room.isLocal || room.mode !== "online_match" || !room.debate?.id) return;
    if (!isOnlineDebater(room.participant)) {
      const joinPath = isGuestWeb() ? `/join/${room.debate.id}` : `/join/${room.debate.id}`;
      navigate(joinPath, { replace: true });
    }
  }, [room.hydrating, room.isLocal, room.mode, room.debate?.id, room.participant, navigate]);

  function openMobileLeft(tab) {
    setLeftTab(tab);
    setRightTab(null);
  }

  function openMobileRight(tab) {
    setRightTab(tab);
    setLeftTab(null);
  }

  useEffect(() => {
    if (room.isLocal || room.debate?.phase === "finished") return;
    const inTeamDiscussion = isTeamDiscussionSegment(room.debate);
    const segmentKey = `${room.debate?.schedule_index ?? 0}:${room.debate?.segment_label || ""}`;

    if (inTeamDiscussion) {
      if (autoTeamSegmentRef.current === segmentKey) return;
      autoTeamSegmentRef.current = segmentKey;
      setLeftTab(null);
      setRightTab("team");
      return;
    }

    if (autoTeamSegmentRef.current) {
      autoTeamSegmentRef.current = null;
      setRightTab((prev) => (prev === "team" ? null : prev));
    }
  }, [
    room.isLocal,
    room.debate?.phase,
    room.debate?.schedule_index,
    room.debate?.segment_label,
  ]);

  return (
    <main className="app-shell app-shell--with-dock">
      {waitingForGuests && (
        <div className="online-waiting-banner" role="status">
          等待其他辩手加入… 请将邀请链接发给同学，对方完成加入后即可开始。
        </div>
      )}

      <DebateLeftRail
        debate={room.debate}
        mode={room.mode}
        isLocal={room.isLocal}
        onRequestLeave={confirmLeave}
        health={room.health}
        healthError={room.healthError}
        pipelineHint={room.pipelineHint}
        timing={room.timing}
        setTiming={room.setTiming}
        visibility={room.visibility}
        setVisibility={room.setVisibility}
        awaitingUser={room.awaitingUser}
        turnSecondsLeft={room.turnSecondsLeft}
        materialTitle={room.materialTitle}
        setMaterialTitle={room.setMaterialTitle}
        materialDraft={room.materialDraft}
        setMaterialDraft={room.setMaterialDraft}
        materialStatus={room.materialStatus}
        uploadMaterials={room.uploadMaterials}
        onMaterialFile={room.onMaterialFile}
        activeAgent={room.activeAgent}
        activeTab={leftTab}
        setActiveTab={setLeftTab}
      />

      <DebateCenterStage
        debate={room.debate}
        isLocal={room.isLocal}
        status={room.status}
        speakingNow={room.speakingNow}
        ownSeatLabel={ownSeatLabel}
        messageBoardRef={room.messageBoardRef}
        messageListScrollRef={room.messageListScrollRef}
        visibleMessages={room.visibleMessages}
        showStreamingPublic={room.showStreamingPublic}
        streaming={room.streaming}
        audioByMessage={room.audioByMessage}
        playMessageAudio={room.playMessageAudio}
        exportFullHistory={room.exportFullHistory}
        exportPdf={room.exportPdf}
        speechFontPx={room.speechFontPx}
        setSpeechFontPx={room.setSpeechFontPx}
        userInputEnabled={room.userInputEnabled}
        awaitingUser={room.awaitingUser}
        speechInputState={room.speechInputState}
        draft={room.draft}
        setDraft={room.setDraft}
        askAssist={room.askAssist}
        askDraft={room.askDraft}
        assistLoading={room.assistLoading}
        draftLoading={room.draftLoading}
        showDraftPreview={room.showDraftPreview}
        setShowDraftPreview={room.setShowDraftPreview}
        sendMessage={room.sendMessage}
        messageSending={room.messageSending}
        speechRecording={room.speechRecording}
        speechStatus={room.speechStatus}
        toggleSpeechInput={room.toggleSpeechInput}
        assist={room.assist}
        autoScroll={room.autoScroll}
        setAutoScroll={room.setAutoScroll}
      />

      <DebateRightRail
        debate={room.debate}
        activeAgent={room.activeAgent}
        judgeThoughts={room.judgeThoughts}
        aiStrategyNotes={room.aiStrategyNotes}
        streaming={room.streaming}
        participant={room.participant}
        teamDiscussions={room.teamDiscussions}
        workflowColumns={room.workflowColumns}
        activeTab={rightTab}
        setActiveTab={setRightTab}
        visibility={room.visibility}
        userSide={room.userSide}
      />

      {compactViewport && (
        <nav className="debate-mobile-tabs" aria-label="辩论室面板">
          <button
            type="button"
            className={leftTab === "materials" ? "is-active" : ""}
            onClick={() => openMobileLeft(leftTab === "materials" ? null : "materials")}
          >
            资料
          </button>
          <button type="button" className={!leftTab && !rightTab ? "is-active" : ""} onClick={() => { setLeftTab(null); setRightTab(null); }}>
            发言
          </button>
          <button
            type="button"
            className={rightTab === "online" || rightTab === "turn" ? "is-active" : ""}
            onClick={() => openMobileRight(rightTab ? null : room.mode === "online_match" ? "online" : "turn")}
          >
            {room.mode === "online_match" ? "联机" : "回合"}
          </button>
        </nav>
      )}

      <DebateRoomDock
        debate={room.debate}
        pipelineHint={room.pipelineHint}
        status={room.status}
        awaitingUser={room.awaitingUser}
        speechInputState={room.speechInputState}
        isLocal={room.isLocal}
        roomNav={
          !room.isLocal ? (
            <BrowserNavBar
              variant="dock"
              onBeforeBack={confirmLeave}
              onBeforeForward={confirmLeave}
            />
          ) : null
        }
        wsConnected={room.wsConnected}
        wsReconnecting={room.wsReconnecting}
        wsConnectionState={room.wsConnectionState}
        ttsStatus={room.ttsStatus}
        currentAudio={room.currentAudio}
        audioQueueLength={room.audioQueueLength}
        audioPaused={room.audioPaused}
        audioDisabled={room.audioDisabled}
        pauseAudio={room.pauseAudio}
        resumeAudio={room.resumeAudio}
        skipCurrentAudio={room.skipCurrentAudio}
        stopTtsSession={room.stopTtsSession}
        resumeDebate={room.resumeDebate}
        exportFullHistory={room.exportFullHistory}
        visibility={room.visibility}
        setVisibility={room.setVisibility}
        streaming={room.streaming}
      />

      <FloatingConfidenceCamera enabledByMode={showConfidenceCamera} />
      <FloatingOnlineCamera camera={onlineCameraBundle} enabled={showOnlineCamera} />
    </main>
  );
}
