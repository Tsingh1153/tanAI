"use client";

import { useState } from "react";
import { Check, ChevronRight, Loader2, Terminal, X } from "lucide-react";
import clsx from "clsx";
import type { AgentStep } from "@/lib/types";

const TOOL_LABELS: Record<string, string> = {
  get_current_time: "Checked the time",
  web_fetch: "Fetched a web page",
  list_files: "Listed files",
  read_file: "Read a file",
  write_file: "Wrote a file",
  run_python: "Ran Python",
  // Computer use
  screen_info: "Checked the screen",
  screenshot: "Took a screenshot",
  move_mouse: "Moved the mouse",
  click: "Clicked",
  double_click: "Double-clicked",
  type_text: "Typed text",
  press_key: "Pressed a key",
  scroll: "Scrolled",
};

// Renders the agent's tool-use timeline above its final answer.
export function AgentSteps({ steps }: { steps: AgentStep[] }) {
  if (!steps.length) return null;
  return (
    <div className="mb-3 space-y-1.5">
      {steps.map((s, i) => (
        <StepRow key={i} step={s} />
      ))}
    </div>
  );
}

function StepRow({ step }: { step: AgentStep }) {
  const [open, setOpen] = useState(false);
  const label = TOOL_LABELS[step.tool] ?? step.tool;
  const arg = summarizeArgs(step.arguments);

  return (
    <div className="rounded-lg border border-border bg-elevated px-2.5 py-1.5 text-xs">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-1.5 text-left"
      >
        <ChevronRight
          size={12}
          className={clsx(
            "shrink-0 text-muted transition-transform",
            open && "rotate-90",
          )}
        />
        <Terminal size={12} className="shrink-0 text-muted" />
        <span className="font-medium text-content">{label}</span>
        {arg && <span className="truncate text-muted">{arg}</span>}
        <span className="ml-auto shrink-0">
          {step.status === "running" && (
            <Loader2 size={12} className="animate-spin text-muted" />
          )}
          {step.status === "done" && (
            <Check size={12} className="text-green-500" />
          )}
          {step.status === "denied" && <X size={12} className="text-accent" />}
        </span>
      </button>
      {open && step.output && (
        <pre className="mt-1.5 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-canvas px-2 py-1.5 text-[11px] text-muted">
          {step.output}
        </pre>
      )}
    </div>
  );
}

function summarizeArgs(args: Record<string, unknown>): string {
  if (args.url) return String(args.url);
  if (args.path) return String(args.path);
  if (args.code) return "code";
  if (args.text) return `"${String(args.text).slice(0, 40)}"`;
  if (args.keys) return String(args.keys);
  if (args.x !== undefined && args.y !== undefined)
    return `(${args.x}, ${args.y})`;
  return "";
}
