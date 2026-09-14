"use client";

import { Sparkles } from "lucide-react";
import clsx from "clsx";

// tanAI brand mark: a gradient rounded square with a spark, optionally paired
// with the gradient wordmark.
export function Logo({
  size = 26,
  wordmark = false,
}: {
  size?: number;
  wordmark?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <div
        className="flex shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-white shadow-sm"
        style={{ width: size, height: size }}
      >
        <Sparkles size={size * 0.56} strokeWidth={2.4} />
      </div>
      {wordmark && (
        <span
          className={clsx("brand-gradient font-semibold tracking-tight")}
          style={{ fontSize: size * 0.62 }}
        >
          tanAI
        </span>
      )}
    </div>
  );
}
