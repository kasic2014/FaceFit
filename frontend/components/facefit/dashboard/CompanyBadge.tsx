const brands: Record<string, { initial: string; bg: string; fg: string }> = {
  "네이버": { initial: "N", bg: "#03C75A", fg: "#ffffff" },
  "카카오": { initial: "K", bg: "#FEE500", fg: "#3A1D1D" },
  "삼성전자": { initial: "S", bg: "#1428A0", fg: "#ffffff" },
  "LG전자": { initial: "L", bg: "#A50034", fg: "#ffffff" },
  "현대자동차": { initial: "H", bg: "#002C5F", fg: "#ffffff" },
};

export function CompanyBadge({ name, size = 40 }: { name: string; size?: number }) {
  const brand = brands[name] ?? { initial: name.slice(0, 1), bg: "#7A9B7E", fg: "#ffffff" };
  return (
    <span
      className="grid shrink-0 place-items-center rounded-xl text-sm font-bold"
      style={{ width: size, height: size, backgroundColor: brand.bg, color: brand.fg }}
      aria-hidden="true"
    >
      {brand.initial}
    </span>
  );
}
