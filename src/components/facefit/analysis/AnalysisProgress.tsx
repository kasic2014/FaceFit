"use client";

import Link from "next/link";
import { useEffect, useState, type ComponentType } from "react";
import {
  AudioLines,
  Check,
  FileCheck2,
  FileText,
  LoaderCircle,
  MessageSquareText,
  ScanFace,
} from "lucide-react";

type AnalysisStage = {
  title: string;
  description: string;
  icon: ComponentType<{ size?: number; strokeWidth?: number }>;
};

const analysisStages: AnalysisStage[] = [
  { title: "답변 데이터 준비", description: "답변 파일을 안전하게 정리하고 있어요", icon: FileCheck2 },
  { title: "음성 전달력 분석", description: "말의 속도와 전달력을 살펴보고 있어요", icon: AudioLines },
  { title: "시선·자세 분석", description: "시선과 자세의 흐름을 분석하고 있어요", icon: ScanFace },
  { title: "답변 내용 분석", description: "답변의 구조와 핵심 내용을 확인하고 있어요", icon: MessageSquareText },
  { title: "리포트 생성", description: "분석 결과를 리포트로 정리하고 있어요", icon: FileText },
];

export function AnalysisProgress() {
  const [currentStage, setCurrentStage] = useState(0);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const isComplete = currentStage >= analysisStages.length;
  const activeStage = analysisStages[Math.min(currentStage, analysisStages.length - 1)];
  const ActiveIcon = activeStage.icon;

  useEffect(() => {
    if (isComplete) return;

    // TODO: Replace this mock timer with the analysis status returned by the API.
    const timer = window.setTimeout(() => {
      setCurrentStage((stage) => Math.min(stage + 1, analysisStages.length));
    }, 1800);

    return () => window.clearTimeout(timer);
  }, [currentStage, isComplete]);

  return (
    <section className="w-full" aria-live="polite">
      <AnalysisVisual icon={ActiveIcon} complete={isComplete} />
      <p className="mt-7 text-sm font-bold text-moss-700">분석 진행 중</p>
      <h1 className="mt-2 text-3xl font-bold tracking-[-.03em] text-ink-900">
        {isComplete ? "리포트를 준비했어요." : activeStage.description}
      </h1>
      <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-ink-600">
        분석에는 몇 분 정도 걸릴 수 있어요.<br />
        페이지를 나가도 완료된 결과는 마이페이지에서 확인할 수 있습니다.
      </p>

      <div className="mt-7" aria-label={`${analysisStages.length}단계 중 ${Math.min(currentStage + 1, analysisStages.length)}단계`}>
        <div className="grid grid-cols-5 gap-2" aria-hidden="true">
          {analysisStages.map((stage, index) => (
            <span
              key={stage.title}
              className={index < currentStage
                ? "h-1.5 rounded-full bg-moss-700"
                : index === currentStage && !isComplete
                  ? "h-1.5 animate-pulse rounded-full bg-moss-500 motion-reduce:animate-none"
                  : "h-1.5 rounded-full bg-line-200"}
            />
          ))}
        </div>
        <p className="mt-2 text-right text-xs font-medium text-ink-400">{isComplete ? "모든 단계 완료" : `${currentStage + 1} / ${analysisStages.length} 단계`}</p>
      </div>

      <ol className="mt-6 space-y-2 text-left" aria-label="분석 단계">
        {analysisStages.map((stage, index) => {
          const status = index < currentStage ? "complete" : index === currentStage && !isComplete ? "current" : "waiting";
          const Icon = stage.icon;

          return (
            <li
              key={stage.title}
              className={status === "current"
                ? "analysis-step flex min-w-0 items-center gap-3 rounded-xl border border-moss-300 bg-white px-4 py-3 opacity-100 shadow-[0_6px_18px_rgba(45,70,53,.06)]"
                : status === "complete"
                  ? "analysis-step flex min-w-0 items-center gap-3 rounded-xl border border-line-200 bg-white px-4 py-3 opacity-100"
                  : "analysis-step flex min-w-0 items-center gap-3 rounded-xl border border-line-200 bg-white px-4 py-3 opacity-45"}
            >
              <span className={status === "current"
                ? "grid size-8 shrink-0 place-items-center rounded-full bg-moss-900 text-white"
                : status === "complete"
                  ? "grid size-8 shrink-0 place-items-center rounded-full bg-moss-700 text-white"
                  : "grid size-8 shrink-0 place-items-center rounded-full bg-ivory-300 text-ink-400"}
              >
                {status === "complete" ? <Check className="animate-[analysis-check_0.28s_ease-out] motion-reduce:animate-none" size={16} strokeWidth={3} /> : status === "current" ? <LoaderCircle className="animate-spin motion-reduce:animate-none" size={16} /> : <Icon size={16} />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block break-words text-sm font-semibold text-ink-900">{stage.title}</span>
                {status === "current" && <span className="mt-0.5 block break-words text-xs text-ink-600">{stage.description}</span>}
              </span>
              {status === "current" && <span aria-hidden="true" className="flex shrink-0 gap-1"><i className="size-1.5 animate-pulse rounded-full bg-moss-700 motion-reduce:animate-none" /><i className="size-1.5 animate-pulse rounded-full bg-moss-700 [animation-delay:150ms] motion-reduce:animate-none" /><i className="size-1.5 animate-pulse rounded-full bg-moss-700 [animation-delay:300ms] motion-reduce:animate-none" /></span>}
            </li>
          );
        })}
      </ol>

      <button type="button" onClick={() => setLeaveOpen(true)} className="mt-7 inline-flex min-h-11 items-center justify-center rounded-xl border border-line-300 bg-white px-5 text-sm font-bold text-ink-700 transition hover:border-moss-300 hover:text-moss-900">
        나중에 확인하기
      </button>

      {leaveOpen && <LeaveAnalysisModal onClose={() => setLeaveOpen(false)} />}
    </section>
  );
}

function AnalysisVisual({ icon: Icon, complete }: { icon: AnalysisStage["icon"]; complete: boolean }) {
  return (
    <div className="relative mx-auto grid size-48 place-items-center sm:size-56" aria-hidden="true">
      <span className="analysis-ring absolute size-[74%] rounded-full border border-moss-300" />
      <span className="analysis-ring absolute size-[92%] rounded-full border border-moss-300/70 [animation-direction:reverse] [animation-duration:12s]" />
      <span className="absolute inset-[18%] overflow-hidden rounded-full border border-line-200 bg-white">
        <i className="analysis-scan absolute inset-x-0 top-0 h-px bg-moss-500" />
      </span>
      <span className={complete
        ? "relative z-10 grid size-20 place-items-center rounded-full bg-moss-700 text-white sm:size-24"
        : "analysis-core relative z-10 grid size-20 place-items-center rounded-full bg-moss-900 text-white sm:size-24"}
      >
        {complete ? <Check size={32} strokeWidth={2.5} /> : <Icon size={32} strokeWidth={1.8} />}
      </span>
    </div>
  );
}

function LeaveAnalysisModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink-900/35 p-4">
      <section role="dialog" aria-modal="true" aria-labelledby="later-title" className="w-full max-w-md rounded-[18px] border border-line-200 bg-white p-6 text-left shadow-xl">
        <h2 id="later-title" className="text-xl font-bold text-ink-900">마이페이지에서 나중에 확인할까요?</h2>
        <p className="mt-3 text-sm leading-6 text-ink-600">분석은 계속 진행되며 완료된 결과는 마이페이지에서 확인할 수 있습니다.</p>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button type="button" onClick={onClose} className="min-h-11 rounded-lg bg-moss-900 px-4 text-sm font-semibold text-white">계속 기다리기</button>
          <Link href="/dashboard" className="inline-flex min-h-11 items-center justify-center rounded-lg border border-line-300 px-4 text-sm font-semibold text-ink-700">마이페이지로 이동</Link>
        </div>
      </section>
    </div>
  );
}
