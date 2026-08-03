import { ChevronRight, TrendingUp } from "lucide-react";

const points = [
  { x: 40, y: 58, label: "06.12" },
  { x: 170, y: 64, label: "06.19" },
  { x: 300, y: 68, label: "06.26" },
  { x: 430, y: 72, label: "07.05" },
  { x: 560, y: 78, label: "07.10" },
];

function yFor(score: number) {
  return 200 - (score / 100) * 180;
}

export function GrowthTrendCard() {
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"}${p.x} ${yFor(p.y)}`).join(" ");

  return (
    <div className="rounded-2xl border border-line-200 bg-white p-6">
      <div className="mb-1 flex items-center justify-between">
        <div>
          <p className="text-[15px] font-bold text-ink-900">성장 추이 (최근 5회)</p>
          <p className="mt-1 text-[12.5px] text-ink-400">면접 실력의 변화를 확인해 보세요.</p>
        </div>
        <span className="rounded-lg border border-line-300 px-3 py-1.5 text-[12px] font-medium text-ink-600">전체 ⌄</span>
      </div>

      <div className="mt-4 grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <svg viewBox="0 0 600 220" className="w-full" aria-hidden="true">
          {[0, 20, 40, 60, 80, 100].map((v) => (
            <g key={v}>
              <line x1="30" y1={yFor(v)} x2="590" y2={yFor(v)} stroke="oklch(0.93 0.008 70)" />
              <text x="0" y={yFor(v) + 4} fontSize="11" fill="oklch(0.58 0.012 60)">{v}</text>
            </g>
          ))}
          <path d={linePath} fill="none" stroke="#3E5A42" strokeWidth="2.5" />
          {points.map((p, i) => (
            <g key={p.label}>
              <circle cx={p.x} cy={yFor(p.y)} r={i === points.length - 1 ? 0 : 5} fill="#fff" stroke="#3E5A42" strokeWidth="2.5" />
              {i !== points.length - 1 && (
                <text x={p.x} y={yFor(p.y) - 14} textAnchor="middle" fontSize="12" fontWeight="700" fill="#3E5A42">{p.y}</text>
              )}
              <text x={p.x} y="215" textAnchor="middle" fontSize="11" fill="oklch(0.58 0.012 60)">{p.label}</text>
            </g>
          ))}
          <g transform={`translate(${points[points.length - 1].x}, ${yFor(points[points.length - 1].y)})`}>
            <rect x="-19" y="-30" width="38" height="24" rx="12" fill="#3E5A42" />
            <text x="0" y="-13" textAnchor="middle" fontSize="13" fontWeight="700" fill="#fff">{points[points.length - 1].y}</text>
            <circle r="5" fill="#3E5A42" />
          </g>
        </svg>

        <div className="flex flex-col justify-between gap-4 rounded-xl bg-ivory-100 p-4">
          <div className="flex flex-col gap-3">
            <div className="flex items-start gap-2.5">
              <TrendingUp size={16} className="mt-0.5 flex-none text-moss-700" />
              <p className="text-[13px] leading-[1.6] text-ink-700">답변 내용은 꾸준히 상승하고 있어요.</p>
            </div>
            <p className="text-[13px] leading-[1.6] text-ink-700">시선 점수는 최근 3회 동안 큰 변화가 없어요.</p>
          </div>
          <button className="flex items-center gap-1 self-start text-[13px] font-semibold text-moss-700">
            분석 자세히 보기
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}
