"""ngrok 隧道（比 Cloudflare Quick Tunnel 更稳定，需免费注册获取 authtoken）。"""

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
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_NGROK_ZIP_URL = "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip"
_NGROK_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.(?:ngrok-free\.app|ngrok-free\.dev|ngrok\.io)", re.I)
_NGROK_API = "http://127.0.0.1:4040/api/tunnels"

_process: subprocess.Popen[str] | None = None
_public_url: str | None = None
_error: str | None = None
_log_path: Path | None = None
_log_handle = None
_watchdog_thread: threading.Thread | None = None
_last_port: int | None = None
_last_subprocess_env: dict[str, str] | None = None
_restart_attempts = 0
_max_restart_attempts = 3
_lock = threading.Lock()


def _project_root() -> Path:
    custom = os.environ.get("DEBATE_PROJECT_ROOT", "").strip()
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parents[3]


def _ngrok_path() -> Path:
    override = os.environ.get("NGROK_PATH", "").strip()
    if override:
        return Path(override)
    return _project_root() / "tools" / "ngrok.exe"


def _settings_path() -> Path:
    return _project_root() / "tools" / "tunnel-settings.json"


def get_ngrok_authtoken() -> str | None:
    for key in ("NGROK_AUTHTOKEN", "NGROK_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    try:
        from app.core.config import get_settings

        settings = get_settings()
        if getattr(settings, "ngrok_authtoken", None):
            token = str(settings.ngrok_authtoken).strip()
            if token:
                return token
    except Exception:
        pass
    path = _settings_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            token = (data.get("ngrok_authtoken") or "").strip()
            if token:
                return token
        except Exception:
            pass
    return None


def set_ngrok_authtoken(token: str | None) -> str | None:
    cleaned = (token or "").strip() or None
    path = _settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, str] = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    if cleaned:
        data["ngrok_authtoken"] = cleaned
        os.environ["NGROK_AUTHTOKEN"] = cleaned
    else:
        data.pop("ngrok_authtoken", None)
        os.environ.pop("NGROK_AUTHTOKEN", None)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def ensure_ngrok() -> Path:
    path = _ngrok_path()
    if path.is_file():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    zip_path = path.with_suffix(".zip")
    logger.info("downloading ngrok to %s", path)
    with urllib.request.urlopen(_NGROK_ZIP_URL, timeout=180) as resp, zip_path.open("wb") as out:
        shutil.copyfileobj(resp, out)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("ngrok.exe"):
                with zf.open(name) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                break
    zip_path.unlink(missing_ok=True)
    if not path.is_file():
        raise RuntimeError("ngrok 解压失败")
    return path


def _parse_target_port(target: str) -> int:
    parsed = urlparse(target)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _fetch_public_url() -> str | None:
    try:
        with urllib.request.urlopen(_NGROK_API, timeout=2) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tunnels = payload.get("tunnels") or []
    https_url = None
    http_url = None
    for tunnel in tunnels:
        url = tunnel.get("public_url") or ""
        if not url:
            continue
        if url.startswith("https://"):
            https_url = url
        elif url.startswith("http://"):
            http_url = url
    return https_url or http_url


def _kill_tracked_ngrok() -> None:
    """仅终止本应用启动的 ngrok 进程。"""
    global _process
    with _lock:
        proc = _process
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    with _lock:
        if _process is proc:
            _process = None


def _kill_all_ngrok_processes() -> None:
    """强制启动前清理残留 ngrok，避免 ERR_NGROK_334。"""
    _kill_tracked_ngrok()
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW
        subprocess.run(
            ["taskkill", "/IM", "ngrok.exe", "/F"],
            capture_output=True,
            creationflags=creationflags,
        )
    else:
        subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
    time.sleep(0.6)


def _parse_log_error(tail: str) -> str | None:
    if not tail:
        return None
    upper = tail.upper()
    if "ERR_NGROK_334" in upper:
        return "ngrok 隧道冲突（ERR_NGROK_334）。请关闭其他 ngrok 程序后，重新点击「复制公网邀请链接」。"
    if "ERR_NGROK_3200" in upper:
        return "ngrok 公网链接已离线（ERR_NGROK_3200）。请重新复制邀请链接。"
    if "authentication failed" in tail.lower() or "invalid authtoken" in tail.lower():
        return "ngrok Authtoken 无效，请重新复制并保存"
    for line in reversed(tail.splitlines()):
        cleaned = line.strip()
        if cleaned.upper().startswith("ERROR:"):
            detail = cleaned[6:].strip(" :")
            if detail:
                return detail
    last = tail.splitlines()[-1].strip()
    return last if last else None


def _tail_log(max_lines: int = 8) -> str:
    path = _log_path or (_project_root() / "tools" / "ngrok-tunnel.log")
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except Exception:
        return ""


def _spawn_ngrok_process(port: int, subprocess_env: dict[str, str]) -> bool:
    global _process, _log_handle, _error
    try:
        ngrok = ensure_ngrok()
    except Exception as exc:
        _error = f"无法下载 ngrok：{exc}"
        return False
    token = get_ngrok_authtoken()
    if not token:
        _error = "未配置 ngrok Authtoken"
        return False
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        _process = subprocess.Popen(
            [str(ngrok), "http", str(port), "--authtoken", token, "--log=stdout", "--log-format=logfmt"],
            stdout=_log_handle,
            stderr=subprocess.STDOUT,
            env=subprocess_env,
            creationflags=creationflags,
        )
        return True
    except Exception as exc:
        _error = f"启动 ngrok 失败：{exc}"
        _process = None
        return False


def _watchdog() -> None:
    global _error, _public_url, _process, _restart_attempts
    while True:
        time.sleep(4)
        with _lock:
            proc = _process
        if proc is None:
            return
        if proc.poll() is not None:
            with _lock:
                tail = _tail_log(12)
                detail = _parse_log_error(tail)
                port = _last_port
                env = _last_subprocess_env
                attempts = _restart_attempts
                _process = None
                _public_url = None
            if port is not None and env is not None and attempts < _max_restart_attempts:
                with _lock:
                    _restart_attempts += 1
                time.sleep(min(8, 2 ** attempts))
                with _lock:
                    if _spawn_ngrok_process(port, env):
                        continue
            with _lock:
                _error = detail or "ngrok 已退出，公网链接失效。请重新复制邀请链接。"
            return


def is_running() -> bool:
    with _lock:
        return _process is not None and _process.poll() is None


def sync_public_url() -> str | None:
    """从 ngrok 本地 API 同步公网地址；进程已退出时返回 None。"""
    global _public_url, _error, _process
    if not is_running():
        return None
    url = _fetch_public_url()
    if not url and _log_path and _log_path.is_file():
        try:
            match = _NGROK_URL_PATTERN.search(_log_path.read_text(encoding="utf-8", errors="replace"))
            if match:
                url = match.group(0)
        except Exception:
            pass
    with _lock:
        if url:
            _public_url = url
            _error = None
            return url
        if _process is not None and _process.poll() is None:
            _error = "ngrok 进程在运行但未获取到公网地址"
        return _public_url


def is_healthy() -> bool:
    """进程存活且本地 agent 已注册隧道。"""
    if not is_running():
        return False
    return bool(sync_public_url())


def get_url() -> str | None:
    if not is_running():
        return None
    return sync_public_url()


def get_error() -> str | None:
    with _lock:
        return _error


def stop() -> None:
    global _process, _public_url, _error, _log_handle, _watchdog_thread, _log_path
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
        _watchdog_thread = None


def start(target: str, *, subprocess_env: dict[str, str], force: bool = False) -> tuple[str | None, str | None]:
    """返回 (public_url, error)。"""
    global _process, _public_url, _error, _log_handle, _watchdog_thread, _log_path
    global _last_port, _last_subprocess_env, _restart_attempts

    token = get_ngrok_authtoken()
    if not token:
        return None, (
            "未配置 ngrok。请到 https://dashboard.ngrok.com/get-started/your-authtoken "
            "免费注册并复制 Authtoken，在联机页保存后重试。"
        )

    if is_running() and is_healthy():
        with _lock:
            return _public_url, None

    stop()
    if force:
        _kill_all_ngrok_processes()
    else:
        _kill_tracked_ngrok()

    port = _parse_target_port(target)
    _last_port = port
    _last_subprocess_env = dict(subprocess_env)
    _restart_attempts = 0
    _log_path = _project_root() / "tools" / "ngrok-tunnel.log"
    _log_path.parent.mkdir(parents=True, exist_ok=True)

    with _lock:
        _public_url = None
        _error = None
        try:
            _log_handle = _log_path.open("a", encoding="utf-8")
            _log_handle.write(f"\n--- ngrok start {time.strftime('%Y-%m-%d %H:%M:%S')} port {port} ---\n")
            _log_handle.flush()
        except Exception as exc:
            return None, f"无法写入 ngrok 日志：{exc}"

        if not _spawn_ngrok_process(port, subprocess_env):
            if _log_handle:
                _log_handle.close()
            _log_handle = None
            return None, _error or "启动 ngrok 失败"

        _watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
        _watchdog_thread.start()

    deadline = time.time() + 20.0
    while time.time() < deadline:
        url = _fetch_public_url()
        if not url:
            with _lock:
                if _log_path and _log_path.is_file():
                    text = _log_path.read_text(encoding="utf-8", errors="replace")
                    match = _NGROK_URL_PATTERN.search(text)
                    if match:
                        url = match.group(0)
        if url and is_running():
            with _lock:
                _public_url = url
                _error = None
            return url, None
        if not is_running():
            with _lock:
                tail = _tail_log(12)
                err = _parse_log_error(tail) or "ngrok 启动失败"
                _error = err
            return None, _error
        time.sleep(0.25)

    with _lock:
        _error = "等待 ngrok 公网地址超时"
    return None, _error
