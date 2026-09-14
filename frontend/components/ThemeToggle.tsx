"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

// Toggles the `dark` class on <html> and persists the choice. Initial state is
// read from the DOM (set pre-paint by the inline script in layout.tsx).
export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  const toggle = () => {
    const next = !dark;
    setDark(next);
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("localmind-theme", next ? "dark" : "light");
    } catch {
      /* ignore storage errors */
    }
  };

  return (
    <button
      onClick={toggle}
      className="rounded-lg p-2 text-muted transition-colors hover:bg-elevated hover:text-content"
      aria-label="Toggle theme"
      title="Toggle theme"
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
