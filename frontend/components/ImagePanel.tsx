"use client";

import { useCallback, useState } from "react";
import { Download, ImageIcon, Loader2, Sparkles, X } from "lucide-react";
import clsx from "clsx";
import { api, API_BASE } from "@/lib/api";

// Image generation panel: enter a prompt, generate via the configured backend
// (Stable Diffusion / image API), preview and download results.
export function ImagePanel({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [prompt, setPrompt] = useState("");
  const [count, setCount] = useState(1);
  const [busy, setBusy] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(async () => {
    if (!prompt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { images: urls } = await api.generateImages(prompt.trim(), count);
      setImages((prev) => [...urls, ...prev]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, [prompt, count, busy]);

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
          "fixed right-0 top-0 z-30 flex h-full w-[28rem] max-w-[94vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-content">
            <ImageIcon size={16} /> Generate image
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        <div className="border-b border-border p-4">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) generate();
            }}
            rows={3}
            placeholder="Describe the image… (⌘/Ctrl+Enter to generate)"
            className="w-full resize-none rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
          />
          <div className="mt-2 flex items-center gap-2">
            <select
              value={count}
              onChange={(e) => setCount(Number(e.target.value))}
              className="rounded-lg border border-border bg-surface px-2 py-1.5 text-sm text-content outline-none"
            >
              {[1, 2, 3, 4].map((n) => (
                <option key={n} value={n}>
                  {n} image{n > 1 ? "s" : ""}
                </option>
              ))}
            </select>
            <button
              onClick={generate}
              disabled={busy || !prompt.trim()}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-lg bg-gradient-to-br from-accent to-accent-2 px-3 py-2 text-sm font-medium text-white transition-opacity hover:opacity-95 disabled:opacity-40"
            >
              {busy ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <Sparkles size={16} />
              )}
              {busy ? "Generating…" : "Generate"}
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {images.length === 0 ? (
            <p className="py-10 text-center text-sm text-muted">
              Generated images appear here. Requires a Stable Diffusion server or
              image API (see Settings).
            </p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              {images.map((url, i) => {
                const src = `${API_BASE}${url}`;
                return (
                  <a
                    key={i}
                    href={src}
                    download
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group relative overflow-hidden rounded-lg border border-border"
                  >
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={src} alt="generated" className="w-full" />
                    <span className="absolute right-1.5 top-1.5 rounded-md bg-black/50 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100">
                      <Download size={13} />
                    </span>
                  </a>
                );
              })}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
