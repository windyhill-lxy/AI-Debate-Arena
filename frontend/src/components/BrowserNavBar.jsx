import { ChevronLeft, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function BrowserNavBar({ onBeforeBack, onBeforeForward, variant = "default" }) {
  const navigate = useNavigate();

  function tryNavigate(delta) {
    const handler = delta < 0 ? onBeforeBack : onBeforeForward;
    if (handler && handler() === false) return;
    navigate(delta);
  }

  if (variant === "dock") {
    return (
      <nav className="browser-nav browser-nav--dock" aria-label="页面导航">
        <button type="button" className="browser-nav__btn" title="后退" onClick={() => tryNavigate(-1)}>
          <ChevronLeft size={16} />
        </button>
        <button type="button" className="browser-nav__btn" title="前进" onClick={() => tryNavigate(1)}>
          <ChevronRight size={16} />
        </button>
      </nav>
    );
  }

  return (
    <nav className="browser-nav" aria-label="页面导航">
      <button type="button" className="browser-nav__btn" title="后退" onClick={() => tryNavigate(-1)}>
        <ChevronLeft size={18} />
      </button>
      <button type="button" className="browser-nav__btn" title="前进" onClick={() => tryNavigate(1)}>
        <ChevronRight size={18} />
      </button>
    </nav>
  );
}
