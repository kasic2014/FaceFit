import { useState } from "react";
import { Check } from "lucide-react";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

type Plan = {
  name: string;
  summary: string;
  price: string;
  period: string;
  benefits: string[];
  cta: "이용 안내" | "현재 준비 중";
  recommended?: boolean;
};

const plans: Plan[] = [
  {
    name: "Free",
    summary: "기본 면접 체험",
    price: "0원",
    period: "무료 체험",
    benefits: ["기본 모의면접 1회", "핵심 피드백 요약", "면접 환경 점검"],
    cta: "이용 안내",
  },
  {
    name: "Standard",
    summary: "월간 면접 및 상세 리포트",
    price: "19,900원",
    period: "월간 콘셉트",
    benefits: ["월간 모의면접 5회", "질문별 상세 리포트", "개선 답변 다시 듣기"],
    cta: "현재 준비 중",
    recommended: true,
  },
  {
    name: "Pro",
    summary: "추가 면접 및 성장 분석",
    price: "39,900원",
    period: "월간 콘셉트",
    benefits: ["월간 모의면접 12회", "면접 기록 성장 분석", "집중 연습 가이드"],
    cta: "현재 준비 중",
  },
];

export default function PricingPage() {
  const [message, setMessage] = useState("");

  const showNotice = (plan: Plan) => {
    setMessage(`${plan.name} 플랜은 발표용 콘셉트입니다. 실제 결제는 진행되지 않습니다.`);
  };

  return (
    <div className="min-h-screen bg-ivory-50 text-ink-900">
      <AppNav active="요금제" />
      <PageContainer as="main" size="standard" className="py-12 md:py-16">
        <header className="mx-auto max-w-[720px] text-center">
          <p className="text-sm font-bold text-moss-700">FACE FIT PLANS</p>
          <h1 className="mt-3 text-3xl font-bold tracking-[-.03em] md:text-4xl">연습 목표에 맞는 플랜을 확인해 보세요.</h1>
          <p className="mt-4 text-sm leading-7 text-ink-600 md:text-base">
            면접 경험과 리포트 범위를 비교할 수 있도록 구성한 발표용 요금제입니다.
          </p>
        </header>

        <section className="mt-10 grid grid-cols-1 gap-5 lg:grid-cols-3" aria-label="Face Fit 요금제">
          {plans.map((plan) => (
            <article
              key={plan.name}
              className={plan.recommended
                ? "relative flex min-w-0 flex-col rounded-2xl border-2 border-moss-700 bg-white p-6"
                : "relative flex min-w-0 flex-col rounded-2xl border border-line-300 bg-white p-6"}
            >
              {plan.recommended && (
                <span className="absolute top-5 right-5 rounded-full bg-moss-900 px-3 py-1 text-xs font-bold text-white">추천</span>
              )}
              <div className="pr-16">
                <h2 className="font-heading text-2xl font-bold">{plan.name}</h2>
                <p className="mt-2 break-words text-sm text-ink-600">{plan.summary}</p>
              </div>
              <div className="mt-7 border-b border-line-200 pb-6">
                <strong className="text-3xl font-bold tracking-[-.03em]">{plan.price}</strong>
                <span className="ml-2 text-xs text-ink-400">{plan.period}</span>
              </div>
              <ul className="mt-6 flex-1 space-y-3">
                {plan.benefits.map((benefit) => (
                  <li key={benefit} className="flex items-start gap-2.5 text-sm leading-6 text-ink-700">
                    <span className={plan.recommended ? "mt-1 grid size-5 shrink-0 place-items-center rounded-full bg-moss-900 text-white" : "mt-1 grid size-5 shrink-0 place-items-center rounded-full bg-ivory-300 text-ink-600"}>
                      <Check size={12} />
                    </span>
                    <span className="min-w-0 break-words">{benefit}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={() => showNotice(plan)}
                className={plan.recommended
                  ? "mt-8 w-full rounded-xl bg-moss-900 px-5 py-3.5 text-sm font-bold text-white transition hover:bg-moss-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-moss-700"
                  : "mt-8 w-full rounded-xl border border-line-300 px-5 py-3.5 text-sm font-bold text-ink-700 transition hover:bg-ivory-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink-600"}
              >
                {plan.cta}
              </button>
            </article>
          ))}
        </section>

        <div className="mx-auto mt-8 max-w-[720px] text-center">
          {message && <p role="status" className="mb-4 rounded-xl border border-moss-300 bg-white px-4 py-3 text-sm text-moss-900">{message}</p>}
          <p className="text-xs leading-5 text-ink-400">요금제 페이지는 서비스 콘셉트 화면이며 실제 결제 기능은 제공하지 않습니다.</p>
        </div>
      </PageContainer>
    </div>
  );
}
