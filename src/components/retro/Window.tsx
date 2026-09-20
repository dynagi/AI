"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * Retro window with a lavender title bar. Minimise really collapses the body; close hides the window
 * behind a "Restore" button (component state only; nothing is deleted).
 */
export function RetroWindow({
  title, children, className, bodyClassName, tone, focused, closable = true, right,
}: {
  title: string; children: React.ReactNode; className?: string; bodyClassName?: string;
  tone?: "grey" | "yellow"; focused?: boolean; closable?: boolean; right?: React.ReactNode;
}) {
  const [min, setMin] = useState(false);
  const [closed, setClosed] = useState(false);
  if (closed) {
    return (
      <button className={cn("retro-bevel w-full px-3 py-1.5 text-left text-xs font-bold", className)} onClick={() => setClosed(false)}>
        ▢ Restore {title}
      </button>
    );
  }
  return (
    <section className={cn("retro-window", className)}>
      <div className="retro-titlebar" data-tone={tone} data-focused={focused ? "true" : undefined}>
        <span className="font-pixel truncate text-[13px] font-semibold uppercase tracking-wider">{title}</span>
        <span className="flex items-center gap-1">
          {right}
          <button className="retro-winbtn" aria-label={min ? "Restore" : "Minimise"} onClick={() => setMin((v) => !v)}>{min ? "▢" : "–"}</button>
          {closable && <button className="retro-winbtn" aria-label="Close" onClick={() => setClosed(true)}>×</button>}
        </span>
      </div>
      {!min && <div className={cn("p-3", bodyClassName)}>{children}</div>}
    </section>
  );
}
