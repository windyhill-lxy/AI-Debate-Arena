import { useLocation, useParams } from "react-router-dom";
import GuestJoinFlow from "./GuestJoinFlow.jsx";
import HostJoinFlow from "./HostJoinFlow.jsx";
import { isHostDesktop } from "../utils/visitContext.js";

export default function JoinRoom() {
  const { id, sessionId: sessionParam } = useParams();
  const location = useLocation();
  const isSessionEntry = Boolean(sessionParam) || location.pathname.includes("/join/session/");
  const sessionId = sessionParam || (isSessionEntry ? id : null);
  const debateRouteId = isSessionEntry ? null : id;
  const fromCreate = Boolean(location.state?.fromCreate);
  const isHost = fromCreate && isHostDesktop();

  if (isHost && debateRouteId) {
    return <HostJoinFlow debateId={debateRouteId} initialTopic={location.state?.topic} />;
  }

  return <GuestJoinFlow sessionId={sessionId} debateRouteId={debateRouteId} />;
}
