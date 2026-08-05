import { useEffect, useRef } from "react";

type InterviewEndDialogProps = {
  open: boolean;
  turnOrder: number | null;
  pending: boolean;
  onCancel: () => void;
  onConfirm: () => void;
};

export function InterviewEndDialog({
  open,
  turnOrder,
  pending,
  onCancel,
  onConfirm,
}: InterviewEndDialogProps) {
  const dialogRef = useRef<HTMLElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable =
        dialogRef.current?.querySelectorAll<HTMLElement>("button:not(:disabled)");
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
  }, [onCancel, open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-ink-900/45 p-4">
      <section
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="interview-end-title"
        aria-describedby="interview-end-description"
        className="w-full max-w-md rounded-[18px] border border-line-200 bg-white p-6 shadow-xl"
      >
        <h2
          id="interview-end-title"
          className="text-xl font-bold text-ink-900"
        >
          면접을 중단할까요?
        </h2>
        <p
          id="interview-end-description"
          className="mt-3 text-sm leading-6 text-ink-600"
        >
          중단한 면접은 분석과 결과 리포트를 받을 수 없습니다. 지금까지 저장된
          답변도 점수로 이어지지 않습니다.
        </p>
        <p className="mt-4 rounded-xl bg-ivory-100 px-4 py-3 text-sm text-ink-700">
          {turnOrder === null
            ? "아직 답변을 시작하지 않았어요."
            : `현재 ${turnOrder}번째 질문을 진행 중이에요.`}
        </p>
        <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-end">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="min-h-11 rounded-lg bg-moss-900 px-4 text-sm font-semibold text-white"
          >
            면접 계속하기
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={pending}
            className="min-h-11 rounded-lg border border-sunset-600 px-4 text-sm font-semibold text-sunset-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? "중단하는 중" : "중단하고 나가기"}
          </button>
        </div>
      </section>
    </div>
  );
}
