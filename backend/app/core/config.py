from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_ENV_FILE = _PROJECT_ROOT / ".env"


def _read_loose_env_value(*keys: str) -> str | None:
    """
    从 .env 中读取非标准键写法（如 `kimi：sk-...`、`MiniMax tts:sk-...`）。
    """
    if not _ENV_FILE.exists():
        return None
    key_set = {k.strip().lower() for k in keys if k and k.strip()}
    if not key_set:
        return None
    try:
        for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            sep = None
            if "=" in line:
                sep = "="
            elif ":" in line:
                sep = ":"
            elif "：" in line:
                sep = "："
            if not sep:
                continue
            left, right = line.split(sep, 1)
            if left.strip().lower() in key_set:
                value = right.strip().strip("\"'")
                if value:
                    return value
    except OSError:
        return None
    return None


class Settings(BaseSettings):
    app_name: str = "AI Debate Arena"
    backend_host: str = "127.0.0.1"
    backend_port: int = 9000
    frontend_port: int = 5173

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_db: str = "ai_debate_arena"
    redis_url: str = "redis://localhost:6379/0"

    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    google_api_key: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-pro"
    deepseek_flash_model: str = "deepseek-v4-flash"
    # 逗号分隔；主模型与 flash 均失败时继续尝试（多模型降级）
    deepseek_fallback_models: str = ""
    # 使用 dsapi 等兼容网关时自动请求联网搜索；若网关不支持会自动降级为普通对话。
    deepseek_auto_search: bool = False

    dashscope_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    aliyun_tts_enabled: bool = True
    aliyun_tts_model: str = "qwen3-tts-instruct-flash"
    aliyun_tts_language_type: str = "Chinese"
    minimax_api_key: str | None = None
    minimax_base_url: str = "https://api.minimax.chat/v1"
    minimax_tts_model: str = "speech-01-turbo"
    minimax_tts_voice_id: str = "female-shaonv"
    minimax_model: str = "MiniMax-M2.1-highspeed"
    minimax_flash_model: str = "MiniMax-M2.1-highspeed"
    qwen_api_key: str | None = None
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_model: str = "qwen-plus"
    qwen_flash_model: str = "qwen-turbo"
    kimi_api_key: str | None = None
    kimi_base_url: str = "https://api.moonshot.cn/v1"
    kimi_model: str = "moonshot-v1-8k"
    kimi_flash_model: str = "moonshot-v1-8k"
    aliyun_asr_enabled: bool = True
    aliyun_ak_id: str | None = None
    aliyun_ak_secret: str | None = None
    aliyun_isi_appkey: str | None = None
    nls_app_key: str | None = None
    aliyun_asr_region: str = "cn-shanghai"
    aliyun_asr_sample_rate: int = 16000
    aliyun_asr_endpoint: str = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
    aliyun_token_endpoint: str = "https://nls-meta.cn-shanghai.aliyuncs.com/"

    rag_top_k: int = 4
    schedule_template: str = "formal_4v4"
    # 逗号分隔 phase，仅这些环节合成 TTS（轻量化默认）
    tts_phases: str = "opening_statement,cross_examination,closing,post_match"
    debate_turn_seconds: int = 90

    log_level: str = "INFO"
    api_rate_limit_create_per_min: int = 30
    api_rate_limit_write_per_min: int = 120
    # 公网隧道 HTTP 代理，如 http://127.0.0.1:7890（Clash/V2Ray 本地端口）
    tunnel_http_proxy: str | None = None
    tunnel_https_proxy: str | None = None
    tunnel_provider: str = "auto"
    ngrok_authtoken: str | None = None
    # 逗号分隔；生产部署时改为实际前端域名
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # 允许局域网开发机访问（如 192.168.x.x:5173 / 10.x.x.x:5173 / Radmin 26.x.x.x:5173）
    cors_origin_regex: str = (
        r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|26\.\d+\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)(:5173)?$"
        r"|^https://[a-z0-9-]+\.trycloudflare\.com$"
        r"|^https://[a-z0-9-]+\.ngrok-free\.app$"
        r"|^https://[a-z0-9-]+\.ngrok-free\.dev$"
        r"|^https://[a-z0-9-]+\.ngrok\.io$"
        r"|^https://[a-z0-9-]+\.loca\.lt$"
    )
    # 强模型用于总结陈词、裁判终局等（逗号前为主力，后与 flash 区分）
    deepseek_pro_phases: str = "closing,post_match"

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def minimax_api_key_effective(self) -> str | None:
        return self.minimax_api_key or _read_loose_env_value("MINIMAX_API_KEY", "MiniMax tts", "minimax tts")

    @property
    def kimi_api_key_effective(self) -> str | None:
        return self.kimi_api_key or _read_loose_env_value("KIMI_API_KEY", "kimi")


@lru_cache
def get_settings() -> Settings:
    return Settings()
