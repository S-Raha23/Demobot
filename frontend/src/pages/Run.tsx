import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { AgentFeed } from "../components/AgentFeed";
import { CorrectionDock } from "../components/CorrectionDock";
import { Icon } from "../components/Icon";
import { ModelBadge } from "../components/ModelBadge";
import { Segmented } from "../components/PanelHeader";
import { RealPanel, trackColor } from "../components/RealPanel";
import { StageStepper } from "../components/StageStepper";
import { CostsTab } from "../components/tabs/CostsTab";
import { ProgramTab, type Iteration } from "../components/tabs/ProgramTab";
import { SpecTab } from "../components/tabs/SpecTab";
import { StressTab } from "../components/tabs/StressTab";
import { VerifyTab } from "../components/tabs/VerifyTab";
import { Timeline } from "../components/Timeline";
import { TopNav } from "../components/TopNav";
import { TwinPanel } from "../components/TwinPanel";
import { Pill, Spinner } from "../components/ui";
import { istDate, usd } from "../lib/format";
import { STAGE_DOING, STAGE_LABEL } from "../lib/models";
import { buildAnchors, skillSpans, videoToRobot } from "../lib/sync";
import type {
  CalibrationOverlay,
  CameraTrack,
  CrossWatch,
  GroundedDemo,
  IngestInfo,
  Program,
  SimResult,
  SkillCard,
  StressReport,
  TaskSpec,
  ToolCallPayload,
  TracksFile,
  Transcript,
  TwinScene,
  TwinTrajectory,
  Verification,
} from "../lib/types";
import { MediaClock } from "../replay/mediaClock";
import { hasArtifact, latestArtifact } from "../replay/state";
import { RunContext, useArtifact, useRunPlayback, useTicker, type RunPlayback } from "../replay/useRun";

type Tab = "spec" | "program" | "verify" | "stress" | "costs";
const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "spec", label: "Spec", icon: "eye" },
  { id: "program", label: "Program", icon: "code" },
  { id: "verify", label: "Verify", icon: "shield" },
  { id: "stress", label: "Stress", icon: "grid" },
  { id: "costs", label: "Costs", icon: "dollar" },
];

export default function Run() {
  const { id = "" } = useParams();
  const [q] = useSearchParams();
  const speed = Number(q.get("speed") ?? 2) || 2;
  const pb = useRunPlayback(id, { speed, skip: q.get("skip") === "1" });
  return (
    <RunContext.Provider value={pb}>
      <MissionControl pb={pb} initialTab={(q.get("tab") as Tab) ?? null} />
    </RunContext.Provider>
  );
}

function MissionControl({ pb, initialTab }: { pb: RunPlayback; initialTab: Tab | null }) {
  const { runId, view, detail } = pb;
  const index = useMemo(() => new Set(detail?.artifacts ?? []), [detail]);
  const stageDone = (s: string) => view.stages[s]?.status === "done" || view.stages[s]?.status === "failed";
  /** A file the run directory lists, loaded once the stage that writes it has ended. */
  const gated = (path: string, stage: string) => (index.has(path) && stageDone(stage) ? path : null);
  const announced = (name: string) => hasArtifact(view, name)?.path ?? null;

  const ingest = useArtifact<IngestInfo>(runId, gated("artifacts/ingest.json", "ingest"));
  const videoPath = latestArtifact(view, "video")?.path ?? null;
  const poster = announced("kf_00.jpg");
  const overlay = useArtifact<CalibrationOverlay>(runId, announced("calibration_overlay.json"));
  const cameraTrack = useArtifact<CameraTrack>(runId, announced("camera_track.json"));
  const rectified = announced("rectified_first.png");
  const transcript = useArtifact<Transcript>(runId, announced("transcript.json"));
  const spec = useArtifact<TaskSpec>(runId, announced("taskspec.json"));
  const cross = useArtifact<CrossWatch>(runId, announced("crosswatch.json") ?? gated("artifacts/crosswatch.json", "watch"));
  const tracks = useArtifact<TracksFile>(runId, announced("tracks.json"));
  const grounded = useArtifact<GroundedDemo>(runId, announced("grounded.json"));
  const scene = useArtifact<TwinScene>(runId, announced("twin_scene.json"));
  const programs = useArtifact<Program[]>(runId, announced("programs.json") ?? gated("artifacts/programs.json", view.stages.harden?.status === "done" ? "harden" : "program"));
  const verify = useArtifact<Verification>(runId, announced("verify.json"));
  const stress = useArtifact<StressReport>(runId, announced("stress.json"));
  const card = useArtifact<SkillCard>(runId, announced("card.json"));
  const trajArt = latestArtifact(view, "trajectory");
  const traj = useArtifact<TwinTrajectory>(runId, trajArt?.path);
  const resultPath = trajArt ? trajArt.path.replace(/[^/]+$/, "result.json") : null;
  const simResult = useArtifact<SimResult>(runId, resultPath && index.has(resultPath) ? resultPath : null);

  // ---- the shared media clock ----
  const clock = useMemo(() => new MediaClock(), []);
  useEffect(() => {
    clock.start();
    return () => clock.stop();
  }, [clock]);
  const [videoDur, setVideoDur] = useState<number | null>(null);
  const duration = videoDur ?? ingest?.duration_s ?? (videoPath ? 0 : traj?.duration_s ?? 0);
  useEffect(() => {
    clock.duration = duration;
  }, [clock, duration]);

  const anchors = useMemo(() => {
    if (!traj) return null;
    if (!videoPath || !duration) return null;
    return buildAnchors(grounded?.contacts ?? [], traj.events, duration, traj.duration_s);
  }, [traj, grounded, duration, videoPath]);
  const anchorsRef = useRef(anchors);
  anchorsRef.current = anchors;
  const timeSource = useMemo(() => () => (anchorsRef.current ? videoToRobot(anchorsRef.current, clock.t) : clock.t), [clock]);

  // ---- tabs follow the pipeline until the user picks one ----
  const [tab, setTab] = useState<Tab>(initialTab ?? "spec");
  const pinned = useRef(Boolean(initialTab));
  const st = view.stages;
  const followed: Tab | null =
    st.card?.status === "running"
      ? "costs"
      : st.stress?.status === "running" || st.harden?.status === "running"
        ? "stress"
        : hasArtifact(view, "verify.json") && st.verify?.status !== "todo"
          ? "verify"
          : st.program?.status === "running" || st.verify?.status === "running"
            ? "program"
            : st.watch?.status === "done"
              ? "spec"
              : null;
  useEffect(() => {
    if (!pinned.current && followed) setTab(followed);
  }, [followed]);
  useEffect(() => {
    if (pb.finished && !pinned.current && st.verify?.status === "done") setTab("verify");
  }, [pb.finished, st.verify?.status]);

  const codeArtifacts = view.artifactList.filter((a) => a.kind === "code");
  // A resumed run can repeat a stage (with cached calls): keep the latest of each tool call.
  const iterations: Iteration[] = (() => {
    const all = view.events.filter((e) => e.type === "tool_call").map((e) => ({ seq: e.seq, stage: e.stage, p: e.payload as unknown as ToolCallPayload }));
    const key = (i: Iteration) => `${i.p.agent}|${i.p.iteration}|${i.p.tool}|${JSON.stringify(i.p.args)}`;
    const last = new Map(all.map((i) => [key(i), i.seq]));
    return all.filter((i) => last.get(key(i)) === i.seq);
  })();
  const swarm = view.events
    .filter((e) => e.type === "model_call" && String((e.payload as { purpose?: string }).purpose ?? "").startsWith("redteam:"))
    .map((e) => ({ purpose: String((e.payload as { purpose: string }).purpose), model: e.model ?? "", provider: e.provider ?? "" }));

  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 4200);
    return () => window.clearTimeout(t);
  }, [notice]);

  const colorOf = (name: string) => (tracks ? trackColor(tracks.tracks, name) : "#94a3b8");
  const run = detail?.run;

  if (pb.error)
    return (
      <div className="flex h-full flex-col">
        <TopNav />
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-ink-300">
          <Icon name="alert" size={28} className="text-bad" />
          <div className="text-[15px] font-semibold text-ink-100">This run could not be loaded</div>
          <div className="text-[13px]">{pb.error}</div>
          <Link to="/" className="btn mt-2">
            <Icon name="back" size={14} /> Back to the library
          </Link>
        </div>
      </div>
    );

  return (
    <div className="flex min-h-full flex-col lg:h-full">
      <TopNav center={<NowLine pb={pb} card={card} />}>
        <ReplayControls pb={pb} />
      </TopNav>
      <main className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-rows-[auto_minmax(0,1.12fr)_auto_minmax(0,1fr)]">
        <div className="flex min-w-0 items-stretch gap-3">
          <div className="min-w-0 flex-1">
            <StageStepper stages={view.stages} finalStatus={pb.finished ? detail?.state?.stages : null} />
          </div>
          <RunMeta pb={pb} title={run?.title ?? spec?.summary ?? runId} />
        </div>
        <div className="grid min-h-0 grid-cols-1 gap-3 lg:grid-cols-2">
          <div className="aspect-video min-h-0 lg:aspect-auto">
            <RealPanel
              runId={runId}
              clock={clock}
              videoPath={videoPath}
              posterPath={poster}
              tracks={tracks}
              overlay={overlay}
              transcript={transcript}
              grounded={grounded}
              calibrating={view.current === "calibrate"}
              size={ingest ? [ingest.width, ingest.height] : null}
              onDuration={(d) => Number.isFinite(d) && setVideoDur(d)}
            />
          </div>
          <div className="aspect-video min-h-0 lg:aspect-auto">
            <TwinPanel
              runId={runId}
              scene={scene}
              cameraTrack={cameraTrack}
              trajectory={traj}
              trajectoryLabel={trajArt?.label ?? null}
              result={simResult}
              rectified={rectified}
              timeSource={timeSource}
            />
          </div>
        </div>
        <Timeline
          clock={clock}
          duration={duration}
          steps={spec?.steps ?? []}
          segments={grounded?.segments ?? []}
          contacts={grounded?.contacts ?? []}
          narration={transcript?.segments ?? []}
          skills={simResult && traj ? skillSpans(simResult.skill_calls, traj.duration_s) : []}
          robotEvents={traj?.events ?? []}
          anchors={anchors}
          colorOf={colorOf}
          robotLabel={view.current === "program" ? "Muse Wonder is writing the program…" : null}
        />
        <div className="grid min-h-0 grid-cols-1 gap-3 lg:grid-cols-[minmax(360px,0.82fr)_2fr]">
          <div className="h-[420px] min-h-0 lg:h-auto">
            <AgentFeed footer={<CorrectionDock runId={runId} enabled={pb.finished} onNotice={setNotice} />} />
          </div>
          <div className="panel flex min-h-[420px] flex-col overflow-hidden lg:min-h-0" data-testid="tabs">
            <div className="flex h-10 shrink-0 items-center gap-1 border-b border-ink-700/60 px-2">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    pinned.current = true;
                    setTab(t.id);
                  }}
                  className={`relative flex h-10 items-center gap-1.5 px-3 text-[12.5px] font-semibold transition-colors ${tab === t.id ? "text-ink-50" : "text-ink-400 hover:text-ink-200"}`}
                >
                  <Icon name={t.icon} size={14} />
                  {t.label}
                  <TabDot tab={t.id} pb={pb} verify={verify} stress={stress} />
                  {tab === t.id && <span className="absolute inset-x-2 bottom-0 h-[2px] rounded-full bg-sparkopen" />}
                </button>
              ))}
            </div>
            <div className="scroll-thin min-h-0 flex-1 overflow-y-auto p-4">
              {tab === "spec" && <SpecTab spec={spec} cross={cross} transcript={transcript} grounded={grounded} />}
              {tab === "program" && <ProgramTab writing={view.stages.program?.status === "running"} runId={runId} codeArtifacts={codeArtifacts} programs={programs} iterations={iterations} animate={!pb.finished} />}
              {tab === "verify" && <VerifyTab runId={runId} verify={verify} />}
              {tab === "stress" && <StressTab
                  runId={runId}
                  stress={stress}
                  codeArtifacts={codeArtifacts}
                  programs={programs}
                  swarm={swarm}
                  attempts={iterations.filter((i) => i.p.agent === "redteam").map((i) => i.p)}
                  running={view.stages.stress?.status === "running"}
                />}
              {tab === "costs" && <CostsTab cost={view.cost} fixture={Boolean(run?.fixture)} />}
            </div>
          </div>
        </div>
      </main>
      {notice && (
        <div className="animate-slide-in fixed bottom-5 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-ink-700 px-4 py-2.5 text-[13px] text-ink-50 shadow-2xl ring-1 ring-ink-500">
          {notice}
        </div>
      )}
    </div>
  );
}

function TabDot({ tab, pb, verify, stress }: { tab: Tab; pb: RunPlayback; verify: Verification | null; stress: StressReport | null }) {
  const st = pb.view.stages;
  const running = (tab === "program" && (st.program?.status === "running" || st.harden?.status === "running")) || (tab === "verify" && st.verify?.status === "running") || (tab === "stress" && st.stress?.status === "running") || (tab === "spec" && st.watch?.status === "running");
  if (running) return <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-sparkopen" />;
  if (tab === "verify" && verify) return <span className={`h-1.5 w-1.5 rounded-full ${verify.agree ? "bg-ok" : "bg-warn"}`} />;
  if (tab === "stress" && stress) return <span className="num text-[10.5px] text-ink-400">{Math.round((stress.robustness_after ?? stress.robustness_before) * stress.cases.length)}/{stress.cases.length}</span>;
  return null;
}

function RunMeta({ pb, title }: { pb: RunPlayback; title: string }) {
  const run = pb.detail?.run;
  return (
    <div className="panel hidden w-[250px] shrink-0 flex-col justify-center gap-1.5 px-3.5 py-2 xl:flex">
      <div className="line-clamp-2 text-[13px] font-semibold leading-snug text-ink-50" title={title}>
        {title}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {pb.mode === "live" && !pb.finished ? (
          <Pill tone="bad">
            <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-bad" /> Live
          </Pill>
        ) : run?.fixture ? (
          <Pill tone="warn" className="!whitespace-normal">Synthetic fixture run (model calls simulated)</Pill>
        ) : run ? (
          <Pill tone="info" className="!whitespace-normal">Replay of a recorded run ({istDate(run.created_at)})</Pill>
        ) : null}
      </div>
    </div>
  );
}

function NowLine({ pb, card }: { pb: RunPlayback; card: SkillCard | null }) {
  const { view, clock, finished } = pb;
  useTicker(!finished, 8);
  const now = clock.recordedNow();
  const cur = view.current;
  if (!pb.detail)
    return (
      <div className="flex items-center gap-2 text-[12.5px] text-ink-400">
        <Spinner size={12} /> Loading the run…
      </div>
    );
  if (finished || view.stages.card?.status === "done") {
    const stress = view.metrics.robustness_after ?? view.metrics.robustness_before;
    return (
      <div className="flex min-w-0 items-center justify-center gap-2.5 text-[12.5px]">
        <span className="flex items-center gap-1.5 font-semibold text-ok">
          <Icon name="check" size={14} /> Skill learned
        </span>
        <span className="hidden truncate text-ink-200 2xl:inline">{card?.title}</span>
        {card && <Pill tone="neutral">program v{card.program_version}</Pill>}
        {stress && typeof stress.value === "number" && <Pill tone="ok">robust {Math.round(stress.value * 100)}%</Pill>}
        <Pill tone="neutral">
          <span className="num">{usd(view.cost.total, 3)}</span> to learn
        </Pill>
        <Link to={`/try/${pb.runId}`} className="btn btn-primary !py-1 !text-[12px]">
          Try it yourself <Icon name="arrow" size={13} />
        </Link>
      </div>
    );
  }
  const inflight = view.inflight[view.inflight.length - 1];
  const stageStart = cur ? view.stages[cur]?.startMs : undefined;
  const el = inflight ? (now - inflight.startMs) / 1000 : stageStart ? (now - stageStart) / 1000 : null;
  return (
    <div className="flex min-w-0 items-center justify-center gap-2.5 text-[12.5px]">
      {cur ? (
        <>
          <span className="relative flex h-2 w-2">
            <span className="absolute inset-0 animate-ping rounded-full bg-sparkopen/60" />
            <span className="relative h-2 w-2 rounded-full bg-sparkopen" />
          </span>
          <span className="truncate font-medium text-ink-100">{STAGE_DOING[cur] ?? STAGE_LABEL[cur]}</span>
          {inflight && <ModelBadge model={inflight.model} size="xs" live />}
          {el != null && <span className="num text-ink-300">{el.toFixed(1)} s</span>}
        </>
      ) : (
        <span className="text-ink-400">Between stages…</span>
      )}
      <span className="mx-1 h-4 w-px bg-ink-700" />
      <span className="num text-ink-200">{usd(view.cost.total, 3)}</span>
      <span className="text-ink-400">spent</span>
    </div>
  );
}

function ReplayControls({ pb }: { pb: RunPlayback }) {
  useTicker(!pb.finished, 4);
  const p = pb.clock.progress();
  if (pb.mode === "live") return null;
  return (
    <div className="flex items-center gap-2 [&_.btn]:max-sm:!px-2">
      <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-ink-700 lg:block" title="Replay progress">
        <div className="h-full rounded-full bg-sparkopen transition-[width] duration-300" style={{ width: `${Math.round(p * 100)}%` }} />
      </div>
      {!pb.finished ? (
        <>
          <button type="button" className="btn btn-ghost !px-2" onClick={pb.togglePlay} aria-label={pb.playing ? "Pause replay" : "Resume replay"}>
            <Icon name={pb.playing ? "pause" : "play"} size={13} />
          </button>
          <Segmented
            value={pb.speed}
            onChange={pb.setSpeed}
            options={[
              { value: 1, label: "1×" },
              { value: 2, label: "2×" },
              { value: 4, label: "4×" },
            ]}
          />
          <button type="button" className="btn !py-1.5" onClick={pb.skipToEnd} data-testid="skip">
            <Icon name="skip" size={12} /> Skip to result
          </button>
        </>
      ) : (
        <button type="button" className="btn !py-1.5" onClick={pb.restart} data-testid="replay-again">
          <Icon name="reset" size={13} /> Replay
        </button>
      )}
    </div>
  );
}
