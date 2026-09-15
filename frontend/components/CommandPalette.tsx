"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Search } from "lucide-react";
import clsx from "clsx";

export interface Command {
  id: string;
  label: string;
  group: string;
  hint?: string;
  active?: boolean;
  run: () => void;
}

// Fuzzy-ish command palette (⌘K). One input, a grouped/filtered list, full
// keyboard nav. Centralizes navigation and toggles so the visible UI can stay
// minimal.
export function CommandPalette({
  open,
  onClose,
  commands,
}: {
  open: boolean;
  onClose: () => void;
  commands: Command[];
}) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) =>
        c.label.toLowerCase().includes(q) ||
        c.group.toLowerCase().includes(q) ||
        (c.hint?.toLowerCase().includes(q) ?? false),
    );
  }, [commands, query]);

  useEffect(() => {
    setActive((a) => Math.min(a, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  if (!open) return null;

  const run = (c?: Command) => {
    if (!c) return;
    c.run();
    onClose();
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(filtered[active]);
    }
  };

  // Preserve command order but tag group headers at first appearance.
  let lastGroup = "";

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/40 pt-[12vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-surface shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2 border-b border-border px-3.5">
          <Search size={16} className="shrink-0 text-muted" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats, models, personas, actions…"
            className="w-full bg-transparent py-3 text-sm text-content outline-none placeholder:text-muted"
          />
        </div>
        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-1.5">
          {filtered.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted">
              No matches
            </p>
          ) : (
            filtered.map((c, i) => {
              const header = c.group !== lastGroup ? c.group : null;
              lastGroup = c.group;
              return (
                <div key={c.id}>
                  {header && (
                    <p className="px-2.5 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                      {header}
                    </p>
                  )}
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => run(c)}
                    className={clsx(
                      "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors",
                      i === active
                        ? "bg-elevated text-content"
                        : "text-content hover:bg-elevated",
                    )}
                  >
                    <span className="flex-1 truncate">{c.label}</span>
                    {c.active && (
                      <span className="text-[11px] text-accent">on</span>
                    )}
                    {c.hint && (
                      <span className="shrink-0 text-[11px] text-muted">
                        {c.hint}
                      </span>
                    )}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
