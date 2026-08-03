import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";
import { Logo } from "@/components/facefit/Logo";

export default function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-ivory-50 px-5 text-center text-ink-900">
      <section className="max-w-md">
        <div className="flex justify-center">
          <Logo size="lg" />
        </div>
        <p className="mt-10 text-sm font-bold tracking-[0.12em] text-moss-700">404</p>
        <h1 className="mt-3 text-3xl font-bold tracking-[-.04em]">페이지를 찾을 수 없어요.</h1>
        <p className="mt-3 text-sm leading-6 text-ink-600">
          주소가 변경되었거나 존재하지 않는 페이지입니다. 랜딩으로 돌아가 면접 연습을 이어가 주세요.
        </p>
        <Link to="/" className="mt-7 inline-flex min-h-11 items-center gap-2 rounded-xl bg-moss-900 px-5 text-sm font-bold text-white">
          <ArrowLeft size={16} /> 랜딩으로 돌아가기
        </Link>
      </section>
    </main>
  );
}
