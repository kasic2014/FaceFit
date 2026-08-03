const bars = [
  { label: "시선 접촉", mine: 80 },
  { label: "발화 안정", mine: 70 },
  { label: "자세", mine: 75 },
  { label: "답변 내용", mine: 88 },
];

export function ScoreBars() {
  return (
    <div className="mt-6 rounded-[18px] border border-session-line bg-white p-6 px-8">
      <div className="mb-4.5 font-sans text-sm font-semibold text-session-ink">
        축별 점수
      </div>
      <div className="flex flex-col gap-3.5">
        {bars.map((b) => (
          <div key={b.label}>
            <div className="mb-1.5 flex justify-between font-sans text-xs text-session-muted-2">
              <span>{b.label}</span>
              <span className="font-heading">{b.mine}</span>
            </div>
            <div className="relative h-2 rounded-full bg-session-line">
              <div
                className="absolute h-full rounded-full bg-gradient-to-r from-violet-500 to-session-teal-500"
                style={{ width: `${b.mine}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
