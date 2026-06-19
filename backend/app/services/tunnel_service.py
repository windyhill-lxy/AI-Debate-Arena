"""公网隧道管理：默认 ngrok（更稳定），备选 Cloudflare Quick Tunnel。"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from app.services import tunnel_ngrok

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
_CLOUDFLARED_RELEASE = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
_CF_API_PROBE = "https://api.trycloudflare.com/"

_lock = threading.Lock()
_process: subprocess.Popen[str] | None = None
_public_url: str | None = None
_error: str | None = None
_log_thread: threading.Thread | None = None
_watchdog_thread: threading.Thread | None = None
_log_path: Path | None = None
_log_handle = None
_runtime_proxy: str | None = None
_active_provider: str = "ngrok"
_proxy_file = lambda: _project_root() / "tools" / "tunnel-proxy.json"
_settings_file = lambda: _project_root() / "tools" / "tunnel-settings.json"
_remote_probe_cache: dict[str, object] = {"url": None, "ok": False, "at": 0.0}
_PROBE_TTL_SEC = 25.0
_TIMEOUT_LOCAL = 1.5
_TIMEOUT_CF_API = 3.0
_TIMEOUT_REMOTE = 4.0


def get_tunnel_proxy() -> str | None:
    global _runtime_proxy
    if _runtime_proxy:
        return _runtime_proxy
    for key in ("TUNNEL_HTTP_PROXY", "TUNNEL_HTTPS_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        from app.core.config import get_settings

        settings = get_settings()
        for value in (settings.tunnel_http_proxy, settings.tunnel_https_proxy):
            if value and str(value).strip():
                return str(value).strip()
    except Exception:
        pass
    path = _proxy_file()
    if path.is_file():
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            saved = (data.get("proxy") or "").strip()
            if saved:
                _runtime_proxy = saved
                return saved
        except Exception:
            pass
    return None


def set_tunnel_proxy(proxy: str | None) -> str | None:
    global _runtime_proxy
    cleaned = (proxy or "").strip() or None
    _runtime_proxy = cleaned
    path = _proxy_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    if cleaned:
        path.write_text(json.dumps({"proxy": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
        os.environ["TUNNEL_HTTP_PROXY"] = cleaned
        os.environ["TUNNEL_HTTPS_PROXY"] = cleaned
    elif path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
        os.environ.pop("TUNNEL_HTTP_PROXY", None)
        os.environ.pop("TUNNEL_HTTPS_PROXY", None)
    return cleaned


def _urlopen(req: urllib.request.Request, timeout: float = 8):
    proxy = get_tunnel_proxy()
    if proxy:
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        return opener.open(req, timeout=timeout)
    return urllib.request.urlopen(req, timeout=timeout)


def _subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    proxy = get_tunnel_proxy()
    if proxy:
        env["HTTP_PROXY"] = proxy
        env["HTTPS_PROXY"] = proxy
        env["http_proxy"] = proxy
        env["https_proxy"] = proxy
    return env


@dataclass
class TunnelStatus:
    running: bool
    url: str | None
    error: str | None
    provider: str = "ngrok"
    local_url: str = "http://127.0.0.1:5173"
    healthy: bool = False
    remote_reachable: bool = False
    ngrok_configured: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def get_tunnel_provider() -> str:
    for key in ("TUNNEL_PROVIDER",):
        value = os.environ.get(key, "").strip().lower()
        if value in {"ngrok", "cloudflare", "auto"}:
            return value
    path = _settings_file()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            value = (data.get("provider") or "").strip().lower()
            if value in {"ngrok", "cloudflare", "auto"}:
                return value
        except Exception:
            pass
    try:
        from app.core.config import get_settings

        settings = get_settings()
        if getattr(settings, "tunnel_provider", None):
            value = str(settings.tunnel_provider).strip().lower()
            if value in {"ngrok", "cloudflare", "auto"}:
                return value
    except Exception:
        pass
    return "auto"


def set_tunnel_provider(provider: str) -> str:
    value = (provider or "auto").strip().lower()
    if value not in {"ngrok", "cloudflare", "auto"}:
        value = "auto"
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, str] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    data["provider"] = value
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return value


def _resolve_provider() -> str:
    pref = get_tunnel_provider()
    has_ngrok = bool(tunnel_ngrok.get_ngrok_authtoken())
    if pref == "ngrok":
        return "ngrok"
    if pref == "cloudflare":
        return "cloudflare-quick"
    return "ngrok" if has_ngrok else "cloudflare-quick"


def list_providers() -> dict[str, object]:
    has_ngrok = bool(tunnel_ngrok.get_ngrok_authtoken())
    return {
        "current": get_tunnel_provider(),
        "active": _active_provider,
        "ngrok_configured": has_ngrok,
        "options": [
            {
                "id": "ngrok",
                "label": "ngrok（推荐，更稳定）",
                "requires_token": True,
                "ready": has_ngrok,
            },
            {
                "id": "cloudflare",
                "label": "Cloudflare 临时隧道（免注册，易断开）",
                "requires_token": False,
                "ready": True,
            },
            {"id": "auto", "label": "自动（有 ngrok token 用 ngrok，否则 Cloudflare）", "requires_token": False, "ready": True},
        ],
    }


def _project_root() -> Path:
    custom = os.environ.get("DEBATE_PROJECT_ROOT", "").strip()
    return Path(custom) if custom else _PROJECT_ROOT


def _cloudflared_path() -> Path:
    override = os.environ.get("CLOUDFLARED_PATH", "").strip()
    if override:
        return Path(override)
    root = _project_root()
    for candidate in (
        root / "tools" / "cloudflared.exe",
        root / "tools" / "cloudflared",
        root.parent / "tools" / "cloudflared.exe",
    ):
        if candidate.is_file():
            return candidate
    return root / "tools" / "cloudflared.exe"


def _tunnel_log_path() -> Path:
    return _project_root() / "tools" / "cloudflared-tunnel.log"


def ensure_cloudflared() -> Path:
    path = _cloudflared_path()
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("downloading cloudflared to %s", path)
    tmp = path.with_suffix(".exe.download")
    with urllib.request.urlopen(_CLOUDFLARED_RELEASE, timeout=120) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(path)
    return path


def _origin_reachable(url: str, timeout: float | None = None) -> bool:
    probe = url.rstrip("/") + "/"
    try:
        req = urllib.request.Request(probe, method="GET")
        with _urlopen(req, timeout=timeout or _TIMEOUT_LOCAL) as resp:
            return resp.status < 500
    except Exception:
        return False


def _remote_tunnel_reachable(public_url: str, timeout: float | None = None) -> bool:
    if not public_url:
        return False
    now = time.time()
    cached_url = _remote_probe_cache.get("url")
    if cached_url == public_url and now - float(_remote_probe_cache.get("at") or 0) < _PROBE_TTL_SEC:
        return bool(_remote_probe_cache.get("ok"))
    probe = public_url.rstrip("/") + "/"
    ok = False
    try:
        req = urllib.request.Request(
            probe,
            method="GET",
            headers={"User-Agent": "AI-Debate-Tunnel-Probe/1.0"},
        )
        with _urlopen(req, timeout=timeout or _TIMEOUT_REMOTE) as resp:
            ok = resp.status < 500
    except Exception:
        ok = False
    _remote_probe_cache.update({"url": public_url, "ok": ok, "at": now})
    return ok


def _cloudflare_api_reachable(timeout: float | None = None) -> tuple[bool, str | None]:
    try:
        req = urllib.request.Request(_CF_API_PROBE, method="HEAD")
        with _urlopen(req, timeout=timeout or _TIMEOUT_CF_API) as resp:
            if resp.status < 500:
                return True, None
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            return True, None
    except Exception as exc:
        message = str(exc)
        if "timed out" in message.lower() or "timeout" in message.lower():
            return (
                False,
                "无法连接 Cloudflare 隧道服务（api.trycloudflare.com 超时）。"
                "请检查网络、防火墙或代理；中国大陆网络可能无法使用公网穿透，请改用局域网联机。",
            )
        return False, f"无法连接 Cloudflare 隧道服务：{message}"
    return False, "无法连接 Cloudflare 隧道服务，请稍后重试或改用局域网联机。"


def _tail_log(max_lines: int = 12) -> str:
    path = _log_path or _tunnel_log_path()
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _watch_log_for_url(path: Path) -> None:
    global _public_url
    last_size = 0
    while True:
        with _lock:
            proc = _process
        if proc is None or proc.poll() is not None:
            return
        try:
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="replace")
                if len(text) > last_size:
                    last_size = len(text)
                    matches = _URL_PATTERN.findall(text)
                    if matches:
                        with _lock:
                            _public_url = matches[-1]
        except Exception:
            pass
        time.sleep(0.2)


def _watchdog() -> None:
    global _error, _public_url, _process
    while True:
        time.sleep(3)
        with _lock:
            proc = _process
            url = _public_url
        if proc is None:
            return
        if proc.poll() is not None:
            tail = _tail_log(6)
            with _lock:
                _error = (
                    "cloudflared 已退出，公网链接已失效（Cloudflare 1033）。"
                    "请保持程序运行并重新开启公网隧道、复制新链接。"
                )
                if "context deadline exceeded" in tail or "failed to request quick Tunnel" in tail:
                    _error = (
                        "无法向 Cloudflare 申请隧道（网络超时）。"
                        "请检查网络或改用局域网联机；旧链接将显示 1033 错误。"
                    )
                elif tail:
                    _error = f"{_error}\n最近日志：{tail.splitlines()[-1]}"
                _process = None
                _public_url = None
            return
        # 远程探测由 /verify 或复制链接触发，避免后台线程拖慢接口


def _read_active_tunnel() -> tuple[bool, str | None, str | None, str]:
    global _active_provider, _error
    if tunnel_ngrok.is_running():
        if tunnel_ngrok.is_healthy():
            _active_provider = "ngrok"
            return True, tunnel_ngrok.get_url(), tunnel_ngrok.get_error(), "ngrok"
        with _lock:
            if not _error:
                _error = "ngrok 隧道已离线（ERR_NGROK_3200）。请保持程序运行并重新复制公网链接。"
    with _lock:
        running = _process is not None and _process.poll() is None
        url = _public_url if running else None
        error = _error
        if _process is not None and _process.poll() is not None:
            running = False
            url = None
    if running and url:
        _active_provider = "cloudflare-quick"
        return running, url, error, "cloudflare-quick"
    return False, None, error or tunnel_ngrok.get_error(), _active_provider


def get_status(*, probe_remote: bool = False) -> TunnelStatus:
    running, url, error, provider = _read_active_tunnel()
    local = os.environ.get("TUNNEL_LOCAL_URL", "http://127.0.0.1:5173")
    local_ok = _origin_reachable(local) if running else False
    remote_ok = bool(url and _remote_tunnel_reachable(url)) if probe_remote and url else False
    healthy = running and bool(url) and local_ok and (remote_ok if probe_remote else True)
    return TunnelStatus(
        running=running,
        url=url,
        error=error,
        provider=provider,
        local_url=local,
        healthy=healthy,
        remote_reachable=remote_ok,
        ngrok_configured=bool(tunnel_ngrok.get_ngrok_authtoken()),
    )


def stop_tunnel() -> TunnelStatus:
    global _process, _public_url, _error, _log_thread, _watchdog_thread, _log_handle, _log_path, _active_provider
    tunnel_ngrok.stop()
    with _lock:
        if _process and _process.poll() is None:
            _process.terminate()
            try:
                _process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                _process.kill()
        if _log_handle:
            try:
                _log_handle.close()
            except Exception:
                pass
        _log_handle = None
        _process = None
        _public_url = None
        _error = None
        _log_thread = None
        _watchdog_thread = None
    return get_status()


def _start_cloudflare(target: str) -> TunnelStatus:
    global _process, _public_url, _error, _log_thread, _watchdog_thread, _log_path, _log_handle, _active_provider
    api_ok, api_error = _cloudflare_api_reachable()
    if not api_ok:
        with _lock:
            _error = api_error
        return get_status()

    stop_tunnel()

    with _lock:
        _public_url = None
        _error = None

        try:
            cloudflared = ensure_cloudflared()
        except Exception as exc:
            _error = f"无法下载 cloudflared：{exc}"
            return get_status()

        _log_path = _tunnel_log_path()
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _log_handle = _log_path.open("a", encoding="utf-8")
            _log_handle.write(f"\n--- tunnel start {time.strftime('%Y-%m-%d %H:%M:%S')} -> {target} ---\n")
            _log_handle.flush()
        except Exception as exc:
            _error = f"无法写入隧道日志：{exc}"
            return get_status()

        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        try:
            _process = subprocess.Popen(
                [
                    str(cloudflared),
                    "tunnel",
                    "--url",
                    target,
                    "--no-autoupdate",
                    "--loglevel",
                    "info",
                ],
                stdout=_log_handle,
                stderr=subprocess.STDOUT,
                env=_subprocess_env(),
                creationflags=creationflags,
            )
        except Exception as exc:
            _error = f"启动 cloudflared 失败：{exc}"
            _process = None
            if _log_handle:
                _log_handle.close()
            _log_handle = None
            return get_status()

        _log_thread = threading.Thread(target=_watch_log_for_url, args=(_log_path,), daemon=True)
        _log_thread.start()
        _watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        _watchdog_thread.start()

    # 仅等待 cloudflared 输出公网 URL，不做慢速远程探测
    deadline = time.time() + 25.0
    while time.time() < deadline:
        with _lock:
            proc_alive = _process is not None and _process.poll() is None
            url = _public_url
        if url and proc_alive:
            with _lock:
                _error = None
            _active_provider = "cloudflare-quick"
            return get_status()
        if not proc_alive:
            with _lock:
                tail = _tail_log(8)
                if not _error:
                    _error = "cloudflared 已退出，请查看 tools/cloudflared-tunnel.log"
                if "context deadline exceeded" in tail or "failed to request quick Tunnel" in tail:
                    _error = (
                        "无法向 Cloudflare 申请隧道（网络超时）。"
                        "公网穿透需要能访问 Cloudflare；请改用局域网联机，或改善网络后重试。"
                    )
            return get_status()
        time.sleep(0.2)

    with _lock:
        if not _public_url:
            _error = "等待公网地址超时。请检查网络能否访问 Cloudflare，或改用局域网联机。"
    _active_provider = "cloudflare-quick"
    return get_status()


def start_tunnel(local_url: str | None = None, *, force: bool = False) -> TunnelStatus:
    global _active_provider
    target = (local_url or os.environ.get("TUNNEL_LOCAL_URL") or "http://127.0.0.1:5173").strip()

    if force:
        stop_tunnel()
    else:
        running, url, _, provider = _read_active_tunnel()
        if running and url and (provider != "ngrok" or tunnel_ngrok.is_healthy()):
            return get_status()

    if not _origin_reachable(target):
        with _lock:
            global _error
            _error = (
                f"本地页面服务未响应（{target}）。"
                "请先启动 AI辩论场程序，确认窗口已打开且 5173 端口正常，再开启公网隧道。"
            )
        return get_status()

    provider = _resolve_provider()
    if provider == "ngrok":
        url, err = tunnel_ngrok.start(target, subprocess_env=_subprocess_env(), force=force)
        if url:
            _active_provider = "ngrok"
            with _lock:
                _error = None
            return get_status()
        with _lock:
            _error = err
        if get_tunnel_provider() == "auto":
            return _start_cloudflare(target)
        return get_status()

    return _start_cloudflare(target)


def verify_tunnel() -> TunnelStatus:
    """深度校验（含远程探测），仅在用户主动验证时调用。"""
    global _error
    status = get_status(probe_remote=True)
    if not status.running or not status.url:
        with _lock:
            if status.provider == "ngrok" or tunnel_ngrok.get_ngrok_authtoken():
                _error = (
                    "公网隧道已离线（同学会看到 ERR_NGROK_3200）。"
                    "请保持 AI辩论场 窗口不要关闭，并重新点击「复制公网邀请链接」。"
                )
            elif not _error:
                _error = "公网隧道未开启或已断开。"
        return get_status(probe_remote=True)
    if status.remote_reachable:
        with _lock:
            _error = None
        return get_status(probe_remote=True)
    if not status.remote_reachable:
        with _lock:
            if status.provider == "ngrok":
                _error = (
                    "ngrok 公网地址暂未响应（ERR_NGROK_3200）。"
                    "请确认程序仍在运行，然后重新复制公网链接。"
                )
            else:
                _error = "公网地址暂未响应，同学可能看到 1033。可稍后重试或检查代理/VPN。"
    return status
