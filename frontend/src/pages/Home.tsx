import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ModelBadge } from "../components/ModelBadge";
import { TopNav } from "../components/TopNav";
import { Pill, Spinner } from "../components/ui";
import { api, ApiError, artifactUrl, type Sample } from "../lib/api";
import { istDate, usd } from "../lib/format";
import type { Health, RunMeta, SkillCard } from "../lib/types";

const MOMENTS = [
  { icon: "eye", title: "It watched me once", text: "Spark 1.3 turns the clip and your narration into a task spec. SAM 3.1 tracks every object and your hand.", models: ["muse-spark-1.3", "muse-voice-transcribe-1.0", "sam-3.1"] },
  { icon: "code", title: "It wrote its own program", text: "Muse Wonder writes the robot program, runs it in simulation, reads the failure and fixes it.", models: ["muse-wonder-1.0"] },
  { icon: "shield", title: "It checks itself", text: "The same eyes judge the twin from your camera's pose: symbolic, real-world and perceptual checks.", models: ["sam-3.1", "meta-models/muse-spark-open-1026"] },
  { icon: "grid", title: "It attacks itself", text: "A swarm of open-weight Spark Open personas invents layouts to break it. Wonder hardens it.", models: ["meta-models/muse-spark-open-1026", "muse-wonder-1.0"] },
  { icon: "mic", title: "Talk to it", text: "Correct it by voice in English, Hindi or Bengali. The goal and the code change; it re-verifies.", models: ["muse-voice-transcribe-1.0", "muse-wonder-1.0"] },
  { icon: "hand", title: "Your turn", text: "Drag anything on the 3D twin. The robot re-plans and does it, live and free.", models: ["muse-image-1.0"] },
];

function cardImage(c: SkillCard): string {
  if (c.image) return artifactUrl(c.run_id, c.image.startsWith("artifacts/") ? c.image : `artifacts/${c.image}`);
  return artifactUrl(c.run_id, "artifacts/reference_frame.jpg");
}

export default function Home() {
  const [runs, setRuns] = useState<RunMeta[] | null>(null);
  const [skills, setSkills] = useState<SkillCard[] | null>(null);
  const [samples, setSamples] = useState<Sample[] | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [upload, setUpload] = useState(false);
  useEffect(() => {
    api.runs().then(setRuns).catch(() => setRuns([]));
    api.skills().then(setSkills).catch(() => setSkills([]));
    api.samples().then(setSamples).catch(() => setSamples([]));
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const best = useMemo(() => {
    if (!runs?.length) return null;
    const done = runs.filter((r) => r.card);
    const pool = done.filter((r) => !r.fixture).length ? done.filter((r) => !r.fixture) : done.length ? done : runs;
    return [...pool].sort((a, b) => (b.card?.robustness ?? 0) - (a.card?.robustness ?? 0))[0];
  }, [runs]);

  return (
    <div className="min-h-full">
      <TopNav>
        {health && (
          <span className="hidden items-center gap-1.5 text-[11.5px] text-ink-400 sm:flex">
            <span className={`h-1.5 w-1.5 rounded-full ${health.mode === "replay" ? "bg-spark" : "bg-ok"}`} />
            {health.mode === "replay" ? "Replay mode" : health.mode === "judge" ? "Judge mode" : "Dev mode"}
          </span>
        )}
      </TopNav>

      <section className="relative overflow-hidden">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_80%_at_75%_10%,rgba(45,212,191,0.10),transparent_60%),radial-gradient(50%_60%_at_10%_0%,rgba(96,165,250,0.10),transparent_60%)]" />
        <div className="relative mx-auto grid max-w-[1560px] grid-cols-1 items-center gap-10 px-5 pb-10 pt-12 md:px-8 lg:grid-cols-[1fr_1.15fr] lg:pt-16">
          <div>
            <div className="mb-5 flex flex-wrap items-center gap-2">
              <Pill tone="info">Meta Global AI Developer Hackathon · Push the Frontier</Pill>
            </div>
            <h1 className="text-[52px] font-semibold leading-[1.02] tracking-[-0.035em] text-ink-50 md:text-[76px]">
              Show it <span className="bg-gradient-to-r from-sparkopen to-spark bg-clip-text text-transparent">once.</span>
            </h1>
            <p className="mt-5 max-w-[560px] text-[17px] leading-relaxed text-ink-300">
              Film yourself doing a tabletop task once, on your phone. A team of agents on Meta's models watches it, writes a robot program, tests it on a simulated
              Franka Panda, attacks its own work, and hands you a verified, robot-agnostic skill.
            </p>
            <div className="mt-7 flex flex-wrap items-center gap-3">
              {best && (
                <Link to={`/run/${best.run_id}`} className="btn btn-primary !px-5 !py-3 !text-[14px]" data-testid="watch-best">
                  <Icon name="play" size={14} /> Watch it learn
                </Link>
              )}
              <button type="button" className="btn !px-5 !py-3 !text-[14px]" onClick={() => setUpload(true)}>
                <Icon name="upload" size={15} /> Teach a new skill
              </button>
              <Link to={best ? `/try/${best.run_id}` : "/try"} className="btn btn-ghost !px-4 !py-3 !text-[14px]">
                Try it yourself <Icon name="arrow" size={14} />
              </Link>
            </div>
            <div className="mt-8 flex flex-wrap gap-1.5">
              {["muse-spark-1.3", "meta-models/muse-spark-open-1026", "sam-3.1", "muse-wonder-1.0", "muse-voice-transcribe-1.0", "muse-image-1.0"].map((m) => (
                <ModelBadge key={m} model={m} size="sm" showProvider={false} />
              ))}
            </div>
          </div>
          <Hero run={best} />
        </div>
      </section>

      <main className="mx-auto max-w-[1560px] space-y-14 px-5 pb-16 md:px-8">
        <section>
          <SectionTitle eyebrow="Skill library" title="Skills it has learned" sub="Each one from a single demo. Open the replay to see how, or move things around and watch it adapt." />
          {skills == null ? (
            <SkeletonRow />
          ) : skills.length === 0 ? (
            <div className="panel p-8 text-center text-[13px] text-ink-400">No skills yet. Teach the first one.</div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="skills">
              {skills.map((c) => (
                <SkillCardView key={c.skill_id + c.run_id} card={c} run={runs?.find((r) => r.run_id === c.run_id)} />
              ))}
            </div>
          )}
        </section>

        <section>
          <SectionTitle eyebrow="Samples" title="Run a sample clip" sub="Three clips you can send through the whole pipeline. Live runs use a small daily budget; recorded runs and Try it are always free." />
          <Samples samples={samples} runs={runs} />
        </section>

        <section>
          <SectionTitle eyebrow="How it works" title="Six moments, six Meta models" />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
            {MOMENTS.map((m, i) => (
              <div key={m.title} className="panel flex flex-col gap-2.5 p-4">
                <div className="flex items-center gap-2">
                  <span className="num flex h-6 w-6 items-center justify-center rounded-full bg-ink-700 text-[11px] text-ink-200">{i + 1}</span>
                  <Icon name={m.icon} size={16} className="text-ink-300" />
                </div>
                <div className="text-[15px] font-semibold tracking-tight text-ink-50">{m.title}</div>
                <div className="flex-1 text-[12.5px] leading-relaxed text-ink-300">{m.text}</div>
                <div className="flex flex-wrap gap-1">
                  {m.models.map((x) => (
                    <ModelBadge key={x} model={x} size="xs" showProvider={false} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>

        <footer className="flex flex-col gap-2 border-t border-ink-700/60 pt-6 text-[12px] text-ink-400 md:flex-row md:items-center md:justify-between">
          <div>The robot is simulated (a Franka Panda in PyBullet). DemoBot exports a robot-agnostic program; no physical robot was used.</div>
          <div>
            Built during the Meta Global AI Developer Hackathon, Oct 26 – Nov 4, 2026 ·{" "}
            <Link to="/costs" className="text-ink-200 underline-offset-2 hover:underline">
              Costs &amp; credits
            </Link>
          </div>
        </footer>
      </main>
      {upload && <UploadDialog onClose={() => setUpload(false)} mode={health?.mode} />}
    </div>
  );
}

function SectionTitle({ eyebrow, title, sub }: { eyebrow: string; title: string; sub?: string }) {
  return (
    <div className="mb-5">
      <div className="eyebrow">{eyebrow}</div>
      <h2 className="mt-1 text-[24px] font-semibold tracking-tight text-ink-50">{title}</h2>
      {sub && <p className="mt-1 max-w-3xl text-[13.5px] text-ink-400">{sub}</p>}
    </div>
  );
}

function SkeletonRow() {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="panel shimmer h-72" />
      ))}
    </div>
  );
}

/** A looping 6-second replay of the best run: the real video crossfading to the twin. */
function Hero({ run }: { run: RunMeta | null }) {
  const vid = useRef<HTMLVideoElement>(null);
  const [phase, setPhase] = useState<"real" | "twin">("real");
  const [twinSrc, setTwinSrc] = useState<string | null>(null);
  useEffect(() => {
    if (!run) return;
    let alive = true;
    api
      .run(run.run_id)
      .then((d) => {
        if (!alive) return;
        const cams = d.artifacts.filter((a) => /sim\/demo_v\d+\/camera_demo\.png$/.test(a)).sort();
        setTwinSrc(cams.length ? artifactUrl(run.run_id, cams[cams.length - 1]) : null);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [run]);
  useEffect(() => {
    const v = vid.current;
    if (!v || !run) return;
    let timer = 0;
    const loop = () => {
      const d = v.duration || 13;
      const start = Math.max(0, d - 6.2);
      if (v.currentTime < start - 0.5 || v.ended) v.currentTime = start;
      if (v.currentTime >= d - 0.15 || v.ended) {
        if (twinSrc) {
          setPhase("twin");
          v.pause();
          timer = window.setTimeout(() => {
            setPhase("real");
            v.currentTime = start;
            v.play().catch(() => undefined);
          }, 2600);
          return;
        }
        v.currentTime = start;
      }
    };
    const onTime = () => loop();
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("ended", onTime);
    return () => {
      v.removeEventListener("timeupdate", onTime);
      v.removeEventListener("ended", onTime);
      window.clearTimeout(timer);
    };
  }, [run, twinSrc]);

  if (!run)
    return (
      <div className="panel flex aspect-video items-center justify-center">
        <Spinner />
      </div>
    );
  return (
    <Link to={`/run/${run.run_id}`} className="group relative block" aria-label="Open the best run">
      <div className="absolute -inset-3 rounded-[26px] bg-gradient-to-br from-sparkopen/20 via-transparent to-spark/20 opacity-70 blur-2xl" />
      <div className="panel relative overflow-hidden !rounded-[20px] p-0">
        <div className="relative aspect-video bg-black">
          <video
            ref={vid}
            src={artifactUrl(run.run_id, "artifacts/display.mp4")}
            muted
            autoPlay
            playsInline
            preload="auto"
            onLoadedMetadata={(e) => {
              e.currentTarget.currentTime = Math.max(0, e.currentTarget.duration - 6.2);
            }}
            className="absolute inset-0 h-full w-full object-cover"
          />
          {twinSrc && (
            <img
              src={twinSrc}
              alt="The digital twin, rendered from the phone's pose"
              className="absolute inset-0 h-full w-full object-cover transition-opacity duration-1000"
              style={{ opacity: phase === "twin" ? 1 : 0 }}
            />
          )}
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/25" />
          <div className="absolute left-4 top-4 flex gap-1.5">
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 transition ${phase === "real" ? "bg-white text-ink-900 ring-white" : "bg-black/40 text-white/70 ring-white/20"}`}>Real</span>
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 transition ${phase === "twin" ? "bg-sparkopen text-ink-950 ring-sparkopen" : "bg-black/40 text-white/70 ring-white/20"}`}>Twin</span>
          </div>
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-3 p-4">
            <div>
              <div className="text-[16px] font-semibold text-white">{run.card?.title ?? run.title}</div>
              <div className="mt-0.5 text-[12px] text-white/70">
                {run.fixture ? "Synthetic fixture run (model calls simulated)" : `Replay of a recorded run (${istDate(run.created_at)})`}
              </div>
            </div>
            <span className="flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-[12px] font-semibold text-white ring-1 ring-white/20 backdrop-blur transition group-hover:bg-white/20">
              <Icon name="play" size={11} /> Open mission control
            </span>
          </div>
        </div>
      </div>
    </Link>
  );
}

function SkillCardView({ card, run }: { card: SkillCard; run?: RunMeta }) {
  const fixture = card.fixture ?? run?.fixture;
  return (
    <div className="panel group flex flex-col overflow-hidden !p-0 transition hover:-translate-y-0.5 hover:ring-1 hover:ring-ink-500">
      <Link to={`/run/${card.run_id}`} className="relative block aspect-[16/10] overflow-hidden bg-ink-850">
        <img src={cardImage(card)} alt={card.title} loading="lazy" className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]" />
        <div className="absolute inset-0 bg-gradient-to-t from-ink-900/80 via-transparent to-transparent" />
        {!card.image && <span className="absolute right-2 top-2 rounded bg-black/55 px-1.5 py-0.5 text-[10px] font-medium text-white/80">final frame</span>}
        {fixture && <span className="absolute left-2 top-2 rounded bg-warn/90 px-1.5 py-0.5 text-[10px] font-bold text-ink-950">synthetic</span>}
      </Link>
      <div className="flex flex-1 flex-col gap-2 p-4">
        <div className="text-[15px] font-semibold leading-snug tracking-tight text-ink-50">{card.title}</div>
        <div className="flex-1 text-[12.5px] leading-relaxed text-ink-300">{card.description}</div>
        <div className="flex flex-wrap gap-1.5">
          {card.robustness != null && (
            <Pill tone={card.robustness >= 0.99 ? "ok" : "warn"}>
              <Icon name="shield" size={11} /> robust {Math.round(card.robustness * 100)}%
            </Pill>
          )}
          <Pill tone="neutral">
            <span className="num">{usd(card.cost_to_learn_usd, 3)}</span> to learn
          </Pill>
          <Pill tone="neutral">v{card.program_version}</Pill>
        </div>
        <div className="mt-1 flex gap-2">
          <Link to={`/run/${card.run_id}`} className="btn flex-1 justify-center !py-1.5 !text-[12px]">
            <Icon name="play" size={11} /> Replay
          </Link>
          <Link to={`/try/${card.run_id}`} className="btn flex-1 justify-center !py-1.5 !text-[12px]">
            <Icon name="hand" size={13} /> Try it
          </Link>
        </div>
      </div>
    </div>
  );
}

function Samples({ samples, runs }: { samples: Sample[] | null; runs: RunMeta[] | null }) {
  const nav = useNavigate();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  if (samples == null || runs == null) return <SkeletonRow />;
  const start = async (s: Sample) => {
    setBusy(s.id);
    setMsg(null);
    try {
      const r = await api.createSampleRun(s.id);
      nav(`/run/${r.run_id}`);
    } catch (e) {
      setMsg(e instanceof ApiError && e.status === 429 ? "Live budget for today is used. Enjoy the recorded runs and the free Try-it page." : e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };
  // Until the server lists sample clips, the recorded runs stand in (replays are free).
  const items = samples.length
    ? samples.slice(0, 3).map((s) => ({ key: s.id, title: s.title, thumb: s.thumb ?? null, sub: s.duration_s ? `${s.duration_s.toFixed(0)} s clip` : "sample clip", action: () => start(s), label: "Run it live", live: true }))
    : runs.slice(0, 3).map((r) => ({
        key: r.run_id,
        title: r.title,
        thumb: artifactUrl(r.run_id, "artifacts/keyframes/kf_00.jpg"),
        sub: r.fixture ? "synthetic clip · recorded run" : `recorded ${istDate(r.created_at)}`,
        action: () => nav(`/run/${r.run_id}`),
        label: "Watch the recorded run",
        live: false,
      }));
  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {items.map((it) => (
          <button key={it.key} type="button" onClick={it.action} disabled={busy != null} className="panel group flex items-center gap-4 !p-3 text-left transition hover:ring-1 hover:ring-ink-500">
            <div className="relative h-20 w-32 shrink-0 overflow-hidden rounded-lg bg-ink-850">
              {it.thumb && <img src={it.thumb} alt="" loading="lazy" className="h-full w-full object-cover" />}
              <div className="absolute inset-0 flex items-center justify-center bg-black/25 opacity-80 transition group-hover:opacity-100">
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white/90 text-ink-900">{busy === it.key ? <Spinner size={13} color="#0a0f16" /> : <Icon name="play" size={12} />}</span>
              </div>
            </div>
            <div className="min-w-0">
              <div className="truncate text-[14px] font-semibold text-ink-50">{it.title}</div>
              <div className="mt-0.5 text-[12px] text-ink-400">{it.sub}</div>
              <div className={`mt-1.5 text-[12px] font-semibold ${it.live ? "text-sparkopen" : "text-spark"}`}>{it.label} →</div>
            </div>
          </button>
        ))}
      </div>
      {msg && <div className="mt-3 text-[12.5px] text-warn">{msg}</div>}
    </>
  );
}

function UploadDialog({ onClose, mode }: { onClose: () => void; mode?: string }) {
  const [file, setFile] = useState<File | null>(null);
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const nav = useNavigate();
  const submit = async () => {
    if (!file) return;
    setBusy(true);
    setErr(null);
    try {
      const f = new FormData();
      f.append("clip", file);
      if (hint.trim()) f.append("task_hint", hint.trim());
      const r = await api.createRun(f);
      nav(`/run/${r.run_id}`);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) setErr("Live runs are not enabled on this server. Enjoy the recorded runs and the free Try-it page.");
      else if (e instanceof ApiError && e.code === "NO_MARKERS") setErr("The four printed markers must be visible in the clip so it can measure the table in centimetres.");
      else if (e instanceof ApiError && e.status === 429) setErr("Live budget for today is used. Enjoy the recorded runs and the free Try-it page.");
      else setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="panel animate-slide-in w-full max-w-lg !bg-ink-800 p-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h3 className="text-[18px] font-semibold text-ink-50">Teach a new skill</h3>
          <button type="button" className="btn btn-ghost !p-1.5" onClick={onClose} aria-label="Close">
            <Icon name="x" size={16} />
          </button>
        </div>
        <ol className="mt-3 space-y-1.5 text-[13px] text-ink-300">
          <li>1. Put the four printed ArUco markers at the corners of your work area.</li>
          <li>2. Hold your phone in one hand and do the task once with the other (10–30 s).</li>
          <li>3. Narrate if you like, in English, Hindi or Bengali.</li>
        </ol>
        <label className="mt-4 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-ink-500 bg-ink-850 px-4 py-7 text-center transition hover:border-sparkopen/60">
          <Icon name="upload" size={22} className="text-ink-300" />
          <span className="text-[13px] font-medium text-ink-100">{file ? file.name : "Choose a video (mp4, mov)"}</span>
          <input type="file" accept="video/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <input
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          placeholder="Optional hint, e.g. “pens go in the mug”"
          className="mt-3 h-10 w-full rounded-lg bg-ink-850 px-3 text-[13px] text-ink-100 ring-1 ring-inset ring-ink-600 outline-none placeholder:text-ink-500 focus:ring-sparkopen/50"
        />
        {mode === "replay" && <div className="mt-3 text-[12px] text-ink-400">This server runs in replay mode, so live runs may be off.</div>}
        {err && <div className="mt-3 text-[12.5px] text-warn">{err}</div>}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary" disabled={!file || busy} onClick={submit}>
            {busy ? <Spinner size={13} color="#04201c" /> : <Icon name="sparkle" size={14} />} Learn it
          </button>
        </div>
      </div>
    </div>
  );
}
