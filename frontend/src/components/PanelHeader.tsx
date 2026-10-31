import type { ReactNode } from "react";

export function PanelHeader({ icon, title, sub, children }: { icon?: ReactNode; title: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b border-ink-700/60 px-3">
      {icon && <span className="text-ink-300">{icon}</span>}
      <span className="eyebrow !text-ink-200">{title}</span>
      {sub && <span className="truncate text-[11.5px] text-ink-400">{sub}</span>}
      <div className="ml-auto flex items-center gap-1.5">{children}</div>
    </div>
  );
}

export function Toggle({ on, onClick, children, title }: { on: boolean; onClick: () => void; children: ReactNode; title?: string }) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={`rounded-md px-2 py-[3px] text-[11px] font-semibold transition-colors ring-1 ring-inset ${
        on ? "bg-sparkopen/12 text-sparkopen ring-sparkopen/35" : "text-ink-400 ring-ink-600/70 hover:text-ink-200 hover:ring-ink-500"
      }`}
    >
      {children}
    </button>
  );
}

export function Segmented<T extends string | number>({ value, options, onChange }: { value: T; options: { value: T; label: ReactNode; title?: string }[]; onChange: (v: T) => void }) {
  return (
    <div className="inline-flex rounded-lg bg-ink-850 p-[3px] ring-1 ring-inset ring-ink-600/70">
      {options.map((o) => (
        <button
          type="button"
          key={String(o.value)}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-2.5 py-[3px] text-[11.5px] font-semibold transition-colors ${
            o.value === value ? "bg-ink-600 text-ink-50 shadow-sm" : "text-ink-400 hover:text-ink-200"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
