"use client";

import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Brain,
  Camera,
  Globe,
  ImageIcon,
  MoreHorizontal,
  Volume2,
  Wrench,
} from "lucide-react";
import clsx from "clsx";

// Compact composer toolbar: the four generation toggles stay inline; less-used
// utilities (manage panels, webcam, image, speak) live behind a single "More"
// menu so the row stays clean.
export function Toolbar({
  useRag,
  availableDocs,
  onToggleRag,
  useMemory,
  onToggleMemory,
  useWeb,
  onToggleWeb,
  useAgent,
  onToggleAgent,
  speakReplies,
  onToggleSpeak,
  onManageDocs,
  onManageMemory,
  onWebcam,
  onImage,
}: {
  useRag: boolean;
  availableDocs: number;
  onToggleRag: () => void;
  useMemory: boolean;
  onToggleMemory: () => void;
  useWeb: boolean;
  onToggleWeb: () => void;
  useAgent: boolean;
  onToggleAgent: () => void;
  speakReplies: boolean;
  onToggleSpeak: () => void;
  onManageDocs: () => void;
  onManageMemory: () => void;
  onWebcam: () => void;
  onImage: () => void;
}) {
  const [menu, setMenu] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node))
        setMenu(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenu(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  return (
    <div className="mx-auto flex w-full max-w-3xl items-center gap-1.5 px-4 pt-1">
      <Toggle
        active={useRag && availableDocs > 0}
        disabled={availableDocs === 0}
        onClick={onToggleRag}
        icon={<BookOpen size={14} />}
        label="Documents"
        badge={availableDocs > 0 ? availableDocs : undefined}
        title={
          availableDocs === 0
            ? "Upload documents to enable"
            : "Answer from this chat's documents"
        }
      />
      <Toggle
        active={useMemory}
        onClick={onToggleMemory}
        icon={<Brain size={14} />}
        label="Memory"
        title={useMemory ? "Memory on" : "Memory off"}
      />
      <Toggle
        active={useWeb}
        onClick={onToggleWeb}
        icon={<Globe size={14} />}
        label="Web"
        title={useWeb ? "Web search on" : "Search the web for current info"}
      />
      <Toggle
        active={useAgent}
        onClick={onToggleAgent}
        icon={<Wrench size={14} />}
        label="Agent"
        title={useAgent ? "Agent on — can use tools" : "Agent off"}
      />

      <div ref={ref} className="relative ml-auto">
        <button
          onClick={() => setMenu((v) => !v)}
          title="More tools"
          aria-label="More tools"
          className={clsx(
            "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors",
            menu
              ? "border-accent/50 bg-elevated text-content"
              : "border-border bg-surface text-muted hover:bg-elevated hover:text-content",
          )}
        >
          <MoreHorizontal size={14} />
          More
        </button>

        {menu && (
          <div className="absolute bottom-full right-0 z-40 mb-1.5 w-52 overflow-hidden rounded-xl border border-border bg-surface p-1 shadow-xl">
            <MenuItem
              icon={<BookOpen size={14} />}
              label="Manage documents"
              onClick={() => {
                setMenu(false);
                onManageDocs();
              }}
            />
            <MenuItem
              icon={<Brain size={14} />}
              label="Manage memory"
              onClick={() => {
                setMenu(false);
                onManageMemory();
              }}
            />
            <div className="my-1 h-px bg-border" />
            <MenuItem
              icon={<Camera size={14} />}
              label="Webcam"
              onClick={() => {
                setMenu(false);
                onWebcam();
              }}
            />
            <MenuItem
              icon={<ImageIcon size={14} />}
              label="Generate image"
              onClick={() => {
                setMenu(false);
                onImage();
              }}
            />
            <MenuItem
              icon={<Volume2 size={14} />}
              label="Read replies aloud"
              active={speakReplies}
              onClick={onToggleSpeak}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function Toggle({
  icon,
  label,
  badge,
  onClick,
  active,
  disabled,
  title,
}: {
  icon: React.ReactNode;
  label: string;
  badge?: number;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={clsx(
        "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors disabled:opacity-40",
        active
          ? "border-accent bg-accent text-accent-fg"
          : "border-border bg-surface text-content hover:bg-elevated",
      )}
    >
      {icon}
      <span>{label}</span>
      {badge !== undefined && (
        <span
          className={clsx(
            "rounded-full px-1.5 text-[10px] font-semibold",
            active ? "bg-accent-fg/20" : "bg-elevated text-muted",
          )}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  active,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-sm text-content transition-colors hover:bg-elevated"
    >
      <span className="text-muted">{icon}</span>
      <span className="flex-1">{label}</span>
      {active && <span className="text-[11px] text-accent">on</span>}
    </button>
  );
}
