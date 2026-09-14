// Hook owning one conversation's message list and its per-turn streaming WebSocket.

import { useCallback, useEffect, useRef, useState } from "react";
import { api, wsBase } from "./api";
import type {
  AgentStep,
  Message,
  PendingApproval,
  SendOptions,
  StreamEvent,
} from "./types";

export interface UseChat {
  messages: Message[];
  streaming: boolean;
  error: string | null;
  pendingApproval: PendingApproval | null;
  send: (content: string, options?: SendOptions) => void;
  regenerate: (options?: SendOptions) => void;
  editResend: (
    messageId: string,
    content: string,
    options?: SendOptions,
  ) => void;
  approve: (approved: boolean) => void;
  stop: () => void;
}

function tempId(): string {
  return `tmp-${Math.random().toString(36).slice(2)}`;
}

export function useChat(conversationId: string | null): UseChat {
  const [messages, setMessages] = useState<Message[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingApproval, setPendingApproval] =
    useState<PendingApproval | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  // Load history whenever the active conversation changes.
  useEffect(() => {
    let cancelled = false;
    setError(null);
    if (!conversationId) {
      setMessages([]);
      return;
    }
    api
      .getConversation(conversationId)
      .then((conv) => {
        if (!cancelled) setMessages(conv.messages);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Tear down any open socket on unmount.
  useEffect(() => {
    return () => socketRef.current?.close();
  }, []);

  const stop = useCallback(() => {
    socketRef.current?.close();
    socketRef.current = null;
    setStreaming(false);
    setPendingApproval(null);
  }, []);

  // Answer an agent approval request over the live socket.
  const approve = useCallback((approved: boolean) => {
    socketRef.current?.send(JSON.stringify({ approved }));
    setPendingApproval(null);
  }, []);

  // Core streaming routine shared by send / regenerate / editResend.
  const runStream = useCallback(
    (content: string, options: SendOptions, addUserBubble: boolean) => {
      if (!conversationId || streaming || !content.trim()) return;
      setError(null);
      const {
        model,
        provider,
        useRag,
        documentIds,
        useMemory,
        useWeb,
        agent,
        images,
        regenerate,
      } = options;

      const assistantId = tempId();
      const newTurns: Message[] = [];
      if (addUserBubble) {
        newTurns.push({
          id: tempId(),
          role: "user",
          content,
          images,
          created_at: new Date().toISOString(),
        });
      }
      newTurns.push({
        id: assistantId,
        role: "assistant",
        content: "",
        model,
        created_at: new Date().toISOString(),
      });
      setMessages((prev) => [...prev, ...newTurns]);

      setStreaming(true);
      const ws = new WebSocket(`${wsBase()}/ws/chat/${conversationId}`);
      socketRef.current = ws;

      ws.onopen = () =>
        ws.send(
          JSON.stringify({
            content,
            model,
            provider,
            use_rag: !!useRag,
            document_ids: documentIds,
            use_memory: useMemory !== false,
            use_web: !!useWeb,
            agent: !!agent,
            images,
            regenerate: !!regenerate,
          }),
        );

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as StreamEvent;
        if (msg.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + msg.data }
                : m,
            ),
          );
        } else if (msg.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, sources: msg.data } : m,
            ),
          );
        } else if (msg.type === "web_sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, webSources: msg.data } : m,
            ),
          );
        } else if (msg.type === "memory") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, memories: msg.data } : m,
            ),
          );
        } else if (msg.type === "tool_call") {
          const step: AgentStep = {
            tool: msg.tool,
            arguments: msg.arguments,
            status: "running",
          };
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, steps: [...(m.steps ?? []), step] }
                : m,
            ),
          );
        } else if (msg.type === "tool_result") {
          setMessages((prev) =>
            prev.map((m) => {
              if (m.id !== assistantId || !m.steps) return m;
              // Update the most recent running step for this tool.
              const steps = [...m.steps];
              for (let i = steps.length - 1; i >= 0; i--) {
                if (
                  steps[i].tool === msg.tool &&
                  steps[i].status === "running"
                ) {
                  steps[i] = {
                    ...steps[i],
                    output: msg.output,
                    status: msg.denied ? "denied" : "done",
                  };
                  break;
                }
              }
              return { ...m, steps };
            }),
          );
        } else if (msg.type === "approval_request") {
          setPendingApproval({ tool: msg.tool, arguments: msg.arguments });
        } else if (msg.type === "error") {
          setError(msg.detail);
          setStreaming(false);
          setPendingApproval(null);
          ws.close();
        } else if (msg.type === "done") {
          setStreaming(false);
          setPendingApproval(null);
          ws.close();
        }
      };

      ws.onerror = () => {
        setError("Connection to the model backend failed.");
        setStreaming(false);
      };

      ws.onclose = () => {
        setStreaming(false);
        if (socketRef.current === ws) socketRef.current = null;
      };
    },
    [conversationId, streaming],
  );

  const send = useCallback(
    (content: string, options: SendOptions = {}) =>
      runStream(content, options, true),
    [runStream],
  );

  // Redo the last assistant reply: drop it (server + UI), re-run without adding
  // a new user turn.
  const regenerate = useCallback(
    async (options: SendOptions = {}) => {
      if (!conversationId || streaming) return;
      const lastAssistant = [...messages]
        .reverse()
        .find((m) => m.role === "assistant");
      const lastUser = [...messages].reverse().find((m) => m.role === "user");
      if (!lastAssistant || !lastUser) return;
      try {
        await api.truncateFrom(conversationId, lastAssistant.id);
      } catch {
        /* it may already be gone; continue */
      }
      setMessages((prev) => prev.filter((m) => m.id !== lastAssistant.id));
      runStream(lastUser.content, { ...options, regenerate: true }, false);
    },
    [conversationId, streaming, messages, runStream],
  );

  // Edit a user message: truncate from it, then resend the new text.
  const editResend = useCallback(
    async (messageId: string, content: string, options: SendOptions = {}) => {
      if (!conversationId || streaming) return;
      try {
        await api.truncateFrom(conversationId, messageId);
      } catch {
        /* continue */
      }
      setMessages((prev) => {
        const idx = prev.findIndex((m) => m.id === messageId);
        return idx === -1 ? prev : prev.slice(0, idx);
      });
      runStream(content, options, true);
    },
    [conversationId, streaming, runStream],
  );

  return {
    messages,
    streaming,
    error,
    pendingApproval,
    send,
    regenerate,
    editResend,
    approve,
    stop,
  };
}
