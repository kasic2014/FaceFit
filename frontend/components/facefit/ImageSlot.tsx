import { cn } from "@/lib/utils";

export function ImageSlot({
  label,
  shape = "rect",
  className,
}: {
  label: string;
  shape?: "rect" | "circle";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "relative flex items-center justify-center overflow-hidden bg-line-100",
        shape === "circle" ? "rounded-full" : "rounded-xl",
        className
      )}
    >
      <div className="absolute inset-0 bg-[repeating-linear-gradient(135deg,rgba(48,43,39,.07)_0px,rgba(48,43,39,.07)_1px,transparent_1px,transparent_11px)] opacity-60" />
      <span className="relative px-2 text-center text-2xs font-medium tracking-wide text-ink-400">
        {label}
      </span>
    </div>
  );
}
