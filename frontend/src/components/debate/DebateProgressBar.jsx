import { getDebateProgressHint } from "../../features/debate-room/utils.js";

export default function DebateProgressBar({ debate, pipelineHint, autoRunning, speechInputState }) {
  const schedule = debate.schedule || [];
  const total = schedule.length || 1;
  const currentIndex = debate.schedule_index ?? 0;
  const done = schedule.filter((item) => item.status === "done").length;
  const percent = Math.min(100, Math.round((done / total) * 100));
  const progressHint = getDebateProgressHint({ autoRunning, speechInputState, debate });

  return (
    <div className="debate-progress">
      <div className="debate-progress__head">
        <span>
          赛程进度 {Math.min(currentIndex + 1, total)} / {total}
        </span>
        <span>{debate.segment_label || debate.phase}</span>
      </div>
      <div className="debate-progress__track" aria-hidden>
        <div className="debate-progress__fill" style={{ width: `${percent}%` }} />
      </div>
      <p className="debate-progress__hint">
        {progressHint}
        {pipelineHint ? ` · ${pipelineHint}` : ""}
      </p>
    </div>
  );
}
