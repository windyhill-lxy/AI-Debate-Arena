import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Users } from "lucide-react";
import OnlineSimplePanel from "../components/OnlineSimplePanel.jsx";
import { API_BASE } from "../utils/apiBase.js";
import "../styles/home.css";

export default function OnlineLobby() {
  const [rooms, setRooms] = useState([]);
  const [topic, setTopic] = useState("人工智能是否会提升青少年的综合学习能力");

  useEffect(() => {
    let stopped = false;
    async function loadRooms() {
      try {
        const response = await fetch(`${API_BASE}/api/debates/online-lobby`);
        if (!response.ok) return;
        const data = await response.json();
        if (!stopped) setRooms(data.rooms || []);
      } catch {
        if (!stopped) setRooms([]);
      }
    }
    loadRooms();
    const timer = setInterval(loadRooms, 5000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  return (
    <div className="home-page">
      <header className="home-nav">
        <div className="home-logo">
          <Users size={20} />
          <span>联机</span>
        </div>
        <Link to="/welcome" className="home-admin-link">
          返回模式选择
        </Link>
      </header>

      <OnlineSimplePanel variant="lobby" topic={topic} onTopicChange={setTopic} rooms={rooms} />
    </div>
  );
}
