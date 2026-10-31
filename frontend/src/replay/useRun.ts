import { createContext, useCallback, useContext, useEffect, useReducer, useRef, useState } from "react";
import { api, fetchArtifactJson, fetchArtifactText } from "../lib/api";
import type { RunDetail, RunEvent } from "../lib/types";
import { LiveStream, ReplayEngine } from "./engine";
import { emptyView, reduceEvents, type RunView } from "./state";

export type PlayMode = "replay" | "live";

export interface RunClock {
  /** Recorded wall-clock time (ms) "now" in the run: interpolated in replays, Date.now() live. */
  recordedNow(): number;
  progress(): number;
}

export interface RunPlayback {
  runId: string;
  detail: RunDetail | null;
  error: string | null;
  mode: PlayMode;
  view: RunView;
  clock: RunClock;
  speed: number;
  playing: boolean;
  finished: boolean;
  setSpeed(s: number): void;
  togglePlay(): void;
  skipToEnd(): void;
  restart(): void;
}

type Action = { type: "events"; events: RunEvent[] } | { type: "reset" } | { type: "ended" };

function reducer(state: RunView, a: Action): RunView {
  if (a.type === "reset") return emptyView();
  if (a.type === "ended") return { ...state, ended: true };
  return reduceEvents(state, a.events);
}

/** Only these run states are streamed live; everything else (done, failed, partial…) replays. */
const LIVE = new Set(["running", "queued", "pending", "live", "started"]);

export function useRunPlayback(runId: string, opts: { speed?: number; skip?: boolean } = {}): RunPlayback {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [view, dispatch] = useReducer(reducer, undefined, emptyView);
  const [mode, setMode] = useState<PlayMode>("replay");
  const [speed, setSpeedState] = useState(opts.speed ?? 2);
  const [playing, setPlaying] = useState(true);
  const [finished, setFinished] = useState(false);
  const [generation, setGeneration] = useState(0);
  const engineRef = useRef<ReplayEngine | null>(null);
  const liveRef = useRef<LiveStream | null>(null);
  const eventsRef = useRef<RunEvent[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: number | undefined;
    dispatch({ type: "reset" });
    setFinished(false);
    setError(null);
    (async () => {
      try {
        const d = await api.run(runId);
        if (cancelled) return;
        setDetail(d);
        const status = d.run?.status ?? "";
        const isReplay = !LIVE.has(status) || d.run?.mode === "replay";
        if (isReplay) {
          setMode("replay");
          const events = eventsRef.current ?? (await api.events(runId));
          if (cancelled) return;
          eventsRef.current = events;
          const eng = new ReplayEngine(events, { speed: opts.speed ?? speed });
          engineRef.current = eng;
          if (opts.skip && generation === 0) {
            dispatch({ type: "events", events: eng.skipToEnd() });
            dispatch({ type: "ended" });
            setFinished(true);
            return;
          }
          const loop = () => {
            const due = eng.tick();
            if (due.length) dispatch({ type: "events", events: due });
            if (eng.done) {
              dispatch({ type: "ended" });
              setFinished(true);
              return;
            }
            timer = window.setTimeout(loop, 40);
          };
          loop();
        } else {
          setMode("live");
          const ls = new LiveStream(
            `/api/runs/${encodeURIComponent(runId)}/events`,
            (evs) => dispatch({ type: "events", events: evs }),
            () => {
              dispatch({ type: "ended" });
              setFinished(true);
            },
          );
          liveRef.current = ls;
          ls.start();
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
      liveRef.current?.stop();
      liveRef.current = null;
      engineRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId, generation]);

  const clock: RunClock = {
    recordedNow: () => engineRef.current?.recordedNow() ?? Date.now(),
    progress: () => (engineRef.current ? engineRef.current.progress() : finished ? 1 : 0),
  };

  const setSpeed = useCallback((s: number) => {
    engineRef.current?.setSpeed(s);
    setSpeedState(s);
  }, []);

  const togglePlay = useCallback(() => {
    const e = engineRef.current;
    if (!e) return;
    if (e.playing) e.pause();
    else e.play();
    setPlaying(e.playing);
  }, []);

  const skipToEnd = useCallback(() => {
    const e = engineRef.current;
    if (!e) return;
    const rest = e.skipToEnd();
    if (rest.length) dispatch({ type: "events", events: rest });
  }, []);

  const restart = useCallback(() => {
    setPlaying(true);
    setGeneration((g) => g + 1);
  }, []);

  return { runId, detail, error, mode, view, clock, speed, playing, finished, setSpeed, togglePlay, skipToEnd, restart };
}

export const RunContext = createContext<RunPlayback | null>(null);

export function useRun(): RunPlayback {
  const r = useContext(RunContext);
  if (!r) throw new Error("useRun outside RunContext");
  return r;
}

/** Load a JSON artifact once it has been announced (path null = not yet). */
export function useArtifact<T>(runId: string | null | undefined, path: string | null | undefined): T | null {
  const [data, setData] = useState<{ key: string; value: T } | null>(null);
  const key = runId && path ? `${runId}/${path}` : null;
  useEffect(() => {
    if (!runId || !path) return;
    let alive = true;
    fetchArtifactJson<T>(runId, path)
      .then((v) => alive && setData({ key: `${runId}/${path}`, value: v }))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [runId, path]);
  return data && data.key === key ? data.value : null;
}

export function useArtifactText(runId: string | null | undefined, path: string | null | undefined): string | null {
  const [data, setData] = useState<{ key: string; value: string } | null>(null);
  const key = runId && path ? `${runId}/${path}` : null;
  useEffect(() => {
    if (!runId || !path) return;
    let alive = true;
    fetchArtifactText(runId, path)
      .then((v) => alive && setData({ key: `${runId}/${path}`, value: v }))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [runId, path]);
  return data && data.key === key ? data.value : null;
}

/** Re-render at `hz` while `active` (for live timers). */
export function useTicker(active: boolean, hz = 10): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setN((x) => x + 1), 1000 / hz);
    return () => window.clearInterval(id);
  }, [active, hz]);
  return n;
}
