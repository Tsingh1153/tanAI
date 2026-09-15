# Changelog

All notable changes to **tanAI** are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/).

> tanAI was built in an intensive development sprint, so the versions below are
> feature milestones rather than calendar-spaced releases. Dates reflect the day
> the work was committed.

---

## [1.2.0] — 2026-09-15

### Added
- **Finance personas** — a tab bar switches the assistant into a domain mode:
  Personal Finance, Markets & Investing, Corporate Finance, or Finance Tutor
  (General is the default). Each injects a domain system prompt served from a new
  `/api/personas` endpoint, with an education-not-advice guardrail on every finance
  mode. Applies to both normal and agent turns.
- **Finance corpus + seed script** — an original reference corpus in
  `backend/corpus/finance/` plus `scripts/seed_corpus.py` to load it as global RAG
  documents, so the personas are grounded out of the box.

### Changed
- **De-AI cleanup pass** — trimmed verbose docstrings/comments to one-liners and
  "why" notes across the codebase; ran Ruff + Prettier; import cleanup.

### Fixed
- **Test isolation** — added a `conftest.py` that resets the schema before each
  test, fixing cross-file database pollution that made the suite order-dependent.

---

## [1.1.0] — 2026-09-14

### Added
- **Pinned chats** — pin conversations to a dedicated section at the top of the
  sidebar, via a per-chat options menu.
- **Folders** — organize conversations into collapsible, renamable folders;
  deleting a folder keeps its chats (they become ungrouped).
- **Resizable sidebar** — drag the divider to resize; width persists across
  sessions.

### Changed
- **Softer, less "blocky" UI** — assistant replies are now clean, borderless
  prose beside the avatar; user messages sit in a softer rounded bubble; roomier
  spacing and a rounder, gentler composer.
- **Streaming performance** — messages are memoized with stable callbacks, so
  only the actively streaming bubble re-renders (big win for long conversations).

---

## [1.0.0] — 2026-09-14

First feature-complete release: a local-first assistant approaching a modern
frontier chat app, running entirely on-device by default.

### Added
- **Web search** — grounds answers in live results (DuckDuckGo by default;
  Brave / Tavily / SearXNG optional) with clickable citations; also a
  `web_search` agent tool.
- **Artifacts** — ` ```html ` and ` ```svg ` code blocks render as a live,
  sandboxed preview with a Preview/Code toggle.
- **Apple Foundation Models** (macOS 27+) — the launcher auto-starts `fm serve`
  and exposes Apple's on-device model (and Private Cloud Compute) via the
  existing OpenAI-compatible provider, with quota display in Settings.

### Changed
- **Performance** — `keep_alive` keeps models resident between messages, a
  startup warm-up removes the cold-first-message delay, and the docs cover
  Ollama's flash-attention / KV-cache speedups.

---

## [0.9.0] — 2026-09-14

### Added
- **Plugin system** — drop a Python file in `backend/plugins/` defining
  `register(registry)` to add agent tools (hot-loaded).
- **MCP (Model Context Protocol)** — connect external MCP servers via a
  dependency-free stdio JSON-RPC client; their tools appear to the agent.
- Settings UI to manage MCP servers and view loaded plugins.

---

## [0.8.0] — 2026-09-14

### Added
- **Voice** — local speech-to-text (faster-whisper) behind a mic button, and
  text-to-speech via the browser's speech synthesis (per-reply speaker button +
  auto-speak toggle).

---

## [0.7.0] — 2026-09-14

### Added
- **Vision** — attach or paste images; they're sent to a vision-capable model.
- **Vision assist** — images sent to a text-only model are auto-described by a
  vision model, giving any model "borrowed eyes."
- **Webcam** — live capture with on-demand or interval analysis.
- **Image generation** — pluggable backend (AUTOMATIC1111 or OpenAI-compatible
  images API), with an Image panel and a `generate_image` agent tool.

---

## [0.6.0] — 2026-09-14

### Added
- **Computer use** (opt-in, off by default) — desktop-control agent tools
  (screenshot, mouse, keyboard, scroll), every action approval-gated, optional
  dependencies kept out of the core install.

---

## [0.5.0] — 2026-09-14

### Added
- **Agent + tools** — a plan-execute tool-calling loop with web fetch,
  filesystem read/list/write, sandboxed Python execution, and a clock.
- **Safety** — filesystem/code confined to a sandbox root, per-action approval
  prompts for writes/execution, a step limit, and audit logging.
- **Message editing / regeneration** and a truncate-from-message endpoint.

---

## [0.4.0] — 2026-09-14

### Added
- **Multiple model providers** — OpenAI-compatible backend (LM Studio, vLLM,
  llama.cpp server, cloud APIs) behind the provider abstraction, added live from
  Settings and persisted.
- **Hardware detection** (Apple Silicon / CUDA / ROCm / CPU).
- **In-app model manager** — download models with a progress bar and delete them,
  including one-click pulls for recommended models.

---

## [0.3.0] — 2026-09-14

### Added
- **Long-term memory** — durable facts extracted after each exchange, stored as
  embeddings and recalled semantically across chats; editable/pinnable in a
  panel.
- **Context compression** — long conversations auto-summarize older turns so the
  model never hits the context wall.

---

## [0.2.0] — 2026-09-14

### Added
- **RAG (chat with documents)** — upload PDF/Word/PowerPoint/Excel/CSV/Markdown/
  HTML/code; parse → chunk → embed → index; hybrid (semantic + keyword) retrieval
  with inline source citations.
- Documents scoped per conversation, with an "add to memory" action to share a
  document across all chats.

---

## [0.1.0] — 2026-09-14

### Added
- **Runnable vertical slice** — the foundation everything else builds on:
  - FastAPI backend with a layered architecture (routes → services →
    repositories → providers), async SQLAlchemy + SQLite persistence.
  - Streaming chat over WebSockets against a local Ollama model.
  - Next.js + React + TypeScript + Tailwind frontend: conversation list,
    streaming message bubbles, markdown + syntax highlighting + LaTeX, light/dark
    mode, model selector, keyboard shortcuts.
  - Pluggable `LLMProvider` abstraction (the seam that later made every new
    backend a drop-in), end-to-end tests, and one-command launch scripts.

### Notable milestones folded into this era
- Renamed the app to **tanAI**; adopted a dark-purple theme.
- **Mermaid** diagram rendering; production build support (`start-prod.sh`).
- Aesthetic overhaul: brand mark, welcome screen, message avatars.

---

[1.1.0]: https://github.com/Tsingh1153/tanAI
[1.0.0]: https://github.com/Tsingh1153/tanAI
[0.9.0]: https://github.com/Tsingh1153/tanAI
[0.8.0]: https://github.com/Tsingh1153/tanAI
[0.7.0]: https://github.com/Tsingh1153/tanAI
[0.6.0]: https://github.com/Tsingh1153/tanAI
[0.5.0]: https://github.com/Tsingh1153/tanAI
[0.4.0]: https://github.com/Tsingh1153/tanAI
[0.3.0]: https://github.com/Tsingh1153/tanAI
[0.2.0]: https://github.com/Tsingh1153/tanAI
[0.1.0]: https://github.com/Tsingh1153/tanAI
