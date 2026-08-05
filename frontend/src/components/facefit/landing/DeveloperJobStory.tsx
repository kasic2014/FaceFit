import { ArrowDownRight, Braces, FileSearch, Mic, Sparkles } from "lucide-react";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const storyBeats = [
  {
    number: "01",
    icon: FileSearch,
    title: "공고가 바뀔 때마다, 같은 경험을 다시 번역합니다.",
    copy: "백엔드 개발 경험은 있는데, 이번 공고가 원하는 역량과 어떻게 이어지는지 한 문장으로 정리하기가 어렵습니다.",
    detail: "채용 공고 키워드 ↔ 내 프로젝트의 역할 · 판단 · 결과",
  },
  {
    number: "02",
    icon: Braces,
    title: "준비한 답은 있지만, 꼬리질문 앞에서 흐름이 끊깁니다.",
    copy: "기술을 설명하는 데 집중하다 보면 왜 그렇게 결정했는지, 무엇이 달라졌는지가 빠지기 쉽습니다.",
    detail: "문제 해결 과정 ↔ 나의 판단 ↔ 검증된 결과",
  },
  {
    number: "03",
    icon: Mic,
    title: "혼자 녹화해도, 성장 과제 한 가지가 남지 않습니다.",
    copy: "시선·발화·자세와 답변 내용을 한꺼번에 보기는 어렵고, 점수만으로는 성장 과제를 정하기 어렵습니다.",
    detail: "답변 · 발화 · 시선 · 자세의 근거 ↔ 성장 과제",
  },
] as const;

export function DeveloperJobStory() {
  return (
    <section id="developer-story" className="bg-[#f4f5f1] px-5 py-20 md:px-8 lg:px-12 lg:py-28">
      <div className="mx-auto max-w-[1280px]">
        <ScrollReveal>
          <div className="max-w-[760px]">
            <p className="text-sm font-medium text-[#c75f1d]">개발자의 면접은 코드 밖에서 이어집니다.</p>
            <h2 className="mt-5 text-[clamp(2.85rem,5.4vw,5.9rem)] font-semibold leading-[.96] tracking-[-.058em] text-[#12221c]">
              <span className="md:hidden">코드를 만들고,<br />경험을 설명합니다.</span>
              <span className="hidden md:block">개발자는 코드를 만들지만,<br />면접에서는 경험을 설명해야 합니다.</span>
            </h2>
            <p className="mt-7 max-w-[56ch] text-pretty text-lg leading-8 text-[#526159]">
              지원 공고마다 필요한 언어가 달라지고, 면접에서는 준비한 문장보다 그다음 질문에 어떻게 답하는지가 더 중요해집니다.
            </p>
          </div>
        </ScrollReveal>

        <div className="mt-14 grid gap-px overflow-hidden border border-[#12221c]/15 bg-[#12221c]/15 lg:mt-20 lg:grid-cols-3">
          {storyBeats.map((beat, index) => {
            const Icon = beat.icon;
            return (
              <ScrollReveal key={beat.number} delay={index * 90} className="bg-[#f4f5f1]">
                <article className="group min-h-[282px] p-6 transition duration-500 hover:bg-white md:p-8">
                  <div className="flex items-center justify-between text-[#628b70]">
                    <span className="text-sm font-semibold">{beat.number}</span>
                    <Icon className="size-5 transition duration-300 group-hover:rotate-[-8deg] group-hover:scale-110" />
                  </div>
                  <h3 className="mt-10 max-w-[15ch] text-xl font-semibold leading-[1.28] tracking-[-.035em] text-[#12221c]">{beat.title}</h3>
                  <p className="mt-4 line-clamp-2 max-w-[34ch] text-sm leading-6 text-[#526159]">{beat.copy}</p>
                  <p className="mt-6 flex items-start gap-2 border-t border-[#12221c]/15 pt-4 text-xs font-medium leading-5 text-[#628b70]">
                    <ArrowDownRight className="mt-0.5 size-3.5 shrink-0" />{beat.detail}
                  </p>
                </article>
              </ScrollReveal>
            );
          })}
        </div>

        <ScrollReveal delay={120}>
          <div className="relative mt-12 overflow-hidden border border-[#12221c]/15 bg-[#e2ece4] p-7 md:mt-16 md:grid md:grid-cols-[.78fr_1.22fr] md:gap-14 md:p-10">
            <div>
              <p className="text-sm font-medium text-[#628b70]">그래서 필요한 것은 더 많은 예상 질문이 아닙니다.</p>
              <p className="mt-5 max-w-[13ch] text-3xl font-semibold leading-[1.12] tracking-[-.045em] text-[#12221c]">내 경험을 다음 답변까지 연결하는 연습입니다.</p>
            </div>
            <div className="mt-9 border-l-2 border-[#d96d25] pl-5 md:mt-0 md:self-end md:pl-7">
              <div className="flex items-center gap-2 text-xs font-semibold tracking-[.12em] text-[#c75f1d]"><Sparkles className="size-3.5" /> FACE FIT LOOP</div>
              <p className="mt-3 text-xl font-medium leading-8 tracking-[-.025em] text-[#12221c]">“이번 답에서 빠진 결과를 찾고, 다음 답에서 바로 말할 수 있게 만듭니다.”</p>
              <p className="mt-4 text-sm leading-7 text-[#526159]">이력서와 공고 맥락을 질문으로 연결하고, 실제 답변의 근거를 리포트와 성장 과제로 이어갑니다.</p>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
