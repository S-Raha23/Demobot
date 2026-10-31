import { useEffect, useRef, useState } from "react";
import { artifactUrl } from "../lib/api";
import { indexAt } from "../lib/sync";
import type { CalibrationOverlay, GroundedDemo, Track, TracksFile, Transcript, Vec2 } from "../lib/types";
import type { MediaClock } from "../replay/mediaClock";
import { Icon } from "./Icon";
import { PanelHeader, Toggle } from "./PanelHeader";
import { Empty } from "./ui";

export const TRACK_COLORS = ["#38bdf8", "#f472b6", "#a3e635", "#fb923c", "#c084fc", "#facc15", "#2dd4bf", "#f87171"];

export function trackColor(tracks: Track[], name: string): string {
  const objs = tracks.filter((t) => t.name !== "hand");
  const i = objs.findIndex((t) => t.name === name);
  return name === "hand" ? "#f8fafc" : TRACK_COLORS[(i < 0 ? 0 : i) % TRACK_COLORS.length];
}

interface Props {
  runId: string;
  clock: MediaClock;
  videoPath: string | null;
  posterPath: string | null;
  tracks: TracksFile | null;
  overlay: CalibrationOverlay | null;
  transcript: Transcript | null;
  grounded: GroundedDemo | null;
  calibrating: boolean;
  size: [number, number] | null;
  onDuration?: (d: number) => void;
}

function polyCentroid(p: Vec2[]): Vec2 {
  let x = 0;
  let y = 0;
  for (const q of p) {
    x += q[0];
    y += q[1];
  }
  return [x / p.length, y / p.length];
}

export function RealPanel(props: Props) {
  const { runId, clock, videoPath, posterPath, tracks, overlay, transcript, grounded, calibrating, size, onDuration } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [masks, setMasks] = useState(true);
  const [trails, setTrails] = useState(true);
  const [markers, setMarkers] = useState(false);
  const [caption, setCaption] = useState<string | null>(null);
  const [tLabel, setTLabel] = useState("0:00.0");
  const showMarkers = markers || calibrating;

  useEffect(() => {
    clock.video = videoRef.current;
    return () => {
      if (clock.video === videoRef.current) clock.video = null;
    };
  }, [clock, videoPath]);

  useEffect(() => {
    const draw = (t: number) => {
      const cv = canvasRef.current;
      const box = boxRef.current;
      const vid = videoRef.current;
      if (!cv || !box) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const W = box.clientWidth;
      const H = box.clientHeight;
      if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) {
        cv.width = Math.round(W * dpr);
        cv.height = Math.round(H * dpr);
      }
      const g = cv.getContext("2d")!;
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, W, H);
      const iw = tracks?.size[0] ?? size?.[0] ?? vid?.videoWidth ?? 1280;
      const ih = tracks?.size[1] ?? size?.[1] ?? vid?.videoHeight ?? 720;
      const s = Math.min(W / iw, H / ih);
      const ox = (W - iw * s) / 2;
      const oy = (H - ih * s) / 2;
      const P = (p: Vec2): Vec2 => [ox + p[0] * s, oy + p[1] * s];

      const ids = tracks?.tracks.map((x) => x.track_id) ?? [];
      const uniqueIds = ids.every((x) => x != null) && new Set(ids).size === ids.length;
      if (tracks && (masks || trails)) {
        const moving = new Set((grounded?.segments ?? []).filter((m) => t >= m.t0 - 0.2 && t <= m.t1 + 0.2).map((m) => m.object));
        tracks.tracks.forEach((tr, ti) => {
          const col = trackColor(tracks.tracks, tr.name);
          const fr = tr.frames;
          const i = indexAt(fr, t, (f) => f.t);
          if (i < 0) return;
          const f = fr[i];
          const isHand = tr.name === "hand";
          if (trails && !isHand) {
            const pts: Vec2[] = [];
            const j0 = Math.max(0, indexAt(fr, t - 1.5, (x) => x.t));
            for (let j = j0; j <= i; j++) {
              const q = fr[j].poly_px;
              if (q && q.length > 2) pts.push(P(polyCentroid(q)));
            }
            if (pts.length > 1) {
              g.lineCap = "round";
              g.lineJoin = "round";
              for (let k = 1; k < pts.length; k++) {
                const a = k / pts.length;
                g.strokeStyle = col;
                g.globalAlpha = 0.15 + 0.75 * a;
                g.lineWidth = 1.5 + 2.5 * a;
                g.beginPath();
                g.moveTo(pts[k - 1][0], pts[k - 1][1]);
                g.lineTo(pts[k][0], pts[k][1]);
                g.stroke();
              }
              g.globalAlpha = 1;
            }
          }
          if (!masks || !f.poly_px || f.poly_px.length < 3 || t - f.t > 0.35) return;
          const poly = f.poly_px.map(P);
          g.beginPath();
          poly.forEach((p, k) => (k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
          g.closePath();
          if (isHand) {
            g.setLineDash([5, 4]);
            g.strokeStyle = "rgba(248,250,252,0.85)";
            g.lineWidth = 1.6;
            g.fillStyle = "rgba(248,250,252,0.07)";
            g.fill();
            g.stroke();
            g.setLineDash([]);
          } else {
            const hot = moving.has(tr.name);
            g.fillStyle = col + (hot ? "66" : "40");
            g.shadowColor = col;
            g.shadowBlur = hot ? 18 : 10;
            g.fill();
            g.shadowBlur = 0;
            g.strokeStyle = col;
            g.lineWidth = hot ? 2.6 : 1.8;
            g.stroke();
          }
          // label
          let minX = Infinity;
          let minY = Infinity;
          for (const p of poly) {
            minX = Math.min(minX, p[0]);
            minY = Math.min(minY, p[1]);
          }
          const text = `#${uniqueIds ? tr.track_id : ti} ${tr.name}`;
          g.font = "600 11.5px Inter Variable, Inter, sans-serif";
          const tw = g.measureText(text).width;
          const lx = Math.max(ox + 2, Math.min(minX, ox + iw * s - tw - 16));
          const ly = Math.max(oy + 2, minY - 22);
          g.fillStyle = "rgba(8,12,18,0.78)";
          roundRect(g, lx, ly, tw + 14, 18, 9);
          g.fill();
          g.strokeStyle = isHand ? "rgba(248,250,252,0.5)" : col + "aa";
          g.lineWidth = 1;
          g.stroke();
          g.fillStyle = isHand ? "#f8fafc" : col;
          g.fillText(text, lx + 7, ly + 13);
        });
      }

      if (overlay && showMarkers) {
        g.lineWidth = 2;
        for (const m of overlay.markers) {
          const q = m.corners_px.map(P);
          g.beginPath();
          q.forEach((p, k) => (k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
          g.closePath();
          g.strokeStyle = "#5eead4";
          g.shadowColor = "#2dd4bf";
          g.shadowBlur = 12;
          g.stroke();
          g.shadowBlur = 0;
          const c = polyCentroid(q);
          g.font = "700 11px JetBrains Mono, monospace";
          g.fillStyle = "rgba(8,12,18,0.8)";
          roundRect(g, c[0] - 11, c[1] - 9, 22, 18, 5);
          g.fill();
          g.fillStyle = "#5eead4";
          g.fillText(String(m.id), c[0] - 3.5, c[1] + 4);
        }
        const wa = overlay.work_area_px.map(P);
        g.setLineDash([7, 6]);
        g.strokeStyle = "rgba(94,234,212,0.7)";
        g.lineWidth = 1.5;
        g.beginPath();
        wa.forEach((p, k) => (k ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
        g.closePath();
        g.stroke();
        g.setLineDash([]);
        const o = P(overlay.axes_px.origin);
        arrow(g, o, P(overlay.axes_px.x10cm), "#f87171", "x · 10 cm");
        arrow(g, o, P(overlay.axes_px.y10cm), "#34d399", "y · 10 cm");
      }

      // captions and time
      const seg = transcript?.segments.find((x) => t >= x.t0 && t <= x.t1 + 0.4);
      setCaption(seg ? seg.text : null);
      setTLabel(fmt(t));
    };
    const unsub = clock.subscribe(draw);
    draw(clock.t);
    return () => {
      unsub();
    };
  }, [clock, tracks, overlay, transcript, grounded, masks, trails, showMarkers, size]);

  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <PanelHeader icon={<Icon name="video" size={15} />} title="Real" sub="your demo, stabilised">
        {tracks && (
          <>
            <Toggle on={masks} onClick={() => setMasks(!masks)} title="SAM 3.1 masks and track IDs">
              Masks
            </Toggle>
            <Toggle on={trails} onClick={() => setTrails(!trails)} title="1.5 s motion trails">
              Trails
            </Toggle>
          </>
        )}
        {overlay && (
          <Toggle on={showMarkers} onClick={() => setMarkers(!markers)} title="ArUco markers and table axes">
            Markers
          </Toggle>
        )}
        <span className="num ml-1 rounded-md bg-ink-850 px-1.5 py-[2px] text-[11px] text-ink-300 ring-1 ring-ink-700">{tLabel}</span>
      </PanelHeader>
      <div ref={boxRef} className="relative min-h-0 flex-1 bg-black/60">
        {videoPath ? (
          <video
            ref={videoRef}
            key={videoPath}
            src={artifactUrl(runId, videoPath)}
            muted
            playsInline
            preload="auto"
            className="absolute inset-0 h-full w-full object-contain"
            onLoadedMetadata={(e) => onDuration?.(e.currentTarget.duration)}
          />
        ) : posterPath ? (
          <>
            <img src={artifactUrl(runId, posterPath)} alt="First frame" className="absolute inset-0 h-full w-full object-contain opacity-60" />
            <div className="shimmer absolute inset-0" />
          </>
        ) : (
          <div className="bg-grid absolute inset-0">
            <Empty icon="video" title="Waiting for the clip" hint="The stabilised demo appears after Calibrate." />
          </div>
        )}
        <canvas ref={canvasRef} className="pointer-events-none absolute inset-0 h-full w-full" />
        {caption && (
          <div className="pointer-events-none absolute inset-x-0 bottom-4 flex justify-center px-6">
            <div className="animate-fade-in max-w-[80%] rounded-lg bg-black/70 px-3.5 py-1.5 text-center text-[15px] font-medium leading-snug text-white shadow-lg ring-1 ring-white/10 backdrop-blur-sm">
              <span className="mr-2 align-middle text-[10px] font-bold uppercase tracking-wider text-voice">{transcript?.language}</span>
              {caption}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function fmt(t: number) {
  const m = Math.floor(t / 60);
  return `${m}:${(t - m * 60).toFixed(1).padStart(4, "0")}`;
}

function roundRect(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function arrow(g: CanvasRenderingContext2D, a: Vec2, b: Vec2, col: string, label: string) {
  const ang = Math.atan2(b[1] - a[1], b[0] - a[0]);
  g.strokeStyle = col;
  g.fillStyle = col;
  g.lineWidth = 3;
  g.shadowColor = col;
  g.shadowBlur = 8;
  g.beginPath();
  g.moveTo(a[0], a[1]);
  g.lineTo(b[0], b[1]);
  g.stroke();
  g.beginPath();
  g.moveTo(b[0], b[1]);
  g.lineTo(b[0] - 11 * Math.cos(ang - 0.4), b[1] - 11 * Math.sin(ang - 0.4));
  g.lineTo(b[0] - 11 * Math.cos(ang + 0.4), b[1] - 11 * Math.sin(ang + 0.4));
  g.closePath();
  g.fill();
  g.shadowBlur = 0;
  g.font = "600 11px JetBrains Mono, monospace";
  g.fillText(label, b[0] + 8 * Math.cos(ang) + 4, b[1] + 8 * Math.sin(ang) + 4);
}
