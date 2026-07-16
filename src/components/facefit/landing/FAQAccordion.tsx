"use client";
import { useState } from "react";
import { Plus } from "lucide-react";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const faqs=[
 {q:"Face Fit은 어떤 서비스인가요?",a:"AI 면접관과 실전처럼 연습하고, 음성·시선·자세·답변 내용을 분석해 맞춤 피드백을 제공하는 모의면접 서비스입니다."},
 {q:"면접 결과는 어디에서 확인하나요?",a:"면접이 끝난 뒤 생성되는 리포트와 마이페이지의 면접 기록에서 다시 확인할 수 있습니다."},
 {q:"면접 질문은 어떻게 생성되나요?",a:"업로드한 이력서와 선택한 직무·기업 정보를 바탕으로 맞춤 질문을 생성하는 흐름을 목표로 합니다."},
 {q:"분석 리포트에는 무엇이 포함되나요?",a:"발화 명확도, 속도, 시선, 자세, 답변 구조와 함께 강점·개선점·다음 연습 목표를 보여줍니다."},
 {q:"개인정보는 안전하게 보호되나요?",a:"실제 서비스 단계에서는 최소 수집, 암호화, 보관 기간 고지 등 개인정보 보호 원칙을 적용할 예정입니다."},
];

export function FAQAccordion(){const [open,setOpen]=useState<number|null>(0);return <section className="bg-[#fcfaf6] px-5 pb-28 md:px-8 lg:px-12"><div className="mx-auto grid max-w-[1200px] gap-10 lg:grid-cols-[.72fr_1.28fr] lg:gap-20">
 <ScrollReveal><div className="lg:sticky lg:top-24"><p className="text-xs font-semibold tracking-[.08em] text-sunset-700">자주 묻는 질문</p><h2 className="mt-3 text-3xl font-bold leading-tight tracking-[-.03em] text-ink-900 md:text-4xl">궁금한 내용을<br className="hidden lg:block"/> 확인해보세요</h2><p className="mt-5 max-w-[340px] text-sm leading-7 text-ink-600">서비스 이용 전 자주 확인하는 내용을 정리했습니다.</p></div></ScrollReveal>
 <ScrollReveal delay={100}><div className="border-t border-line-300">{faqs.map((f,i)=>{const on=open===i;return <div key={f.q} className="border-b border-line-300"><button onClick={()=>setOpen(on?null:i)} aria-expanded={on} className="flex min-h-16 w-full items-center justify-between gap-4 py-5 text-left text-sm font-semibold text-ink-900 transition-colors duration-200 hover:text-moss-700 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-moss-700 md:px-4 md:text-base"><span>{f.q}</span><Plus size={18} className={`shrink-0 transition-transform duration-250 ${on?"rotate-45":"rotate-0"}`}/></button><div className={`grid transition-[grid-template-rows,opacity] duration-250 ease-out ${on?"grid-rows-[1fr] opacity-100":"grid-rows-[0fr] opacity-0"}`}><div className="overflow-hidden"><p className="max-w-[720px] pb-6 text-sm leading-7 text-ink-600 md:px-4">{f.a}</p></div></div></div>})}</div></ScrollReveal>
 </div></section>}
