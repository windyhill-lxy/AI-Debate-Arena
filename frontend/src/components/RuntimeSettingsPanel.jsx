import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, KeyRound, Save } from "lucide-react";
import { useErrorDialog } from "./ErrorDialogProvider.jsx";
import { API_BASE } from "../utils/apiBase.js";
import { errorDialogPayload, parseHttpErrorBody } from "../utils/httpError.js";

const KEY_GROUPS = [
  {
    title: "语音输入模型",
    hint: "用于人类发言的语音识别。阿里云一句话识别需要 AccessKey 与 AppKey。",
    providers: [
      ["aliyun_ak_id", "AccessKey ID"],
      ["aliyun_ak_secret", "AccessKey Secret"],
      ["aliyun_isi_appkey", "智能语音交互 AppKey"],
    ],
  },
  {
    title: "TTS 模型",
    hint: "用于 AI 辩手朗读。当前使用阿里百炼 Qwen3-TTS。",
    providers: [["dashscope", "DashScope API Key"]],
  },
  {
    title: "LLM 模型",
    hint: "用于辩手、裁判、训练分析与 RAG 评估。",
    providers: [
      ["deepseek", "DeepSeek API Key"],
      ["qwen", "Qwen API Key"],
      ["kimi", "Kimi API Key"],
      ["minimax", "MiniMax API Key"],
    ],
  },
];

const PROVIDERS = KEY_GROUPS.flatMap((group) => group.providers.map(([provider]) => provider));

const MODEL_SEATS = [
  ["aff_1", "正方一辩"],
  ["aff_2", "正方二辩"],
  ["aff_3", "正方三辩"],
  ["aff_4", "正方四辩"],
  ["neg_1", "反方一辩"],
  ["neg_2", "反方二辩"],
  ["neg_3", "反方三辩"],
  ["neg_4", "反方四辩"],
  ["judge", "裁判"],
];

async function fetchRuntimeSettings() {
  const response = await fetch(`${API_BASE}/api/debates/runtime-settings`);
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  return response.json();
}

async function saveRuntimeSettings(settings) {
  const response = await fetch(`${API_BASE}/api/debates/runtime-settings`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(settings),
  });
  if (!response.ok) throw parseHttpErrorBody(await response.text(), response);
  return response.json();
}

export default function RuntimeSettingsPanel({ className = "" }) {
  const { reportError } = useErrorDialog();
  const [apiKeys, setApiKeys] = useState({});
  const [savedKeys, setSavedKeys] = useState({});
  const [keyMasks, setKeyMasks] = useState({});
  const [agentModels, setAgentModels] = useState({});
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [visibleKeys, setVisibleKeys] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    setHint("");
    try {
      const data = await fetchRuntimeSettings();
      setSavedKeys(data.api_keys || {});
      setKeyMasks(data.api_key_masks || {});
      setAgentModels(data.models || {});
      setApiKeys(data.api_keys || {});
    } catch (error) {
      setHint(`加载失败：${error.message || "请确认后端已启动"}`);
      reportError(errorDialogPayload(error, "加载运行设置失败", "RuntimeSettingsPanel.load", "请确认后端已启动"));
    } finally {
      setLoading(false);
    }
  }, [reportError]);

  useEffect(() => {
    load();
  }, [load]);

  async function onSave() {
    setSaving(true);
    setHint("保存中…");
    try {
      const mergedKeys = { ...savedKeys };
      for (const provider of PROVIDERS) {
        const value = (apiKeys[provider] || "").trim();
        if (value) mergedKeys[provider] = value;
      }
      const result = await saveRuntimeSettings({
        api_keys: mergedKeys,
        models: agentModels,
        defaults: {},
      });
      setSavedKeys(mergedKeys);
      setKeyMasks(result.api_key_masks || {});
      setAgentModels(result.models || {});
      setApiKeys(result.api_keys || mergedKeys);
      setHint("已保存，后续 AI 调用会使用这里的配置。");
    } catch (error) {
      setHint(`保存失败：${error.message || "请确认后端已启动"}`);
      reportError(errorDialogPayload(error, "保存运行设置失败", "RuntimeSettingsPanel.save", "请确认后端已启动"));
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={`admin-panel runtime-settings-panel ${className}`.trim()}>
      <h2>
        <KeyRound size={18} /> API Key 与模型
      </h2>
      <p className="admin-lead" style={{ fontSize: 13, marginBottom: 12 }}>
        配置生成式 AI、TTS/ASR 等服务的密钥与每位辩手使用的模型。已从 .env 或设置文件读取到的密钥会以密码形式显示。
      </p>
      {loading ? (
        <p style={{ fontSize: 13 }}>加载配置中…</p>
      ) : (
        <>
          <div className="runtime-settings-groups">
            {KEY_GROUPS.map((group) => (
              <section key={group.title} className="runtime-settings-group">
                <div>
                  <h3>{group.title}</h3>
                  <p>{group.hint}</p>
                </div>
                <div className="runtime-settings-grid">
                  {group.providers.map(([provider, label]) => (
                    <label key={provider} className="runtime-settings-field">
                      <span>{label}</span>
                      <div className="runtime-settings-secret">
                        <input
                          type={visibleKeys[provider] ? "text" : "password"}
                          value={apiKeys[provider] || ""}
                          onChange={(event) => setApiKeys((prev) => ({ ...prev, [provider]: event.target.value }))}
                          placeholder={keyMasks[provider] ? `已读取 ${keyMasks[provider]}` : "填写后保存"}
                        />
                        <button
                          type="button"
                          className="runtime-settings-eye"
                          onClick={() => setVisibleKeys((prev) => ({ ...prev, [provider]: !prev[provider] }))}
                          title={visibleKeys[provider] ? "隐藏密钥" : "显示密钥"}
                        >
                          {visibleKeys[provider] ? <EyeOff size={15} /> : <Eye size={15} />}
                        </button>
                      </div>
                      {keyMasks[provider] && <small>已读取 {keyMasks[provider]}</small>}
                    </label>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="runtime-settings-grid runtime-settings-grid--models">
            {MODEL_SEATS.map(([id, label]) => (
              <label key={id} className="runtime-settings-field">
                <span>{label}模型</span>
                <input
                  value={agentModels[id] || ""}
                  onChange={(event) => setAgentModels((prev) => ({ ...prev, [id]: event.target.value }))}
                  placeholder="deepseek-v4-pro / qwen-plus / moonshot-v1-8k"
                />
              </label>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 12, flexWrap: "wrap" }}>
            <button type="button" className="admin-btn" onClick={onSave} disabled={saving}>
              <Save size={14} /> {saving ? "保存中…" : "保存配置"}
            </button>
          </div>
        </>
      )}
      {hint && (
        <p
          style={{
            fontSize: 13,
            color: hint.includes("失败") ? "#c00" : "#2a7",
            marginTop: 8,
          }}
        >
          {hint}
        </p>
      )}
    </section>
  );
}
