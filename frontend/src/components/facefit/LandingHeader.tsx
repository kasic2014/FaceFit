import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Logo } from "./Logo";

const links = [
  { label: "서비스 소개", href: "/#service" },
  { label: "분석 근거", href: "/#evidence" },
  { label: "성장 과제", href: "/#evidence" },
  { label: "진행 방식", href: "/#how-it-works" },
  { label: "요금제", href: "/pricing" },
];

export function LandingHeader() {
  const [isScrolled, setIsScrolled] = useState(false);

  useEffect(() => {
    const updateHeader = () => setIsScrolled(window.scrollY > 18);
    updateHeader();
    window.addEventListener("scroll", updateHeader, { passive: true });
    return () => window.removeEventListener("scroll", updateHeader);
  }, []);

  return (
    <header className={`sticky top-0 z-20 border-b px-5 text-white transition-[background-color,box-shadow,backdrop-filter] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] md:px-8 lg:px-12 ${isScrolled ? "border-white/12 bg-[#091511]/82 py-3 shadow-[0_8px_24px_rgba(0,0,0,.14)] backdrop-blur-xl" : "border-white/10 bg-[#091511] py-4"}`}>
      <div className="mx-auto flex max-w-[1440px] items-center justify-between">
        <div className="flex items-center gap-10">
          <Link to="/" aria-label="Face Fit 홈" className="shrink-0">
            <Logo size="lg" textClassName="text-white" />
          </Link>
          <nav className="hidden items-center gap-7 lg:flex" aria-label="랜딩 메뉴">
            {links.map((item) =>
              item.href.includes("#") ? (
                <a
                  key={item.label}
                  href={item.href}
                  className="text-sm font-medium text-white/62 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
                >
                  {item.label}
                </a>
              ) : (
                <Link
                  key={item.label}
                  to={item.href}
                  className="text-sm font-medium text-white/62 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white"
                >
                  {item.label}
                </Link>
              ),
            )}
          </nav>
        </div>
        <Link to="/login" className="inline-flex min-h-11 items-center bg-[#d96d25] px-4 text-sm font-semibold text-white transition hover:bg-[#ef8036] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-white">
          로그인
        </Link>
      </div>
    </header>
  );
}
