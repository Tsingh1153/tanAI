"""FastAPI application: REST endpoints + WebSocket streaming chat.

Wiring strategy:
- A lifespan handler initializes the database and builds the provider registry
  once, stashing the registry on ``app.state`` for reuse across requests.
- Dependency-injection functions build repositories/services per request from a
  scoped DB session, keeping handlers thin and testable.
- Streaming uses a WebSocket so the frontend receives tokens the instant the
  model emits them; a non-streaming REST fallback is also provided.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession

from .agent import (
    AgentService,
    MCPManager,
    MCPServerConfig,
    build_default_tools,
    load_plugins,
)
from .agent.tools import ToolContext, ToolRegistry, ToolSpec
from .config import get_settings
from .database import SessionLocal, get_session, init_db
from .hardware import detect_hardware
from .imagegen import ImageGenError, build_image_generator
from .memory import MemoryService
from .providers import (
    ChatMessage,
    ProviderRegistry,
    build_default_registry,
    make_openai_provider,
)
from .rag import IngestionService, RagService
from .rag.embeddings import EmbeddingProvider, OllamaEmbeddingProvider
from .rag.parsers import supported_extension
from .repositories import (
    ChunkRepository,
    ConversationRepository,
    DocumentRepository,
    FolderRepository,
    MCPServerRepository,
    MemoryRepository,
    MessageRepository,
    ProviderRepository,
)
from .schemas import (
    ChatRequest,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    ConversationWithMessages,
    DocumentOut,
    FolderCreate,
    FolderOut,
    FolderUpdate,
    HealthOut,
    MemoryCreate,
    MemoryOut,
    MemoryUpdate,
    MessageOut,
    ImageGenRequest,
    MCPServerCreate,
    MCPServerOut,
    ModelInfo,
    PluginInfo,
    ProviderCreate,
    ProviderOut,
    SearchRequest,
    SearchResponse,
)
from .services.chat_service import ChatService, ConversationNotFound
from .web import fetch_url_text, web_search

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await init_db()
    os.makedirs(settings.documents_dir, exist_ok=True)
    os.makedirs(
        os.path.expandvars(os.path.expanduser(settings.agent_workspace_dir)),
        exist_ok=True,
    )
    os.makedirs(settings.images_dir, exist_ok=True)
    os.makedirs(settings.plugins_dir, exist_ok=True)
    registry = build_default_registry(settings)
    # Restore user-registered OpenAI-compatible providers from the database so
    # they survive restarts.
    async with SessionLocal() as session:
        for row in await ProviderRepository(session).list():
            registry.register(
                make_openai_provider(
                    row.name,
                    row.base_url,
                    row.api_key,
                    row.label,
                    settings.request_timeout,
                )
            )
    app.state.registry = registry
    app.state.embeddings = OllamaEmbeddingProvider(
        settings.ollama_base_url,
        settings.embedding_model,
        keep_alive=settings.ollama_keep_alive,
    )

    # Connect saved MCP servers so their tools are available to the agent.
    mcp = MCPManager()
    async with SessionLocal() as session:
        configs = [
            MCPServerConfig(
                name=row.name,
                command=row.command,
                args=json.loads(row.args_json) if row.args_json else [],
                env=json.loads(row.env_json) if row.env_json else {},
            )
            for row in await MCPServerRepository(session).list()
        ]
    await mcp.connect_all(configs)
    app.state.mcp = mcp

    app.state.imagegen = build_image_generator(settings)

    # Warm the chat + embedding models in the background so the first real
    # request doesn't pay the cold-load cost.
    if settings.warm_up:
        asyncio.create_task(_warm_up_models())

    try:
        yield
    finally:
        await app.state.registry.aclose()
        await app.state.embeddings.aclose()
        await app.state.mcp.aclose()
        await app.state.imagegen.aclose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve stored images (vision uploads / captures). check_dir=False so mounting
# succeeds before the directory is created in the lifespan handler.
app.mount(
    "/images",
    StaticFiles(directory=settings.images_dir, check_dir=False),
    name="images",
)


# --------------------------------------------------------------------------- #
# Dependency injection helpers
# --------------------------------------------------------------------------- #
def get_registry() -> ProviderRegistry:
    return app.state.registry


def get_embeddings() -> EmbeddingProvider:
    return app.state.embeddings


def get_chat_service(
    session: AsyncSession = Depends(get_session),
    registry: ProviderRegistry = Depends(get_registry),
) -> ChatService:
    return ChatService(
        ConversationRepository(session),
        MessageRepository(session),
        registry,
        settings,
    )


def get_memory_service(
    session: AsyncSession = Depends(get_session),
    embeddings: EmbeddingProvider = Depends(get_embeddings),
) -> MemoryService:
    return MemoryService(MemoryRepository(session), embeddings, settings)


def get_rag_service(
    session: AsyncSession = Depends(get_session),
    embeddings: EmbeddingProvider = Depends(get_embeddings),
) -> RagService:
    return RagService(ChunkRepository(session), embeddings)


def get_ingestion_service(
    session: AsyncSession = Depends(get_session),
    embeddings: EmbeddingProvider = Depends(get_embeddings),
) -> IngestionService:
    return IngestionService(
        DocumentRepository(session), ChunkRepository(session), embeddings
    )


# --------------------------------------------------------------------------- #
# Health & models
# --------------------------------------------------------------------------- #
@app.get("/api/health", response_model=HealthOut)
async def health(
    registry: ProviderRegistry = Depends(get_registry),
    embeddings: EmbeddingProvider = Depends(get_embeddings),
    session: AsyncSession = Depends(get_session),
) -> HealthOut:
    provider = registry.get()
    online = await provider.health()
    embedding_online = await embeddings.health()
    indexed = await ChunkRepository(session).count()
    return HealthOut(
        status="ok",
        provider=provider.name,
        provider_online=online,
        default_model=settings.default_model,
        embedding_model=embeddings.model,
        embedding_online=embedding_online,
        indexed_chunks=indexed,
        hardware=detect_hardware().label,
    )


@app.get("/api/models", response_model=list[ModelInfo])
async def list_models(
    registry: ProviderRegistry = Depends(get_registry),
) -> list[ModelInfo]:
    """Aggregate available models across every registered provider.

    A single provider being offline never fails the whole call — its models are
    simply omitted, so the UI still shows models from providers that are up.
    """

    models: list[ModelInfo] = []
    for provider in registry.all():
        try:
            for m in await provider.list_models():
                models.append(
                    ModelInfo(
                        name=m.name,
                        provider=provider.name,
                        provider_label=provider.label,
                        size=m.size,
                        modified_at=m.modified_at,
                    )
                )
        except Exception:
            continue  # skip offline/unreachable providers
    return models


# --------------------------------------------------------------------------- #
# Model management (pull / delete via Ollama)
# --------------------------------------------------------------------------- #
@app.get("/api/models/pull")
async def pull_model(
    name: str, registry: ProviderRegistry = Depends(get_registry)
) -> StreamingResponse:
    """Stream download progress (SSE) while Ollama pulls a model."""

    provider = registry.get("ollama") if registry.has("ollama") else None
    if provider is None or not hasattr(provider, "pull"):
        raise HTTPException(
            status_code=400, detail="Model pulling requires the Ollama backend."
        )

    async def events() -> AsyncIterator[str]:
        try:
            async for line in provider.pull(name):
                yield f"data: {line}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'status': 'error', 'error': str(exc)})}\n\n"
        yield f"data: {json.dumps({'status': 'done'})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@app.delete("/api/models", status_code=204, response_class=Response)
async def delete_model(
    name: str, registry: ProviderRegistry = Depends(get_registry)
) -> Response:
    provider = registry.get("ollama") if registry.has("ollama") else None
    if provider is None or not hasattr(provider, "delete_model"):
        raise HTTPException(status_code=400, detail="Requires the Ollama backend.")
    await provider.delete_model(name)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Providers (model backends)
# --------------------------------------------------------------------------- #
def _slugify(value: str) -> str:
    slug = "".join(c if c.isalnum() else "-" for c in value.lower()).strip("-")
    return slug or "provider"


@app.get("/api/providers", response_model=list[ProviderOut])
async def list_providers(
    registry: ProviderRegistry = Depends(get_registry),
    session: AsyncSession = Depends(get_session),
) -> list[ProviderOut]:
    persisted = {p.name: p for p in await ProviderRepository(session).list()}
    out: list[ProviderOut] = []
    for provider in registry.all():
        row = persisted.get(provider.name)
        out.append(
            ProviderOut(
                name=provider.name,
                label=provider.label,
                kind=provider.kind,
                base_url=row.base_url if row else getattr(provider, "_base_url", None),
                online=await provider.health(),
                has_api_key=bool(row and row.api_key),
                removable=provider.name in persisted,  # built-ins are permanent
            )
        )
    return out


@app.post("/api/providers", response_model=ProviderOut)
async def add_provider(
    payload: ProviderCreate,
    registry: ProviderRegistry = Depends(get_registry),
    session: AsyncSession = Depends(get_session),
) -> ProviderOut:
    name = _slugify(payload.name or payload.label)
    if registry.has(name):
        raise HTTPException(
            status_code=409, detail=f"A provider named '{name}' already exists"
        )

    provider = make_openai_provider(
        name, payload.base_url, payload.api_key, payload.label,
        settings.request_timeout,
    )
    # Verify reachability before committing so bad endpoints fail fast.
    if not await provider.health():
        await provider.aclose()
        raise HTTPException(
            status_code=400,
            detail=(
                "Could not reach that endpoint. Check the base URL "
                "(it should end in /v1) and API key."
            ),
        )

    repo = ProviderRepository(session)
    await repo.create(
        name=name,
        label=payload.label,
        base_url=payload.base_url,
        api_key=payload.api_key,
    )
    registry.register(provider)
    return ProviderOut(
        name=name,
        label=payload.label,
        kind="openai",
        base_url=payload.base_url,
        online=True,
        has_api_key=bool(payload.api_key),
        removable=True,
    )


@app.delete(
    "/api/providers/{name}", status_code=204, response_class=Response
)
async def remove_provider(
    name: str,
    registry: ProviderRegistry = Depends(get_registry),
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = ProviderRepository(session)
    row = await repo.get_by_name(name)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="Provider not found or is a built-in that cannot be removed",
        )
    await repo.delete(row)
    await registry.unregister(name)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Conversations CRUD
# --------------------------------------------------------------------------- #
@app.get("/api/conversations", response_model=list[ConversationOut])
async def list_conversations(
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    repo = ConversationRepository(session)
    return [ConversationOut.model_validate(c) for c in await repo.list()]


@app.post("/api/conversations", response_model=ConversationWithMessages)
async def create_conversation(
    payload: ConversationCreate,
    session: AsyncSession = Depends(get_session),
) -> ConversationWithMessages:
    repo = ConversationRepository(session)
    created = await repo.create(
        model=payload.model or settings.default_model,
        title=payload.title or "New chat",
    )
    # Re-fetch with the messages relationship eagerly loaded so serialization
    # never triggers a lazy load outside the async session context.
    conversation = await repo.get(created.id)
    return ConversationWithMessages.model_validate(conversation)


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationWithMessages,
)
async def get_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> ConversationWithMessages:
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationWithMessages.model_validate(conversation)


@app.patch(
    "/api/conversations/{conversation_id}",
    response_model=ConversationOut,
)
async def update_conversation(
    conversation_id: str,
    payload: ConversationUpdate,
    session: AsyncSession = Depends(get_session),
) -> ConversationOut:
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # exclude_unset means only the fields the client actually sent are applied —
    # so folder_id=null (unfile) is honored, while omitting it leaves it alone.
    fields = payload.model_dump(exclude_unset=True)
    updated = await repo.apply(conversation, fields) if fields else conversation
    return ConversationOut.model_validate(updated)


@app.delete(
    "/api/conversations/{conversation_id}",
    status_code=204,
    response_class=Response,
)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = ConversationRepository(session)
    conversation = await repo.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await repo.delete(conversation)
    return Response(status_code=204)


@app.get("/api/folders", response_model=list[FolderOut])
async def list_folders(
    session: AsyncSession = Depends(get_session),
) -> list[FolderOut]:
    return [FolderOut.model_validate(f) for f in await FolderRepository(session).list()]


@app.post("/api/folders", response_model=FolderOut)
async def create_folder(
    payload: FolderCreate,
    session: AsyncSession = Depends(get_session),
) -> FolderOut:
    folder = await FolderRepository(session).create(payload.name.strip() or "Folder")
    return FolderOut.model_validate(folder)


@app.patch("/api/folders/{folder_id}", response_model=FolderOut)
async def rename_folder(
    folder_id: str,
    payload: FolderUpdate,
    session: AsyncSession = Depends(get_session),
) -> FolderOut:
    repo = FolderRepository(session)
    folder = await repo.get(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return FolderOut.model_validate(await repo.rename(folder, payload.name.strip()))


@app.delete("/api/folders/{folder_id}", status_code=204, response_class=Response)
async def delete_folder(
    folder_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = FolderRepository(session)
    folder = await repo.get(folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Detach its conversations first (they become ungrouped, not deleted).
    await ConversationRepository(session).clear_folder(folder_id)
    await repo.delete(folder)
    return Response(status_code=204)


@app.delete(
    "/api/conversations/{conversation_id}/messages/{message_id}",
    status_code=204,
    response_class=Response,
)
async def truncate_from_message(
    conversation_id: str,
    message_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Delete a message and everything after it (edit / regenerate support)."""

    await MessageRepository(session).delete_from(conversation_id, message_id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# RAG: documents & search
# --------------------------------------------------------------------------- #
@app.get("/api/documents", response_model=list[DocumentOut])
async def list_documents(
    conversation_id: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[DocumentOut]:
    repo = DocumentRepository(session)
    # Scoped view (a chat's own docs + global) when a conversation is given;
    # otherwise every document.
    docs = (
        await repo.list_for_conversation(conversation_id)
        if conversation_id
        else await repo.list()
    )
    return [DocumentOut.model_validate(d) for d in docs]


@app.post("/api/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    conversation_id: str | None = Form(default=None),
    session: AsyncSession = Depends(get_session),
    ingestion: IngestionService = Depends(get_ingestion_service),
) -> DocumentOut:
    filename = file.filename or "upload"
    if not supported_extension(filename):
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {filename}",
        )

    # Persist the upload to the documents directory under an opaque name.
    os.makedirs(settings.documents_dir, exist_ok=True)
    stored_name = f"{uuid.uuid4()}_{os.path.basename(filename)}"
    stored_path = os.path.join(settings.documents_dir, stored_name)
    payload = await file.read()
    with open(stored_path, "wb") as fh:
        fh.write(payload)

    repo = DocumentRepository(session)
    document = await repo.create(
        filename=filename,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(payload),
        source_path=stored_path,
        conversation_id=conversation_id or None,
    )
    # Ingest synchronously so the response reflects the final indexed state.
    document = await ingestion.ingest(document, stored_path)
    return DocumentOut.model_validate(document)


@app.post("/api/documents/{document_id}/memory", response_model=DocumentOut)
async def promote_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> DocumentOut:
    """Promote a chat-scoped document to the global memory knowledge base."""

    repo = DocumentRepository(session)
    document = await repo.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document = await repo.promote_to_global(document)
    return DocumentOut.model_validate(document)


@app.delete(
    "/api/documents/{document_id}", status_code=204, response_class=Response
)
async def delete_document(
    document_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = DocumentRepository(session)
    document = await repo.get(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    # Best-effort removal of the stored file.
    if document.source_path and os.path.exists(document.source_path):
        try:
            os.remove(document.source_path)
        except OSError:
            pass
    await repo.delete(document)
    return Response(status_code=204)


@app.post("/api/search", response_model=SearchResponse)
async def search_documents(
    payload: SearchRequest,
    rag: RagService = Depends(get_rag_service),
) -> SearchResponse:
    try:
        scored = await rag.search(
            payload.query, payload.top_k, payload.document_ids
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SearchResponse(results=RagService._to_sources(scored))


# --------------------------------------------------------------------------- #
# Agent tools
# --------------------------------------------------------------------------- #
def _agent_root() -> Path:
    """Resolve the agent's filesystem root, expanding ~ and env vars."""

    raw = os.path.expandvars(os.path.expanduser(settings.agent_workspace_dir))
    return Path(raw).resolve()


def _tool_context() -> ToolContext:
    return ToolContext(
        workspace=_agent_root(),
        timeout=settings.tool_timeout,
        output_limit=settings.tool_output_limit,
    )


def _build_agent_tools() -> ToolRegistry:
    """All agent tools: built-ins, computer use, plugins, and MCP servers."""

    tools = build_default_tools(_tool_context(), settings.computer_use_enabled)
    if settings.plugins_enabled:
        load_plugins(tools, settings.plugins_dir)
    mcp: MCPManager | None = getattr(app.state, "mcp", None)
    if mcp is not None:
        for spec in mcp.tool_specs():
            tools.register(spec)

    tools.register(_image_tool_spec())
    if settings.web_search_enabled:
        tools.register(_web_search_tool_spec())
    return tools


def _image_tool_spec() -> ToolSpec:
    """Agent tool that generates an image and returns it as markdown."""

    async def handler(args: dict, ctx: ToolContext) -> str:
        prompt = (args.get("prompt") or "").strip()
        if not prompt:
            return "Error: missing image prompt."
        try:
            names = await _generate_images(prompt, 1)
        except Exception as exc:  # ImageGenError or transport error
            return f"Error: {exc}"
        urls = [f"{settings.public_base_url}/images/{n}" for n in names]
        markdown = "\n".join(f"![{prompt}]({u})" for u in urls)
        return (
            "Image generated. Include it in your reply to the user with this "
            f"exact markdown so it displays:\n{markdown}"
        )

    return ToolSpec(
        name="generate_image",
        description=(
            "Generate an image from a text prompt using the configured image "
            "backend (Stable Diffusion / image API)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Description of the image to create",
                }
            },
            "required": ["prompt"],
        },
        requires_approval=False,
        handler=handler,
    )


@app.get("/api/agent/tools")
async def list_agent_tools() -> dict:
    registry = _build_agent_tools()
    return {
        "enabled": settings.agent_enabled,
        "computer_use": settings.computer_use_enabled,
        "workspace": str(_agent_root()),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
                "requires_approval": t.requires_approval,
            }
            for t in registry.specs()
        ],
    }


# --------------------------------------------------------------------------- #
# Apple Foundation Models (macOS 27+): quota
# --------------------------------------------------------------------------- #
@app.get("/api/fm/quota")
async def fm_quota() -> dict:
    """Run `fm quota-usage` and return its output (macOS 27+ only)."""

    import shutil

    if shutil.which("fm") is None:
        return {"available": False, "output": ""}
    try:
        proc = await asyncio.create_subprocess_exec(
            "fm",
            "quota-usage",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        return {"available": True, "output": out.decode(errors="replace").strip()}
    except Exception as exc:
        return {"available": False, "output": f"Error: {exc}"}


# --------------------------------------------------------------------------- #
# Voice: speech-to-text (local Whisper)
# --------------------------------------------------------------------------- #
def _load_whisper():
    """Lazily load and cache the Whisper model (optional dependency)."""

    model = getattr(app.state, "whisper", None)
    if model is not None:
        return model
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Speech-to-text is not installed. Run: "
                "pip install -r requirements-voice.txt"
            ),
        ) from exc
    model = WhisperModel(
        settings.voice_stt_model, device="cpu", compute_type="int8"
    )
    app.state.whisper = model
    return model


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    """Transcribe an uploaded audio clip to text with local Whisper."""

    model = _load_whisper()
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="Empty audio upload.")

    suffix = os.path.splitext(file.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio)
        path = tmp.name

    try:
        def work() -> tuple[str, str]:
            segments, info = model.transcribe(path, beam_size=1)
            text = " ".join(seg.text for seg in segments).strip()
            return text, info.language

        text, language = await run_in_threadpool(work)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Transcription failed: {exc}"
        ) from exc
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return {"text": text, "language": language}


# --------------------------------------------------------------------------- #
# Image generation
# --------------------------------------------------------------------------- #
async def _generate_images(prompt: str, n: int) -> list[str]:
    """Generate images, save them, and return their served filenames."""

    generator = app.state.imagegen
    pngs = await generator.generate(
        prompt, settings.image_size, settings.image_steps, max(1, min(n, 4))
    )
    os.makedirs(settings.images_dir, exist_ok=True)
    names: list[str] = []
    for png in pngs:
        name = f"gen_{uuid.uuid4()}.png"
        with open(os.path.join(settings.images_dir, name), "wb") as fh:
            fh.write(png)
        names.append(name)
    return names


@app.post("/api/images/generate")
async def generate_images_endpoint(payload: ImageGenRequest) -> dict:
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Missing prompt.")
    try:
        names = await _generate_images(payload.prompt, payload.n)
    except ImageGenError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"images": [f"/images/{name}" for name in names]}


# --------------------------------------------------------------------------- #
# Plugins & MCP
# --------------------------------------------------------------------------- #
@app.get("/api/plugins", response_model=PluginInfo)
async def list_installed_plugins() -> PluginInfo:
    registry = ToolRegistry(_tool_context())
    result = load_plugins(registry, settings.plugins_dir)
    return PluginInfo(
        loaded=result.loaded,
        errors=result.errors,
        tools=[t.name for t in registry.specs()],
    )


@app.get("/api/mcp", response_model=list[MCPServerOut])
async def list_mcp_servers() -> list[MCPServerOut]:
    mcp: MCPManager = app.state.mcp
    return [MCPServerOut(**s) for s in mcp.status()]


@app.post("/api/mcp", response_model=MCPServerOut)
async def add_mcp_server(
    payload: MCPServerCreate,
    session: AsyncSession = Depends(get_session),
) -> MCPServerOut:
    repo = MCPServerRepository(session)
    if await repo.get_by_name(payload.name):
        raise HTTPException(
            status_code=409, detail=f"An MCP server named '{payload.name}' exists"
        )
    mcp: MCPManager = app.state.mcp
    server = await mcp.connect(
        MCPServerConfig(
            name=payload.name,
            command=payload.command,
            args=payload.args,
            env=payload.env,
        )
    )
    # Persist so it reconnects on restart (even if it failed once, keep config).
    await repo.create(payload.name, payload.command, payload.args, payload.env)
    return MCPServerOut(
        name=payload.name,
        command=payload.command,
        connected=server.client is not None,
        error=server.error,
        tools=[t.name for t in server.tools],
    )


@app.delete("/api/mcp/{name}", status_code=204, response_class=Response)
async def remove_mcp_server(
    name: str, session: AsyncSession = Depends(get_session)
) -> Response:
    repo = MCPServerRepository(session)
    row = await repo.get_by_name(name)
    if row is not None:
        await repo.delete(row)
    await app.state.mcp.disconnect(name)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Memory
# --------------------------------------------------------------------------- #
@app.get("/api/memories", response_model=list[MemoryOut])
async def list_memories(
    memory: MemoryService = Depends(get_memory_service),
) -> list[MemoryOut]:
    return [MemoryOut.model_validate(m) for m in await memory.list()]


@app.post("/api/memories", response_model=MemoryOut)
async def create_memory(
    payload: MemoryCreate,
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    try:
        created = await memory.create(
            content=payload.content,
            kind=payload.kind,
            importance=payload.importance,
            pinned=payload.pinned,
        )
    except Exception as exc:  # embedding backend offline
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MemoryOut.model_validate(created)


@app.patch("/api/memories/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    session: AsyncSession = Depends(get_session),
    memory: MemoryService = Depends(get_memory_service),
) -> MemoryOut:
    existing = await MemoryRepository(session).get(memory_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    updated = await memory.update(
        existing, payload.model_dump(exclude_unset=True)
    )
    return MemoryOut.model_validate(updated)


@app.delete(
    "/api/memories/{memory_id}", status_code=204, response_class=Response
)
async def delete_memory(
    memory_id: str,
    session: AsyncSession = Depends(get_session),
) -> Response:
    repo = MemoryRepository(session)
    existing = await repo.get(memory_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    await repo.delete(existing)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Chat: non-streaming REST fallback
# --------------------------------------------------------------------------- #
@app.post(
    "/api/conversations/{conversation_id}/chat",
    response_model=MessageOut,
)
async def chat_once(
    conversation_id: str,
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> MessageOut:
    try:
        tokens = [
            token
            async for token in service.stream_turn(
                conversation_id,
                payload.content,
                payload.model,
                provider_name=payload.provider,
            )
        ]
    except ConversationNotFound as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Generation failed: {exc}") from exc

    return MessageOut(
        id="",
        role="assistant",
        content="".join(tokens),
        model=payload.model,
        created_at=datetime.now(timezone.utc),
    )


# --------------------------------------------------------------------------- #
# Chat: WebSocket streaming
# --------------------------------------------------------------------------- #
@app.websocket("/ws/chat/{conversation_id}")
async def chat_ws(websocket: WebSocket, conversation_id: str) -> None:
    """Stream assistant tokens for a conversation.

    Protocol: client sends
    ``{"content": str, "model"?: str, "use_rag"?: bool, "document_ids"?: [str]}``.
    Server replies with an optional ``{"type": "sources", "data": [...]}`` event
    (when RAG is on), a stream of ``{"type": "token", "data": str}`` events, then
    a terminal ``{"type": "done"}``. Errors: ``{"type": "error", ...}``.
    """

    await websocket.accept()
    registry: ProviderRegistry = websocket.app.state.registry
    embeddings: EmbeddingProvider = websocket.app.state.embeddings
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "detail": "Invalid JSON payload"}
                )
                continue

            content = (message.get("content") or "").strip()
            if not content:
                await websocket.send_json(
                    {"type": "error", "detail": "Empty message content"}
                )
                continue
            model = message.get("model")
            provider_name = message.get("provider")
            use_rag = bool(message.get("use_rag"))
            document_ids = message.get("document_ids") or None
            images = message.get("images") or None
            regenerate = bool(message.get("regenerate"))
            use_web = bool(message.get("use_web")) and settings.web_search_enabled
            use_memory = bool(message.get("use_memory", True)) and settings.memory_enabled
            use_agent = bool(message.get("agent")) and settings.agent_enabled

            if use_agent:
                await _run_agent_turn(
                    websocket,
                    conversation_id,
                    content,
                    model,
                    provider_name,
                    use_memory,
                    registry,
                    embeddings,
                )
                continue

            # Each turn gets its own DB session bound to this handler.
            async with SessionLocal() as session:
                service = ChatService(
                    ConversationRepository(session),
                    MessageRepository(session),
                    registry,
                    settings,
                )
                await websocket.send_json({"type": "start"})

                system_primes: list[str] = []

                # Long-term memory recall (best-effort; never blocks the answer).
                if use_memory:
                    try:
                        mem_service = MemoryService(
                            MemoryRepository(session), embeddings, settings
                        )
                        mem_prime, used = await mem_service.build_prompt(
                            content, settings.memory_top_k
                        )
                        if mem_prime:
                            system_primes.append(mem_prime)
                        if used:
                            await websocket.send_json(
                                {
                                    "type": "memory",
                                    "data": [
                                        MemoryOut.model_validate(m).model_dump(
                                            mode="json"
                                        )
                                        for m in used
                                    ],
                                }
                            )
                    except Exception:
                        pass  # memory is an enhancement, not a hard dependency

                # Optional web search grounding (best-effort; never blocks).
                if use_web:
                    try:
                        web_prime, web_sources = await _web_context(content)
                        if web_prime:
                            system_primes.append(web_prime)
                        await websocket.send_json(
                            {"type": "web_sources", "data": web_sources}
                        )
                    except Exception:
                        await websocket.send_json(
                            {"type": "web_sources", "data": []}
                        )

                # Optional RAG retrieval, scoped to this chat's documents plus
                # the global memory set. Explicit document_ids from the client
                # further narrow the set if provided.
                if use_rag:
                    try:
                        allowed = await DocumentRepository(
                            session
                        ).ready_ids_for_conversation(conversation_id)
                        if document_ids:
                            allowed = [d for d in allowed if d in document_ids]
                        if allowed:
                            rag = RagService(ChunkRepository(session), embeddings)
                            rag_prime, sources = await rag.build_context(
                                content, settings.rag_top_k, allowed
                            )
                            if rag_prime:
                                system_primes.append(rag_prime)
                            await websocket.send_json(
                                {
                                    "type": "sources",
                                    "data": [s.model_dump() for s in sources],
                                }
                            )
                        else:
                            # No documents in scope for this chat.
                            await websocket.send_json(
                                {"type": "sources", "data": []}
                            )
                    except Exception as exc:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "detail": f"Retrieval failed: {exc}",
                            }
                        )
                        continue

                parts: list[str] = []
                try:
                    async for token in service.stream_turn(
                        conversation_id,
                        content,
                        model,
                        provider_name=provider_name,
                        system_primes=system_primes,
                        images=images,
                        persist_user=not regenerate,
                    ):
                        parts.append(token)
                        await websocket.send_json(
                            {"type": "token", "data": token}
                        )
                    await websocket.send_json({"type": "done"})
                except ConversationNotFound:
                    await websocket.send_json(
                        {"type": "error", "detail": "Conversation not found"}
                    )
                    continue
                except Exception as exc:  # surface generation failures cleanly
                    await websocket.send_json(
                        {"type": "error", "detail": f"Generation failed: {exc}"}
                    )
                    continue

            # Fire-and-forget: mine the completed exchange for durable memories.
            if use_memory and parts:
                asyncio.create_task(
                    _extract_memories(
                        conversation_id,
                        content,
                        "".join(parts),
                        model or settings.default_model,
                        registry,
                        embeddings,
                    )
                )
    except WebSocketDisconnect:
        return


async def _web_context(query: str) -> tuple[str | None, list[dict]]:
    """Search the web and build a grounding prime + citations."""

    results = await web_search(query, settings)
    if not results:
        return None, []
    top = results[: settings.web_fetch_pages]
    pages = await asyncio.gather(
        *[fetch_url_text(r.url) for r in top], return_exceptions=True
    )
    blocks: list[str] = []
    for i, r in enumerate(results, start=1):
        block = f"[{i}] {r.title} ({r.url})\n{r.snippet}"
        if i - 1 < len(pages) and isinstance(pages[i - 1], str) and pages[i - 1]:
            block += f"\nExcerpt: {pages[i - 1][:1500]}"
        blocks.append(block)
    prime = (
        "WEB SEARCH RESULTS for the user's message. Use them to answer with "
        "current, accurate information and cite sources by number like [1].\n\n"
        + "\n\n".join(blocks)
    )
    sources = [
        {"title": r.title, "url": r.url, "snippet": r.snippet} for r in results
    ]
    return prime, sources


def _web_search_tool_spec() -> ToolSpec:
    async def handler(args: dict, ctx: ToolContext) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            return "Error: missing search query."
        try:
            results = await web_search(query, settings)
        except Exception as exc:
            return f"Error: {exc}"
        if not results:
            return "No results found."
        return "\n\n".join(
            f"{r.title}\n{r.url}\n{r.snippet}" for r in results
        )

    return ToolSpec(
        name="web_search",
        description="Search the web and return titles, URLs, and snippets.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        requires_approval=False,
        handler=handler,
    )


async def _warm_up_models() -> None:
    """Load the default chat + embedding models so the first request is fast."""

    try:
        provider = app.state.registry.get("ollama")
        await provider.complete(
            settings.default_model, [ChatMessage(role="user", content="hi")]
        )
    except Exception:
        pass  # Ollama may be offline or the model not pulled yet.
    try:
        await app.state.embeddings.embed(["warm up"])
    except Exception:
        pass


async def _run_agent_turn(
    websocket: WebSocket,
    conversation_id: str,
    content: str,
    model: str | None,
    provider_name: str | None,
    use_memory: bool,
    registry: ProviderRegistry,
    embeddings: EmbeddingProvider,
) -> None:
    """Run one agentic turn: tool loop with live events and approval gating."""

    async with SessionLocal() as session:
        conversations = ConversationRepository(session)
        messages_repo = MessageRepository(session)
        conversation = await conversations.get(conversation_id)
        if conversation is None:
            await websocket.send_json(
                {"type": "error", "detail": "Conversation not found"}
            )
            return

        chosen_model = model or conversation.model
        provider = registry.get(provider_name)

        await messages_repo.add(conversation_id, "user", content)
        history_rows = await messages_repo.list_for_conversation(conversation_id)
        history = [
            ChatMessage(role=m.role, content=m.content) for m in history_rows
        ]

        # Optional long-term memory prime.
        primes: list[str] = []
        if use_memory:
            try:
                mem = MemoryService(MemoryRepository(session), embeddings, settings)
                mem_prime, used = await mem.build_prompt(
                    content, settings.memory_top_k
                )
                if mem_prime:
                    primes.append(mem_prime)
                if used:
                    await websocket.send_json(
                        {
                            "type": "memory",
                            "data": [
                                MemoryOut.model_validate(m).model_dump(mode="json")
                                for m in used
                            ],
                        }
                    )
            except Exception:
                pass

        tools = _build_agent_tools()
        # Tell the model where its file tools operate so it uses valid paths.
        primes.append(
            f"Your file tools (list_files, read_file, write_file) and the "
            f"Python tool operate under this root path: {_agent_root()}. "
            f"Use absolute paths within it when reading or writing files."
        )
        agent = AgentService(
            provider, chosen_model, tools, settings.agent_max_steps
        )

        await websocket.send_json({"type": "start"})

        async def emit(event: dict) -> None:
            await websocket.send_json(event)

        async def request_approval(tool: str, arguments: dict) -> bool:
            await websocket.send_json(
                {
                    "type": "approval_request",
                    "tool": tool,
                    "arguments": arguments,
                }
            )
            raw = await websocket.receive_text()
            try:
                return bool(json.loads(raw).get("approved"))
            except json.JSONDecodeError:
                return False

        try:
            final = await agent.run(history, emit, request_approval, primes)
        except Exception as exc:
            await websocket.send_json(
                {"type": "error", "detail": f"Agent failed: {exc}"}
            )
            return

        await websocket.send_json({"type": "token", "data": final})
        await messages_repo.add(
            conversation_id, "assistant", final, model=chosen_model
        )
        if conversation.title == "New chat":
            title = content.strip().splitlines()[0][:60] or "New chat"
            await conversations.update(conversation, title=title)
        await websocket.send_json({"type": "done"})

    # Mine the exchange for durable memories, as in the normal chat path.
    if use_memory:
        asyncio.create_task(
            _extract_memories(
                conversation_id,
                content,
                final,
                chosen_model,
                registry,
                embeddings,
            )
        )


async def _extract_memories(
    conversation_id: str,
    user_content: str,
    assistant_content: str,
    model: str,
    registry: ProviderRegistry,
    embeddings: EmbeddingProvider,
) -> None:
    """Background memory extraction with its own session; failures are ignored."""

    try:
        async with SessionLocal() as session:
            service = MemoryService(
                MemoryRepository(session), embeddings, settings
            )
            await service.extract(
                conversation_id,
                user_content,
                assistant_content,
                registry.get(),
                model,
            )
    except Exception:
        return
