import { modelInfo, providerLabel, providerOf } from "../lib/models";

interface Props {
  model: string;
  provider?: string | null;
  size?: "xs" | "sm" | "md";
  dim?: boolean;
  live?: boolean;
  showProvider?: boolean;
}

/** The model badge reused everywhere: accent colour per model plus a provider suffix. */
export function ModelBadge({ model, provider, size = "sm", dim = false, live = false, showProvider = true }: Props) {
  const m = modelInfo(model);
  const p = providerLabel(providerOf(model, provider));
  const pad = size === "xs" ? "px-1.5 py-[1px] text-[10px]" : size === "md" ? "px-2.5 py-1 text-[12.5px]" : "px-2 py-[3px] text-[11px]";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full font-semibold whitespace-nowrap ${pad} transition-opacity`}
      style={{
        color: m.color,
        background: `color-mix(in srgb, ${m.color} ${dim ? 6 : 13}%, transparent)`,
        boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${m.color} ${dim ? 18 : 38}%, transparent)`,
        opacity: dim ? 0.5 : 1,
      }}
      title={`${m.long} · ${p}`}
    >
      <span
        className={`inline-block rounded-full ${live ? "animate-pulse-soft" : ""}`}
        style={{ width: size === "xs" ? 5 : 6, height: size === "xs" ? 5 : 6, background: m.color, boxShadow: live ? `0 0 10px ${m.color}` : undefined }}
      />
      {m.label}
      {showProvider && <span className="font-medium opacity-60">· {p}</span>}
    </span>
  );
}
