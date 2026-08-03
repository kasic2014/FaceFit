const breakdown = [
  {
    label: "시선 접촉",
    score: 80,
    evidence: "카메라 응시 58%, 권장 75%",
    tag: "정면 응시 훈련 필요",
    tagClass: "text-violet-700 bg-[#f3ebfe]",
  },
  {
    label: "발화 안정",
    score: 70,
    evidence: "필러 14회",
    tag: "문장 끝까지 말하기",
    tagClass: "text-[#0d9488] bg-[#e6faf5]",
  },
  {
    label: "자세",
    score: 75,
    evidence: "상체 흔들림 5회 감지",
    tag: "어깨 고정 연습",
    tagClass: "text-sunset-700 bg-[#fef3e2]",
  },
  {
    label: "답변 내용",
    score: 88,
    evidence: "구조화된 STAR 답변 4/5",
    tag: "우수",
    tagClass: "text-[#2563eb] bg-[#eaf1fe]",
  },
];

export function AxisRadarChart() {
  return (
    <div className="mt-6 flex gap-10 rounded-[18px] border border-session-line bg-white p-8">
      <div className="flex flex-none basis-[300px] flex-col items-center">
        <svg width="280" height="280" viewBox="0 0 300 300" className="overflow-visible">
          <polygon points="150,30 270,150 150,270 30,150" fill="none" stroke="oklch(0.92 0.02 300)" strokeWidth="1" />
          <polygon points="150,60 240,150 150,240 60,150" fill="none" stroke="oklch(0.92 0.02 300)" strokeWidth="1" />
          <polygon points="150,90 210,150 150,210 90,150" fill="none" stroke="oklch(0.92 0.02 300)" strokeWidth="1" />
          <polygon points="150,120 180,150 150,180 120,150" fill="none" stroke="oklch(0.92 0.02 300)" strokeWidth="1" />
          <line x1="150" y1="150" x2="150" y2="30" stroke="oklch(0.92 0.02 300)" />
          <line x1="150" y1="150" x2="270" y2="150" stroke="oklch(0.92 0.02 300)" />
          <line x1="150" y1="150" x2="150" y2="270" stroke="oklch(0.92 0.02 300)" />
          <line x1="150" y1="150" x2="30" y2="150" stroke="oklch(0.92 0.02 300)" />

          <polygon
            points="150,54 234,150 150,240 44,150"
            fill="url(#radarGrad)"
            fillOpacity=".35"
            stroke="oklch(0.64 0.24 296)"
            strokeWidth="2"
          />
          <defs>
            <linearGradient id="radarGrad" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="oklch(0.56 0.24 293)" />
              <stop offset="1" stopColor="oklch(0.68 0.13 178)" />
            </linearGradient>
          </defs>
          <circle cx="150" cy="54" r="4" fill="oklch(0.64 0.24 296)" />
          <circle cx="234" cy="150" r="4" fill="oklch(0.64 0.24 296)" />
          <circle cx="150" cy="240" r="4" fill="oklch(0.64 0.24 296)" />
          <circle cx="44" cy="150" r="4" fill="oklch(0.64 0.24 296)" />

          <text x="150" y="18" textAnchor="middle" fontSize="13" fontWeight="600" fill="oklch(0.22 0.01 300)" fontFamily="Pretendard">
            시선 접촉
          </text>
          <text x="286" y="154" textAnchor="start" fontSize="13" fontWeight="600" fill="oklch(0.22 0.01 300)" fontFamily="Pretendard">
            발화
          </text>
          <text x="150" y="292" textAnchor="middle" fontSize="13" fontWeight="600" fill="oklch(0.22 0.01 300)" fontFamily="Pretendard">
            자세
          </text>
          <text x="14" y="154" textAnchor="end" fontSize="13" fontWeight="600" fill="oklch(0.22 0.01 300)" fontFamily="Pretendard">
            답변 내용
          </text>
        </svg>
      </div>

      <div className="flex flex-1 flex-col justify-center gap-4">
        {breakdown.map((b) => (
          <div
            key={b.label}
            className="flex items-center justify-between rounded-xl border border-session-line bg-session-surface px-4 py-3.5"
          >
            <div>
              <div className="font-sans text-sm font-semibold text-session-ink">
                {b.label}: <span className="font-heading">{b.score}/100</span>
              </div>
              <div className="mt-1 font-sans text-xs text-session-muted-2">근거: {b.evidence}</div>
            </div>
            <div className={`rounded-full px-3 py-1.5 font-sans text-2xs font-semibold whitespace-nowrap ${b.tagClass}`}>
              {b.tag}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
