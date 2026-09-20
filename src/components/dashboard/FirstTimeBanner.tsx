"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const KEY = "finpilot.guide.seen";

/** Shown once to new users: points to the User Guide. Dismissal is remembered in this browser only. */
export default function FirstTimeBanner() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    try {
      setShow(window.localStorage.getItem(KEY) !== "1");
    } catch {
      setShow(true);
    }
  }, []);

  function dismiss() {
    setShow(false);
    try {
      window.localStorage.setItem(KEY, "1");
    } catch {
      /* private mode: it will show again next visit */
    }
  }

  if (!show) return null;
  return (
    <div className="flex items-start gap-3 border-2 border-black bg-[#FFF29A] p-3 text-sm" role="note">
      <span aria-hidden className="text-xl">📖</span>
      <p className="min-w-0 flex-1">
        <b>New here?</b> The User Guide explains what each page and dashboard section is for, and how to read your warnings.{" "}
        <Link href="/guide" onClick={dismiss} className="font-bold underline">Open the User Guide</Link>
      </p>
      <button className="retro-winbtn shrink-0" aria-label="Dismiss" onClick={dismiss}>×</button>
    </div>
  );
}
