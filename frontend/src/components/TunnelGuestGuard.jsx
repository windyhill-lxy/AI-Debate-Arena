import { useLocation } from "react-router-dom";
import { isHostDesktop } from "../utils/visitContext.js";
import { isTunnelHost } from "../utils/apiBase.js";
import GuestLinkLanding from "../pages/GuestLinkLanding.jsx";

const GUEST_ALLOWED_PREFIXES = ["/join/", "/room/", "/replay/", "/share/"];

export default function TunnelGuestGuard({ children }) {
  const location = useLocation();
  const hostname = typeof window !== "undefined" ? window.location.hostname : "";

  if (!isTunnelHost(hostname) || isHostDesktop()) {
    return children;
  }

  const path = location.pathname || "/";
  if (GUEST_ALLOWED_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    return children;
  }

  return <GuestLinkLanding />;
}
