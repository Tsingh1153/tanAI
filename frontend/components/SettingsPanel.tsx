"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Cpu,
  Download,
  Loader2,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type {
  MCPServerInfo,
  ModelInfo,
  PluginInfo,
  ProviderInfo,
} from "@/lib/types";

// Curated one-click pulls. Vision models power image/webcam analysis.
const SUGGESTED_MODELS: { name: string; note: string }[] = [
  { name: "qwen2.5:7b", note: "strong text (default)" },
  { name: "llama3.1:8b", note: "strong text" },
  { name: "llama3.2-vision", note: "vision" },
  { name: "llava", note: "vision" },
  { name: "moondream", note: "small vision" },
  { name: "nomic-embed-text", note: "embeddings (RAG)" },
];

interface PullState {
  name: string;
  status: string;
  pct: number;
}

// One-click fills for common local OpenAI-compatible servers.
const PROVIDER_PRESETS = [
  {
    label: "Apple Foundation Models",
    base_url: "http://localhost:1976/v1",
    hint: "macOS 27+ on-device LLM — started automatically by the launcher (fm serve)",
  },
  {
    label: "LM Studio",
    base_url: "http://localhost:1234/v1",
    hint: "LM Studio's local server",
  },
  {
    label: "vLLM",
    base_url: "http://localhost:8001/v1",
    hint: "A local vLLM server",
  },
];

const VISION_HINTS = [
  "vision",
  "llava",
  "-vl",
  "moondream",
  "bakllava",
  "minicpm-v",
];

function isVision(name: string): boolean {
  const n = name.toLowerCase();
  return VISION_HINTS.some((h) => n.includes(h));
}

function formatSize(bytes?: number | null): string {
  if (!bytes) return "";
  const gb = bytes / 1e9;
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  return `${Math.round(bytes / 1e6)} MB`;
}

// Settings drawer: shows detected hardware and manages model providers. New
// OpenAI-compatible endpoints (LM Studio, vLLM, llama.cpp server, or a cloud
// API) can be added here and take effect immediately — no restart.
export function SettingsPanel({
  open,
  onClose,
  hardware,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  hardware: string | null;
  onChange: () => void;
}) {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [mcpServers, setMcpServers] = useState<MCPServerInfo[]>([]);
  const [plugins, setPlugins] = useState<PluginInfo | null>(null);
  const [mcpName, setMcpName] = useState("");
  const [mcpCommand, setMcpCommand] = useState("");
  const [mcpArgs, setMcpArgs] = useState("");
  const [mcpBusy, setMcpBusy] = useState(false);
  const [mcpError, setMcpError] = useState<string | null>(null);
  const [fm, setFm] = useState<{ available: boolean; output: string } | null>(
    null,
  );
  const [fmBusy, setFmBusy] = useState(false);

  const refreshFmQuota = useCallback(async () => {
    setFmBusy(true);
    try {
      setFm(await api.fmQuota());
    } catch {
      setFm({ available: false, output: "" });
    } finally {
      setFmBusy(false);
    }
  }, []);
  const [label, setLabel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [customModel, setCustomModel] = useState("");
  const [pull, setPull] = useState<PullState | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const refresh = useCallback(async () => {
    try {
      setProviders(await api.listProviders());
    } catch (e) {
      setError((e as Error).message);
    }
    try {
      setModels(await api.listModels());
    } catch {
      /* provider offline */
    }
    try {
      setMcpServers(await api.listMcpServers());
    } catch {
      /* ignore */
    }
    try {
      setPlugins(await api.listPlugins());
    } catch {
      /* ignore */
    }
  }, []);

  const addMcp = useCallback(async () => {
    if (!mcpName.trim() || !mcpCommand.trim()) return;
    setMcpBusy(true);
    setMcpError(null);
    try {
      const server = await api.addMcpServer({
        name: mcpName.trim(),
        command: mcpCommand.trim(),
        args: mcpArgs.trim() ? mcpArgs.trim().split(/\s+/) : [],
      });
      if (!server.connected) {
        setMcpError(server.error ?? "Could not connect to that server.");
      }
      setMcpName("");
      setMcpCommand("");
      setMcpArgs("");
      await refresh();
      onChange();
    } catch (e) {
      setMcpError((e as Error).message);
    } finally {
      setMcpBusy(false);
    }
  }, [mcpName, mcpCommand, mcpArgs, refresh, onChange]);

  const removeMcp = useCallback(
    async (name: string) => {
      await api.deleteMcpServer(name);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  useEffect(() => {
    if (open) {
      refresh();
      refreshFmQuota();
    }
  }, [open, refresh, refreshFmQuota]);

  // Close any in-flight pull stream on unmount.
  useEffect(() => () => esRef.current?.close(), []);

  const startPull = useCallback(
    (name: string) => {
      if (!name.trim() || pull) return;
      setError(null);
      setPull({ name, status: "starting", pct: 0 });
      const es = new EventSource(api.pullModelUrl(name.trim()));
      esRef.current = es;
      es.onmessage = (e) => {
        let d: {
          status?: string;
          error?: string;
          total?: number;
          completed?: number;
        };
        try {
          d = JSON.parse(e.data);
        } catch {
          return;
        }
        if (d.status === "done") {
          es.close();
          setPull(null);
          refresh();
          onChange();
          return;
        }
        if (d.status === "error") {
          es.close();
          setPull({ name, status: `error: ${d.error ?? "failed"}`, pct: 0 });
          return;
        }
        const pct =
          d.total && d.completed
            ? Math.round((d.completed / d.total) * 100)
            : 0;
        setPull({ name, status: d.status ?? "downloading", pct });
      };
      es.onerror = () => {
        es.close();
        setPull((p) => (p ? { ...p, status: "connection lost" } : null));
        setTimeout(() => setPull(null), 2500);
      };
    },
    [pull, refresh, onChange],
  );

  const removeModel = useCallback(
    async (name: string) => {
      await api.deleteModel(name);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  // Local (Ollama) models, de-duplicated by name, keeping size metadata.
  const seen = new Set<string>();
  const localModels: ModelInfo[] = [];
  for (const m of models) {
    if (m.provider === "ollama" && !seen.has(m.name)) {
      seen.add(m.name);
      localModels.push(m);
    }
  }
  const localNames = localModels.map((m) => m.name);

  const add = useCallback(async () => {
    if (!label.trim() || !baseUrl.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.addProvider({
        label: label.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || undefined,
      });
      setLabel("");
      setBaseUrl("");
      setApiKey("");
      await refresh();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [label, baseUrl, apiKey, refresh, onChange]);

  const remove = useCallback(
    async (name: string) => {
      await api.deleteProvider(name);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-20 bg-black/40 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <aside
        className={clsx(
          "fixed right-0 top-0 z-30 flex h-full w-[26rem] max-w-[92vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-content">Settings</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          {/* Hardware */}
          <div className="mb-6 flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2.5">
            <Cpu size={16} className="text-accent" />
            <div>
              <p className="text-xs text-muted">Detected hardware</p>
              <p className="text-sm text-content">{hardware ?? "—"}</p>
            </div>
          </div>

          {/* Apple Foundation Models quota (macOS 27+) */}
          {fm?.available && (
            <div className="mb-6">
              <div className="mb-2 flex items-center gap-2">
                <Activity size={14} className="text-accent" />
                <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Apple Foundation Models
                </h3>
                <button
                  onClick={refreshFmQuota}
                  className="ml-auto text-muted hover:text-content"
                  aria-label="Refresh quota"
                  title="Refresh"
                >
                  {fmBusy ? (
                    <Loader2 size={13} className="animate-spin" />
                  ) : (
                    <RefreshCw size={13} />
                  )}
                </button>
              </div>
              <pre className="overflow-x-auto rounded-lg border border-border bg-elevated p-2.5 text-[11px] leading-relaxed text-content">
                {fm.output || "No quota information reported."}
              </pre>
              <p className="mt-1 text-[11px] text-muted">
                Private Cloud Compute (pcc) usage. On-device (system) is
                unlimited.
              </p>
            </div>
          )}

          {/* Models (download / remove via Ollama) */}
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Local models
          </h3>
          {pull && (
            <div className="mb-3 rounded-lg border border-border bg-surface px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-content">
                <Loader2 size={14} className="animate-spin text-accent" />
                <span className="truncate">{pull.name}</span>
                <span className="ml-auto text-xs text-muted">
                  {pull.pct > 0 ? `${pull.pct}%` : pull.status}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-elevated">
                <div
                  className="h-full bg-accent transition-all"
                  style={{ width: `${pull.pct}%` }}
                />
              </div>
              <p className="mt-1 truncate text-xs text-muted">{pull.status}</p>
            </div>
          )}

          <p className="mb-2 text-xs text-muted">
            {localModels.length > 0
              ? `${localModels.length} installed on this computer:`
              : "No models installed yet — download one below."}
          </p>
          {localModels.length > 0 && (
            <ul className="mb-3 space-y-1.5">
              {localModels.map((m) => (
                <li
                  key={m.name}
                  className="group flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-1.5 text-sm"
                >
                  <span className="truncate text-content">{m.name}</span>
                  {isVision(m.name) && (
                    <span className="shrink-0 rounded bg-elevated px-1.5 py-0.5 text-[10px] font-medium text-accent">
                      vision
                    </span>
                  )}
                  <span className="ml-auto shrink-0 text-xs text-muted">
                    {formatSize(m.size)}
                  </span>
                  <button
                    onClick={() => removeModel(m.name)}
                    className="shrink-0 text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
                    aria-label="Delete model"
                  >
                    <Trash2 size={14} />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <p className="mb-2 text-xs text-muted">Download a model:</p>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {SUGGESTED_MODELS.filter((m) => !localNames.includes(m.name)).map(
              (m) => (
                <button
                  key={m.name}
                  onClick={() => startPull(m.name)}
                  disabled={!!pull}
                  title={m.note}
                  className="flex items-center gap-1 rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-content transition-colors hover:bg-elevated disabled:opacity-40"
                >
                  <Download size={12} /> {m.name}
                </button>
              ),
            )}
          </div>
          <div className="mb-6 flex items-center gap-2">
            <input
              value={customModel}
              onChange={(e) => setCustomModel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  startPull(customModel);
                  setCustomModel("");
                }
              }}
              placeholder="Any Ollama model tag, e.g. gemma2:9b"
              className="flex-1 rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <button
              onClick={() => {
                startPull(customModel);
                setCustomModel("");
              }}
              disabled={!customModel.trim() || !!pull}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              aria-label="Download model"
            >
              <Download size={16} />
            </button>
          </div>

          {/* Providers list */}
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Model providers
          </h3>
          <ul className="mb-5 space-y-2">
            {providers.map((p) => (
              <li
                key={p.name}
                className="group flex items-center gap-2 rounded-lg border border-border bg-surface px-3 py-2"
              >
                <Server size={15} className="shrink-0 text-muted" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-content">{p.label}</p>
                  <p className="truncate text-xs text-muted">
                    {p.base_url ?? "local"}
                  </p>
                </div>
                <span
                  className={clsx(
                    "h-2 w-2 shrink-0 rounded-full",
                    p.online ? "bg-green-500" : "bg-muted",
                  )}
                  title={p.online ? "Online" : "Offline"}
                />
                {p.removable && (
                  <button
                    onClick={() => remove(p.name)}
                    className="shrink-0 text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
                    aria-label="Remove provider"
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </li>
            ))}
          </ul>

          {/* Add provider */}
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
            Add an OpenAI-compatible provider
          </h3>
          <div className="mb-2 flex flex-wrap gap-1.5">
            {PROVIDER_PRESETS.map((p) => (
              <button
                key={p.label}
                onClick={() => {
                  setLabel(p.label);
                  setBaseUrl(p.base_url);
                }}
                title={p.hint}
                className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-content transition-colors hover:bg-elevated"
              >
                {p.label}
              </button>
            ))}
          </div>
          <div className="space-y-2">
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Name (e.g. LM Studio, OpenRouter)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <input
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
              placeholder="Base URL (e.g. http://localhost:1234/v1)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <input
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              type="password"
              placeholder="API key (optional, for cloud services)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <button
              onClick={add}
              disabled={busy || !label.trim() || !baseUrl.trim()}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Plus size={16} />
              {busy ? "Connecting…" : "Add provider"}
            </button>
            {error && <p className="text-xs text-accent">{error}</p>}
            <p className="pt-1 text-xs text-muted">
              Works with LM Studio, vLLM, llama.cpp server, and cloud APIs
              (OpenAI, Groq, OpenRouter). The base URL should end in{" "}
              <code className="rounded bg-elevated px-1">/v1</code>.
            </p>
          </div>

          {/* Extensions: MCP servers + plugins */}
          <h3 className="mb-2 mt-8 text-xs font-semibold uppercase tracking-wide text-muted">
            MCP servers
          </h3>
          {mcpServers.length > 0 && (
            <ul className="mb-3 space-y-2">
              {mcpServers.map((s) => (
                <li
                  key={s.name}
                  className="group rounded-lg border border-border bg-surface px-3 py-2"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={clsx(
                        "h-2 w-2 shrink-0 rounded-full",
                        s.connected ? "bg-green-500" : "bg-accent",
                      )}
                      title={s.connected ? "Connected" : "Disconnected"}
                    />
                    <span className="truncate text-sm text-content">
                      {s.name}
                    </span>
                    <span className="ml-auto shrink-0 text-xs text-muted">
                      {s.connected ? `${s.tools.length} tools` : "offline"}
                    </span>
                    <button
                      onClick={() => removeMcp(s.name)}
                      className="shrink-0 text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
                      aria-label="Remove server"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                  {s.error && (
                    <p className="mt-1 truncate text-xs text-accent">
                      {s.error}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
          <div className="space-y-2">
            <input
              value={mcpName}
              onChange={(e) => setMcpName(e.target.value)}
              placeholder="Name (e.g. filesystem)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <input
              value={mcpCommand}
              onChange={(e) => setMcpCommand(e.target.value)}
              placeholder="Command (e.g. npx)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <input
              value={mcpArgs}
              onChange={(e) => setMcpArgs(e.target.value)}
              placeholder="Args (e.g. -y @modelcontextprotocol/server-filesystem ~/Desktop)"
              className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <button
              onClick={addMcp}
              disabled={mcpBusy || !mcpName.trim() || !mcpCommand.trim()}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Plus size={16} />
              {mcpBusy ? "Connecting…" : "Add MCP server"}
            </button>
            {mcpError && <p className="text-xs text-accent">{mcpError}</p>}
            <p className="pt-1 text-xs text-muted">
              Connect Model Context Protocol servers to add third-party tools.
              Requires the server&apos;s runtime (e.g. Node for{" "}
              <code className="rounded bg-elevated px-1">npx</code> servers).
            </p>
          </div>

          {/* Plugins */}
          <h3 className="mb-2 mt-8 text-xs font-semibold uppercase tracking-wide text-muted">
            Python plugins
          </h3>
          <p className="mb-2 text-xs text-muted">
            {plugins && plugins.loaded.length > 0
              ? `${plugins.loaded.length} loaded · ${plugins.tools.length} tools`
              : "No plugins loaded."}{" "}
            Drop <code className="rounded bg-elevated px-1">.py</code> files in{" "}
            <code className="rounded bg-elevated px-1">backend/plugins/</code>.
          </p>
          {plugins && plugins.tools.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {plugins.tools.map((t) => (
                <span
                  key={t}
                  className="rounded-full border border-border bg-surface px-2.5 py-1 text-xs text-content"
                >
                  {t}
                </span>
              ))}
            </div>
          )}
          {plugins &&
            Object.entries(plugins.errors).map(([name, err]) => (
              <p key={name} className="text-xs text-accent">
                {name}: {err}
              </p>
            ))}

          {/* Image generation */}
          <h3 className="mb-2 mt-8 text-xs font-semibold uppercase tracking-wide text-muted">
            Image generation
          </h3>
          <p className="text-xs leading-relaxed text-muted">
            The <span className="font-medium text-content">Image</span> button
            needs an external backend. Point it at a local Stable Diffusion
            server (AUTOMATIC1111 run with{" "}
            <code className="rounded bg-elevated px-1">--api</code>, or SD.Next
            / Forge) or an OpenAI-compatible images API, via env vars in{" "}
            <code className="rounded bg-elevated px-1">backend/.env</code>:
          </p>
          <pre className="mt-2 overflow-x-auto rounded-lg border border-border bg-elevated p-2.5 text-[11px] text-muted">
            {`LOCALMIND_IMAGE_BACKEND=automatic1111
LOCALMIND_IMAGE_SERVER_URL=http://localhost:7860

# …or a hosted images API:
# LOCALMIND_IMAGE_BACKEND=openai
# LOCALMIND_IMAGE_SERVER_URL=https://api.openai.com/v1
# LOCALMIND_IMAGE_API_KEY=sk-...`}
          </pre>
        </div>
      </aside>
    </>
  );
}
