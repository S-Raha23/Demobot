// The replay engine (docs/07 "Replay engine"): plays a recorded events.jsonl with its original
// relative timing scaled by speed. Gaps longer than `maxGapS` are compressed (the backend's SSE
// replay does the same), so replays never stall. Live runs use LiveStream below; both feed the
// same reducer (state.ts), so one code path renders live runs and replays.

import type { RunEvent } from "../lib/types";

export interface Clock {
  now(): number; // milliseconds
}

const systemClock: Clock = {
  now: () => (typeof performance !== "undefined" ? performance.now() : Date.now()),
};

export interface EngineOptions {
  speed?: number;
  maxGapS?: number;
  clock?: Clock;
  autoplay?: boolean;
}

export const tsOf = (e: RunEvent) => new Date(e.ts).getTime();

/** Replay-timeline offsets (seconds, unscaled by speed) with long gaps capped. */
export function replayOffsets(events: RunEvent[], maxGapS = 3): number[] {
  const out: number[] = [];
  let acc = 0;
  let prev: number | null = null;
  for (const e of events) {
    const t = tsOf(e);
    if (prev !== null) acc += Math.min(maxGapS, Math.max(0, (t - prev) / 1000));
    prev = t;
    out.push(acc);
  }
  return out;
}

export class ReplayEngine {
  readonly events: RunEvent[];
  readonly offsets: number[];
  readonly recorded: number[];
  private pos = 0;
  private vBase = 0;
  private wBase: number;
  private _speed: number;
  private _playing: boolean;
  private clock: Clock;

  constructor(events: RunEvent[], opts: EngineOptions = {}) {
    this.events = [...events].sort((a, b) => a.seq - b.seq);
    this.offsets = replayOffsets(this.events, opts.maxGapS ?? 3);
    this.recorded = this.events.map(tsOf);
    this.clock = opts.clock ?? systemClock;
    this._speed = opts.speed ?? 1;
    this._playing = opts.autoplay ?? true;
    this.wBase = this.clock.now();
  }

  get total(): number {
    return this.offsets.length ? this.offsets[this.offsets.length - 1] : 0;
  }
  get speed(): number {
    return this._speed;
  }
  get playing(): boolean {
    return this._playing;
  }
  get done(): boolean {
    return this.pos >= this.events.length;
  }
  get emitted(): number {
    return this.pos;
  }

  /** The replay-timeline position in seconds. */
  virtual(): number {
    const v = this._playing ? this.vBase + ((this.clock.now() - this.wBase) / 1000) * this._speed : this.vBase;
    return Math.min(v, this.total);
  }

  progress(): number {
    return this.total > 0 ? this.virtual() / this.total : this.done ? 1 : 0;
  }

  private anchor(): void {
    this.vBase = this.virtual();
    this.wBase = this.clock.now();
  }

  setSpeed(s: number): void {
    this.anchor();
    this._speed = Math.max(0.1, s);
  }

  pause(): void {
    if (!this._playing) return;
    this.anchor();
    this._playing = false;
  }

  play(): void {
    if (this._playing) return;
    this.wBase = this.clock.now();
    this._playing = true;
  }

  /** Events that are now due (in order). Call this from a timer. */
  tick(): RunEvent[] {
    const v = this.virtual();
    const out: RunEvent[] = [];
    while (this.pos < this.events.length && this.offsets[this.pos] <= v + 1e-9) {
      out.push(this.events[this.pos++]);
    }
    return out;
  }

  /** "Skip to result": everything that is left, at once. */
  skipToEnd(): RunEvent[] {
    this.vBase = this.total;
    this.wBase = this.clock.now();
    const out = this.events.slice(this.pos);
    this.pos = this.events.length;
    return out;
  }

  /** Seconds (replay timeline) until the next event, or null when done. */
  nextIn(): number | null {
    if (this.done) return null;
    return Math.max(0, (this.offsets[this.pos] - this.virtual()) / this._speed);
  }

  /** The recorded wall-clock time (ms) at the current replay position, interpolated between
   * events, so live timers show the real elapsed time of a call even when gaps are compressed. */
  recordedNow(): number {
    return this.recordedAt(this.virtual());
  }

  recordedAt(v: number): number {
    const n = this.offsets.length;
    if (!n) return 0;
    if (v <= this.offsets[0]) return this.recorded[0];
    if (v >= this.offsets[n - 1]) return this.recorded[n - 1];
    let lo = 0;
    let hi = n - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.offsets[mid] <= v) lo = mid;
      else hi = mid;
    }
    const span = this.offsets[hi] - this.offsets[lo];
    const f = span > 0 ? (v - this.offsets[lo]) / span : 1;
    return this.recorded[lo] + f * (this.recorded[hi] - this.recorded[lo]);
  }
}

/** A live run: the backend's SSE stream (`event: event` lines, then `event: end`). */
export class LiveStream {
  private es: EventSource | null = null;
  constructor(
    private url: string,
    private onEvents: (e: RunEvent[]) => void,
    private onEnd: () => void,
    private onError?: () => void,
  ) {}

  start(): void {
    const es = new EventSource(this.url);
    this.es = es;
    es.addEventListener("event", (m) => {
      try {
        this.onEvents([JSON.parse((m as MessageEvent).data) as RunEvent]);
      } catch {
        /* skip malformed line */
      }
    });
    es.addEventListener("end", () => {
      es.close();
      this.onEnd();
    });
    es.onerror = () => this.onError?.();
  }

  stop(): void {
    this.es?.close();
    this.es = null;
  }
}
