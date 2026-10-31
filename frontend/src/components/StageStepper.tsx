import { modelInfo, STAGE_LABEL, STAGE_MODELS } from "../lib/models";
import { STAGES } from "../lib/types";
import type { StageInfo } from "../replay/state";
import { Icon } from "./Icon";
import { ModelBadge } from "./ModelBadge";

export function StageStepper({ stages, finalStatus }: { stages: Record<string, StageInfo>; finalStatus?: Record<string, string> | null }) {
  return (
    <div className="panel scroll-thin flex items-stretch overflow-x-auto px-2 py-2" data-testid="stepper">
      {STAGES.map((s, i) => {
        const st = stages[s];
        let status = st?.status ?? "todo";
        // a stage the finished run skipped (e.g. harden when nothing failed)
        if (status === "todo" && finalStatus?.[s] === "skipped" && stages.card?.status === "done") status = "skipped";
        const models = st?.models.length ? st.models : STAGE_MODELS[s] ?? [];
        const used = Boolean(st?.models.length);
        const accent = models.length ? modelInfo(models[0].id).color : "#94a3b8";
        const running = status === "running";
        const done = status === "done";
        return (
          <div key={s} data-stage={s} data-status={status} className="flex min-w-[112px] flex-1 items-stretch" title={st?.summary ? `${STAGE_LABEL[s]}: ${st.summary}${st.durationS != null ? ` (${st.durationS.toFixed(1)} s)` : ""}` : STAGE_LABEL[s]}>
            <div
              className={`relative flex w-full flex-col gap-1.5 rounded-xl px-2.5 py-2 transition-all duration-500 ${
                running ? "bg-ink-700/70" : done ? "bg-ink-800/40" : ""
              }`}
              style={running ? { boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${accent} 55%, transparent), 0 0 24px -8px ${accent}` } : undefined}
            >
              <div className="flex items-center gap-2">
                <StatusDot status={status} accent={accent} index={i + 1} />
                <span className={`truncate text-[12.5px] font-semibold ${status === "todo" || status === "skipped" ? "text-ink-400" : "text-ink-50"}`}>{STAGE_LABEL[s]}</span>
              </div>
              <div className="flex min-h-[18px] flex-wrap gap-1">
                {status === "skipped" ? (
                  <span className="text-[10px] font-medium text-ink-500">skipped · not needed</span>
                ) : models.length ? (
                  models.map((m) => <ModelBadge key={m.id + m.provider} model={m.id} provider={m.provider} size="xs" dim={!used} live={running} />)
                ) : (
                  <span className="text-[10px] font-medium text-ink-500">local</span>
                )}
              </div>
            </div>
            {i < STAGES.length - 1 && (
              <div className="flex w-2 shrink-0 items-center">
                <div className={`h-px w-full ${done ? "bg-ink-400" : "bg-ink-700"}`} />
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function StatusDot({ status, accent, index }: { status: string; accent: string; index: number }) {
  if (status === "done")
    return (
      <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-ok/15 text-ok ring-1 ring-ok/40">
        <Icon name="check" size={11} />
      </span>
    );
  if (status === "failed")
    return (
      <span className="flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full bg-bad/15 text-bad ring-1 ring-bad/40">
        <Icon name="x" size={11} />
      </span>
    );
  if (status === "running")
    return (
      <span className="relative flex h-[18px] w-[18px] shrink-0 items-center justify-center">
        <span className="absolute inset-0 animate-ping rounded-full opacity-40" style={{ background: accent }} />
        <span className="relative h-[10px] w-[10px] rounded-full" style={{ background: accent, boxShadow: `0 0 10px ${accent}` }} />
      </span>
    );
  return (
    <span className={`num flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full text-[9.5px] ring-1 ${status === "skipped" ? "text-ink-500 ring-ink-600 ring-dashed" : "text-ink-400 ring-ink-600"}`}>
      {index}
    </span>
  );
}
