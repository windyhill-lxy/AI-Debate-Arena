import { API_BASE } from "../../utils/apiBase.js";

export { API_BASE };

export const MODE_LABELS = {
  ai_autonomous: "AI 自主辩论",
  user_affirmative: "用户加入正方",
  user_negative: "用户加入反方",
  online_match: "多人联机辩论",
};

export const SPEECH_FONT_SIZES = [12, 14, 16, 18, 20];
export const SPEECH_FONT_STORAGE_KEY = "debate-room-speech-font-px";

export const INITIAL_DEMO_MESSAGES = [
  {
    id: "m1",
    speaker_id: "judge",
    speaker_name: "紫苑裁判",
    side: "judge",
    phase: "pre_match",
    segment_label: "赛前介绍",
    content: "欢迎进入 AI 辩论场。本场将**自动推进** AI 回合，发言以 Markdown 流式呈现。",
    sources: [],
    score_delta: null,
  },
];
