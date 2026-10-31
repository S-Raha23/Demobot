import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { CodeView } from "../components/CodeView";
import { Icon } from "../components/Icon";
import { Segmented, Toggle } from "../components/PanelHeader";
import { GoalChips } from "../components/tabs/SpecTab";
import { TopNav } from "../components/TopNav";
import { Empty, OkMark, Pill, Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { clauseSentence } from "../lib/goal";
import { skillSpans } from "../lib/sync";
import type { Layout, Program, RunMeta, SceneObject, SkillCard, TaskSpec, TryLayoutResponse, TwinScene as TwinSceneData } from "../lib/types";
import { useArtifact } from "../replay/useRun";
import type { TwinHandle } from "../twin/TwinView";

const TwinView = lazy(() => import("../twin/TwinView").then((m) => ({ default: m.TwinView })));

function extents(o: SceneObject): [number, number] {
  if (o.shape !== "box") {
    const r = Math.max(o.w, o.d) / 2;
    return [r, r];
  }
  const c = Math.abs(Math.cos((o.yaw * Math.PI) / 180));
  const s = Math.abs(Math.sin((o.yaw * Math.PI) / 180));
  return [(o.w * c + o.d * s) / 2, (o.w * s + o.d * c) / 2];
}

/** Quick client-side hints (the server's validator has the final say). */
function hints(layout: Layout, reach: TwinSceneData["reach"] | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const o of layout.objects) {
    if (reach) {
      const c = Math.round((o.x - reach.x0) / reach.step_cm);
      const r = Math.round((o.y - reach.y0) / reach.step_cm);
      if (reach.cells[r]?.[c] === false) out.set(o.name, "out of the robot's reach");
    }
  }
  const objs = layout.objects;
  for (let i = 0; i < objs.length; i++)
    for (let j = i + 1; j < objs.length; j++) {
      const a = objs[i];
      const b = objs[j];
      const [ax, ay] = extents(a);
      const [bx, by] = extents(b);
      if (Math.abs(a.x - b.x) < ax + bx + 0.5 && Math.abs(a.y - b.y) < ay + by + 0.5) {
        out.set(a.name, `overlaps ${b.name}`);
        out.set(b.name, `overlaps ${a.name}`);
      }
    }
  return out;
}

export default function TryIt() {
  const { id } = useParams();
  const nav = useNavigate();
  const [skills, setSkills] = useState<SkillCard[] | null>(null);
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  useEffect(() => {
    api.skills().then(setSkills).catch(() => setSkills([]));
    api.runs().then(setRuns).catch(() => setRuns([]));
  }, []);
  useEffect(() => {
    if (id || !skills) return;
    const pick = skills[0]?.run_id ?? runs?.[0]?.run_id;
    if (pick) nav(`/try/${pick}`, { replace: true });
  }, [id, skills, runs, nav]);

  return (
    <div className="flex min-h-full flex-col lg:h-full">
      <TopNav
        center={
          skills && skills.length > 0 ? (
            <div className="flex justify-center">
              <select
                value={id ?? ""}
                onChange={(e) => nav(`/try/${e.target.value}`)}
                className="h-8 max-w-[420px] rounded-lg bg-ink-800 px-3 text-[12.5px] font-medium text-ink-100 ring-1 ring-inset ring-ink-600 outline-none"
                aria-label="Skill"
              >
                {skills.map((s) => (
                  <option key={s.run_id} value={s.run_id}>
                    {s.title}
                    {s.fixture ? " (synthetic)" : ""}
                  </option>
                ))}
              </select>
            </div>
          ) : null
        }
      />
      {id ? <Playground key={id} runId={id} /> : <div className="flex flex-1 items-center justify-center">{skills && !skills.length ? <Empty icon="cube" title="No skills to try yet" /> : <Spinner />}</div>}
    </div>
  );
}

function Playground({ runId }: { runId: string }) {
  const scene = useArtifact<TwinSceneData>(runId, "artifacts/twin_scene.json");
  const spec = useArtifact<TaskSpec>(runId, "artifacts/taskspec.json");
  const programs = useArtifact<Program[]>(runId, "artifacts/programs.json");
  const [layout, setLayout] = useState<Layout | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState<"run" | "shuffle" | null>(null);
  const [res, setRes] = useState<TryLayoutResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [cam, setCam] = useState<"top" | "orbit">("top");
  const [reach, setReach] = useState(false);
  const [showCode, setShowCode] = useState(false);
  const [simT, setSimT] = useState(0);
  const twin = useRef<TwinHandle | null>(null);
  const t0 = useRef(0);
  const timeRef = useRef(0);
  const [, force] = useState(0);

  useEffect(() => {
    if (scene && !layout) setLayout(structuredClone(scene.layout));
  }, [scene, layout]);

  const trajectory = res?.ok ? (res.result?.twin ?? null) : null;

  // animate the returned trajectory at 1×
  useEffect(() => {
    if (!trajectory) return;
    t0.current = performance.now();
    let raf = 0;
    const step = () => {
      const t = Math.min(trajectory.duration_s, (performance.now() - t0.current) / 1000);
      timeRef.current = t;
      setSimT(t);
      if (t < trajectory.duration_s) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [trajectory]);

  const onMove = useCallback((name: string, x: number, y: number, yaw: number) => {
    setLayout((l) => (l ? { ...l, objects: l.objects.map((o) => (o.name === name ? { ...o, x, y, yaw } : o)) } : l));
  }, []);
  const options = useMemo(() => ({ editable: true, onMove, onSelect: setSelected }), [onMove]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "SELECT") return;
      if (e.key === "r" || e.key === "R") twin.current?.rotateSelected(e.shiftKey ? -15 : 15);
      if (e.key === "Escape") twin.current?.select(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const run = async () => {
    if (!layout) return;
    setBusy("run");
    setErr(null);
    try {
      const r = await api.tryLayout(
        runId,
        layout.objects.map((o) => ({ name: o.name, x: o.x, y: o.y, yaw: o.yaw })),
      );
      setRes(r);
      twin.current?.select(null);
    } catch (e) {
      setErr(e instanceof ApiError ? `${e.code}: ${e.message}` : String(e));
    } finally {
      setBusy(null);
    }
  };
  const shuffle = async () => {
    setBusy("shuffle");
    setErr(null);
    try {
      const l = await api.shuffle(runId, Math.floor(Math.random() * 1e6));
      setRes(null);
      setLayout(l);
      force((n) => n + 1);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(null);
    }
  };
  const reset = () => {
    if (!scene) return;
    setRes(null);
    setLayout(structuredClone(scene.layout));
  };
  const editAgain = () => setRes(null);

  const h = useMemo(() => (layout ? hints(layout, scene?.reach) : new Map<string, string>()), [layout, scene]);
  const goalResults = res?.ok ? res.result?.goal_results : null;
  const spans = res?.ok && res.result && trajectory ? skillSpans(res.result.skill_calls, trajectory.duration_s) : [];
  const activeSpan = spans.findIndex((s) => simT >= s.t0 && simT < s.t1);
  const done = trajectory ? simT >= trajectory.duration_s - 1e-3 : false;
  const program = programs ? [...programs].filter((p) => p.passed_demo).sort((a, b) => b.version - a.version)[0] ?? programs[programs.length - 1] : null;
  const sel = layout?.objects.find((o) => o.name === selected);

  if (!scene || !layout)
    return (
      <div className="flex flex-1 items-center justify-center text-ink-300">
        <Spinner size={20} />
      </div>
    );

  return (
    <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_400px]">
      <div className="panel relative flex min-h-[460px] flex-col overflow-hidden">
        <div className="flex h-11 shrink-0 items-center gap-2 border-b border-ink-700/60 px-3">
          <Icon name="hand" size={15} className="text-ink-300" />
          <span className="eyebrow !text-ink-200">Try it</span>
          <span className="text-[12px] text-ink-400">{trajectory ? "The robot runs the learned program on your layout" : "Drag objects to move them. Select one and press R to rotate."}</span>
          <div className="ml-auto flex items-center gap-2">
            <Pill tone="ok">simulation only · free</Pill>
            <Toggle on={reach} onClick={() => setReach(!reach)} title="Where the Panda can reach">
              Reach map
            </Toggle>
            <Segmented
              value={cam}
              onChange={setCam}
              options={[
                { value: "top", label: "Top-down" },
                { value: "orbit", label: "3D" },
              ]}
            />
          </div>
        </div>
        <div className="relative min-h-0 flex-1" data-testid="try-twin">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <Spinner />
              </div>
            }
          >
            <TwinView
              ref={twin}
              runId={runId}
              scene={scene}
              layout={layout}
              trajectory={trajectory}
              timeSource={() => timeRef.current}
              cameraMode={cam}
              reach={reach && !trajectory}
              ghostRobot={!trajectory}
              labels
              options={options}
            />
          </Suspense>
          {trajectory && (
            <div className="absolute inset-x-4 bottom-4 flex items-center gap-3 rounded-xl bg-ink-900/85 px-3 py-2 ring-1 ring-ink-600 backdrop-blur">
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-full bg-ink-100 text-ink-900"
                onClick={() => {
                  t0.current = performance.now();
                  const tr = trajectory;
                  const step = () => {
                    const t = Math.min(tr.duration_s, (performance.now() - t0.current) / 1000);
                    timeRef.current = t;
                    setSimT(t);
                    if (t < tr.duration_s) requestAnimationFrame(step);
                  };
                  requestAnimationFrame(step);
                }}
                aria-label="Replay the robot"
              >
                <Icon name={done ? "reset" : "play"} size={12} />
              </button>
              <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-ink-700">
                <div className="absolute inset-y-0 left-0 rounded-full bg-sparkopen" style={{ width: `${(simT / trajectory.duration_s) * 100}%` }} />
              </div>
              <span className="num w-20 text-right text-[11.5px] text-ink-300">
                {simT.toFixed(1)} / {trajectory.duration_s.toFixed(1)} s
              </span>
              <button type="button" className="btn !py-1 !text-[12px]" onClick={editAgain}>
                <Icon name="hand" size={13} /> Move things again
              </button>
            </div>
          )}
        </div>
      </div>

      <aside className="flex min-h-0 flex-col gap-3 lg:overflow-y-auto scroll-thin">
        <div className="panel p-4">
          <div className="eyebrow">The skill</div>
          <div className="mt-1 text-[16px] font-semibold leading-snug text-ink-50">{spec?.summary ?? "…"}</div>
          {spec?.generalization && <div className="mt-1 text-[12.5px] text-ink-300">{spec.generalization}</div>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" className="btn btn-primary flex-1 justify-center !py-2.5" onClick={run} disabled={busy != null} data-testid="try-run">
              {busy === "run" ? <Spinner size={14} color="#04201c" /> : <Icon name="play" size={13} />} Run
            </button>
            <button type="button" className="btn !py-2.5" onClick={shuffle} disabled={busy != null} data-testid="try-shuffle">
              {busy === "shuffle" ? <Spinner size={13} /> : <Icon name="shuffle" size={14} />} Shuffle
            </button>
            <button type="button" className="btn !py-2.5" onClick={reset} disabled={busy != null} title="Back to the demo layout">
              <Icon name="reset" size={14} />
            </button>
          </div>
          <div className="mt-2 text-[11.5px] text-ink-400">No model calls: the program Muse Wonder wrote runs in PyBullet on your layout.</div>
        </div>

        <div className="panel p-4" data-testid="goal-chips">
          <div className="mb-2 flex items-center gap-2">
            <span className="eyebrow">Goal</span>
            {goalResults && done && (
              <Pill tone={res?.result?.goal_ok ? "ok" : "bad"}>
                {res?.result?.goal_ok ? "achieved" : "not achieved"}
              </Pill>
            )}
          </div>
          <div className="space-y-2">
            {(spec?.goal ?? []).map((g, i) => {
              const r = goalResults?.[i];
              const shown = r && (done || !trajectory) ? r.holds : null;
              return (
                <div
                  key={i}
                  className={`rounded-lg px-3 py-2 ring-1 ring-inset transition-colors duration-500 ${shown == null ? "bg-ink-800/60 ring-ink-700/60" : shown ? "bg-ok/[0.08] ring-ok/35" : "bg-bad/[0.08] ring-bad/40"}`}
                >
                  <GoalChips clause={g} holds={shown} />
                  <div className="mt-1 text-[12px] text-ink-300">{clauseSentence(g)}</div>
                  {r && shown != null && r.detail && <div className="mt-0.5 text-[11px] text-ink-400">{r.detail}</div>}
                </div>
              );
            })}
          </div>
        </div>

        {res && !res.ok && (
          <div className="panel p-4 ring-1 ring-warn/30">
            <div className="flex items-center gap-2 text-[13px] font-semibold text-warn">
              <Icon name="alert" size={15} /> That layout is not valid
            </div>
            <ul className="mt-1.5 list-disc pl-5 text-[12.5px] text-ink-200">
              {(res.problems ?? []).map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {err && <div className="panel p-3 text-[12.5px] text-bad">{err}</div>}

        {res?.ok && res.result && (
          <div className="panel p-4">
            <div className="flex items-center gap-2">
              <span className="eyebrow">Robot run</span>
              <span className="num ml-auto text-[11px] text-ink-400">
                program v{res.program_version} · sim {res.result.duration_s.toFixed(1)} s · wall {res.result.wall_s.toFixed(2)} s
              </span>
            </div>
            {res.result.error && <div className="mt-2 rounded-md bg-bad/10 px-2.5 py-1.5 font-mono text-[11.5px] text-bad">{res.result.error}</div>}
            <ol className="mt-2 space-y-1">
              {spans.map((s, i) => (
                <li
                  key={i}
                  className={`flex items-center gap-2 rounded-md px-2 py-1 font-mono text-[11.5px] ${i === activeSpan && !done ? "bg-sparkopen/15 text-ink-50 ring-1 ring-inset ring-sparkopen/40" : i < activeSpan || done ? "text-ink-200" : "text-ink-500"}`}
                >
                  {i < activeSpan || done ? (
                    <OkMark ok={s.ok} size={9} />
                  ) : i === activeSpan ? (
                    <span className="flex h-[15px] w-[15px] items-center justify-center text-sparkopen">
                      <Spinner size={12} />
                    </span>
                  ) : (
                    <span className="inline-block h-[15px] w-[15px] rounded-full ring-1 ring-ink-600" />
                  )}
                  {s.label}
                </li>
              ))}
            </ol>
          </div>
        )}

        {!trajectory && (
          <div className="panel p-4">
            <div className="eyebrow mb-2">Objects</div>
            <div className="space-y-1">
              {layout.objects.map((o) => (
                <button
                  type="button"
                  key={o.name}
                  onClick={() => twin.current?.select(o.name)}
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-[12.5px] transition ${o.name === selected ? "bg-sparkopen/10 ring-1 ring-inset ring-sparkopen/40" : "hover:bg-ink-750"}`}
                >
                  <span className="h-3 w-3 shrink-0 rounded-full ring-1 ring-white/20" style={{ background: o.color }} />
                  <span className="min-w-0 flex-1 truncate text-ink-100">{o.name}</span>
                  {h.get(o.name) ? <span className="truncate text-[11px] text-warn">{h.get(o.name)}</span> : null}
                  <span className="num text-[10.5px] text-ink-400">
                    {o.x.toFixed(0)}, {o.y.toFixed(0)} cm{o.shape === "box" ? ` · ${o.yaw.toFixed(0)}°` : ""}
                  </span>
                </button>
              ))}
            </div>
            {sel && sel.shape === "box" && (
              <div className="mt-2 flex items-center gap-2 text-[12px] text-ink-300">
                Rotate {sel.name}:
                <button type="button" className="btn !px-2 !py-1" onClick={() => twin.current?.rotateSelected(-15)}>
                  −15°
                </button>
                <button type="button" className="btn !px-2 !py-1" onClick={() => twin.current?.rotateSelected(15)}>
                  +15°
                </button>
                <span className="text-ink-500">or press R</span>
              </div>
            )}
          </div>
        )}

        {program && (
          <div className="panel p-4">
            <button type="button" className="flex w-full items-center gap-2" onClick={() => setShowCode(!showCode)}>
              <span className="eyebrow">The program it runs</span>
              <span className="num text-[11px] text-wonder">v{program.version}</span>
              <Icon name="code" size={14} className="ml-auto text-ink-400" />
            </button>
            {showCode && (
              <div className="mt-2">
                <CodeView code={program.code} />
              </div>
            )}
          </div>
        )}
        <Link to={`/run/${runId}`} className="btn btn-ghost justify-center">
          <Icon name="play" size={12} /> See how it learned this
        </Link>
      </aside>
    </main>
  );
}
