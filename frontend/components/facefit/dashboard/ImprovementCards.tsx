import { TrendingUp, Eye } from "lucide-react";

export function ImprovementCards() {
  return (
    <div className="grid grid-cols-2 gap-4">
      <div className="rounded-2xl border border-moss-300/50 bg-[#edf4ef] p-4">
        <div className="flex items-center justify-between">
          <p className="text-[12.5px] font-semibold text-moss-700">가장 개선된 항목</p>
          <TrendingUp size={16} className="text-moss-700" />
        </div>
        <div className="mt-3 flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-full bg-white text-moss-700">
            <TrendingUp size={16} />
          </span>
          <div>
            <p className="text-sm font-bold text-ink-900">답변 내용 <span className="text-moss-700">+8점</span></p>
            <p className="text-[11px] text-ink-400">이전 대비</p>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-sunset-300/60 bg-[#fdf1e8] p-4">
        <div className="flex items-center justify-between">
          <p className="text-[12.5px] font-semibold text-sunset-700">우선 개선할 항목</p>
          <span className="text-sunset-600">◎</span>
        </div>
        <div className="mt-3 flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-full bg-white text-sunset-600">
            <Eye size={16} />
          </span>
          <div>
            <p className="text-sm font-bold text-ink-900">시선 유지</p>
            <p className="text-[11px] text-ink-400">집중 연습이 필요해요</p>
          </div>
        </div>
      </div>
    </div>
  );
}
