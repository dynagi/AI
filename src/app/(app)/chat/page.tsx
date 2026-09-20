"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { readTone } from "@/lib/tone";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Where did I spend the most this month?",
  "Which subscriptions am I paying for?",
  "What expenses increased compared with last month?",
  "How much of my budget is already committed?",
  "Am I on track for my savings goal?",
  "Am I on track with my emergency fund?",
  "Why is my savings goal at risk?",
  "How much do I need to save each month?",
  "How much money do I have?",
  "What can I spend if I still want to save ₹25,000?",
  "Generate my monthly financial summary.",
  "How much did I spend today?",
];

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [convId, setConvId] = useState<string | undefined>();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, busy]);

  async function send(text: string) {
    const message = text.trim();
    if (!message || busy) return;
    setMsgs((m) => [...m, { role: "user", content: message }]);
    setInput("");
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

  return (
    <div className="mx-auto flex h-[calc(100vh-9rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold"><Sparkles className="h-5 w-5 text-primary" /> Ask Penny</h1>
        <p className="text-sm text-muted-foreground">Answers come from tool calls against your own ledger. Penny analyses your data; she does not give investment advice.</p>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {msgs.length === 0 && (
          <p className="text-sm">Hi, I&apos;m Penny, FinPilot&apos;s assistant. Ask me anything about your money.</p>
        )}
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
