"use client";

import { useCallback, useEffect, useState } from "react";
import { Sparkles, Pencil, Trash2, X, Plus } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { Persona } from "@/lib/types";

// Drawer for managing custom personas. Built-ins are shown read-only; custom
// personas can be created, edited, and deleted. Each is just a system prompt.
export function PersonasPanel({
  open,
  onClose,
  personas,
  onChange,
}: {
  open: boolean;
  onClose: () => void;
  personas: Persona[];
  onChange: () => void;
}) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);

  const custom = personas.filter((p) => !p.builtin);
  const builtin = personas.filter((p) => p.builtin);

  const reset = useCallback(() => {
    setEditingId(null);
    setLabel("");
    setDescription("");
    setPrompt("");
    setError(null);
  }, []);

  useEffect(() => {
    if (!open) reset();
  }, [open, reset]);

  const startEdit = useCallback((p: Persona) => {
    setEditingId(p.id);
    setLabel(p.label);
    setDescription(p.description);
    setPrompt(p.system_prompt);
    setError(null);
  }, []);

  const save = useCallback(async () => {
    if (!label.trim() || !prompt.trim()) {
      setError("Label and system prompt are required.");
      return;
    }
    setError(null);
    try {
      if (editingId) {
        await api.updatePersona(editingId, {
          label: label.trim(),
          description: description.trim(),
          system_prompt: prompt.trim(),
        });
      } else {
        await api.createPersona({
          label: label.trim(),
          description: description.trim(),
          system_prompt: prompt.trim(),
        });
      }
      reset();
      onChange();
    } catch (e) {
      setError((e as Error).message);
    }
  }, [editingId, label, description, prompt, reset, onChange]);

  const remove = useCallback(
    async (id: string) => {
      try {
        await api.deletePersona(id);
        if (editingId === id) reset();
        onChange();
      } catch (e) {
        setError((e as Error).message);
      }
    },
    [editingId, reset, onChange],
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
          "fixed right-0 top-0 z-30 flex h-full w-[28rem] max-w-[92vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-content">
            <Sparkles size={16} /> Personas
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        {/* Editor */}
        <div className="border-b border-border p-4">
          <p className="mb-2 text-xs font-medium text-muted">
            {editingId ? "Edit persona" : "New persona"}
          </p>
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (e.g. Legal Assistant)"
            className="mb-2 w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short description (shown under the tab)"
            className="mb-2 w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
          />
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
            placeholder="System prompt — tell the assistant who to be and how to answer in this mode."
            className="w-full resize-none rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none placeholder:text-muted focus:border-accent"
          />
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}
          <div className="mt-2 flex items-center gap-2">
            <button
              onClick={save}
              disabled={!label.trim() || !prompt.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Plus size={15} />
              {editingId ? "Save changes" : "Create persona"}
            </button>
            {editingId && (
              <button
                onClick={reset}
                className="rounded-lg px-3 py-1.5 text-sm text-muted hover:bg-elevated hover:text-content"
              >
                Cancel
              </button>
            )}
          </div>
        </div>

        {/* Lists */}
        <div className="flex-1 overflow-y-auto p-4">
          {custom.length > 0 && (
            <>
              <p className="mb-2 text-xs font-medium text-muted">
                Your personas
              </p>
              <ul className="mb-5 space-y-2">
                {custom.map((p) => (
                  <li
                    key={p.id}
                    className="group flex items-start gap-2 rounded-lg border border-border bg-surface px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-content">
                        {p.label}
                      </p>
                      {p.description && (
                        <p className="text-xs text-muted">{p.description}</p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                      <button
                        onClick={() => startEdit(p)}
                        className="text-muted hover:text-accent"
                        aria-label="Edit persona"
                      >
                        <Pencil size={14} />
                      </button>
                      <button
                        onClick={() => remove(p.id)}
                        className="text-muted hover:text-accent"
                        aria-label="Delete persona"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}

          <p className="mb-2 text-xs font-medium text-muted">Built-in</p>
          <ul className="space-y-2">
            {builtin.map((p) => (
              <li
                key={p.id}
                className="rounded-lg border border-border bg-surface px-3 py-2"
              >
                <p className="text-sm font-medium text-content">{p.label}</p>
                {p.description && (
                  <p className="text-xs text-muted">{p.description}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      </aside>
    </>
  );
}
