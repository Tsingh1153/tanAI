"""Centralized application configuration.

Settings are loaded from environment variables (prefixed ``LOCALMIND_``) and an
optional ``.env`` file. ``get_settings`` is cached so the configuration is parsed
once and shared across the process, which keeps the app cheap to wire up via
dependency injection.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Every field has a sensible local-first default so the application runs with
    zero configuration against a standard Ollama install.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="LOCALMIND_",
        extra="ignore",
    )

    app_name: str = "tanAI"
    host: str = "127.0.0.1"
    port: int = 8000
    # Public base URL the browser uses to reach this API (for absolute media
    # links, e.g. generated images embedded in markdown).
    public_base_url: str = "http://localhost:8000"

    # Persistence. Async SQLAlchemy URL; SQLite by default, Postgres-ready.
    database_url: str = "sqlite+aiosqlite:///./localmind.db"

    # Model backend.
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "qwen2.5:7b"
    request_timeout: float = 300.0

    # Performance. Keep the model resident in memory so it never has to reload
    # between messages ("30m", "1h", or "-1" for as long as the app runs).
    ollama_keep_alive: str = "30m"
    # Warm the chat + embedding models at startup so the first message is fast.
    warm_up: bool = True
    # Optional hard cap on generated tokens (None = model/user decides).
    num_predict: int | None = None

    # Context window (tokens) requested from the model. Ollama defaults to a
    # small 2048 unless overridden; a larger value keeps more of the
    # conversation live at the cost of memory. 8192 is a sensible default for a
    # ~3B model on 16 GB RAM; raise toward 32768/131072 with more headroom.
    num_ctx: int = 8192

    # RAG. Embedding model (must be pulled in Ollama) and where uploads live.
    embedding_model: str = "nomic-embed-text"
    documents_dir: str = "./data/documents"
    rag_top_k: int = 5

    # Vision. Where uploaded/captured images are stored for redisplay.
    images_dir: str = "./data/images"
    # Vision assist: when an image is sent to a text-only model, route it through
    # a vision model to describe it, then let the text model reason over the
    # description. Empty = auto-detect an installed vision model.
    vision_assist_enabled: bool = True
    vision_assist_model: str = ""

    # Memory & context management.
    # Approx tokens of recent conversation kept verbatim before older turns are
    # compressed into the rolling summary. Sits comfortably inside num_ctx.
    history_token_budget: int = 3000
    # Automatic extraction of durable facts after each exchange.
    memory_enabled: bool = True
    memory_top_k: int = 5
    # Optional lifetime for auto-captured memories (days). None = never expire.
    memory_ttl_days: int | None = None
    # Cosine similarity above which a candidate memory is treated as a duplicate.
    memory_dedup_threshold: float = 0.9

    # Agent / tools.
    agent_enabled: bool = True
    agent_max_steps: int = 6
    # Sandbox root for filesystem tools and code execution. All file access and
    # the Python tool's working directory are confined here for safety.
    agent_workspace_dir: str = "./data/agent"
    # Wall-clock limit (seconds) for the Python execution tool.
    tool_timeout: float = 30.0
    # Max characters of tool output fed back to the model (keeps context bounded).
    tool_output_limit: int = 6000

    # Computer use (desktop control). OFF by default — this is powerful and can
    # move the mouse, type, and screenshot the real screen. Enable explicitly
    # and install the optional deps (see requirements-computer.txt). Every action
    # still requires per-step user approval.
    computer_use_enabled: bool = False

    # Plugins. Python files dropped in this directory can register extra agent
    # tools. Plugins run in-process (trusted code), so only add ones you trust.
    plugins_enabled: bool = True
    plugins_dir: str = "./plugins"

    # Web search. Lets the assistant answer with current information.
    #   backend: "duckduckgo" (no key) | "brave" | "tavily" | "searxng"
    web_search_enabled: bool = True
    search_backend: str = "duckduckgo"
    search_api_key: str = ""  # for brave / tavily
    searxng_url: str = ""  # base URL of a SearXNG instance
    web_results: int = 5  # results to show
    web_fetch_pages: int = 3  # top pages to open for grounding

    # Voice. Local speech-to-text via faster-whisper (optional dependency).
    # Model size vs. speed/accuracy: tiny < base < small < medium. "base" is a
    # good default on modest hardware. Text-to-speech runs in the browser.
    voice_stt_model: str = "base"

    # Image generation. Needs an external backend: a local Stable Diffusion
    # server (AUTOMATIC1111 / SD.Next / Forge — OpenAI-compatible or the native
    # /sdapi txt2img) or an OpenAI-compatible images API.
    #   backend: "automatic1111" | "openai"
    image_backend: str = "automatic1111"
    image_server_url: str = "http://localhost:7860"  # AUTOMATIC1111 default
    image_api_key: str = ""  # for the "openai" backend
    image_model: str = ""  # e.g. "dall-e-3" for openai; blank = server default
    image_steps: int = 20
    image_size: int = 512

    # Frontend origins permitted to call the API.
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""

    return Settings()
