"use client";

import { useState } from "react";
import { ChevronRight, FileText } from "lucide-react";
import type { RetrievedSource } from "@/lib/types";

// Collapsible list of retrieved citations shown beneath a grounded answer.
export function Sources({ sources }: { sources: RetrievedSource[] }) {
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
        {sources.length} source{sources.length > 1 ? "s" : ""}
      </button>
      {open && (
        <ol className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <li
              key={`${s.document_id}-${i}`}
              className="rounded-lg border border-border bg-elevated px-3 py-2 text-xs"
            >
              <div className="mb-1 flex items-center gap-1.5 font-medium text-content">
                <FileText size={12} className="text-muted" />
                <span className="truncate">{s.filename}</span>
                {s.locator && (
                  <span className="text-muted">· {s.locator}</span>
                )}
                <span className="ml-auto shrink-0 text-muted">
                  {(s.score * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-muted">{s.snippet}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
