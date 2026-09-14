"use client";

import { useState } from "react";
import {
  Brain,
  Check,
  Copy,
  Pencil,
  RefreshCw,
  Volume2,
  VolumeX,
} from "lucide-react";
import clsx from "clsx";
import { Markdown } from "./Markdown";
import { Sources } from "./Sources";
import { WebSources } from "./WebSources";
import { AgentSteps } from "./AgentSteps";
import { API_BASE } from "@/lib/api";
import { isSpeaking, speak, stopSpeaking, ttsSupported } from "@/lib/tts";
import { Logo } from "./Logo";
import type { Message } from "@/lib/types";

// Data URLs render as-is; server paths (/images/...) get the API base prefixed.
function imageSrc(url: string): string {
  return url.startsWith("data:") ? url : `${API_BASE}${url}`;
}

// One chat turn. User turns are right-aligned in an accent bubble; assistant
// turns are full-width prose, mirroring the Claude layout.
export function MessageBubble({
  message,
  streaming,
  onEdit,
  onRegenerate,
}: {
  message: Message;
  streaming?: boolean;
  onEdit?: (newContent: string) => void;
  onRegenerate?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);
  const isUser = message.role === "user";

  const copy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const toggleSpeak = () => {
    if (speaking || isSpeaking()) {
      stopSpeaking();
      setSpeaking(false);
    } else {
      setSpeaking(true);
      speak(message.content, () => setSpeaking(false));
    }
  };

  return (
    <div
      className={clsx(
        "group flex w-full animate-rise gap-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      {!isUser && (
        <div className="mt-0.5 shrink-0">
          <Logo size={28} />
        </div>
      )}
      <div
        className={clsx(
          "relative max-w-[min(46rem,100%)] rounded-2xl px-4 py-3 text-[0.95rem] shadow-sm",
          isUser
            ? "bg-accent text-accent-fg"
            : "border border-border bg-surface text-content",
        )}
      >
        {message.images && message.images.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {message.images.map((src, i) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={i}
                src={imageSrc(src)}
                alt="attachment"
                className="max-h-48 rounded-lg border border-border object-cover"
              />
            ))}
          </div>
        )}
        {isUser ? (
          editing ? (
            <div className="w-[min(32rem,70vw)]">
              <textarea
                value={draft}
                autoFocus
                onChange={(e) => setDraft(e.target.value)}
                rows={Math.min(8, draft.split("\n").length + 1)}
                className="w-full resize-none rounded-lg bg-accent-fg/10 px-2 py-1.5 text-accent-fg outline-none"
              />
              <div className="mt-2 flex justify-end gap-2">
                <button
                  onClick={() => {
                    setEditing(false);
                    setDraft(message.content);
                  }}
                  className="rounded-lg px-2.5 py-1 text-xs text-accent-fg/80 hover:text-accent-fg"
                >
                  Cancel
                </button>
                <button
                  onClick={() => {
                    setEditing(false);
                    if (draft.trim()) onEdit?.(draft.trim());
                  }}
                  className="rounded-lg bg-accent-fg/20 px-2.5 py-1 text-xs font-medium text-accent-fg hover:bg-accent-fg/30"
                >
                  Save &amp; submit
                </button>
              </div>
            </div>
          ) : message.content ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : null
        ) : (
          <>
            {message.steps && message.steps.length > 0 && (
              <AgentSteps steps={message.steps} />
            )}
            {message.memories && message.memories.length > 0 && (
              <div className="mb-2 flex items-center gap-1.5 text-xs text-muted">
                <Brain size={13} />
                <span>
                  Recalled {message.memories.length} memor
                  {message.memories.length > 1 ? "ies" : "y"}:{" "}
                  {message.memories.map((m) => m.content).join("; ")}
                </span>
              </div>
            )}
            <span className={clsx(streaming && "stream-caret")}>
              <Markdown content={message.content || ""} />
            </span>
            {message.sources && message.sources.length > 0 && (
              <Sources sources={message.sources} />
            )}
            {message.webSources && message.webSources.length > 0 && (
              <WebSources sources={message.webSources} />
            )}
          </>
        )}

        {!isUser && message.content && (
          <div className="absolute -bottom-3 right-2 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            {onRegenerate && (
              <button
                onClick={onRegenerate}
                className="rounded-md border border-border bg-elevated p-1 text-muted hover:text-content"
                aria-label="Regenerate"
                title="Regenerate"
              >
                <RefreshCw size={14} />
              </button>
            )}
            {ttsSupported() && (
              <button
                onClick={toggleSpeak}
                className="rounded-md border border-border bg-elevated p-1 text-muted hover:text-content"
                aria-label={speaking ? "Stop speaking" : "Read aloud"}
                title={speaking ? "Stop" : "Read aloud"}
              >
                {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </button>
            )}
            <button
              onClick={copy}
              className="rounded-md border border-border bg-elevated p-1 text-muted hover:text-content"
              aria-label="Copy message"
              title="Copy"
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </button>
          </div>
        )}

        {isUser && onEdit && !editing && message.content && (
          <button
            onClick={() => {
              setDraft(message.content);
              setEditing(true);
            }}
            className="absolute -bottom-3 right-2 rounded-md border border-border bg-elevated p-1 text-muted opacity-0 transition-opacity hover:text-content group-hover:opacity-100"
            aria-label="Edit message"
            title="Edit"
          >
            <Pencil size={14} />
          </button>
        )}
      </div>
    </div>
  );
}
