const questions = [
  { label: "Q1 · 자기소개", score: 82, height: 66 },
  { label: "Q2 · 프로젝트 경험", score: 69, height: 55 },
  { label: "Q3 · 꼬리질문", score: 74, height: 60 },
];

export function PeerComparisonCards() {
  return (
    <div className="mt-6 flex gap-4">
      {questions.map((q) => (
        <div key={q.label} className="flex-1 rounded-2xl border border-session-line bg-white p-5.5">
          <div className="mb-3.5 font-sans text-sm font-semibold text-session-muted">{q.label}</div>
          <div className="flex h-[120px] items-end gap-2 pt-2.5">
            <div className="flex flex-col items-center gap-1.5">
              <div className="font-heading text-xs font-semibold text-session-ink">{q.score}</div>
              <div
                className="w-[34px] rounded-md bg-gradient-to-b from-violet-500 to-violet-700"
                style={{ height: q.height }}
              />
              <div className="font-sans text-2xs font-medium text-session-ink">내 점수</div>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
