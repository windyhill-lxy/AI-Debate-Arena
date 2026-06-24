import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import GuestShell from "../components/GuestShell.jsx";
import {
  JOIN_STEPS,
  JoinWizardActions,
  JoinWizardPanels,
  JoinWizardStepBar,
  validateSeatStep,
} from "../components/JoinWizardSteps.jsx";
import { debateRequest } from "../features/debate-room/api.js";
import { useErrorDialog } from "../components/ErrorDialogProvider.jsx";
import { errorDialogPayload } from "../utils/httpError.js";
import { useDebateHealth } from "../hooks/useDebateHealth.js";
import { firstFreePosition, isSeatTaken } from "../utils/joinSeatUtils.js";
import { participantStorageKey, saveStoredParticipant } from "../utils/participantStorage.js";
import { isCompactViewport } from "../utils/visitContext.js";
import "../styles/home.css";

export default function GuestJoinFlow({ sessionId, debateRouteId }) {
  const navigate = useNavigate();
  const isSessionEntry = Boolean(sessionId);
  const { health, error: healthError } = useDebateHealth();

  const [phase, setPhase] = useState("waiting_create");
  const [waitMessage, setWaitMessage] = useState("对方正在创建房间中，请稍候…");
  const [debate, setDebate] = useState(null);
  const [resolvedDebateId, setResolvedDebateId] = useState(debateRouteId || "");
  const [stepIndex, setStepIndex] = useState(0);
  const [name, setName] = useState(() => `辩手${Math.floor(Math.random() * 90 + 10)}`);
  const [side, setSide] = useState("affirmative");
  const [position, setPosition] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState("");
  const [cameraEnabled, setCameraEnabled] = useState(false);
  const [lastPollAt, setLastPollAt] = useState(null);
  const pollStateRef = useRef({ phase: "", debateId: "" });
  const { reportError } = useErrorDialog();

  const loadDebate = useCallback(async (debateId) => {
    const data = await debateRequest(`/api/debates/${debateId}`);
    setDebate(data);
    setResolvedDebateId(debateId);
    return data;
  }, []);

  useEffect(() => {
    if (!isSessionEntry && debateRouteId) {
      loadDebate(debateRouteId)
        .then((data) => {
          if (data.online_ready) setPhase("wizard");
          else {
            setPhase("waiting_ready");
            setWaitMessage("等待房主开启房间…");
          }
        })
        .catch((error) => {
          setPhase("waiting_create");
          setWaitMessage("对方正在创建房间中，请稍候…");
          reportError(errorDialogPayload(error, "加载加入链接失败", "GuestJoinFlow.initialLoad"), {
            dedupeKey: `guest-initial:${debateRouteId}`,
            throttleMs: 30000,
          });
        });
    }
  }, [debateRouteId, isSessionEntry, loadDebate, reportError]);

  useEffect(() => {
    if (phase !== "waiting_create" && phase !== "waiting_ready") return undefined;
    let cancelled = false;

    async function poll() {
      try {
        if (isSessionEntry && sessionId) {
          const session = await debateRequest(`/api/debates/online-session/${sessionId}`);
          if (cancelled) return;
          setLastPollAt(Date.now());
          const nextPhase =
            session.status === "waiting"
              ? "waiting_create"
              : session.status === "preparing"
                ? "waiting_ready"
                : session.status === "ready"
                  ? "wizard"
                  : phase;
          const nextDebateId = session.debate_id || resolvedDebateId || "";
          const stateKey = `${nextPhase}:${nextDebateId}`;
          if (pollStateRef.current.key !== stateKey) {
            pollStateRef.current.key = stateKey;
            if (session.status === "waiting") {
              setPhase("waiting_create");
              setWaitMessage(session.message || "对方正在创建房间中，请稍候…");
            } else if (session.status === "preparing") {
              setPhase("waiting_ready");
              setWaitMessage(session.message || "等待房主开启房间…");
              if (session.debate_id && pollStateRef.current.loadedDebateId !== session.debate_id) {
                pollStateRef.current.loadedDebateId = session.debate_id;
                await loadDebate(session.debate_id);
              }
            } else if (session.status === "ready" && session.debate_id) {
              if (pollStateRef.current.loadedDebateId !== session.debate_id) {
                pollStateRef.current.loadedDebateId = session.debate_id;
                await loadDebate(session.debate_id);
              }
              if (!cancelled) setPhase("wizard");
            }
          }
          return;
        }
        if (resolvedDebateId) {
          const data = await loadDebate(resolvedDebateId);
          if (cancelled) return;
          setLastPollAt(Date.now());
          const nextPhase = data.online_ready ? "wizard" : "waiting_ready";
          const stateKey = `${nextPhase}:${resolvedDebateId}`;
          if (pollStateRef.current.key !== stateKey) {
            pollStateRef.current.key = stateKey;
            if (data.online_ready) setPhase("wizard");
            else {
              setPhase("waiting_ready");
              setWaitMessage("等待房主开启房间…");
            }
          }
        }
      } catch (error) {
        if (!cancelled) {
          setPhase("waiting_create");
          setWaitMessage("对方正在创建房间中，请稍候…");
          reportError(errorDialogPayload(error, "同步加入状态失败", "GuestJoinFlow.poll"), {
            dedupeKey: `guest-poll:${sessionId || resolvedDebateId || "pending"}`,
            throttleMs: 30000,
          });
        }
      }
    }

    poll();
    const timer = setInterval(poll, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isSessionEntry, loadDebate, phase, reportError, resolvedDebateId, sessionId]);

  useEffect(() => {
    if (phase !== "wizard" || !resolvedDebateId) return undefined;
    let cancelled = false;

    async function pollSeats() {
      try {
        await loadDebate(resolvedDebateId);
        if (!cancelled) setLastPollAt(Date.now());
      } catch (error) {
        reportError(errorDialogPayload(error, "同步席位失败", "GuestJoinFlow.pollSeats"), {
          dedupeKey: `guest-seat-poll:${resolvedDebateId}`,
          throttleMs: 30000,
        });
      }
    }

    pollSeats();
    const timer = setInterval(pollSeats, 3000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [phase, resolvedDebateId, loadDebate, reportError]);

  const occupiedSeats = useMemo(() => {
    const seats = new Set();
    for (const p of debate?.participants || []) {
      if (p.connected && p.side !== "spectator") seats.add(`${p.side}:${p.position}`);
    }
    return seats;
  }, [debate]);

  const materials = debate?.materials_preview || [];
  const currentStep = JOIN_STEPS[stepIndex];
  const isDesktopLayout = !isCompactViewport();
  const seatValidation = validateSeatStep({ side, position, occupiedSeats });
  const seatStepBlocked = currentStep === "seat" && !seatValidation.ok;

  useEffect(() => {
    if (!debate) return;
    if (!isSeatTaken(side, position, occupiedSeats)) return;
    const freeOnSide = firstFreePosition(side, occupiedSeats);
    if (freeOnSide != null) {
      setPosition(freeOnSide);
      return;
    }
    const altSide = side === "affirmative" ? "negative" : "affirmative";
    const freeAlt = firstFreePosition(altSide, occupiedSeats);
    if (freeAlt != null) {
      setSide(altSide);
      setPosition(freeAlt);
    }
  }, [debate, occupiedSeats, side, position]);

  async function confirmEnter() {
    if (!resolvedDebateId) return;
    const check = validateSeatStep({ side, position, occupiedSeats });
    if (!check.ok) {
      setHint(check.message);
      return;
    }
    setLoading(true);
    setHint("正在进入辩论室…");
    try {
      const stored = window.localStorage.getItem(participantStorageKey(resolvedDebateId));
      const old = stored ? JSON.parse(stored) : null;
      const data = await debateRequest(`/api/debates/${resolvedDebateId}/participants`, {
        method: "POST",
        body: JSON.stringify({
          participant_id: old?.id,
          name,
          side,
          position: Number(position),
        }),
      });
      saveStoredParticipant(resolvedDebateId, data.participant);
      navigate(`/room/${resolvedDebateId}`, {
        state: {
          debate: data.debate,
          mode: data.debate.mode,
          participant: data.participant,
          cameraEnabled,
        },
      });
    } catch (error) {
      setHint(`进入失败：${error.message}`);
      reportError(errorDialogPayload(error, "进入房间失败", "GuestJoinFlow.confirmEnter"));
    } finally {
      setLoading(false);
    }
  }

  function nextStep() {
    if (currentStep === "seat") {
      const check = validateSeatStep({ side, position, occupiedSeats });
      if (!check.ok) {
        setHint(check.message);
        return;
      }
    }
    setHint("");
    if (stepIndex < JOIN_STEPS.length - 1) setStepIndex((i) => i + 1);
    else confirmEnter();
  }

  if (phase === "waiting_create" || phase === "waiting_ready") {
    return (
      <GuestShell>
        <div className="guest-wait">
          <Loader2 size={36} className="spin guest-wait__icon" />
          <h1>{phase === "waiting_create" ? "等待房主创建房间" : "等待房主开启房间"}</h1>
          <p className="guest-wait__message">{waitMessage}</p>
          {!health && healthError && (
            <p className="guest-wait__error">
              无法连接服务器。{healthError || "请确认房主程序仍在运行，并请房主重新复制链接。"}
            </p>
          )}
          <p className="guest-wait__micro">
            页面会自动刷新，无需手动操作。
            {lastPollAt ? ` 最近同步：${new Date(lastPollAt).toLocaleTimeString()}` : ""}
          </p>
          <button type="button" className="online-simple__secondary guest-wait__exit" onClick={() => navigate("/welcome")}>
            退出等待
          </button>
        </div>
      </GuestShell>
    );
  }

  return (
    <GuestShell>
      <section className="online-simple online-simple--join-page guest-join">
        <JoinWizardStepBar stepIndex={stepIndex} />
        <h1 className="online-simple__title">{debate?.topic || "联机辩论"}</h1>
        {hint && <p className="online-simple__hint">{hint}</p>}
        <JoinWizardPanels
          currentStep={currentStep}
          debate={debate}
          materials={materials}
          name={name}
          setName={setName}
          side={side}
          setSide={setSide}
          position={position}
          setPosition={setPosition}
          occupiedSeats={occupiedSeats}
          cameraEnabled={cameraEnabled}
          setCameraEnabled={setCameraEnabled}
        />
        <JoinWizardActions
          stepIndex={stepIndex}
          loading={loading}
          debate={debate}
          onPrev={() => setStepIndex((i) => Math.max(0, i - 1))}
          onNext={nextStep}
          nextDisabled={seatStepBlocked}
        />
      </section>
    </GuestShell>
  );
}
