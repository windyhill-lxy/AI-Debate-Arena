import { useEffect } from "react";
import { isCompactViewport } from "../utils/visitContext.js";
import "../styles/guest-mobile.css";

export default function GuestShell({ children }) {
  useEffect(() => {
    function sync() {
      document.documentElement.classList.toggle("guest-mobile", isCompactViewport());
    }
    sync();
    const mq = window.matchMedia("(max-width: 900px)");
    mq.addEventListener("change", sync);
    return () => {
      mq.removeEventListener("change", sync);
      document.documentElement.classList.remove("guest-mobile");
    };
  }, []);

  return <div className="guest-shell">{children}</div>;
}
