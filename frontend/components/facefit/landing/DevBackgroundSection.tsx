import { ScrollReveal } from "@/components/facefit/ScrollReveal";

export function DevBackgroundSection() {
  return (
    <section className="bg-[#fcfaf6] px-5 py-28 md:px-8 lg:px-12">
      <div className="mx-auto max-w-[860px]">
        <ScrollReveal>
          <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">프로젝트 개발 배경</p>
          <h2 className="mt-4 text-2xl font-bold leading-[1.5] tracking-[-.02em] text-ink-900 md:text-3xl">
            질문을 많이 푸는 것보다,
            <br />한 번의 답변을 제대로 고치는 것이 중요하다고 생각했습니다
          </h2>
          <div className="mt-7 space-y-5 text-[15px] leading-[1.9] text-ink-600 md:text-base">
            <p>
              개발자 취업 준비 과정에서는 프로젝트 경험과 기술 지식이 있어도, 이를 면접관이 이해하기 쉬운 구조로 설명하는 일이 어렵습니다.
            </p>
            <p>
              기존의 질문 모음과 모범 답변은 무엇을 말해야 하는지는 알려주지만, 내가 방금 한 답변에서 무엇이 부족했는지와 다음 답변에서 어떻게 바꿔야 하는지는 알려주지 못합니다.
            </p>
            <p>
              Face Fit은 질문을 반복해서 제공하는 서비스가 아니라, 사용자의 이력서와 실제 답변을 바탕으로 부족한 부분을 찾고 다음 연습에서 개선할 수 있도록 돕는 것을 목표로 합니다.
            </p>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
