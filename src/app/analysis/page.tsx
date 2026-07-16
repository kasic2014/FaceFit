"use client";

import Link from "next/link";
import { RefreshCw } from "lucide-react";
import { AnalysisProgress } from "@/components/facefit/analysis/AnalysisProgress";
import { Logo } from "@/components/facefit/Logo";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { errorGuidance } from "@/lib/facefit-content";

export default function AnalysisPage() {
  const delayed = typeof window !== "undefined" && new URLSearchParams(window.location.search).get("state") === "delayed";

  return (
    <div className="min-h-screen bg-ivory-50">
      <header className="flex h-[70px] items-center justify-between border-b border-line-200 bg-white px-5 md:px-8 lg:px-12">
        <Logo size="sm" />
        <span className="text-sm font-semibold text-ink-600">결과 분석 중</span>
      </header>
      <PageContainer as="main" size="narrow" className="grid min-h-[650px] place-items-center py-12 text-center md:py-16">
        {delayed ? <Delayed /> : <AnalysisProgress />}
      </PageContainer>
    </div>
  );
}

function Delayed() {
  return (
    <section className="w-full rounded-[18px] border border-sunset-300 bg-white p-8">
      <span className="inline-flex size-11 items-center justify-center rounded-full bg-sunset-300/30 text-sunset-700">···</span>
      <h1 className="mt-5 text-2xl font-bold text-ink-900">분석에 시간이 더 필요해요</h1>
      <p className="mt-3 text-sm leading-6 text-ink-600">{errorGuidance.analysis}</p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <button type="button" className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-line-300 px-4 text-sm font-bold text-ink-700"><RefreshCw size={15} />다시 시도</button>
        <Link href="/dashboard" className="inline-flex min-h-11 items-center rounded-lg bg-moss-900 px-4 text-sm font-bold text-white">마이페이지로 이동</Link>
      </div>
    </section>
  );
}
