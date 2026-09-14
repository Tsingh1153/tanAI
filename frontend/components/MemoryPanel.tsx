"use client";

import { useCallback, useEffect, useState } from "react";
import { Brain, Pin, PinOff, Plus, Trash2, X } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { MemoryInfo } from "@/lib/types";

// Right-hand drawer for browsing and curating long-term memory: add, pin,
// delete. Pinned memories are always injected; others are recalled by relevance.
export function MemoryPanel({
  open,
  onClose,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  onChange: () => void;
}) {
  const [memories, setMemories] = useState<MemoryInfo[]>([]);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setMemories(await api.listMemories());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const add = useCallback(async () => {
    const content = draft.trim();
    if (!content) return;
    setError(null);
    try {
      await api.createMemory(content);
      setDraft("");
      await refresh();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [draft, refresh, onChange]);

  const togglePin = useCallback(
    async (m: MemoryInfo) => {
      await api.updateMemory(m.id, { pinned: !m.pinned });
      await refresh();
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.deleteMemory(id);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-20 bg-black/30 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <aside
        className={clsx(
          "fixed right-0 top-0 z-30 flex h-full w-96 max-w-[90vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-content">
            <Brain size={16} /> Memory
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        {/* Add */}
        <div className="border-b border-border p-4">
          <div className="flex items-start gap-2">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  add();
                }
              }}
              rows={2}
              placeholder="Teach the assistant something to remember…"
              className="flex-1 resize-none rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
            />
            <button
              onClick={add}
              disabled={!draft.trim()}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
              aria-label="Add memory"
            >
              <Plus size={18} />
            </button>
          </div>
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}
        </div>

        {/* List */}
        <div className="flex-1 overflow-y-auto p-4">
          {memories.length === 0 ? (
            <p className="py-8 text-center text-sm text-muted">
              No memories yet. The assistant learns as you chat, or add facts
              manually above.
            </p>
          ) : (
            <ul className="space-y-2">
              {memories.map((m) => (
                <li
                  key={m.id}
                  className="group flex items-start gap-2 rounded-lg border border-border bg-surface px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-content">{m.content}</p>
                    <div className="mt-1 flex items-center gap-2 text-xs text-muted">
                      <span className="rounded bg-elevated px-1.5 py-0.5">
                        {m.kind}
                      </span>
                      <span>importance {(m.importance * 100).toFixed(0)}%</span>
                      {m.use_count > 0 && <span>· used {m.use_count}×</span>}
                      {m.pinned && (
                        <span className="text-accent">· pinned</span>
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={() => togglePin(m)}
                      className="text-muted hover:text-accent"
                      aria-label={m.pinned ? "Unpin" : "Pin"}
                      title={m.pinned ? "Unpin" : "Pin (always recall)"}
                    >
                      {m.pinned ? <PinOff size={14} /> : <Pin size={14} />}
                    </button>
                    <button
                      onClick={() => remove(m.id)}
                      className="text-muted hover:text-accent"
                      aria-label="Delete memory"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>
    </>
  );
}
