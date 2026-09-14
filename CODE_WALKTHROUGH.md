# tanAI — Code Walkthrough

*A code-level companion to `HOW_IT_WORKS.md`. Every snippet below is real code
from this repository, explained line group by line group. Written assuming Java
proficiency and reading-level Python. Java analogies appear in *italics*.*

Files referenced (so you can open them alongside):

```
backend/app/
  providers/base.py            the LLMProvider interface
  providers/ollama_provider.py one implementation
  providers/registry.py        the "which provider?" lookup
  repositories.py              database access
  services/chat_service.py     the core orchestration
  main.py                      routes + WebSocket
  rag/retriever.py             the embedding search
frontend/
  lib/api.ts                   typed backend calls
  lib/useChat.ts               streaming chat state
  components/MessageBubble.tsx one message on screen
```

---

## Part 1 — The provider interface (the backbone)

Everything the app does with a model goes through one small contract. Open
`providers/base.py`:

```python
class LLMProvider(ABC):
    name: str = "base"     # stable id, e.g. "ollama"
    label: str = "base"    # shown in the UI, e.g. "Ollama (local)"

    @abstractmethod
    async def list_models(self) -> list[ProviderModel]:
        """Return the models this provider can serve."""

    @abstractmethod
    def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        """Yield response tokens as they are generated."""

    @abstractmethod
    async def health(self) -> bool:
        """Return True if the backend is reachable."""
```

**What to notice:**

- `ABC` = "Abstract Base Class." *This is a Java `interface`.* `@abstractmethod`
  means "a subclass must provide this or Python refuses to instantiate it" —
  *exactly like an abstract method in Java.*
- `async def ... -> AsyncIterator[str]` — `stream_chat` doesn't return a string;
  it returns a **stream** of strings, produced one at a time. *The closest Java
  analogy is returning a `Stream<String>` or an `Iterator<String>` that's fed
  lazily, except each item can also wait on network I/O.*
- Types everywhere (`list[ProviderModel]`, `-> bool`). *Same compile-time-ish
  safety you get from Java's type system.*

The base class also gives every provider two **free** helper methods with default
implementations, so subclasses don't repeat themselves:

```python
async def complete(self, model, messages) -> str:
    """Non-streaming: collect the whole reply as one string."""
    parts: list[str] = []
    async for token in self.stream_chat(model, messages):
        parts.append(token)
    return "".join(parts)
```

*This is a default method on the interface (like a Java 8 `default` method): it
drains the stream and joins it. Any provider gets `complete()` for free just by
implementing `stream_chat()`.* Summarization and memory extraction call
`complete()` because they want the whole answer at once, not a stream.

---

## Part 2 — One implementation

Now `providers/ollama_provider.py` — the class that actually talks to Ollama.
Here's `stream_chat`, the important method:

```python
async def stream_chat(
    self, model: str, messages: list[ChatMessage]
) -> AsyncIterator[str]:
    body = {
        "model": model,
        "messages": [self._serialize(m) for m in messages],
        "stream": True,
        "options": self._options(),        # {"num_ctx": 8192, ...}
        "keep_alive": self._keep_alive,     # keep model loaded
    }
    async with self._client.stream("POST", "/api/chat", json=body) as resp:
        resp.raise_for_status()
        async for line in resp.aiter_lines():
            if not line.strip():
                continue
            chunk = json.loads(line)
            token = (chunk.get("message") or {}).get("content", "")
            if token:
                yield token           # <-- hand one token to the caller
            if chunk.get("done"):
                break
```

**Reading it:**

- `body` is a Python dict → sent as JSON to Ollama's `/api/chat`. Ollama streams
  back **newline-delimited JSON**: one small JSON object per line, each carrying a
  fragment of the answer.
- `async with self._client.stream(...)` opens a streaming HTTP request and
  guarantees it's closed afterward. *This is a `try-with-resources` block in Java —
  `with` = auto-close.*
- `async for line in resp.aiter_lines()` reads response lines **as they arrive**,
  not after the whole response is done.
- `yield token` — this function is an **async generator**. *Instead of `return`ing
  once, it `yield`s many times.* Each `yield` hands one token back to whoever is
  looping over it, then pauses until they ask for the next.

`self._serialize(m)` converts our internal `ChatMessage` into the exact dict shape
Ollama expects, and also attaches images or tool results if present. That's the
one spot that knows Ollama's format — swap providers and only this file changes.

---

## Part 3 — Choosing a provider (the registry)

`providers/registry.py` is a tiny lookup table so the rest of the app can ask for
"the provider named X" or "the default":

```python
class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, LLMProvider] = {}
        self._default: str | None = None

    def register(self, provider: LLMProvider, *, default: bool = False) -> None:
        self._providers[provider.name] = provider
        if default or self._default is None:
            self._default = provider.name

    def get(self, name: str | None = None) -> LLMProvider:
        key = name or self._default
        return self._providers[key]
```

*It's a `HashMap<String, LLMProvider>` with a remembered default key.* At startup
we `register(OllamaProvider(...), default=True)`, and later `register(...)` any
cloud providers the user added. Because `get()` returns the **interface type**, the
caller is completely insulated from which concrete class it gets — the payoff of
Part 1.

---

## Part 4 — Database access (repositories + ORM)

`repositories.py` holds all database queries. Here's the message repository's core:

```python
class MessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, conversation_id, role, content,
                  model=None, image_files=None) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            model=model,
            images_json=json.dumps(image_files) if image_files else None,
        )
        self._session.add(message)
        await self._session.commit()      # write the row
        await self._session.refresh(message)
        return message

    async def list_for_conversation(self, conversation_id) -> list[Message]:
        result = await self._session.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        return list(result.scalars().all())
```

**Reading it:**

- `Message(...)` builds a Python object; `session.add()` + `commit()` writes it to
  the database as a row. *This is `entityManager.persist(message)` in JPA — you
  never write `INSERT INTO ...` yourself.*
- `select(Message).where(...).order_by(...)` is a query written in Python that
  SQLAlchemy turns into SQL. *It's the Criteria API / a query builder — type-safe,
  no string SQL.*
- `AsyncSession` is the database connection for this request, handed in by the
  caller. *Constructor injection — the class doesn't create its own connection, so
  in tests you pass a throwaway one.*

**Why one class per data type?** So every conversation query lives in
`ConversationRepository`, every message query here, etc. If storage ever changes
(SQLite → Postgres), only these classes care. *Classic Repository Pattern.*

---

## Part 5 — The orchestrator (`chat_service.py`)

This is the method that runs when you send a message. It's long, so here's the
spine with the key parts kept and the rest summarized in comments:

```python
async def stream_turn(self, conversation_id, user_content,
                      model=None, provider_name=None,
                      system_primes=None, images=None,
                      persist_user=True) -> AsyncIterator[str]:

    conversation = await self._conversations.get(conversation_id)
    if conversation is None:
        raise ConversationNotFound(conversation_id)

    chosen_model = model or conversation.model
    provider = self._registry.get(provider_name)   # <-- interface, not a class

    # 1. Save the user's message first (so history is right even if we crash).
    if persist_user:
        await self._messages.add(conversation_id, "user", user_content, ...)

    # 2. Load the whole history as provider-agnostic ChatMessages.
    history_rows = await self._messages.list_for_conversation(conversation_id)
    history = [ChatMessage(role=m.role, content=m.content) for m in history_rows]

    # 3. (vision handling — attach images or a described-image "prime")
    primes: list[str] = list(system_primes or [])
    # ...

    # 4. Context compression: if the history is too long, summarize the old part.
    summary_text = conversation.summary
    recent = history[conversation.summarized_count:]
    total_tokens = sum(estimate_tokens(m.content) for m in history)
    if budget and (total_tokens > budget or conversation.summarized_count):
        result = await Summarizer(provider).compress(...)
        recent, summary_text = result.recent, result.summary
        # ...persist the new summary...

    # 5. Assemble the final prompt: system primes -> summary -> recent turns.
    prompt: list[ChatMessage] = []
    for prime in primes:
        prompt.append(ChatMessage(role="system", content=prime))
    if summary_text:
        prompt.append(ChatMessage(role="system",
                                  content=f"Summary...\n{summary_text}"))
    prompt.extend(recent)

    # 6. Stream the reply, forwarding each token AND collecting them.
    parts: list[str] = []
    async for token in provider.stream_chat(chosen_model, prompt):
        parts.append(token)
        yield token                     # <-- to the WebSocket, live

    # 7. Save the finished reply and auto-title the chat.
    await self._messages.add(conversation_id, "assistant", "".join(parts),
                             model=chosen_model)
```

**The three ideas to take away:**

1. **It's a generator that both forwards and accumulates.** `yield token` sends
   each word to the browser immediately (the typing effect), while `parts.append`
   keeps a copy so it can save the full message at the end (step 7). One loop, two
   jobs.
2. **The prompt is *assembled*, not fixed.** Steps 3–5 decide what text goes in
   front of the model: image descriptions, a running summary, retrieved memory.
   This is the "every capability is really prompt construction" idea, in code.
3. **It depends only on interfaces.** `provider` is an `LLMProvider`; `_messages`
   is a repository. It never mentions Ollama or SQLite. That's why the test suite
   can run this exact method with a fake provider that yields `"Hello"` and a
   throwaway database.

---

## Part 6 — The web layer (`main.py`)

A plain REST route is thin — gather inputs, call a layer, return:

```python
@app.get("/api/conversations", response_model=list[ConversationOut])
async def list_conversations(session: AsyncSession = Depends(get_session)):
    repo = ConversationRepository(session)
    return [ConversationOut.model_validate(c) for c in await repo.list()]
```

- `@app.get(...)` maps this function to `GET /api/conversations`. *Java/Spring:
  `@GetMapping`.*
- `Depends(get_session)` — FastAPI builds a database session and passes it in.
  *Dependency injection, like `@Autowired`.*
- `ConversationOut.model_validate(c)` turns a database object into a **Pydantic
  schema** — the clean public shape. *Like mapping a JPA entity to a DTO before
  returning it, so your API contract doesn't leak your table structure.*

The **WebSocket** handler is where streaming happens:

```python
@app.websocket("/ws/chat/{conversation_id}")
async def chat_ws(websocket: WebSocket, conversation_id: str):
    await websocket.accept()
    registry = websocket.app.state.registry
    while True:
        raw = await websocket.receive_text()      # wait for a message
        message = json.loads(raw)
        content = message.get("content", "").strip()

        async with SessionLocal() as session:     # a DB session per turn
            service = ChatService(ConversationRepository(session),
                                  MessageRepository(session),
                                  registry, settings)
            await websocket.send_json({"type": "start"})
            async for token in service.stream_turn(conversation_id, content, ...):
                await websocket.send_json({"type": "token", "data": token})
            await websocket.send_json({"type": "done"})
```

- `while True:` + `await websocket.receive_text()` — the connection stays open and
  the handler waits for each message you send. *Unlike a normal request that
  returns once, this loops for the life of the socket.*
- For each token the service yields, it sends `{"type":"token","data": "..."}` down
  the socket. The frontend appends each to the bubble.
- The events form a tiny **protocol**: `start` → many `token`s → `done` (plus
  `sources`, `web_sources`, `tool_call`, `approval_request` for the fancier
  features). *Think of it as a small enum of message kinds both sides agree on.*

---

## Part 7 — RAG search is just NumPy (`rag/retriever.py`)

The "chat with your documents" magic is linear algebra you already know from
Pandas/NumPy. Given the question's embedding and all the stored chunk embeddings:

```python
def retrieve(query_embedding, query_text, chunks, top_k=5, alpha=0.65):
    # Normalize the query vector to unit length.
    query = np.asarray(query_embedding, dtype=np.float32)
    query_norm = query / (np.linalg.norm(query) + 1e-9)

    # Stack every chunk's vector into a matrix and normalize each row.
    matrix = np.vstack([unpack_vector(c.embedding) for c in chunks])
    matrix_norm = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)

    # One matrix-vector product = cosine similarity of the query vs every chunk.
    semantic = matrix_norm @ query_norm

    # Also count shared keywords (lexical), then blend the two signals.
    combined = alpha * _minmax(semantic) + (1 - alpha) * _minmax(lexical)

    # Take the indices of the top-k highest scores.
    order = np.argsort(-combined)[:top_k]
    return [ScoredChunk(chunks[i], float(combined[i])) for i in order]
```

**Reading it:**

- An **embedding** is a `np.array` of floats capturing meaning. Two texts with
  similar meaning have vectors pointing in similar directions.
- Normalizing to unit length + a dot product (`matrix_norm @ query_norm`) **is**
  cosine similarity — the cosine of the angle between vectors. `1.0` = identical
  direction (very similar), `0.0` = unrelated. *`@` is NumPy's matrix multiply;
  this one line scores the query against thousands of chunks at once.*
- `np.argsort(-combined)[:top_k]` sorts scores descending and takes the best few.
- There's **no AI in the search itself** — the AI was used earlier to *make* the
  vectors; finding the match is pure geometry. Those top chunks then get pasted
  into the prompt (Part 5, step 3), which is the whole RAG trick.

---

## Part 8 — The frontend, briefly

**`lib/api.ts`** wraps every backend call in a typed function, with all error
handling in one helper:

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error((await res.json()).detail ?? res.statusText);
  return (await res.json()) as T;
}

export const api = {
  listConversations: () => request<Conversation[]>("/api/conversations"),
  createConversation: (model?: string) =>
    request<ConversationWithMessages>("/api/conversations", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  // ...
};
```

*`request<T>` is a generic method — `<T>` is a type parameter exactly like Java
generics `<T>`. It says "this returns whatever type the caller asks for," so
`listConversations()` is typed as returning `Conversation[]`.* Every component
calls `api.something()` and never touches a URL.

**`lib/useChat.ts`** is a custom **hook** — a reusable bundle of state + behavior.
The streaming happens here (simplified):

```typescript
const assistantId = tempId();
// optimistically show your message + an empty assistant bubble
setMessages((prev) => [...prev, userMsg, { id: assistantId, role: "assistant",
                                           content: "" }]);

const ws = new WebSocket(`${wsBase()}/ws/chat/${conversationId}`);
ws.onopen = () => ws.send(JSON.stringify({ content, model, use_web, /* ... */ }));

ws.onmessage = (event) => {
  const msg = JSON.parse(event.data);
  if (msg.type === "token") {
    setMessages((prev) => prev.map((m) =>
      m.id === assistantId ? { ...m, content: m.content + msg.data } : m));
  } else if (msg.type === "done") {
    setStreaming(false);
    ws.close();
  }
};
```

**The React idea to grasp:** you never say "append this text to that box." You call
`setMessages(newArray)` and React **re-draws** the message list to match the new
data. The UI is a *function of the state*. *This is the opposite of Java Swing's
`label.setText(...)`; here you change the data and the screen follows automatically.*
Each arriving token updates the assistant message's `content`, and the bubble
re-renders — that's the live typing.

---

## Part 9 — How to trace any feature yourself

When you want to understand a feature, follow the data. Example — "how does the
Web toggle work?"

1. **Frontend origin:** the `Web` chip flips `useWeb` state (`app/page.tsx`).
2. **Sent:** `useChat` includes `use_web: true` in the WebSocket message.
3. **Received:** `main.py`'s `chat_ws` reads `use_web`, and if set, calls
   `_web_context(query)` which searches + fetches pages and builds a prime string.
4. **Injected:** that prime is passed to `stream_turn` as a `system_prime`, so it
   lands in the prompt (Part 5, step 5).
5. **Cited:** the handler also sends a `web_sources` event, which `useChat` attaches
   to the message and `MessageBubble` renders as clickable links.

Every feature is that same trace: **UI state → WebSocket message → handler in
`main.py` → prompt construction in `chat_service.py` → provider → tokens back →
UI.** Once you can follow one feature end to end, you can follow them all — and
you can add your own by copying the trace.

---

## Appendix — the recurring patterns, named

You've now seen these repeatedly. Naming them makes them yours:

- **Strategy pattern** — many implementations behind one interface
  (`LLMProvider`, `EmbeddingProvider`, `ImageGenerator`). Add a new one without
  touching callers.
- **Repository pattern** — all queries for one entity behind one class. Storage is
  swappable and testable.
- **Dependency injection** — pass a class its collaborators (DB session, provider)
  instead of it building them. Makes fakes trivial in tests.
- **DTO / schema separation** — Pydantic `...Out` classes are the public wire
  shape, kept apart from ORM models so the API and the database can evolve
  independently.
- **Generators for streaming** — `yield` tokens so the UI can render them live
  instead of waiting for the whole reply.
- **Prompt assembly** — features work by deciding what text precedes the model, not
  by changing the model.

Those six patterns, plus "one job per layer," are the entire architecture. The
rest is detail.
