import { Navigate } from "react-router-dom";
import { isGuestWeb, isHostDesktop } from "../utils/visitContext.js";
import GuestLinkLanding from "./GuestLinkLanding.jsx";
import Welcome from "./Welcome.jsx";

export default function RootEntry() {
  if (isHostDesktop()) {
    return <Navigate to="/welcome" replace />;
  }
  if (isGuestWeb("/")) {
    return <GuestLinkLanding />;
  }
  return <Welcome />;
}
