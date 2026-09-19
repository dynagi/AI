"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "How much have I spent this month?",
  "Why did my expenses increase?",
  "Which subscriptions am I paying for?",
  "How much of my income is already committed?",
  "What changed compared with last cycle?",
  "I want to save ₹25,000. Am I on track?",
  "What are my biggest recurring expenses?",
  "Show me unusual spending this cycle.",
];

interface Msg {
  role: "user" | "assistant";
  content: string;
  tools?: string[];
}

export default function ChatPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [convId, setConvId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => end.current?.scrollIntoView({ behavior: "smooth" }), [msgs, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setInput("");
    setBusy(true);
    setError(null);
    try {
      const r = await api<{ conversation_id: string; reply: string; tool_calls: { tool: string }[] }>("/chat", { json: { message, conversation_id: convId } });
      setConvId(r.conversation_id);
      setMsgs((m) => [...m, { role: "assistant", content: r.reply, tools: r.tool_calls.map((t) => t.tool) }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-9rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold"><Sparkles className="h-5 w-5 text-primary" /> Ask FinPilot</h1>
        <p className="text-sm text-muted-foreground">Answers come from tool calls against your own ledger. FinPilot analyses your data; it does not give investment advice.</p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {msgs.length === 0 && (
          <div className="grid gap-2 sm:grid-cols-2">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => send(s)} className="rounded-lg border border-border bg-card p-3 text-left text-sm transition-colors hover:border-primary/50 hover:bg-secondary">
                {s}
              </button>
            ))}
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={cn("max-w-[85%]", m.role === "user" && "ml-auto")}>
            <Card className={cn("whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed", m.role === "user" && "border-transparent bg-primary text-primary-foreground")}>{m.content}</Card>
            {m.tools && m.tools.length > 0 && (
              <p className="mt-1 px-1 text-[11px] text-muted-foreground">Data used: {Array.from(new Set(m.tools)).join(" · ")}</p>
            )}
          </div>
        ))}
        {busy && <Card className="max-w-[85%] px-4 py-3 text-sm text-muted-foreground">Looking through your transactions…</Card>}
        {error && <p className="text-sm text-negative">{error}</p>}
        <div ref={end} />
      </div>

      <form className="mt-4 flex gap-2" onSubmit={(e) => { e.preventDefault(); void send(input); }}>
        <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about your spending, cycles, budgets or savings target…" maxLength={2000} />
        <Button type="submit" disabled={busy || !input.trim()}>Send</Button>
      </form>
    </div>
  );
}
