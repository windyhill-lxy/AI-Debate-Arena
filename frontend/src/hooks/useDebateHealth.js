import { useEffect, useState } from "react";
import { API_BASE } from "../utils/apiBase.js";

export function useDebateHealth() {
  const [health, setHealth] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_BASE}/health`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("health failed"))))
      .then((data) => {
        if (!cancelled) {
          setHealth(data);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setHealth(null);
          setError(err.message || "无法连接后端");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { health, error, apiBase: API_BASE };
}
