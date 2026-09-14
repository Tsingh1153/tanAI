"use client";

import { useState } from "react";
import { ChevronRight, Globe } from "lucide-react";
import type { WebSource } from "@/lib/types";

// Collapsible list of web citations shown beneath a web-grounded answer.
export function WebSources({ sources }: { sources: WebSource[] }) {
  const [open, setOpen] = useState(false);
  if (!sources.length) return null;

  return (
    <div className="mt-3 border-t border-border pt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 text-xs font-medium text-muted transition-colors hover:text-content"
      >
        <ChevronRight
          size={13}
          className={open ? "rotate-90 transition-transform" : "transition-transform"}
        />
        <Globe size={12} />
        {sources.length} web source{sources.length > 1 ? "s" : ""}
      </button>
      {open && (
        <ol className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <li
              key={`${s.url}-${i}`}
              className="rounded-lg border border-border bg-elevated px-3 py-2 text-xs"
            >
              <a
                href={s.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-accent hover:underline"
              >
                {i + 1}. {s.title || s.url}
              </a>
              <p className="mt-0.5 truncate text-muted">{s.url}</p>
              {s.snippet && <p className="mt-1 text-muted">{s.snippet}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
