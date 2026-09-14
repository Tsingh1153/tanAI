# tanAI

A fully local, open-source AI assistant with a Claude-inspired interface. This
repository is a **runnable, feature-rich app**: a real, working chat application
that streams responses from a local model, persists your conversations, and ships
with a clean, extensible architecture designed to grow into the full assistant
(RAG, memory, agents, tools, plugins).

Everything runs on `localhost`. No data leaves your machine unless you point it
at a remote API yourself.

---

## What works today

- **Streaming chat** over WebSockets against a local **Ollama** model.
- **Chat with your documents (RAG)** — upload PDF, Word, PowerPoint, Excel, CSV,
  Markdown, HTML, or code; the app parses, chunks, embeds, and indexes them, then
  grounds answers in the relevant passages with **inline source citations**.
  Retrieval is **hybrid** (semantic embeddings + keyword) over a local vector store.
- **Memory & unlimited context** — long conversations auto-compress older turns
  into a **rolling summary** so you never hit the context wall, and the assistant
  builds **long-term memory** of durable facts/preferences across chats. Memories
  are semantically recalled, importance-scored, pinnable, and fully editable in a
  dedicated panel; recalled memories are shown inline on each answer.
- **Agent with tools** — toggle Agent mode and the model can call tools in a
  plan-execute loop: **fetch web pages**, **read/list/write files**, **run
  Python**, and check the time. Filesystem and code execution are confined to a
  **sandbox workspace**, and any write or code execution requires **explicit
  approval**. A live tool timeline shows each step, and every call is audit-logged.
- **Computer use (optional, off by default)** — when explicitly enabled, the
  agent gains desktop-control tools (screenshot, move/click mouse, type, hotkeys,
  scroll). Every action requires per-step approval. Requires optional deps and an
  opt-in flag; see below.
- **Vision (image input)** — attach images to a message (image button, or paste).
  Images are stored and re-displayed in the conversation.
- **Vision assist (vision + text fusion)** — send an image to a *text-only* model
  and it's automatically routed through an installed **vision model** to describe
  the image, then your strong text model reasons over the description. Effectively
  gives any text model "sight."
- **Webcam** — a live camera panel captures frames and sends them to the chat for
  analysis, with an on-demand capture or a "live" interval mode.
- **In-app model manager** — download models (with a progress bar) and delete
  them from Settings, including one-click pulls for recommended vision/text models.
- **Plugins & MCP** — extend the agent with custom tools. Drop a Python file in
  `backend/plugins/` that defines `register(registry)` to add tools (hot-loaded),
  or connect **Model Context Protocol (MCP)** servers from Settings to bring in
  third-party tools. A dependency-free MCP stdio client ships built in.
- **Voice** — talk to it (mic button → local **Whisper** speech-to-text) and have
  it talk back (per-reply speaker button + auto-speak toggle, via your browser's
  built-in speech synthesis). STT is an optional dep: `pip install -r
  requirements-voice.txt`; TTS needs nothing.
- **Image generation** — the **Image** button (and a `generate_image` agent tool)
  create images via a pluggable backend: a local Stable Diffusion server
  (AUTOMATIC1111 `--api`, SD.Next, Forge) or an OpenAI-compatible images API.
  Configure it in Settings / `backend/.env`.
- **Web search** — flip on **Web** and answers are grounded in live search
  results (DuckDuckGo by default, no key; Brave/Tavily/SearXNG optional) with
  clickable citations. Also available as a `web_search` agent tool.
- **Artifacts** — ` ```html ` and ` ```svg ` blocks render as a **live sandboxed
  preview** with a Preview/Code toggle.
- **Regenerate & edit** — redo the last reply or edit any of your messages and
  re-run. **Mermaid** diagrams render inline. **Keyboard shortcuts**: ⌘/Ctrl+K new
  chat, Esc to stop.
- **Production mode** — `./scripts/start-prod.sh` builds and serves an optimized
  bundle for faster daily use.
- **Conversation persistence** (SQLite) with automatic titling, search, and delete.
- **Model selector** populated live from your installed Ollama models.
- **Markdown rendering** with GitHub-flavored markdown, syntax highlighting, and
  **LaTeX** (KaTeX).
- **Light / dark mode**, responsive layout, copy-to-clipboard, stop generation.
- **Apple Foundation Models (macOS 27+)** — if the `fm` CLI is present, the
  launcher automatically runs `fm serve` and exposes Apple's **on-device** LLM
  (and Private Cloud Compute) as an OpenAI-compatible API. Add it in one click
  from Settings → provider presets. Very fast and memory-light, ideal for quick
  tasks alongside a bigger Ollama model.
- **Multiple model providers** — besides local Ollama, add any
  **OpenAI-compatible** endpoint (LM Studio, vLLM, llama.cpp server, or a cloud
  API like OpenAI / Groq / OpenRouter) from Settings. Providers are added live —
  no restart — persist across restarts, and you can **switch model or provider
  mid-conversation**. Detected hardware (Apple Silicon / CUDA / ROCm / CPU) is
  shown in Settings.
- **Clean architecture**: repository pattern, dependency injection, typed schemas,
  async throughout, and passing end-to-end tests for both chat and RAG.

## Requirements

- **Python 3.10+**
- **Node.js 20+**
- **[Ollama](https://ollama.com)** installed and running, with a chat model and
  an embedding model (the embedding model powers document search / RAG):
  ```bash
  ollama pull qwen2.5:7b        # chat  (default; or llama3.2, mistral, gemma2…)
  ollama pull nomic-embed-text  # embeddings for RAG
  ```

## Quickstart

### Option A — one command (macOS / Linux)

```bash
cd tanAI
./scripts/start.sh
```

On Windows (PowerShell):

```powershell
cd tanAI
./scripts/start.ps1
```

Then open **http://localhost:3000**.

### Option B — manual

Backend:

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend (in a second terminal):

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

### Option B2 — production build (faster at runtime)

`./scripts/start.sh` runs the dev servers (fast to start, heavier at runtime).
For daily use, build an optimized production bundle and serve it:

```bash
cd tanAI
./scripts/start-prod.sh
```

This runs `next build` + `next start` and the backend without auto-reload. The
build step needs a bit of RAM; the `build` script already raises Node's heap to
4 GB. If a low-memory machine still errors during "Collecting build traces,"
raise it further: `NODE_OPTIONS=--max-old-space-size=6144 npm run build`.

### Option C — Docker

```bash
docker compose up --build
docker compose exec ollama ollama pull llama3.2   # first run only
```

The API's interactive docs are at **http://localhost:8000/docs**.

---

## Making it faster

Most of the speed comes from Ollama and your hardware, but a few settings help a
lot:

- **Model stays warm.** tanAI sends `keep_alive` so Ollama keeps the model in
  memory between messages (no multi-second reloads), and warms the chat +
  embedding models at startup so the *first* message is fast too. Tune with
  `LOCALMIND_OLLAMA_KEEP_ALIVE` (`30m`, `1h`, `-1`).
- **Pick a right-sized model.** A 3–4B model (e.g. `qwen2.5:3b`, `moondream`) is
  much faster than a 7–8B one on a MacBook Air; use the bigger model only when you
  need the quality. Switch instantly from the model dropdown.
- **Lower the context window** if you don't need long memory:
  `LOCALMIND_NUM_CTX=4096` speeds up load time and reduces memory.
- **Enable Ollama's speedups** (set these for the Ollama server, once). On macOS:
  ```bash
  launchctl setenv OLLAMA_FLASH_ATTENTION 1
  launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0
  ```
  Then restart Ollama. Flash attention speeds up attention; the quantized KV cache
  cuts memory so more of the model fits on the GPU. (In a terminal-launched
  Ollama, `export` them before `ollama serve` instead.)

## Architecture

```
tanAI/
├── backend/                 FastAPI + async SQLAlchemy
│   ├── app/
│   │   ├── main.py          REST routes + WebSocket streaming, DI wiring
│   │   ├── config.py        Centralized settings (env / .env)
│   │   ├── database.py      Async engine, session factory, schema bootstrap
│   │   ├── models.py        ORM models (Conversation, Message)
│   │   ├── schemas.py       Pydantic request/response contracts
│   │   ├── repositories.py  Repository pattern (all queries live here)
│   │   ├── services/        Business logic (ChatService orchestration)
│   │   └── providers/       Pluggable model backends
│   │       ├── base.py           LLMProvider interface
│   │       ├── ollama_provider.py
│   │       └── registry.py       Provider registry / hot-swap
│   └── tests/test_smoke.py  End-to-end test (no Ollama required)
├── frontend/                Next.js 14 + TypeScript + Tailwind
│   ├── app/                 App Router pages, layout, global styles
│   ├── components/          Sidebar, MessageList, Composer, Markdown, …
│   └── lib/                 Typed API client, streaming useChat hook, types
├── scripts/                 Cross-platform launchers
└── docker-compose.yml       Ollama + backend + frontend
```

### Key design decisions

- **Provider abstraction is the core seam.** The app talks to models only through
  a three-method `LLMProvider` interface (`list_models`, `stream_chat`, `health`).
  This is what makes backends interchangeable and hot-swappable; adding vLLM or an
  OpenAI-compatible endpoint is a new file plus one `register()` call.
- **Repository pattern + DI.** Services depend on repositories, not the ORM
  session, so persistence is centralized, mockable, and swappable (SQLite → Postgres
  is a URL change).
- **Streaming is transport-agnostic.** `ChatService.stream_turn` is a plain async
  generator, reused by both the WebSocket handler and the REST fallback and driven
  by a fake provider in tests.
- **Async end to end.** Async SQLAlchemy + httpx streaming keep the event loop free
  during long generations.

---

## Configuration

Backend settings are environment variables prefixed `LOCALMIND_` (see
`backend/.env.example`). Common ones:

| Variable | Default | Purpose |
| --- | --- | --- |
| `LOCALMIND_OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `LOCALMIND_DEFAULT_MODEL` | `llama3.2` | Fallback model |
| `LOCALMIND_DATABASE_URL` | `sqlite+aiosqlite:///./localmind.db` | Persistence |
| `LOCALMIND_PORT` | `8000` | API port |

Frontend: `NEXT_PUBLIC_API_BASE` (see `frontend/.env.local.example`).

---

## Testing

```bash
cd backend
PYTHONPATH=. python tests/test_smoke.py     # exercises the full request path
```

The smoke test injects a fake provider, so it runs without Ollama and verifies
health, model listing, conversation CRUD, WebSocket streaming, history
persistence, and auto-titling.

---

## Roadmap

This slice is the foundation for the full assistant. Planned, in order:

1. ~~**RAG** — document indexing, embeddings, local vector store, hybrid search.~~
   ✅ **Done.**
2. ~~**Memory** — long-term memory, importance scoring, semantic retrieval,
   context compression.~~ ✅ **Done.**
3. ~~**More providers** — OpenAI-compatible (LM Studio, vLLM, llama.cpp, cloud),
   hardware detection, hot-swap.~~ ✅ **Done.** (HF Transformers backend still to come.)
4. ~~**Agents & tools** — planning, tool calling (web, filesystem, Python),
   sandboxed execution, approval prompts.~~ ✅ **Done.** (Web search, shell, and
   multi-agent orchestration still to come.)
5. ~~**Computer use** — desktop control (screenshot, mouse, keyboard) with
   approval.~~ ✅ **Done** (opt-in; vision-guided control still to come).
6. ~~**Vision** — image input to multimodal models.~~ ✅ **Done.**
7. ~~**Webcam & real-time analysis**~~ ✅ **Done** (interval-based; true
   high-FPS realtime is model-speed-bound).
8. ~~**Plugins** — Python plugins and MCP integration.~~ ✅ **Done.**
9. ~~**Speech** — voice in (Whisper STT) / out (TTS).~~ ✅ **Done.**
10. **Frontend depth** — Mermaid diagrams, message editing/regeneration, folders,
    pinned chats, keyboard shortcuts, resizable/split panes.

## Enabling computer use

Computer use is off by default. To turn it on:

```bash
cd backend
pip install -r requirements-computer.txt        # optional OS-automation deps
export LOCALMIND_COMPUTER_USE_ENABLED=true       # opt in
```

On macOS, also grant your terminal app **Accessibility** and **Screen Recording**
permission in System Settings → Privacy & Security. Then restart. Every desktop
action still prompts for approval before it runs. Note: the model can *act*, but
deciding *where* to click from a screenshot needs a vision-capable model — that
multimodal step is a follow-up.

---

## License & models

The application code is yours to run and modify. Models are pulled and licensed
separately through Ollama; review each model's license before use.
