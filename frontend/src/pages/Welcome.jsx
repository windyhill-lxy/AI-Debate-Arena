import { Link } from "react-router-dom";
import { Bot, FileCheck2, Server, Users } from "lucide-react";
import "../styles/home.css";
import "../styles/guest-mobile.css";

export default function Welcome() {
  return (
    <div className="home-page welcome-page">
      <header className="home-nav">
        <div className="home-logo">
          <Bot size={20} />
          <span>AI 辩论场</span>
        </div>
      </header>

      <section className="welcome-hero">
        <h1>选择你要进行的模式</h1>
      </section>

      <div className="welcome-grid">
        <Link to="/solo" className="welcome-card welcome-card--solo">
          <Bot size={28} />
          <h2>个人辩论</h2>
          <p>AI 自主或人机对战。</p>
        </Link>
        <Link to="/training/opening" className="welcome-card welcome-card--opening">
          <FileCheck2 size={28} />
          <h2>一辩立论训练</h2>
          <p>写稿、评分、AI 循环改稿。</p>
        </Link>
        <Link to="/lobby" className="welcome-card welcome-card--online">
          <Users size={28} />
          <h2>联机对战</h2>
          <p>局域网或公网。</p>
        </Link>
        <Link to="/admin" className="welcome-card welcome-card--admin">
          <Server size={28} />
          <h2>系统管理</h2>
          <p>配置模型与密钥。</p>
        </Link>
      </div>
    </div>
  );
}
