import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const slidesDir = path.join(root, "slides");
const sharedDir = path.join(root, "shared");
const outputDir = path.join(root, "output");
fs.mkdirSync(slidesDir, { recursive: true });
fs.mkdirSync(sharedDir, { recursive: true });
fs.mkdirSync(outputDir, { recursive: true });

const slides = [
  {
    file: "01-cover.html",
    label: "封面",
    section: "AI 智能体开发专项赛 · 项目报告",
    title: "AI辩论场",
    subtitle: "一套将标准竞技辩论赛制与多智能体工作流深度融合的系统",
    body: "让思辨训练可被观测、论据可被验证、过程可被复盘。",
    className: "cover",
    meta: ["江门市第一中学", "林湘岩、湛昊轩、梁志聪"],
  },
  {
    file: "02-origin.html",
    label: "项目缘起",
    section: "第一幕 · 为什么做",
    eyebrow: "从真实问题出发",
    title: "从一场对话，到一套赛制。",
    lead:
      "学校和班级组织辩论时，最常见的问题不是没有观点，而是发言不规范、词不达意、磕磕绊绊。辩论社同学也反馈，平时较少有机会和同学完整练习，想练却不一定能凑齐对手、队友和裁判。",
    body:
      "大模型对话产品已经十分普及，但多数仍停留在「你问我答」。对于需要结构化思辨、多轮攻防、可验证论据的辩论训练场景，简单聊天界面既无法还原正式辩论节奏，也难以让使用者判断 AI 发言是否站得住脚。",
    note: "AI辩论场的目标，是成为一套可以真正用于课堂思辨训练、赛事备赛演练和智能体能力展示的完整系统，而非又一个通用聊天 Demo。",
  },
  {
    file: "03-problem.html",
    label: "问题定义",
    section: "第一幕 · 问题定义",
    eyebrow: "我们要解决的三件事",
    title: "辩论训练最难的，不是写稿，而是反复经历完整对抗。",
    cards: [
      ["结构化赛制缺失", "通用 AI 对话缺乏立论、驳论、质询、自由辩论、总结陈词等正式环节的状态切换与限时约束。"],
      ["论据不可验证", "大模型容易生成看似权威但无法溯源的表述，「研究表明」「数据显示」背后可能没有真实来源。"],
      ["过程不可观测", "策略规划、队内讨论、事实核查等内部步骤如果不可见，评委和开发者无法判断系统是否真正在执行智能决策。"],
    ],
    note: "核心判断：把 AI 辩论做成「可验证的训练场」，比做一个会说话的聊天机器人更有价值。",
  },
  {
    file: "04-agent-thinking.html",
    label: "智能体理解",
    section: "第一幕 · 方向确立",
    eyebrow: "为什么选择 Agent 工作流",
    title: "AI 的用武之地，不只是聊天，而是把概率模型流程化、约束化。",
    lead:
      "我对 OpenClaw、Claude Code 等智能体形态很感兴趣。它们让我意识到：大模型本质上仍是概率模型，但如果把它放进明确流程、权限边界、检查节点和可回放记录中，它就不再只是聊天机器人，而能成为稳定生产力的一部分。",
    split: [
      ["聊天机器人形态", "单轮回答为主，输出看起来流畅，但过程不透明、事实难核验、角色和权限容易混在一起。"],
      ["智能体工作流形态", "把任务拆成节点：检索、判断、生成、自检、发布、评分。每一步有输入、有约束、有记录。"],
    ],
    note: "所以项目从一开始就不是追求「AI 会辩论」这一句话，而是追求「辩论这件事能不能被设计成一个清晰、可控、可复盘的智能体系统」。",
  },
  {
    file: "05-product.html",
    label: "产品概览",
    section: "第二幕 · 系统与能力",
    eyebrow: "一套完整的辩论智能体系统",
    title: "从辩题输入到裁判报告，系统跑通完整训练链路。",
    image: "../assets/old-ppt-media/image2.png",
    imageCaption: "旧项目报告中的辩论室主界面截图",
    bullets: [
      "支持 AI 自主辩论、用户加入正方、用户加入反方、多人联机同房间。",
      "三栏布局承载赛程控制、角色舞台、发言流、AI 教练、论据库与工作流脑图。",
      "WebSocket 流式输出 Markdown 发言，前端同步显示当前发言人、赛程进度与工作流节点。",
    ],
  },
  {
    file: "06-user-flow.html",
    label: "用户路径",
    section: "第二幕 · 用户路径",
    eyebrow: "一次训练如何发生",
    title: "系统把复杂辩论拆成可执行、可暂停、可复盘的训练流程。",
    flow: [
      ["建立房间", "输入辩题，选择赛制、计时、可见性和参与身份。"],
      ["导入资料", "上传参考材料，写入本场向量库，形成可引用来源。"],
      ["自动推进", "赛程状态机控制环节，AI 辩手按职责发言。"],
      ["人类介入", "轮到用户时暂停，AI 教练给建议但不代替提交。"],
      ["赛后复盘", "裁判报告、逐字稿导出、回放分享沉淀训练记录。"],
    ],
  },
  {
    file: "07-architecture.html",
    label: "系统架构",
    section: "第二幕 · 系统设计",
    eyebrow: "四层技术架构",
    title: "架构不是为展示而画，而是支撑多人、实时、可复盘的辩论现场。",
    layers: [
      ["表现层", "React + Vite 构建首页、辩论室、联机大厅、回放页和管理页；同一套 Web UI 覆盖电脑、手机和 Electron 桌面壳。"],
      ["编排层", "FastAPI 提供 REST 与 WebSocket；LangGraph 负责单回合智能体循环；YAML 赛程状态机推进正式 4v4。"],
      ["智能层", "DeepSeek 双模型路由、RAG 检索、TTS/ASR、自信度摄像头训练、用户发言评分共同构成 AI 能力层。"],
      ["数据层", "MongoDB 持久化、Redis 实时广播、SQLite 向量索引；没有数据库时自动降级内存模式，便于现场演示。"],
    ],
  },
  {
    file: "08-agents.html",
    label: "多智能体",
    section: "第二幕 · 多智能体",
    eyebrow: "九个角色，各司其职",
    title: "系统把「一个 AI 发言」拆成一支辩队的协作。",
    teams: [
      ["正方四辩", "云汐、澜汐、珂绫、青萝分别负责立论、驳论、质辩与总结，角色职责来自真实 4v4 辩论分工。"],
      ["紫苑裁判", "不只宣布结果，还参与任务合理性、论点强度、事实风险、总结质量和最终胜负判断。"],
      ["反方四辩", "橙律、星白、反方三辩、反方四辩分别建立反方框架、拆解论证、推进盘问并完成价值收束。"],
    ],
    note: "创新不在「角色名字很多」，而在于角色职责、赛程阶段、可见性边界和裁判判断被放进同一套状态系统。",
  },
  {
    file: "09-workflow.html",
    label: "工作流设计",
    section: "第二幕 · 工作流",
    eyebrow: "符合专项赛核心要求",
    title: "67 个赛程段、43 个展示节点、10 个 LangGraph 节点，让辩论不是线性文本生成。",
    stats: [
      ["67", "正式 4v4 赛程段，覆盖准备、立论、驳论、质辩、自由辩、总结与终局裁决。"],
      ["43", "前端工作流展示节点，让评委看到当前处于哪类智能体动作。"],
      ["10", "LangGraph 运行节点，构成检索、判断、生成、核查、评分、路由的闭环。"],
      ["12", "大模型判断/评语/胜负相关赛程段，体现真正的智能决策。"],
    ],
    note: "这些数字来自项目源码统计：`formal_4v4.yaml`、`workflow_template()` 与 `DebateGraph._build_graph()`。",
  },
  {
    file: "10-runtime-loop.html",
    label: "单回合内核",
    section: "第二幕 · 运行时内核",
    eyebrow: "每一轮发言的生命周期",
    title: "一段发言要经过检索、判断、反思与核查，不是直接把辩题丢给模型。",
    flow: [
      ["RAG 检索", "从辩题资料、上传材料和历史上下文中取当前可用依据。"],
      ["策略规划", "根据赛程阶段选择立论、反驳、盘问或总结的表达目标。"],
      ["方向判断", "大模型判断本轮任务是否合理，避免偏离战场。"],
      ["生成与反思", "非自由辩先形成内部草稿，再凝练为正式发言。"],
      ["核查与评分", "事实核查失败回环重写；通过后裁判记录分数与风险。"],
    ],
  },
  {
    file: "11-anti-hallucination.html",
    label: "防幻觉机制",
    section: "第二幕 · 防幻觉工程",
    eyebrow: "让每一条论据都可以被追问",
    className: "compact-table",
    title: "AI 辩论最危险的地方，是「听起来很有道理」。",
    lead:
      "系统不把流畅文本当作最终答案，而是把事实来源、引用编号、核查结果和裁判扣分放进同一条链路。目标不是让模型永不出错，而是让错误在训练流程里被发现、被标记、被复盘。",
    rows: [
      ["资料入库", "用户上传材料分块写入本场向量库；AI 检索到的真实论据登记为 AFF/NEG 编号。"],
      ["发言前", "RAG 根据当前环节、持方和历史战场检索资料，提示词约束不得编造来源。"],
      ["发言中", "正式知识性发言必须引用本方论据 ID；用户公开发言也会校验引用。"],
      ["发布前", "`sanitize_citations` 移除未入库资料编号，让伪造引用不能伪装成真实资料。"],
      ["赛后", "裁判报告记录主战场、失误与幻觉风险，训练者据此复盘证据使用质量。"],
    ],
  },
  {
    file: "12-context.html",
    label: "上下文权限",
    section: "第二幕 · 权限与可见性",
    eyebrow: "后端 AI 上下文管理系统",
    title: "不是所有 AI 都该看到所有信息，权限边界本身就是系统能力。",
    columns: [
      ["真实赛场视角", "只看到公开发言和自己应当看到的信息；队内讨论不会泄露给对方。"],
      ["上下文学习视角", "保留本方策略、内部思路和裁判反馈，适合训练与复盘。"],
      ["上帝视角", "老师、评委或开发者可观察全量队内讨论、策略与裁判判断。"],
    ],
    note: "`ai_context_manager.py` 与 `message_visibility.py` 共同限制每位 AI 与每个观众能获得的信息，避免把队内策略错误暴露给对手。",
  },
  {
    file: "13-human-ai.html",
    label: "人机协同",
    section: "第二幕 · 人机协同",
    eyebrow: "AI 辅助思考，而非替代思考",
    title: "系统刻意保留学生的发言权，让 AI 做陪练、资料官和教练。",
    image: "../assets/old-ppt-media/image1.png",
    bullets: [
      "人机混合模式下，轮到用户时自动暂停；用户可以查看资料、当前战场和 AI 建议。",
      "AI 教练提供反驳切口、追问方向与可编辑草稿，但最终提交权仍在学生手里。",
      "语音输入、ASR 转写和自信度摄像头训练，让表达训练不止停留在文字层面。",
    ],
    note: "人机协同的边界越清楚，训练价值越高：AI 给方向和证据，人完成判断与表达。",
  },
  {
    file: "14-cross-device.html",
    label: "跨端部署",
    section: "第三幕 · 工程实现",
    eyebrow: "不止于文字辩论",
    title: "同一套系统覆盖电脑主持、手机加入、桌面发行和弱环境演示。",
    image: "../assets/old-ppt-media/image11.jpeg",
    bullets: [
      "Web / Electron / U 盘便携三种交付形态，适配比赛现场和学校机房环境。",
      "支持局域网联机与公网穿透；参与者通过邀请链接选择席位，WebSocket 同步在线状态。",
      "TTS 独立音色、录音 ASR、摄像头表现评价，让系统具备多模态调用与扩展基础。",
    ],
  },
  {
    file: "15-engineering.html",
    label: "工程成果",
    section: "第三幕 · 开发与测试",
    eyebrow: "从能跑到跑得稳",
    title: "项目不只完成演示界面，也补齐了测试、导出、回放和运维入口。",
    rows: [
      ["质量保障", "32 个测试文件、142 个测试函数，覆盖引用校验、赛程元数据、WebSocket、联机、用户发言评审等模块。"],
      ["可观测性", "管理页提供房间列表、单房间诊断、LLM 用量粗统计、自动推进停止与恢复。"],
      ["输出沉淀", "全场发言可导出 Markdown/PDF；回放页和分享链接让一次训练变成可复盘材料。"],
      ["现场可靠性", "后端启动恢复 auto_runner，MongoDB/Redis 未启动时内存降级，E2E 支持一键脚本运行。"],
    ],
  },
  {
    file: "16-score-map.html",
    label: "评分映射",
    section: "第四幕 · 对标评分标准",
    eyebrow: "按高分标准倒推表达重点",
    title: "这份作品的关键能力，逐项对应专项赛评分维度。",
    matrix: [
      ["创新性 25%", "辩论训练场景 + 多模型/多角色对抗 + 防幻觉裁判 + 训练/复盘闭环，避免大众化聊天 Demo。"],
      ["完整性 20%", "PPT、源码、工作流图、测试、部署脚本、报告视频素材均能支撑需求分析到维护的完整过程。"],
      ["先进性 30%", "LangGraph 工作流、多智能体协同、RAG 检索、ASR/TTS/摄像头多模态、人机协同提示词边界。"],
      ["扩展性 10%", "Web/Electron/U 盘/局域网/公网穿透，具备扩展到手机和其它终端设备的基础。"],
      ["传播性 15%", "项目叙事围绕真实训练痛点，配合演示、回放、导出和使用照片，增强汇报完整性与说服力。"],
    ],
  },
  {
    file: "17-reflection.html",
    label: "反思与展望",
    section: "第四幕 · 反思",
    eyebrow: "开发过程中的取舍",
    title: "我们没有把所有事情一次做满，而是先把「可信的辩论工作流」做扎实。",
    columns: [
      ["已经完成", "正式赛制、九位智能体、工作流可视化、论据入库、防幻觉校验、人机协同、联机与导出。"],
      ["仍待完善", "更大规模辩论社回访记录、多厂商模型异构对抗、实时语音辩论、更多真实赛事资料库。"],
      ["下一步方向", "把系统从比赛作品继续推进成社团训练工具，让每次练习都有记录、证据和复盘。"],
    ],
  },
  {
    file: "18-closing.html",
    label: "封底",
    section: "AI DEBATE ARENA",
    title: "让思辨可被看见，论据可被验证，过程可被复盘。",
    className: "closing",
  },
];

const css = String.raw`
* { box-sizing: border-box; }
html, body {
  width: 1920px;
  height: 1080px;
  margin: 0;
  overflow: hidden;
  background: #eee4d2;
  color: #211b16;
  font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
}
body {
  background:
    radial-gradient(circle at 8% 20%, rgba(138, 47, 35, 0.10), transparent 30%),
    radial-gradient(circle at 82% 72%, rgba(33, 83, 87, 0.12), transparent 32%),
    linear-gradient(135deg, #f4ecdf 0%, #e3d6c2 100%);
}
.slide {
  position: relative;
  width: 1920px;
  height: 1080px;
  padding: 76px 104px 72px;
}
.slide::before {
  content: "";
  position: absolute;
  inset: 30px;
  border: 1px solid rgba(33, 27, 22, .16);
  pointer-events: none;
}
.masthead {
  position: absolute;
  top: 44px;
  left: 104px;
  right: 104px;
  display: flex;
  justify-content: space-between;
  gap: 36px;
  color: rgba(33, 27, 22, .58);
  font-size: 18px;
  letter-spacing: .13em;
  text-transform: uppercase;
}
.eyebrow {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-top: 58px;
  margin-bottom: 28px;
  color: #8d3328;
  font-weight: 800;
  font-size: 22px;
  letter-spacing: .16em;
}
.eyebrow::before { content: ""; width: 74px; height: 3px; background: #8d3328; }
h1, h2 {
  margin: 0;
  font-family: "SimSun", "Songti SC", "Noto Serif CJK SC", serif;
  color: #211b16;
  font-weight: 900;
  letter-spacing: 0;
  text-wrap: balance;
}
h1 { font-size: 118px; line-height: 1.03; }
h2 { font-size: 68px; line-height: 1.14; max-width: 1320px; }
h3 { margin: 0; color: #8d3328; font-size: 32px; line-height: 1.22; }
p { margin: 0; color: rgba(33, 27, 22, .82); font-size: 28px; line-height: 1.72; text-wrap: pretty; }
.lead { margin-top: 28px; max-width: 1180px; font-size: 35px; line-height: 1.58; color: rgba(33, 27, 22, .80); }
.body { max-width: 1200px; margin-top: 28px; }
.note {
  margin-top: 34px;
  padding: 24px 30px;
  border-left: 7px solid #8d3328;
  background: rgba(255, 250, 240, .58);
  font-size: 31px;
  line-height: 1.52;
  color: rgba(33, 27, 22, .86);
}
.footer {
  position: absolute;
  left: 104px;
  right: 104px;
  bottom: 42px;
  display: flex;
  justify-content: space-between;
  gap: 40px;
  color: rgba(33, 27, 22, .46);
  font-size: 17px;
  letter-spacing: .08em;
}
.cover h1 { font-size: 150px; margin-top: 94px; }
.cover .subtitle { margin-top: 22px; max-width: 1180px; font-size: 40px; line-height: 1.35; color: rgba(33, 27, 22, .82); }
.cover .body { margin-top: 34px; font-size: 34px; }
.cover .meta {
  position: absolute;
  left: 104px;
  bottom: 140px;
  display: flex;
  gap: 20px;
  font-size: 24px;
  color: rgba(33, 27, 22, .72);
}
.meta span { padding: 13px 18px; border: 1px solid rgba(33, 27, 22, .16); background: rgba(255,250,240,.52); }
.grid-2 { display: grid; grid-template-columns: 1.04fr .96fr; gap: 72px; align-items: center; }
.card-grid { margin-top: 56px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 26px; }
.card {
  min-height: 300px;
  padding: 34px 34px 30px;
  border: 1px solid rgba(33, 27, 22, .15);
  background: rgba(255, 250, 240, .62);
  box-shadow: 0 18px 42px rgba(54, 42, 28, .10);
}
.card p { margin-top: 18px; font-size: 26px; line-height: 1.58; }
.split { margin-top: 48px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 34px; }
.split .card { min-height: 260px; }
.image-panel {
  border: 1px solid rgba(33, 27, 22, .16);
  background: rgba(255,250,240,.62);
  padding: 18px;
  box-shadow: 0 18px 42px rgba(54,42,28,.11);
}
.image-panel img { display: block; width: 100%; height: 100%; object-fit: contain; background: #fbf7ef; }
.image-caption { margin-top: 12px; font-size: 18px; color: rgba(33,27,22,.55); }
.bullets { display: grid; gap: 22px; margin-top: 38px; }
.bullet {
  display: grid;
  grid-template-columns: 34px 1fr;
  gap: 18px;
  align-items: start;
  padding: 20px 24px;
  background: rgba(255,250,240,.58);
  border: 1px solid rgba(33,27,22,.12);
  font-size: 27px;
  line-height: 1.55;
}
.dot { width: 14px; height: 14px; margin-top: 13px; border-radius: 50%; background: #8d3328; }
.flow { margin-top: 56px; display: grid; grid-template-columns: repeat(5, 1fr); border: 1px solid rgba(33,27,22,.16); background: rgba(255,250,240,.52); }
.flow-item { min-height: 260px; padding: 32px 28px; border-right: 1px solid rgba(33,27,22,.13); position: relative; }
.flow-item:last-child { border-right: 0; }
.flow-item strong { display: block; color: #215357; font-size: 30px; margin-bottom: 18px; }
.flow-item span { display: block; color: rgba(33,27,22,.76); font-size: 24px; line-height: 1.5; }
.layers { margin-top: 44px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 22px; }
.layer { min-height: 390px; padding: 31px 28px; background: rgba(255,250,240,.62); border: 1px solid rgba(33,27,22,.14); }
.layer p { margin-top: 18px; font-size: 23px; line-height: 1.55; }
.teams { margin-top: 52px; display: grid; grid-template-columns: 1fr .82fr 1fr; gap: 30px; align-items: stretch; }
.team { padding: 36px; background: rgba(255,250,240,.62); border: 1px solid rgba(33,27,22,.14); min-height: 340px; }
.team.judge { background: #211b16; }
.team.judge h3 { color: #d8ad58; }
.team.judge p { color: rgba(250,244,234,.82); }
.team p { margin-top: 20px; font-size: 26px; line-height: 1.58; }
.stats { margin-top: 50px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 24px; }
.stat { padding: 30px 28px; min-height: 250px; border: 1px solid rgba(33,27,22,.14); background: rgba(255,250,240,.62); }
.stat strong { display:block; color:#215357; font-size: 82px; line-height: .95; font-family: Georgia, serif; }
.stat span { display:block; margin-top: 18px; color: rgba(33,27,22,.75); font-size: 23px; line-height: 1.42; }
.rows { margin-top: 44px; display: grid; border: 1px solid rgba(33,27,22,.16); }
.row { display: grid; grid-template-columns: 270px 1fr; min-height: 92px; border-bottom: 1px solid rgba(33,27,22,.12); background: rgba(255,250,240,.58); }
.row:last-child { border-bottom: 0; }
.row strong { padding: 25px 30px; color:#8d3328; font-size: 26px; border-right: 1px solid rgba(33,27,22,.12); }
.row span { padding: 24px 30px; color: rgba(33,27,22,.80); font-size: 25px; line-height: 1.5; }
.compact-table h2 { font-size: 62px; max-width: 1260px; }
.compact-table .lead { margin-top: 22px; font-size: 31px; line-height: 1.48; max-width: 1240px; }
.compact-table .rows { margin-top: 28px; }
.compact-table .row { min-height: 78px; }
.compact-table .row strong { padding: 20px 28px; font-size: 24px; }
.compact-table .row span { padding: 18px 28px; font-size: 23px; line-height: 1.38; }
.columns { margin-top: 52px; display:grid; grid-template-columns: repeat(3, 1fr); gap: 28px; }
.column { min-height: 320px; padding: 34px; border: 1px solid rgba(33,27,22,.14); background: rgba(255,250,240,.62); }
.column p { margin-top: 20px; font-size: 25px; line-height: 1.58; }
.matrix { margin-top: 34px; display:grid; border: 1px solid rgba(33,27,22,.16); }
.matrix-row { display:grid; grid-template-columns: 230px 1fr; border-bottom:1px solid rgba(33,27,22,.12); background: rgba(255,250,240,.58); min-height: 90px; }
.matrix-row:last-child { border-bottom: 0; }
.matrix-row strong { padding: 23px 26px; color:#8d3328; font-size: 24px; border-right: 1px solid rgba(33,27,22,.12); }
.matrix-row span { padding: 22px 28px; font-size: 23px; line-height:1.46; color: rgba(33,27,22,.80); }
.closing { display:grid; place-items:center; text-align:center; background: #211b16; color: #f6ead8; }
.closing::before { border-color: rgba(246,234,216,.25); }
.closing .masthead, .closing .footer { color: rgba(246,234,216,.56); }
.closing h1 { max-width: 1320px; color: #f6ead8; font-size: 86px; line-height: 1.18; }
.closing .section-kicker { color: #d8ad58; margin-bottom: 44px; font-size: 25px; letter-spacing:.18em; }
code { font-family: "Consolas", "JetBrains Mono", monospace; font-size: .86em; color: #215357; }
`;

function escapeHtml(value = "") {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function masthead(slide) {
  return `<div class="masthead"><span>AI DEBATE ARENA</span><span>${escapeHtml(slide.section || "")}</span></div>`;
}

function footer(label) {
  return `<div class="footer"><span>${escapeHtml(label)}</span><span>AI 智能体开发专项赛</span></div>`;
}

function titleBlock(slide) {
  if (slide.className === "cover") {
    return `
      <h1>${escapeHtml(slide.title)}</h1>
      <p class="subtitle">${escapeHtml(slide.subtitle)}</p>
      <p class="body">${escapeHtml(slide.body)}</p>
      <div class="meta">${slide.meta.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}</div>
    `;
  }
  if (slide.className === "closing") {
    return `<div><div class="section-kicker">${escapeHtml(slide.section)}</div><h1>${escapeHtml(slide.title)}</h1></div>`;
  }
  return `
    <div class="eyebrow">${escapeHtml(slide.eyebrow || slide.label)}</div>
    <h2>${escapeHtml(slide.title)}</h2>
    ${slide.lead ? `<p class="lead">${escapeHtml(slide.lead)}</p>` : ""}
    ${slide.body ? `<p class="body">${escapeHtml(slide.body)}</p>` : ""}
  `;
}

function renderBullets(items = []) {
  return `<div class="bullets">${items.map((item) => `<div class="bullet"><span class="dot"></span><span>${escapeHtml(item)}</span></div>`).join("")}</div>`;
}

function renderSlide(slide) {
  let content = titleBlock(slide);
  if (slide.cards) {
    content += `<div class="card-grid">${slide.cards.map(([h, p]) => `<article class="card"><h3>${escapeHtml(h)}</h3><p>${escapeHtml(p)}</p></article>`).join("")}</div>`;
  }
  if (slide.split) {
    content += `<div class="split">${slide.split.map(([h, p]) => `<article class="card"><h3>${escapeHtml(h)}</h3><p>${escapeHtml(p)}</p></article>`).join("")}</div>`;
  }
  if (slide.image && slide.bullets) {
    content += `<div class="grid-2" style="margin-top:44px;"><div><div class="image-panel" style="height:455px;"><img src="${slide.image}" alt="${escapeHtml(slide.imageCaption || "")}"></div>${slide.imageCaption ? `<div class="image-caption">${escapeHtml(slide.imageCaption)}</div>` : ""}</div><div>${renderBullets(slide.bullets)}</div></div>`;
  } else if (slide.bullets) {
    content += renderBullets(slide.bullets);
  }
  if (slide.flow) {
    content += `<div class="flow">${slide.flow.map(([h, p]) => `<article class="flow-item"><strong>${escapeHtml(h)}</strong><span>${escapeHtml(p)}</span></article>`).join("")}</div>`;
  }
  if (slide.layers) {
    content += `<div class="layers">${slide.layers.map(([h, p]) => `<article class="layer"><h3>${escapeHtml(h)}</h3><p>${escapeHtml(p)}</p></article>`).join("")}</div>`;
  }
  if (slide.teams) {
    content += `<div class="teams">${slide.teams.map(([h, p], idx) => `<article class="team ${idx === 1 ? "judge" : ""}"><h3>${escapeHtml(h)}</h3><p>${escapeHtml(p)}</p></article>`).join("")}</div>`;
  }
  if (slide.stats) {
    content += `<div class="stats">${slide.stats.map(([n, p]) => `<article class="stat"><strong>${escapeHtml(n)}</strong><span>${escapeHtml(p)}</span></article>`).join("")}</div>`;
  }
  if (slide.rows) {
    content += `<div class="rows">${slide.rows.map(([h, p]) => `<div class="row"><strong>${escapeHtml(h)}</strong><span>${escapeHtml(p)}</span></div>`).join("")}</div>`;
  }
  if (slide.columns) {
    content += `<div class="columns">${slide.columns.map(([h, p]) => `<article class="column"><h3>${escapeHtml(h)}</h3><p>${escapeHtml(p)}</p></article>`).join("")}</div>`;
  }
  if (slide.matrix) {
    content += `<div class="matrix">${slide.matrix.map(([h, p]) => `<div class="matrix-row"><strong>${escapeHtml(h)}</strong><span>${escapeHtml(p)}</span></div>`).join("")}</div>`;
  }
  if (slide.note) {
    content += `<p class="note">${escapeHtml(slide.note)}</p>`;
  }
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>${escapeHtml(slide.label)} · AI辩论场</title>
  <link rel="stylesheet" href="../shared/tokens.css">
</head>
<body>
  <section class="slide ${slide.className || ""}">
    ${masthead(slide)}
    ${content}
    ${footer(slide.label)}
  </section>
</body>
</html>
`;
}

const indexHtml = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>AI 辩论场 · 优化项目报告</title>
<script>
window.DECK_MANIFEST = ${JSON.stringify(slides.map(({ file, label }) => ({ file: `slides/${file}`, label })), null, 2)};
window.DECK_WIDTH = 1920;
window.DECK_HEIGHT = 1080;
</script>
<style>
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%;overflow:hidden;background:#211b16;font-family:"Microsoft YaHei","PingFang SC",sans-serif}
body[data-mode="present"] .overview,body[data-mode="present"] .start-btn{display:none}
body[data-mode="overview"] #present-ui{display:none}
.overview{position:fixed;inset:0;overflow:auto;padding:70px 78px 120px;background:linear-gradient(135deg,#f1eadf,#d8cbb7)}
.overview-title{text-align:center;margin-bottom:34px;color:rgba(33,27,22,.62);letter-spacing:.16em;font-size:15px;text-transform:uppercase}
.wall{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:26px;perspective:2000px}
.card{position:relative;aspect-ratio:16/9;overflow:hidden;border-radius:8px;background:#fff8ed;box-shadow:0 22px 50px rgba(56,42,29,.22);cursor:pointer;transition:.24s ease}
.card:hover{transform:translateY(-8px) scale(1.04);box-shadow:0 34px 76px rgba(56,42,29,.32);z-index:3}
.card iframe{width:1920px;height:1080px;border:0;transform-origin:top left;pointer-events:none}
.num{position:absolute;left:10px;bottom:10px;padding:5px 9px;border-radius:999px;background:rgba(33,27,22,.76);color:#fff;font-size:12px;letter-spacing:.04em}
.start-btn{position:fixed;right:28px;bottom:28px;z-index:50;border:0;border-radius:999px;padding:14px 26px;background:#211b16;color:#f7f0e4;font-size:16px;letter-spacing:.06em;cursor:pointer;box-shadow:0 12px 32px rgba(33,27,22,.28)}
#stage{position:fixed;top:50%;left:50%;width:1920px;height:1080px;transform-origin:top left;background:#fff;box-shadow:0 16px 70px rgba(0,0,0,.45)}
#frame{width:100%;height:100%;border:0;display:block;background:#fff}
.counter,.overview-btn{position:fixed;z-index:60;border:0;border-radius:999px;background:rgba(0,0,0,.58);color:rgba(255,255,255,.86);font-size:14px;letter-spacing:.05em}
.counter{right:22px;bottom:22px;padding:7px 14px}
.overview-btn{left:22px;top:22px;padding:8px 14px;cursor:pointer}
.nav{position:fixed;top:0;bottom:0;width:18%;z-index:40;cursor:pointer}.nav.left{left:0}.nav.right{right:0}
@media print{@page{size:1920px 1080px;margin:0}body{overflow:visible;background:#fff}.overview,.start-btn,.counter,.overview-btn,.nav,#present-ui{display:none!important}.print-stack{display:block!important}.print-stack iframe{width:1920px;height:1080px;page-break-after:always;border:0;display:block}}
</style>
</head>
<body data-mode="overview">
<main class="overview"><div class="overview-title">AI Debate Arena · 优化项目报告 · 点击任意页进入演示</div><div class="wall" id="wall"></div></main>
<button class="start-btn" id="startBtn">开始演示</button>
<section id="present-ui"><div id="stage"><iframe id="frame" src="about:blank"></iframe></div><button class="overview-btn" id="overviewBtn">概览</button><div class="nav left" id="prev"></div><div class="nav right" id="next"></div><div class="counter" id="counter"></div></section>
<div class="print-stack" id="printStack" style="display:none;"></div>
<script>
(function(){const deck=window.DECK_MANIFEST,W=window.DECK_WIDTH,H=window.DECK_HEIGHT,wall=document.getElementById("wall"),stage=document.getElementById("stage"),frame=document.getElementById("frame"),counter=document.getElementById("counter"),printStack=document.getElementById("printStack");let current=Number(localStorage.getItem("ai-debate-report-current")||0);function buildOverview(){wall.innerHTML="";deck.forEach((item,idx)=>{const card=document.createElement("div");card.className="card";const iframe=document.createElement("iframe");iframe.src=item.file;card.appendChild(iframe);const num=document.createElement("div");num.className="num";num.textContent=idx+1+" · "+item.label;card.appendChild(num);card.addEventListener("click",()=>{current=idx;present()});wall.appendChild(card)});requestAnimationFrame(resizeOverviewCards)}function resizeOverviewCards(){document.querySelectorAll(".card iframe").forEach((iframe)=>{const rect=iframe.parentElement.getBoundingClientRect();iframe.style.transform="scale("+(rect.width/W)+")"})}function fit(){const scale=Math.min(window.innerWidth/W,window.innerHeight/H);stage.style.transform="translate("+(-W*scale/2)+"px, "+(-H*scale/2)+"px) scale("+scale+")"}function show(idx){current=Math.max(0,Math.min(deck.length-1,idx));localStorage.setItem("ai-debate-report-current",String(current));frame.src=deck[current].file;counter.textContent=(current+1)+" / "+deck.length+" · "+deck[current].label}function present(){document.body.dataset.mode="present";fit();show(current)}function overview(){document.body.dataset.mode="overview";buildOverview()}function go(delta){if(document.body.dataset.mode!=="present")return;show(current+delta)}function buildPrintStack(){printStack.innerHTML="";deck.forEach((item)=>{const iframe=document.createElement("iframe");iframe.src=item.file;printStack.appendChild(iframe)})}document.getElementById("startBtn").addEventListener("click",present);document.getElementById("overviewBtn").addEventListener("click",overview);document.getElementById("prev").addEventListener("click",()=>go(-1));document.getElementById("next").addEventListener("click",()=>go(1));window.addEventListener("resize",()=>{fit();resizeOverviewCards()});window.addEventListener("beforeprint",buildPrintStack);window.addEventListener("keydown",(event)=>{if(event.key==="Escape")overview();if(event.key==="ArrowRight"||event.key===" "||event.key==="PageDown")go(1);if(event.key==="ArrowLeft"||event.key==="PageUp")go(-1);if(event.key==="Home"){current=0;present()}if(event.key==="End"){current=deck.length-1;present()}if(event.key.toLowerCase()==="p")window.print()});buildOverview()})();
</script>
</body>
</html>
`;

const manifest = slides.map(({ file, label, section, title }) => ({ file, label, section, title }));

fs.writeFileSync(path.join(sharedDir, "tokens.css"), css, "utf8");
for (const slide of slides) {
  fs.writeFileSync(path.join(slidesDir, slide.file), renderSlide(slide), "utf8");
}
fs.writeFileSync(path.join(root, "index.html"), indexHtml, "utf8");
fs.writeFileSync(path.join(root, "deck-manifest.json"), JSON.stringify(manifest, null, 2), "utf8");

console.log(`Generated ${slides.length} slides in ${root}`);
