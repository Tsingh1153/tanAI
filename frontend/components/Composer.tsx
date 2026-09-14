"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, ImagePlus, Loader2, Mic, Square, X } from "lucide-react";
import clsx from "clsx";
import { api } from "@/lib/api";

// Auto-growing message input with optional image attachments. Enter sends;
// Shift+Enter inserts a newline. While a response streams, send becomes stop.
export function Composer({
  onSend,
  onStop,
  streaming,
  disabled,
}: {
  onSend: (text: string, images: string[]) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const [images, setImages] = useState<string[]>([]); // data URLs
  const [recording, setRecording] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    setVoiceError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size) chunksRef.current.push(e.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setTranscribing(true);
        try {
          const { text: transcript } = await api.transcribe(blob);
          if (transcript) {
            setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
          }
        } catch (e) {
          setVoiceError((e as Error).message);
        } finally {
          setTranscribing(false);
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setVoiceError("Could not access the microphone.");
    }
  };

  const stopRecording = () => {
    recorderRef.current?.stop();
    recorderRef.current = null;
    setRecording(false);
  };

  const toggleMic = () => (recording ? stopRecording() : startRecording());

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [text]);

  const addFiles = (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () =>
        setImages((prev) => [...prev, reader.result as string]);
      reader.readAsDataURL(file);
    }
  };

  const submit = () => {
    const value = text.trim();
    if ((!value && images.length === 0) || streaming || disabled) return;
    onSend(value, images);
    setText("");
    setImages([]);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  // Allow pasting images directly into the box.
  const onPaste = (e: React.ClipboardEvent) => {
    const files = Array.from(e.clipboardData.files);
    if (files.length) addFiles(files);
  };

  const canSend = (!!text.trim() || images.length > 0) && !disabled;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-6">
      {images.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {images.map((src, i) => (
            <div key={i} className="relative">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt="attachment"
                className="h-16 w-16 rounded-lg border border-border object-cover"
              />
              <button
                onClick={() =>
                  setImages((prev) => prev.filter((_, j) => j !== i))
                }
                className="absolute -right-1.5 -top-1.5 rounded-full bg-canvas p-0.5 text-muted shadow hover:text-accent"
                aria-label="Remove image"
              >
                <X size={13} />
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-2 rounded-[1.75rem] border border-border bg-surface p-2 shadow-md transition-shadow focus-within:border-accent/60 focus-within:shadow-lg">
        <button
          onClick={() => fileRef.current?.click()}
          disabled={disabled}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-muted transition-colors hover:bg-elevated hover:text-content disabled:opacity-40"
          aria-label="Attach image"
          title="Attach image"
        >
          <ImagePlus size={18} />
        </button>
        <button
          onClick={toggleMic}
          disabled={disabled || transcribing}
          className={clsx(
            "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl transition-colors disabled:opacity-40",
            recording
              ? "bg-accent text-accent-fg"
              : "text-muted hover:bg-elevated hover:text-content",
          )}
          aria-label={recording ? "Stop recording" : "Record voice"}
          title={recording ? "Stop recording" : "Record voice"}
        >
          {transcribing ? (
            <Loader2 size={18} className="animate-spin" />
          ) : (
            <Mic size={18} className={recording ? "animate-pulse" : ""} />
          )}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <textarea
          ref={ref}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
          rows={1}
          disabled={disabled}
          placeholder={
            disabled ? "Select or start a chat…" : "Message tanAI…"
          }
          className="max-h-[220px] flex-1 resize-none bg-transparent px-2 py-1.5 text-[0.95rem] text-content outline-none placeholder:text-muted disabled:opacity-50"
        />
        {streaming ? (
          <button
            onClick={onStop}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-elevated text-content transition-colors hover:bg-border"
            aria-label="Stop generating"
            title="Stop"
          >
            <Square size={16} />
          </button>
        ) : (
          <button
            onClick={submit}
            disabled={!canSend}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent text-accent-fg transition-opacity hover:opacity-90 disabled:opacity-40"
            aria-label="Send message"
            title="Send"
          >
            <ArrowUp size={18} />
          </button>
        )}
      </div>
      {(recording || transcribing || voiceError) && (
        <p className="mt-1.5 text-center text-xs text-muted">
          {recording
            ? "Recording… click the mic to stop"
            : transcribing
              ? "Transcribing…"
              : voiceError}
        </p>
      )}
      <p className="mt-2 text-center text-xs text-muted">
        Runs locally. Responses may be inaccurate — verify important information.
      </p>
    </div>
  );
}
