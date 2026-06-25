export default function SystemConfigBanner({ health, healthError, apiBase }) {
  if (healthError) {
    const lanHint =
      typeof window !== "undefined" &&
      window.location.hostname &&
      !["localhost", "127.0.0.1"].includes(window.location.hostname)
        ? " 联机场景请确认服务端已启动，且防火墙已放行 9000 端口。"
        : " 单机请运行 start.bat；教室联机请运行 start-lan.bat。";
    return (
      <div className="system-banner system-banner--error" role="alert">
        无法连接后端（{healthError}）。当前 API：{apiBase || "http://127.0.0.1:9000"}。{lanHint}
      </div>
    );
  }
  if (!health) return null;

  const warnings = [];
  if (!health.deepseek_configured) {
    warnings.push("未配置 DEEPSEEK_API_KEY：AI 将使用兜底文案，无法正常辩论。");
  }
  if (health.storage === "memory") {
    warnings.push("MongoDB 未连接：房间数据保存在内存中，重启后端后会丢失。");
  }
  if (health.aliyun_tts_enabled === false) {
    warnings.push("语音合成已关闭（ALIYUN_TTS_ENABLED=false）。");
  }
  if (health.aliyun_asr_enabled !== false && health.aliyun_asr_configured === false) {
    warnings.push("语音识别未配置：请在 .env 填写 ALIYUN_AK_ID、ALIYUN_AK_SECRET、ALIYUN_ISI_APPKEY。");
  }

  if (!warnings.length) return null;

  return (
    <div className="system-banner system-banner--warn" role="status">
      {warnings.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}
