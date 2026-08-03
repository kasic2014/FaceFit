import { useState } from "react";
import { cn } from "@/lib/utils";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const axes = [
  { label: "시선 처리", score: 92, detail: "카메라 응시 비율이 권장 수치를 웃돌아요. 안정적인 시선 처리를 유지하고 있어요.", dot: "bg-moss-300" },
  { label: "발화", score: 78, detail: "필러 단어 사용이 다소 감지돼요. 문장을 끝까지 말하는 연습을 추천해요.", dot: "bg-moss-700" },
  { label: "자세", score: 85, detail: "상체 흔들림이 가끔 감지돼요. 어깨를 고정하는 연습이 도움이 돼요.", dot: "bg-sunset-600" },
  { label: "답변 내용", score: 88, detail: "구조화된 STAR 답변 비율이 높아요. 근거 제시가 특히 우수해요.", dot: "bg-ink-900" },
];

export function InteractiveScorePicker() {
  const [selected, setSelected] = useState(0);
  const axis = axes[selected];

  return (
    <section className="flex flex-col items-center bg-white px-14 pb-14">
      <ScrollReveal>
        <div className="flex flex-wrap justify-center gap-2.5">
        {axes.map((a, i) => (
          <button
            key={a.label}
            onClick={() => setSelected(i)}
            className={cn(
              "flex items-center gap-2 rounded-full border px-4 py-2 font-sans text-sm font-semibold transition-all duration-150 ease-out",
              i === selected
                ? "border-moss-700/40 bg-moss-700/10 text-moss-900"
                : "border-line-300 bg-white text-ink-600 hover:bg-ivory-100"
            )}
          >
            <span className={cn("size-2 rounded-full", a.dot)} />
            {a.label}
          </button>
        ))}
        </div>
      </ScrollReveal>

      <ScrollReveal delay={120}>
        <div className="mx-auto mt-5 w-full max-w-[520px]">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="font-sans text-sm font-semibold text-ink-900">
            {axis.label} 점수
          </span>
          <span className="font-heading text-xl font-extrabold text-ink-900">
            {axis.score}
          </span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-ivory-300">
          <div
            className="h-full rounded-full bg-gradient-to-r from-moss-500 to-moss-900 transition-all duration-500 ease-out"
            style={{ width: `${axis.score}%` }}
          />
        </div>
        <p className="mt-2 font-sans text-xs text-ink-400">{axis.detail}</p>
        </div>
      </ScrollReveal>
    </section>
  );
}
