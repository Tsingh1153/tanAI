"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import type { Message } from "@/lib/types";

// Scrollable transcript. Auto-scrolls to the newest content while streaming,
// but only if the user is already near the bottom (so scrolling up to read
// history is not fought by the autoscroll).
export function MessageList({
  messages,
  streaming,
  onEdit,
  onRegenerate,
}: {
  messages: Message[];
  streaming: boolean;
  onEdit?: (messageId: string, content: string) => void;
  onRegenerate?: () => void;
}) {
  const lastAssistantIndex = (() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === "assistant") return i;
    }
    return -1;
  })();
  const endRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const nearBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight < 160;
    if (nearBottom) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  return (
    <div ref={containerRef} className="flex-1 overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-8">
        {messages.map((m, i) => (
          <MessageBubble
            key={m.id}
            message={m}
            streaming={
              streaming && i === messages.length - 1 && m.role === "assistant"
            }
            onEdit={
              m.role === "user" && onEdit && !streaming
                ? (content) => onEdit(m.id, content)
                : undefined
            }
            onRegenerate={
              i === lastAssistantIndex && onRegenerate && !streaming
                ? onRegenerate
                : undefined
            }
          />
        ))}
        <div ref={endRef} />
      </div>
    </div>
  );
}
