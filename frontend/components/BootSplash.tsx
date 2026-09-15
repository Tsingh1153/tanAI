"use client";

import { useEffect, useState } from "react";
import clsx from "clsx";
import { Logo } from "./Logo";

const STATUS = ["Waking up tanAI", "Connecting to the model", "Almost ready"];

// Full-screen launch splash. Shows a floating logo with expanding halo rings and
// a cycling status line while the backend/model warms up, then fades out once the
// app reports ready (health resolved or failed). Kept up for a short minimum so
// it never flashes on a fast boot.
export function BootSplash({ ready }: { ready: boolean }) {
  const [minElapsed, setMinElapsed] = useState(false);
  const [gone, setGone] = useState(false);
  const [status, setStatus] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setMinElapsed(true), 1200);
    const cycle = setInterval(
      () => setStatus((s) => Math.min(s + 1, STATUS.length - 1)),
      900,
    );
    return () => {
      clearTimeout(t);
      clearInterval(cycle);
    };
  }, []);

  const done = ready && minElapsed;

  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => setGone(true), 550);
    return () => clearTimeout(t);
  }, [done]);

  if (gone) return null;

  return (
    <div
      className={clsx(
        "fixed inset-0 z-50 flex flex-col items-center justify-center bg-canvas transition-opacity duration-500",
        done ? "pointer-events-none opacity-0" : "opacity-100",
      )}
    >
      <div className="relative mb-8 flex h-24 w-24 items-center justify-center">
        <span className="absolute inset-0 rounded-full border border-accent/40 animate-splash-ring" />
        <span
          className="absolute inset-0 rounded-full border border-accent/30 animate-splash-ring"
          style={{ animationDelay: "0.7s" }}
        />
        <div className="animate-float">
          <Logo size={60} />
        </div>
      </div>
      <h1 className="brand-gradient animate-fade-up text-3xl font-semibold tracking-tight">
        tanAI
      </h1>
      <p
        key={status}
        className="mt-3 animate-fade-up text-sm text-muted"
        aria-live="polite"
      >
        {ready ? "Ready" : STATUS[status]}
        <span className="ml-0.5 inline-flex">
          <span
            className="typing-dot !h-1 !w-1"
            style={{ animationDelay: "0ms" }}
          />
        </span>
      </p>
    </div>
  );
}
