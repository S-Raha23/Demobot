import { clauseChips, clauseSentence, stepSentence } from "../../lib/goal";
import type { ClauseResult, CrossWatch, GoalClause, GroundedDemo, TaskSpec, Transcript } from "../../lib/types";
import { Icon } from "../Icon";
import { ModelBadge } from "../ModelBadge";
import { Empty, OkMark, Pill } from "../ui";

const CHIP: Record<string, string> = {
  quant: "bg-ink-600/70 text-ink-100",
  sel: "bg-spark/12 text-spark ring-1 ring-inset ring-spark/30",
  pred: "bg-wonder/12 text-wonder ring-1 ring-inset ring-wonder/30",
  target: "bg-sparkopen/12 text-sparkopen ring-1 ring-inset ring-sparkopen/30",
};

export function GoalChips({ clause, holds }: { clause: GoalClause; holds?: boolean | null }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {holds != null && <OkMark ok={holds} size={11} />}
      {clauseChips(clause).map((c, i) => (
        <span key={i} className={`rounded-md px-1.5 py-[2px] font-mono text-[11px] font-medium ${CHIP[c.kind]}`}>
          {c.text}
        </span>
      ))}
    </div>
  );
}

const ROLE_TONE: Record<string, "info" | "ok" | "neutral" | "warn"> = { moved: "info", container: "ok", reference: "warn", distractor: "neutral" };

export function SpecTab({ spec, cross, transcript, grounded }: { spec: TaskSpec | null; cross: CrossWatch | null; transcript: Transcript | null; grounded: GroundedDemo | null }) {
  if (!spec) return <Empty icon="eye" title="Spark 1.3 has not watched the clip yet" hint="The TaskSpec appears after the Watch stage." />;
  const realHolds = (i: number): ClauseResult | undefined => grounded?.real_world?.[i];
  const colorOf = (name: string) => grounded?.initial.find((o) => o.name === name)?.color;
  return (
    <div className="grid h-full grid-cols-1 gap-5 lg:grid-cols-[1.15fr_1fr]">
      <div className="min-w-0 space-y-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="eyebrow">What it understood</span>
            <ModelBadge model="muse-spark-1.3" size="xs" />
          </div>
          <div className="mt-1.5 text-[19px] font-semibold leading-snug tracking-tight text-ink-50">{spec.summary}</div>
          <div className="mt-1 flex items-start gap-1.5 text-[13px] text-ink-300">
            <Icon name="sparkle" size={13} className="mt-[3px] shrink-0 text-wonder" />
            <span>
              <span className="font-semibold text-ink-200">Generalises: </span>
              {spec.generalization}
            </span>
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1.5">Goal, as a checkable program</div>
          <div className="space-y-2">
            {spec.goal.map((g, i) => (
              <div key={i} className="rounded-lg bg-ink-800/60 px-3 py-2 ring-1 ring-inset ring-ink-700/60">
                <GoalChips clause={g} holds={realHolds(i)?.holds} />
                <div className="mt-1 text-[12.5px] text-ink-200">{clauseSentence(g)}</div>
                {realHolds(i) && (
                  <div className="mt-0.5 text-[11px] text-ink-400">On your real final table: {realHolds(i)!.holds ? "holds" : "fails"} (measured from SAM 3.1 tracks)</div>
                )}
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="eyebrow mb-1.5">Steps it saw</div>
          <ol className="space-y-1.5">
            {spec.steps.map((s, i) => (
              <li key={i} className="flex gap-2.5 text-[13px]">
                <span className="num mt-[1px] flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-spark/15 text-[10.5px] text-spark">{i + 1}</span>
                <div className="min-w-0">
                  <div className="text-ink-100">
                    {stepSentence(s)}{" "}
                    <span className="num text-[11px] text-ink-400">
                      {s.t_start.toFixed(1)}–{s.t_end.toFixed(1)} s
                    </span>
                  </div>
                  {s.evidence && <div className="text-[11.5px] italic text-ink-400">“{s.evidence}”</div>}
                </div>
              </li>
            ))}
          </ol>
        </div>
      </div>
      <div className="min-w-0 space-y-4">
        {cross && (
          <div className={`rounded-lg px-3 py-2.5 ring-1 ring-inset ${cross.agree ? "bg-ok/[0.06] ring-ok/25" : "bg-warn/[0.07] ring-warn/30"}`}>
            <div className="flex flex-wrap items-center gap-1.5 text-[12.5px] font-semibold">
              <OkMark ok={cross.agree} size={11} />
              <span className={cross.agree ? "text-ok" : "text-warn"}>{cross.agree ? "Two models agree" : "The models disagree"}</span>
              <ModelBadge model="muse-spark-1.3" size="xs" />
              <span className="text-ink-400">vs</span>
              <ModelBadge model="meta-models/Muse-Spark-Open-816B-A42B" provider="modal" size="xs" />
            </div>
            {cross.differences.length > 0 && (
              <ul className="mt-1.5 list-disc pl-5 text-[12px] text-ink-200">
                {cross.differences.map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            )}
            {cross.arbitration && <div className="mt-1 text-[12px] text-ink-300">Wonder arbitrated: {cross.arbitration}</div>}
          </div>
        )}
        <div>
          <div className="eyebrow mb-1.5">Objects</div>
          <div className="overflow-hidden rounded-lg ring-1 ring-inset ring-ink-700/60">
            {spec.objects.map((o, i) => (
              <div key={o.name} className={`flex items-center gap-2.5 px-3 py-1.5 text-[12.5px] ${i % 2 ? "bg-ink-800/30" : ""}`}>
                <span className="h-3 w-3 shrink-0 rounded-full ring-1 ring-white/20" style={{ background: colorOf(o.name) ?? "#64748b" }} />
                <span className="min-w-0 flex-1 truncate font-medium text-ink-100">{o.name}</span>
                <span className="num text-[11px] text-ink-400">
                  {o.est_size_cm[0]}×{o.est_size_cm[1]}×{o.est_height_cm} cm
                </span>
                <Pill tone={ROLE_TONE[o.role] ?? "neutral"}>{o.role}</Pill>
              </div>
            ))}
          </div>
        </div>
        {transcript && transcript.text && (
          <div>
            <div className="mb-1.5 flex items-center gap-2">
              <span className="eyebrow">Narration</span>
              <ModelBadge model="muse-voice-transcribe-1.0" size="xs" />
              <span className="text-[11px] text-ink-400">{transcript.languages.join(", ") || transcript.language}</span>
            </div>
            <div className="rounded-lg bg-voice/[0.06] px-3 py-2 text-[13.5px] text-ink-100 ring-1 ring-inset ring-voice/20">“{transcript.text}”</div>
          </div>
        )}
        {spec.uncertainties.length > 0 && (
          <div>
            <div className="eyebrow mb-1.5">Uncertainties</div>
            <ul className="list-disc pl-5 text-[12px] text-ink-300">
              {spec.uncertainties.map((u) => (
                <li key={u}>{u}</li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
