import { useRef, useState, type PointerEvent } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ArrowRight, Eye, MessageSquareText, ScanFace, Sparkles } from "lucide-react";
import { Link } from "react-router";
import { Footer } from "@/components/facefit/Footer";
import { LandingHeader } from "@/components/facefit/LandingHeader";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";
import { DeveloperJobStory } from "@/components/facefit/landing/DeveloperJobStory";
import { EvidenceRetrievalSection } from "@/components/facefit/landing/EvidenceRetrievalSection";
import { LivePracticePreview } from "@/components/facefit/landing/LivePracticePreview";

gsap.registerPlugin(ScrollTrigger);

const storyStages = [
  { id: "answer", label: "답변의 순간", signal: "RESPONSE / 00:28", quote: "정확도가 떨어진 원인을 분리해, 조명 환경과 손가락 관절 값을 다시 검증했습니다.", insight: "경험은 남았지만, 결과가 빠져 있습니다." },
  { id: "evidence", label: "근거를 읽는 순간", signal: "EVIDENCE / CONTENT", quote: "문제 해결 과정은 구체적입니다. 이제 내가 만든 변화와 수치를 한 문장 더 붙일 차례입니다.", insight: "분석은 판단이 아니라 다음 답변의 근거입니다." },
  { id: "practice", label: "성장 과제가 생기는 순간", signal: "NEXT PRACTICE / 30 SEC", quote: "역할 · 행동 · 결과를 30초 안에 다시 말해보세요.", insight: "면접 한 번이 다음 성장 루프로 이어집니다." },
] as const;

const analysisAxes = [
  { icon: Eye, label: "시선", score: "74", action: "핵심 결과를 말하는 구간에서 카메라 시선을 한 번 더 유지해 보세요.", note: "핵심 결과를 말하는 구간에서 카메라 시선이 아래로 이동했습니다." },
  { icon: MessageSquareText, label: "발화", score: "81", action: "마지막 문장을 한 박자 늦춰, 결과가 또렷하게 들리도록 말해 보세요.", note: "답변 후반부가 빨라졌지만 전달력은 안정적으로 유지됐습니다." },
  { icon: ScanFace, label: "자세", score: "78", action: "기술 설명을 시작할 때 어깨와 시선을 먼저 안정시켜 보세요.", note: "기술 설명 구간에서 상체 움직임이 커졌습니다." },
  { icon: Sparkles, label: "답변 내용", score: "69", action: "역할 · 행동 · 결과를 30초 안에 다시 말해보세요.", note: "문제와 해결은 선명하지만, 본인의 판단과 결과가 빠져 있습니다." },
];

const waveformHeights = ["h-3", "h-6", "h-10", "h-5", "h-14", "h-8", "h-[4.5rem]", "h-11", "h-6", "h-12", "h-[4.25rem]", "h-7", "h-4", "h-9", "h-14", "h-6"];
const processSteps = [
  ["지원 자료 등록", "이력서와 지원 공고를 연결합니다."],
  ["실제처럼 면접", "질문에 답하고 면접을 마칩니다."],
  ["성장 과제 재연습", "분석 근거를 확인하고 다시 답합니다."],
] as const;
type HeroDirection = "center" | "top-left" | "top-right" | "bottom-left" | "bottom-right";

export default function Home() {
  const [stageId, setStageId] = useState<(typeof storyStages)[number]["id"]>("answer");
  const [activeAxis, setActiveAxis] = useState(3);
  const [heroDirection, setHeroDirection] = useState<HeroDirection>("center");
  const heroRef = useRef<HTMLElement>(null);
  const stage = storyStages.find((item) => item.id === stageId) ?? storyStages[0];
  const axis = analysisAxes[activeAxis];

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    gsap.timeline({ defaults: { ease: "power3.out" } })
      .from(".hero-kicker", { opacity: 0.5, y: 10, duration: 0.42 })
      .from(".hero-heading", { opacity: 0.58, y: 28, duration: 0.72 }, "-=0.14")
      .from(".hero-copy", { opacity: 0.55, y: 18, duration: 0.5 }, "-=0.34")
      .from(".hero-actions", { opacity: 0.62, y: 14, duration: 0.46 }, "-=0.26")
      .from(".hero-signal-card", { autoAlpha: 0, x: 22, duration: 0.56 }, "-=0.44")
      .from(".hero-panel", { autoAlpha: 0, y: 16, duration: 0.54 }, "-=0.3");
  }, { scope: heroRef });

  useGSAP(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const context = gsap.context(() => {
      gsap.fromTo(
        ".context-source",
        { y: 18, opacity: 0.72 },
        {
          y: 0,
          opacity: 1,
          duration: 0.52,
          stagger: 0.08,
          ease: "power3.out",
          scrollTrigger: { trigger: "#question-evidence", start: "top 72%", once: true },
        },
      );
      gsap.fromTo(
        ".context-question",
        { y: 16, opacity: 0.7, clipPath: "inset(0 0 18% 0)" },
        {
          y: 0,
          opacity: 1,
          clipPath: "inset(0 0 0% 0)",
          duration: 0.64,
          ease: "power3.out",
          scrollTrigger: { trigger: "#question-evidence", start: "top 62%", once: true },
        },
      );
      gsap.fromTo(
        ".report-task-panel, .report-axes",
        { y: 20, opacity: 0.78 },
        {
          y: 0,
          opacity: 1,
          duration: 0.56,
          stagger: 0.1,
          ease: "power3.out",
          scrollTrigger: { trigger: "#evidence", start: "top 68%", once: true },
        },
      );
    });
    return () => context.revert();
  });

  const updateHeroDirection = (event: PointerEvent<HTMLElement>) => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width;
    const y = (event.clientY - bounds.top) / bounds.height;
    setHeroDirection(`${y < 0.42 ? "top" : "bottom"}-${x < 0.5 ? "left" : "right"}` as HeroDirection);
  };

  return (
    <div className="landing-copy min-w-0 overflow-x-hidden bg-[#f4f5f1] text-[#12221c]">
      <a className="skip-link" href="#main-content">본문으로 건너뛰기</a>
      <LandingHeader />
      <main id="main-content">
        <section ref={heroRef} id="service" onPointerMove={updateHeroDirection} onPointerLeave={() => setHeroDirection("center")} className="relative isolate min-h-[calc(100svh-72px)] overflow-hidden bg-[#091511] px-5 py-12 text-white md:px-8 lg:px-12 lg:py-16">
          <div className={`hero-orb hero-orb--${heroDirection} absolute inset-y-0 right-0 h-full w-full md:w-[72%]`} aria-hidden="true">
            <img src="/images/facefit-coaching-orb-hero-v2.png" alt="" className={`h-full w-full object-cover object-[69%_center] opacity-[.82] ${stageId === "practice" ? "hero-orb-image--practice" : ""}`} />
          </div>
          <div aria-hidden="true" className="hero-scan absolute inset-y-0 right-0 hidden w-[72%] overflow-hidden md:block"><span /></div>
          <div aria-hidden="true" className="hero-orbit hero-orbit--outer absolute right-[9%] top-[12%] hidden size-[36rem] rounded-full border border-[#d9f0df]/15 md:block" />
          <div aria-hidden="true" className="hero-orbit hero-orbit--inner absolute right-[23%] top-[31%] hidden size-56 rounded-full border border-dashed border-[#f2ab72]/35 md:block" />
          <div aria-hidden="true" className="hero-glow absolute right-[18%] top-[21%] size-44 rounded-full bg-[#d96d25]/20 blur-3xl" />
          <div aria-hidden="true" className="hero-grain absolute inset-0" />
          <div aria-hidden="true" className="absolute inset-0 bg-[linear-gradient(90deg,#091511_0%,rgba(9,21,17,.98)_28%,rgba(9,21,17,.54)_57%,rgba(9,21,17,.18)_100%)]" />
          <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/2 bg-[linear-gradient(0deg,rgba(9,21,17,.76),transparent)]" />

          <div className="relative mx-auto flex min-h-[calc(100svh-168px)] max-w-[1440px] flex-col justify-between">
            <div className="max-w-[720px] pt-2 lg:pt-8">
              <p className="hero-kicker text-sm font-medium text-[#b4d3bd]">답변의 신호를, 성장 과제로.</p>
              <h1 className="hero-heading mt-5 text-[2.55rem] font-semibold leading-[.96] tracking-[-.04em] text-white sm:text-[clamp(3.2rem,6.4vw,6.8rem)]">
                <span className="block whitespace-nowrap">면접이 끝난 뒤,</span>
                <span className="md:hidden">성장은<br />시작됩니다.</span>
                <span className="hidden md:block md:whitespace-nowrap">성장은 시작됩니다.</span>
              </h1>
              <p className="hero-copy mt-6 max-w-[50ch] text-pretty text-base leading-8 text-white/78 md:text-lg">이력서와 지원 공고를 바탕으로 실제처럼 면접하고, 시선·발화·답변을 분석해 다음 성장 과제를 제안합니다.</p>
              <div className="hero-actions mt-8 flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:gap-x-6">
                <Link to="/onboarding" className="group inline-flex min-h-14 items-center gap-3 bg-[#d96d25] px-6 text-sm font-semibold text-white transition duration-200 hover:-translate-y-0.5 hover:bg-[#ef8036] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">첫 맞춤 면접 시작하기 <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" /></Link>
                <a href="#evidence" className="text-sm font-medium text-white/75 underline decoration-white/35 underline-offset-8 transition hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">리포트가 바꾸는 것 보기</a>
              </div>
              <p className="mt-4 text-xs leading-5 text-white/55">약 10분 · 카메라와 마이크 사용 · 면접 후 분석 리포트 제공</p>
            </div>

            <div className="hero-signal-card absolute right-5 top-[34%] hidden w-72 border border-white/20 bg-[#10251d]/72 p-5 backdrop-blur-xl lg:block" aria-live="polite">
              <div className="flex items-center justify-between text-[10px] font-semibold tracking-[.14em] text-[#b4d3bd]"><span>INTERVIEW / LIVE</span><span className="hero-signal-dot" /></div>
              <p className="mt-5 text-xs font-medium text-[#f2ab72]">QUESTION 03 / 05</p>
              <p className="mt-2 text-sm font-medium leading-6 text-white">오류를 재현한 뒤, 어떤 기준으로 원인을 분리했나요?</p>
              <div className="mt-5 flex h-9 items-center gap-1" aria-label="답변 음성 파형">{["h-3", "h-5", "h-7", "h-4", "h-8", "h-6", "h-9", "h-5", "h-7", "h-4", "h-6", "h-3"].map((height, index) => <span key={index} className={`demo-wave demo-wave--${index % 4} w-1 bg-[#f2ab72] ${height}`} />)}</div>
              <div className="mt-4 flex items-center justify-between border-t border-white/12 pt-4"><span className="text-xs text-white/55">시선 · 발화 · 답변 분석</span><span className="text-xs font-semibold text-[#b4d3bd]">분석 중</span></div>
            </div>

            <div className="hero-panel mt-12 grid gap-6 border-t border-white/15 pt-5 lg:mt-0 lg:grid-cols-[210px_minmax(0,1fr)] lg:items-end">
              <div role="tablist" aria-label="성장 루프 미리보기" className="flex gap-1.5 lg:flex-col lg:gap-0">
                {storyStages.map((item, index) => {
                  const selected = item.id === stageId;
                  return <button key={item.id} type="button" role="tab" aria-selected={selected} aria-controls="hero-story-panel" onClick={() => setStageId(item.id)} className={`min-h-10 border-b border-white/12 px-0 text-left text-xs font-medium transition duration-200 lg:py-3 ${selected ? "text-[#f2ab72]" : "text-white/45 hover:text-white/80"}`}><span className="mr-2 text-white/35">0{index + 1}</span>{item.label}</button>;
                })}
              </div>
              <div id="hero-story-panel" role="tabpanel" className="max-w-[670px] border-l border-[#d96d25] pl-5 md:pl-7">
                <div key={stage.id} className="animate-[fade-up_.42s_cubic-bezier(0.16,1,0.3,1)_both]"><p className="text-xs font-medium tracking-[.1em] text-[#f2ab72]">{stage.signal}</p><p className="mt-2 max-w-[58ch] text-base font-medium leading-7 text-white md:text-lg">“{stage.quote}”</p><p className="mt-3 text-sm text-[#b4d3bd]">{stage.insight}</p></div>
              </div>
            </div>
          </div>
        </section>

        <DeveloperJobStory />

        <EvidenceRetrievalSection />

        <LivePracticePreview />

        <section id="evidence" className="bg-[#f4f5f1] px-5 py-20 md:px-8 lg:px-12 lg:py-28">
          <div className="mx-auto max-w-[1280px]">
            <ScrollReveal className="grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:gap-20"><div><p className="text-sm font-medium text-[#c75f1d]">분석은 재연습할 이유가 되어야 합니다.</p><h2 className="mt-5 text-[clamp(3rem,5vw,5.4rem)] font-semibold leading-[.97] tracking-[-.052em]"><span className="block">면접의 기록을,</span><span className="block">성장 과제로.</span></h2></div><div className="self-end border-t border-[#12221c]/20 pt-6"><p className="max-w-[42ch] text-lg leading-8 text-[#526159]">면접에서 확인한 신호와 답변의 근거를 한 가지 성장 과제로 정리해, 재연습에서 바로 다시 답해봅니다.</p><div className="mt-9 flex items-end gap-1.5" aria-hidden="true">{waveformHeights.map((height, index) => <span key={index} className={`wave-bar w-1.5 bg-[#d96d25] ${height}`} />)}</div></div></ScrollReveal>
            <ScrollReveal delay={100} className="mt-14 lg:mt-20"><div className="grid overflow-hidden border border-[#12221c]/15 bg-[#f8faf7] lg:grid-cols-[.82fr_1.18fr]">
              <div key={axis.label} className="report-task-panel animate-[fade-up-sm_.32s_cubic-bezier(0.16,1,0.3,1)_both] bg-[#10251d] p-7 text-white md:p-10"><p className="text-sm font-medium text-[#b4d3bd]">선택된 성장 과제 · {axis.label}</p><p className="mt-7 max-w-[15ch] text-3xl font-medium leading-[1.25] tracking-[-.035em]">{axis.action}</p><p className="mt-10 border-t border-white/15 pt-5 text-sm leading-7 text-white/62">분석 근거: {axis.note}</p><Link to="/onboarding" className="mt-8 inline-flex text-sm font-semibold text-[#f2ab72] underline underline-offset-8">이 성장 과제로 재연습하기</Link></div>
              <div className="report-axes p-5 md:p-8"><div className="flex items-center justify-between border-b border-[#12221c]/15 pb-5"><div><p className="text-xs font-medium text-[#526159]">INTERVIEW REPORT / LAST SESSION</p><p className="mt-2 text-2xl font-semibold tracking-[-.025em]">성장 과제를 고르는 분석 근거</p></div><span className="text-sm text-[#526159]">4 axes</span></div><div className="mt-5 grid border-l border-t border-[#12221c]/15 sm:grid-cols-2">{analysisAxes.map((item, index) => { const Icon = item.icon; const selected = activeAxis === index; return <button key={item.label} type="button" onClick={() => setActiveAxis(index)} aria-pressed={selected} className={`min-h-52 border-b border-r border-[#12221c]/15 p-6 text-left transition duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#d96d25] ${selected ? "bg-[#d96d25] text-white" : "bg-[#f8faf7] text-[#12221c] hover:bg-white"}`}><div className="flex items-center justify-between"><Icon className="size-5" /><span className="text-base font-semibold tabular-nums">{item.score}<span className={selected ? "text-white/60" : "text-[#526159]"}>/100</span></span></div><p className="mt-10 text-xl font-semibold">{item.label}</p><p className={`mt-2 text-sm ${selected ? "text-white/75" : "text-[#526159]"}`}>분석 근거 보기</p></button>; })}</div></div>
            </div></ScrollReveal>
          </div>
        </section>

        <section id="how-it-works" className="bg-[#e2ece4] px-5 py-20 md:px-8 lg:px-12 lg:py-28"><ScrollReveal className="mx-auto max-w-[1280px]"><div className="flex flex-col justify-between gap-7 md:flex-row md:items-end"><div><p className="text-sm font-medium text-[#c75f1d]">이용 흐름</p><h2 className="mt-5 text-[clamp(3rem,5vw,5.4rem)] font-semibold leading-[.97] tracking-[-.052em]"><span className="block">준비하고,</span><span className="block">답하고, 다시 답합니다.</span></h2></div><p className="max-w-[38ch] text-lg leading-8 text-[#526159]">지원 자료 등록부터 재연습까지, 다음 면접을 위한 한 번의 흐름입니다.</p></div><ol className="mt-14 border-t border-[#12221c]/18 lg:mt-20">{processSteps.map(([title, copy], index) => <li key={title} className="group grid gap-4 border-b border-[#12221c]/18 py-6 md:grid-cols-[110px_1fr_.78fr] md:items-baseline md:gap-8"><span className="text-2xl font-semibold text-[#628b70] transition duration-300 group-hover:translate-x-1">0{index + 1}</span><h3 className="text-xl font-semibold tracking-[-.025em]">{title}</h3><p className="text-sm leading-6 text-[#526159]">{copy}</p></li>)}</ol></ScrollReveal></section>

        <section className="bg-[#164032] px-5 py-20 text-white md:px-8 lg:px-12 lg:py-28">
          <ScrollReveal className="mx-auto flex max-w-[1280px] flex-col gap-8 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-medium text-[#b4d3bd]">다음 면접을 위한 첫 연습</p>
              <h2 className="mt-5 text-[clamp(2.75rem,4.4vw,4.8rem)] font-semibold leading-[.99] tracking-[-.04em]">
                <span className="block">첫 맞춤 면접을</span>
                <span className="block">시작해보세요.</span>
              </h2>
            </div>
            <div><Link to="/onboarding" className="group inline-flex min-h-14 shrink-0 items-center gap-3 bg-[#d96d25] px-6 text-sm font-semibold text-white transition duration-200 hover:-translate-y-0.5 hover:bg-[#ef8036] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">이력서로 면접 준비하기 <ArrowRight className="size-4 transition-transform duration-200 group-hover:translate-x-1" /></Link><p className="mt-3 text-xs text-white/58">약 10분 · 카메라와 마이크 사용 · 면접 후 분석 리포트 제공</p></div>
          </ScrollReveal>
        </section>
      </main>
      <Footer />
    </div>
  );
}
