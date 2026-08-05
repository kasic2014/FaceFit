import { ArrowDown, FileText, SearchCheck, Sparkles } from "lucide-react";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

export function EvidenceRetrievalSection() {
  return (
    <section id="question-evidence" className="bg-[#e2ece4] px-5 py-20 text-[#12221c] md:px-8 lg:px-12 lg:py-28">
      <div className="mx-auto grid max-w-[1280px] gap-12 lg:grid-cols-[.78fr_1.22fr] lg:items-end lg:gap-20">
        <ScrollReveal>
          <p className="text-sm font-medium text-[#c75f1d]">지원 자료가 질문의 근거가 됩니다.</p>
          <h2 className="mt-5 max-w-[12ch] text-[clamp(2.8rem,5vw,5.4rem)] font-semibold leading-[.99] tracking-[-.04em]">
            내 경험에 맞는<br />질문부터<br />시작합니다.
          </h2>
          <p className="mt-7 max-w-[40ch] text-lg leading-8 text-[#43534b]">
            이력서와 채용 공고에 더해, 기업과 직무의 관련 자료를 찾아 질문의 맥락과 근거를 구성합니다.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={110}>
          <div className="overflow-hidden border border-[#164032]/18 bg-[#f8faf7] shadow-[0_10px_22px_rgba(22,64,50,.1)]">
            <div className="flex items-center justify-between border-b border-[#12221c]/12 px-5 py-4 md:px-7">
              <p className="text-xs font-semibold text-[#628b70]">QUESTION CONTEXT / 03</p>
              <p className="text-xs font-medium text-[#c75f1d]">지원 자료 기반</p>
            </div>
            <div className="grid gap-px bg-[#12221c]/12 md:grid-cols-2">
              <article className="context-source bg-[#f8faf7] p-5 transition duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1 hover:bg-white md:p-7">
                <div className="flex items-center gap-2 text-[#628b70]"><FileText className="size-4" /><p className="text-xs font-semibold">이력서 문장</p></div>
                <p className="mt-5 text-base font-semibold leading-7 tracking-[-.02em]">“이미지 업로드 오류를 재현하고, API 무효화 시점을 수정했습니다.”</p>
                <p className="mt-3 text-sm leading-6 text-[#526159]">문제 재현 · 원인 분리 · 수정 결과</p>
              </article>
              <article className="context-source bg-[#f8faf7] p-5 transition duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] hover:-translate-y-1 hover:bg-white md:p-7">
                <div className="flex items-center gap-2 text-[#628b70]"><SearchCheck className="size-4" /><p className="text-xs font-semibold">채용 공고 기준</p></div>
                <p className="mt-5 text-base font-semibold leading-7 tracking-[-.02em]">백엔드 안정성, 장애 대응, 유관 부서와의 협업 경험</p>
                <p className="mt-3 text-sm leading-6 text-[#526159]">지원 포지션이 확인하려는 역량</p>
              </article>
            </div>
            <div className="context-connector flex justify-center bg-[#f8faf7] py-3 text-[#d96d25]" aria-hidden="true"><ArrowDown className="size-4" /></div>
            <div className="context-question flex min-h-[190px] flex-col justify-center bg-[#164032] p-7 text-white md:min-h-[224px] md:p-10">
              <div className="flex items-center gap-2 text-[#f2ab72]"><Sparkles className="size-4" /><p className="text-xs font-semibold">생성된 면접 질문</p></div>
              <p className="mt-5 max-w-[42ch] text-xl font-medium leading-8 tracking-[-.025em] md:text-[1.7rem] md:leading-10">이미지 업로드 오류를 해결하셨다고 했는데요. 당시 어떤 현상부터 확인했고, API 무효화 시점을 수정해야 한다고 판단한 근거는 무엇이었나요?</p>
              <p className="mt-6 border-t border-white/22 pt-4 text-[0.9375rem] font-medium leading-6 text-[#e7f4ec]">문제 재현부터 원인 분리, 수정 판단까지 실제 경험의 순서를 확인하는 질문입니다.</p>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
