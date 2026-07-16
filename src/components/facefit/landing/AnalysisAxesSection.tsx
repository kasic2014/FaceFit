import { EyeAnalysisIcon, SpeechAnalysisIcon, PostureAnalysisIcon, ContentAnalysisIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const axes = [
  { icon: EyeAnalysisIcon, label: "시선", score: 74, evidence: "답변 중 화면 아래를 3초 이상 바라본 구간이 반복됐습니다." },
  { icon: SpeechAnalysisIcon, label: "발화", score: 81, evidence: "답변 후반부의 말하기 속도가 초반보다 빨라졌습니다." },
  { icon: PostureAnalysisIcon, label: "자세", score: 78, evidence: "기술 설명 구간에서 상체 움직임이 커졌습니다." },
  { icon: ContentAnalysisIcon, label: "내용", score: 69, evidence: "문제 상황은 구체적이지만 본인의 판단과 최종 결과가 빠져 있습니다." },
];

export function AnalysisAxesSection() {
  return (
    <section className="bg-[#fcfaf6] px-5 py-24 md:px-8 lg:px-12">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">4축 분석</p>
            <span className="rounded-full border border-line-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-ink-400">샘플 리포트</span>
          </div>
          <h2 className="mt-3 max-w-[620px] text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
            점수가 아니라, 점수의 이유를 보여줍니다
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 rounded-2xl border border-line-200 bg-white p-6 md:p-8">
            <div className="mb-6 rounded-xl border border-moss-300/40 bg-[#edf4ef] px-5 py-4">
              <p className="text-[11px] font-semibold text-moss-700">가장 중요한 개선 포인트</p>
              <p className="mt-1.5 text-[15px] font-medium leading-[1.6] text-ink-900">
                내용 — 결과 문장 앞에서 한 번 호흡하고, 최종 판단과 결과를 붙여 말해 보세요.
              </p>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              {axes.map((a) => (
                <div key={a.label} className="rounded-xl border border-line-200 px-5 py-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="grid size-8 place-items-center rounded-full bg-ivory-100 text-moss-700">
                        <a.icon className="size-4" />
                      </span>
                      <p className="text-sm font-bold text-ink-900">{a.label}</p>
                    </div>
                    <span className="text-sm font-bold tabular-nums text-ink-900">{a.score}<span className="text-ink-300">/100</span></span>
                  </div>
                  <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-line-200">
                    <div className="h-full rounded-full bg-moss-500" style={{ width: `${a.score}%` }} />
                  </div>
                  <p className="mt-3 text-[13px] leading-[1.6] text-ink-600">근거 — {a.evidence}</p>
                </div>
              ))}
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
