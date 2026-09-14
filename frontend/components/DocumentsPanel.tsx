"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  BrainCircuit,
  CheckCircle2,
  FileText,
  Globe,
  Loader2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";
import type { DocumentInfo } from "@/lib/types";

// Right-hand drawer for a chat's documents. Uploads are scoped to the active
// conversation; documents can be promoted to the global "memory" set so they
// persist across all chats. New chats start with an empty "This chat" section.
export function DocumentsPanel({
  open,
  onClose,
  onChange,
  conversationId,
  ensureConversation,
}: {
  open: boolean;
  onClose: () => void;
  onChange: () => void;
  conversationId: string | null;
  ensureConversation: () => Promise<string>;
}) {
  const [docs, setDocs] = useState<DocumentInfo[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      setDocs(await api.listDocuments(conversationId ?? undefined));
    } catch (e) {
      setError((e as Error).message);
    }
  }, [conversationId]);

  useEffect(() => {
    if (open) refresh();
  }, [open, refresh]);

  const uploadFiles = useCallback(
    async (files: FileList | File[]) => {
      setError(null);
      setUploading(true);
      try {
        // Ensure a chat exists so uploads have somewhere to live.
        const cid = await ensureConversation();
        for (const file of Array.from(files)) {
          await api.uploadDocument(file, cid);
          await refresh();
          onChange();
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setUploading(false);
      }
    },
    [ensureConversation, refresh, onChange],
  );

  const remove = useCallback(
    async (id: string) => {
      await api.deleteDocument(id);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  const promote = useCallback(
    async (id: string) => {
      await api.promoteDocument(id);
      await refresh();
      onChange();
    },
    [refresh, onChange],
  );

  const chatDocs = docs.filter((d) => d.conversation_id === conversationId);
  const memoryDocs = docs.filter((d) => !d.conversation_id);

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-20 bg-black/40 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <aside
        className={clsx(
          "fixed right-0 top-0 z-30 flex h-full w-96 max-w-[90vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold text-content">Documents</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        {/* Dropzone */}
        <div className="p-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              if (e.dataTransfer.files.length)
                uploadFiles(e.dataTransfer.files);
            }}
            onClick={() => inputRef.current?.click()}
            className={clsx(
              "flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-6 text-center transition-colors",
              dragOver
                ? "border-accent bg-elevated"
                : "border-border hover:bg-elevated",
            )}
          >
            {uploading ? (
              <Loader2 size={22} className="animate-spin text-accent" />
            ) : (
              <Upload size={22} className="text-muted" />
            )}
            <p className="text-sm text-content">
              {uploading ? "Indexing…" : "Drop files or click to upload"}
            </p>
            <p className="text-xs text-muted">
              Added to <span className="font-medium">this chat</span> · PDF,
              Word, Excel, CSV, Markdown, HTML, code
            </p>
          </div>
          <input
            ref={inputRef}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files?.length) uploadFiles(e.target.files);
              e.target.value = "";
            }}
          />
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}
        </div>

        {/* Lists */}
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <Section title="This chat" hint="Only used in this conversation">
            {chatDocs.length === 0 ? (
              <Empty text="No documents in this chat yet." />
            ) : (
              chatDocs.map((d) => (
                <DocRow
                  key={d.id}
                  doc={d}
                  onDelete={() => remove(d.id)}
                  onPromote={() => promote(d.id)}
                />
              ))
            )}
          </Section>

          <Section
            title="Memory"
            hint="Available in every chat"
            icon={<Globe size={13} className="text-muted" />}
          >
            {memoryDocs.length === 0 ? (
              <Empty text="No shared documents. Use “Add to memory”." />
            ) : (
              memoryDocs.map((d) => (
                <DocRow key={d.id} doc={d} onDelete={() => remove(d.id)} />
              ))
            )}
          </Section>
        </div>
      </aside>
    </>
  );
}

function Section({
  title,
  hint,
  icon,
  children,
}: {
  title: string;
  hint: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5">
      <div className="mb-2 flex items-center gap-1.5">
        {icon}
        <h3 className="text-xs font-semibold uppercase tracking-wide text-muted">
          {title}
        </h3>
        <span className="text-xs text-muted">· {hint}</span>
      </div>
      <div className="space-y-2">{children}</div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="px-1 py-3 text-sm text-muted">{text}</p>;
}

function DocRow({
  doc,
  onDelete,
  onPromote,
}: {
  doc: DocumentInfo;
  onDelete: () => void;
  onPromote?: () => void;
}) {
  return (
    <div className="group flex items-start gap-2 rounded-lg border border-border bg-surface px-3 py-2">
      <FileText size={16} className="mt-0.5 shrink-0 text-muted" />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm text-content" title={doc.filename}>
          {doc.filename}
        </p>
        <div className="mt-0.5 flex items-center gap-1.5 text-xs text-muted">
          <StatusBadge doc={doc} />
        </div>
        {doc.status === "error" && doc.error && (
          <p className="mt-1 text-xs text-accent">{doc.error}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1.5 opacity-0 transition-opacity group-hover:opacity-100">
        {onPromote && doc.status === "ready" && (
          <button
            onClick={onPromote}
            className="text-muted hover:text-accent"
            aria-label="Add to memory"
            title="Add to memory (use in all chats)"
          >
            <BrainCircuit size={15} />
          </button>
        )}
        <button
          onClick={onDelete}
          className="text-muted hover:text-accent"
          aria-label="Delete document"
        >
          <Trash2 size={15} />
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ doc }: { doc: DocumentInfo }) {
  if (doc.status === "ready") {
    return (
      <>
        <CheckCircle2 size={12} className="text-green-500" />
        <span>{doc.num_chunks} chunks</span>
      </>
    );
  }
  if (doc.status === "error") {
    return (
      <>
        <AlertCircle size={12} className="text-accent" />
        <span>Failed</span>
      </>
    );
  }
  return (
    <>
      <Loader2 size={12} className="animate-spin" />
      <span>Indexing…</span>
    </>
  );
}
