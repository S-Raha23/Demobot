import { useEffect, useRef, useState } from "react";
import { robotToVideo, type Anchor, type SkillSpan } from "../lib/sync";
import type { Contact, MotionSegment, Segment, Step, TwinEvent } from "../lib/types";
import type { MediaClock } from "../replay/mediaClock";
import { Icon } from "./Icon";

interface Props {
  clock: MediaClock;
  duration: number;
  steps: Step[];
  segments: MotionSegment[];
  contacts: Contact[];
  narration: Segment[];
  skills: SkillSpan[];
  robotEvents: TwinEvent[];
  anchors: Anchor[] | null;
  colorOf: (name: string) => string;
  robotLabel?: string | null;
}

const SKILL_COLOR: Record<string, string> = {
  pick: "#fbbf24",
  place_in: "#2dd4bf",
  place_at: "#2dd4bf",
  place_next_to: "#2dd4bf",
  home: "#64748b",
};

const LANE = "relative h-[22px] rounded-md bg-ink-850/80 ring-1 ring-inset ring-ink-700/60";

function stepText(s: Step) {
  const rel = s.relation ? s.relation.replace(/_/g, " ") : s.action === "place_in" ? "into" : "at";
  return `${s.object} ${rel === "into" ? "→" : `· ${rel}`} ${s.target ?? ""}`.trim();
}

export function Timeline(p: Props) {
  const { clock, duration } = p;
  const trackRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLDivElement>(null);
  const timeRef = useRef<HTMLSpanElement>(null);
  const [playing, setPlaying] = useState(clock.playing);
  const pct = (t: number) => `${(Math.max(0, Math.min(duration, t)) / Math.max(duration, 1e-6)) * 100}%`;
  const R = (t: number) => (p.anchors ? robotToVideo(p.anchors, t) : t);

  useEffect(() => {
    return clock.subscribe((t) => {
      if (headRef.current) headRef.current.style.left = pct(t);
      if (timeRef.current) timeRef.current.textContent = `${t.toFixed(1)}`;
      if (clock.playing !== playing) setPlaying(clock.playing);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clock, duration, playing]);

  const seekFrom = (clientX: number) => {
    const r = trackRef.current!.getBoundingClientRect();
    clock.seek(((clientX - r.left) / r.width) * duration);
  };

  const onDown = (e: React.PointerEvent) => {
    if (duration <= 0) return;
    const was = clock.playing;
    clock.setPlaying(false);
    seekFrom(e.clientX);
    const move = (ev: PointerEvent) => seekFrom(ev.clientX);
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      clock.setPlaying(was);
      setPlaying(was);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  const ticks: number[] = [];
  const stepT = duration > 30 ? 5 : duration > 12 ? 2 : 1;
  for (let t = stepT; t <= duration - stepT * 0.3; t += stepT) ticks.push(t);

  const disabled = duration <= 0;

  return (
    <div className="panel shrink-0 px-3 py-2.5" data-testid="timeline">
      <div className="grid grid-cols-[104px_minmax(0,1fr)] gap-x-3">
        {/* header row: transport + ruler */}
        <div className="flex h-7 items-center gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              clock.setPlaying(!clock.playing);
              setPlaying(clock.playing);
            }}
            className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-100 text-ink-900 transition hover:bg-white disabled:opacity-30"
            aria-label={playing ? "Pause" : "Play"}
          >
            <Icon name={playing ? "pause" : "play"} size={12} />
          </button>
          <div className="num whitespace-nowrap text-[12px] text-ink-100">
            <span ref={timeRef}>0.0</span>
            <span className="text-ink-400"> / {duration.toFixed(1)}s</span>
          </div>
        </div>
        <div ref={trackRef} className="relative row-span-4 cursor-pointer select-none" onPointerDown={onDown}>
          <div className="relative h-7">
            {ticks.map((t) => (
              <div key={t} className="absolute top-[7px] flex -translate-x-1/2 flex-col items-center" style={{ left: pct(t) }}>
                <span className="num text-[9.5px] text-ink-400">{t}s</span>
                <span className="mt-[1px] h-[4px] w-px bg-ink-600" />
              </div>
            ))}
          </div>
          <div className="space-y-[6px]">
            {/* human lane */}
            <div className={LANE}>
              {p.steps.map((s, i) => (
                <div
                  key={`st${i}`}
                  className="absolute inset-y-[2px] overflow-hidden rounded-[5px] border border-dashed border-spark/50 bg-spark/[0.07] px-1.5"
                  style={{ left: pct(s.t_start), width: `calc(${pct(s.t_end)} - ${pct(s.t_start)})` }}
                  title={`Spark 1.3 step ${i + 1}: ${stepText(s)} (${s.t_start.toFixed(1)}–${s.t_end.toFixed(1)} s)`}
                >
                  <span className="relative z-10 block truncate text-[10.5px] font-semibold leading-[16px] text-spark">
                    {i + 1}. {stepText(s)}
                  </span>
                </div>
              ))}
              {p.segments.map((m, i) => (
                <div
                  key={`sg${i}`}
                  className="absolute bottom-[2px] h-[3px] rounded-full"
                  style={{ left: pct(m.t0), width: `calc(${pct(m.t1)} - ${pct(m.t0)})`, background: p.colorOf(m.object), boxShadow: `0 0 8px ${p.colorOf(m.object)}` }}
                  title={`measured: ${m.object} moved ${m.t0.toFixed(2)}–${m.t1.toFixed(2)} s`}
                />
              ))}
              {p.contacts.map((c, i) => (
                <Diamond key={`c${i}`} left={pct(c.t)} color={p.colorOf(c.object)} filled={c.type === "grasp"} title={`${c.type} ${c.object} at ${c.t.toFixed(2)} s (SAM contact)`} />
              ))}
            </div>
            {p.narration.length > 0 && (
              <div className="relative h-[8px]">
                {p.narration.map((n, i) => (
                  <div
                    key={i}
                    className="absolute inset-y-[1px] rounded-full bg-voice/50"
                    style={{ left: pct(n.t0), width: `calc(${pct(n.t1)} - ${pct(n.t0)})` }}
                    title={`"${n.text}"`}
                  />
                ))}
              </div>
            )}
            {/* robot lane */}
            <div className={LANE}>
              {p.skills.length === 0 && (
                <span className="absolute inset-0 flex items-center px-2 text-[10.5px] text-ink-500">{p.robotLabel ?? "The robot program has not run yet"}</span>
              )}
              {p.skills.map((s, i) => {
                const a = R(s.t0);
                const b = R(s.t1);
                const col = SKILL_COLOR[s.skill] ?? "#94a3b8";
                return (
                  <div
                    key={`sk${i}`}
                    className="absolute inset-y-[2px] overflow-hidden rounded-[5px] px-1.5"
                    style={{
                      left: pct(a),
                      width: `calc(${pct(b)} - ${pct(a)} - 2px)`,
                      background: `color-mix(in srgb, ${col} ${s.ok ? 14 : 30}%, transparent)`,
                      boxShadow: `inset 0 0 0 1px color-mix(in srgb, ${s.ok ? col : "#f87171"} 45%, transparent)`,
                    }}
                    title={`${s.label} · sim ${s.t0.toFixed(1)}–${s.t1.toFixed(1)} s`}
                  >
                    <span className="block truncate font-mono text-[10px] font-medium leading-[16px]" style={{ color: col }}>
                      {s.label}
                    </span>
                  </div>
                );
              })}
              {p.robotEvents
                .filter((e) => e.type === "grasp" || e.type === "release")
                .map((e, i) => (
                  <Diamond key={`r${i}`} left={pct(R(e.t))} color={e.object ? p.colorOf(e.object) : "#e2e8f0"} filled={e.type === "grasp"} title={`robot ${e.type} ${e.object ?? ""}`} />
                ))}
            </div>
          </div>
          {/* playhead */}
          {!disabled && (
            <div ref={headRef} className="pointer-events-none absolute bottom-[-2px] top-[20px] z-20 w-0" style={{ left: "0%" }}>
              <div className="absolute -left-[5px] -top-[1px] h-[10px] w-[10px] rotate-45 rounded-[2px] bg-ink-50 shadow" />
              <div className="absolute bottom-0 left-[-0.75px] top-0 w-[1.5px] bg-ink-50/90 shadow-[0_0_8px_rgba(255,255,255,0.5)]" />
            </div>
          )}
        </div>
        <LaneLabel icon="hand" text="Human" sub="video" first />
        {p.narration.length > 0 && <div className="mt-[6px] flex h-[8px] items-center pl-[18px] text-[9.5px] font-semibold uppercase tracking-wider text-voice/80">voice</div>}
        <LaneLabel icon="cube" text="Robot" sub="twin" />
      </div>
    </div>
  );
}

function LaneLabel({ icon, text, sub, first = false }: { icon: string; text: string; sub: string; first?: boolean }) {
  return (
    <div className={`${first ? "" : "mt-[6px]"} flex h-[22px] items-center gap-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-ink-300`}>
      <Icon name={icon} size={12} />
      {text}
      <span className="font-medium normal-case tracking-normal text-ink-500">{sub}</span>
    </div>
  );
}

function Diamond({ left, color, filled, title }: { left: string; color: string; filled: boolean; title: string }) {
  return (
    <div className="absolute top-1/2 z-10 -translate-x-1/2 -translate-y-1/2" style={{ left }} title={title}>
      <div
        className="h-[10px] w-[10px] rotate-45 rounded-[2px]"
        style={{ background: filled ? color : "#0d131c", border: `2px solid ${color}`, boxShadow: `0 0 6px ${color}` }}
      />
    </div>
  );
}
