import { useState } from "react";
import { Link } from "react-router-dom";
import { AppNav } from "@/components/facefit/AppNav";
import { PageContainer } from "@/components/facefit/layout/PageContainer";

const tabs = ["이용 안내", "개인정보 처리", "데이터 기준"] as const;
type Tab = (typeof tabs)[number];

export default function PolicyPage() {
  const [activeTab, setActiveTab] = useState<Tab>("이용 안내");

  return (
    <div className="min-h-screen bg-ivory-50 text-ink-900">
      <AppNav active="" />
      <PageContainer as="main" size="narrow" className="py-12 md:py-16">
        <p className="text-sm font-bold text-sunset-700">FACE FIT PROTOTYPE POLICY</p>
        <h1 className="mt-3 text-3xl font-bold tracking-[-.05em] md:text-4xl">이용과 데이터 처리 안내</h1>
        <p className="mt-4 max-w-[62ch] text-sm leading-7 text-ink-600 md:text-base">이 화면은 Face Fit 프로토타입의 이용 기준을 쉽게 설명합니다. 정식 서비스의 약관과 개인정보 처리방침은 출시 전 별도로 확정됩니다.</p>

        <div className="mt-10 flex flex-wrap gap-2 border-b border-line-200" role="tablist" aria-label="정책 안내 구분">
          {tabs.map((tab) => (
            <button key={tab} type="button" role="tab" aria-selected={activeTab === tab} onClick={() => setActiveTab(tab)} className={activeTab === tab ? "border-b-2 border-moss-900 px-4 py-3 text-sm font-bold text-moss-900" : "px-4 py-3 text-sm font-medium text-ink-600 hover:text-ink-900"}>{tab}</button>
          ))}
        </div>

        <section className="mt-8 rounded-2xl border border-line-200 bg-white p-7 md:p-9" role="tabpanel">
          {activeTab === "이용 안내" && <PolicyCopy title="연습을 위한 프로토타입입니다" items={["Face Fit은 면접 합격 여부를 판단하지 않는 연습용 코칭 화면입니다.", "현재 로그인, 결제, 영상·음성 저장, 외부 데이터 전송은 구현되어 있지 않습니다.", "화면에 나타나는 회사명·점수·리포트는 사용 흐름을 설명하기 위한 샘플입니다."]} />}
          {activeTab === "개인정보 처리" && <PolicyCopy title="향후 수집될 수 있는 정보" items={["정식 서비스에서는 면접 연습을 위해 영상·음성, 이력서, 지원 공고, 답변 내용을 처리할 수 있습니다.", "수집 목적은 맞춤 질문 구성, 면접 분석, 성장 과제 제안이며 채용 평가나 제3자 제공을 목적으로 하지 않습니다.", "프로토타입에서는 위 정보가 실제로 저장되거나 전송되지 않습니다."]} />}
          {activeTab === "데이터 기준" && <PolicyCopy title="정식 서비스 전 적용 예정 기준" items={["향후 수집되는 면접 영상·음성·지원 자료는 30일 뒤 자동 삭제를 기본 기준으로 합니다.", "사용자는 삭제를 요청하거나 동의를 철회할 수 있으며, 정식 서비스에서는 그 방법을 계정 설정에서 제공합니다.", "이 기준은 법률 검토와 정식 서비스 정책 확정 과정에서 변경될 수 있습니다."]} />}
        </section>
        <Link to="/onboarding" className="mt-8 inline-flex min-h-11 items-center rounded-xl bg-moss-900 px-5 text-sm font-bold text-white">면접 설정으로 돌아가기</Link>
      </PageContainer>
    </div>
  );
}

function PolicyCopy({ title, items }: { title: string; items: string[] }) {
  return <><h2 className="text-xl font-bold tracking-[-.03em]">{title}</h2><ul className="mt-6 space-y-4">{items.map((item) => <li key={item} className="border-l-2 border-moss-500 pl-4 text-sm leading-7 text-ink-700">{item}</li>)}</ul></>;
}
