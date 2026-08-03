export function ScoreHero() {
  const score = 85;
  const radius = 48;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - score / 100);

  return (
    <div className="mb-8 flex items-center gap-9 rounded-[20px] bg-gradient-to-br from-violet-900 via-violet-700 to-violet-700 p-8 px-10">
      <div className="relative size-28 flex-none">
        <svg width="112" height="112" viewBox="0 0 112 112" className="-rotate-90">
          <circle cx="56" cy="56" r={radius} fill="none" stroke="rgba(255,255,255,.16)" strokeWidth="9" />
          <circle
            cx="56"
            cy="56"
            r={radius}
            fill="none"
            stroke="#fff"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="font-heading text-4xl leading-none font-bold text-white">
            {score}
            <span className="font-sans text-[15px] text-white/60">점</span>
          </div>
          <div className="mt-1 font-sans text-2xs font-medium text-white/55">종합 분석 점수</div>
        </div>
      </div>
      <div className="max-w-prose flex-1">
        <div className="mb-2 flex items-center gap-2 font-heading text-xs font-semibold tracking-[0.08em] text-violet-400 uppercase">
          총평
          <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[10px] font-semibold normal-case tracking-normal text-white/70">샘플 리포트</span>
        </div>
        <p className="font-sans text-base text-white/85">
          답변이 구조적이고 사례가 명확해 설득력이 돋보였습니다. 목소리 톤은 안정적이었으나, 시선
          처리에서 약간의 긴장감이 관찰되었습니다. 압박 질문 상황에서도 침착하게 논리를 유지한
          점이 이번 면접의 강점입니다.
        </p>
      </div>
    </div>
  );
}
