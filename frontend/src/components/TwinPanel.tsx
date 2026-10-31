import { lazy, Suspense, useState } from "react";
import { artifactUrl } from "../lib/api";
import type { CameraTrack, SimResult, TwinScene as TwinSceneData, TwinTrajectory } from "../lib/types";
import { Icon } from "./Icon";
import { PanelHeader, Segmented, Toggle } from "./PanelHeader";
import { Empty, Pill, Spinner } from "./ui";

const TwinView = lazy(() => import("../twin/TwinView").then((m) => ({ default: m.TwinView })));

interface Props {
  runId: string;
  scene: TwinSceneData | null;
  cameraTrack: CameraTrack | null;
  trajectory: TwinTrajectory | null;
  trajectoryLabel: string | null;
  result: SimResult | null;
  rectified: string | null;
  timeSource: () => number | null;
  defaultCamera?: "orbit" | "real";
}

export function TwinPanel(p: Props) {
  const [cam, setCam] = useState<"orbit" | "real">(p.defaultCamera ?? "orbit");
  const [reach, setReach] = useState(false);
  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden" data-testid="twin-panel">
      <PanelHeader icon={<Icon name="cube" size={15} />} title="Twin" sub={p.trajectoryLabel ?? (p.scene ? "digital twin, PyBullet" : undefined)}>
        {p.result && (
          <Pill tone={p.result.goal_ok ? "ok" : "bad"}>
            <Icon name={p.result.goal_ok ? "check" : "x"} size={11} />
            {p.result.goal_ok ? "goal holds" : "goal fails"}
          </Pill>
        )}
        {p.scene && (
          <>
            <span className="hidden sm:inline-flex">
              <Toggle on={reach} onClick={() => setReach(!reach)} title="Cells the Panda can reach">
                Reach map
              </Toggle>
            </span>
            <Segmented
              value={cam}
              onChange={setCam}
              options={[
                { value: "orbit", label: "Orbit" },
                { value: "real", label: <><span className="hidden sm:inline">Real camera view</span><span className="sm:hidden">Phone</span></>, title: "Snap to the calibrated phone pose" },
              ]}
            />
          </>
        )}
      </PanelHeader>
      <div className="relative min-h-0 flex-1 bg-ink-900">
        {/* The twin mounts at once so the Panda's meshes load while the pipeline runs. */}
        <Suspense
          fallback={
            <div className="flex h-full items-center justify-center text-ink-300">
              <Spinner />
            </div>
          }
        >
          <TwinView
            runId={p.runId}
            scene={p.scene}
            cameraTrack={p.cameraTrack}
            trajectory={p.trajectory}
            timeSource={p.timeSource}
            cameraMode={cam}
            reach={reach}
            labels={cam === "orbit"}
          />
        </Suspense>
        {p.scene && cam === "real" && (
          <div className="pointer-events-none absolute left-3 top-3 rounded-md bg-black/55 px-2 py-1 text-[11px] font-medium text-ink-200 ring-1 ring-white/10">
            Seen from your phone's calibrated pose · robot hidden (it stands where the phone was)
          </div>
        )}
        {!p.scene && (
          <div className="absolute inset-0 bg-ink-900/92 backdrop-blur-[2px]">
            {p.rectified ? (
              <div className="relative h-full w-full animate-fade-in">
                <img src={artifactUrl(p.runId, p.rectified)} alt="Rectified table, top-down" className="absolute inset-0 h-full w-full object-contain p-6 opacity-80" />
                <div className="absolute inset-x-0 bottom-3 flex justify-center">
                  <span className="rounded-md bg-black/60 px-2.5 py-1 text-[11.5px] text-ink-200 ring-1 ring-white/10">Your table, measured: 10 px per cm, top-down. The twin builds after Ground.</span>
                </div>
              </div>
            ) : (
              <div className="bg-grid h-full">
                <Empty icon="cube" title="The digital twin builds here" hint="A Franka Panda, your table, and a stand-in for every object." />
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
