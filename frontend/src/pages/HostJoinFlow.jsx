import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Users } from "lucide-react";
import {
  JOIN_STEPS,
  JoinWizardActions,
  JoinWizardPanels,
  JoinWizardStepBar,
  validateSeatStep,
} from "../components/JoinWizardSteps.jsx";
import { debateRequest } from "../features/debate-room/api.js";
import { hostTokenHeaders } from "../utils/hostToken.js";
import { firstFreePosition, isSeatTaken } from "../utils/joinSeatUtils.js";
import { participantStorageKey, saveStoredParticipant } from "../utils/participantStorage.js";
import "../styles/home.css";

export default function HostJoinFlow({ debateId, initialTopic }) {
  const navigate = useNavigate();
  const [debate, setDebate] = useState(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [name, setName] = useState(() => `房主${Math.floor(Math.random() * 90 + 10)}`);
  const [side, setSide] = useState("affirmative");
  const [position, setPosition] = useState(1);
  const [loading, setLoading] = useState(false);
  const [hint, setHint] = useState("");

  const loadDebate = useCallback(async (id) => {
    const data = await debateRequest(`/api/debates/${id}`);
    setDebate(data);
    return data;
  }, []);

  useEffect(() => {
    if (debateId) loadDebate(debateId).catch(() => setHint("无法加载房间信息"));
  }, [debateId, loadDebate]);

  useEffect(() => {
    if (!debateId) return undefined;
    const timer = setInterval(() => {
      loadDebate(debateId).catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, [debateId, loadDebate]);

  const occupiedSeats = useMemo(() => {
    const seats = new Set();
    for (const p of debate?.participants || []) {
      if (p.connected && p.side !== "spectator") seats.add(`${p.side}:${p.position}`);
    }
    return seats;
  }, [debate]);

  const materials = debate?.materials_preview || [];
  const currentStep = JOIN_STEPS[stepIndex];
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
    if (!debateId) return;
    const check = validateSeatStep({ side, position, occupiedSeats });
    if (!check.ok) {
      setHint(check.message);
      return;
    }
    setLoading(true);
    setHint("正在进入辩论室…");
    try {
      const stored = window.localStorage.getItem(participantStorageKey(debateId));
      const old = stored ? JSON.parse(stored) : null;
      const data = await debateRequest(`/api/debates/${debateId}/participants`, {
        method: "POST",
        body: JSON.stringify({
          participant_id: old?.id,
          name,
          side,
          position: Number(position),
        }),
      });
      saveStoredParticipant(debateId, data.participant);
      await debateRequest(`/api/debates/${debateId}/online-ready`, {
        method: "POST",
        headers: hostTokenHeaders(debateId),
      });
      navigate(`/room/${debateId}`, {
        state: {
          debate: data.debate,
          mode: data.debate.mode,
          participant: data.participant,
        },
      });
    } catch (error) {
      setHint(`进入失败：${error.message}`);
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

  return (
    <div className="home-page">
      <header className="home-nav">
        <div className="home-logo">
          <Users size={20} />
          <span>房主准备</span>
        </div>
        <Link to="/lobby" className="home-admin-link">
          返回联机大厅
        </Link>
      </header>

      <section className="online-simple online-simple--join-page">
        <JoinWizardStepBar stepIndex={stepIndex} />
        <h1 className="online-simple__title">{debate?.topic || initialTopic || "联机辩论"}</h1>
        <p className="online-simple__subtitle">完成准备并确认进入后，宾客方可开始加入。</p>
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
          topicReadOnlyHint="辩题与资料已设定，创建后不可在此修改。"
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
    </div>
  );
}
