import { Eye, MessageSquareText, Hash, ArrowRight } from "lucide-react";

const items = [
  { icon: Eye, title: "시선 유지 연습", desc: "카메라를 자연스럽게 바라보는 연습", duration: "5분" },
  { icon: MessageSquareText, title: "결론 먼저 말하기", desc: "답변의 첫 문장에서 핵심 전달 연습", duration: "5분" },
  { icon: Hash, title: "구체적 수치 표현", desc: "성과를 숫자로 설명하는 연습", duration: "5분" },
];

export function RecommendedPracticeRow() {
  return (
    <div className="rounded-2xl bg-[#f5efe4] p-6">
      <p className="mb-1 text-[15px] font-bold text-ink-900">이번 주 추천 연습</p>
      <p className="mb-4 text-[12.5px] text-ink-600">우선 개선 항목을 중심으로 연습해 보세요.</p>

      <div className="flex flex-col gap-4 md:flex-row md:items-stretch">
        <div className="grid flex-1 gap-3 sm:grid-cols-3">
          {items.map((it) => (
            <div key={it.title} className="flex flex-col justify-between rounded-xl border border-line-200 bg-white p-4">
              <div>
                <span className="grid size-8 place-items-center rounded-full bg-ivory-100 text-moss-700">
                  <it.icon size={15} />
                </span>
                <p className="mt-2.5 text-[13px] font-bold text-ink-900">{it.title}</p>
                <p className="mt-1 text-[11.5px] leading-[1.5] text-ink-400">{it.desc}</p>
              </div>
              <span className="mt-3 w-fit rounded-full bg-ivory-100 px-2 py-0.5 text-[10px] font-semibold text-ink-400">{it.duration}</span>
            </div>
          ))}
        </div>
        <button className="flex flex-none items-center justify-center gap-2 rounded-xl bg-sunset-600 px-6 py-3 text-[13px] font-semibold text-white transition hover:bg-sunset-700 md:w-[150px]">
          연습 시작하기
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  );
}
