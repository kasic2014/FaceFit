import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { ContentAnalysisIcon } from "@/components/facefit/icons";

const WAVE = [6, 10, 15, 9, 20, 13, 28, 18, 36, 22, 14, 8, 17, 26, 34, 19, 12, 23, 31, 17, 10, 16, 25, 14, 8, 18, 29, 20, 12, 7];
const MINI_WAVE = [5, 9, 14, 8, 16, 10, 6, 12, 8, 5];

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return reduced;
}

function Waveform({ active, reduced }: { active: boolean; reduced: boolean }) {
  return (
    <div
      aria-hidden="true"
      className="absolute left-1/2 top-1/2 flex h-24 w-[340px] -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-[3px] transition-transform duration-300 [mask-image:linear-gradient(90deg,transparent,black_8%,black_92%,transparent)] md:h-32 md:w-[540px]"
      style={{ transform: `translate(-50%, -50%) scaleY(${active && !reduced ? 1.14 : 1})` }}
    >
      <span className="absolute h-px w-full bg-gradient-to-r from-transparent via-[#50dcc7]/35 to-transparent" />
      {WAVE.map((height, index) => (
        <span
          key={index}
          className={`w-[2px] origin-center rounded-full bg-[#5eead4] shadow-[0_0_9px_rgba(94,234,212,.45)] ${reduced ? "" : `animate-[mic-wave-${(index % 3) + 1}_1.15s_ease-in-out_infinite]`}`}
          style={{ height, animationDelay: `${index * 37}ms`, opacity: 0.45 + (index % 5) * 0.1 }}
        />
      ))}
    </div>
  );
}

function Robot({ x, y, active, reduced, onActive }: { x: number; y: number; active: boolean; reduced: boolean; onActive: (value: boolean) => void }) {
  const [ripple, setRipple] = useState(false);
  function react() {
    if (reduced) return;
    setRipple(false);
    requestAnimationFrame(() => setRipple(true));
    window.setTimeout(() => setRipple(false), 520);
  }
  return (
    <div
      className="relative z-10 grid place-items-center"
      onMouseEnter={() => onActive(true)}
      onMouseLeave={() => onActive(false)}
      onPointerDown={react}
    >
      <div aria-hidden="true" className="absolute size-[220px] rounded-full bg-[radial-gradient(circle,rgba(94,234,212,.2),rgba(94,234,212,.04)_40%,transparent_69%)] md:size-[320px] md:bg-[radial-gradient(circle,rgba(94,234,212,.3),rgba(94,234,212,.07)_40%,transparent_69%)]" />
      <div aria-hidden="true" className="absolute size-[174px] rounded-full border border-[#5eead4]/15 md:size-[254px]" />
      <div aria-hidden="true" className="absolute size-[210px] rounded-full border border-dashed border-white/[.09] md:size-[306px]" />
      <div aria-hidden="true" className={`absolute size-[158px] rounded-full border border-[#5eead4]/20 md:size-[230px] md:border-[#5eead4]/30 ${reduced ? "" : "animate-[pulse-ring_4s_ease-out_infinite]"}`} />
      {ripple && <div aria-hidden="true" className="robot-ripple pointer-events-none absolute size-[210px] rounded-full border border-[#7A9B7E]/45 md:size-[280px]" />}
      <div className={reduced ? "" : "animate-[robot-breathe_5s_ease-in-out_infinite]"}>
        <div className="relative transition-transform duration-300 ease-out" style={{ transform: reduced ? undefined : `rotateX(${y * -2.5}deg) rotateY(${x * 2.5}deg)` }}>
          <div className="relative grid size-[148px] place-items-center rounded-full bg-[linear-gradient(135deg,#ffffff_0%,#eaf5f4_30%,#b8d0ce_68%,#708c8e_100%)] p-[10px] shadow-[inset_6px_7px_14px_rgba(255,255,255,.95),inset_-9px_-12px_20px_rgba(0,30,34,.28),0_20px_40px_rgba(0,0,0,.46),0_0_28px_rgba(94,234,212,.18)] md:size-[204px] md:p-[14px] md:shadow-[inset_6px_7px_14px_rgba(255,255,255,.95),inset_-9px_-12px_20px_rgba(0,30,34,.28),0_28px_58px_rgba(0,0,0,.52),0_0_48px_rgba(94,234,212,.3)]">
            <span aria-hidden="true" className="absolute -left-[12px] top-[48px] h-[52px] w-[23px] rounded-l-[16px] border border-white/50 bg-[linear-gradient(90deg,#809597,#e7f2f1)] shadow-[-6px_4px_14px_rgba(0,0,0,.28)] md:-left-[17px] md:top-[66px] md:h-[72px] md:w-[32px] md:rounded-l-[20px]" />
            <span aria-hidden="true" className="absolute -right-[12px] top-[48px] h-[52px] w-[23px] rounded-r-[16px] border border-white/30 bg-[linear-gradient(90deg,#dcebea,#748b8d)] shadow-[6px_4px_14px_rgba(0,0,0,.28)] md:-right-[17px] md:top-[66px] md:h-[72px] md:w-[32px] md:rounded-r-[20px]" />
            <span aria-hidden="true" className="absolute left-8 top-3 h-2 w-16 rotate-[-8deg] rounded-full bg-white/75 blur-[1px] md:left-10 md:top-4 md:h-2.5 md:w-24" />
            <div className="relative grid size-full place-items-center overflow-hidden rounded-full border border-white/10 bg-[radial-gradient(circle_at_40%_24%,#294d51_0%,#0c1a1e_42%,#030708_100%)] shadow-[inset_0_5px_16px_rgba(0,0,0,.8),inset_0_-2px_0_rgba(94,234,212,.22)]">
              <span aria-hidden="true" className="absolute -left-5 -top-7 size-28 rounded-full bg-white/[.08] blur-lg" />
              <div className="flex flex-col items-center gap-4">
                <div className="flex gap-8">
                  {[0, 1].map((eye) => (
                    <span key={eye} className="relative size-3 transition-transform duration-200 md:size-4" style={{ transform: reduced ? undefined : `translate(${x * 4}px,${y * 4}px)` }}>
                      <span className={`absolute -inset-2 rounded-full bg-[#5eead4] blur-md transition-opacity ${active ? "opacity-55" : "opacity-30"}`} />
                      <span className={`robot-eye-idle absolute inset-0 rounded-full bg-[#7A9B7E] transition-shadow duration-300 ${active ? "shadow-[0_0_12px_rgba(122,155,126,.72)]" : "shadow-[0_0_7px_rgba(122,155,126,.58)]"}`} />
                    </span>
                  ))}
                </div>
                {active ? (
                  <div className="flex h-3 items-center gap-[2px]" aria-label="AI가 듣고 있습니다">
                    {[5, 9, 12, 8, 5].map((height, index) => <span key={index} className={`w-[2px] rounded-full bg-[#5eead4] ${reduced ? "" : "animate-[mic-wave-1_1s_ease-in-out_infinite]"}`} style={{ height, animationDelay: `${index * 80}ms` }} />)}
                  </div>
                ) : <span className="h-[3px] w-6 rounded-full bg-[#5eead4]/75" />}
              </div>
            </div>
          </div>
        </div>
      </div>
      <span className={`pointer-events-none absolute -bottom-10 whitespace-nowrap rounded-full border border-white/10 bg-black/45 px-3 py-1.5 text-[10px] font-medium text-white/70 backdrop-blur transition-opacity ${active ? "opacity-100" : "opacity-0"}`}>답변을 듣고 있어요</span>
    </div>
  );
}

const card = "rounded-2xl border border-white/[.1] bg-[#102325]/85 p-4 shadow-[inset_0_1px_0_rgba(255,255,255,.06),0_16px_40px_rgba(0,0,0,.3)] backdrop-blur-xl transition duration-300 hover:scale-[1.015] hover:border-[#5eead4]/25 hover:shadow-[0_20px_45px_rgba(0,0,0,.38)]";

function MetricCard({ title, value, note, width }: { title: string; value: string; note: string; width: string }) {
  return (
    <article className={card}>
      <p className="text-[11px] font-medium tracking-[.02em] text-white/50">{title}</p>
      <p className="mt-1 font-heading text-xl font-bold tabular-nums text-white">{value}</p>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-[#5eead4]" style={{ width }} /></div>
      <p className="mt-2 text-[10px] text-[#83dfd1]">{note}</p>
    </article>
  );
}

export function HeroDashboard() {
  const frame = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  const [pointer, setPointer] = useState({ x: 0, y: 0 });
  const [active, setActive] = useState(false);

  function move(event: ReactPointerEvent<HTMLDivElement>) {
    if (reduced || window.innerWidth < 1024 || !frame.current) return;
    const box = frame.current.getBoundingClientRect();
    setPointer({ x: Math.max(-1, Math.min(1, ((event.clientX - box.left) / box.width - 0.5) * 2)), y: Math.max(-1, Math.min(1, ((event.clientY - box.top) / box.height - 0.5) * 2)) });
  }

  return (
    <div ref={frame} onPointerMove={move} onPointerLeave={() => setPointer({ x: 0, y: 0 })} className="relative mx-auto hidden w-full max-w-[640px] md:block md:h-[520px]">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-[32px]">
        <div className="absolute inset-0 opacity-[.12] [background-image:radial-gradient(rgba(94,234,212,.7)_1px,transparent_1px)] [background-size:28px_28px] [mask-image:radial-gradient(circle_at_center,black,transparent_78%)]" />
        <svg viewBox="0 0 640 520" className="size-full opacity-10"><path d="M42 104 210 202M598 112 430 205M66 420 224 326M574 416 418 326" fill="none" stroke="#5eead4" strokeDasharray="3 6" />{[[42,104],[598,112],[66,420],[574,416],[320,28],[320,492]].map(([cx,cy]) => <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2.5" fill="#5eead4" />)}</svg>
      </div>

      <div className="absolute left-[52%] top-[48%] h-auto w-auto -translate-x-1/2 -translate-y-1/2">
        <Waveform active={active} reduced={reduced} />
        <Robot x={pointer.x} y={pointer.y} active={active} reduced={reduced} onActive={setActive} />
      </div>

      <div className="absolute left-[1%] top-[1%] w-[170px]"><MetricCard title="발화 명확도" value="92%" note="지난 연습 대비 +4" width="92%" /></div>
      <div className="absolute bottom-[9%] left-[1%] w-[170px]"><MetricCard title="말하기 속도" value="287 WPM" note="권장 범위 240–300" width="76%" /></div>

      <article className={`${card} absolute right-[0%] top-[5%] w-[210px]`}>
        <div className="flex items-center gap-2"><p className="text-[11px] font-medium text-white/50">AI 피드백</p><span className="rounded-md bg-[#5eead4]/12 px-1.5 py-0.5 text-[9px] font-semibold text-[#70dfcf]">분석 완료</span></div>
        <p className="mt-2 text-[13px] leading-relaxed text-white/85">논리적인 구조로 답변했어요. 구체적인 경험을 한 문장 더하면 설득력이 높아집니다.</p>
        <div className="mt-3 flex items-center gap-2 rounded-full border border-white/[.08] bg-white/[.04] px-2.5 py-1.5">
          <span className="flex size-5 flex-none items-center justify-center rounded-full bg-[#5eead4]">
            <span className="ml-0.5 border-y-[4px] border-l-[6px] border-y-transparent border-l-[#062821]" />
          </span>
          <div className="flex h-3 flex-1 items-end gap-[2px]">
            {MINI_WAVE.map((h, i) => <span key={i} className={`w-[2px] rounded-full bg-[#5eead4]/70 ${reduced ? "" : `animate-[mic-wave-${(i % 3) + 1}_1.1s_ease-in-out_infinite]`}`} style={{ height: h, animationDelay: `${i * 40}ms` }} />)}
          </div>
          <span className="text-[9px] tabular-nums text-white/45">0:28</span>
        </div>
      </article>

      <article className={`${card} absolute bottom-[5%] right-[0%] w-[200px]`}>
        <div className="flex items-center gap-2">
          <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#5eead4]/12 text-[#5eead4]"><ContentAnalysisIcon className="size-4" /></span>
          <p className="text-[11px] font-medium text-white/50">4축 분석</p>
        </div>
        <p className="mt-2.5 text-[13px] font-semibold leading-[1.5] text-white/90">시선 · 발화 · 자세 · 내용<br/>근거와 함께 확인해요</p>
      </article>
    </div>
  );
}
