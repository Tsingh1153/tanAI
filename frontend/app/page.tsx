"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Settings2 } from "lucide-react";
import { speak, stopSpeaking } from "@/lib/tts";
import clsx from "clsx";
import { Sidebar } from "@/components/Sidebar";
import { MessageList } from "@/components/MessageList";
import { Composer } from "@/components/Composer";
import { ModelSelector } from "@/components/ModelSelector";
import { ThemeToggle } from "@/components/ThemeToggle";
import { DocumentsPanel } from "@/components/DocumentsPanel";
import { MemoryPanel } from "@/components/MemoryPanel";
import { SettingsPanel } from "@/components/SettingsPanel";
import { ApprovalPrompt } from "@/components/ApprovalPrompt";
import { WebcamPanel } from "@/components/WebcamPanel";
import { ImagePanel } from "@/components/ImagePanel";
import { Logo } from "@/components/Logo";
import { PersonaTabs } from "@/components/PersonaTabs";
import { PersonasPanel } from "@/components/PersonasPanel";
import { Toolbar } from "@/components/Toolbar";
import { BootSplash } from "@/components/BootSplash";
import { CommandPalette, type Command } from "@/components/CommandPalette";
import { Onboarding } from "@/components/Onboarding";
import { useChat } from "@/lib/useChat";
import { api } from "@/lib/api";
import { personaColor, personaTint, startersFor } from "@/lib/personaStyle";
import type { Conversation, Health, ModelInfo, Persona } from "@/lib/types";

export default function Home() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [model, setModel] = useState<string>("");
  const [provider, setProvider] = useState<string>("ollama");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [health, setHealth] = useState<Health | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [docsOpen, setDocsOpen] = useState(false);
  const [availableDocs, setAvailableDocs] = useState(0);
  const [useRag, setUseRag] = useState(false);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [universalMemory, setUniversalMemory] = useState(true);
  const [webcamOpen, setWebcamOpen] = useState(false);
  const [imageOpen, setImageOpen] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(false);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [persona, setPersona] = useState<string | null>(null);
  const [personasOpen, setPersonasOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const prevStreamingRef = useRef(false);

  // Show the welcome/setup guide on first run.
  useEffect(() => {
    if (!localStorage.getItem("tanai-onboarded")) setOnboardingOpen(true);
  }, []);

  // Universal memory is a persisted preference (on by default), set in Settings.
  useEffect(() => {
    if (localStorage.getItem("tanai-universal-memory") === "0") {
      setUniversalMemory(false);
    }
  }, []);

  const changeUniversalMemory = useCallback((value: boolean) => {
    setUniversalMemory(value);
    try {
      localStorage.setItem("tanai-universal-memory", value ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, []);

  // Each chat remembers the mode it was used in (persisted), so switching chats
  // restores its mode and the sidebar can mark it.
  const [convPersona, setConvPersona] = useState<Record<string, string | null>>(
    {},
  );
  const convPersonaRef = useRef(convPersona);
  useEffect(() => {
    convPersonaRef.current = convPersona;
  }, [convPersona]);
  useEffect(() => {
    try {
      const raw = localStorage.getItem("tanai-conv-persona");
      if (raw) setConvPersona(JSON.parse(raw));
    } catch {
      /* ignore */
    }
  }, []);

  const rememberPersona = useCallback(
    (convId: string, personaId: string | null) => {
      setConvPersona((prev) => {
        const next = { ...prev, [convId]: personaId };
        try {
          localStorage.setItem("tanai-conv-persona", JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [],
  );

  // Adopt a chat's saved mode when it becomes active.
  useEffect(() => {
    if (activeId) setPersona(convPersonaRef.current[activeId] ?? null);
  }, [activeId]);

  const choosePersona = useCallback(
    (id: string | null) => {
      setPersona(id);
      if (activeId) rememberPersona(activeId, id);
    },
    [activeId, rememberPersona],
  );

  const closeOnboarding = useCallback(() => {
    try {
      localStorage.setItem("tanai-onboarded", "1");
    } catch {
      /* ignore */
    }
    setOnboardingOpen(false);
  }, []);

  const {
    messages,
    streaming,
    error,
    pendingApproval,
    send,
    regenerate,
    editResend,
    approve,
    stop,
  } = useChat(activeId);

  // Shared generation options for send / regenerate / edit.
  const chatOptions = useCallback(
    () => ({
      model: model || undefined,
      provider: provider || undefined,
      useRag: useRag && availableDocs > 0,
      useMemory: universalMemory,
      persona: persona ?? undefined,
    }),
    [model, provider, useRag, availableDocs, universalMemory, persona],
  );

  // Stable handlers for message edit / regenerate (keeps memoized bubbles from
  // re-rendering on every streamed token).
  const handleEdit = useCallback(
    (id: string, content: string) => editResend(id, content, chatOptions()),
    [editResend, chatOptions],
  );
  const handleRegenerate = useCallback(
    () => regenerate(chatOptions()),
    [regenerate, chatOptions],
  );

  // Documents available to the active chat = its own uploads + global "memory".
  const refreshDocs = useCallback(async () => {
    try {
      const list = await api.listDocuments(activeId ?? undefined);
      const ready = list.filter((d) => d.status === "ready");
      const count = activeId
        ? ready.length
        : ready.filter((d) => !d.conversation_id).length;
      setAvailableDocs(count);
      if (count === 0) setUseRag(false);
    } catch {
      setAvailableDocs(0);
    }
  }, [activeId]);

  const refreshHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
    } catch {
      /* backend may be momentarily busy; ignore */
    }
    await refreshDocs();
  }, [refreshDocs]);

  // Re-scope the document count whenever the active chat changes.
  useEffect(() => {
    refreshDocs();
  }, [refreshDocs]);

  // Auto-speak: read a reply aloud only when it *finishes* streaming (the
  // true->false transition), never on load or when toggling the setting.
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current;
    prevStreamingRef.current = streaming;
    if (speakReplies && wasStreaming && !streaming) {
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant" && last.content) {
        speak(last.content);
      }
    }
  }, [streaming, speakReplies, messages]);

  const refreshConversations = useCallback(async () => {
    const list = await api.listConversations();
    setConversations(list);
    return list;
  }, []);

  const refreshModels = useCallback(async () => {
    try {
      setModels(await api.listModels());
    } catch {
      /* providers may be momentarily offline */
    }
  }, []);

  const refreshPersonas = useCallback(async () => {
    try {
      const list = await api.listPersonas();
      setPersonas(list);
      // If the active persona was deleted, fall back to General.
      setPersona((cur) => (cur && list.some((p) => p.id === cur) ? cur : null));
    } catch {
      /* personas are optional; General mode still works */
    }
  }, []);

  // Keep the model list current: repopulates if Ollama starts after the app,
  // or once a newly downloaded model finishes.
  useEffect(() => {
    const id = setInterval(refreshModels, 15000);
    return () => clearInterval(id);
  }, [refreshModels]);

  // Initial load: health, models, conversation list. The bundled backend takes
  // a few seconds to boot on a cold start, so poll health for up to a minute
  // before showing an error — the boot splash stays up meanwhile.
  useEffect(() => {
    let cancelled = false;
    const waitForBackend = async () => {
      for (let attempt = 0; attempt < 40 && !cancelled; attempt++) {
        try {
          return await api.health();
        } catch {
          await new Promise((r) => setTimeout(r, 1500));
        }
      }
      return null;
    };
    (async () => {
      const h = await waitForBackend();
      if (cancelled) return;
      if (!h) {
        setLoadError(
          "Cannot reach the backend at " +
            (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000") +
            ". Is it running?",
        );
        return;
      }
      setLoadError(null);
      setHealth(h);
      setModel(h.default_model);
      try {
        const m = await api.listModels();
        setModels(m);
        // Default to the configured model on Ollama, else the first available.
        if (m.length > 0) {
          const preferred = m.find((x) => x.name === model) ?? m[0];
          setProvider((p) => p || preferred.provider);
          setModel((prev) => prev || preferred.name);
        }
      } catch {
        /* Ollama may be offline; model list stays empty. */
      }
      await refreshPersonas();
      const list = await refreshConversations();
      if (!cancelled && list.length > 0) setActiveId(list[0].id);
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshConversations, refreshPersonas]);

  // If the error screen ever shows, keep checking quietly so it recovers on its
  // own once the backend comes up — no need for the user to click "Try again".
  useEffect(() => {
    if (!loadError) return;
    const id = setInterval(async () => {
      try {
        await api.health();
        window.location.reload();
      } catch {
        /* still down; keep waiting */
      }
    }, 3000);
    return () => clearInterval(id);
  }, [loadError]);

  const activeConversation = conversations.find((c) => c.id === activeId);

  const handleNew = useCallback(async () => {
    const conv = await api.createConversation(model || undefined);
    await refreshConversations();
    setActiveId(conv.id);
  }, [model, refreshConversations]);

  // Guarantee a conversation exists (for uploading before the first message).
  const ensureConversation = useCallback(async (): Promise<string> => {
    if (activeId) return activeId;
    const conv = await api.createConversation(model || undefined);
    await refreshConversations();
    setActiveId(conv.id);
    return conv.id;
  }, [activeId, model, refreshConversations]);

  const handleDelete = useCallback(
    async (id: string) => {
      await api.deleteConversation(id);
      const list = await refreshConversations();
      if (id === activeId) setActiveId(list[0]?.id ?? null);
    },
    [activeId, refreshConversations],
  );

  // Attach files directly from the composer: upload to this chat, then turn
  // Documents on so the next message is grounded in them.
  const handleAttachFiles = useCallback(
    async (files: File[]) => {
      const targetId = await ensureConversation();
      for (const file of files) {
        try {
          await api.uploadDocument(file, targetId);
        } catch (e) {
          setLoadError(null);
          console.error(`Failed to read ${file.name}: ${(e as Error).message}`);
        }
      }
      await refreshDocs();
      setUseRag(true);
    },
    [ensureConversation, refreshDocs],
  );

  const handleSend = useCallback(
    async (text: string, images: string[] = []) => {
      let targetId = activeId;
      // Starting from the empty state: create a conversation on first send.
      if (!targetId) {
        const conv = await api.createConversation(model || undefined);
        targetId = conv.id;
        setActiveId(conv.id);
      }
      send(text, {
        model: model || undefined,
        provider: provider || undefined,
        useRag: useRag && availableDocs > 0,
        useMemory: universalMemory,
        persona: persona ?? undefined,
        images: images.length ? images : undefined,
      });
      rememberPersona(targetId, persona);
      // Refresh titles/order shortly after the turn begins.
      setTimeout(() => refreshConversations(), 400);
    },
    [
      activeId,
      model,
      provider,
      useRag,
      availableDocs,
      universalMemory,
      persona,
      send,
      refreshConversations,
      rememberPersona,
    ],
  );

  // Keyboard shortcuts: ⌘/Ctrl+K command palette, Esc stops generation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      } else if (e.key === "Escape" && streaming) {
        stop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [streaming, stop]);

  // Command palette actions — one source for navigation and toggles.
  const commands = useMemo<Command[]>(() => {
    const cmds: Command[] = [
      {
        id: "new-chat",
        label: "New chat",
        group: "Actions",
        hint: "⌘K",
        run: handleNew,
      },
    ];
    for (const c of conversations.slice(0, 20)) {
      cmds.push({
        id: `chat-${c.id}`,
        label: c.title || "Untitled chat",
        group: "Jump to chat",
        run: () => setActiveId(c.id),
      });
    }
    cmds.push({
      id: "model-auto",
      label: "Auto (route each message)",
      group: "Model",
      active: model === "auto",
      run: () => {
        setProvider("auto");
        setModel("auto");
      },
    });
    for (const m of models) {
      cmds.push({
        id: `model-${m.provider}-${m.name}`,
        label: m.name,
        group: "Model",
        hint: m.provider_label,
        active: model === m.name && provider === m.provider,
        run: () => {
          setProvider(m.provider);
          setModel(m.name);
        },
      });
    }
    cmds.push({
      id: "persona-general",
      label: "General",
      group: "Persona",
      active: persona === null,
      run: () => choosePersona(null),
    });
    for (const p of personas) {
      cmds.push({
        id: `persona-${p.id}`,
        label: p.label,
        group: "Persona",
        active: persona === p.id,
        run: () => choosePersona(p.id),
      });
    }
    if (availableDocs > 0) {
      cmds.push({
        id: "toggle-docs",
        label: "Toggle Documents",
        group: "Toggle",
        active: useRag,
        run: () => setUseRag((v) => !v),
      });
    }
    cmds.push(
      {
        id: "open-personas",
        label: "Manage personas",
        group: "Open",
        run: () => setPersonasOpen(true),
      },
      {
        id: "open-docs",
        label: "Manage documents",
        group: "Open",
        run: () => setDocsOpen(true),
      },
      {
        id: "open-memory",
        label: "Manage memory",
        group: "Open",
        run: () => setMemoryOpen(true),
      },
      {
        id: "open-image",
        label: "Generate image",
        group: "Open",
        run: () => setImageOpen(true),
      },
      {
        id: "open-webcam",
        label: "Webcam",
        group: "Open",
        run: () => setWebcamOpen(true),
      },
      {
        id: "open-settings",
        label: "Settings",
        group: "Open",
        run: () => setSettingsOpen(true),
      },
      {
        id: "open-onboarding",
        label: "Setup & help",
        group: "Open",
        run: () => setOnboardingOpen(true),
      },
    );
    return cmds;
  }, [
    handleNew,
    conversations,
    models,
    model,
    provider,
    personas,
    persona,
    choosePersona,
    useRag,
    availableDocs,
  ]);

  const offline = health && !health.provider_online;

  // Resizable sidebar (persisted).
  const [sidebarWidth, setSidebarWidth] = useState(288);
  const widthRef = useRef(288);
  const draggingRef = useRef(false);

  useEffect(() => {
    const saved = Number(localStorage.getItem("tanai-sidebar-width"));
    if (saved >= 220 && saved <= 520) {
      setSidebarWidth(saved);
      widthRef.current = saved;
    }
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (!draggingRef.current) return;
      const w = Math.min(520, Math.max(220, e.clientX));
      widthRef.current = w;
      setSidebarWidth(w);
    };
    const onUp = () => {
      if (!draggingRef.current) return;
      draggingRef.current = false;
      document.body.style.userSelect = "";
      try {
        localStorage.setItem("tanai-sidebar-width", String(widthRef.current));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <BootSplash ready={!!health || !!loadError} />
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        width={sidebarWidth}
        conversationPersona={convPersona}
        onSelect={setActiveId}
        onNew={handleNew}
        onDelete={handleDelete}
        onRefresh={refreshConversations}
      />
      <div
        onMouseDown={() => {
          draggingRef.current = true;
          document.body.style.userSelect = "none";
        }}
        className="w-1 shrink-0 cursor-col-resize bg-transparent transition-colors hover:bg-accent/40"
        title="Drag to resize"
      />

      <main
        className="flex h-full flex-1 flex-col transition-[background] duration-700"
        style={
          persona
            ? {
                backgroundImage: `linear-gradient(180deg, ${personaTint(persona, 0.14)}, transparent 55%)`,
              }
            : undefined
        }
      >
        {/* Header */}
        <header className="flex items-center justify-between border-b border-border bg-canvas px-4 py-2.5">
          <div className="flex items-center gap-3">
            <span className="text-sm font-medium text-content">
              {activeConversation?.title ?? "tanAI"}
            </span>
            {offline && (
              <span className="rounded-full bg-elevated px-2 py-0.5 text-xs text-accent">
                model backend offline
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <ModelSelector
              models={models}
              provider={provider}
              model={model}
              onChange={(p, m) => {
                setProvider(p);
                setModel(m);
              }}
              disabled={streaming}
            />
            <button
              onClick={() => setSettingsOpen(true)}
              title="Settings, providers & models"
              className="rounded-lg p-2 text-muted transition-colors hover:bg-elevated hover:text-content"
              aria-label="Settings"
            >
              <Settings2 size={18} />
            </button>
            <ThemeToggle />
          </div>
        </header>

        {/* Body */}
        {loadError ? (
          <div className="flex flex-1 items-center justify-center p-8 text-center">
            <div className="max-w-md">
              <h2 className="mb-2 text-lg font-semibold text-content">
                tanAI is still starting
              </h2>
              <p className="text-sm leading-relaxed text-muted">
                The engine that powers tanAI isn't ready yet. The first launch
                takes a minute or two while it sets itself up — this screen
                clears on its own once it's ready.
              </p>
              <div className="mt-5 flex items-center justify-center gap-2">
                <button
                  onClick={() => window.location.reload()}
                  className="rounded-lg border border-border px-3 py-1.5 text-sm text-content transition-colors hover:bg-elevated"
                >
                  Try again
                </button>
                <button
                  onClick={() => setOnboardingOpen(true)}
                  className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
                >
                  Open setup guide
                </button>
              </div>
            </div>
          </div>
        ) : messages.length === 0 && !activeId ? (
          <EmptyState
            onPrompt={handleSend}
            disabled={!!offline}
            personaId={persona}
            personaLabel={personas.find((p) => p.id === persona)?.label ?? null}
          />
        ) : (
          <MessageList
            messages={messages}
            streaming={streaming}
            onEdit={handleEdit}
            onRegenerate={handleRegenerate}
          />
        )}

        {error && (
          <div className="mx-auto w-full max-w-3xl px-4">
            <p className="rounded-lg border border-accent/40 bg-elevated px-3 py-2 text-sm text-accent">
              {error}
            </p>
          </div>
        )}

        {pendingApproval && (
          <ApprovalPrompt
            pending={pendingApproval}
            onApprove={() => approve(true)}
            onDeny={() => approve(false)}
          />
        )}

        {!loadError && (
          <div className="pt-2">
            <PersonaTabs
              personas={personas}
              active={persona}
              onChange={choosePersona}
              onManage={() => setPersonasOpen(true)}
            />
          </div>
        )}

        {!loadError && (
          <Toolbar
            useRag={useRag}
            availableDocs={availableDocs}
            onToggleRag={() => setUseRag((v) => !v)}
            speakReplies={speakReplies}
            onToggleSpeak={() => {
              const next = !speakReplies;
              setSpeakReplies(next);
              if (!next) stopSpeaking();
            }}
            onManageDocs={() => setDocsOpen(true)}
            onManageMemory={() => setMemoryOpen(true)}
            onWebcam={() => setWebcamOpen(true)}
            onImage={() => setImageOpen(true)}
          />
        )}

        {!loadError && (
          <Composer
            onSend={handleSend}
            onStop={stop}
            onAttachFiles={handleAttachFiles}
            streaming={streaming}
            disabled={!!offline}
          />
        )}
      </main>

      <DocumentsPanel
        open={docsOpen}
        onClose={() => setDocsOpen(false)}
        onChange={refreshHealth}
        conversationId={activeId}
        ensureConversation={ensureConversation}
      />

      <MemoryPanel
        open={memoryOpen}
        onClose={() => setMemoryOpen(false)}
        onChange={refreshHealth}
      />

      <SettingsPanel
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        hardware={health?.hardware ?? null}
        universalMemory={universalMemory}
        onUniversalMemoryChange={changeUniversalMemory}
        onChange={() => {
          refreshModels();
          refreshHealth();
        }}
      />

      <WebcamPanel
        open={webcamOpen}
        onClose={() => setWebcamOpen(false)}
        onCapture={(img, p) => handleSend(p, [img])}
        streaming={streaming}
      />

      <ImagePanel open={imageOpen} onClose={() => setImageOpen(false)} />

      <PersonasPanel
        open={personasOpen}
        onClose={() => setPersonasOpen(false)}
        personas={personas}
        onChange={refreshPersonas}
      />

      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        commands={commands}
      />

      <Onboarding open={onboardingOpen} onClose={closeOnboarding} />
    </div>
  );
}

function timeGreeting(hour: number): string {
  if (hour < 5) return "Working late?";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

// Welcome / zero-state: a warm, time-aware greeting and persona-aware starters.
function EmptyState({
  onPrompt,
  disabled,
  personaId,
  personaLabel,
}: {
  onPrompt: (text: string) => void;
  disabled: boolean;
  personaId: string | null;
  personaLabel: string | null;
}) {
  const greeting = timeGreeting(new Date().getHours());
  const starters = startersFor(personaId);
  const dot = personaColor(personaId);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4">
      <div className="mb-5 animate-rise">
        <Logo size={52} />
      </div>
      <h1 className="mb-1.5 animate-rise text-center text-[1.7rem] font-semibold tracking-tight text-content">
        {greeting}. How can I help?
      </h1>
      <p className="mb-9 animate-rise text-sm text-muted">
        {personaLabel
          ? `${personaLabel} mode — grounded, local, and private.`
          : "A fully local assistant — your conversations stay on your machine."}
      </p>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {starters.map((text, i) => (
          <button
            key={text}
            disabled={disabled}
            onClick={() => onPrompt(text)}
            style={{ animationDelay: `${i * 60}ms` }}
            className="group flex animate-rise items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-left text-sm text-content shadow-sm transition-all hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md disabled:opacity-50"
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: dot }}
            />
            {text}
          </button>
        ))}
      </div>
      <p className="mt-7 animate-rise text-[11px] text-muted/70">
        Press{" "}
        <kbd className="rounded border border-border bg-elevated px-1 py-0.5 text-[10px]">
          ⌘K
        </kbd>{" "}
        for commands
      </p>
    </div>
  );
}
