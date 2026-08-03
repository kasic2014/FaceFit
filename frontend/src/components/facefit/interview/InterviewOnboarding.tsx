import { Check, Keyboard, X } from "lucide-react";
import { useEffect, useRef } from "react";

type InterviewOnboardingProps = {
  onStart: () => void;
  onDismissForever: () => void;
};

const guideItems = [
  "면접관의 질문을 확인하세요.",
  "질문이 끝난 뒤 답변을 시작하세요.",
  "답변 후 5초 동안 침묵하면 답변이 자동 완료될 수 있어요.",
  "자동 완료되지 않거나 바로 끝내고 싶다면 '답변 완료' 버튼 또는 Space 키를 사용하세요.",
  "다음 질문이 있으면 계속 진행되고, 마지막 답변 후 면접이 종료됩니다.",
  "오른쪽 가이드 패널에서 현재 질문과 도움말을 확인할 수 있어요.",
];

export function InterviewOnboarding({ onStart, onDismissForever }: InterviewOnboardingProps) {
  const startButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    startButtonRef.current?.focus();
  }, []);

  return <div className="fixed inset-0 z-40 grid place-items-center overflow-y-auto bg-[#10221D]/70 p-4" role="dialog" aria-modal="true" aria-labelledby="interview-onboarding-title">
    <section className="w-full max-w-xl rounded-2xl border border-white/10 bg-[#F7F5EF] p-5 text-ink-900 shadow-[0_20px_50px_rgba(0,0,0,.28)] sm:p-7">
      <div className="flex items-start justify-between gap-4"><div><p className="text-sm font-bold text-moss-800">FaceFit AI 면접</p><h1 id="interview-onboarding-title" className="mt-1 text-2xl font-bold tracking-[-.045em]">면접 시작 전 안내</h1></div><Keyboard className="mt-1 shrink-0 text-moss-800" size={22} aria-hidden="true" /></div>
      <ul className="mt-5 space-y-3 text-sm leading-6 text-ink-700">{guideItems.map((item) => <li key={item} className="flex gap-2.5"><Check className="mt-1 shrink-0 text-moss-800" size={15} aria-hidden="true" /><span>{item}</span></li>)}</ul>
      <p className="mt-5 rounded-xl bg-[#EAF0E9] px-4 py-3 text-sm leading-6 text-moss-900 md:hidden">모바일에서는 <b>답변 완료</b> 버튼을 사용해 답변을 마칠 수 있어요.</p>
      <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end"><button type="button" onClick={onDismissForever} className="inline-flex min-h-11 items-center justify-center gap-1.5 rounded-xl border border-line-300 px-4 py-3 text-sm font-bold text-ink-700 transition hover:bg-ivory-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-moss-700"><X size={16} />다시 보지 않기</button><button ref={startButtonRef} type="button" onClick={onStart} className="min-h-11 rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white transition hover:bg-moss-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">면접 시작하기</button></div>
    </section>
  </div>;
}
