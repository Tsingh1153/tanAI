# How tanAI Works — A Builder's Guide

*Written for someone comfortable with Java (classes, interfaces, OOP) and Python
up to the Pandas level. By the end you should understand not just what this app
does, but the ideas behind it well enough to build something similar yourself.*

---

## 0. How to read this

You don't need to read top to bottom in one sitting. The order is deliberate,
though: each section builds on the last.

1. **The big picture** — what the app is and its two halves.
2. **Core concepts** — the handful of ideas everything rests on.
3. **The backend** — where the real logic lives, layer by layer.
4. **The intelligence** — RAG, memory, agents, vision, web search, explained from scratch.
5. **The frontend** — how the screen works and talks to the backend.
6. **How to build one yourself** — the method, not just the result.
7. **Glossary** — every term in one place.

Analogies to Java and Pandas appear throughout in *italics*.

---

## 1. The big picture

tanAI is a **web application** that runs entirely on your own computer. "Web
application" doesn't mean it's on the internet — it means it's built with web
technology (a browser page) but the server it talks to is also your machine.

It has **two programs** that run at the same time and talk to each other:

- **The backend** (Python) — the "brain." It holds the logic: talking to the AI
  model, saving conversations, searching documents, running tools. It has no
  visual appearance; it just answers requests. It runs on `localhost:8000`.
- **The frontend** (TypeScript/React) — the "face." It's the chat interface you
  see in the browser: the sidebar, the message bubbles, the input box. It runs
  on `localhost:3000` and it can't think for itself — every time it needs
  something real, it asks the backend.

*Think of a restaurant. The frontend is the dining room and the waiter — pretty,
interactive, but it doesn't cook. The backend is the kitchen — no customers see
it, but that's where the food is made. They communicate through order tickets.*

A third program is involved but isn't part of tanAI: **Ollama**, the engine that
actually runs the language model. The backend sends Ollama a prompt and Ollama
streams back the words. tanAI never "contains" the model — it orchestrates it.

So the flow of a single message is:

```
You type → Frontend → (WebSocket) → Backend → (HTTP) → Ollama → model
                                       ↓
                          saves to database, retrieves memory,
                          searches docs, etc.
                                       ↓
You see words appear ← Frontend ← (WebSocket) ← Backend ← Ollama streams tokens
```

Everything else in this guide is just detail hung on that skeleton.

---

## 2. Core concepts

Five ideas. Once these click, the whole codebase reads easily.

### 2.1 Client and server

A **server** is a program that waits for requests and sends back responses. A
**client** is a program that makes requests. The frontend is a client; the
backend is a server; and confusingly, the backend is *also* a client when it
calls Ollama. "Client" and "server" are roles in a conversation, not fixed
identities.

### 2.2 An API is a menu of things you can ask for

The backend exposes an **API** (Application Programming Interface): a fixed set
of URLs, each of which does one thing. For example:

- `GET /api/conversations` → "give me the list of chats"
- `POST /api/conversations` → "make a new chat"
- `DELETE /api/conversations/{id}` → "delete this chat"

`GET`, `POST`, `DELETE` are **HTTP methods** — verbs. The convention: GET reads,
POST creates, PATCH edits, DELETE removes. *This is just like a set of public
methods on a Java class, except you call them over the network with a URL
instead of `object.method()`.*

Data goes back and forth as **JSON** — text that looks like Python dicts:
`{"title": "New chat", "id": "abc"}`. Both Python and JavaScript speak it
natively.

### 2.3 HTTP vs WebSocket

Normal API calls are **request → response → done.** You ask, you get one answer,
the line hangs up. That's HTTP. Great for "list my chats."

But a chatbot reply arrives **word by word over several seconds.** You don't want
to wait for the whole thing, then dump it. You want to watch it type. For that we
use a **WebSocket** — a connection that stays *open* so the server can keep
pushing data down it until it's done. That's why the chat uses
`ws://localhost:8000/ws/chat/...` instead of a normal URL.

*HTTP is texting: one message, one reply. WebSocket is a phone call: the line
stays open and either side can talk whenever.*

### 2.4 Async (the app juggles instead of waiting)

When the backend asks Ollama for a reply, Ollama takes seconds. If the program
just *froze* and waited, it couldn't do anything else — no other user, no saving,
nothing. Python's **async/await** lets it say "start this, and while I wait, go do
other useful work." You'll see `async def` and `await` everywhere.

*In Java terms this is like non-blocking I/O or `CompletableFuture`, but with much
nicer syntax. `await something()` means "pause this one task here until the result
is ready, but let other tasks run meanwhile."* You don't need to master it to read
the code — just know that `await` marks "this line waits for something slow."

### 2.5 Types and models

Both halves are **statically typed** — every variable has a declared type, checked
before the program runs. Python uses type hints (`def add(x: int) -> int:`) plus a
library called **Pydantic** that validates data at the boundaries. TypeScript is
JavaScript with types bolted on. *If you liked how Java catches `String`-vs-`int`
mistakes at compile time, this is the same safety net, and it's why the app rarely
crashes on bad data.*

---

## 3. The backend, layer by layer

The backend's golden rule: **each layer has one job and only talks to the layer
next to it.** This is the single most important design idea in the whole project,
and it's why the app could grow to a dozen features without turning into
spaghetti.

Here are the layers, from the outside in:

```
HTTP/WebSocket request
        │
   ┌────▼─────┐   routes (main.py)         "what URL was hit? gather inputs"
   │  Routes  │
   └────┬─────┘
        │
   ┌────▼─────┐   services (chat_service)  "the actual business logic"
   │ Services │
   └────┬─────┘
        │
   ┌────▼──────────┐  repositories         "read/write the database"
   │ Repositories  │
   └────┬──────────┘
        │
   ┌────▼─────┐   models (ORM classes)     "the shape of a row in a table"
   │  Models  │
   └──────────┘

   (off to the side: providers = "how to talk to an AI model")
```

Let me walk each one.

### 3.1 Models — the shape of your data

Open `backend/app/models.py`. You'll see classes like `Conversation`, `Message`,
`Memory`. Each class is a **table** in the database, and each attribute is a
**column**:

```python
class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    role: Mapped[str] = mapped_column(String(16))       # "user" or "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

This is an **ORM** (Object-Relational Mapper). *If you've seen JPA/Hibernate in
Java, this is exactly that: a Python object is a row, saving the object writes the
row, and you never write raw SQL.* The library is **SQLAlchemy**, and the actual
data lives in a single file, `localmind.db` (a **SQLite** database — a whole
database in one file, no server needed).

Why an ORM instead of raw SQL? Because you get to think in objects (`message.content`)
instead of strings of SQL, and the types are checked. *Same reason you'd rather
use an `ArrayList<Message>` than parse a CSV by hand.*

### 3.2 Repositories — the only place that touches the database

A **repository** is a small class whose only job is database queries for one kind
of thing. `ConversationRepository` has `list()`, `get(id)`, `create()`,
`delete()`. Nothing else in the app is allowed to run database queries — it must
go through a repository.

Why bother? Two reasons:

1. **All the queries for conversations live in one file.** If a query is slow or
   wrong, you know exactly where to look.
2. **You can swap the storage without touching the rest of the app.** Today it's
   SQLite; if you moved to Postgres, only the repositories would care.

*This is the Repository Pattern, straight out of enterprise Java. It's a form of
encapsulation: hide the messy details (SQL) behind a clean interface (methods).*

### 3.3 Services — the business logic

A **service** coordinates. `ChatService.stream_turn(...)` is the heart of the app.
When you send a message, it:

1. Saves your message (via the message repository).
2. Loads the conversation history.
3. Decides whether the history is too long and needs summarizing.
4. Assembles the final prompt (history + any memory + any retrieved documents).
5. Streams the reply from the model provider, token by token.
6. Saves the finished reply.

Notice what it does **not** do: it doesn't know about HTTP, it doesn't write SQL,
it doesn't know which specific AI model is running. It just orchestrates other
layers. *This is the "single responsibility principle" — the S in SOLID. A class
should have one reason to change.* Because the service knows nothing about the web,
we can call it from both the WebSocket handler and a plain REST endpoint, and we
can test it with a fake model.

### 3.4 Routes — the front door

`main.py` defines the **routes**: the mapping from a URL to a function. It uses
**FastAPI**, a Python web framework. A route looks like this:

```python
@app.get("/api/conversations")
async def list_conversations(session = Depends(get_session)):
    repo = ConversationRepository(session)
    return [ConversationOut.model_validate(c) for c in await repo.list()]
```

Three things to notice:

- `@app.get("/api/conversations")` — a **decorator** that says "run this function
  when someone GETs this URL." *Java has annotations like `@GetMapping` in Spring;
  this is identical in spirit.*
- `Depends(get_session)` — **dependency injection.** FastAPI automatically creates
  a database session and hands it in. The function doesn't build its own
  dependencies; they're provided. *Exactly like Spring's `@Autowired` or a DI
  container — it makes testing easy because you can inject a fake.*
- `ConversationOut.model_validate(...)` — converts a database object into a
  **Pydantic schema**, the clean public shape that gets sent as JSON. Schemas
  (`schemas.py`) are separate from models on purpose: the database shape can change
  without breaking the API's promise to the frontend.

Routes stay **thin** — they gather inputs, call a service or repository, and return
a result. All the thinking is a layer down.

### 3.5 Providers — the key abstraction, and why it matters most

This is the cleverest part of the design, so slow down here.

The app needs to talk to a language model. But there are *many* ways to run a model:
Ollama, LM Studio, a cloud API like OpenAI, Apple's built-in model. They all have
different URLs and formats. We do **not** want the chat logic tangled up with
"if Ollama do this, if OpenAI do that."

So we define an **interface** — a contract that says "any model provider must offer
these three abilities":

```python
class LLMProvider(ABC):
    async def list_models(self) -> list[ProviderModel]: ...
    def stream_chat(self, model, messages) -> AsyncIterator[str]: ...
    async def health(self) -> bool: ...
```

*This is literally a Java `interface` (`ABC` = Abstract Base Class = interface).*
Then each backend is a class that **implements** the interface: `OllamaProvider`,
`OpenAICompatibleProvider`. The rest of the app only ever refers to the interface,
never a concrete class. It calls `provider.stream_chat(...)` without knowing or
caring which one it got.

This is the **Strategy Pattern**, and its payoff is enormous. When macOS shipped a
built-in AI model with an OpenAI-compatible API, we added support with **zero new
code** — the existing `OpenAICompatibleProvider` already spoke that language. When
we added cloud models, agents, vision — all of it plugged into this one seam.

**The lesson to steal:** find the thing in your project that has many variations
(storage backends, payment processors, notification channels...) and hide all of
them behind one interface. Everything downstream gets simpler and future-proof.

### 3.6 Streaming, concretely

`stream_chat` returns an **async generator** — a function that `yield`s values one
at a time, asynchronously. *You know Python generators from `yield`; this is the
same, but each item can `await` slow work.* The WebSocket handler does:

```python
async for token in service.stream_turn(...):
    await websocket.send_json({"type": "token", "data": token})
```

Each token the model produces is immediately shipped down the open WebSocket to the
browser, which appends it to the bubble. That's the "typing" effect — it's not
cosmetic, it's the data genuinely arriving piece by piece.

---

## 4. The intelligence — how the "smart" features actually work

None of these features required a smarter *model*. They're clever plumbing around a
model that, on its own, only knows how to continue text.

### 4.1 The fundamental trick: it's all just the prompt

A language model has no memory and no senses. It takes text in, predicts text out.
**Every "capability" in this app is really a trick of putting the right text into
the prompt before the model sees it.** Remembering you? Inserting facts about you.
Reading a document? Pasting the relevant paragraph in. Searching the web? Pasting
search results in. Hold onto this idea — it demystifies everything below.

### 4.2 RAG — chatting with your documents

RAG = Retrieval-Augmented Generation. The problem: the model hasn't read your PDF.
The solution: find the relevant part of your PDF and paste it into the prompt.

But how do you "find the relevant part"? You can't just keyword-match ("car" won't
find a paragraph about "automobiles"). This is where **embeddings** come in, and
they're beautiful:

An **embedding** is a list of numbers (a vector) that represents the *meaning* of a
piece of text. A special model (`nomic-embed-text`) turns "the cat sat on the mat"
into something like `[0.02, -0.15, 0.88, ...]` (hundreds of numbers). The key
property: **texts with similar meaning get similar vectors.** "automobile" and "car"
land close together in this number-space, even though they share no letters.

*You already know vectors from NumPy — an embedding is exactly a NumPy array. And
"how similar are two vectors" is just an angle between them: **cosine similarity**,
a one-line dot-product. tanAI stores every document chunk's vector and, at query
time, computes the cosine similarity between your question's vector and all of them
with NumPy, then grabs the closest few.* That's the whole magic — no AI in the
search step, just geometry.

The pipeline (`app/rag/`):

1. **Parse** the file into text (PDF, Word, etc. — `parsers.py`).
2. **Chunk** it into ~1000-character pieces (`chunker.py`), because a whole book
   won't fit in one vector meaningfully.
3. **Embed** each chunk → store the vector in the database.
4. At query time: embed your question, find the closest chunks (cosine similarity),
   paste them into the prompt with "answer using this context," and cite them.

### 4.3 Memory and summarization — beating the context limit

A model can only "see" a fixed amount of text at once (its **context window**, e.g.
8,192 tokens — a token is roughly ¾ of a word). Two problems, two fixes:

- **Long conversation overflows the window.** Fix: when the chat gets long,
  `Summarizer` asks the model to compress the oldest turns into a short summary, and
  future prompts use `[summary] + recent messages` instead of everything. The chat
  can run forever without the model ever seeing more than fits.
- **Facts should persist across separate chats.** Fix: **long-term memory.** After
  each exchange, an extraction step asks the model "any durable facts about the user
  here?" and stores them (as embeddings, reusing the RAG machinery). In a new chat,
  relevant memories are retrieved by similarity and pasted into the prompt. That's
  how it "remembers" you across conversations — it's re-reading saved notes each
  time, not truly remembering.

### 4.4 Agents and tools — letting it *do* things

Left alone, the model can only produce text. **Tool calling** lets it act. We give
the model a list of tools with descriptions ("`web_search(query)` — searches the
web"). Modern models can respond with "I want to call `web_search` with
`query='...'`" instead of a normal answer.

The **agent loop** (`app/agent/agent_service.py`) is then simple:

```
loop:
    ask the model (with the tool list)
    if it asked for a tool:
        run the tool, feed the result back
        continue looping
    else:
        that's the final answer, stop
```

*Think of it as a `while` loop where the model is the decision-maker and your code
is its hands.* Sensitive tools (writing files, running code, controlling the mouse)
are gated behind an **approval prompt** — the loop pauses and waits for you to click
Approve. Safety here is deliberate: the tools are confined to a sandbox folder, code
runs with a timeout, and every call is logged.

### 4.5 Vision, web search, image generation — same pattern, different data

- **Vision:** images are sent alongside the text to a model that can see. If your
  chosen model is text-only, "vision assist" routes the image to a vision model to
  *describe* it, then pastes that description into the prompt — giving a blind model
  borrowed eyes.
- **Web search:** search the web, fetch the top pages, paste their text into the
  prompt as context (with citations). Same shape as RAG, but the "documents" are
  live web results.
- **Image generation:** the one thing that's *not* just prompt-stuffing — it calls a
  separate image model (Stable Diffusion or an API) and hands back a picture.

Notice the recurring shape: **gather relevant text → put it in the prompt → let the
model write.** Master that one move and you can add "capabilities" endlessly.

### 4.6 Personas — specializing the model without retraining

The finance "modes" (Personal Finance, Markets & Investing, Corporate Finance,
Finance Tutor) are the purest example of section 4.1's idea. A persona is nothing
but a **system prompt** — a paragraph telling the model who to be and how to
answer. The backend keeps them in one file (`app/personas.py`) and serves them at
`/api/personas`; the frontend shows them as tabs. When you pick a tab, its id
rides along with your message, and the WebSocket handler prepends that persona's
prompt to the same "system primes" list that memory, RAG, and web search feed
into. The model isn't retrained or swapped — it just receives different
instructions, so it *behaves* like a finance tutor.

This is why "specializing" a modern LLM app usually means **prompting + retrieval**,
not building a neural network. Pair a persona with the bundled finance corpus
(loaded via `scripts/seed_corpus.py`) and you get a specialist that both talks and
cites like one — for a fraction of the effort of fine-tuning. Every finance persona
also carries an education-not-advice guardrail, so the model explains concepts
without posing as a licensed advisor.

---

## 5. The frontend

The frontend is a **React** app (with **Next.js**, a framework on top of React, and
**Tailwind CSS** for styling). Three ideas explain most of it.

### 5.1 Components are reusable UI Lego

A **component** is a function that returns a piece of screen. `MessageBubble` draws
one chat message. `Sidebar` draws the left rail. `Composer` is the input box. You
build the whole UI by nesting small components. *Think of each component as a class
whose `render()` returns HTML, and you compose them like objects.* They live in
`frontend/components/`.

### 5.2 State and re-rendering

**State** is data that can change over time — the list of messages, whether we're
currently streaming, the current model. In React you declare state with
`useState`, and the golden rule is: **when state changes, React automatically
redraws the parts of the screen that depend on it.** You never manually update the
DOM ("put this text in that box"); you change the data and the screen follows.

*This is the biggest mental shift from, say, Java Swing, where you'd call
`label.setText(...)` yourself. In React you say `setMessages(newList)` and the
message list re-renders itself. The UI is a function of the state.*

### 5.3 Hooks bundle logic

The file `lib/useChat.ts` is a **custom hook** — a reusable bundle of state plus
logic. It owns the message list and the WebSocket. A component calls
`const { messages, send } = useChat(chatId)` and gets both the data to display and
the function to send a message, without caring how the WebSocket works underneath.
*It's the same encapsulation instinct as the backend's services: hide the machinery,
expose a clean handle.*

### 5.4 How the frontend talks to the backend

Every network call is funneled through `lib/api.ts` — one file that knows the
backend's address and has a typed function per endpoint (`api.listConversations()`,
`api.createConversation()`). Components never write URLs; they call these functions.
*Same principle again: one place that knows a detail (the API), everything else
depends on the clean wrapper.* The streaming chat is the exception — it uses a raw
WebSocket in `useChat` because it needs the always-open connection.

---

## 6. How to build something like this yourself

The features are impressive, but the *method* is the transferable skill. Here's how
this was actually built, in order, and how you'd do it too.

**1. Start with the thinnest possible thing that works end to end.** The very first
version was: one backend endpoint, one model, streaming text, and a bare chat box.
No RAG, no memory, no agents. This is a **vertical slice** — a sliver that touches
every layer (screen → server → model → screen) and actually runs. Get *something*
working before you get *everything* working. A running skeleton beats a perfect plan.

**2. Draw your layers before you write logic.** Decide "routes call services,
services call repositories, repositories touch the database" up front. The
discipline of never skipping a layer is what keeps a growing project sane.

**3. Find the seams and put interfaces there.** Anywhere you'll have more than one
option later (which model? which database? which search engine?), define an
interface now and code against it. This one habit is why every later feature
"just plugged in."

**4. Add one feature at a time, and test each before the next.** Every subsystem
here shipped with a small test that ran it end-to-end with fake stand-ins for the
slow/external parts (a fake model, a fake search). *Fakes are just classes
implementing the same interface — trivial because of step 3.* When the test passes,
that feature is done and you can build the next on solid ground.

**5. Keep the boring stuff centralized.** Configuration in one file, all API calls
in one file, all database queries behind repositories. Boring, findable, changeable.

**6. Be honest about limits.** A local 7B model is not a frontier model. Good
engineering can't fix that — but knowing *which* problems are solvable by code
(features) and which aren't (raw intelligence) is what lets you spend effort well.

If you internalize those six, you can build a RAG app, a different agent, a
completely unrelated web app — the shapes are the same.

---

## 7. Glossary

- **API** — the set of URLs a server offers; its public methods.
- **Async / await** — lets one program do other work while waiting on slow things.
- **Backend / frontend** — the logic server / the visual client.
- **Chunk** — a small slice of a document, sized to embed meaningfully.
- **Component** — a reusable piece of UI in React.
- **Context window** — the max amount of text a model can consider at once.
- **Cosine similarity** — a number (−1 to 1) for how alike two vectors are; used to
  find relevant text.
- **Dependency injection** — dependencies are handed to a function instead of it
  building them; makes testing and swapping easy.
- **Embedding** — a vector of numbers capturing a text's meaning; similar meanings →
  nearby vectors.
- **FastAPI** — the Python web framework used for the backend.
- **Hook** — a reusable bundle of state + logic in React (`useState`, `useChat`).
- **HTTP** — request/response networking (one ask, one answer).
- **Interface / ABC** — a contract of methods a class promises to implement.
- **JSON** — text data format that looks like a Python dict.
- **LLM** — Large Language Model; the text-predicting AI.
- **ORM** — maps database rows to objects (SQLAlchemy); like JPA/Hibernate.
- **Ollama** — the separate engine that runs the model locally.
- **Pydantic** — validates and shapes data at the API boundary.
- **RAG** — Retrieval-Augmented Generation; find relevant text, paste into prompt.
- **Repository** — the only class allowed to run queries for one data type.
- **Route** — a function mapped to a URL.
- **Service** — a class holding business logic; coordinates other layers.
- **State** — changeable UI data; changing it re-renders the screen.
- **Strategy pattern** — many implementations behind one interface (the providers).
- **Token** — a chunk of text (~¾ of a word) the model reads/writes in.
- **Vector** — a list of numbers (a NumPy array); an embedding is one.
- **WebSocket** — a connection that stays open so the server can stream data.

---

*You built (well, directed the building of) a real, layered, extensible AI
application. The parts that look like magic — memory, document chat, agents — are
all the same honest trick: put the right text in front of the model. The parts that
look like architecture — providers, repositories, services — are all the same honest
discipline: one job per layer, interfaces at the seams. Take those two ideas to your
next project.*
