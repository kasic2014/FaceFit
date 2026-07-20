import { CircleCheck, Circle, Headphones, Mic, Video, ChevronDown, RotateCcw } from "lucide-react";
import { FollowUpQuestionIcon, ContentAnalysisIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const structureChecklist = [
  { label: "상황 설명", done: true },
  { label: "본인 역할", done: true },
  { label: "어려운 지점", done: false },
  { label: "결과", done: false },
];

export function LiveInterviewSection() {
  return (
    <section className="bg-ivory-100 px-5 py-24 md:px-8 lg:px-12">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">실제 면접실 경험</p>
          <h2 className="mt-3 max-w-[640px] text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
            녹음 위젯이 아니라, 면접관과 마주 앉은 화면
          </h2>
          <p className="mt-4 max-w-[560px] text-sm leading-7 text-ink-600">
            질문을 듣고 답변하는 동안, 옆에서는 질문 의도와 답변 구조를 함께 확인할 수 있습니다.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 flex flex-col gap-4 rounded-[24px] bg-[#10221D] p-4 shadow-[0_22px_55px_rgba(42,48,39,.12)] md:p-5">
            <div className="flex flex-col gap-4 md:flex-row">
              <div className="relative flex-[0_0_68%] overflow-hidden rounded-2xl bg-[#1c2b26]">
                <div className="absolute inset-0 min-h-[360px]"><img src="/images/interviewer-hr.png" alt="AI 면접관 영상" className="absolute inset-0 size-full object-cover" loading="lazy" /></div>
                <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/45 via-transparent via-30% to-black/20" />

                <div className="pointer-events-none absolute top-5 left-5 flex items-center gap-3">
                  <span className="grid size-11 shrink-0 place-items-center rounded-full bg-black/40 text-xs font-bold text-white">AI</span>
                  <div>
                    <p className="text-sm font-semibold text-white">HR 면접관 · 압박</p>
                    <p className="mt-0.5 flex items-center gap-1.5 text-xs text-white/70">
                      <span className="size-1.5 rounded-full bg-[#7A9B7E]" />
                      연결 상태: 양호
                    </p>
                  </div>
                </div>

                <div className="absolute right-5 bottom-5 left-5 rounded-2xl bg-[#0e1a17]/85 px-6 py-5 text-center backdrop-blur-sm">
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

              <div className="flex flex-[0_0_32%] flex-col gap-3.5 rounded-2xl bg-white p-5">
                <div className="flex items-center justify-between">
                  <span className="text-[14px] font-bold text-zinc-900">연습 코치</span>
                </div>

                <div>
                  <p className="mb-2 text-xs font-semibold text-ink-400">나의 화면</p>
                  <div className="relative aspect-video w-full overflow-hidden rounded-xl">
                    <img src="/images/user-webcam.png" alt="내 웹캠" className="absolute inset-0 size-full object-cover" loading="lazy" />
                  </div>
                </div>

                <div className="rounded-xl border border-line-200 bg-ivory-100 p-3.5">
                  <div className="flex items-center gap-2">
                    <FollowUpQuestionIcon className="size-4 text-moss-700" />
                    <p className="text-xs font-bold text-ink-900">질문 의도</p>
                  </div>
                  <p className="mt-1.5 text-[12.5px] leading-[1.6] text-ink-600">
                    문제 해결 과정과 본인의 기여도를 확인하는 질문입니다.
                  </p>
                </div>

                <div className="rounded-xl border border-line-200 p-3.5">
                  <div className="flex items-center gap-2">
                    <ContentAnalysisIcon className="size-4 text-moss-700" />
                    <p className="text-xs font-bold text-ink-900">답변 구조 체크</p>
                  </div>
                  <ul className="mt-2.5 flex flex-col gap-1.5">
                    {structureChecklist.map((item) => (
                      <li key={item.label} className="flex items-center gap-2 text-[12.5px]">
                        {item.done ? <CircleCheck size={15} className="text-moss-700" /> : <Circle size={15} className="text-line-300" />}
                        <span className={item.done ? "text-ink-900" : "text-ink-400"}>{item.label}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-3 rounded-2xl bg-[#0e1a17] px-5 py-4 md:justify-between">
              <button className="flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-[13px] font-medium text-white/75">
                <Headphones size={15} />
                오디오 점검
              </button>
              <div className="flex flex-wrap items-center justify-center gap-3">
                <button className="flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-[13px] font-medium text-white/75">
                  <Mic size={15} />
                  마이크 ON
                  <ChevronDown size={13} className="text-white/40" />
                </button>
                <button className="flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2.5 text-[13px] font-medium text-white/75">
                  <Video size={15} />
                  카메라 ON
                  <ChevronDown size={13} className="text-white/40" />
                </button>
                <button className="rounded-xl bg-sunset-600 px-6 py-2.5 text-[13px] font-semibold text-white transition hover:bg-sunset-700">
                  답변 완료
                </button>
                <button className="rounded-xl border border-white/10 px-5 py-2.5 text-[13px] font-medium text-white/75">
                  면접 종료
                </button>
              </div>
              <span className="w-full text-center text-[10px] text-white/30 md:w-auto">
                Spacebar로도 종료할 수 있어요 · 5초 침묵 자동 감지는 보조 기능입니다
              </span>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
