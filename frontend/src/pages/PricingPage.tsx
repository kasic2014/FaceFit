import { BellRing, Check } from "lucide-react";
import { useState } from "react";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type BetaPlan = { name: string; summary: string; price: string; benefits: readonly string[]; featured?: boolean };

const plans: readonly BetaPlan[] = [
  { name: "Free", summary: "기본 면접 연습", price: "무료", benefits: ["모의 면접 1회", "답변 요약", "장비 환경 확인"] },
  { name: "Standard", summary: "질문별 분석과 성장 과제", price: "출시 준비 중", benefits: ["월간 모의 면접", "질문별 분석 근거", "성장 과제 재연습"], featured: true },
  { name: "Pro", summary: "집중 연습과 기록 비교", price: "출시 준비 중", benefits: ["추가 면접 횟수", "면접 기록 비교", "집중 재연습 가이드"] },
] as const;

export default function PricingPage() {
  const [message, setMessage] = useState("");
  return <div className="min-h-screen bg-ivory-50 text-ink-900"><AppNav active="요금제" /><PageContainer as="main" size="standard" className="py-12 md:py-16"><header className="mx-auto max-w-[720px] text-center"><p className="text-sm font-bold text-sunset-700">FACE FIT BETA</p><h1 className="mt-3 text-3xl font-bold tracking-[-.05em] md:text-4xl">요금제는 출시를 준비하고 있어요.</h1><p className="mt-4 text-sm leading-7 text-ink-600 md:text-base">현재는 기능과 흐름을 검증하는 프로토타입입니다. 실제 결제나 구독은 진행되지 않습니다.</p></header><section className="mt-10 grid gap-5 lg:grid-cols-3">{plans.map((plan) => <article key={plan.name} className={plan.featured ? "relative flex flex-col rounded-2xl border-2 border-moss-700 bg-white p-6" : "flex flex-col rounded-2xl border border-line-300 bg-white p-6"}>{plan.featured && <span className="absolute right-5 top-5 rounded-full bg-moss-900 px-3 py-1 text-xs font-bold text-white">추천 예정</span>}<h2 className="text-2xl font-bold">{plan.name}</h2><p className="mt-2 text-sm text-ink-600">{plan.summary}</p><strong className="mt-7 block border-b border-line-200 pb-6 text-2xl">{plan.price}</strong><ul className="mt-6 flex-1 space-y-3">{plan.benefits.map((benefit) => <li key={benefit} className="flex gap-2.5 text-sm leading-6 text-ink-700"><Check className="mt-1 size-4 shrink-0 text-moss-700" />{benefit}</li>)}</ul><button type="button" onClick={() => setMessage("출시 안내 요청은 현재 화면 데모로만 제공됩니다.")} className={plan.featured ? "mt-8 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl bg-moss-900 px-5 text-sm font-bold text-white hover:bg-moss-700" : "mt-8 inline-flex min-h-12 items-center justify-center gap-2 rounded-xl border border-line-300 px-5 text-sm font-bold text-ink-700 hover:bg-ivory-100"}><BellRing size={16} />출시 안내 받기</button></article>)}</section>{message && <p role="status" className="mx-auto mt-8 max-w-[720px] rounded-xl border border-moss-300 bg-white px-4 py-3 text-center text-sm text-moss-900">{message}</p>}<p className="mx-auto mt-8 max-w-[720px] text-center text-xs leading-5 text-ink-500">출시 시점과 요금, 제공 범위는 정식 서비스 정책이 확정된 뒤 안내됩니다.</p></PageContainer></div>;
}
