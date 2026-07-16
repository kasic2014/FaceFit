"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronDown, Eye, MessageSquare, Plus, TrendingUp } from "lucide-react";
import { useState, type ReactNode } from "react";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type InterviewStatus = "analyzing" | "complete";

type InterviewRecord = {
  company: string;
  role: string;
  meta: string;
  score?: string;
  status: InterviewStatus;
};

// TODO: Replace this mock status with persisted analysis status from the API.
const interviews: InterviewRecord[] = [
  { company: "Face Fit 면접", role: "백엔드 개발자", meta: "기술 면접관 · 일반 · 방금 전", status: "analyzing" },
  { company: "네이버 (NAVER)", role: "백엔드 개발자", meta: "기술 면접관 · 일반 · 2026.07.10", score: "78", status: "complete" },
  { company: "카카오 (KAKAO)", role: "AI 엔지니어", meta: "HR 면접관 · 일반 · 2026.07.05", score: "72", status: "complete" },
  { company: "삼성전자 (SAMSUNG)", role: "소프트웨어 개발자", meta: "기술 면접관 · 압박 · 2026.06.28", score: "65", status: "complete" },
  { company: "LG전자 (LG)", role: "SW 개발자", meta: "HR 면접관 · 일반 · 2026.06.20", score: "61", status: "complete" },
  { company: "현대자동차 (HYUNDAI)", role: "백엔드 개발자", meta: "기술 면접관 · 압박 · 2026.06.12", score: "58", status: "complete" },
];

export default function DashboardPage() {
  const [tab, setTab] = useState("요약");
  return <div className="min-h-screen bg-[#f6f4ee] text-[#1f2220]"><AppNav active="마이페이지" />
    <PageContainer as="main" size="standard" className="py-10">
      <header className="flex flex-wrap items-start justify-between gap-5"><div><h1 className="text-3xl font-bold tracking-[-.055em]">마이페이지</h1><p className="mt-2 text-sm text-ink-600">면접 기록과 성장 변화를 한눈에 확인하세요.</p></div><Link href="/onboarding" className="inline-flex items-center gap-2 rounded-xl bg-sunset-600 px-5 py-3 text-sm font-bold text-white"><Plus size={16}/>새 면접 시작</Link></header>
      <div className="mt-6 inline-flex rounded-xl border border-line-300 bg-white p-1" role="tablist">{["요약", "면접 기록", "성장 분석"].map((item) => <button key={item} onClick={() => setTab(item)} className={tab === item ? "rounded-lg bg-moss-900 px-4 py-2.5 text-sm font-bold text-white" : "px-4 py-2.5 text-sm font-medium text-ink-600"}>{item}</button>)}</div>
      {tab === "요약" ? <Summary onViewRecords={() => setTab("면접 기록")} /> : tab === "면접 기록" ? <InterviewList /> : <Growth />}
    </PageContainer>
  </div>;
}

function Summary({ onViewRecords }: { onViewRecords: () => void }) { return <div className="mt-7 grid gap-5 lg:grid-cols-[1.65fr_1fr]"><div className="space-y-5"><LatestResult/><Growth compact/><Practice/></div><aside className="space-y-5"><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-1"><Tip title="가장 개선된 항목" icon={<TrendingUp size={17}/>} tint="bg-[#edf6f0] border-[#c9dfd0]" value="답변 내용 +8점" note="이전 대비"/><Tip title="우선 개선할 항목" icon={<Eye size={17}/>} tint="bg-[#fff0e7] border-[#f6c6aa]" value="시선 유지" note="집중 연습이 필요해요"/></div><InterviewList onViewRecords={onViewRecords}/></aside></div>; }

function LatestResult() { return <section className="rounded-2xl border border-line-300 bg-white p-6"><h2 className="text-sm font-bold">최근 면접 결과</h2><div className="mt-6 grid items-center gap-5 sm:grid-cols-[1.3fr_.55fr_.8fr_.9fr]"><div className="min-w-0"><b className="block truncate text-sm">네이버 (NAVER)</b><p className="mt-1 text-xs text-ink-600">백엔드 개발자</p><p className="truncate text-xs text-ink-400">기술 면접관 · 일반 · 2026.07.10</p></div><div className="text-center"><p className="text-xs text-ink-600">종합 점수</p><strong className="text-5xl leading-none text-moss-900">78<small className="text-base">점</small></strong><p className="mt-2 text-xs font-bold text-moss-700">▲ 6점</p><p className="text-[10px] text-ink-400">이전 면접(72점) 대비</p></div><p className="rounded-xl bg-[#f7f6f1] p-4 text-sm leading-6">논리적인 답변 구조는 좋았지만, 카메라 시선 유지와 결론 전달이 부족했어요.</p><div className="grid gap-2"><Link href="/report" className="rounded-xl border border-line-300 px-4 py-3 text-center text-sm font-bold">리포트 보기</Link><Link href="/onboarding" className="rounded-xl bg-moss-900 px-4 py-3 text-center text-sm font-bold text-white">같은 조건으로 다시 면접</Link></div></div></section>; }

function Tip({title, icon, tint, value, note}:{title:string;icon:ReactNode;tint:string;value:string;note:string}) { return <section className={`rounded-2xl border p-4 ${tint}`}><div className="flex justify-between text-sm font-bold"><span>{title}</span>{icon}</div><div className="mt-4 flex items-center gap-3"><span className="grid size-9 place-items-center rounded-full bg-white">{icon}</span><div><b className="text-sm">{value}</b><p className="text-xs text-ink-600">{note}</p></div></div></section>; }

function PracticeCard({icon, title, text}:{icon:ReactNode;title:string;text:string}) { return <article className="rounded-xl border border-line-300 bg-white p-4"><span className="grid size-8 place-items-center rounded-full bg-ivory-100 text-moss-900">{icon}</span><b className="mt-4 block text-sm">{title}</b><p className="mt-2 text-xs leading-5 text-ink-600">{text}</p><span className="mt-4 inline-block rounded-full bg-[#f6f4ee] px-2 py-1 text-[10px]">5분</span></article>; }
function Practice() { return <section className="rounded-2xl bg-[#f6f0e4] p-6"><h2 className="font-bold">이번 주 추천 연습</h2><p className="mt-2 text-sm text-ink-600">우선 개선 항목을 중심으로 연습해 보세요.</p><div className="mt-5 grid gap-3 sm:grid-cols-4"><PracticeCard icon={<Eye size={15}/>} title="시선 유지 연습" text="카메라를 자연스럽게 바라보는 연습"/><PracticeCard icon={<MessageSquare size={15}/>} title="결론 먼저 말하기" text="답변의 첫 문장에서 핵심 전달"/><PracticeCard icon="#" title="구체적 수치 표현" text="성과를 숫자로 설명하는 연습"/><Link href="/onboarding" className="grid min-h-40 place-items-center rounded-xl bg-sunset-600 p-4 text-center text-sm font-bold text-white">연습 시작하기 →</Link></div></section>; }

function InterviewList({ onViewRecords }: { onViewRecords?: () => void }) {
  return (
    <section className="rounded-2xl border border-line-300 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold">최근 면접 기록</h2>
        {onViewRecords && <button type="button" onClick={onViewRecords} className="min-h-11 text-sm font-bold text-moss-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-moss-700">전체 면접 기록 보기</button>}
      </div>
      <div className="mt-4 space-y-3">
        {interviews.map((interview) => (
          <article key={interview.company} className="flex min-w-0 flex-col items-stretch gap-3 rounded-xl border border-line-200 px-3 py-3 sm:flex-row sm:items-center">
            <div className="min-w-0 flex-1">
              <b className="block truncate text-sm">{interview.company}</b>
              <p className="text-xs text-ink-600">{interview.role}</p>
              <p className="truncate text-[10px] text-ink-400">{interview.meta}</p>
              {interview.status === "analyzing" && <span className="mt-1 inline-flex rounded-full bg-moss-300/35 px-2 py-0.5 text-[10px] font-bold text-moss-900">분석 중</span>}
            </div>
            {interview.status === "analyzing"
              ? <div className="shrink-0 text-right"><p className="text-xs font-bold text-moss-700">분석 중</p><p className="mt-1 max-w-20 text-[10px] leading-4 text-ink-400">리포트를 생성하고 있어요</p></div>
              : <strong className="shrink-0 text-xl">{interview.score}<small className="text-xs font-medium">점</small></strong>}
            <div className="grid shrink-0 gap-1 sm:ml-auto">
              {interview.status === "complete" && <Link href="/report" className="rounded-lg border border-line-300 px-2 py-1 text-center text-xs font-bold">리포트 보기</Link>}
              <Link href="/onboarding" className="rounded-lg border border-line-300 px-2 py-1 text-center text-xs font-bold">다시 면접</Link>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
function Growth({compact=false}:{compact?:boolean}) { return <section className={compact ? "rounded-2xl border border-line-300 bg-white p-6" : "mt-7 rounded-2xl border border-line-300 bg-white p-7"}><div className="flex items-start justify-between"><div><h2 className="font-bold">성장 추이 (최근 5회)</h2><p className="mt-1 text-sm text-ink-600">면접 실력의 변화를 확인해 보세요.</p></div><button className="flex items-center gap-1 rounded-lg border border-line-300 px-3 py-2 text-xs">전체 <ChevronDown size={12}/></button></div><div className={compact ? "mt-5 grid gap-5 md:grid-cols-[1.55fr_.95fr]" : "mt-7"}><ScoreGraph />{compact && <div className="rounded-xl bg-[#f7f6f1] p-5"><p className="text-sm font-semibold leading-7"><ArrowUpRight className="mr-2 inline text-moss-700" size={16}/>답변 내용은 꾸준히 상승하고 있어요.</p><p className="mt-3 text-sm leading-7">시선 점수는 최근 3회 동안 큰 변화가 없어요.</p></div>}</div></section>; }
function ScoreGraph() { const points="24,95 105,82 185,76 265,65 345,49"; return <svg viewBox="0 0 380 145" className="w-full" aria-label="최근 5회 면접 점수 추이"><g stroke="#e7e3dc">{[25,52,79,106].map(y=><line key={y} x1="22" x2="365" y1={y} y2={y}/>)}</g><polyline points={points} fill="none" stroke="#33583f" strokeWidth="2"/>{points.split(" ").map((point, i)=>{const [cx,cy]=point.split(","); return <g key={point}><circle cx={cx} cy={cy} r="3.5" fill="white" stroke="#33583f" strokeWidth="2"/><text x={cx} y={Number(cy)-10} textAnchor="middle" fontSize="10" fill="#33583f">{[58,64,68,72,78][i]}</text><text x={cx} y="137" textAnchor="middle" fontSize="9" fill="#817e77">{["06.12","06.19","06.26","07.05","07.10"][i]}</text></g>})}</svg>; }
