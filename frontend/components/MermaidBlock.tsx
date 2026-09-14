"use client";

import { useEffect, useId, useRef, useState } from "react";

// Renders a Mermaid diagram from a ```mermaid code block. Mermaid is imported
// dynamically (client-only, sizeable) and re-rendered when the theme flips.
export function MermaidBlock({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rawId = useId().replace(/[:]/g, "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        const dark = document.documentElement.classList.contains("dark");
        mermaid.initialize({
          startOnLoad: false,
          theme: dark ? "dark" : "neutral",
          securityLevel: "strict",
        });
        const { svg } = await mermaid.render(`m-${rawId}`, code.trim());
        if (!cancelled && containerRef.current) {
          containerRef.current.innerHTML = svg;
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code, rawId]);

  if (error) {
    // Fall back to showing the source so nothing is lost on a parse error.
    return (
      <pre className="text-xs">
        {code}
        {"\n"}
        <span className="text-accent">Diagram error: {error}</span>
      </pre>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-3 flex justify-center overflow-x-auto rounded-lg border border-border bg-surface p-3"
    />
  );
}
