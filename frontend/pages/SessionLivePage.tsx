import { useCallback, useEffect, useRef, useState } from "react";
import { CircleHelp, Headphones, Mic, Video } from "lucide-react";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { VideoPanel } from "@/components/facefit/interview/VideoPanel";
import { GuidePanel } from "@/components/facefit/interview/GuidePanel";
import { InterviewOnboarding } from "@/components/facefit/interview/InterviewOnboarding";
import { Logo } from "@/components/facefit/Logo";
import { ConfirmModal } from "@/components/facefit/ui/States";

type InterviewPhase = "answering" | "saving" | "next";
const totalQuestions = 5;

export default function InterviewRoomPage() {
  const [end, setEnd] = useState(false);
  const [mic, setMic] = useState(true);
  const [camera, setCamera] = useState(true);
  const [phase, setPhase] = useState<InterviewPhase>("answering");
  const [questionIndex, setQuestionIndex] = useState(0);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const completionTimer = useRef<number | null>(null);
  const completingRef = useRef(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setOnboardingOpen(window.localStorage.getItem("facefit-interview-onboarding-dismissed") !== "true");
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => () => {
    if (completionTimer.current) window.clearTimeout(completionTimer.current);
  }, []);

  const completeAnswer = useCallback(() => {
    if (phase !== "answering" || end || onboardingOpen || completingRef.current) return;
    completingRef.current = true;
    setPhase("saving");
    // TODO: Connect silence-detection auto completion here when recording/STT is available.
    completionTimer.current = window.setTimeout(() => {
      if (questionIndex === totalQuestions - 1) {
        setEnd(true);
      } else {
        setQuestionIndex((index) => index + 1);
        setPhase("next");
      }
      completingRef.current = false;
    }, 700);
  }, [end, onboardingOpen, phase, questionIndex]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && onboardingOpen) {
        setOnboardingOpen(false);
        return;
      }
      if (event.code !== "Space" || event.repeat || phase !== "answering" || end || onboardingOpen || completingRef.current) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, button") || target?.isContentEditable) return;
      event.preventDefault();
      completeAnswer();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [completeAnswer, end, onboardingOpen, phase]);

  const closeOnboarding = () => setOnboardingOpen(false);
  const dismissOnboarding = () => {
    window.localStorage.setItem("facefit-interview-onboarding-dismissed", "true");
    closeOnboarding();
  };
  const closeEndModal = () => {
    setEnd(false);
    if (phase === "saving") setPhase("answering");
  };

  return <div className="min-h-screen bg-[#24372F]">
    <PageContainer size="wide" className="flex min-h-screen flex-col gap-4 py-4 md:h-dvh md:min-h-0 md:py-5">
      <header className="flex shrink-0 items-center justify-between px-1 text-white">
        <div className="flex min-w-0 items-center gap-3"><Logo size="sm" textClassName="text-white" /><span className="truncate text-sm text-white/55">AI 면접 진행 중</span></div>
        <div className="flex items-center gap-2"><button type="button" onClick={() => setOnboardingOpen(true)} className="grid size-9 place-items-center rounded-lg text-white/70 transition hover:bg-white/10 hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white" aria-label="면접 안내 다시 보기"><CircleHelp size={18} /></button><span className="shrink-0 text-xs text-white/70">질문 {questionIndex + 1} / {totalQuestions}</span></div>
      </header>

      <section className="flex flex-1 flex-col justify-center gap-4 md:hidden" aria-labelledby="mobile-interview-notice">
        <div className="w-full rounded-2xl border border-white/10 bg-[#1C2A24] px-6 py-8 text-center text-white"><h1 id="mobile-interview-notice" className="text-xl font-bold">큰 화면에서 면접을 진행해 주세요</h1><p className="mt-3 break-words text-sm leading-6 text-white/60">카메라 화면과 실시간 가이드를 안정적으로 확인하려면 태블릿 또는 데스크톱 사용을 권장합니다.</p></div>
        <div className="grid grid-cols-2 gap-3"><button type="button" onClick={phase === "next" ? () => setPhase("answering") : completeAnswer} disabled={phase === "saving" || onboardingOpen} className="min-h-11 rounded-xl border border-white/30 bg-white px-3 py-3 text-sm font-bold text-[#24372F] transition hover:bg-[#F2F0EA] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/10 disabled:text-white/40">{phase === "saving" ? "저장 중" : phase === "next" ? "다음 질문 답변하기" : <>답변 완료 <kbd className="ml-1 whitespace-nowrap rounded border border-current/25 px-1 py-0.5 text-[10px] font-medium">Space</kbd></>}</button><button type="button" onClick={() => setEnd(true)} className="min-h-11 rounded-xl bg-sunset-600 px-3 py-3 text-sm font-bold text-white">면접 종료</button></div>
      </section>

      <main className="relative hidden min-h-0 flex-1 gap-4 md:grid md:grid-cols-6 md:grid-rows-[minmax(240px,3fr)_minmax(160px,2fr)] lg:grid-cols-12 lg:grid-rows-1">
        <VideoPanel /><GuidePanel />
        {phase !== "answering" && <div className="absolute inset-0 z-10 grid place-items-center bg-[#10221D]/55 p-4"><div className="min-w-0 max-w-lg rounded-xl border border-white/10 bg-[#1C2A24] px-6 py-5 text-center text-white"><p className="break-words text-lg font-bold">{phase === "saving" ? "답변을 저장하고 있어요." : "다음 질문을 준비했어요."}</p><p className="mt-2 break-words text-sm text-white/60">{phase === "saving" ? "답변을 정리하고 다음 질문을 확인합니다." : "프로젝트에서 가장 어려웠던 판단은 무엇이었나요?"}</p>{phase === "next" && <button type="button" onClick={() => setPhase("answering")} className="mt-4 min-h-11 rounded-lg bg-sunset-600 px-4 py-2.5 text-sm font-bold">다음 질문 답변하기</button>}</div></div>}
      </main>

      <footer className="hidden shrink-0 flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-[#1C2A24] px-5 py-4 md:flex lg:flex-nowrap">
        <div className="flex shrink-0 gap-2"><button type="button" onClick={() => setMic(!mic)} className="min-h-11 whitespace-nowrap rounded-lg border border-white/15 px-4 py-2.5 text-sm text-white"><Mic size={15} className="mr-1 inline" />마이크 {mic ? "ON" : "OFF"}</button><button type="button" onClick={() => setCamera(!camera)} className="min-h-11 whitespace-nowrap rounded-lg border border-white/15 px-4 py-2.5 text-sm text-white"><Video size={15} className="mr-1 inline" />카메라 {camera ? "ON" : "OFF"}</button></div>
        <div className="flex shrink-0 gap-2"><button type="button" onClick={completeAnswer} disabled={phase !== "answering" || onboardingOpen} className="min-h-11 whitespace-nowrap rounded-lg border border-white/25 bg-white px-5 py-2.5 text-sm font-bold text-[#24372F] transition hover:bg-[#F2F0EA] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/10 disabled:text-white/40">답변 완료 <kbd className="ml-1 rounded border border-current/25 px-1 py-0.5 text-[10px] font-medium">Space</kbd></button><button type="button" onClick={() => setEnd(true)} className="min-h-11 whitespace-nowrap rounded-lg bg-sunset-600 px-4 py-2.5 text-sm font-bold text-white">면접 종료</button></div>
        <span className="basis-full break-words text-center text-xs text-white/45 lg:min-w-0 lg:flex-1 lg:basis-auto lg:truncate lg:text-right"><Headphones size={13} className="mr-1 inline" />답변 완료 후 저장한 뒤 다음 질문을 준비합니다.</span>
      </footer>
      <ConfirmModal open={end} onClose={closeEndModal} />
      {onboardingOpen && <InterviewOnboarding onStart={closeOnboarding} onDismissForever={dismissOnboarding} />}
    </PageContainer>
  </div>;
}
