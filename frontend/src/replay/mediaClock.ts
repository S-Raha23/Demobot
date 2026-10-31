// The shared timeline clock (video seconds). It is not React state: the video, the canvas
// overlay, the twin and the scrubber read it every animation frame.

export class MediaClock {
  t = 0;
  duration = 0;
  playing = true;
  loop = true;
  /** Seconds to hold the last frame before looping. */
  hold = 1.2;
  private held = 0;
  private listeners = new Set<(t: number) => void>();
  private last = 0;
  private raf = 0;
  /** When set, the clock follows this media element while playing. */
  video: HTMLVideoElement | null = null;

  start() {
    this.last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      this.advance(dt);
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
  }

  stop() {
    cancelAnimationFrame(this.raf);
  }

  private advance(dt: number) {
    if (this.duration <= 0) return;
    if (this.playing) {
      const v = this.video;
      if (v && v.readyState >= 2 && !v.paused && !v.ended && v.currentTime < this.duration - 0.05) {
        this.t = v.currentTime;
      } else if (this.t >= this.duration) {
        this.held += dt;
        if (this.loop && this.held >= this.hold) {
          this.held = 0;
          this.seek(0);
          return;
        }
      } else {
        this.t = Math.min(this.duration, this.t + dt);
      }
    }
    this.syncVideo();
    this.emit();
  }

  private syncVideo() {
    const v = this.video;
    if (!v || v.readyState < 1) return;
    if (this.playing && this.t < this.duration) {
      if (v.paused) v.play().catch(() => undefined);
      if (Math.abs(v.currentTime - this.t) > 0.3) v.currentTime = this.t;
    } else {
      if (!v.paused) v.pause();
      if (Math.abs(v.currentTime - this.t) > 0.04) v.currentTime = Math.min(this.t, (v.duration || this.duration) - 0.02);
    }
  }

  seek(t: number) {
    this.t = Math.max(0, Math.min(this.duration, t));
    this.held = 0;
    const v = this.video;
    if (v && v.readyState >= 1) v.currentTime = Math.min(this.t, (v.duration || this.duration) - 0.02);
    this.emit();
  }

  setPlaying(p: boolean) {
    this.playing = p;
    if (p && this.t >= this.duration) this.seek(0);
    this.syncVideo();
    this.emit();
  }

  subscribe(fn: (t: number) => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private emit() {
    for (const fn of this.listeners) fn(this.t);
  }
}
