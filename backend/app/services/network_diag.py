"""联机网络诊断：Cloudflare、本地端口、代理与防火墙提示。"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from app.services import tunnel_ngrok
from app.services.tunnel_service import (
    _cloudflare_api_reachable,
    _cloudflared_path,
    _origin_reachable,
    _project_root,
    _tail_log,
    get_status,
    get_tunnel_proxy,
)

_LOCAL_FRONTEND = os.environ.get("TUNNEL_LOCAL_URL", "http://127.0.0.1:5173")
_DIAG_CACHE: dict[str, object] = {"at": 0.0, "payload": None}
_DIAG_TTL_SEC = 8.0


def _check(name: str, ok: bool, detail: str, fix: str = "") -> dict[str, object]:
    return {"name": name, "ok": ok, "detail": detail, "fix": fix}


def _tcp_port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _dns_resolve(host: str) -> tuple[bool, str]:
    try:
        socket.setdefaulttimeout(2.0)
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        addrs = sorted({item[4][0] for item in infos})
        return True, ", ".join(addrs[:3])
    except OSError as exc:
        return False, str(exc)


def _firewall_rules_present() -> tuple[bool, str]:
    if sys.platform != "win32":
        return True, "非 Windows，请自行配置防火墙"
    try:
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=AI辩论场-页面5173"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        text = (result.stdout or "") + (result.stderr or "")
        if "AI辩论场-页面5173" in text and "没有与指定标准相匹配的规则" not in text:
            return True, "已检测到防火墙入站规则（5173）"
        return False, "未检测到项目防火墙规则，建议以管理员运行「配置联机网络.bat」"
    except Exception as exc:
        return False, f"无法查询防火墙：{exc}"


def run_network_diagnose(*, quick: bool = True) -> dict[str, object]:
    now = time.time()
    cached = _DIAG_CACHE.get("payload")
    if quick and cached and now - float(_DIAG_CACHE.get("at") or 0) < _DIAG_TTL_SEC:
        return cached  # type: ignore[return-value]

    cf_timeout = 2.5 if quick else 3.0
    tasks: dict[str, object] = {}

    def job_fe_port():
        return _tcp_port_open("127.0.0.1", 5173, timeout=1.0)

    def job_be_port():
        return _tcp_port_open("127.0.0.1", 9000, timeout=1.0)

    def job_fe_http():
        return _origin_reachable(_LOCAL_FRONTEND, timeout=1.5)

    def job_dns():
        return _dns_resolve("api.trycloudflare.com")

    def job_api():
        return _cloudflare_api_reachable(timeout=cf_timeout)

    def job_fw():
        return _firewall_rules_present()

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {
            pool.submit(job_fe_port): "fe_open",
            pool.submit(job_be_port): "be_open",
            pool.submit(job_fe_http): "fe_http",
            pool.submit(job_dns): "dns",
            pool.submit(job_api): "api",
            pool.submit(job_fw): "fw",
        }
        for future in as_completed(futures, timeout=6):
            key = futures[future]
            try:
                tasks[key] = future.result()
            except Exception as exc:
                tasks[key] = exc

    fe_open = bool(tasks.get("fe_open"))
    be_open = bool(tasks.get("be_open"))
    fe_http = bool(tasks.get("fe_http"))
    dns_result = tasks.get("dns") if isinstance(tasks.get("dns"), tuple) else (False, "超时")
    dns_ok, dns_detail = dns_result  # type: ignore[misc]
    api_result = tasks.get("api") if isinstance(tasks.get("api"), tuple) else (False, "检测超时")
    api_ok, api_err = api_result  # type: ignore[misc]
    fw_result = tasks.get("fw") if isinstance(tasks.get("fw"), tuple) else (False, "检测超时")
    fw_ok, fw_detail = fw_result  # type: ignore[misc]

    proxy = get_tunnel_proxy()
    cf_path = _cloudflared_path()
    tunnel = get_status(probe_remote=not quick)
    ngrok_ready = bool(tunnel_ngrok.get_ngrok_authtoken())

    checks: list[dict[str, object]] = [
        _check("本地页面端口 5173", fe_open, "正在监听" if fe_open else "未响应", "请启动 AI辩论场程序"),
        _check("本地 API 端口 9000", be_open, "正在监听" if be_open else "未响应", "桌面版会自动启动后端"),
        _check("本地页面 HTTP", fe_http, "可访问" if fe_http else "无法打开", "确认 5173 页面服务已启动"),
        _check("DNS 解析 api.trycloudflare.com", dns_ok, dns_detail, "可尝试 DNS 1.1.1.1 / 8.8.8.8"),
        _check("代理设置", True, proxy or "未配置（直连）", "直连失败时填写 HTTP 代理"),
        _check(
            "Cloudflare 隧道 API",
            api_ok,
            "可连接" if api_ok else (api_err or "连接失败"),
            "开启 VPN/代理或配置 TUNNEL_HTTP_PROXY",
        ),
        _check(
            "cloudflared 程序",
            cf_path.is_file(),
            str(cf_path) if cf_path.is_file() else "未找到",
            "首次开隧道会自动下载",
        ),
        _check("Windows 防火墙规则", fw_ok, fw_detail, "以管理员运行「配置联机网络.bat」"),
        _check(
            "ngrok Authtoken",
            ngrok_ready,
            "已配置（推荐）" if ngrok_ready else "未配置",
            "在联机页保存 ngrok Token，比 Cloudflare 更稳定",
        ),
        _check(
            "公网隧道状态",
            tunnel.healthy or (tunnel.running and bool(tunnel.url)),
            (
                f"运行中 · {tunnel.url}"
                if tunnel.running and tunnel.url
                else tunnel.error or "未开启"
            ),
            "保持程序运行；1033 时重新复制新链接",
        ),
    ]

    suggestions: list[str] = []
    if not ngrok_ready:
        suggestions.append(
            "推荐免费注册 ngrok 并保存 Authtoken（联机页可配置），公网链接比 trycloudflare 更稳定。"
        )
    if not api_ok and not ngrok_ready:
        suggestions.append("公网穿透需访问 Cloudflare。请配置代理/VPN，或改用局域网联机。")
    if not fe_open or not fe_http:
        suggestions.append("先确保本机 5173 页面服务正常。")
    if not fw_ok:
        suggestions.append("以管理员运行「配置联机网络.bat」。")
    if not suggestions:
        suggestions.append("基础检查完成。可复制公网链接；请保持程序窗口不要关闭。")

    payload = {
        "checks": checks,
        "suggestions": suggestions,
        "proxy": proxy,
        "tunnel": tunnel.to_dict(),
        "log_tail": _tail_log(5),
        "firewall_script": "配置联机网络.bat",
        "project_root": str(_project_root()),
        "quick": quick,
    }
    _DIAG_CACHE["at"] = now
    _DIAG_CACHE["payload"] = payload
    return payload
