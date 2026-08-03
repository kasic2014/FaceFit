import type { ComponentPropsWithoutRef, ElementType, ReactNode } from "react";

export type PageContainerSize = "auth" | "narrow" | "compact" | "standard" | "wide" | "full";

type PageContainerProps<T extends ElementType = "div"> = {
  as?: T;
  children: ReactNode;
  className?: string;
  size?: PageContainerSize;
} & Omit<ComponentPropsWithoutRef<T>, "as" | "children" | "className">;

const sizeClasses: Record<PageContainerSize, string> = {
  auth: "max-w-[440px] md:max-w-[464px] lg:max-w-[496px]",
  narrow: "max-w-xl",
  compact: "max-w-[880px] lg:max-w-[896px]",
  standard: "max-w-[1200px]",
  wide: "max-w-[1360px]",
  full: "max-w-none",
};

export function PageContainer<T extends ElementType = "div">({
  as,
  children,
  className,
  size = "standard",
  ...props
}: PageContainerProps<T>) {
  const Component = as ?? "div";
  const classes = [
    "mx-auto w-full px-5 md:px-8 lg:px-12",
    sizeClasses[size],
    className,
  ].filter(Boolean).join(" ");

  return <Component className={classes} {...props}>{children}</Component>;
}
