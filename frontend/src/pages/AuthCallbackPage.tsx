import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { exchangeLoginTicket } from "@/api/auth";
import { isApiConfigured } from "@/api/config";
import { useAuth } from "@/auth/auth-context";

export default function AuthCallbackPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { completeLogin } = useAuth();
  const loginTicket = useMemo(() => new URLSearchParams(location.search).get("loginTicket"), [location.search]);
  const initialMessage = !isApiConfigured()
    ? "VITE_API_BASE_URL을 설정한 뒤 다시 로그인해 주세요."
    : !loginTicket
      ? "로그인 티켓이 없습니다. 로그인 화면에서 다시 시도해 주세요."
      : "로그인 정보를 확인하고 있어요.";
  const [message, setMessage] = useState(initialMessage);

  useEffect(() => {
    if (!isApiConfigured() || !loginTicket) return;

    void exchangeLoginTicket(loginTicket)
      .then((auth) => {
        completeLogin(auth);
        window.history.replaceState(null, "", location.pathname);
        navigate(auth.nextAction === "COMPLETE_ONBOARDING" ? "/account-onboarding" : auth.nextAction === "GO_TO_SERVICE" ? "/dashboard" : "/login", { replace: true });
      })
      .catch(() => {
        window.history.replaceState(null, "", location.pathname);
        setMessage("로그인 정보를 확인하지 못했습니다. 로그인 화면에서 다시 시도해 주세요.");
      });
  }, [completeLogin, location.pathname, loginTicket, navigate]);

  return <main className="grid min-h-screen place-items-center bg-ivory-50 px-5 text-center"><p className="max-w-sm text-sm leading-6 text-ink-700">{message}</p></main>;
}
