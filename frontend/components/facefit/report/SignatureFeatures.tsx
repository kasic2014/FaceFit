export function SignatureFeatures() {
  return (
    <div className="mt-6 flex gap-5">
      <div className="flex-1 rounded-[18px] border border-session-line bg-white p-6 px-7">
        <div className="mb-2.5 flex items-center gap-2">
          <span className="size-[22px] flex-none rounded-md bg-gradient-to-br from-moss-500 to-moss-900" />
          <span className="font-heading text-2xs font-semibold tracking-[0.06em] text-moss-900 uppercase">
            내 목소리로 듣기 · Beta
          </span>
        </div>
        <h3 className="mb-2 font-sans text-lg leading-[1.4] font-bold text-session-ink">
          개선 답변, 표준 음성으로 들어보세요
        </h3>
        <p className="mb-4.5 font-sans text-base text-session-muted">
          개선 답변을 음성으로 들으며 다시 연습해보세요. 개인화 음성은 준비 중인 기능입니다.
        </p>
        <div className="flex items-center gap-3 rounded-full border border-session-line bg-session-surface px-4 py-2.5">
          <span className="flex size-[30px] flex-none items-center justify-center rounded-full bg-moss-900">
            <span className="ml-0.5 border-y-[7px] border-l-[11px] border-y-transparent border-l-white" />
          </span>
          <div className="relative h-1 flex-1 rounded-full bg-session-line">
            <div className="absolute top-0 left-0 h-full w-[32%] rounded-full bg-moss-500" />
          </div>
          <span className="flex-none font-heading text-2xs font-medium text-session-muted-2">
            0:14 / 0:44
          </span>
        </div>
      </div>

      <div className="flex-1 rounded-[18px] border border-session-line bg-white p-6 px-7">
        <div className="mb-2.5 flex items-center gap-2">
          <span className="size-[22px] flex-none rounded-md bg-gradient-to-br from-sunset-600 to-sunset-700" />
          <span className="font-heading text-2xs font-semibold tracking-[0.06em] text-sunset-700 uppercase">
            마무리 답변 추천
          </span>
        </div>
        <h3 className="mb-2 font-sans text-lg leading-[1.4] font-bold text-session-ink">
          마지막으로 하고싶은 말, AI가 추천해요
        </h3>
        <div className="mt-3.5 flex flex-col gap-2">
          <div className="rounded-[10px] border border-session-line px-3.5 py-3 font-sans text-sm text-session-ink">
            &quot;오늘 논의된 프로젝트 경험을 바탕으로, 입사 후에도 데이터 기반 문제 해결로
            빠르게 기여하고 싶습니다.&quot;
          </div>
          <div className="rounded-[10px] border border-session-line px-3.5 py-3 font-sans text-sm text-session-ink">
            &quot;부족한 점은 빠르게 배우는 태도로 채워왔습니다. 합격한다면 그 태도로 팀에
            곧바로 녹아들겠습니다.&quot;
          </div>
        </div>
      </div>
    </div>
  );
}
