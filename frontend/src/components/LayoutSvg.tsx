import type { Layout } from "../lib/types";

/** A crisp top-down drawing of a layout in table cm (robot at the bottom). */
export function LayoutSvg({ layout, highlight, className = "" }: { layout: Layout; highlight?: Set<string>; className?: string }) {
  const wa = layout.work_area;
  const pad = 3;
  const x0 = wa.x0 - pad;
  const y0 = wa.y0 - pad;
  const w = wa.x1 - wa.x0 + 2 * pad;
  const h = wa.y1 - wa.y0 + 2 * pad;
  const [bx, by] = layout.robot_base_cm;
  return (
    <svg viewBox={`${x0} ${y0} ${w} ${h}`} className={className} preserveAspectRatio="xMidYMid meet">
      <defs>
        <pattern id="g2" width="5" height="5" patternUnits="userSpaceOnUse">
          <path d="M5 0H0V5" fill="none" stroke="rgba(148,163,184,0.09)" strokeWidth="0.25" />
        </pattern>
      </defs>
      <rect x={x0} y={y0} width={w} height={h} fill="#111925" />
      <rect x={wa.x0} y={wa.y0} width={wa.x1 - wa.x0} height={wa.y1 - wa.y0} fill="url(#g2)" stroke="rgba(94,234,212,0.35)" strokeWidth="0.35" strokeDasharray="1.2 0.8" rx="0.8" />
      {by < y0 + h + 30 && <circle cx={bx} cy={by} r={9} fill="rgba(226,232,240,0.08)" stroke="rgba(226,232,240,0.25)" strokeWidth="0.4" />}
      {layout.objects.map((o) => {
        const hot = highlight?.has(o.name);
        const container = o.role === "container" || o.hollow;
        const stroke = hot ? "#f87171" : "rgba(0,0,0,0.45)";
        if (o.shape === "cylinder" || o.shape === "sphere") {
          const r = Math.max(o.w, o.d) / 2;
          return (
            <g key={o.name}>
              <circle cx={o.x} cy={o.y} r={r} fill={container ? "rgba(255,255,255,0.04)" : o.color} stroke={container ? o.color : stroke} strokeWidth={container ? 1.1 : 0.35} />
            </g>
          );
        }
        return (
          <g key={o.name} transform={`translate(${o.x} ${o.y}) rotate(${o.yaw})`}>
            <rect
              x={-o.w / 2}
              y={-o.d / 2}
              width={o.w}
              height={o.d}
              rx={Math.min(o.w, o.d) * 0.2}
              fill={container ? "rgba(255,255,255,0.04)" : o.color}
              stroke={container ? o.color : stroke}
              strokeWidth={container ? 1.1 : 0.35}
            />
          </g>
        );
      })}
    </svg>
  );
}
