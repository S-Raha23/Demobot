export function Donut({ parts, size = 120, thickness = 14, center, sub }: { parts: { value: number; color: string; label: string }[]; size?: number; thickness?: number; center?: string; sub?: string }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  const r = (size - thickness) / 2;
  const C = 2 * Math.PI * r;
  let acc = 0;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#1b2737" strokeWidth={thickness} />
        {parts.map((p) => {
          const len = (p.value / total) * C;
          const el = (
            <circle
              key={p.label}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={p.color}
              strokeWidth={thickness}
              strokeDasharray={`${Math.max(0, len - 1.5)} ${C}`}
              strokeDashoffset={-acc}
              style={{ transition: "stroke-dasharray 0.6s ease, stroke-dashoffset 0.6s ease" }}
            >
              <title>{p.label}</title>
            </circle>
          );
          acc += len;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        {center && <div className="num text-[20px] font-semibold text-ink-50">{center}</div>}
        {sub && <div className="text-[10.5px] text-ink-400">{sub}</div>}
      </div>
    </div>
  );
}
