// Per-persona accent color + starter prompts, derived on the client so the
// backend stays unchanged. Built-ins get hand-picked hues; custom personas get a
// stable hue hashed from their id. "General" uses the brand violet.

const BUILTIN_HUES: Record<string, number> = {
  "personal-finance": 150, // green
  "markets-investing": 265, // brand violet
  "corporate-finance": 210, // blue
  "finance-tutor": 28, // amber
};

export function personaHue(id: string | null): number {
  if (!id) return 265;
  if (id in BUILTIN_HUES) return BUILTIN_HUES[id];
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) % 360;
  return h;
}

export function personaColor(id: string | null, s = 55, l = 58): string {
  return `hsl(${personaHue(id)} ${s}% ${l}%)`;
}

const STARTERS: Record<string, string[]> = {
  general: [
    "Explain quantum entanglement simply",
    "Write a Python function to debounce calls",
    "Draft a friendly out-of-office email",
    "Summarize the causes of World War I",
  ],
  "personal-finance": [
    "How much emergency fund should I aim for?",
    "Explain the avalanche vs. snowball debt methods",
    "What's the difference between a Roth and traditional IRA?",
    "Help me build a simple monthly budget",
  ],
  "markets-investing": [
    "What is an ETF and how does it differ from a mutual fund?",
    "Explain diversification in one paragraph",
    "What does a P/E ratio actually tell me?",
    "Index funds vs. active funds — trade-offs?",
  ],
  "corporate-finance": [
    "Walk me through how the three financial statements link",
    "Explain a DCF valuation step by step",
    "What is WACC and how is it calculated?",
    "Compute the present value of $1,000 in 3 years at 5%",
  ],
  "finance-tutor": [
    "Teach me compound interest with an example",
    "What is inflation, in plain English?",
    "Explain assets vs. liabilities like I'm new to this",
    "Give me a 5-minute intro to how markets work",
  ],
};

export function startersFor(id: string | null): string[] {
  return STARTERS[id ?? "general"] ?? STARTERS.general;
}
