import { ResumeAnalysisIcon } from "@/components/facefit/icons";
import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const fields = [
  { label: "프로젝트", value: "미니프로젝트" },
  { label: "역할", value: "PM 및 제스처 로직 구현" },
  { label: "기술", value: "MediaPipe, JavaScript, FastAPI" },
  { label: "지원 기업 · 직무", value: "OO테크 · 프론트엔드 개발자" },
];

export function ResumeQuestionSection() {
  return (
    <section className="bg-ivory-100 px-6 py-24 md:px-12 lg:px-16">
      <div className="mx-auto grid max-w-[1200px] gap-10 lg:grid-cols-2 lg:gap-14">
        <ScrollReveal>
          <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">이력서 기반 질문</p>
          <h2 className="mt-3 text-3xl font-bold leading-[1.3] tracking-[-.03em] text-ink-900 md:text-4xl">
            내가 올린 이력서에서
            <br />
            질문이 시작됩니다
          </h2>
          <p className="mt-4 max-w-[440px] text-sm leading-7 text-ink-600">
            이력서 업로드, 자기소개서, 지원 기업, 목표 직무를 입력하면 그 정보를 바탕으로 질문이 만들어집니다.
          </p>

          <div className="mt-8 rounded-2xl border border-line-200 bg-white p-6">
            <div className="flex items-center gap-2.5">
              <span className="grid size-9 place-items-center rounded-full bg-[#edf4ef] text-moss-700">
                <ResumeAnalysisIcon className="size-[18px]" />
              </span>
              <p className="text-sm font-bold text-ink-900">이력서 정보</p>
            </div>
            <dl className="mt-5 space-y-3.5">
              {fields.map((f) => (
                <div key={f.label} className="grid grid-cols-[110px_1fr] gap-3 text-[13px]">
                  <dt className="text-ink-400">{f.label}</dt>
                  <dd className="font-medium text-ink-900">{f.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </ScrollReveal>

        <ScrollReveal delay={100}>
          <div className="relative flex h-full flex-col justify-center rounded-2xl border border-[#16302f]/15 bg-[#10221D] p-7 text-white md:p-9">
            <span className="w-fit rounded-full border border-white/15 bg-white/5 px-2.5 py-1 text-[10px] font-semibold text-white/70">예시 면접</span>
            <p className="mt-5 text-[11px] font-medium text-white/40">이력서 기반으로 생성된 질문</p>
            <p className="mt-2 text-lg font-semibold leading-[1.6] md:text-xl">
              &ldquo;MediaPipe 손 인식 정확도가 떨어졌을 때 문제를 어떤 기준으로 분류했고, 실제로 어떤 로직을 수정했나요?&rdquo;
            </p>
            <div className="mt-6 flex flex-wrap gap-2 text-[11px] text-white/45">
              <span className="rounded-full border border-white/10 px-2.5 py-1">근거: 프로젝트 &middot; 미니프로젝트</span>
              <span className="rounded-full border border-white/10 px-2.5 py-1">근거: 기술 &middot; MediaPipe</span>
            </div>
          </div>
        </ScrollReveal>
      </div>
    </section>
  );
}
