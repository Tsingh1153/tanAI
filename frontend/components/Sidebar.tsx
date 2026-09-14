"use client";

import { useMemo, useState } from "react";
import { MessageSquarePlus, Search, Trash2 } from "lucide-react";
import clsx from "clsx";
import { Logo } from "./Logo";
import type { Conversation } from "@/lib/types";

// Left rail: brand, new-chat action, search, and the conversation list grouped
// by recency. Purely presentational — mutations are delegated to callbacks.
export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => c.title.toLowerCase().includes(q));
  }, [conversations, query]);

  const groups = useMemo(() => groupByRecency(filtered), [filtered]);

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r border-border bg-elevated">
      <div className="flex items-center gap-2 px-4 pb-1 pt-4">
        <Logo size={26} wordmark />
      </div>

      <div className="p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-xl bg-gradient-to-br from-accent to-accent-2 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-95"
        >
          <MessageSquarePlus size={17} />
          New chat
        </button>
      </div>

      <div className="px-3 pb-2">
        <div className="flex items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 transition-colors focus-within:border-accent">
          <Search size={15} className="text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            className="w-full bg-transparent text-sm text-content outline-none placeholder:text-muted"
          />
        </div>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {filtered.length === 0 && (
          <p className="px-3 py-6 text-center text-sm text-muted">
            {conversations.length === 0 ? "No chats yet." : "No matches."}
          </p>
        )}
        {groups.map(
          ([label, items]) =>
            items.length > 0 && (
              <div key={label} className="mb-2">
                <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {label}
                </p>
                {items.map((c) => (
                  <div
                    key={c.id}
                    className={clsx(
                      "group flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                      c.id === activeId
                        ? "bg-surface text-content shadow-sm"
                        : "text-muted hover:bg-surface hover:text-content",
                    )}
                  >
                    <span
                      className={clsx(
                        "h-4 w-0.5 shrink-0 rounded-full transition-colors",
                        c.id === activeId ? "bg-accent" : "bg-transparent",
                      )}
                    />
                    <button
                      onClick={() => onSelect(c.id)}
                      className="flex-1 truncate text-left"
                      title={c.title}
                    >
                      {c.title}
                    </button>
                    <button
                      onClick={() => onDelete(c.id)}
                      className="opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
                      aria-label="Delete chat"
                      title="Delete"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                ))}
              </div>
            ),
        )}
      </nav>

      <div className="border-t border-border px-4 py-3 text-xs text-muted">
        tanAI · fully local
      </div>
    </aside>
  );
}

// Bucket conversations into Today / Yesterday / Previous 7 days / Older.
function groupByRecency(
  conversations: Conversation[],
): [string, Conversation[]][] {
  const now = new Date();
  const startOfToday = new Date(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  ).getTime();
  const day = 86400000;

  const buckets: Record<string, Conversation[]> = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    Older: [],
  };

  for (const c of conversations) {
    const t = new Date(c.updated_at).getTime();
    if (t >= startOfToday) buckets.Today.push(c);
    else if (t >= startOfToday - day) buckets.Yesterday.push(c);
    else if (t >= startOfToday - 7 * day) buckets["Previous 7 days"].push(c);
    else buckets.Older.push(c);
  }

  return Object.entries(buckets);
}
