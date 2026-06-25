import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Link2 } from "lucide-react";
import GuestShell from "../components/GuestShell.jsx";
import { parseJoinTarget } from "../utils/onlineInvite.js";
import "../styles/home.css";

export default function GuestLinkLanding() {
  const navigate = useNavigate();
  const [input, setInput] = useState("");
  const [hint, setHint] = useState("");

  function goJoin() {
    const target = parseJoinTarget(input);
    if (!target?.id) {
      setHint("请粘贴房主发来的完整邀请链接");
      return;
    }
    if (target.kind === "session") {
      navigate(`/join/session/${encodeURIComponent(target.id)}`);
      return;
    }
    navigate(`/join/${encodeURIComponent(target.id)}`);
  }

  return (
    <GuestShell>
      <div className="guest-landing">
        <div className="guest-landing__card">
          <Link2 size={28} className="guest-landing__icon" />
          <h1>加入联机辩论</h1>
          <p>请粘贴房主发来的<strong>完整邀请链接</strong>（必须含 <code>/join/session/</code>），不要只打开 ngrok 域名。</p>
          <label className="guest-landing__field">
            邀请链接
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="https://…/join/session/…"
              autoComplete="off"
            />
          </label>
          {hint && <p className="guest-landing__hint">{hint}</p>}
          <button type="button" className="online-simple__primary" onClick={goJoin}>
            进入等待页
          </button>
          <p className="guest-landing__micro">
            若页面无法打开，请确认房主程序仍在运行，并请房主重新复制链接。
          </p>
        </div>
      </div>
    </GuestShell>
  );
}
