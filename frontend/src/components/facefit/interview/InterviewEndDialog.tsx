import { useEffect, useRef } from "react";
import { Link } from "react-router";

export function InterviewEndDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>('button, a[href]');
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  return <div className="fixed inset-0 z-50 grid place-items-center bg-ink-900/35 p-4"><section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="end-title" className="w-full max-w-md rounded-[18px] border border-line-200 bg-white p-6 shadow-xl"><div className="flex items-start justify-between gap-3"><div><h2 id="end-title" className="text-xl font-bold text-ink-900">면접을 종료할까요?</h2><p className="mt-2 text-sm leading-6 text-ink-600">현재까지의 답변은 이 데모 흐름에서 분석 화면으로 이어집니다.</p></div><button ref={closeRef} type="button" onClick={onClose} aria-label="모달 닫기" className="grid size-9 place-items-center rounded-lg text-ink-600 hover:bg-ivory-100">×</button></div><dl className="mt-5 grid grid-cols-3 gap-2 rounded-xl bg-ivory-100 p-3 text-center"><div><dt className="text-xs text-ink-600">경과 시간</dt><dd className="mt-1 text-sm font-bold">12:38</dd></div><div><dt className="text-xs text-ink-600">완료 질문</dt><dd className="mt-1 text-sm font-bold">4 / 5</dd></div><div><dt className="text-xs text-ink-600">분석 상태</dt><dd className="mt-1 text-sm font-bold text-moss-700">준비</dd></div></dl><div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end"><button type="button" onClick={onClose} className="min-h-11 rounded-lg bg-moss-900 px-4 text-sm font-semibold text-white">면접 계속하기</button><Link to="/analysis" className="inline-flex min-h-11 items-center justify-center rounded-lg border border-sunset-600 px-4 text-sm font-semibold text-sunset-700">종료하고 분석하기</Link></div></section></div>;
}
