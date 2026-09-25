"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Brain,
  Check,
  ChevronDown,
  Copy,
  Download,
  Globe,
  Loader2,
  MessageSquare,
  RefreshCw,
  Shuffle,
  Sparkles,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { Logo } from "./Logo";

interface Status {
  backend: boolean; // is the local engine reachable at all
  ollama: boolean; // is Ollama running
  chatModel: boolean; // is a chat model installed
  embedModel: boolean; // is the document-search model installed
}

const CHAT_MODEL = "qwen2.5:7b";
const EMBED_MODEL = "nomic-embed-text";
const TOTAL_STEPS = 4;

// First-run welcome + guided setup, written for someone who has never used a
// terminal. It detects what's missing live, installs the models for you with a
// progress bar, points you to the one thing you must download yourself (Ollama),
// and explains what to do when something looks stuck. Reopenable any time.
export function Onboarding({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [status, setStatus] = useState<Status | null>(null);
  const [checking, setChecking] = useState(false);

  const check = useCallback(async () => {
    setChecking(true);
    try {
      const [health, models] = await Promise.all([
        api.health(),
        api.listModels().catch(() => []),
      ]);
      setStatus({
        backend: true,
        ollama: health.provider_online,
        chatModel: models.some((m) => !m.name.toLowerCase().includes("embed")),
        embedModel: health.embedding_online,
      });
    } catch {
      // Health threw → the local engine isn't up yet (still starting, or a
      // missing prerequisite). Everything downstream is unknown/false.
      setStatus({
        backend: false,
        ollama: false,
        chatModel: false,
        embedModel: false,
      });
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setStep(0);
      check();
    }
  }, [open, check]);

  // While on the setup step, re-check often so ticks turn green on their own as
  // things come online (Ollama opening, a download finishing).
  useEffect(() => {
    if (!open || step !== 1) return;
    const id = setInterval(check, 3000);
    return () => clearInterval(id);
  }, [open, step, check]);

  if (!open) return null;

  const allReady =
    !!status &&
    status.backend &&
    status.ollama &&
    status.chatModel &&
    status.embedModel;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[88vh] w-full max-w-2xl flex-col overflow-hidden rounded-3xl border border-border bg-canvas shadow-2xl">
        <div className="flex-1 overflow-y-auto p-8">
          {step === 0 && <WelcomeStep />}
          {step === 1 && (
            <SetupStep status={status} checking={checking} onRecheck={check} />
          )}
          {step === 2 && <TourStep />}
          {step === 3 && <DoneStep allReady={allReady} />}
        </div>

        {/* Footer: progress dots + navigation */}
        <div className="flex items-center justify-between border-t border-border px-8 py-4">
          <div className="flex gap-1.5">
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <span
                key={i}
                className={clsx(
                  "h-1.5 rounded-full transition-all",
                  i === step ? "w-6 bg-accent" : "w-1.5 bg-border",
                )}
              />
            ))}
          </div>
          <div className="flex items-center gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep((s) => s - 1)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-muted transition-colors hover:bg-elevated hover:text-content"
              >
                <ArrowLeft size={15} /> Back
              </button>
            )}
            {step < TOTAL_STEPS - 1 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
              >
                Next <ArrowRight size={15} />
              </button>
            ) : (
              <button
                onClick={onClose}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
              >
                Start using tanAI
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function WelcomeStep() {
  return (
    <div className="flex flex-col items-center text-center animate-fade-up">
      <div className="mb-5 animate-float">
        <Logo size={56} />
      </div>
      <h1 className="brand-gradient text-3xl font-semibold tracking-tight">
        Welcome to tanAI
      </h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
        A private AI assistant that runs entirely on your own computer — your
        chats, documents, and memory never leave this machine. There's a little
        one-time setup, and the next screen does most of it for you.
      </p>
      <div className="mt-6 grid w-full grid-cols-3 gap-3">
        <MiniCard icon={<Sparkles size={16} />} label="Fully private" />
        <MiniCard icon={<BookOpen size={16} />} label="Chat with your docs" />
        <MiniCard icon={<Brain size={16} />} label="Remembers you" />
      </div>
    </div>
  );
}

function SetupStep({
  status,
  checking,
  onRecheck,
}: {
  status: Status | null;
  checking: boolean;
  onRecheck: () => void;
}) {
  // The engine itself isn't up yet: nothing else can be checked, so show a
  // focused "starting / needs one thing" panel instead of a wall of red.
  if (status && !status.backend) {
    return <BackendDownStep checking={checking} onRecheck={onRecheck} />;
  }

  const ollamaOk = !!status?.ollama;

  return (
    <div className="animate-fade-up">
      <h2 className="text-xl font-semibold text-content">
        Let's finish setting up
      </h2>
      <p className="mt-1.5 text-sm text-muted">
        tanAI runs its AI models through a free app called{" "}
        <strong>Ollama</strong>. You install Ollama once; tanAI downloads the
        models for you. These checks turn green on their own as each piece is
        ready.
      </p>

      <div className="mt-5 space-y-3">
        <OllamaRow ok={ollamaOk} />
        <ModelRow
          ok={status?.chatModel}
          title="Download the main AI model"
          detail="This is the brain that answers you. About 4.7 GB — a one-time download."
          model={CHAT_MODEL}
          canInstall={ollamaOk}
          onDone={onRecheck}
        />
        <ModelRow
          ok={status?.embedModel}
          title="Download the document-search model"
          detail="Lets tanAI read and answer from your files. Small — about 275 MB."
          model={EMBED_MODEL}
          canInstall={ollamaOk}
          onDone={onRecheck}
        />
      </div>

      <div className="mt-4 flex items-center gap-3">
        <button
          onClick={onRecheck}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:bg-elevated hover:text-content"
        >
          {checking ? (
            <Loader2 size={13} className="animate-spin" />
          ) : (
            <RefreshCw size={13} />
          )}
          Re-check
        </button>
      </div>

      <Troubleshooting />
    </div>
  );
}

function BackendDownStep({
  checking,
  onRecheck,
}: {
  checking: boolean;
  onRecheck: () => void;
}) {
  return (
    <div className="animate-fade-up">
      <h2 className="text-xl font-semibold text-content">tanAI is starting…</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-muted">
        The first launch sets things up and can take a minute or two. This
        screen will move on by itself once the engine is ready.
      </p>

      <div className="mt-5 flex items-center gap-3 rounded-xl border border-border bg-surface p-4">
        <Loader2 size={20} className="animate-spin text-accent" />
        <p className="text-sm text-content">Waiting for the local engine…</p>
      </div>

      <div className="mt-5 rounded-xl border border-border bg-surface p-4">
        <p className="text-sm font-medium text-content">
          Still waiting after a couple of minutes?
        </p>
        <p className="mt-1.5 text-xs leading-relaxed text-muted">
          tanAI needs a free tool called <strong>Python</strong> (version 3.10
          or newer) to run. Most Macs have it, but if this screen never turns
          green, install Python, then quit and reopen tanAI.
        </p>
        <div className="mt-3">
          <LinkButton
            href="https://www.python.org/downloads/"
            label="Download Python"
          />
        </div>
      </div>

      <button
        onClick={onRecheck}
        className="mt-5 flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted transition-colors hover:bg-elevated hover:text-content"
      >
        {checking ? (
          <Loader2 size={13} className="animate-spin" />
        ) : (
          <RefreshCw size={13} />
        )}
        Check again
      </button>
    </div>
  );
}

function OllamaRow({ ok }: { ok: boolean }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-3.5">
      <div className="flex items-center gap-2.5">
        <StatusDot ok={ok} />
        <p className="text-sm font-medium text-content">
          {ok ? "Ollama is installed and running" : "Install Ollama"}
        </p>
      </div>
      {!ok && (
        <div className="mt-2.5 pl-7">
          <p className="text-xs leading-relaxed text-muted">
            Download Ollama, open the downloaded file, and drag it to your
            Applications folder. Open it once — a small llama icon appears in
            your menu bar and it keeps running quietly. This box turns green
            automatically.
          </p>
          <div className="mt-2.5 flex items-center gap-2">
            <LinkButton
              href="https://ollama.com/download"
              label="Download Ollama"
            />
          </div>
        </div>
      )}
    </div>
  );
}

// A model row that installs the model in-app (no terminal) with a live progress
// bar, driven by the backend's pull SSE stream.
function ModelRow({
  ok,
  title,
  detail,
  model,
  canInstall,
  onDone,
}: {
  ok: boolean | undefined;
  title: string;
  detail: string;
  model: string;
  canInstall: boolean;
  onDone: () => void;
}) {
  const [pulling, setPulling] = useState(false);
  const [pct, setPct] = useState(0);
  const [phase, setPhase] = useState("");
  const [error, setError] = useState("");
  const [showCmd, setShowCmd] = useState(false);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    return () => esRef.current?.close();
  }, []);

  const install = () => {
    setPulling(true);
    setError("");
    setPct(0);
    setPhase("Starting download…");
    const es = new EventSource(api.pullModelUrl(model));
    esRef.current = es;
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as {
          status?: string;
          error?: string;
          total?: number;
          completed?: number;
        };
        if (data.error || data.status === "error") {
          setError(data.error || "Download failed.");
          es.close();
          setPulling(false);
          return;
        }
        if (data.status === "done") {
          setPct(100);
          es.close();
          setPulling(false);
          onDone();
          return;
        }
        if (data.total && data.completed) {
          setPct(
            Math.min(100, Math.round((data.completed / data.total) * 100)),
          );
        }
        if (data.status) setPhase(data.status);
      } catch {
        /* ignore keep-alive / non-JSON lines */
      }
    };
    es.onerror = () => {
      es.close();
      setPulling(false);
      setError((prev) => prev || "Lost connection. Make sure Ollama is open.");
    };
  };

  return (
    <div className="rounded-xl border border-border bg-surface p-3.5">
      <div className="flex items-center gap-2.5">
        <StatusDot ok={ok} />
        <p className="text-sm font-medium text-content">
          {ok ? title.replace(/^Download the/, "Installed:") : title}
        </p>
        {!ok && !pulling && (
          <button
            onClick={install}
            disabled={!canInstall}
            title={
              canInstall ? undefined : "Install Ollama first (the step above)"
            }
            className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <Download size={13} /> Download
          </button>
        )}
      </div>

      {!ok && (
        <div className="mt-2 pl-7">
          <p className="text-xs leading-relaxed text-muted">{detail}</p>

          {pulling && (
            <div className="mt-2.5">
              <div className="h-2 w-full overflow-hidden rounded-full bg-elevated">
                <div
                  className="h-full rounded-full bg-accent transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="mt-1 text-[11px] text-muted">
                {pct}% · {phase}
              </p>
            </div>
          )}

          {error && (
            <p className="mt-2 text-[11px] text-red-400">
              {error} You can also{" "}
              <button
                onClick={() => setShowCmd((v) => !v)}
                className="underline hover:text-content"
              >
                install it manually
              </button>
              .
            </p>
          )}

          {(showCmd || (!canInstall && !pulling)) && (
            <details className="mt-2" open={showCmd}>
              <summary className="cursor-pointer text-[11px] text-muted hover:text-content">
                Prefer the Terminal?
              </summary>
              <CommandLine command={`ollama pull ${model}`} />
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function Troubleshooting() {
  const items = [
    {
      q: "I typed a message and nothing happened",
      a: "The main model is probably still downloading, or Ollama isn't open yet. Check that both boxes above are green.",
    },
    {
      q: "The first reply is slow",
      a: "The model loads into memory on the first message of a session, then speeds up. On a 16 GB Mac, larger models are heavier — the default is chosen to run well.",
    },
    {
      q: 'It says the model is "offline"',
      a: "Open the Ollama app (look for the llama icon in your menu bar). tanAI reconnects automatically.",
    },
    {
      q: "I want to reopen this guide later",
      a: "Press ⌘K any time and choose “Setup & help”.",
    },
  ];
  return (
    <details className="mt-5 rounded-xl border border-border bg-surface p-3.5">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-content">
        <ChevronDown size={15} className="text-muted" />
        Something not working? Common fixes
      </summary>
      <div className="mt-3 space-y-3">
        {items.map((it) => (
          <div key={it.q}>
            <p className="text-xs font-medium text-content">{it.q}</p>
            <p className="mt-0.5 text-xs leading-relaxed text-muted">{it.a}</p>
          </div>
        ))}
      </div>
    </details>
  );
}

function TourStep() {
  const features = [
    {
      icon: <MessageSquare size={18} />,
      title: "Chat",
      body: "Ask anything. Switch models any time from the top-right dropdown.",
    },
    {
      icon: <Sparkles size={18} />,
      title: "Modes",
      body: "Tabs above the box switch tanAI's focus — the finance modes, or your own.",
    },
    {
      icon: <BookOpen size={18} />,
      title: "Documents",
      body: "Attach files and toggle Documents to get answers grounded in them, with citations.",
    },
    {
      icon: <Brain size={18} />,
      title: "Memory",
      body: "tanAI remembers durable facts about you across chats — manage them any time.",
    },
    {
      icon: <Globe size={18} />,
      title: "Web & tools",
      body: "tanAI decides on its own when to search the web or use a tool — no buttons to flip.",
    },
    {
      icon: <Shuffle size={18} />,
      title: "Auto",
      body: "Pick Auto and each message routes to the best model you have installed.",
    },
  ];
  return (
    <div className="animate-fade-up">
      <h2 className="text-xl font-semibold text-content">What you can do</h2>
      <p className="mt-1.5 text-sm text-muted">
        A quick tour. Press <Kbd>⌘K</Kbd> any time for the command palette.
      </p>
      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {features.map((f) => (
          <div
            key={f.title}
            className="flex gap-3 rounded-xl border border-border bg-surface p-3.5"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
              {f.icon}
            </span>
            <div>
              <p className="text-sm font-medium text-content">{f.title}</p>
              <p className="mt-0.5 text-xs leading-relaxed text-muted">
                {f.body}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DoneStep({ allReady }: { allReady: boolean }) {
  return (
    <div className="flex flex-col items-center text-center animate-fade-up">
      <div
        className={clsx(
          "mb-5 flex h-16 w-16 items-center justify-center rounded-full",
          allReady ? "bg-accent-soft text-accent" : "bg-elevated text-muted",
        )}
      >
        <Check size={30} />
      </div>
      <h2 className="text-2xl font-semibold text-content">
        {allReady ? "You're all set" : "Almost there"}
      </h2>
      <p className="mt-2 max-w-md text-sm leading-relaxed text-muted">
        {allReady
          ? "Everything's installed and running. Ask tanAI anything to begin — your first message may take a few seconds while the model warms up."
          : "You can start now, but finish the setup steps whenever you're ready for chat, documents, and memory to work. Reopen this guide any time with ⌘K → “Setup & help”."}
      </p>
    </div>
  );
}

function StatusDot({ ok }: { ok: boolean | undefined }) {
  if (ok) {
    return (
      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent text-accent-fg">
        <Check size={13} />
      </span>
    );
  }
  return (
    <span className="h-5 w-5 shrink-0 rounded-full border-2 border-border" />
  );
}

function LinkButton({ href, label }: { href: string; label: string }) {
  return (
    <button
      onClick={() => window.open(href, "_blank")}
      className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-accent-fg transition-opacity hover:opacity-90"
    >
      <Download size={13} /> {label}
    </button>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(command);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="mt-1.5 flex items-center justify-between gap-2 rounded-lg bg-elevated px-3 py-2 font-mono text-xs text-content">
      <span className="truncate">{command}</span>
      <button
        onClick={copy}
        className="shrink-0 text-muted transition-colors hover:text-accent"
        aria-label="Copy command"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  );
}

function MiniCard({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 rounded-xl border border-border bg-surface p-3 text-center">
      <span className="text-accent">{icon}</span>
      <span className="text-xs text-muted">{label}</span>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-border bg-elevated px-1 py-0.5 text-[10px]">
      {children}
    </kbd>
  );
}
