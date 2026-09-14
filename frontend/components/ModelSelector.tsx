"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import clsx from "clsx";
import type { ModelInfo } from "@/lib/types";

// Custom model picker (button + popover). Grouped by provider, with a checkmark
// on the active model. A custom menu is used instead of a native <select> so it
// renders reliably and matches the app's theme, including on macOS.
export function ModelSelector({
  models,
  provider,
  model,
  onChange,
  disabled,
}: {
  models: ModelInfo[];
  provider: string;
  model: string;
  onChange: (provider: string, model: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  // Group by provider label, preserving provider name for selection.
  const groups = new Map<string, ModelInfo[]>();
  for (const m of models) {
    const arr = groups.get(m.provider_label) ?? [];
    arr.push(m);
    groups.set(m.provider_label, arr);
  }

  const label = model || "Select model";

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => !disabled && setOpen((v) => !v)}
        disabled={disabled}
        className="flex max-w-[220px] items-center gap-1.5 rounded-lg border border-border bg-surface py-1.5 pl-3 pr-2 text-sm text-content transition-colors hover:bg-elevated focus:border-accent disabled:opacity-50"
        title={label}
      >
        <span className="truncate">{label}</span>
        <ChevronDown size={15} className="shrink-0 text-muted" />
      </button>

      {open && (
        <div className="absolute right-0 z-40 mt-1.5 max-h-[60vh] w-64 overflow-y-auto rounded-xl border border-border bg-surface p-1 shadow-xl">
          {models.length === 0 ? (
            <p className="px-3 py-4 text-center text-sm text-muted">
              No models found. Download one in Settings.
            </p>
          ) : (
            [...groups.entries()].map(([groupLabel, items]) => (
              <div key={groupLabel} className="mb-1 last:mb-0">
                <p className="px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
                  {groupLabel}
                </p>
                {items.map((m) => {
                  const selected = m.provider === provider && m.name === model;
                  return (
                    <button
                      key={`${m.provider}:${m.name}`}
                      onClick={() => {
                        onChange(m.provider, m.name);
                        setOpen(false);
                      }}
                      className={clsx(
                        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors",
                        selected
                          ? "bg-elevated text-content"
                          : "text-content hover:bg-elevated",
                      )}
                    >
                      <Check
                        size={14}
                        className={clsx(
                          "shrink-0",
                          selected ? "text-accent" : "opacity-0",
                        )}
                      />
                      <span className="truncate">{m.name}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
