import { useEffect, useMemo, useState } from "react";
import { lineDiff } from "../../lib/diff";
import type { ArtifactPayload, Program, ToolCallPayload } from "../../lib/types";
import { useArtifactText } from "../../replay/useRun";
import { CodeView, DiffView } from "../CodeView";
import { Icon } from "../Icon";
import { ModelBadge } from "../ModelBadge";
import { Segmented } from "../PanelHeader";
import { Empty, OkMark, Pill } from "../ui";

export interface Iteration {
  seq: number;
  stage: string;
  p: ToolCallPayload;
}

interface Props {
  writing?: boolean;
  runId: string;
  codeArtifacts: ArtifactPayload[];
  programs: Program[] | null;
  iterations: Iteration[];
  animate: boolean;
}

const versionOf = (a: ArtifactPayload) => Number(/v(\d+)\.py$/.exec(a.name)?.[1] ?? 0);

const AUTHOR: Record<string, string> = {
  wonder: "Wonder",
  "wonder-harden": "Wonder · harden",
  "wonder-correction": "Wonder · correction",
  "spark-open-draft": "Spark Open draft",
  human: "human",
};

export function ProgramTab({ runId, codeArtifacts, programs, iterations, animate, writing }: Props) {
  const versions = useMemo(() => {
    const m = new Map<number, ArtifactPayload>();
    for (const a of codeArtifacts) m.set(versionOf(a), a);
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  }, [codeArtifacts]);
  const latest = versions.length ? versions[versions.length - 1][0] : null;
  const [sel, setSel] = useState<number | null>(null);
  const [mode, setMode] = useState<"code" | "diff">("code");
  const [streamed, setStreamed] = useState<Set<number>>(new Set());
  useEffect(() => {
    setSel(latest);
  }, [latest]);
  const v = sel ?? latest;
  const art = versions.find(([n]) => n === v)?.[1] ?? null;
  const meta = programs?.find((p) => p.version === v) ?? null;
  const code = useArtifactText(runId, art?.path) ?? meta?.code ?? null;
  const prevArt = versions.find(([n]) => n === (meta?.parent_version ?? (v ?? 0) - 1))?.[1] ?? null;
  const prevCode = useArtifactText(runId, prevArt?.path);
  const stream = animate && v === latest && v != null && !streamed.has(v);
  useEffect(() => {
    if (stream && v != null) {
      const id = window.setTimeout(() => setStreamed((s) => new Set(s).add(v)), 2400);
      return () => window.clearTimeout(id);
    }
  }, [stream, v]);

  if (!versions.length)
    return (
      <div className="grid h-full grid-cols-[1fr_300px] gap-4">
        {writing ? (
          <div className="flex flex-col gap-3">
            <div className="flex items-center gap-2 text-[12.5px] text-ink-200">
              <ModelBadge model="muse-wonder-1.0" size="xs" live />
              Writing <code className="font-mono text-wonder">run(scene, robot)</code> from the TaskSpec…
            </div>
            <div className="space-y-2 rounded-lg bg-ink-950/70 p-4 ring-1 ring-inset ring-ink-700/60">
              {[38, 62, 54, 71, 46, 30, 58].map((w, i) => (
                <div key={i} className="shimmer h-3 rounded bg-ink-800" style={{ width: `${w}%`, marginLeft: i && i < 6 ? 24 : 0 }} />
              ))}
            </div>
          </div>
        ) : (
          <Empty icon="code" title="Muse Wonder has not written a program yet" hint="It writes run(scene, robot), simulates it, and fixes it until the goal holds." />
        )}
        <IterationList iterations={iterations} />
      </div>
    );

  const diff = meta?.diff_from_parent || (prevCode && code ? lineDiff(prevCode, code, `v${(v ?? 1) - 1}.py`, `v${v}.py`) : "");
  const hasParent = v != null && v > (versions[0]?.[0] ?? 1);

  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 lg:grid-cols-[1fr_300px]">
      <div className="flex min-h-0 min-w-0 flex-col gap-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <ModelBadge model="muse-wonder-1.0" size="xs" />
          <div className="flex gap-1">
            {versions.map(([n]) => {
              const pm = programs?.find((p) => p.version === n);
              return (
                <button
                  key={n}
                  type="button"
                  onClick={() => setSel(n)}
                  className={`num flex items-center gap-1.5 rounded-md px-2 py-[3px] text-[11.5px] font-semibold ring-1 ring-inset transition ${
                    n === v ? "bg-wonder/15 text-wonder ring-wonder/40" : "text-ink-300 ring-ink-600 hover:text-ink-100"
                  }`}
                >
                  v{n}
                  {pm && <span className={`h-1.5 w-1.5 rounded-full ${pm.passed_demo ? "bg-ok" : "bg-bad"}`} />}
                </button>
              );
            })}
          </div>
          {meta && <span className="text-[11.5px] text-ink-400">{AUTHOR[meta.author] ?? meta.author}</span>}
          {meta && <Pill tone={meta.passed_demo ? "ok" : "bad"}>{meta.passed_demo ? "passes the demo" : "fails the demo"}</Pill>}
          <div className="ml-auto">
            <Segmented
              value={hasParent ? mode : "code"}
              onChange={setMode}
              options={[
                { value: "code", label: "Code" },
                ...(hasParent ? [{ value: "diff" as const, label: `Diff v${(v ?? 1) - 1} → v${v}` }] : []),
              ]}
            />
          </div>
        </div>
        {meta?.explanation && (
          <div className="flex items-start gap-1.5 text-[12.5px] text-ink-200">
            <Icon name="sparkle" size={13} className="mt-[3px] shrink-0 text-wonder" />
            {meta.explanation}
          </div>
        )}
        <div className="min-h-0 flex-1">
          {code == null ? (
            <div className="shimmer h-24 rounded-lg bg-ink-850" />
          ) : mode === "diff" && hasParent && diff ? (
            <DiffView diff={diff} maxHeight={9999} />
          ) : (
            <CodeView code={code} stream={stream} />
          )}
        </div>
      </div>
      <IterationList iterations={iterations} />
    </div>
  );
}

function IterationList({ iterations }: { iterations: Iteration[] }) {
  const sims = iterations.filter((i) => i.p.agent !== "redteam");
  const last = sims[sims.length - 1];
  return (
    <div className="min-h-0 min-w-0 overflow-y-auto scroll-thin">
      <div className="flex items-baseline justify-between">
        <span className="eyebrow">Synthesis loop</span>
        {last && (
          <span className="num text-[11.5px] text-ink-300">
            iteration <span className="text-[15px] font-semibold text-ink-50">{last.p.iteration}</span>
          </span>
        )}
      </div>
      {sims.length === 0 ? (
        <div className="mt-3 text-[12px] text-ink-400">Tool calls to the simulator appear here.</div>
      ) : (
        <ol className="relative ml-2 mt-2 space-y-2 border-l border-ink-700 pl-4">
          {sims.map((it) => {
            const r = it.p.result ?? { ok: true };
            const ok = r.clauses_total != null ? r.ok && r.clauses_passed === r.clauses_total : r.ok;
            return (
              <li key={it.seq} className="animate-slide-in relative">
                <span className={`absolute -left-[21px] top-[3px] h-2.5 w-2.5 rounded-full ring-4 ring-ink-850 ${ok ? "bg-ok" : "bg-bad"}`} />
                <div className="flex items-center gap-1.5 text-[12px]">
                  <span className="num text-ink-400">{it.p.iteration > 0 ? `#${it.p.iteration}` : "·"}</span>
                  <code className="font-mono text-[11.5px] text-ink-100">{it.p.tool}</code>
                  {it.p.args?.program != null && <span className="num text-[11px] text-wonder">v{String(it.p.args.program)}</span>}
                  {it.p.args?.draft != null && (
                    <span className="text-[11px] text-sparkopen">
                      draft {Number(it.p.args.draft) + 1}
                      {it.p.args.author ? ` · ${String(it.p.args.author).replace(/^Muse /, "")}` : ""}
                    </span>
                  )}
                  {it.p.agent !== "coder" && <span className="text-[10.5px] text-ink-400">{it.p.agent}</span>}
                  <span className="ml-auto">
                    {r.clauses_total != null ? (
                      <Pill tone={ok ? "ok" : "bad"}>
                        {r.clauses_passed}/{r.clauses_total}
                      </Pill>
                    ) : (
                      <OkMark ok={r.ok} size={10} />
                    )}
                  </span>
                </div>
                {r.error && <div className="mt-0.5 font-mono text-[10.5px] leading-snug text-bad/90">{r.error}</div>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
