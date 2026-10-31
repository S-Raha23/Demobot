import { describe, expect, it } from "vitest";
import { ReplayEngine, replayOffsets, type Clock } from "../src/replay/engine";
import { emptyView, reduceEvents } from "../src/replay/state";
import type { RunEvent } from "../src/lib/types";

const t0 = Date.parse("2026-10-31T09:00:00.000Z");
function ev(seq: number, dtS: number, type: RunEvent["type"], extra: Partial<RunEvent> = {}): RunEvent {
  return {
    ts: new Date(t0 + dtS * 1000).toISOString(),
    run_id: "r",
    seq,
    stage: "watch",
    type,
    payload: {},
    ...extra,
  };
}

class FakeClock implements Clock {
  t = 0;
  now() {
    return this.t;
  }
  advance(s: number) {
    this.t += s * 1000;
  }
}

const events: RunEvent[] = [
  ev(0, 0, "stage_start"),
  ev(1, 1, "log", { payload: { heartbeat: true, purpose: "watch", model: "muse-spark-1.3", elapsed_s: 5 } }),
  ev(2, 11, "model_call", {
    model: "muse-spark-1.3",
    provider: "meta",
    cost_usd: 0.03,
    payload: { purpose: "watch", open_weight: false },
  }),
  ev(3, 12, "stage_end", { payload: { ok: true, summary: "done", duration_s: 12 } }),
];

describe("replayOffsets", () => {
  it("keeps short gaps and caps long ones at maxGapS", () => {
    expect(replayOffsets(events, 3)).toEqual([0, 1, 4, 5]);
  });
});

describe("ReplayEngine", () => {
  it("emits events on their (capped) relative timing at 1x", () => {
    const c = new FakeClock();
    const e = new ReplayEngine(events, { clock: c });
    expect(e.tick().map((x) => x.seq)).toEqual([0]);
    c.advance(0.5);
    expect(e.tick()).toEqual([]);
    c.advance(0.6);
    expect(e.tick().map((x) => x.seq)).toEqual([1]);
    c.advance(2.95);
    expect(e.tick().map((x) => x.seq)).toEqual([2]);
    c.advance(1);
    expect(e.tick().map((x) => x.seq)).toEqual([3]);
    expect(e.done).toBe(true);
  });

  it("scales timing by speed, and speed changes mid-replay keep the position", () => {
    const c = new FakeClock();
    const e = new ReplayEngine(events, { clock: c, speed: 2 });
    e.tick();
    c.advance(0.5); // v = 1
    expect(e.tick().map((x) => x.seq)).toEqual([1]);
    e.setSpeed(4);
    expect(e.virtual()).toBeCloseTo(1);
    c.advance(0.75); // v = 4
    expect(e.tick().map((x) => x.seq)).toEqual([2]);
  });

  it("pauses and resumes without losing time", () => {
    const c = new FakeClock();
    const e = new ReplayEngine(events, { clock: c });
    e.tick();
    c.advance(0.9);
    e.pause();
    c.advance(100);
    expect(e.tick()).toEqual([]);
    expect(e.virtual()).toBeCloseTo(0.9);
    e.play();
    c.advance(0.2);
    expect(e.tick().map((x) => x.seq)).toEqual([1]);
  });

  it("skips to the result with everything that is left", () => {
    const c = new FakeClock();
    const e = new ReplayEngine(events, { clock: c });
    e.tick();
    expect(e.skipToEnd().map((x) => x.seq)).toEqual([1, 2, 3]);
    expect(e.done).toBe(true);
    expect(e.progress()).toBe(1);
  });

  it("maps the replay position back to recorded time (timers show real elapsed time)", () => {
    const c = new FakeClock();
    const e = new ReplayEngine(events, { clock: c });
    // between seq 1 (v=1, rec=1s) and seq 2 (v=4, rec=11s): halfway is rec 6 s
    expect((e.recordedAt(2.5) - t0) / 1000).toBeCloseTo(6);
    expect((e.recordedAt(99) - t0) / 1000).toBeCloseTo(12);
  });
});

describe("reduceEvents", () => {
  it("tracks stages, in-flight calls, and costs", () => {
    let v = reduceEvents(emptyView(), events.slice(0, 2));
    expect(v.stages.watch.status).toBe("running");
    expect(v.current).toBe("watch");
    expect(v.inflight).toHaveLength(1);
    expect((v.inflight[0].startMs - t0) / 1000).toBeCloseTo(-4); // started 5 s before the heartbeat
    v = reduceEvents(v, events.slice(2));
    expect(v.inflight).toHaveLength(0);
    expect(v.stages.watch.status).toBe("done");
    expect(v.stages.watch.models).toEqual([{ id: "muse-spark-1.3", provider: "meta" }]);
    expect(v.cost.total).toBeCloseTo(0.03);
    expect(v.cost.byProvider.meta).toBeCloseTo(0.03);
  });
});
