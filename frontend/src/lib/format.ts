export function usd(v: number | null | undefined, digits?: number): string {
  if (v == null || Number.isNaN(v)) return "$0";
  const d = digits ?? (Math.abs(v) < 0.01 ? 4 : Math.abs(v) < 1 ? 3 : 2);
  return `$${v.toFixed(d)}`;
}

export function secs(v: number | null | undefined, digits = 1): string {
  if (v == null) return "–";
  return `${v.toFixed(digits)} s`;
}

export function clock(t: number): string {
  const s = Math.max(0, t);
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
}

export function pct(v: number | null | undefined, digits = 0): string {
  if (v == null) return "–";
  return `${(v * 100).toFixed(digits)}%`;
}

export function compact(n: number): string {
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(1)}k`;
  return `${n}`;
}

/** "31 Oct 2026, 14:32 IST" (the human's time zone is IST). */
export function istDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const s = d.toLocaleString("en-GB", {
    timeZone: "Asia/Kolkata",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${s} IST`;
}

export function tsMs(iso: string): number {
  return new Date(iso).getTime();
}

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
