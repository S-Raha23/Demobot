import { artifactUrl } from "../../lib/api";
import { CodeView } from "../CodeView";
import { Icon } from "../Icon";
import { ModelBadge } from "../ModelBadge";
import { Pill } from "../ui";

export interface ForgeRecord {
  request: { name: string; signature: string; purpose: string; evidence: string };
  promoted: boolean;
  code: string;
  tests: string;
  pass_rate: number;
  regression: { checked?: number; worse?: string[]; ok?: boolean };
  explanation: string;
  turns: number;
  versions: { kind: string; version: number; code: string }[];
  grid: { layout: string; passed: boolean; skipped?: boolean; top?: string | null }[];
  reason: string;
  skill_api_version: string;
}

/** Skill Forge (docs/11 F1): the gap, the invented skill, its tests, the regression gate, promotion. */
export function ForgeTab({ runId, rec }: { runId: string; rec: ForgeRecord | null }) {
  if (!rec) return <div className="p-4 text-[13px] text-ink-400">No skill was forged in this run.</div>;
  const passed = rec.grid.filter((c) => c.passed).length;
  return (
    <div className="space-y-3 p-4">
      <div className={`rounded-xl p-3.5 ring-1 ring-inset ${rec.promoted ? "bg-ok/[0.08] ring-ok/35" : "bg-warn/[0.08] ring-warn/35"}`}>
        <div className="flex flex-wrap items-center gap-2">
          <Icon name={rec.promoted ? "check" : "alert"} size={15} className={rec.promoted ? "text-ok" : "text-warn"} />
          <span className="text-[14px] font-semibold text-ink-50">
            {rec.promoted ? `DemoBot invented ${rec.request.name} and added it to its toolkit` : `${rec.request.name} was not promoted`}
          </span>
          <Pill tone="neutral">skill API v{rec.skill_api_version}</Pill>
          <ModelBadge model="muse-wonder-1.0" size="xs" />
        </div>
        {!rec.promoted && rec.reason && <div className="mt-1 text-[12px] text-ink-300">{rec.reason}</div>}
        {rec.explanation && <div className="mt-1 text-[12px] text-ink-300">{rec.explanation}</div>}
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <div className="panel p-3.5">
          <div className="eyebrow">Capability gap</div>
          <div className="mt-1 text-[13px] text-ink-100">{rec.request.evidence}</div>
        </div>
        <div className="panel p-3.5">
          <div className="eyebrow">The new skill</div>
          <div className="mt-1 font-mono text-[12.5px] text-wonder">{rec.request.signature}</div>
          <div className="mt-1 text-[12.5px] text-ink-300">{rec.request.purpose}</div>
        </div>
      </div>

      <div className="panel p-3.5">
        <div className="mb-2 flex items-center gap-2">
          <span className="eyebrow">Tests on fresh randomised layouts</span>
          <Pill tone={passed >= 9 ? "ok" : "warn"}>
            {passed}/{rec.grid.length} passed
          </Pill>
          <span className="text-[11.5px] text-ink-400">{rec.turns} Wonder turns</span>
        </div>
        <div className="grid grid-cols-5 gap-1.5 sm:grid-cols-10" data-testid="forge-grid">
          {rec.grid.map((c) => (
            <div key={c.layout} title={`${c.layout}: ${c.skipped ? "skipped" : c.passed ? "passed" : "failed"}`}
              className={`relative aspect-square overflow-hidden rounded-md ring-1 ring-inset ${c.passed ? "bg-ok/15 ring-ok/40" : "bg-bad/15 ring-bad/40"}`}>
              {c.top && <img src={artifactUrl(runId, c.top)} alt={`test layout ${c.layout}`} className="h-full w-full object-cover opacity-80" />}
              <Icon name={c.passed ? "check" : "x"} size={13} className={`absolute right-1 top-1 ${c.passed ? "text-ok" : "text-bad"}`} />
            </div>
          ))}
        </div>
      </div>

      <div className="panel p-3.5">
        <div className="flex items-center gap-2">
          <span className="eyebrow">Regression check</span>
          {rec.regression.checked != null && (
            <Pill tone={rec.regression.ok ? "ok" : "bad"}>
              {rec.regression.ok ? "no library skill got worse" : `${rec.regression.worse?.length} got worse`}
            </Pill>
          )}
        </div>
        <div className="mt-1 text-[12px] text-ink-400">
          Every learned skill re-ran on its demo layout and 3 random layouts with the new skill available ({rec.regression.checked ?? 0} runs).
        </div>
      </div>

      {rec.code && (
        <div className="panel overflow-hidden">
          <div className="flex items-center gap-2 px-3.5 pt-3">
            <span className="eyebrow">Code</span>
            <span className="text-[11.5px] text-ink-400">{rec.versions.filter((v) => v.kind === "skill").length} versions</span>
          </div>
          <CodeView code={rec.code} />
        </div>
      )}
    </div>
  );
}
