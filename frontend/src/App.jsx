import { useRef } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import BrowserNavBar from "./components/BrowserNavBar.jsx";
import TunnelGuestGuard from "./components/TunnelGuestGuard.jsx";
import Admin from "./pages/Admin.jsx";
import DebateRoom from "./pages/DebateRoom.jsx";
import Home from "./pages/Home.jsx";
import JoinRoom from "./pages/JoinRoom.jsx";
import OnlineLobby from "./pages/OnlineLobby.jsx";
import OpeningTraining from "./pages/OpeningTraining.jsx";
import Replay from "./pages/Replay.jsx";
import RootEntry from "./pages/RootEntry.jsx";
import Welcome from "./pages/Welcome.jsx";
import { shouldHideBrowserNav } from "./utils/visitContext.js";

function AppRoutes({ leaveGuardRef }) {
  const location = useLocation();
  const hideGlobalNav = shouldHideBrowserNav(location.pathname);
  const onBeforeNav = () => {
    if (!location.pathname.startsWith("/room/")) return true;
    return leaveGuardRef.current ? leaveGuardRef.current() : true;
  };

  return (
    <TunnelGuestGuard>
      {!hideGlobalNav && <BrowserNavBar onBeforeBack={onBeforeNav} onBeforeForward={onBeforeNav} />}
      <Routes>
        <Route path="/" element={<RootEntry />} />
        <Route path="/welcome" element={<Welcome />} />
        <Route path="/solo" element={<Home />} />
        <Route path="/training/opening" element={<OpeningTraining />} />
        <Route path="/lobby" element={<OnlineLobby />} />
        <Route path="/join/session/:sessionId" element={<JoinRoom />} />
        <Route path="/join/:id" element={<JoinRoom />} />
        <Route path="/room/:id" element={<DebateRoom leaveGuardRef={leaveGuardRef} />} />
        <Route path="/replay/:id" element={<Replay />} />
        <Route path="/share/:id" element={<Replay shareMode />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </TunnelGuestGuard>
  );
}

export default function App() {
  const leaveGuardRef = useRef(null);

  return (
    <BrowserRouter>
      <AppRoutes leaveGuardRef={leaveGuardRef} />
    </BrowserRouter>
  );
}
