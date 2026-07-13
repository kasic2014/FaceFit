import { ReverseQuestionIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const avoid = ["채용 페이지에 이미 공개된 내용", "직무와 무관한 질문", "지나치게 추상적인 질문", "준비 없이 복지만 묻는 질문"];

export function ReverseQuestionSection() {
  return (
    <section className="bg-[#fcfaf6] px-6 py-24 md:px-12 lg:px-16">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">역질문 추천</p>
            <span className="rounded-full border border-line-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-ink-400">추천 예시</span>
          </div>
          <h2 className="mt-3 max-w-[600px] text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
            지원 기업과 직무에 맞는
            <br />
            역질문을 준비합니다
          </h2>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-line-200 bg-white p-6">
              <div className="flex items-center gap-2.5">
                <span className="grid size-9 place-items-center rounded-full bg-ivory-100 text-moss-700">
                  <ReverseQuestionIcon className="size-[18px]" />
                </span>
                <p className="text-[13px] font-semibold text-ink-400">추천 질문</p>
              </div>
              <p className="mt-4 text-[15px] font-medium leading-[1.6] text-ink-900">
                &ldquo;신입 개발자가 입사 초기 가장 먼저 맡게 되는 업무와, 독립적으로 기능을 담당하기까지의 기준이 궁금합니다.&rdquo;
              </p>
              <p className="mt-3 text-[13px] leading-[1.6] text-ink-600">
                추천 이유 — 목표 직무의 초기 온보딩 구조를 확인해, 입사 후 적응 계획을 구체적으로 설명할 수 있습니다.
              </p>

              <div className="mt-6 border-t border-line-200 pt-5">
                <p className="text-[15px] font-medium leading-[1.6] text-ink-900">
                  &ldquo;현재 팀에서는 새로운 기술 도입 여부를 어떤 기준과 과정으로 결정하는지 궁금합니다.&rdquo;
                </p>
                <p className="mt-3 text-[13px] leading-[1.6] text-ink-600">
                  추천 이유 — 지원한 기술 스택과 팀의 의사결정 방식이 잘 맞는지 확인할 수 있습니다.
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-line-200 bg-white p-6">
              <p className="text-[13px] font-semibold text-ink-400">피해야 할 역질문</p>
              <ul className="mt-4 space-y-2.5">
                {avoid.map((a) => (
                  <li key={a} className="flex items-center gap-2.5 text-[13px] text-ink-700">
                    <span className="size-1.5 shrink-0 rounded-full bg-line-300" />
                    {a}
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
