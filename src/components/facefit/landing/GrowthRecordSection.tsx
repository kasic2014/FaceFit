import { GrowthHistoryIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const sessions = [
  { date: "S1", eye: 58, speech: 64, posture: 60, content: 62 },
  { date: "S2", eye: 63, speech: 68, posture: 65, content: 66 },
  { date: "S3", eye: 66, speech: 74, posture: 70, content: 71 },
  { date: "S4", eye: 71, speech: 78, posture: 74, content: 75 },
  { date: "S5", eye: 74, speech: 81, posture: 78, content: 79 },
];

const axes = [
  { key: "eye", label: "시선", dot: "bg-[#A9C2AC]", bar: "bg-[#A9C2AC]" },
  { key: "speech", label: "발화", dot: "bg-moss-500", bar: "bg-moss-500" },
  { key: "posture", label: "자세", dot: "bg-sunset-600", bar: "bg-sunset-600" },
  { key: "content", label: "내용", dot: "bg-sunset-300", bar: "bg-sunset-300" },
] as const;

export function GrowthRecordSection() {
  return (
    <section className="bg-ivory-100 px-6 py-24 md:px-12 lg:px-16">
      <div className="mx-auto max-w-[1200px]">
        <ScrollReveal>
          <div className="grid gap-6 md:grid-cols-[1fr_1fr] md:items-end">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">성장 기록</p>
                <span className="rounded-full border border-line-300 bg-white px-2.5 py-1 text-[10px] font-semibold text-ink-400">데모 데이터</span>
              </div>
              <h2 className="mt-3 text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
                세션마다, 4축의 변화를 기록합니다
              </h2>
            </div>
            <p className="text-sm leading-7 text-ink-600 md:justify-self-end md:max-w-[380px]">
              마이페이지에서는 면접 날짜, 면접관 유형, 축별 점수와 반복해서 나타나는 개선 포인트를 확인할 수 있습니다.
            </p>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="mt-10 grid gap-6 lg:grid-cols-[1.3fr_.7fr]">
            <div className="rounded-2xl border border-line-200 bg-white p-6 md:p-8">
              <div className="flex items-center justify-between">
                <p className="text-[13px] font-semibold text-ink-900">축별 점수 추이 (최근 5회)</p>
                <div className="flex gap-3 text-[11px] font-medium text-ink-600">
                  {axes.map((a) => (
                    <span key={a.key} className="flex items-center gap-1.5">
                      <span className={`size-2 rounded-full ${a.dot}`} />
                      {a.label}
                    </span>
                  ))}
                </div>
              </div>
              <div className="mt-6 flex items-end gap-6">
                {sessions.map((s) => (
                  <div key={s.date} className="flex flex-1 flex-col items-center gap-1.5">
                    <div className="flex h-[140px] items-end gap-1">
                      {axes.map((a) => (
                        <span key={a.key} className={`w-3 rounded-t ${a.bar}`} style={{ height: `${s[a.key]}%` }} />
                      ))}
                    </div>
                    <span className="text-[11px] font-medium text-ink-400">{s.date}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="rounded-2xl border border-line-200 bg-white p-6">
              <div className="flex items-center gap-2.5">
                <span className="grid size-8 place-items-center rounded-full bg-ivory-100 text-moss-700">
                  <GrowthHistoryIcon className="size-4" />
                </span>
                <p className="text-[13px] font-semibold text-ink-400">가장 많이 개선된 항목</p>
              </div>
              <p className="mt-3 text-[15px] font-medium text-ink-900">발화 — 5회 중 4회 연속 상승</p>
              <div className="mt-5 border-t border-line-200 pt-5">
                <p className="text-[13px] font-semibold text-ink-400">반복해서 나타나는 개선 포인트</p>
                <p className="mt-2 text-[14px] leading-[1.6] text-ink-700">답변 후반부 결과 문장 누락</p>
              </div>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
