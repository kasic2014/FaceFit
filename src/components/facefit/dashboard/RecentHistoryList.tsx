import { Link } from "react-router-dom";
import { CompanyBadge } from "./CompanyBadge";

const rows = [
  { company: "네이버", eng: "NAVER", role: "백엔드 개발자", persona: "기술 면접관 · 일반", date: "2026.07.10", score: 78 },
  { company: "카카오", eng: "KAKAO", role: "AI 엔지니어", persona: "HR 면접관 · 일반", date: "2026.07.05", score: 72 },
  { company: "삼성전자", eng: "SAMSUNG", role: "소프트웨어 개발자", persona: "기술 면접관 · 압박", date: "2026.06.28", score: 65 },
  { company: "LG전자", eng: "LG", role: "SW 개발자", persona: "HR 면접관 · 일반", date: "2026.06.20", score: 61 },
  { company: "현대자동차", eng: "HYUNDAI", role: "백엔드 개발자", persona: "기술 면접관 · 압박", date: "2026.06.12", score: 58 },
];

export function RecentHistoryList() {
  return (
    <div className="rounded-2xl border border-line-200 bg-white p-6">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-[15px] font-bold text-ink-900">최근 면접 기록</p>
        <Link to="/dashboard" className="text-[12.5px] font-semibold text-moss-700">전체 보기</Link>
      </div>

      <div className="flex flex-col gap-3">
        {rows.map((row) => (
          <div key={`${row.company}-${row.date}`} className="flex items-center gap-3 rounded-xl border border-line-100 p-3">
            <CompanyBadge name={row.company} size={36} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-bold text-ink-900">
                {row.company} <span className="font-medium text-ink-400">({row.eng})</span>
              </p>
              <p className="truncate text-[11.5px] text-ink-400">{row.role}</p>
              <p className="truncate text-[10.5px] text-ink-300">{row.persona} · {row.date}</p>
            </div>
            <p className="flex-none text-lg font-bold tabular-nums text-ink-900">{row.score}<span className="text-xs font-medium text-ink-400">점</span></p>
            <div className="flex flex-none flex-col gap-1.5">
              <Link to="/report" className="rounded-lg border border-line-300 px-2.5 py-1 text-center text-[11px] font-semibold text-ink-700 transition hover:bg-ivory-100">
                리포트 보기
              </Link>
              <Link to="/onboarding" className="rounded-lg border border-line-300 px-2.5 py-1 text-center text-[11px] font-semibold text-ink-700 transition hover:bg-ivory-100">
                다시 면접
              </Link>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
