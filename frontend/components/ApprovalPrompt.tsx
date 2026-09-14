"use client";

import { AlertTriangle } from "lucide-react";
import type { PendingApproval } from "@/lib/types";

const TOOL_VERB: Record<string, string> = {
  write_file: "write a file",
  run_python: "run Python code",
  screenshot: "take a screenshot of your screen",
  screen_info: "read your screen size and cursor position",
  move_mouse: "move your mouse",
  click: "click your mouse",
  double_click: "double-click your mouse",
  type_text: "type on your keyboard",
  press_key: "press a key on your keyboard",
  scroll: "scroll",
};

// Inline confirmation shown when the agent wants to perform a sensitive action.
export function ApprovalPrompt({
  pending,
  onApprove,
  onDeny,
}: {
  pending: PendingApproval;
  onApprove: () => void;
  onDeny: () => void;
}) {
  const verb = TOOL_VERB[pending.tool] ?? `run ${pending.tool}`;
  const detail =
    (pending.arguments.path as string) ||
    (pending.arguments.code as string) ||
    "";

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-3">
      <div className="rounded-xl border border-accent/50 bg-elevated p-3">
        <div className="mb-2 flex items-center gap-2 text-sm font-medium text-content">
          <AlertTriangle size={16} className="text-accent" />
          The agent wants to {verb}
        </div>
        {detail && (
          <pre className="mb-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-canvas px-2 py-1.5 text-xs text-muted">
            {detail}
          </pre>
        )}
        <div className="flex gap-2">
          <button
            onClick={onApprove}
            className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90"
          >
            Approve
          </button>
          <button
            onClick={onDeny}
            className="rounded-lg border border-border bg-surface px-3 py-1.5 text-sm text-content transition-colors hover:bg-elevated"
          >
            Deny
          </button>
        </div>
      </div>
    </div>
  );
}
