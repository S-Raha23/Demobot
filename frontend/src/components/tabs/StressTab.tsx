import { useMemo } from "react";
import { artifactUrl } from "../../lib/api";
import type { ArtifactPayload, Program, StressCase, StressReport, ToolCallPayload } from "../../lib/types";
import { useArtifactText } from "../../replay/useRun";
import { lineDiff } from "../../lib/diff";
import { DiffView } from "../CodeView";
import { LayoutSvg } from "../LayoutSvg";
import { ModelBadge } from "../ModelBadge";
import { Empty, OkMark } from "../ui";

const passed = (c: StressCase, which: "before" | "after") => {
  const r = c[which];
  return r ? r.ok && r.goal_ok : null;
};

function Gauge({ value, n, label, color }: { value: number | null; n: number; label: string; color: string }) {
  const k = value == null ? null : Math.round(value * n);
  const C = 2 * Math.PI * 26;
  return (
    <div className="flex items-center gap-3">
      <svg width="64" height="64" viewBox="0 0 64 64" className="-rotate-90">
        <circle cx="32" cy="32" r="26" fill="none" stroke="#1b2737" strokeWidth="6" />
        {value != null && (
          <circle cx="32" cy="32" r="26" fill="none" stroke={color} strokeWidth="6" strokeLinecap="round" strokeDasharray={`${C * value} ${C}`} style={{ transition: "stroke-dasharray 0.8s ease" }} />
        )}
      </svg>
      <div>
        <div className="eyebrow">{label}</div>
        <div className="num text-[26px] font-semibold leading-tight" style={{ color: value == null ? "#5b6b80" : color }}>
          {k == null ? "–" : `${k}/${n}`}
        </div>
      </div>
    </div>
  );
}

export function StressTab({
  runId,
  stress,
  codeArtifacts,
  programs,
  swarm,
  attempts,
  running,
}: {
  runId: string;
  stress: StressReport | null;
  codeArtifacts: ArtifactPayload[];
  programs: Program[] | null;
  swarm: { purpose: string; model: string; provider: string }[];
  attempts: ToolCallPayload[];
  running: boolean;
}) {
  const hardened = stress && stress.program_after != null && stress.program_after !== stress.program_before;
  const beforeArt = codeArtifacts.find((a) => a.name === `v${stress?.program_before}.py`);
  const afterArt = codeArtifacts.find((a) => a.name === `v${stress?.program_after}.py`);
  const beforeCode = useArtifactText(runId, hardened ? beforeArt?.path : null);
  const afterCode = useArtifactText(runId, hardened ? afterArt?.path : null);
  const diff = useMemo(() => {
    if (!hardened) return "";
    const pm = programs?.find((p) => p.version === stress!.program_after);
    if (pm?.diff_from_parent && pm.parent_version === stress!.program_before) return pm.diff_from_parent;
    return beforeCode && afterCode ? lineDiff(beforeCode, afterCode, `v${stress!.program_before}.py`, `v${stress!.program_after}.py`) : "";
  }, [hardened, programs, stress, beforeCode, afterCode]);

  if (!stress) {
    if (!running && !swarm.length)
      return <Empty icon="shield" title="The red team attacks after verification" hint="Six open-weight Spark Open personas invent layouts to break the program." />;
    const n = Math.max(12, attempts.length);
    const passedN = attempts.filter((a) => a.result?.ok).length;
    return (
      <div className="grid h-full min-h-0 grid-cols-1 gap-5 xl:grid-cols-[minmax(0,560px)_1fr]">
        <div className="min-w-0">
          <div className="mb-2 flex items-center gap-2">
            <span className="eyebrow">Red-team layouts</span>
            <ModelBadge model="meta-models/muse-spark-open-1026" size="xs" live={running} />
            <span className="text-[11px] text-ink-400">{attempts.length ? `simulating ${attempts.length}/${n}` : "personas are inventing layouts…"}</span>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {Array.from({ length: n }, (_, i) => {
              const a = attempts[i];
              return (
                <div key={i} className={`relative aspect-[16/10] overflow-hidden rounded-lg ring-1 transition-colors duration-500 ${a ? (a.result?.ok ? "bg-ok/[0.07] ring-ok/35" : "bg-bad/[0.08] ring-bad/45") : "shimmer bg-ink-850 ring-ink-700"}`}>
                  <span className="num absolute left-2 top-1.5 text-[10.5px] text-ink-400">{String(a?.result?.layout ?? a?.args?.layout ?? `red-${String(i).padStart(2, "0")}`)}</span>
                  {a && (
                    <span className="absolute inset-0 flex items-center justify-center">
                      <OkMark ok={Boolean(a.result?.ok)} size={16} />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
        <div className="min-w-0 space-y-4">
          <div className="rounded-xl bg-ink-800/50 px-4 py-3 ring-1 ring-inset ring-ink-700/60">
            <div className="eyebrow">Passing so far</div>
            <div className="num mt-1 text-[26px] font-semibold text-ink-50">
              {passedN}/{attempts.length || "–"}
            </div>
          </div>
          {swarm.length > 0 && <SwarmStrip swarm={swarm} />}
        </div>
      </div>
    );
  }
  const n = stress.cases.length;
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-5 xl:grid-cols-[minmax(0,560px)_1fr]">
      <div className="min-w-0">
        <div className="mb-2 flex items-center gap-2">
          <span className="eyebrow">Red-team layouts</span>
          <ModelBadge model="meta-models/muse-spark-open-1026" size="xs" />
          <span className="text-[11px] text-ink-400">hover a tile to see the robot's result</span>
        </div>
        <div className="grid grid-cols-4 gap-2" data-testid="stress-grid">
          {stress.cases.map((c, i) => {
            const b = passed(c, "before");
            const a = passed(c, "after");
            const final = a ?? b;
            const top = (c.after ?? c.before)?.renders?.top;
            return (
              <div
                key={c.layout.id + i}
                className={`group relative overflow-hidden rounded-lg bg-ink-850 ring-1 transition ${final ? "ring-ok/35" : "ring-bad/50"}`}
                title={c.rationale || c.layout.description}
              >
                <div className="relative aspect-[16/10]">
                  <LayoutSvg layout={c.layout} className="absolute inset-0 h-full w-full" />
                  {top && <img src={artifactUrl(runId, top)} alt="" loading="lazy" className="absolute inset-0 h-full w-full object-cover opacity-0 transition-opacity duration-300 group-hover:opacity-100" />}
                  <div className="absolute inset-x-0 bottom-0 flex items-center gap-1.5 bg-gradient-to-t from-black/80 to-transparent px-1.5 pb-1 pt-3">
                    <span className="truncate text-[10.5px] font-semibold capitalize text-ink-100">{c.persona.replace(/-/g, " ")}</span>
                    <span className="ml-auto flex items-center gap-1">
                      {a != null && b != null && b !== a && <Dot ok={b} small />}
                      <Dot ok={final} />
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap gap-6 rounded-xl bg-ink-800/50 px-4 py-3 ring-1 ring-inset ring-ink-700/60">
          <Gauge value={stress.robustness_before} n={n} label={`Before · v${stress.program_before}`} color={stress.robustness_before >= 1 ? "#34d399" : "#fbbf24"} />
          <Gauge value={stress.robustness_after ?? null} n={n} label={stress.program_after != null ? `After · v${stress.program_after}` : "After hardening"} color="#34d399" />
        </div>
        {!hardened && stress.robustness_before >= 1 && (
          <div className="text-[12.5px] text-ink-300">Every adversarial layout passed on the first try, so hardening was not needed.</div>
        )}
        {hardened && (
          <div>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="eyebrow">Hardening diff</span>
              <ModelBadge model="muse-wonder-1.0" size="xs" />
            </div>
            {diff ? <DiffView diff={diff} maxHeight={240} /> : <div className="shimmer h-24 rounded-lg bg-ink-850" />}
          </div>
        )}
        {stress.clusters.length > 0 && (
          <div>
            <div className="eyebrow mb-1.5">Failure clusters</div>
            <ul className="space-y-1 text-[12px] text-ink-200">
              {stress.clusters.map((c, i) => (
                <li key={i} className="rounded-md bg-bad/[0.06] px-2.5 py-1.5 ring-1 ring-inset ring-bad/20">
                  {String(c.label ?? c.name ?? c.error ?? JSON.stringify(c))}
                  {c.count != null && <span className="num ml-1 text-ink-400">× {String(c.count)}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
        {swarm.length > 0 && <SwarmStrip swarm={swarm} />}
      </div>
    </div>
  );
}

function Dot({ ok, small = false }: { ok: boolean | null; small?: boolean }) {
  const s = small ? 6 : 9;
  return <span className="inline-block rounded-full" style={{ width: s, height: s, background: ok == null ? "#5b6b80" : ok ? "#34d399" : "#f87171", opacity: small ? 0.6 : 1, boxShadow: small ? undefined : `0 0 8px ${ok ? "#34d399" : "#f87171"}` }} />;
}

function SwarmStrip({ swarm }: { swarm: { purpose: string; model: string; provider: string }[] }) {
  return (
    <div>
      <div className="eyebrow mb-1.5">The swarm</div>
      <div className="flex flex-wrap gap-1.5">
        {swarm.map((s) => (
          <span key={s.purpose} className="rounded-full bg-sparkopen/10 px-2 py-[2px] text-[11px] font-medium capitalize text-sparkopen ring-1 ring-inset ring-sparkopen/30">
            {s.purpose.replace(/^redteam:/, "").replace(/-/g, " ")}
          </span>
        ))}
      </div>
    </div>
  );
}
