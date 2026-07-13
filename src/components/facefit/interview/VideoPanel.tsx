import Image from "next/image";
import { RotateCcw } from "lucide-react";

export function VideoPanel() {
  return (
    <div className="relative flex-[0_0_70%] overflow-hidden rounded-2xl bg-[#1c2b26]">
      <Image src="/images/interviewer-hr.png" alt="AI 면접관 영상" fill className="object-cover" priority />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/45 via-transparent via-30% to-black/20" />

      <div className="pointer-events-none absolute top-5 left-5 flex items-center gap-3 animate-[fade-up-sm_0.45s_cubic-bezier(0.16,1,0.3,1)_both]" style={{ animationDelay: "0ms" }}>
        <span className="grid size-11 shrink-0 place-items-center rounded-full bg-black/40 text-xs font-bold text-white">AI</span>
        <div>
          <p className="text-sm font-semibold text-white">AI 면접관 서연</p>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-white/70">
            <span className="size-1.5 rounded-full bg-[#7A9B7E]" />
            연결 상태: 양호
          </p>
        </div>
      </div>

      <div className="absolute right-5 bottom-5 left-5 rounded-2xl bg-[#0e1a17]/85 px-6 py-5 text-center backdrop-blur-sm animate-[fade-up-sm_0.45s_cubic-bezier(0.16,1,0.3,1)_both]" style={{ animationDelay: "140ms" }}>
        <p className="text-xs font-semibold tracking-[0.08em] text-[#7A9B7E] uppercase">질문</p>
        <p className="mt-2.5 text-lg leading-[1.5] font-semibold text-white md:text-xl">
          본인이 가장 어려웠던 프로젝트 경험을 설명해 주세요.
        </p>
        <div className="mx-auto mt-4 max-w-[220px] border-t border-white/10 pt-3.5">
          <button className="inline-flex items-center gap-1.5 text-xs font-medium text-white/55 transition-colors hover:text-white/85">
            <RotateCcw size={13} />
            질문 다시 듣기
          </button>
        </div>
      </div>
    </div>
  );
}
