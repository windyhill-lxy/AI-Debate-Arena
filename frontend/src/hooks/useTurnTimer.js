import { useEffect, useState } from "react";

export function useTurnTimer({ enabled, seconds, running }) {
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    setLeft(seconds);
  }, [seconds, enabled]);

  useEffect(() => {
    if (!enabled || !running) return undefined;
    const timer = setInterval(() => {
      setLeft((value) => Math.max(0, value - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [enabled, running]);

  return left;
}
