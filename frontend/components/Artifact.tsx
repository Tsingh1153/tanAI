"use client";

import { useState } from "react";
import { Code2, Copy, Check, Eye } from "lucide-react";
import clsx from "clsx";

// Renders an HTML or SVG code block as a live, sandboxed preview with a
// Preview/Code toggle — like Claude's artifacts. The preview runs in a
// sandboxed iframe (scripts allowed, but isolated from the app and same-origin
// storage) so model-authored HTML/JS can't touch the page.
export function Artifact({
  code,
  language,
}: {
  code: string;
  language: "html" | "svg";
}) {
  const [view, setView] = useState<"preview" | "code">("preview");
  const [copied, setCopied] = useState(false);

  const doc =
    language === "svg"
      ? `<!doctype html><html><body style="margin:0;display:flex;justify-content:center;align-items:center;min-height:100vh;background:#fff">${code}</body></html>`
      : code;

  const copy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="my-3 overflow-hidden rounded-xl border border-border">
      <div className="flex items-center justify-between border-b border-border bg-elevated px-2.5 py-1.5">
        <div className="flex gap-1">
          <TabButton
            active={view === "preview"}
            onClick={() => setView("preview")}
            icon={<Eye size={13} />}
            label="Preview"
          />
          <TabButton
            active={view === "code"}
            onClick={() => setView("code")}
            icon={<Code2 size={13} />}
            label="Code"
          />
        </div>
        <button
          onClick={copy}
          className="flex items-center gap-1 rounded-md px-1.5 py-1 text-xs text-muted hover:text-content"
          title="Copy code"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
        </button>
      </div>
      {view === "preview" ? (
        <iframe
          title="artifact preview"
          sandbox="allow-scripts"
          className="h-80 w-full bg-white"
          srcDoc={doc}
        />
      ) : (
        <pre className="max-h-80 overflow-auto bg-[#0d1117] p-3 text-xs text-[#e6edf3]">
          {code}
        </pre>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex items-center gap-1 rounded-md px-2 py-1 text-xs transition-colors",
        active
          ? "bg-surface text-content shadow-sm"
          : "text-muted hover:text-content",
      )}
    >
      {icon}
      {label}
    </button>
  );
}
