import { useRef, useState } from "react";
import { artifactUrl } from "../../lib/api";
import type { CheckResult, Verification } from "../../lib/types";
import { Icon } from "../Icon";
import { ModelBadge } from "../ModelBadge";
import { Segmented } from "../PanelHeader";
import { Empty, OkMark } from "../ui";
import { GoalChips } from "./SpecTab";

function Check({ title, sub, ok, inconclusive, children, badge }: { title: string; sub: string; ok: boolean; inconclusive?: boolean; children?: React.ReactNode; badge?: React.ReactNode }) {
  const tone = inconclusive ? "bg-ink-700/25 ring-ink-500/40" : ok ? "bg-ok/[0.06] ring-ok/30" : "bg-bad/[0.07] ring-bad/35";
  return (
    <div className={`animate-fade-in rounded-xl px-3 py-2.5 ring-1 ring-inset transition-colors ${tone}`}>
      <div className="flex items-center gap-2">
        {inconclusive ? (
          <span title="inconclusive" className="grid h-[17px] w-[17px] place-items-center rounded-full bg-ink-600 text-[11px] font-bold leading-none text-ink-200">–</span>
        ) : (
          <OkMark ok={ok} size={13} />
        )}
        <span className="text-[13px] font-semibold text-ink-50">{title}</span>
        <span className="ml-auto">{badge}</span>
      </div>
      <div className="mt-1 text-[11.5px] leading-snug text-ink-300">{sub}</div>
      {children}
    </div>
  );
}

function measuredText(m: Record<string, number | boolean | string>) {
  return Object.entries(m)
    .filter(([k]) => !k.endsWith("below_rim"))
    .slice(0, 4)
    .map(([k, v]) => `${k.replace(/_cm$/, "")} ${typeof v === "number" ? v.toFixed(2) + (k.endsWith("_cm") ? " cm" : "") : String(v)}`)
    .join(" · ");
}

export function VerifyTab({ runId, verify }: { runId: string; verify: Verification | null }) {
  const [view, setView] = useState<"side" | "wipe">("side");
  if (!verify) return <Empty icon="eye" title="Verification runs after the program passes" hint="Symbolic, real-world and perceptual checks, plus an open-weight judge." />;
  const checks: [string, CheckResult][] = [
    ["symbolic", verify.symbolic],
    ["real", verify.real_world],
    ["perceptual", verify.perceptual],
  ];
  const real = verify.renders.real;
  const cam = verify.renders.camera;
  return (
    <div className="grid h-full min-h-0 grid-cols-1 gap-4 xl:grid-cols-[1fr_1.1fr]">
      <div className="min-w-0 space-y-3">
        <div className="grid grid-cols-2 gap-2.5">
          <Check title="Symbolic" sub="The goal, checked on the simulated final state" ok={verify.symbolic.ok} badge={<span className="text-[10.5px] text-ink-400">PyBullet</span>} />
          <Check title="Real world" sub="The same goal on your real final table, from the tracks" ok={verify.real_world.ok} badge={<ModelBadge model="sam-3.1" size="xs" showProvider={false} />} />
          <Check
            title="Perceptual"
            sub="SAM 3.1 segments the twin's render; the goal is checked on what it sees"
            ok={verify.perceptual.ok}
            inconclusive={verify.perceptual.inconclusive}
            badge={<ModelBadge model="sam-3.1" size="xs" showProvider={false} />}
          >
            {verify.perceptual.detail && <div className="mt-1 text-[11px] text-ink-400">{verify.perceptual.detail}</div>}
          </Check>
          {verify.judge ? (
            <Check
              title="Judge"
              sub={verify.judge.same_goal_achieved ? `Same goal achieved · confidence ${(verify.judge.confidence * 100).toFixed(0)}%` : verify.judge.suspected_error || "The judge sees a difference"}
              ok={verify.judge.same_goal_achieved}
              badge={<ModelBadge model="meta-models/muse-spark-open-1026" size="xs" />}
            >
              {verify.judge.differences.length > 0 && <div className="mt-1 text-[11px] italic text-ink-400">Noted: {verify.judge.differences.join("; ")}</div>}
            </Check>
          ) : (
            <Check title="Judge" sub="No judge verdict" ok={false} />
          )}
        </div>
        <div className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[12.5px] ring-1 ring-inset ${verify.agree ? "bg-ok/[0.06] text-ok ring-ok/25" : "bg-warn/[0.08] text-warn ring-warn/30"}`}>
          <Icon name={verify.agree ? "shield" : "alert"} size={15} />
          <span className="font-semibold">
            {verify.agree
              ? "All checks agree"
              : verify.accepted_caveat
                ? "Accepted by the supervisor"
                : `Checks disagree${verify.failure_class ? ` · ${verify.failure_class.replace(/_/g, " ")}` : ""}`}
          </span>
          <span className="ml-auto num text-[11px] text-ink-300">program v{verify.program_version}</span>
        </div>
        {verify.accepted_caveat && (
          <div className="rounded-lg bg-warn/[0.06] px-3 py-2 text-[11.5px] leading-snug text-ink-200 ring-1 ring-inset ring-warn/25">
            <span className="font-semibold text-warn">Caveat · </span>
            {verify.accepted_caveat}
          </div>
        )}
        <div>
          <div className="eyebrow mb-1.5">Clauses</div>
          <div className="overflow-hidden rounded-lg ring-1 ring-inset ring-ink-700/60">
            <div className="grid grid-cols-[1fr_repeat(3,64px)] gap-2 bg-ink-800/60 px-3 py-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-ink-400">
              <span>Clause</span>
              <span className="text-center">Sym.</span>
              <span className="text-center">Real</span>
              <span className="text-center">Perc.</span>
            </div>
            {verify.symbolic.clauses.map((c, i) => (
              <div key={i} className="grid grid-cols-[1fr_repeat(3,64px)] items-center gap-2 border-t border-ink-700/50 px-3 py-2">
                <div className="min-w-0">
                  <GoalChips clause={c.clause} />
                  <div className="num mt-1 truncate text-[10.5px] text-ink-400">{measuredText(c.measured)}</div>
                </div>
                {checks.map(([k, ch]) => (
                  <span key={k} className="flex justify-center">
                    <OkMark ok={ch.clauses[i]?.holds ?? null} size={11} />
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="flex min-h-0 min-w-0 flex-col gap-2">
        <div className="flex items-center gap-2">
          <span className="eyebrow">Same eyes, same angle</span>
          <div className="ml-auto">
            <Segmented
              value={view}
              onChange={setView}
              options={[
                { value: "side", label: "Side by side" },
                { value: "wipe", label: "Wipe" },
              ]}
            />
          </div>
        </div>
        {real && cam ? (
          view === "side" ? (
            <div className="grid grid-cols-2 gap-2">
              <Figure src={artifactUrl(runId, real)} label="Your real final frame" />
              <Figure src={artifactUrl(runId, cam)} label="Twin, from your camera's pose" />
            </div>
          ) : (
            <Wipe a={artifactUrl(runId, real)} b={artifactUrl(runId, cam)} />
          )
        ) : (
          <Empty icon="camera" title="No renders" />
        )}
        {verify.renders.top && (
          <div className="text-[11px] text-ink-400">
            The camera-pose render hides the robot, so it compares like for like with your real frame.
          </div>
        )}
      </div>
    </div>
  );
}

function Figure({ src, label }: { src: string; label: string }) {
  return (
    <figure className="overflow-hidden rounded-lg bg-black ring-1 ring-ink-700/70">
      <img src={src} alt={label} className="aspect-video w-full object-cover" />
      <figcaption className="px-2 py-1 text-[11px] font-medium text-ink-300">{label}</figcaption>
    </figure>
  );
}

function Wipe({ a, b }: { a: string; b: string }) {
  const [x, setX] = useState(0.5);
  const ref = useRef<HTMLDivElement>(null);
  const move = (cx: number) => {
    const r = ref.current!.getBoundingClientRect();
    setX(Math.min(1, Math.max(0, (cx - r.left) / r.width)));
  };
  return (
    <div
      ref={ref}
      className="relative aspect-video w-full cursor-ew-resize select-none overflow-hidden rounded-lg bg-black ring-1 ring-ink-700/70"
      onPointerDown={(e) => {
        move(e.clientX);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={(e) => e.buttons && move(e.clientX)}
    >
      <img src={b} alt="Twin render" className="absolute inset-0 h-full w-full object-cover" />
      <img src={a} alt="Real frame" className="absolute inset-0 h-full w-full object-cover" style={{ clipPath: `inset(0 ${100 - x * 100}% 0 0)` }} />
      <div className="absolute inset-y-0 w-[2px] bg-white shadow-[0_0_12px_rgba(255,255,255,0.7)]" style={{ left: `${x * 100}%` }} />
      <span className="absolute left-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10.5px] font-semibold text-white">Real</span>
      <span className="absolute right-2 top-2 rounded bg-black/60 px-1.5 py-0.5 text-[10.5px] font-semibold text-white">Twin</span>
    </div>
  );
}
