import { cn } from "@/lib/utils";

export function Logo({
  size = "lg",
  textClassName,
  className,
}: {
  size?: "lg" | "sm";
  textClassName?: string;
  className?: string;
}) {
  const isLg = size === "lg";

  return (
    <div className={cn("flex items-center", isLg ? "gap-2" : "gap-2", className)}>
      <div
        className={cn(
          "relative flex-none rounded-[7px] bg-gradient-to-br from-moss-500 to-moss-900",
          isLg ? "size-[34px] rounded-[9px]" : "size-[26px]"
        )}
      >
        <div
          className={cn(
            "absolute rounded-full border-white",
            isLg ? "inset-2 border-[1.5px]" : "inset-1.5 border-[1.2px]"
          )}
        />
        <div
          className={cn(
            "absolute border-t-sunset-300 border-l-sunset-300",
            isLg ? "top-1.5 left-1.5 size-1.5 border-t-[1.5px] border-l-[1.5px]" : "top-1 left-1 size-[5px] border-t-[1.2px] border-l-[1.2px]"
          )}
        />
        <div
          className={cn(
            "absolute border-b-sunset-300 border-r-sunset-300",
            isLg ? "bottom-1.5 right-1.5 size-1.5 border-b-[1.5px] border-r-[1.5px]" : "bottom-1 right-1 size-[5px] border-b-[1.2px] border-r-[1.2px]"
          )}
        />
      </div>
      <div
        className={cn(
          "font-heading font-bold tracking-[-0.01em] text-ink-900",
          isLg ? "text-xl" : "text-lg",
          textClassName
        )}
      >
        Face <span className="text-moss-700">Fit</span>
      </div>
    </div>
  );
}
