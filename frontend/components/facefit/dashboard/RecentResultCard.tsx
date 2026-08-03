import { Link } from "react-router-dom";
import { CompanyBadge } from "./CompanyBadge";

export function RecentResultCard() {
  return (
    <div className="rounded-2xl border border-line-200 bg-white p-6">
      <p className="mb-4 text-[15px] font-bold text-ink-900">최근 면접 결과</p>

      <div className="flex flex-col gap-5 md:flex-row md:items-center">
        <div className="flex items-center gap-3 md:w-[220px] md:flex-none">
          <CompanyBadge name="네이버" size={44} />
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-ink-900">네이버 (NAVER)</p>
            <p className="truncate text-[12.5px] text-ink-400">백엔드 개발자</p>
            <p className="mt-0.5 text-[11px] text-ink-300">기술 면접관 · 일반 · 2026.07.10</p>
          </div>
        </div>

        <div className="flex flex-none flex-col items-center md:w-[110px]">
          <p className="text-[11px] font-medium text-ink-400">종합 점수</p>
          <p className="text-3xl font-bold tabular-nums text-moss-900">
            78<span className="text-base font-medium text-ink-400">점</span>
          </p>
          <p className="mt-0.5 text-[12px] font-semibold text-moss-700">▲ 6점</p>
          <p className="text-[10px] text-ink-300">이전 면접(72점) 대비</p>
        </div>

        <div className="flex-1 rounded-xl bg-ivory-100 px-4 py-3 text-[13px] leading-[1.6] text-ink-700">
          논리적인 답변 구조는 좋았지만, 카메라 시선 유지와 결론 전달이 부족했어요.
        </div>

        <div className="flex flex-none flex-col gap-2 md:w-[150px]">
          <Link to="/report" className="rounded-xl border border-line-300 px-4 py-2.5 text-center text-[13px] font-semibold text-ink-700 transition hover:bg-ivory-100">
            리포트 보기
          </Link>
          <Link to="/onboarding" className="rounded-xl bg-moss-900 px-4 py-2.5 text-center text-[13px] font-semibold text-white transition hover:bg-[#1f3a24]">
            같은 조건으로 다시 면접
          </Link>
        </div>
      </div>
    </div>
  );
}
