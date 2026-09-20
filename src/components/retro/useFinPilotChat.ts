"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { readTone } from "@/lib/tone";

export interface ChatMsg {
  role: "user" | "assistant";
  content: string;
}

/** Used by the dashboard "Ask FinPilot.exe" window: same POST /chat endpoint and agent as the chat page. */
export function useFinPilotChat() {
  const [msgs, setMsgs] = useState<ChatMsg[]>([]);
  const [convId, setConvId] = useState<string | undefined>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ conversation_id: string; reply: string }>("/chat", { json: { message, conversation_id: convId, tone: readTone() } });
      setConvId(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return { msgs, busy, error, send };
}
