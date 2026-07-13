"use client";

import { Check } from "lucide-react";
import { useEffect, useState } from "react";

export function PrototypeFeedback() {
  const [message, setMessage] = useState("");
  useEffect(() => {
    let timer: number | undefined;
    const handleClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const button = target?.closest("button");
      if (!button || button.hasAttribute("disabled")) return;
      const label = button.getAttribute("aria-label") || button.textContent?.replace(/\s+/g, " ").trim() || "버튼";
      window.clearTimeout(timer);
      setMessage(`“${label}”을(를) 선택했어요.`);
      timer = window.setTimeout(() => setMessage(""), 2400);
    };
    document.addEventListener("click", handleClick);
    return () => { document.removeEventListener("click", handleClick); window.clearTimeout(timer); };
  }, []);
  if (!message) return null;
  return <div role="status" aria-live="polite" className="fixed right-5 bottom-5 z-[70] flex max-w-[calc(100vw-40px)] items-center gap-2 rounded-xl bg-ink-900 px-4 py-3 text-sm font-medium text-white shadow-lg"><Check size={16} className="text-moss-300"/>{message}<span className="ml-1 text-xs text-white/55">프로토타입</span></div>;
}
