import { ArrowLeft, ArrowRight, CheckCircle2 } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { findPrototypeRecord } from "@/lib/prototype-records";

export default function RecordDetailPage() {
  const { recordId = "" } = useParams();
  const record = findPrototypeRecord(recordId);
  if (!record) return <div className="min-h-screen bg-ivory-50"><AppNav active="마이페이지" /><PageContainer as="main" size="narrow" className="py-20"><h1 className="text-2xl font-bold">기록을 찾을 수 없어요.</h1><Link to="/dashboard" className="mt-6 inline-flex rounded-xl bg-moss-900 px-5 py-3 text-sm font-bold text-white">기록으로 돌아가기</Link></PageContainer></div>;

  return <div className="min-h-screen bg-[#f7f6f1] text-ink-900"><AppNav active="마이페이지" /><PageContainer as="main" size="wide" className="py-10">
    <Link to="/dashboard" className="inline-flex items-center gap-1.5 text-sm font-semibold text-ink-600 hover:text-moss-900"><ArrowLeft size={16} />면접 기록으로 돌아가기</Link>
    <header className="mt-7 flex flex-wrap items-end justify-between gap-5"><div><p className="text-sm font-bold text-sunset-700">INTERVIEW RECORD / SAMPLE</p><h1 className="mt-2 text-3xl font-bold tracking-[-.05em]">{record.company} · {record.role}</h1><p className="mt-2 text-sm text-ink-600">{record.date} · {record.interviewer}</p></div><div className="rounded-2xl bg-moss-900 px-6 py-4 text-center text-white"><p className="text-xs text-white/70">종합 분석 점수</p><strong className="mt-1 block text-3xl">{record.score}<small className="ml-1 text-sm">점</small></strong></div></header>
    <section className="mt-7 rounded-2xl border border-moss-300 bg-[#edf4ef] p-6"><h2 className="text-sm font-bold text-moss-900">이번 기록의 요약</h2><p className="mt-3 max-w-[70ch] text-sm leading-7 text-ink-700">{record.summary}</p></section>
    <section className="mt-7"><div className="flex items-baseline justify-between"><h2 className="text-xl font-bold">질문과 분석 근거</h2><p className="text-sm text-ink-500">점수는 관찰을 요약한 참고값입니다.</p></div><div className="mt-4 space-y-4">{record.questions.map((item, index) => <article key={item.question} className="rounded-2xl border border-line-200 bg-white p-6"><div className="flex flex-wrap items-center justify-between gap-3"><p className="text-sm font-bold text-moss-700">QUESTION {String(index + 1).padStart(2, "0")}</p><span className="rounded-full bg-ivory-100 px-3 py-1 text-xs font-bold text-ink-700">관찰 점수 {item.score}/100</span></div><h3 className="mt-4 max-w-[70ch] text-lg font-bold leading-7">{item.question}</h3><div className="mt-5 grid gap-4 border-t border-line-200 pt-5 lg:grid-cols-2"><div><p className="text-xs font-bold text-ink-500">답변 요약</p><p className="mt-2 text-sm leading-6 text-ink-700">{item.answer}</p></div><div><p className="text-xs font-bold text-ink-500">분석 근거</p><p className="mt-2 text-sm leading-6 text-ink-700">{item.evidence}</p></div></div></article>)}</div></section>
    <section className="mt-7 grid gap-6 rounded-[22px] bg-[#10251d] p-7 text-white lg:grid-cols-[1fr_auto] lg:items-end"><div><p className="text-sm font-bold text-[#f2ab72]">선택된 성장 과제</p><h2 className="mt-3 max-w-[24ch] text-2xl font-bold leading-8">{record.growthTask.title}</h2><p className="mt-4 max-w-[65ch] text-sm leading-7 text-white/70">{record.growthTask.reason} {record.growthTask.practice}</p></div><Link to="/onboarding" className="inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-sunset-600 px-5 text-sm font-bold text-white hover:bg-sunset-700">이 성장 과제로 재연습하기 <ArrowRight size={16} /></Link></section>
    <p className="mt-5 flex items-center gap-2 text-xs text-ink-500"><CheckCircle2 size={14} className="text-moss-700" />이 기록은 프로토타입 흐름을 위한 샘플이며 실제 채용 평가가 아닙니다.</p>
  </PageContainer></div>;
}
