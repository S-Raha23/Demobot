import { usd } from "../../lib/format";
import { modelInfo, providerLabel, providerOf } from "../../lib/models";
import type { CostTotals } from "../../replay/state";
import { Donut } from "../Donut";
import { ModelBadge } from "../ModelBadge";
import { Empty, Stat } from "../ui";

const PROVIDER_COLOR: Record<string, string> = { meta: "#60a5fa", baseten: "#2dd4bf", modal: "#5eead4", local: "#94a3b8" };

export function CostsTab({ cost, fixture }: { cost: CostTotals; fixture: boolean }) {
  if (cost.calls === 0) return <Empty icon="dollar" title="No model calls yet" hint="Every call is priced and ledgered by the gateway." />;
  const models = Object.entries(cost.byModel).sort((a, b) => b[1] - a[1]);
  const max = Math.max(...models.map((m) => m[1]), 1e-9);
  const providers = Object.entries(cost.byProvider).sort((a, b) => b[1] - a[1]);
  const share = cost.total > 0 ? cost.openWeight / cost.total : 0;
  const callShare = cost.calls > 0 ? cost.openCalls / cost.calls : 0;
  return (
    <div className="grid h-full grid-cols-1 gap-5 xl:grid-cols-[1.3fr_1fr]">
      <div className="min-w-0">
        <div className="mb-3 flex flex-wrap gap-8">
          <Stat label="Cost to learn" value={usd(cost.total, 3)} sub={fixture ? "simulated fixture prices" : "this run, all models"} />
          <Stat label="Model calls" value={cost.calls} sub={`${cost.cachedCalls} cache hits`} />
          <Stat label="Open-weight calls" value={`${cost.openCalls}/${cost.calls}`} sub="Spark Open on Baseten and Modal" color="#2dd4bf" />
        </div>
        <div className="eyebrow mb-2">Spend per model</div>
        <div className="space-y-2">
          {models.map(([id, v]) => {
            const m = modelInfo(id);
            return (
              <div key={id} className="grid grid-cols-[170px_1fr_72px] items-center gap-3">
                <ModelBadge model={id} provider={providerOf(id)} size="xs" />
                <div className="h-2.5 overflow-hidden rounded-full bg-ink-800">
                  <div className="h-full rounded-full" style={{ width: `${(v / max) * 100}%`, background: m.color, transition: "width 0.6s ease" }} />
                </div>
                <span className="num text-right text-[12px] text-ink-100">{usd(v, 4)}</span>
              </div>
            );
          })}
        </div>
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <div className="flex items-center gap-4">
          <Donut
            parts={[
              { value: cost.openWeight, color: "#2dd4bf", label: "open weights" },
              { value: Math.max(0, cost.total - cost.openWeight), color: "#33445c", label: "API models" },
            ]}
            center={`${Math.round(share * 100)}%`}
            sub="of spend"
          />
          <div className="space-y-1.5 text-[12px]">
            <div className="eyebrow">Open-weight share</div>
            <div className="text-ink-200">
              <span className="num font-semibold text-sparkopen">{Math.round(callShare * 100)}%</span> of calls,{" "}
              <span className="num font-semibold text-sparkopen">{Math.round(share * 100)}%</span> of spend
            </div>
            <div className="max-w-[220px] text-[11.5px] text-ink-400">The supervisor, red team and judge are the high-volume roles, and they all run on Muse Spark Open.</div>
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1.5">By provider</div>
          <div className="flex h-2.5 overflow-hidden rounded-full bg-ink-800">
            {providers.map(([p, v]) => (
              <div key={p} style={{ width: `${(v / (cost.total || 1)) * 100}%`, background: PROVIDER_COLOR[p] ?? "#94a3b8" }} title={`${providerLabel(p)} ${usd(v)}`} />
            ))}
          </div>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
            {providers.map(([p, v]) => (
              <span key={p} className="flex items-center gap-1.5 text-[12px] text-ink-200">
                <span className="h-2 w-2 rounded-full" style={{ background: PROVIDER_COLOR[p] ?? "#94a3b8" }} />
                {providerLabel(p)} <span className="num text-ink-400">{usd(v, 4)}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
