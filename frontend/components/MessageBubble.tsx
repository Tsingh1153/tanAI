"use client";

import { memo, useState } from "react";
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

// One chat turn. User turns sit in a soft accent bubble on the right; assistant
// turns are clean, borderless prose beside the avatar (less boxy, Claude-style).
// Wrapped in memo so that during streaming only the changing bubble re-renders.
function MessageBubbleImpl({
  message,
  streaming,
  onEdit,
  onRegenerate,
}: {
  message: Message;
  streaming?: boolean;
  onEdit?: (id: string, newContent: string) => void;
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
        <div className="mt-1 shrink-0">
          <Logo size={26} />
        </div>
      )}
      <div
        className={clsx(
          "relative min-w-0 text-[0.95rem]",
          isUser
            ? "max-w-[min(42rem,85%)] rounded-3xl rounded-br-md bg-accent px-4 py-2.5 text-accent-fg shadow-sm"
            : "max-w-[min(46rem,100%)] pb-1 text-content",
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
                className="max-h-48 rounded-xl border border-border/60 object-cover"
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
                className="w-full resize-none rounded-xl bg-accent-fg/10 px-2 py-1.5 text-accent-fg outline-none"
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
                    if (draft.trim()) onEdit?.(message.id, draft.trim());
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

        {/* Action row — sits just below the message on hover. */}
        {!isUser && message.content && !streaming && (
          <div className="mt-1 flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
            {onRegenerate && (
              <ActionButton onClick={onRegenerate} label="Regenerate">
                <RefreshCw size={14} />
              </ActionButton>
            )}
            {ttsSupported() && (
              <ActionButton
                onClick={toggleSpeak}
                label={speaking ? "Stop" : "Read aloud"}
              >
                {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
              </ActionButton>
            )}
            <ActionButton onClick={copy} label="Copy">
              {copied ? <Check size={14} /> : <Copy size={14} />}
            </ActionButton>
          </div>
        )}

        {isUser && onEdit && !editing && message.content && (
          <button
            onClick={() => {
              setDraft(message.content);
              setEditing(true);
            }}
            className="absolute -bottom-2.5 right-2 rounded-lg border border-border bg-elevated p-1 text-muted opacity-0 shadow-sm transition-opacity hover:text-content group-hover:opacity-100"
            aria-label="Edit message"
            title="Edit"
          >
            <Pencil size={13} />
          </button>
        )}
      </div>
    </div>
  );
}

function ActionButton({
  onClick,
  label,
  children,
}: {
  onClick: () => void;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-lg p-1.5 text-muted transition-colors hover:bg-elevated hover:text-content"
      aria-label={label}
      title={label}
    >
      {children}
    </button>
  );
}

export const MessageBubble = memo(MessageBubbleImpl);
