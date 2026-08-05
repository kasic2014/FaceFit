import { Pause, Play } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { latestRecord } from "@/lib/prototype-records";

const axes = [
  { label: "시선 유지", score: 80, evidence: "카메라 응시 58% · 권장 75%", task: "답변 시작 10초 동안 카메라 보기" },
  { label: "발화 안정", score: 70, evidence: "불필요한 멈춤 14회", task: "문장 끝까지 말한 뒤 한 번 쉬기" },
  { label: "자세", score: 75, evidence: "상체 흔들림 5회 감지", task: "어깨를 고정하고 답하기" },
  { label: "답변 내용", score: 88, evidence: "STAR 구조 4/5 문항", task: "결론을 먼저 말하기" },
] as const;

type Tab = "종합 리포트" | "질문별 근거" | "성장 과제";
const tabs: Tab[] = ["종합 리포트", "질문별 근거", "성장 과제"];

export default function ReportPage() {
  const [tab, setTab] = useState<Tab>("종합 리포트");
  const [playing, setPlaying] = useState(false);
  return <div className="min-h-screen bg-[#f7f6f1] text-ink-900"><AppNav active="마이페이지" />
    <PageContainer as="main" size="wide" className="py-10">
      <p className="text-xs text-ink-500">샘플 · {latestRecord.date} · {latestRecord.company} {latestRecord.role}</p>
      <h1 className="mt-3 text-3xl font-bold tracking-[-.055em]">답변의 근거를 보고,<br className="sm:hidden" /> 다음 성장 과제를 고릅니다.</h1>
      <p className="mt-3 max-w-[64ch] text-sm leading-6 text-ink-600">이 리포트는 채용 평가가 아닙니다. 이번 답변에서 관찰한 신호를 바탕으로 다음 재연습의 우선순위를 제안합니다.</p>
      <div className="mt-7 flex gap-1 overflow-x-auto border-b border-line-200" role="tablist" aria-label="리포트 구분">{tabs.map((item) => <button key={item} type="button" role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={tab === item ? "shrink-0 border-b-2 border-moss-900 px-4 py-3 text-sm font-bold text-moss-900" : "shrink-0 px-4 py-3 text-sm text-ink-600 hover:text-ink-900"}>{item}</button>)}</div>
      {tab === "종합 리포트" && <Overview playing={playing} onToggle={() => setPlaying((value) => !value)} />}
      {tab === "질문별 근거" && <QuestionEvidence />}
      {tab === "성장 과제" && <GrowthTasks />}
    </PageContainer></div>;
}

function Overview({ playing, onToggle }: { playing: boolean; onToggle: () => void }) {
  return <><section className="mt-7 rounded-[22px] bg-[#10251d] px-7 py-8 text-white md:flex md:items-center md:gap-9 md:px-11"><div className="grid size-28 shrink-0 place-items-center rounded-full border-[8px] border-[#b4d3bd] text-center"><strong className="text-4xl leading-none">{latestRecord.score}<small className="text-sm">점</small></strong><span className="mt-1 text-xs text-white/70">관찰 점수</span></div><div className="mt-5 max-w-4xl md:mt-0"><p className="text-sm font-bold text-[#f2ab72]">이번 답변에서 확인한 강점</p><p className="mt-3 text-lg font-semibold leading-8">문제를 재현하고 원인을 좁혀 가는 과정이 명확했습니다. 다음 답변에서는 결론을 먼저 전달해, 같은 판단 근거가 더 빠르게 이해되도록 해보세요.</p></div></section><section className="mt-7 grid gap-4 md:grid-cols-2">{axes.map((axis) => <article key={axis.label} className="rounded-2xl border border-line-200 bg-white p-6"><div className="flex items-center justify-between gap-3"><h2 className="font-bold">{axis.label}</h2><strong className="text-lg text-moss-900">{axis.score}<small className="text-xs">/100</small></strong></div><div className="mt-4 h-2 overflow-hidden rounded-full bg-ivory-200" aria-label={`${axis.label} ${axis.score}점`}><div className="h-full rounded-full bg-moss-700" style={{ width: `${axis.score}%` }} /></div><p className="mt-4 text-sm leading-6 text-ink-600">관찰 근거: {axis.evidence}</p><p className="mt-2 text-sm font-semibold text-moss-900">성장 과제: {axis.task}</p></article>)}</section><section className="mt-7 grid gap-5 md:grid-cols-2"><article className="rounded-2xl border border-line-200 bg-white p-7"><p className="text-sm font-bold text-moss-700">개선 답변 · 표준 음성</p><h2 className="mt-3 text-xl font-bold">개선 답변을 듣고 다시 연습해 보세요</h2><p className="mt-2 text-sm leading-6 text-ink-600">음성 재생은 화면 데모입니다. 개인화 음성은 정식 기능이 아닙니다.</p><button type="button" onClick={onToggle} aria-pressed={playing} className="mt-5 flex w-full items-center gap-3 rounded-full border border-line-300 bg-ivory-100 px-4 py-3 text-left"><span className="grid size-8 place-items-center rounded-full bg-moss-900 text-white">{playing ? <Pause size={15} /> : <Play size={15} fill="currentColor" />}</span><span className="h-1 flex-1 rounded-full bg-moss-300"><i className="block h-full w-[32%] rounded-full bg-sunset-600" /></span><span className="text-xs text-ink-600">0:14 / 0:44</span></button></article><GrowthTaskCard /></section></>;
}

function QuestionEvidence() { return <section className="mt-7 space-y-4">{latestRecord.questions.map((question, index) => <article key={question.question} className="rounded-2xl border border-line-200 bg-white p-7"><div className="flex items-center justify-between gap-4"><p className="text-sm font-bold text-sunset-700">QUESTION {String(index + 1).padStart(2, "0")}</p><strong className="text-sm text-moss-900">{question.score}/100</strong></div><h2 className="mt-4 text-lg font-bold leading-7">{question.question}</h2><p className="mt-5 border-l-2 border-moss-500 pl-4 text-sm leading-7 text-ink-700">분석 근거: {question.evidence}</p><Link to={`/records/${latestRecord.id}`} className="mt-5 inline-flex text-sm font-bold text-moss-700 underline underline-offset-4">전체 답변 기록 보기</Link></article>)}</section>; }

function GrowthTasks() { return <section className="mt-7"><GrowthTaskCard /><div className="mt-5 rounded-2xl border border-line-200 bg-white p-6"><h2 className="font-bold">재연습 순서</h2><ol className="mt-4 grid gap-3 text-sm leading-6 text-ink-700 md:grid-cols-3"><li><b className="text-moss-900">1. 결론</b>을 첫 문장에 말합니다.</li><li><b className="text-moss-900">2. 근거</b>를 상황·판단·결과로 정리합니다.</li><li><b className="text-moss-900">3. 재연습</b> 후 같은 기준으로 확인합니다.</li></ol></div></section>; }

function GrowthTaskCard() { return <article className="rounded-2xl bg-[#edf4ef] p-7"><p className="text-sm font-bold text-sunset-700">선택된 성장 과제</p><h2 className="mt-3 text-xl font-bold leading-8">결론을 먼저 말하고, 판단 근거를 30초 안에 정리하기</h2><p className="mt-3 text-sm leading-7 text-ink-700">답변 내용은 충분했지만 핵심 결론이 뒤에 나왔습니다. 다음 면접에서는 결론·판단·결과 순서로 다시 답해보세요.</p><Link to="/onboarding" className="mt-6 inline-flex min-h-11 items-center rounded-xl bg-moss-900 px-5 text-sm font-bold text-white">이 성장 과제로 재연습하기</Link></article>; }
