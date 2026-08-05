import { useState } from "react";
import { ArrowRight, Check, Mic, RotateCcw, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const scenarios = [
  { id: "technical", label: "기술 면접", interviewer: "기술 면접관", question: "캐시 오류를 해결할 때, 어떤 가설을 먼저 검증했나요?", cue: "원인 분리 · 판단 · 결과" },
  { id: "hr", label: "HR 면접", interviewer: "HR 면접관", question: "새로운 팀에서 가장 빠르게 기여할 수 있는 경험은 무엇인가요?", cue: "역할 · 행동 · 변화" },
] as const;

const demoWaveHeights = ["h-[1.125rem]", "h-9", "h-[3.125rem]", "h-7", "h-[3.875rem]", "h-10", "h-[4.5rem]", "h-[2.375rem]", "h-6", "h-[3.375rem]", "h-[2.625rem]", "h-[4.125rem]", "h-8", "h-12"];

export function LivePracticePreview() {
  const [scenarioId, setScenarioId] = useState<(typeof scenarios)[number]["id"]>("technical");
  const [completed, setCompleted] = useState(false);
  const scenario = scenarios.find((item) => item.id === scenarioId) ?? scenarios[0];

  const selectScenario = (id: (typeof scenarios)[number]["id"]) => {
    setScenarioId(id);
    setCompleted(false);
  };

  return (
    <section id="live-preview" className="bg-[#10251d] px-5 py-20 text-white md:px-8 lg:px-12 lg:py-28">
      <ScrollReveal className="mx-auto max-w-[1280px]">
        <div className="grid gap-10 lg:grid-cols-[.72fr_1.28fr] lg:gap-20">
          <div>
            <p className="text-sm font-medium text-[#f2ab72]">외운 문장보다, 내 경험의 흐름을.</p>
            <h2 className="mt-5 text-[clamp(2.85rem,5vw,5.4rem)] font-semibold leading-[.99] tracking-[-.04em]">
              외운 답변을<br />실제 대화로<br />바꿉니다.
            </h2>
            <p className="mt-7 max-w-[36ch] text-lg leading-8 text-white/65">이력서와 공고의 맥락으로 질문을 받고, 답변을 마친 뒤 다음 성장 과제를 확인합니다.</p>
            <Link to="/consent" className="group mt-8 inline-flex min-h-12 items-center gap-2 border-b border-[#f2ab72] text-sm font-semibold text-white transition hover:text-[#f2ab72] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">면접 화면 미리보기 <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" /></Link>
          </div>

          <div className="overflow-hidden border border-white/15 bg-[#0a1712] shadow-[0_28px_80px_rgba(0,0,0,.22)]">
            <div className="flex items-center justify-between border-b border-white/10 px-5 py-4 md:px-6"><div className="flex gap-2" role="tablist" aria-label="면접 시나리오 선택">{scenarios.map((item) => <button key={item.id} type="button" role="tab" aria-selected={scenarioId === item.id} onClick={() => selectScenario(item.id)} className={`min-h-9 px-3 text-xs font-semibold transition ${scenarioId === item.id ? "bg-[#d96d25] text-white" : "text-white/50 hover:text-white"}`}>{item.label}</button>)}</div><span className="text-xs font-medium text-white/45">QUESTION 03 / 05</span></div>
            <div className="grid min-h-[390px] md:grid-cols-[.92fr_1.08fr]">
              <div key={`${scenario.id}-question`} className="relative animate-[fade-up-sm_.28s_cubic-bezier(0.16,1,0.3,1)_both] overflow-hidden border-b border-white/10 p-6 md:border-b-0 md:border-r md:p-8">
                <div aria-hidden="true" className="absolute -right-16 top-10 size-56 rounded-full border border-[#b4d3bd]/15" />
                <div aria-hidden="true" className="absolute -right-4 top-20 size-36 rounded-full border border-dashed border-[#f2ab72]/20" />
                <div className="relative"><p className="text-xs font-medium tracking-[.12em] text-[#b4d3bd]">{scenario.interviewer.toUpperCase()}</p><div className="mt-10 grid size-16 place-items-center rounded-full border border-[#b4d3bd]/30 bg-[#17382c] text-[#f2ab72]"><Mic className="size-6" /></div><p className="mt-7 max-w-[21ch] text-xl font-medium leading-8">{scenario.question}</p><p className="mt-7 border-l-2 border-[#d96d25] pl-4 text-sm leading-6 text-white/55">답변에서 확인할 구조<br /><strong className="font-medium text-white/85">{scenario.cue}</strong></p></div>
              </div>
              <div className="flex flex-col p-6 md:p-8"><div className="flex items-center justify-between"><p className="text-xs font-medium tracking-[.12em] text-[#b4d3bd]">YOUR RESPONSE</p><span className="text-sm font-semibold text-[#f2ab72]">00:28</span></div><div className="mt-8 flex flex-1 flex-col justify-center"><div className="flex h-16 items-center gap-1.5" aria-label="답변 음성 파형">{demoWaveHeights.map((height, index) => <span key={index} className={`demo-wave demo-wave--${index % 4} w-1.5 bg-[#f2ab72] ${height}`} />)}</div><p className="mt-7 max-w-[37ch] text-base leading-7 text-white/70">“캐시 키를 먼저 분리해 확인했고, 재현 조건을 좁힌 뒤 API 응답과 무효화 시점을 함께 수정했습니다.”</p></div>{completed ? <div className="mt-6 border border-[#b4d3bd]/25 bg-[#17382c] p-4"><div className="flex items-center gap-2 text-sm font-semibold text-[#d8f0df]"><Check className="size-4" />답변을 저장했습니다.</div><p className="mt-2 text-sm leading-6 text-white/62">분석이 끝나면 ‘판단’과 ‘결과’를 보강할 성장 과제를 제안합니다.</p><button type="button" onClick={() => setCompleted(false)} className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-[#f2ab72] hover:text-white"><RotateCcw className="size-3.5" />다시 답변하기</button></div> : <button type="button" onClick={() => setCompleted(true)} className="mt-6 inline-flex min-h-12 items-center justify-center gap-2 bg-[#d96d25] px-5 text-sm font-semibold transition hover:bg-[#ef8036] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"><Check className="size-4" />답변을 마쳤어요</button>}</div>
            </div>
          </div>
        </div>
        <div className="mt-8 grid gap-px border border-white/12 bg-white/12 md:grid-cols-3"><p className="bg-[#10251d] p-5 text-sm leading-6 text-white/65"><strong className="block text-white">채용 평가가 아닙니다.</strong>Face Fit은 합격 가능성을 판단하지 않는 연습용 코칭 도구입니다.</p><p className="bg-[#10251d] p-5 text-sm leading-6 text-white/65"><strong className="block text-white">점수보다 근거를 봅니다.</strong>각 신호는 관찰 근거와 성장 과제로 이어집니다.</p><p className="bg-[#10251d] p-5 text-sm leading-6 text-white/65"><strong className="flex items-center gap-2 text-white"><ShieldCheck className="size-4 text-[#f2ab72]" />현재는 화면 데모입니다.</strong>이 데모에서는 영상·음성 저장 또는 복제를 수행하지 않습니다.</p></div>
      </ScrollReveal>
    </section>
  );
}
