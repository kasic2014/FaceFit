"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const roles = [
  "백엔드 개발자",
  "프론트엔드 개발자",
  "풀스택 개발자",
  "데이터 엔지니어",
  "AI/ML 엔지니어",
  "DevOps 엔지니어",
  "모바일 개발자",
  "QA 엔지니어",
];

export function JobRoleSelect({ defaultValue = roles[0] }: { defaultValue?: string }) {
  const [open, setOpen] = useState(false);
  const [role, setRole] = useState(defaultValue);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between rounded-xl border border-line-300 px-3.5 py-2.5 text-left text-sm text-ink-900 outline-none transition focus:border-moss-500"
      >
        <span>{role}</span>
        <ChevronDown size={15} className={cn("flex-none text-ink-400 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className="absolute top-[calc(100%+6px)] left-0 z-10 max-h-[240px] w-full overflow-y-auto rounded-xl border border-line-300 bg-white p-1.5 shadow-[0_16px_34px_-12px_rgba(48,43,39,0.25)]">
          {roles.map((r) => (
            <div
              key={r}
              onClick={() => {
                setRole(r);
                setOpen(false);
              }}
              className={cn(
                "cursor-pointer rounded-lg px-3 py-2 text-sm",
                r === role ? "bg-moss-700/10 font-semibold text-moss-900" : "text-ink-900 hover:bg-ivory-100"
              )}
            >
              {r}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
