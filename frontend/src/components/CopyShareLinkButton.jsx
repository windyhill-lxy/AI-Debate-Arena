import { useCallback, useState } from "react";
import { Check, Link2 } from "lucide-react";
import { useErrorDialog } from "./ErrorDialogProvider.jsx";
import { buildJoinUrl, buildShareUrl, copyJoinUrl, copyShareUrl } from "../utils/shareLink.js";

export default function CopyShareLinkButton({
  debateId,
  className = "export-md-btn",
  label = "复制分享链接",
  type = "share",
}) {
  const { reportError } = useErrorDialog();
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");

  const onCopy = useCallback(async () => {
    if (!debateId || debateId === "demo-room") return;
    setError("");
    try {
      if (type === "join") await copyJoinUrl(debateId);
      else await copyShareUrl(debateId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch (e) {
      setError(e.message || "复制失败");
      reportError({
        title: "复制链接失败",
        message: e.message || "复制失败",
        source: `CopyShareLinkButton.${type}`,
      });
    }
  }, [debateId, reportError, type]);

  if (!debateId || debateId === "demo-room") return null;

  return (
    <span className="copy-share-wrap">
      <button
        type="button"
        className={className}
        onClick={onCopy}
        title={type === "join" ? buildJoinUrl(debateId) : buildShareUrl(debateId)}
      >
        {copied ? <Check size={14} /> : <Link2 size={14} />}
        {copied ? "已复制" : label}
      </button>
      {error && <span className="copy-share-error">{error}</span>}
    </span>
  );
}
