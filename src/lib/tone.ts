"use client";

import { useCallback, useEffect, useState } from "react";

export type Tone = "chill" | "coach" | "roast";
export const TONES: { id: Tone; label: string }[] = [
  { id: "chill", label: "😌 Chill" },
  { id: "coach", label: "💪 Coach" },
  { id: "roast", label: "🔥 Roast" },
];

const KEY = "finpilot.tone";

export function readTone(): Tone {
  try {
    const v = window.localStorage.getItem(KEY);
    return v === "coach" || v === "roast" ? v : "chill";
  } catch {
    return "chill";
  }
}

/** The voice of the assistant. It only changes wording; the numbers always come from the backend. */
export function useTone() {
  const [tone, setToneState] = useState<Tone>("chill");
  useEffect(() => setToneState(readTone()), []);
  const setTone = useCallback((t: Tone) => {
    setToneState(t);
    try {
      window.localStorage.setItem(KEY, t);
    } catch {
      /* private mode: keep it for this session only */
    }
  }, []);
  return { tone, setTone };
}
