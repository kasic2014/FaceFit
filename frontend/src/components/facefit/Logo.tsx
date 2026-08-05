import { cn } from "@/lib/utils";

type LogoProps = {
  size?: "lg" | "sm";
  textClassName?: string;
  className?: string;
};

export function FaceFitSymbol({ className, title }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 40 40" role={title ? "img" : undefined} aria-hidden={title ? undefined : true} className={cn("block", className)}>
      {title && <title>{title}</title>}
      <rect width="40" height="40" rx="10" fill="currentColor" />
      <path d="M11 10h19v5H16v5h11v5H16v5H11V10Z" fill="#F4F5F1" />
      <path d="M27.5 27.5 30 30l4.5-5" fill="none" stroke="#F2AB72" strokeLinecap="square" strokeLinejoin="miter" strokeWidth="2.5" />
    </svg>
  );
}

export function Logo({ size = "lg", textClassName, className }: LogoProps) {
  const isLg = size === "lg";

  return (
    <div className={cn("flex items-center", isLg ? "gap-2.5" : "gap-2", className)}>
      <FaceFitSymbol className={cn("shrink-0 text-moss-900", isLg ? "size-[34px]" : "size-[26px]")} />
      <span className={cn("font-heading font-bold leading-none tracking-[-0.045em] text-ink-900", isLg ? "text-xl" : "text-lg", textClassName)}>
        Face <span className="text-sunset-600">Fit</span>
      </span>
    </div>
  );
}
