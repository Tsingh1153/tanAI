"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Brain,
  Camera,
  Code2,
  FolderOpen,
  GraduationCap,
  Globe,
  ImageIcon,
  Lightbulb,
  ListChecks,
  PenLine,
  Settings2,
  Volume2,
  Wrench,
} from "lucide-react";
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
import { useChat } from "@/lib/useChat";
import { api } from "@/lib/api";
import type { Conversation, Health, ModelInfo } from "@/lib/types";

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
  const [useMemory, setUseMemory] = useState(true);
  const [useAgent, setUseAgent] = useState(false);
  const [useWeb, setUseWeb] = useState(false);
  const [webcamOpen, setWebcamOpen] = useState(false);
  const [imageOpen, setImageOpen] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(false);
  const prevStreamingRef = useRef(false);

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
      useMemory,
      useWeb,
      agent: useAgent,
    }),
    [model, provider, useRag, availableDocs, useMemory, useWeb, useAgent],
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

  // Keep the model list current: repopulates if Ollama starts after the app,
  // or once a newly downloaded model finishes.
  useEffect(() => {
    const id = setInterval(refreshModels, 15000);
    return () => clearInterval(id);
  }, [refreshModels]);

  // Initial load: health, models, conversation list.
  useEffect(() => {
    (async () => {
      try {
        const h = await api.health();
        setHealth(h);
        setModel(h.default_model);
      } catch {
        setLoadError(
          "Cannot reach the backend at " +
            (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000") +
            ". Is it running?",
        );
        return;
      }
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
      const list = await refreshConversations();
      if (list.length > 0) setActiveId(list[0].id);
    })();
  }, [refreshConversations]);

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
        useMemory,
        useWeb,
        agent: useAgent,
        images: images.length ? images : undefined,
      });
      // Refresh titles/order shortly after the turn begins.
      setTimeout(() => refreshConversations(), 400);
    },
    [
      activeId,
      model,
      provider,
      useRag,
      availableDocs,
      useMemory,
      useWeb,
      useAgent,
      send,
      refreshConversations,
    ],
  );

  // Keyboard shortcuts: ⌘/Ctrl+K new chat, Esc stops generation.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        handleNew();
      } else if (e.key === "Escape" && streaming) {
        stop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handleNew, streaming, stop]);

  const offline = health && !health.provider_online;

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={setActiveId}
        onNew={handleNew}
        onDelete={handleDelete}
      />

      <main className="flex h-full flex-1 flex-col">
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
                Backend unavailable
              </h2>
              <p className="text-sm text-muted">{loadError}</p>
              <p className="mt-4 text-xs text-muted">
                Start it with{" "}
                <code className="rounded bg-elevated px-1.5 py-0.5">
                  ./scripts/start.sh
                </code>{" "}
                or see the README.
              </p>
            </div>
          </div>
        ) : messages.length === 0 && !activeId ? (
          <EmptyState onPrompt={handleSend} disabled={!!offline} />
        ) : (
          <MessageList
            messages={messages}
            streaming={streaming}
            onEdit={(id, content) => editResend(id, content, chatOptions())}
            onRegenerate={() => regenerate(chatOptions())}
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
          <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-2 px-4 pt-1">
            <Chip
              active={useRag && availableDocs > 0}
              disabled={availableDocs === 0}
              onClick={() => setUseRag((v) => !v)}
              icon={<BookOpen size={14} />}
              label="Documents"
              title={
                availableDocs === 0
                  ? "Upload documents to enable"
                  : "Answer from this chat's documents"
              }
            />
            <Chip
              onClick={() => setDocsOpen(true)}
              icon={<FolderOpen size={14} />}
              label={availableDocs > 0 ? String(availableDocs) : undefined}
              title="Manage this chat's documents"
            />
            <span className="mx-0.5 h-4 w-px bg-border" />
            <Chip
              active={useMemory}
              onClick={() => setUseMemory((v) => !v)}
              icon={<Brain size={14} />}
              label="Memory"
              title={useMemory ? "Memory on" : "Memory off"}
            />
            <Chip
              onClick={() => setMemoryOpen(true)}
              icon={<ListChecks size={14} />}
              title="Manage saved memories"
            />
            <span className="mx-0.5 h-4 w-px bg-border" />
            <Chip
              active={useWeb}
              onClick={() => setUseWeb((v) => !v)}
              icon={<Globe size={14} />}
              label="Web"
              title={
                useWeb
                  ? "Web search on — answers use current info"
                  : "Search the web for current info"
              }
            />
            <Chip
              active={useAgent}
              onClick={() => setUseAgent((v) => !v)}
              icon={<Wrench size={14} />}
              label="Agent"
              title={useAgent ? "Agent on — can use tools" : "Agent off"}
            />
            <Chip
              onClick={() => setWebcamOpen(true)}
              icon={<Camera size={14} />}
              label="Webcam"
              title="Live webcam analysis"
            />
            <Chip
              onClick={() => setImageOpen(true)}
              icon={<ImageIcon size={14} />}
              label="Image"
              title="Generate an image"
            />
            <Chip
              active={speakReplies}
              onClick={() => {
                const next = !speakReplies;
                setSpeakReplies(next);
                if (!next) stopSpeaking();
              }}
              icon={<Volume2 size={14} />}
              label="Speak"
              title="Read replies aloud"
            />
          </div>
        )}

        {!loadError && (
          <Composer
            onSend={handleSend}
            onStop={stop}
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
    </div>
  );
}

// Compact toolbar chip used above the composer.
function Chip({
  icon,
  label,
  onClick,
  active,
  disabled,
  title,
}: {
  icon: React.ReactNode;
  label?: string;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-40",
        active
          ? "border-accent bg-accent text-accent-fg"
          : "border-border bg-surface text-content hover:bg-elevated",
      )}
    >
      {icon}
      {label && <span>{label}</span>}
    </button>
  );
}

// Welcome / zero-state: a warm, time-aware greeting and starter cards.
function EmptyState({
  onPrompt,
  disabled,
}: {
  onPrompt: (text: string) => void;
  disabled: boolean;
}) {
  const hour = new Date().getHours();
  const greeting =
    hour < 5
      ? "Working late?"
      : hour < 12
        ? "Good morning"
        : hour < 18
          ? "Good afternoon"
          : "Good evening";

  const starters = [
    { icon: Lightbulb, text: "Explain quantum entanglement simply" },
    { icon: Code2, text: "Write a Python function to debounce calls" },
    { icon: PenLine, text: "Draft a friendly out-of-office email" },
    { icon: GraduationCap, text: "Summarize the causes of World War I" },
  ];

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4">
      <div className="mb-5 animate-rise">
        <Logo size={52} />
      </div>
      <h1 className="mb-1.5 animate-rise text-center text-[1.7rem] font-semibold tracking-tight text-content">
        {greeting}. How can I help?
      </h1>
      <p className="mb-9 animate-rise text-sm text-muted">
        A fully local assistant — your conversations stay on your machine.
      </p>
      <div className="grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {starters.map((s, i) => {
          const Icon = s.icon;
          return (
            <button
              key={s.text}
              disabled={disabled}
              onClick={() => onPrompt(s.text)}
              style={{ animationDelay: `${i * 60}ms` }}
              className="group flex animate-rise items-center gap-3 rounded-xl border border-border bg-surface px-4 py-3 text-left text-sm text-content shadow-sm transition-all hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-md disabled:opacity-50"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
                <Icon size={16} />
              </span>
              {s.text}
            </button>
          );
        })}
      </div>
    </div>
  );
}
