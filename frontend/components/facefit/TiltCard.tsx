import { useRef, type ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Interactive card wrapper — subtle pointer-tilt (perspective + rotateX/Y,
 * restrained to ~6deg) plus a mouse-following spotlight glow (21st.dev
 * "Spotlight Card" pattern), so every card that uses this reads as part
 * of the same living, cursor-reactive surface as the hero neuron network.
 */
export function TiltCard({
  children,
  className,
  maxTilt = 6,
}: {
  children: ReactNode;
  className?: string;
  maxTilt?: number;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useRef<HTMLDivElement>(null);
  const spotlightRef = useRef<HTMLDivElement>(null);

  function onMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const wrap = wrapRef.current;
    const surface = surfaceRef.current;
    const spotlight = spotlightRef.current;
    if (!wrap || !surface) return;
    const rect = wrap.getBoundingClientRect();
    const px = (e.clientX - rect.left) / rect.width - 0.5;
    const py = (e.clientY - rect.top) / rect.height - 0.5;
    surface.style.transform = `rotateX(${py * -maxTilt}deg) rotateY(${px * maxTilt}deg) translateZ(0)`;
    if (spotlight) {
      spotlight.style.setProperty("--spot-x", `${(px + 0.5) * 100}%`);
      spotlight.style.setProperty("--spot-y", `${(py + 0.5) * 100}%`);
      spotlight.style.opacity = "1";
    }
  }

  function onMouseLeave() {
    const surface = surfaceRef.current;
    if (surface) surface.style.transform = "rotateX(0deg) rotateY(0deg)";
    if (spotlightRef.current) spotlightRef.current.style.opacity = "0";
  }

  return (
    <div
      ref={wrapRef}
      onMouseMove={onMouseMove}
      onMouseLeave={onMouseLeave}
      className="[perspective:900px]"
    >
      <div
        ref={surfaceRef}
        className={cn("relative h-full overflow-hidden transition-transform duration-150 ease-out will-change-transform", className)}
      >
        {children}
        <div
          ref={spotlightRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300"
          style={{
            background:
              "radial-gradient(240px circle at var(--spot-x, 50%) var(--spot-y, 50%), rgba(168,124,247,0.16), transparent 65%)",
          }}
        />
      </div>
    </div>
  );
}
