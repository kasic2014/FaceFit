"use client";

import { useState } from "react";
import Image from "next/image";
import { ChevronUp, ChevronDown, CircleCheck, Circle } from "lucide-react";
import { FollowUpQuestionIcon, ContentAnalysisIcon, SpeechAnalysisIcon } from "@/components/facefit/icons";

const structureChecklist = [
  { label: "상황 설명", done: true },
  { label: "본인 역할", done: true },
  { label: "어려운 지점", done: false },
  { label: "결과", done: false },
  { label: "배운 점", done: false },
];

const speechStatus = [
  { label: "말하기 속도", value: "적절해요" },
  { label: "답변 길이", value: "01:12" },
  { label: "침묵 상태", value: "정상" },
];

export function GuidePanel() {
  const [open, setOpen] = useState(true);

  return (
    <div className="box-border flex min-w-0 flex-[0_0_30%] flex-col overflow-y-auto rounded-2xl bg-white px-5 py-5">
      <div className="flex items-center justify-between animate-[fade-up-sm_0.45s_cubic-bezier(0.16,1,0.3,1)_both]" style={{ animationDelay: "0ms" }}>
        <span className="text-[15px] font-bold text-zinc-900">연습 코치</span>
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-1 text-xs font-medium text-ink-400 transition-colors hover:text-ink-900">
          접기
          {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {open && (
        <div className="mt-4 flex flex-col gap-4 animate-[fade-up-sm_0.45s_cubic-bezier(0.16,1,0.3,1)_both]" style={{ animationDelay: "60ms" }}>
          <div>
            <p className="mb-2 text-xs font-semibold text-ink-400">나의 화면</p>
            <div className="relative aspect-video w-full overflow-hidden rounded-xl">
              <Image src="/images/user-webcam.png" alt="내 웹캠" fill className="object-cover" />
            </div>
          </div>

          <div className="rounded-xl border border-line-200 bg-ivory-100 p-4">
            <div className="flex items-center gap-2">
              <FollowUpQuestionIcon className="size-4 text-moss-700" />
              <p className="text-xs font-bold text-ink-900">질문 의도</p>
            </div>
            <p className="mt-2 text-[13px] leading-[1.6] text-ink-600">
              문제 해결 과정과 본인의 기여도를 확인하는 질문입니다.
            </p>
          </div>

          <div className="rounded-xl border border-line-200 p-4">
            <div className="flex items-center gap-2">
              <ContentAnalysisIcon className="size-4 text-moss-700" />
              <p className="text-xs font-bold text-ink-900">답변 구조 체크</p>
            </div>
            <ul className="mt-3 flex flex-col gap-2">
              {structureChecklist.map((item) => (
                <li key={item.label} className="flex items-center gap-2 text-[13px]">
                  {item.done ? <CircleCheck size={16} className="text-moss-700" /> : <Circle size={16} className="text-line-300" />}
                  <span className={item.done ? "text-ink-900" : "text-ink-400"}>{item.label}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="rounded-xl border border-line-200 p-4">
            <div className="flex items-center gap-2">
              <SpeechAnalysisIcon className="size-4 text-moss-700" />
              <p className="text-xs font-bold text-ink-900">말하기 상태</p>
            </div>
            <ul className="mt-3 flex flex-col gap-2">
              {speechStatus.map((row) => (
                <li key={row.label} className="flex items-center gap-2 text-[13px] text-ink-600">
                  <span className="size-1.5 rounded-full bg-moss-500" />
                  {row.label}: <span className="font-medium text-ink-900">{row.value}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <p className="mb-2 flex items-center gap-2 text-xs font-bold text-ink-900">메모</p>
            <textarea
              placeholder="핵심 키워드를 기록해 보세요"
              rows={3}
              className="w-full resize-none rounded-xl border border-line-200 px-3.5 py-3 text-[13px] text-ink-900 outline-none placeholder:text-ink-300 focus:border-moss-500"
            />
          </div>
        </div>
      )}
    </div>
  );
}
