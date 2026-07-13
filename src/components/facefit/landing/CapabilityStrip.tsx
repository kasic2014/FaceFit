import { ResumeAnalysisIcon, FollowUpQuestionIcon, ContentAnalysisIcon, VoicePlaybackIcon } from "@/components/facefit/icons";

const items = [
  { icon: ResumeAnalysisIcon, title: "이력서 기반 질문", desc: "업로드한 이력서와 지원 정보를 바탕으로 질문을 구성합니다" },
  { icon: FollowUpQuestionIcon, title: "답변 기반 꼬리질문", desc: "직전 답변에서 부족한 지점을 찾아 다음 질문으로 이어갑니다" },
  { icon: ContentAnalysisIcon, title: "시선·발화·자세·내용 4축 분석", desc: "네 가지 축에서 근거와 함께 답변을 분석합니다" },
  { icon: VoicePlaybackIcon, title: "개선 답변 음성 재생", desc: "고친 답변을 음성으로 들으며 다시 연습합니다" },
];

export function CapabilityStrip() {
  return (
    <section className="relative z-20 bg-ivory-100 px-6 md:px-14">
      <div className="mx-auto -translate-y-1/2 max-w-[1200px] overflow-hidden rounded-[18px] border border-line-200 bg-white shadow-[0_18px_50px_rgba(55,40,24,.1)]">
        <div className="grid grid-cols-2 md:grid-cols-4">
          {items.map((item, i) => (
            <div
              key={item.title}
              className={`flex items-start gap-3 px-5 py-6 md:px-6 ${i % 2 === 0 ? "border-r border-line-200" : ""} ${i < 2 ? "border-b border-line-200 md:border-b-0" : ""} ${i > 0 ? "md:border-l md:border-line-200" : ""} md:border-r-0`}
            >
              <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#edf4ef] text-moss-700">
                <item.icon className="size-[18px]" />
              </span>
              <div>
                <p className="text-[14px] font-bold leading-[1.35] text-ink-900">{item.title}</p>
                <p className="mt-1.5 text-[13px] leading-[1.5] text-ink-400">{item.desc}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
