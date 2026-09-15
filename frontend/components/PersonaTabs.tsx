"use client";

import clsx from "clsx";
import { SlidersHorizontal } from "lucide-react";
import type { Persona } from "@/lib/types";

// Horizontal tabs to switch the assistant's domain persona. "General" (id null)
// is the default and sends no persona, leaving tanAI unspecialized. The gear
// opens the editor for creating and managing custom personas.
export function PersonaTabs({
  personas,
  active,
  onChange,
  onManage,
}: {
  personas: Persona[];
  active: string | null;
  onChange: (id: string | null) => void;
  onManage: () => void;
}) {
  const activePersona = personas.find((p) => p.id === active) ?? null;

  return (
    <div className="mx-auto w-full max-w-3xl px-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <Tab
          label="General"
          active={active === null}
          onClick={() => onChange(null)}
        />
        {personas.map((p) => (
          <Tab
            key={p.id}
            label={p.label}
            active={active === p.id}
            title={p.description}
            onClick={() => onChange(p.id)}
          />
        ))}
        <button
          onClick={onManage}
          title="Manage personas"
          aria-label="Manage personas"
          className="ml-0.5 rounded-full p-1.5 text-muted transition-colors hover:bg-elevated hover:text-content"
        >
          <SlidersHorizontal size={14} />
        </button>
      </div>
      {activePersona && (
        <p className="mt-1 px-0.5 text-xs text-muted">
          {activePersona.description}
        </p>
      )}
    </div>
  );
}

function Tab({
  label,
  active,
  onClick,
  title,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={clsx(
        "rounded-full px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "bg-accent text-accent-fg"
          : "text-muted hover:bg-elevated hover:text-content",
      )}
    >
      {label}
    </button>
  );
}
