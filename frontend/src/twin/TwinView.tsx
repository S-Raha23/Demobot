import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { CameraTrack, Layout, TwinScene as TwinSceneData, TwinTrajectory } from "../lib/types";
import { artifactUrl } from "../lib/api";
import { TwinScene, type CameraMode, type TwinSceneOptions } from "./TwinScene";
import type { V3 } from "../lib/frames";

export interface TwinViewProps {
  runId: string;
  scene: TwinSceneData | null;
  layout?: Layout | null;
  cameraTrack?: CameraTrack | null;
  trajectory: TwinTrajectory | null;
  timeSource?: () => number | null;
  cameraMode: CameraMode;
  reach?: boolean;
  labels?: boolean;
  ghostRobot?: boolean;
  options?: TwinSceneOptions;
  className?: string;
}

export interface TwinHandle {
  rotateSelected(deg: number): void;
  select(name: string | null): void;
}

export const TwinView = forwardRef<TwinHandle, TwinViewProps>(function TwinView(p, ref) {
  const host = useRef<HTMLDivElement>(null);
  const tw = useRef<TwinScene | null>(null);
  const timeRef = useRef(p.timeSource);
  timeRef.current = p.timeSource;

  useImperativeHandle(
    ref,
    () => ({
      rotateSelected: (deg: number) => tw.current?.rotateSelected(deg),
      select: (name: string | null) => tw.current?.select(name),
    }),
    [],
  );

  useEffect(() => {
    const s = new TwinScene(host.current!, p.options);
    s.timeSource = () => timeRef.current?.() ?? null;
    s.loadRobot();
    tw.current = s;
    return () => {
      s.dispose();
      tw.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const layout = p.layout ?? p.scene?.layout ?? null;

  useEffect(() => {
    const s = tw.current;
    if (!s || !p.scene) return;
    const sc = p.scene;
    const tex = sc.table_texture
      ? {
          url: artifactUrl(p.runId, sc.table_texture.startsWith("artifacts/") ? sc.table_texture : `artifacts/${sc.table_texture}`),
          originCm: sc.rectify?.origin_cm ?? ([0, 0] as [number, number]),
          pxPerCm: sc.rectify?.px_per_cm ?? 10,
        }
      : null;
    s.setTable(sc.layout.work_area, sc.layout.robot_base_cm, tex);
    s.setRobotBaseCm(sc.layout.robot_base_cm);
    const ct = p.cameraTrack;
    const f0 = ct?.frames?.[0];
    s.setPhoneCamera(
      f0 && ct
        ? { rvec: f0.rvec as V3, tvec: f0.tvec as V3, focal: ct.focal_px, principal: ct.principal_px, imageSize: sc.image_size }
        : { rvec: sc.camera.rvec as V3, tvec: sc.camera.tvec as V3, focal: sc.camera.focal_px, principal: sc.camera.principal_px, imageSize: sc.image_size },
    );
    s.setCameraMode(p.cameraMode);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [p.scene, p.cameraTrack, p.runId]);

  useEffect(() => {
    if (layout) tw.current?.setLayout(layout.objects.map((o) => ({ ...o })));
  }, [layout]);

  useEffect(() => {
    tw.current?.setTrajectory(p.trajectory);
  }, [p.trajectory]);

  useEffect(() => {
    tw.current?.setCameraMode(p.cameraMode);
  }, [p.cameraMode]);

  useEffect(() => {
    tw.current?.setReach(p.scene?.reach ?? null, Boolean(p.reach));
  }, [p.reach, p.scene]);

  useEffect(() => {
    tw.current?.setLabels(p.labels ?? true);
  }, [p.labels]);

  useEffect(() => {
    tw.current?.setRobotGhost(Boolean(p.ghostRobot));
  }, [p.ghostRobot]);

  return <div ref={host} className={`relative h-full w-full overflow-hidden ${p.className ?? ""}`} />;
});
