import type { ReactNode } from "react";
import { Icon } from "./Icon";

export function Pill({ children, tone = "neutral", className = "" }: { children: ReactNode; tone?: "neutral" | "ok" | "bad" | "warn" | "info"; className?: string }) {
  const tones: Record<string, string> = {
    neutral: "text-ink-200 bg-ink-700/60 ring-ink-500/50",
    ok: "text-ok bg-ok/10 ring-ok/30",
    bad: "text-bad bg-bad/10 ring-bad/30",
    warn: "text-warn bg-warn/10 ring-warn/30",
    info: "text-spark bg-spark/10 ring-spark/30",
  };
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-[2px] text-[11px] font-semibold ring-1 ring-inset whitespace-nowrap ${tones[tone]} ${className}`}>{children}</span>;
}

export function OkMark({ ok, size = 14 }: { ok: boolean | null | undefined; size?: number }) {
  if (ok == null) return <span className="inline-block rounded-full bg-ink-600" style={{ width: size, height: size }} />;
  return (
    <span
      className={`inline-flex items-center justify-center rounded-full ${ok ? "bg-ok/15 text-ok" : "bg-bad/15 text-bad"}`}
      style={{ width: size + 6, height: size + 6 }}
    >
      <Icon name={ok ? "check" : "x"} size={size - 2} />
    </span>
  );
}

export function Empty({ icon = "clock", title, hint }: { icon?: string; title: string; hint?: string }) {
  return (
    <div className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 p-6 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-ink-700/60 text-ink-300 ring-1 ring-ink-600">
        <Icon name={icon} size={18} />
      </div>
      <div className="text-[13px] font-medium text-ink-200">{title}</div>
      {hint && <div className="max-w-xs text-[12px] text-ink-400">{hint}</div>}
    </div>
  );
}

export function Spinner({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" className="animate-spin" aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke={color} strokeOpacity="0.2" strokeWidth="3" />
      <path d="M21 12a9 9 0 00-9-9" fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Stat({ label, value, sub, color }: { label: string; value: ReactNode; sub?: ReactNode; color?: string }) {
  return (
    <div className="min-w-0">
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-[22px] font-semibold leading-none" style={{ color }}>
        {value}
      </div>
      {sub && <div className="mt-1 text-[11.5px] text-ink-400">{sub}</div>}
    </div>
  );
}
