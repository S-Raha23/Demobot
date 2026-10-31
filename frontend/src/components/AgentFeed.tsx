import { memo, useEffect, useRef, type ReactNode } from "react";
import { compact, usd } from "../lib/format";
import { STAGE_LABEL } from "../lib/models";
import type { AgentDecision, ArtifactPayload, MetricPayload, ModelCallPayload, QuestionPayload, RunEvent, StageEndPayload, ToolCallPayload } from "../lib/types";
import { useRun, useTicker } from "../replay/useRun";
import type { Inflight } from "../replay/state";
import { Icon } from "./Icon";
import { ModelBadge } from "./ModelBadge";
import { PanelHeader } from "./PanelHeader";
import { Empty, Pill } from "./ui";

function purposeText(p: string) {
  if (p.startsWith("track:")) return `track “${p.slice(6)}”`;
  const turn = /^synth:turn(\d+)$/.exec(p);
  if (turn) return `write / fix the program · turn ${turn[1]}`;
  const draft = /^draft:(\d+)$/.exec(p);
  if (draft) return `draft program ${Number(draft[1]) + 1}`;
  if (p.startsWith("redteam:")) return `red-team persona “${p.slice(8)}”`;
  const map: Record<string, string> = {
    watch: "watch the demo → TaskSpec",
    crosswatch: "second opinion on the clip",
    listen: "transcribe narration",
    synth: "write / fix the program",
    judge: "judge real vs. twin",
    segment_image: "segment the sim renders",
    harden: "harden the program",
    supervise: "supervisor decision",
    card: "illustrate the skill card",
  };
  return map[p] ?? p.replace(/_/g, " ");
}

function argsText(a: Record<string, unknown>) {
  return Object.entries(a ?? {})
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ");
}

const Row = memo(function Row({ e }: { e: RunEvent }) {
  const p = e.payload as Record<string, unknown>;
  switch (e.type) {
    case "stage_start":
      return (
        <div className="flex items-center gap-2 pb-0.5 pt-2.5">
          <span className="eyebrow !text-[10px] !text-ink-300">{STAGE_LABEL[e.stage] ?? e.stage}</span>
          <div className="h-px flex-1 bg-ink-700/70" />
        </div>
      );
    case "stage_end": {
      const s = p as unknown as StageEndPayload;
      return (
        <div className={`flex items-start gap-2 text-[12px] ${s.ok ? "text-ink-200" : "text-bad"}`}>
          <Icon name={s.ok ? "check" : "x"} size={13} className={`mt-[2px] shrink-0 ${s.ok ? "text-ok" : "text-bad"}`} />
          <span className="min-w-0 flex-1">{s.summary}</span>
          <span className="num shrink-0 text-[10.5px] text-ink-400">{s.duration_s?.toFixed(1)}s</span>
        </div>
      );
    }
    case "model_call": {
      const m = p as unknown as ModelCallPayload;
      return (
        <div className="rounded-lg bg-ink-800/70 px-2.5 py-2 ring-1 ring-inset ring-ink-700/70">
          <div className="flex items-center gap-2">
            <ModelBadge model={e.model ?? ""} provider={e.provider} size="xs" />
            <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-ink-100">{purposeText(m.purpose)}</span>
            <span className="num shrink-0 text-[11px] text-ink-200">{usd(e.cost_usd ?? 0)}</span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px] text-ink-400">
            <span className="num">{((e.latency_ms ?? 0) / 1000).toFixed(1)} s</span>
            {e.tokens && (e.tokens.in > 0 || e.tokens.out > 0) && (
              <span className="num">
                {compact(e.tokens.in)} in · {compact(e.tokens.out)} out
              </span>
            )}
            {m.frames ? <span className="num">{m.frames} frames</span> : null}
            {m.images ? <span className="num">{m.images} images</span> : null}
            {m.audio_s ? <span className="num">{m.audio_s.toFixed(1)} s audio</span> : null}
            {m.open_weight && <span className="text-sparkopen">open weights</span>}
            {e.cached && <span className="text-spark">cache hit · $0</span>}
            {m.note === "incomplete" && <span className="text-warn">billed retry</span>}
            {m.fixture && <span className="text-ink-500">simulated</span>}
          </div>
        </div>
      );
    }
    case "tool_call": {
      const t = p as unknown as ToolCallPayload;
      const r = t.result ?? { ok: true };
      return (
        <div className="rounded-lg px-2.5 py-1.5 ring-1 ring-inset ring-ink-700/60">
          <div className="flex items-center gap-2 text-[11.5px]">
            <Icon name="tool" size={13} className="shrink-0 text-ink-300" />
            <span className="font-semibold text-ink-300">{t.agent}</span>
            {t.iteration > 0 && <span className="num text-[10.5px] text-ink-400">iter {t.iteration}</span>}
            <code className="min-w-0 flex-1 truncate font-mono text-[11px] text-ink-100">
              {t.tool}({argsText(t.args)})
            </code>
            {r.clauses_total != null && (
              <Pill tone={r.ok ? "ok" : "bad"}>
                {r.clauses_passed}/{r.clauses_total} clauses
              </Pill>
            )}
            {r.clauses_total == null && <Icon name={r.ok ? "check" : "x"} size={13} className={r.ok ? "text-ok" : "text-bad"} />}
          </div>
          {r.error && <div className="mt-1 truncate pl-[21px] font-mono text-[10.5px] text-bad/90">{r.error}</div>}
        </div>
      );
    }
    case "decision": {
      const d = p as unknown as AgentDecision;
      return (
        <div className="rounded-lg bg-sparkopen/[0.06] px-2.5 py-2 ring-1 ring-inset ring-sparkopen/25">
          <div className="flex items-center gap-2 text-[11.5px]">
            <Icon name="brain" size={13} className="text-sparkopen" />
            <span className="font-semibold capitalize text-sparkopen">{d.agent}</span>
            <code className="font-mono text-[11px] text-ink-200">{d.tool}</code>
            {d.cost_usd > 0 && <span className="num ml-auto text-[10.5px] text-ink-300">{usd(d.cost_usd)}</span>}
          </div>
          <div className="mt-1 text-[12px] leading-snug text-ink-100">{d.reasoning_summary}</div>
          {d.result && <div className="mt-0.5 text-[11px] text-ink-400">→ {d.result}</div>}
        </div>
      );
    }
    case "question": {
      const q = p as unknown as QuestionPayload;
      return (
        <div className="rounded-lg bg-spark/[0.07] px-2.5 py-2 ring-1 ring-inset ring-spark/30">
          <div className="flex items-center gap-2 text-[12px] font-medium text-ink-50">
            <Icon name="chat" size={13} className="text-spark" /> {q.text}
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {q.options.map((o) => (
              <button key={o} type="button" className="btn !px-2 !py-1 !text-[11px]" disabled title="Answers go to live runs">
                {o}
              </button>
            ))}
            <button type="button" className="btn !px-2 !py-1" disabled aria-label="Answer by voice">
              <Icon name="mic" size={12} />
            </button>
          </div>
        </div>
      );
    }
    case "artifact": {
      const a = p as unknown as ArtifactPayload;
      const icon = a.kind === "video" ? "video" : a.kind === "image" ? "camera" : a.kind === "code" ? "code" : a.kind === "trajectory" ? "cube" : "file";
      return (
        <div className="flex items-center gap-2 pl-0.5 text-[11.5px] text-ink-300">
          <Icon name={icon} size={12} className="shrink-0 text-ink-400" />
          <span className="truncate">{a.label}</span>
          <span className="truncate font-mono text-[10px] text-ink-500">{a.name}</span>
        </div>
      );
    }
    case "metric": {
      const m = p as unknown as MetricPayload;
      const v = typeof m.value === "boolean" ? (m.value ? "yes" : "no") : typeof m.value === "number" && m.name.startsWith("robustness") ? `${Math.round(m.value * 100)}%` : String(m.value);
      return (
        <div className="flex items-center gap-2 pl-0.5 text-[11.5px] text-ink-300">
          <Icon name="target" size={12} className="shrink-0 text-ink-400" />
          <span>{m.name.replace(/_/g, " ")}</span>
          <span className="num font-semibold text-ink-100">
            {v}
            {m.unit ? ` ${m.unit}` : ""}
          </span>
        </div>
      );
    }
    case "log": {
      if (p.heartbeat) return null;
      if (p.fallback)
        return (
          <div className="rounded-lg bg-warn/[0.07] px-2.5 py-1.5 text-[11.5px] text-warn ring-1 ring-inset ring-warn/30">
            <b>Fallback</b> for {String(p.purpose)}: {String(p.from)} → {String(p.to)} <span className="text-warn/70">({String(p.code)})</span>
            {p.message ? <div className="text-[11px] text-warn/80">{String(p.message)}</div> : null}
          </div>
        );
      if (p.retry)
        return (
          <div className="pl-0.5 text-[11.5px] text-warn/90">
            Retry {String(p.retry)} for {String(p.purpose)}: {String(p.error)}
          </div>
        );
      if (p.agent)
        return (
          <div className="flex gap-2 rounded-lg bg-wonder/[0.06] px-2.5 py-1.5 ring-1 ring-inset ring-wonder/20">
            <Icon name="chat" size={13} className="mt-[2px] shrink-0 text-wonder" />
            <div className="min-w-0 text-[12px] leading-snug text-ink-100">
              <span className="mr-1 font-semibold capitalize text-wonder">{String(p.agent)}</span>
              {String(p.message ?? "")}
            </div>
          </div>
        );
      return <div className="pl-0.5 text-[11.5px] text-ink-300">{String(p.message ?? "")}</div>;
    }
    case "error":
      return (
        <div className="rounded-lg bg-bad/[0.08] px-2.5 py-1.5 text-[12px] text-bad ring-1 ring-inset ring-bad/30">
          <b>{String(p.code)}</b> {String(p.message)}
        </div>
      );
    default:
      return null;
  }
});

function InflightCard({ item, now }: { item: Inflight; now: number }) {
  const el = Math.max(0, (now - item.startMs) / 1000);
  return (
    <div className="shimmer relative overflow-hidden rounded-lg bg-ink-750/80 px-2.5 py-2 ring-1 ring-inset ring-ink-500/60">
      <div className="flex items-center gap-2">
        <ModelBadge model={item.model} size="xs" live />
        <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-ink-50">{purposeText(item.purpose)}</span>
        <span className="num flex items-center gap-1 text-[12px] text-ink-50">
          <Icon name="clock" size={12} className="text-ink-300" />
          {el.toFixed(1)} s
        </span>
      </div>
      <div className="mt-1 text-[10.5px] text-ink-400">in flight · heartbeat every 5 s</div>
    </div>
  );
}

export function AgentFeed({ footer }: { footer?: ReactNode }) {
  const { view, clock, finished } = useRun();
  const scroller = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const active = view.inflight.length > 0 || Boolean(view.current);
  useTicker(active && !finished, 10);
  const now = clock.recordedNow();
  const items = view.events.filter((e) => !(e.type === "log" && (e.payload as { heartbeat?: boolean }).heartbeat));

  useEffect(() => {
    const el = scroller.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [items.length, view.inflight.length]);

  const stageElapsed = view.current && view.stages[view.current]?.startMs ? (now - view.stages[view.current].startMs!) / 1000 : null;

  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden" data-testid="agent-feed">
      <PanelHeader icon={<Icon name="sparkle" size={15} />} title="Agent feed" sub={`${view.cost.calls} model calls`} />
      <div
        ref={scroller}
        className="scroll-thin min-h-0 flex-1 space-y-1.5 overflow-y-auto px-3 pb-3"
        onScroll={(e) => {
          const el = e.currentTarget;
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
        }}
      >
        {items.length === 0 && <Empty icon="sparkle" title="Starting the run" hint="Events stream in as the agents work." />}
        {items.map((e) => (
          <div key={e.seq} className="animate-slide-in">
            <Row e={e} />
          </div>
        ))}
        {view.inflight.map((i) => (
          <InflightCard key={i.key} item={i} now={now} />
        ))}
        {view.current && view.inflight.length === 0 && stageElapsed != null && (
          <div className="flex items-center gap-2 pl-0.5 pt-1 text-[11.5px] text-ink-400">
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-ink-300" />
            {STAGE_LABEL[view.current]} working · <span className="num">{stageElapsed.toFixed(1)} s</span>
          </div>
        )}
      </div>
      {footer}
    </div>
  );
}
