"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FolderPlus,
  Folder as FolderIcon,
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Pin,
  PinOff,
  Search,
  Trash2,
} from "lucide-react";
import clsx from "clsx";
import { Logo } from "./Logo";
import { api } from "@/lib/api";
import type { Conversation, Folder } from "@/lib/types";

// Left rail: brand, new chat, search, and the conversation list organized into
// Pinned / Folders / recency buckets. Pin and folder membership are edited from a
// per-chat "..." menu. Folder CRUD is handled here; conversation refreshes are
// delegated to the parent via onRefresh.
export function Sidebar({
  conversations,
  activeId,
  width,
  onSelect,
  onNew,
  onDelete,
  onRefresh,
}: {
  conversations: Conversation[];
  activeId: string | null;
  width: number;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [folders, setFolders] = useState<Folder[]>([]);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [menuId, setMenuId] = useState<string | null>(null);

  const refreshFolders = useCallback(async () => {
    try {
      setFolders(await api.listFolders());
    } catch {
      /* backend may be starting */
    }
  }, []);

  useEffect(() => {
    refreshFolders();
  }, [refreshFolders]);

  const matches = useCallback(
    (c: Conversation) => {
      const q = query.trim().toLowerCase();
      return !q || c.title.toLowerCase().includes(q);
    },
    [query],
  );

  const { pinned, byFolder, ungrouped } = useMemo(() => {
    const visible = conversations.filter(matches);
    const pinned = visible.filter((c) => c.pinned);
    const unpinned = visible.filter((c) => !c.pinned);
    const byFolder = new Map<string, Conversation[]>();
    for (const c of unpinned) {
      if (c.folder_id) {
        const arr = byFolder.get(c.folder_id) ?? [];
        arr.push(c);
        byFolder.set(c.folder_id, arr);
      }
    }
    const ungrouped = unpinned.filter((c) => !c.folder_id);
    return { pinned, byFolder, ungrouped };
  }, [conversations, matches]);

  const togglePin = useCallback(
    async (c: Conversation) => {
      await api.updateConversation(c.id, { pinned: !c.pinned });
      onRefresh();
    },
    [onRefresh],
  );

  const moveToFolder = useCallback(
    async (c: Conversation, folderId: string | null) => {
      await api.updateConversation(c.id, { folder_id: folderId });
      onRefresh();
    },
    [onRefresh],
  );

  const newFolder = useCallback(async () => {
    const name = window.prompt("Folder name")?.trim();
    if (!name) return;
    await api.createFolder(name);
    await refreshFolders();
  }, [refreshFolders]);

  const renameFolder = useCallback(
    async (f: Folder) => {
      const name = window.prompt("Rename folder", f.name)?.trim();
      if (!name || name === f.name) return;
      await api.renameFolder(f.id, name);
      await refreshFolders();
    },
    [refreshFolders],
  );

  const removeFolder = useCallback(
    async (f: Folder) => {
      if (!window.confirm(`Delete folder "${f.name}"? Its chats are kept.`)) return;
      await api.deleteFolder(f.id);
      await refreshFolders();
      onRefresh();
    },
    [refreshFolders, onRefresh],
  );

  const toggleCollapse = (id: string) =>
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const row = (c: Conversation) => (
    <ConvRow
      key={c.id}
      conv={c}
      active={c.id === activeId}
      folders={folders}
      menuOpen={menuId === c.id}
      onOpenMenu={() => setMenuId(menuId === c.id ? null : c.id)}
      onCloseMenu={() => setMenuId(null)}
      onSelect={() => onSelect(c.id)}
      onTogglePin={() => togglePin(c)}
      onMove={(fid) => moveToFolder(c, fid)}
      onDelete={() => onDelete(c.id)}
    />
  );

  const empty = conversations.length === 0;

  return (
    <aside
      style={{ width }}
      className="flex h-full shrink-0 flex-col border-r border-border bg-elevated"
    >
      <div className="flex items-center gap-2 px-4 pb-1 pt-4">
        <Logo size={26} wordmark />
      </div>

      <div className="p-3">
        <button
          onClick={onNew}
          className="flex w-full items-center gap-2 rounded-xl bg-gradient-to-br from-accent to-accent-2 px-3 py-2.5 text-sm font-medium text-white shadow-sm transition-opacity hover:opacity-95"
        >
          <MessageSquarePlus size={17} />
          New chat
        </button>
      </div>

      <div className="flex items-center gap-2 px-3 pb-2">
        <div className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-surface px-2.5 py-1.5 transition-colors focus-within:border-accent">
          <Search size={15} className="text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search chats"
            className="w-full bg-transparent text-sm text-content outline-none placeholder:text-muted"
          />
        </div>
        <button
          onClick={newFolder}
          title="New folder"
          className="rounded-lg border border-border bg-surface p-1.5 text-muted transition-colors hover:bg-elevated hover:text-content"
        >
          <FolderPlus size={16} />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-3">
        {empty && (
          <p className="px-3 py-6 text-center text-sm text-muted">No chats yet.</p>
        )}

        {pinned.length > 0 && (
          <Section label="Pinned">{pinned.map(row)}</Section>
        )}

        {folders.map((f) => {
          const items = byFolder.get(f.id) ?? [];
          const isCollapsed = collapsed.has(f.id);
          return (
            <div key={f.id} className="mb-1">
              <div className="group flex items-center gap-1 px-2 py-1">
                <button
                  onClick={() => toggleCollapse(f.id)}
                  className="flex flex-1 items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-muted hover:text-content"
                >
                  {isCollapsed ? (
                    <ChevronRight size={12} />
                  ) : (
                    <ChevronDown size={12} />
                  )}
                  <FolderIcon size={12} />
                  <span className="truncate">{f.name}</span>
                  <span className="text-muted">({items.length})</span>
                </button>
                <button
                  onClick={() => renameFolder(f)}
                  className="text-muted opacity-0 transition-opacity hover:text-content group-hover:opacity-100"
                  title="Rename folder"
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={() => removeFolder(f)}
                  className="text-muted opacity-0 transition-opacity hover:text-accent group-hover:opacity-100"
                  title="Delete folder"
                >
                  <Trash2 size={12} />
                </button>
              </div>
              {!isCollapsed &&
                (items.length > 0 ? (
                  items.map(row)
                ) : (
                  <p className="px-3 py-1 text-xs text-muted">Empty</p>
                ))}
            </div>
          );
        })}

        {ungrouped.length > 0 && (
          <Section label={folders.length > 0 || pinned.length > 0 ? "Chats" : ""}>
            {ungrouped.map(row)}
          </Section>
        )}
      </nav>

      <div className="border-t border-border px-4 py-3 text-xs text-muted">
        tanAI · fully local
      </div>
    </aside>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-1">
      {label && (
        <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
          {label}
        </p>
      )}
      {children}
    </div>
  );
}

function ConvRow({
  conv,
  active,
  folders,
  menuOpen,
  onOpenMenu,
  onCloseMenu,
  onSelect,
  onTogglePin,
  onMove,
  onDelete,
}: {
  conv: Conversation;
  active: boolean;
  folders: Folder[];
  menuOpen: boolean;
  onOpenMenu: () => void;
  onCloseMenu: () => void;
  onSelect: () => void;
  onTogglePin: () => void;
  onMove: (folderId: string | null) => void;
  onDelete: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onCloseMenu();
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [menuOpen, onCloseMenu]);

  return (
    <div
      ref={ref}
      className={clsx(
        "group relative flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
        active
          ? "bg-surface text-content shadow-sm"
          : "text-muted hover:bg-surface hover:text-content",
      )}
    >
      <span
        className={clsx(
          "h-4 w-0.5 shrink-0 rounded-full",
          active ? "bg-accent" : "bg-transparent",
        )}
      />
      {conv.pinned && <Pin size={11} className="shrink-0 text-accent" />}
      <button
        onClick={onSelect}
        className="flex-1 truncate text-left"
        title={conv.title}
      >
        {conv.title}
      </button>
      <button
        onClick={onOpenMenu}
        className="shrink-0 text-muted opacity-0 transition-opacity hover:text-content group-hover:opacity-100"
        aria-label="Chat options"
      >
        <MoreHorizontal size={16} />
      </button>

      {menuOpen && (
        <div className="absolute right-2 top-9 z-40 w-48 rounded-xl border border-border bg-surface p-1 text-content shadow-xl">
          <MenuItem
            icon={conv.pinned ? <PinOff size={14} /> : <Pin size={14} />}
            label={conv.pinned ? "Unpin" : "Pin"}
            onClick={() => {
              onTogglePin();
              onCloseMenu();
            }}
          />
          <div className="my-1 border-t border-border" />
          <p className="px-2.5 py-1 text-[11px] uppercase tracking-wide text-muted">
            Move to folder
          </p>
          <MenuItem
            icon={<span className="w-3.5" />}
            label="No folder"
            selected={!conv.folder_id}
            onClick={() => {
              onMove(null);
              onCloseMenu();
            }}
          />
          {folders.map((f) => (
            <MenuItem
              key={f.id}
              icon={<FolderIcon size={14} />}
              label={f.name}
              selected={conv.folder_id === f.id}
              onClick={() => {
                onMove(f.id);
                onCloseMenu();
              }}
            />
          ))}
          <div className="my-1 border-t border-border" />
          <MenuItem
            icon={<Trash2 size={14} />}
            label="Delete"
            danger
            onClick={() => {
              onDelete();
              onCloseMenu();
            }}
          />
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  selected,
  danger,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  selected?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className={clsx(
        "flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm transition-colors hover:bg-elevated",
        danger ? "text-accent" : "text-content",
      )}
    >
      {icon}
      <span className="flex-1 truncate">{label}</span>
      {selected && <Check size={13} className="text-accent" />}
    </button>
  );
}
