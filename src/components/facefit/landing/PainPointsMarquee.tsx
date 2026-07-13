import { ScrollReveal } from "@/components/facefit/ScrollReveal";

const cards = [
  { tag: "답변 구성", text: "답변은 시작했는데 마지막 문장을 어떻게 끝내야 할지 모르겠어요. 늘 ‘그래서 잘 마무리했습니다’로 끝나요." },
  { tag: "꼬리질문", text: "예상 질문은 준비할 수 있는데, ‘왜 그렇게 했나요?’라는 질문이 나오면 바로 막혀요." },
  { tag: "모범답변", text: "모범답변은 너무 잘 쓰여 있어서 오히려 제 경험처럼 말하기가 어려웠어요." },
  { tag: "이력서 기반 질문", text: "제가 실제로 한 프로젝트를 기준으로 질문해 주면 훨씬 면접처럼 연습할 수 있을 것 같아요." },
  { tag: "분석 피드백", text: "내용 점수가 낮다고만 하면 뭘 고쳐야 하는지 모르겠어요. 부족한 문장을 직접 알려주면 좋겠어요." },
  { tag: "음성 연습", text: "첨삭된 답변을 눈으로 읽을 때는 괜찮은데, 직접 말하려고 하면 너무 길고 어색해요." },
];

const cards2 = [
  { tag: "개인화 음성", text: "개선된 답변을 제 목소리로 들어보면, 실제로 제가 말하는 장면을 더 쉽게 상상할 수 있을 것 같아요." },
  { tag: "시선·발화", text: "혼자 연습하면 제 시선이나 말버릇이 어떤지 객관적으로 확인하기 어려워요." },
  { tag: "답변 기반 질문", text: "제가 방금 말한 답변에서 부족한 부분을 찾아서 다음 질문으로 이어졌으면 좋겠어요." },
  { tag: "역질문", text: "면접 마지막에 궁금한 점이 있냐고 물으면, 항상 준비한 게 없어서 없다고 대답하게 돼요." },
  { tag: "맞춤 역질문", text: "인터넷에 있는 질문 말고, 제가 지원한 회사와 직무에 맞는 역질문을 추천받고 싶어요." },
  { tag: "반복 연습", text: "한 번 분석받고 끝나는 게 아니라, 다시 답했을 때 정말 나아졌는지도 비교하고 싶어요." },
];

function Card({ tag, text }: { tag: string; text: string }) {
  return (
    <article className="flex h-[132px] w-[300px] shrink-0 flex-col justify-between rounded-2xl border border-line-200 bg-white px-5 py-4 md:w-[340px]">
      <span className="inline-block w-fit rounded-full bg-ivory-100 px-2.5 py-1 text-[11px] font-semibold text-moss-700">{tag}</span>
      <p className="text-[13px] leading-[1.6] text-ink-600">{text}</p>
    </article>
  );
}

function Row({ items, reverse }: { items: typeof cards; reverse?: boolean }) {
  const doubled = [...items, ...items];
  return (
    <div className="marquee-row" tabIndex={0} aria-label="개발자 취업 준비생 인터뷰 고민 목록">
      <div className={`marquee-track gap-4 py-1 md:gap-5 ${reverse ? "marquee-track-reverse" : ""}`}>
        {doubled.map((c, i) => (
          <Card key={`${c.tag}-${i}`} {...c} />
        ))}
      </div>
    </div>
  );
}

export function PainPointsMarquee() {
  return (
    <section className="bg-[#fcfaf6] py-24">
      <div className="mx-auto max-w-[1200px] px-6 md:px-12 lg:px-14">
        <ScrollReveal>
          <p className="text-xs font-semibold tracking-[.08em] text-sunset-700">DEVELOPER INTERVIEW PAIN POINTS</p>
          <h2 className="mt-3 max-w-[720px] text-balance text-3xl font-bold leading-tight tracking-[-.03em] text-ink-900 md:text-4xl">
            면접을 준비하면서,
            <br className="md:hidden" /> 이런 순간이 가장 어려웠습니다
          </h2>
          <p className="mt-4 max-w-[560px] text-sm leading-7 text-ink-600">
            개발자 취업 준비생 인터뷰에서 반복적으로 나온 고민을 재구성했습니다.
          </p>
        </ScrollReveal>
      </div>
      <ScrollReveal delay={100}>
        <div className="mt-10 flex flex-col gap-4 md:gap-5">
          <Row items={cards} />
          <Row items={cards2} reverse />
        </div>
      </ScrollReveal>
    </section>
  );
}
