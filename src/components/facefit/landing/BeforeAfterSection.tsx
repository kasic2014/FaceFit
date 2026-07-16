import { AnswerImprovementIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

export function BeforeAfterSection() {
  return (
    <section className="bg-ivory-100 px-5 py-24 md:px-8 lg:px-12">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <div className="flex flex-wrap items-center gap-3">
            <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">개선 전 · 후 답변</p>
            <span className="rounded-full border border-line-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-ink-400">예시 면접</span>
          </div>
          <h2 className="mt-3 max-w-[600px] text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
            내 경험은 그대로,
            <br />
            면접관이 이해하기 쉬운 구조로
          </h2>
          <p className="mt-4 max-w-[560px] text-sm leading-7 text-ink-600">
            사용자가 말하지 않은 경험이나 성과를 임의로 추가하지 않습니다. 실제로 말한 내용과 이력서 안의 사실을 바탕으로 전달 방식만 다듬습니다.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 rounded-2xl border border-line-200 bg-white p-6 md:p-8">
            <p className="text-[13px] font-semibold text-ink-400">질문</p>
            <p className="mt-1.5 text-[15px] font-medium text-ink-900">서버에서 발생한 오류는 어떻게 해결했나요?</p>

            <div className="mt-6 grid gap-4 lg:grid-cols-2">
              <div className="rounded-xl border border-line-200 px-5 py-4">
                <p className="text-[11px] font-semibold text-ink-400">내 답변 원문</p>
                <p className="mt-2 text-[14px] leading-[1.7] text-ink-600">
                  서버에서 오류가 발생해서 로그를 보고 여러 파일을 수정했고, 팀원과 이야기해서 해결했습니다.
                </p>
                <div className="mt-4 rounded-lg bg-ivory-100 px-3.5 py-3 text-[12.5px] leading-[1.6] text-ink-600">
                  분석 근거 — 해결 과정은 설명했지만 본인이 판단한 원인과 수정 결과가 구체적으로 드러나지 않습니다.
                </div>
              </div>

              <div className="rounded-xl border border-moss-300/50 bg-[#edf4ef] px-5 py-4">
                <div className="flex items-center gap-2">
                  <span className="grid size-6 place-items-center rounded-full bg-white text-moss-700">
                    <AnswerImprovementIcon className="size-3.5" />
                  </span>
                  <p className="text-[11px] font-semibold text-moss-700">개선 답변</p>
                </div>
                <p className="mt-2 text-[14px] leading-[1.7] font-medium text-ink-900">
                  서버 로그를 기준으로 프론트 요청 오류와 백엔드 세션 오류를 분리해 확인했습니다. 이후 세션 키 불일치를 수정해 로그인 후 페이지 이동 문제를 해결했습니다.
                </p>
                <button className="mt-4 rounded-lg bg-moss-900 px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-moss-700">
                  이 답변으로 다시 연습하기
                </button>
              </div>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
