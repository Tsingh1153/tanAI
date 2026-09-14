"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Camera, CircleDot, X } from "lucide-react";
import clsx from "clsx";

// Live webcam capture. Grabs frames from the camera and hands them to the chat
// pipeline as images (so vision / vision-assist applies). "Live" mode captures
// on an interval, skipping ticks while a previous analysis is still streaming.
export function WebcamPanel({
  open,
  onClose,
  onCapture,
  streaming,
}: {
  open: boolean;
  onClose: () => void;
  onCapture: (dataUrl: string, prompt: string) => void;
  streaming: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [prompt, setPrompt] = useState("Describe what you see.");
  const [live, setLive] = useState(false);
  const [intervalSec, setIntervalSec] = useState(5);
  const [error, setError] = useState<string | null>(null);

  // Start/stop the camera with the panel.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user" },
          audio: false,
        });
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }
        streamRef.current = stream;
        if (videoRef.current) videoRef.current.srcObject = stream;
      } catch (e) {
        setError(
          "Could not access the camera. Grant camera permission and ensure no " +
            "other app is using it.",
        );
      }
    })();
    return () => {
      cancelled = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setLive(false);
    };
  }, [open]);

  const capture = useCallback((): string | null => {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return null;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0);
    return canvas.toDataURL("image/jpeg", 0.7);
  }, []);

  const snap = useCallback(() => {
    const frame = capture();
    if (frame) onCapture(frame, prompt.trim() || "Describe what you see.");
  }, [capture, onCapture, prompt]);

  // Live loop: capture every intervalSec, but only when idle.
  useEffect(() => {
    if (!open || !live) return;
    const id = setInterval(
      () => {
        if (!streaming) snap();
      },
      Math.max(2, intervalSec) * 1000,
    );
    return () => clearInterval(id);
  }, [open, live, intervalSec, streaming, snap]);

  return (
    <>
      <div
        className={clsx(
          "fixed inset-0 z-20 bg-black/50 transition-opacity",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
        onClick={onClose}
      />
      <aside
        className={clsx(
          "fixed right-0 top-0 z-30 flex h-full w-[28rem] max-w-[94vw] flex-col border-l border-border bg-canvas shadow-xl transition-transform",
          open ? "translate-x-0" : "translate-x-full",
        )}
      >
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-content">
            <Camera size={16} /> Webcam
          </h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-muted hover:bg-elevated hover:text-content"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-4">
          <div className="overflow-hidden rounded-xl border border-border bg-black">
            {/* eslint-disable-next-line jsx-a11y/media-has-caption */}
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              className="aspect-video w-full object-cover"
            />
          </div>
          {error && <p className="mt-2 text-xs text-accent">{error}</p>}

          <label className="mt-4 block text-xs font-medium text-muted">
            Prompt
          </label>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={2}
            className="mt-1 w-full resize-none rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-content outline-none focus:border-accent"
          />

          <div className="mt-3 flex items-center gap-2">
            <button
              onClick={snap}
              disabled={streaming}
              className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            >
              <Camera size={15} /> Capture &amp; analyze
            </button>
            <button
              onClick={() => setLive((v) => !v)}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm transition-colors",
                live
                  ? "border-accent bg-accent text-accent-fg"
                  : "border-border bg-surface text-content hover:bg-elevated",
              )}
            >
              <CircleDot size={15} /> {live ? "Stop live" : "Go live"}
            </button>
          </div>

          <div className="mt-3 flex items-center gap-2 text-xs text-muted">
            <span>Live interval:</span>
            <select
              value={intervalSec}
              onChange={(e) => setIntervalSec(Number(e.target.value))}
              className="rounded-md border border-border bg-surface px-2 py-1 text-content outline-none"
            >
              {[3, 5, 10, 20, 30].map((s) => (
                <option key={s} value={s}>
                  {s}s
                </option>
              ))}
            </select>
          </div>

          <p className="mt-4 text-xs text-muted">
            Frames are sent to the chat as images. For analysis you need a
            vision model selected, or vision-assist enabled with a vision model
            installed. Responses appear in the conversation.
          </p>
        </div>
      </aside>
    </>
  );
}
