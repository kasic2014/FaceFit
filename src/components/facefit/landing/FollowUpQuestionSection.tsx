import { FollowUpQuestionIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const gaps = ["기술 선택 근거 부족", "본인의 역할 불명확", "결과 누락", "추상적인 표현", "행동과 결과 연결 부족"];

export function FollowUpQuestionSection() {
  return (
    <section className="bg-[#fcfaf6] px-6 py-24 md:px-12 lg:px-16">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <div className="grid gap-6 md:grid-cols-[1.1fr_.9fr] md:items-end">
            <div>
              <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">답변 기반 꼬리질문</p>
              <h2 className="mt-3 text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
                방금 한 답변이,
                <br />
                다음 질문이 됩니다
              </h2>
            </div>
            <p className="max-w-[420px] text-sm leading-7 text-ink-600 md:justify-self-end">
              예상 질문을 외우는 연습이 아니라, 내가 방금 한 말을 더 구체적으로 설명하는 연습입니다.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 grid gap-6 lg:grid-cols-[1.3fr_.7fr]">
            <div className="rounded-2xl border border-line-200 bg-white p-6 md:p-8">
              <div className="flex items-start gap-3">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-ivory-100 text-moss-700">
                  <FollowUpQuestionIcon className="size-4" />
                </span>
                <div>
                  <p className="text-[11px] font-semibold text-ink-400">면접관 · 메인 질문</p>
                  <p className="mt-1 text-[15px] font-medium text-ink-900">프로젝트에서 가장 어려웠던 점은 무엇이었나요?</p>
                </div>
              </div>

              <div className="mt-4 ml-11 rounded-xl bg-ivory-100 px-4 py-3">
                <p className="text-[11px] font-semibold text-ink-400">내 답변</p>
                <p className="mt-1 text-[14px] leading-[1.6] text-ink-700">손 인식 정확도가 낮아서 여러 조건을 추가해 개선했습니다.</p>
              </div>

              <div className="mt-4 ml-11 flex items-center gap-2 text-[12px] font-medium text-ink-400">
                <span className="size-1.5 rounded-full bg-sunset-600" />
                분석 중 — 확인할 지점: <span className="font-semibold text-sunset-700">결과 누락, 판단 기준 불명확</span>
              </div>

              <div className="mt-4 flex items-start gap-3 rounded-xl border border-moss-300/40 bg-[#edf4ef] px-4 py-3.5">
                <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white text-moss-700">
                  <FollowUpQuestionIcon className="size-4" />
                </span>
                <div>
                  <p className="text-[11px] font-semibold text-moss-700">면접관 · 꼬리질문</p>
                  <p className="mt-1 text-[14px] font-medium leading-[1.6] text-ink-900">
                    정확도가 낮다고 판단한 구체적인 상황과, 추가한 조건 중 가장 효과가 컸던 기준을 설명해 주시겠어요?
                  </p>
                </div>
              </div>
            </div>

            <div className="rounded-2xl border border-line-200 bg-white p-6">
              <p className="text-[11px] font-semibold text-ink-400">꼬리질문은 다음 지점에서 생성됩니다</p>
              <ul className="mt-4 space-y-2.5">
                {gaps.map((g) => (
                  <li key={g} className="flex items-center gap-2.5 text-[13px] text-ink-700">
                    <span className="size-1.5 shrink-0 rounded-full bg-sunset-600" />
                    {g}
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
