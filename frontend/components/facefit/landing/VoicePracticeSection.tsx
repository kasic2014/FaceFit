import { useState } from "react";
import { VoicePlaybackIcon, VoiceProfileIcon, PrivacyControlIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const WAVE = [8, 14, 22, 12, 28, 18, 34, 21, 13, 25, 17, 9, 23, 30, 16, 10, 20, 27, 15, 8, 18, 26, 14, 9];

export function VoicePracticeSection() {
  const [playing, setPlaying] = useState(false);

  return (
    <section className="bg-[#10221D] px-5 py-24 text-white md:px-8 lg:px-12">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <p className="text-xs font-semibold tracking-[.08em] text-[#83dfd1]">음성으로 다시 듣고 연습하기</p>
          <h2 className="mt-3 max-w-[640px] text-3xl font-bold leading-[1.3] tracking-[-.03em] md:text-4xl">
            첨삭된 문장을 읽고 끝내지 않고,
            <br />
            실제로 말할 수 있을 때까지 연습합니다
          </h2>
          <p className="mt-4 max-w-[560px] text-sm leading-7 text-white/60">
            개선 답변을 음성으로 들으며 실제로 말하는 장면을 상상하고, 다시 답변해 이전과 비교합니다.
          </p>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 grid gap-6 lg:grid-cols-[1.2fr_.8fr]">
            <div className="rounded-2xl border border-white/[.08] bg-[#0d1e1a] p-6 md:p-8">
              <p className="text-[11px] font-semibold text-white/40">개선 답변</p>
              <p className="mt-2 text-[16px] font-medium leading-[1.7] text-white/90">
                서버 로그를 기준으로 프론트 요청 오류와 백엔드 세션 오류를 분리해 확인했습니다. 이후 세션 키 불일치를 수정해 로그인 후 페이지 이동 문제를 해결했습니다.
              </p>

              <div className="mt-6 flex items-center gap-4 rounded-xl border border-white/[.08] bg-white/[.03] px-4 py-4">
                <button
                  onClick={() => setPlaying((v) => !v)}
                  aria-label={playing ? "재생 정지" : "표준 음성으로 듣기"}
                  className="grid size-11 shrink-0 place-items-center rounded-full bg-[#5eead4] text-[#062821] transition hover:opacity-90"
                >
                  {playing ? <span className="flex gap-1"><i className="h-3.5 w-1 rounded-full bg-[#062821]" /><i className="h-3.5 w-1 rounded-full bg-[#062821]" /></span> : <span className="ml-0.5 border-y-[7px] border-l-[11px] border-y-transparent border-l-[#062821]" />}
                </button>
                <div className="flex h-8 flex-1 items-end gap-[3px]">
                  {WAVE.map((h, i) => (
                    <span key={i} className={`w-[2.5px] rounded-full bg-[#5eead4] ${playing ? "animate-[mic-wave-" + ((i % 3) + 1) + "_1.1s_ease-in-out_infinite]" : ""}`} style={{ height: h, opacity: playing ? 1 : 0.4, animationDelay: `${i * 30}ms` }} />
                  ))}
                </div>
                <span className="text-[11px] tabular-nums text-white/40">0:00 / 0:18</span>
              </div>

              <div className="mt-4 flex flex-wrap gap-3">
                <button onClick={() => setPlaying((v) => !v)} className="flex items-center gap-2 rounded-lg border border-white/15 px-4 py-2.5 text-[13px] font-medium text-white/85 transition hover:border-white/25">
                  <VoicePlaybackIcon className="size-4" /> 표준 음성으로 듣기
                </button>
                <button className="flex items-center gap-2 rounded-lg border border-white/15 px-4 py-2.5 text-[13px] font-medium text-white/50">
                  <VoiceProfileIcon className="size-4" /> 내 목소리로 듣기 <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold">Beta</span>
                </button>
                <button className="rounded-lg bg-[#557A5A] px-4 py-2.5 text-[13px] font-semibold text-white transition hover:bg-[#668c69]">
                  다시 답변하기
                </button>
              </div>
            </div>

            <div className="rounded-2xl border border-white/[.08] bg-[#0d1e1a] p-6">
              <div className="flex items-center gap-2">
                <span className="grid size-8 place-items-center rounded-full bg-white/[.06] text-[#5eead4]">
                  <PrivacyControlIcon className="size-4" />
                </span>
                <p className="text-[13px] font-bold text-white/85">개인화 음성 안내</p>
              </div>
              <p className="mt-3 text-[12.5px] leading-[1.7] text-white/50">
                내 목소리와 유사한 음성으로 개선 답변을 들어보며, 실제로 말하는 장면을 더 쉽게 상상할 수 있습니다. 아직 준비 중인 기능입니다.
              </p>
              <ul className="mt-4 space-y-2 text-[12px] text-white/40">
                <li>· 사용자 동의 후에만 생성</li>
                <li>· 개선 답변 재생 목적으로만 사용</li>
                <li>· 언제든 표준 음성으로 대체 가능</li>
                <li>· 음성 프로필 삭제 가능</li>
                <li>· 다른 목적으로 사용하지 않음</li>
              </ul>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
