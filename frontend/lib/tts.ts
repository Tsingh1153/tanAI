// Text-to-speech using the browser's built-in speech synthesis (local, uses the
// OS voices — no dependencies, no network). A tiny module-level wrapper so any
// component can speak/stop and observe availability.

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

export function speak(text: string, onEnd?: () => void): void {
  if (!ttsSupported() || !text.trim()) return;
  window.speechSynthesis.cancel(); // stop anything currently speaking
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.0;
  utterance.pitch = 1.0;
  if (onEnd) utterance.onend = onEnd;
  window.speechSynthesis.speak(utterance);
}

export function stopSpeaking(): void {
  if (ttsSupported()) window.speechSynthesis.cancel();
}

export function isSpeaking(): boolean {
  return ttsSupported() && window.speechSynthesis.speaking;
}
