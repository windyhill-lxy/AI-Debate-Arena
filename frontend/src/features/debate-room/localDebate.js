import { demoAgents, formalSchedulePreview, workflow } from "../../data/agents";
import { INITIAL_DEMO_MESSAGES } from "./constants.js";

const demoArgumentBank = {
  affirmative: [
    ["AI作业批改订正率提升", "2024年某省重点中学引入 AI 作业批改系统后，学生错题订正率提升近30%。这支持正方关于即时反馈能帮助学生发现知识漏洞、提升复盘效率的论证。"],
    ["自适应学习测评提升", "2020年一项教育实验显示，使用 AI 自适应学习平台的学生在阶段测评中薄弱点识别准确率提升。"],
    ["个性化反馈缩短等待", "多所学校的课堂反馈记录显示，AI 辅助批改能把学生等待反馈的时间从数天缩短到当天。"],
    ["错题归因更具体", "学习平台日志显示，AI 能把错题归因为概念混淆、步骤遗漏或审题错误，帮助学生做针对性复盘。"],
    ["教师有更多面批时间", "试点课堂反馈显示，AI 处理重复性批改后，教师把更多时间投入到个别学生面批和思维追问。"],
    ["低基础学生获得支架", "分层教学案例显示，AI 提供分步提示后，低基础学生更容易完成从模仿到独立解题的过渡。"],
    ["学习数据辅助诊断", "阶段学习报告显示，AI 汇总连续错题类型后，教师能更早发现班级共性知识漏洞。"],
    ["口语练习频次增加", "语言学习应用数据表明，AI 陪练让学生在课外获得更多低压力口语练习机会。"],
    ["即时提问降低卡顿", "课堂观察显示，学生在预习中使用 AI 提问，能减少因单个概念卡住而放弃学习的情况。"],
    ["学习计划更可执行", "个性化学习计划案例显示，AI 把大目标拆成每日任务后，学生更容易保持复习节奏。"],
  ],
  negative: [
    ["AI解题后自主解题下降", "2021年一项针对高中生的调查显示，频繁使用 AI 解题后自主解题能力下降。这支持反方关于过度依赖工具会削弱主动思考的论证。"],
    ["答案复制削弱推理", "课堂作业抽查显示，部分学生直接复制 AI 解题过程，能交作业但无法复述关键推理。"],
    ["错误解释会误导学习", "AI 解题评测案例显示，模型可能给出看似流畅但步骤错误的解释，学生若缺少辨别能力会被误导。"],
    ["隐私数据存在风险", "教育技术合规报告提醒，学习平台收集作业、成绩和行为数据时需要严格保护未成年人隐私。"],
    ["过度提示降低耐挫", "学习行为观察显示，学生习惯即时提示后，面对开放题更容易放弃独立尝试。"],
    ["资源差距可能扩大", "地区教育信息化报告显示，设备和账号资源不均会让 AI 学习工具的收益集中到条件较好的学生。"],
    ["写作同质化增加", "作文训练样本显示，过度依赖 AI 润色会让学生文本结构趋同，个人表达能力训练不足。"],
    ["教师难判真实水平", "作业评估案例显示，AI 代写和代改会干扰教师判断学生真实掌握程度。"],
    ["注意力被工具分散", "课堂观察显示，学生在学习设备中频繁切换 AI、网页和聊天内容，会增加任务外分心。"],
    ["长期依赖削弱迁移", "认知训练观点认为，长期跳过检索、试错和归纳过程，会削弱学生把知识迁移到新题的能力。"],
  ],
};

function demoArguments(side) {
  const prefix = side === "affirmative" ? "AFF" : "NEG";
  return demoArgumentBank[side].map(([title, claim], index) => ({
    id: `${prefix}-${index + 1}`,
    side,
    title,
    claim,
    source: "本地演示论据库",
  }));
}

export function createLocalDebate(topic, mode) {
  return {
    id: "demo-room",
    topic,
    mode: mode || "ai_autonomous",
    visibility: "context",
    timing: "limited",
    team_discussion_enabled: false,
    rag_review_mode: "essential",
    awaiting_user: false,
    auto_running: false,
    phase: "pre_match",
    segment_label: "赛前介绍",
    segment_rules: "主席介绍辩题、双方、评委与规则。",
    segment_seconds: 60,
    schedule_index: 0,
    turn_index: 0,
    active_speaker_id: "judge",
    schedule: formalSchedulePreview.map((item, index) => ({
      index,
      id: `preview_${index}`,
      label: item.label,
      phase: item.phase,
      seconds: item.seconds,
      speakerId: item.speakerId,
      status: index === 0 ? "current" : "pending",
    })),
    agents: demoAgents,
    messages: INITIAL_DEMO_MESSAGES,
    score: { affirmative: 0, negative: 0 },
    argument_bank: {
      affirmative: demoArguments("affirmative"),
      negative: demoArguments("negative"),
    },
    argument_bank_locked: true,
    workflow: workflow.map(([id, label, detail, stage, kind], index) => ({
      id,
      label,
      detail,
      stage,
      kind: kind || (index % 3 === 0 ? "llm" : index % 3 === 1 ? "action" : "retrieval"),
      status: id === "opening_evidence_bank" ? "running" : index < 7 ? "done" : "pending",
    })),
  };
}
