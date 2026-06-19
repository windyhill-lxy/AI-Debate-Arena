import { useEffect } from "react";
import { ArrowLeft, ArrowRight, Loader2, LogIn } from "lucide-react";
import { OnlineCameraDebug } from "./OnlineCameraPanel.jsx";
import {
  firstFreePosition,
  isSeatTaken,
  occupantName,
  sideHasFreeSeats,
  validateSeatStep,
} from "../utils/joinSeatUtils.js";

export const JOIN_STEPS = ["materials", "seat", "camera", "confirm"];

export { validateSeatStep };

export function joinStepLabel(step) {
  if (step === "materials") return "辩题资料";
  if (step === "seat") return "选择席位";
  if (step === "camera") return "调试摄像头";
  return "确认进入";
}

export function JoinWizardStepBar({ stepIndex }) {
  return (
    <div className="join-wizard__steps">
      {JOIN_STEPS.map((step, index) => (
        <span
          key={step}
          className={`join-wizard__step ${index === stepIndex ? "is-active" : ""} ${index < stepIndex ? "is-done" : ""}`}
        >
          {joinStepLabel(step)}
        </span>
      ))}
    </div>
  );
}

function SeatPicker({ debate, side, setSide, position, setPosition, occupiedSeats }) {
  useEffect(() => {
    if (!sideHasFreeSeats(side, occupiedSeats)) return;
    if (isSeatTaken(side, position, occupiedSeats)) {
      const free = firstFreePosition(side, occupiedSeats);
      if (free != null) setPosition(free);
    }
  }, [side, position, occupiedSeats, setPosition]);

  const sides = [
    { id: "affirmative", label: "正方" },
    { id: "negative", label: "反方" },
  ];

  return (
    <div className="join-wizard__seat-picker">
      <div className="join-wizard__side-tabs">
        {sides.map((item) => (
          <button
            key={item.id}
            type="button"
            className={side === item.id ? "is-active" : ""}
            onClick={() => {
              setSide(item.id);
              const free = firstFreePosition(item.id, occupiedSeats);
              if (free != null) setPosition(free);
            }}
          >
            {item.label}
            {!sideHasFreeSeats(item.id, occupiedSeats) ? "（已满）" : ""}
          </button>
        ))}
      </div>
      <div className="join-wizard__seat-grid" role="listbox" aria-label="选择席位">
        {[1, 2, 3, 4].map((pos) => {
          const taken = isSeatTaken(side, pos, occupiedSeats);
          const selected = position === pos && !taken;
          return (
            <button
              key={pos}
              type="button"
              role="option"
              aria-selected={selected}
              disabled={taken}
              className={`join-wizard__seat-card ${selected ? "is-selected" : ""} ${taken ? "is-taken" : ""}`}
              onClick={() => !taken && setPosition(pos)}
            >
              <strong>{pos} 辩</strong>
              <span>{taken ? occupantName(debate, side, pos) : "可选"}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function JoinWizardPanels({
  currentStep,
  debate,
  materials,
  name,
  setName,
  side,
  setSide,
  position,
  setPosition,
  occupiedSeats,
  topicReadOnlyHint = "辩题与资料由房主设定，加入方不可修改。",
}) {
  let panel = null;

  if (currentStep === "materials") {
    panel = (
      <div className="join-wizard__panel">
        <p className="online-simple__subtitle">{topicReadOnlyHint}</p>
        <div className="join-wizard__topic-lock">
          <label>辩题</label>
          <p>{debate?.topic}</p>
        </div>
        {materials.length > 0 ? (
          <div className="join-wizard__materials">
            {materials.map((item, index) => (
              <article key={`${item.title}-${index}`}>
                <strong>{item.title || "参考资料"}</strong>
                <p>{item.content}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="online-simple__micro-hint">房主未上传额外参考资料。</p>
        )}
      </div>
    );
  } else if (currentStep === "seat") {
    panel = (
      <div className="join-wizard__panel join-wizard__form">
        <label>
          你的昵称
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={24} required />
        </label>
        <SeatPicker
          debate={debate}
          side={side}
          setSide={setSide}
          position={position}
          setPosition={setPosition}
          occupiedSeats={occupiedSeats}
        />
      </div>
    );
  } else if (currentStep === "camera") {
    panel = <OnlineCameraDebug />;
  } else if (currentStep === "confirm") {
    panel = (
      <div className="join-wizard__panel">
        <p className="online-simple__subtitle">确认信息后即可进入辩论室。</p>
        <ul className="join-wizard__summary">
          <li>
            辩题：<strong>{debate?.topic}</strong>
          </li>
          <li>
            席位：
            <strong>
              {side === "affirmative" ? "正方" : "反方"}
              {position} 辩 · {name}
            </strong>
          </li>
        </ul>
      </div>
    );
  }

  if (!panel) return null;
  return <div className="join-wizard__panels">{panel}</div>;
}

export function JoinWizardActions({ stepIndex, loading, debate, onPrev, onNext, nextDisabled = false }) {
  return (
    <div className="join-wizard__actions">
      {stepIndex > 0 && (
        <button type="button" className="online-simple__secondary" onClick={onPrev}>
          <ArrowLeft size={16} /> 上一步
        </button>
      )}
      <button
        type="button"
        className="online-simple__primary"
        disabled={loading || !debate || nextDisabled}
        onClick={onNext}
      >
        {loading ? (
          <>
            <Loader2 size={16} className="spin" /> 进入中…
          </>
        ) : stepIndex < JOIN_STEPS.length - 1 ? (
          <>
            下一步 <ArrowRight size={18} />
          </>
        ) : (
          <>
            确认进入 <LogIn size={18} />
          </>
        )}
      </button>
    </div>
  );
}
