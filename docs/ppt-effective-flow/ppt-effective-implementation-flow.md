# PPT有效信息页对应的 AI 辩论场实现流程

输入 PPT：`F:\PPT文件\6.26最新最新最新最新版.pptx`

本图只保留 PPT 中能映射到真实项目流程的有效信息页，并把它们放回 `AI辩论项目` 的完整运行链路中：

1. 入口与模式选择：对应 PPT 7、19 页，落到房间创建、用户加入、多人联机、席位和赛程初始化。
2. 资料入库与论据准备：对应 PPT 14、15、22 页，落到 RAG、开场论据预搜集、argument bank 和稳定编号。
3. 赛程编排与智能体工作流：对应 PPT 8、10 页，落到 formal_4v4 赛程和 LangGraph 风格工作流。
4. 队内讨论与上下文权限：对应 PPT 11、16、22 页，落到队内讨论、真人席位等待、AI 队友补充和信息权限控制。
5. 公开发言、人类介入与评分：对应 PPT 17、19、22、23 页，落到用户回合、引用校验、低质量扣分、摄像头/超时评分和自动推进。
6. 多模态与实时同步：对应 PPT 12、13、18、19 页，落到 WebSocket、ASR、TTS、摄像头监测、联机状态和错误弹窗。
7. 复盘与导出：对应 PPT 7、18、23 页，落到裁判报告、Markdown/PDF 导出、回放和管理诊断。

生成文件：

- `docs/ppt-effective-flow/ppt-effective-implementation-flow.svg`
- `docs/ppt-effective-flow/ppt-effective-implementation-flow.png`

参考项目流程底图：

- `docs/ai-debate-project-flow.mmd`
