import { useRef, type ReactNode } from "react";

/**
 * Wraps a single interactive child (button/link) and pulls it a few
 * pixels toward the cursor on hover, springing back on leave — the
 * "magnetic button" hero-CTA pattern (21st.dev-style hover motion).
 * Purely a transform wrapper; the child keeps its own classes/behavior.
 */
export function MagneticButton({ children, strength = 0.35 }: { children: ReactNode; strength?: number }) {
  const ref = useRef<HTMLDivElement>(null);

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const el = ref.current;
    if (!el) return;
    const rect = el.getBoundingClientRect();
    const dx = e.clientX - (rect.left + rect.width / 2);
    const dy = e.clientY - (rect.top + rect.height / 2);
    el.style.transform = `translate(${dx * strength}px, ${dy * strength}px)`;
  }

  function onMouseLeave() {
    const el = ref.current;
    if (!el) return;
    el.style.transform = "translate(0px, 0px)";
  }

  return (
    <div
      ref={ref}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className="inline-block transition-transform duration-200 ease-out will-change-transform"
    >
      {children}
    </div>
  );
}
