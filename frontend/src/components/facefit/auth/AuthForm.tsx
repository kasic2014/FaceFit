import { useState } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Link } from "react-router";
import { getApiUrl, isApiConfigured } from "@/api/config";
import { useAuth } from "@/auth/auth-context";
import { Logo } from "@/components/facefit/Logo";
import { PageContainer } from "@/components/facefit/layout/PageContainer";
import { GoogleIcon, KakaoIcon, NaverIcon } from "./SocialIcons";

const providers = [
  { id: "google", name: "Google", Icon: GoogleIcon, style: "" },
  { id: "kakao", name: "Kakao", Icon: KakaoIcon, style: "bg-[#FEE500] text-[#191600]" },
  { id: "naver", name: "Naver", Icon: NaverIcon, style: "bg-[#03C75A] text-white" },
];

export function AuthForm({ mode }: { mode: "login" | "signup" }) {
  const [message, setMessage] = useState("");
  const { backendConfigured } = useAuth();
  const signup = mode === "signup";
  const action = signup ? "회원가입" : "로그인";
  const startOAuth = (provider: string) => {
    if (!backendConfigured || !isApiConfigured()) {
      setMessage("VITE_API_BASE_URL을 설정한 뒤 소셜 로그인을 사용할 수 있어요.");
      return;
    }

    window.location.assign(getApiUrl(`/oauth2/authorization/${provider}`));
  };

  return (
    <div className="min-h-screen bg-ivory-50">
      <header className="flex h-[70px] items-center justify-between border-b border-line-200 bg-white px-5 md:px-8 lg:px-12">
        <Link to="/" aria-label="Face Fit 홈"><Logo size="sm" /></Link>
        <Link to="/" className="text-sm font-semibold text-ink-600 transition hover:text-moss-900">랜딩으로 돌아가기</Link>
      </header>
      <PageContainer as="main" size="wide" className="flex min-h-[calc(100svh-70px)] items-center py-10 md:py-14">
        <div className="mx-auto grid w-full max-w-[980px] items-center gap-12 lg:grid-cols-[.82fr_1fr] lg:gap-20">
          <section className="hidden lg:block">
            <p className="text-sm font-semibold text-sunset-700">FACE FIT INTERVIEW PRACTICE</p>
            <h1 className="mt-5 text-5xl font-bold leading-[1.04] tracking-[-.06em] text-ink-900">외운 답변 대신,<br />내 경험으로<br />면접을 준비하세요.</h1>
            <p className="mt-7 max-w-[34ch] text-base leading-8 text-ink-600">이력서와 지원 맥락으로 질문을 받고, 답변의 근거를 확인한 뒤 성장 과제로 재연습합니다.</p>
            <ul className="mt-8 space-y-3 text-sm text-ink-700">{["지원 정보 기반 질문", "답변·발화·시선·자세의 근거", "성장 과제로 이어지는 재연습"].map((item) => <li key={item} className="flex items-center gap-2"><Check className="size-4 text-moss-700" />{item}</li>)}</ul>
          </section>

          <section className="mx-auto w-full max-w-[430px] rounded-[18px] border border-line-200 bg-white p-7 shadow-[0_20px_55px_rgba(32,42,35,.06)] md:p-9">
            <p className="text-sm font-semibold text-sunset-700">{signup ? "처음 시작하기" : "다시 이어가기"}</p>
            <h2 className="mt-3 text-3xl font-bold tracking-[-.045em] text-ink-900">{signup ? "Face Fit을 시작해 볼까요?" : "면접 준비를 이어가 볼까요?"}</h2>
            <p className="mt-3 text-sm leading-6 text-ink-600">소셜 계정으로 간편하게 {action}할 수 있어요.</p>
            <div className="mt-8 space-y-3">{providers.map(({ id, name, Icon, style }) => <button key={name} type="button" onClick={() => startOAuth(id)} className="flex min-h-12 w-full items-center justify-center gap-3 rounded-lg border border-line-300 bg-white px-4 text-sm font-bold text-ink-900 transition hover:border-moss-500 hover:bg-ivory-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-moss-700"><span className={`grid size-8 place-items-center rounded-md ${style}`}><Icon className="size-[18px]" /></span>{name}로 {action}</button>)}</div>
            {message && <p role="status" className="mt-4 rounded-lg bg-[#f6f8f5] p-3 text-sm leading-6 text-moss-900">{message}</p>}
            <p className="mt-7 text-center text-xs leading-5 text-ink-600">계속하면 Face Fit의 이용약관 및 개인정보 처리방침에 동의하는 것으로 간주합니다.</p>
            <p className="mt-7 flex items-center justify-center gap-1 text-center text-sm text-ink-600">{signup ? "이미 계정이 있으신가요?" : "처음 이용하시나요?"}<Link to={signup ? "/login" : "/signup"} className="inline-flex items-center gap-1 font-bold text-moss-700 transition hover:text-moss-900">{signup ? "로그인" : "회원가입"}<ArrowRight className="size-3.5" /></Link></p>
          </section>
        </div>
      </PageContainer>
    </div>
  );
}
