"""Live Twin helpers (docs/11 F2): pure, testable parts of the live loop — associating SAM
detections (table cm) to known objects with confirmation and smoothing.

The Modal GPU segmenter, WebSocket transport and phone pairing are deployment pieces; this
module is the deterministic core they feed, so it is unit-tested offline. Association is
greedy nearest-neighbour within a gate (the tables here hold < 10 objects); a detection must
be seen `confirm_frames` times before it moves the twin, then positions are exponentially
smoothed — exactly the 3-frame confirmation the spec asks for.
"""

import math
from dataclasses import dataclass, field

GATE_CM = 12.0


@dataclass
class Detection:
    label: str
    x: float
    y: float
    score: float = 1.0


@dataclass
class Track:
    name: str
    label: str
    x: float
    y: float
    seen: int = 0
    confirmed: bool = False


@dataclass
class LiveTracker:
    """Mirrors layout objects from per-frame detections (table cm)."""

    confirm_frames: int = 3
    alpha: float = 0.5  # smoothing: new = alpha*det + (1-alpha)*old
    tracks: dict[str, Track] = field(default_factory=dict)

    def seed(self, objects: list[tuple[str, str, float, float]]) -> None:
        """(name, label, x, y) of the objects the twin starts from."""
        self.tracks = {n: Track(n, lab, x, y, seen=self.confirm_frames, confirmed=True)
                       for n, lab, x, y in objects}  # fmt: skip

    def update(self, dets: list[Detection]) -> dict[str, tuple[float, float]]:
        """One frame of detections -> the confirmed twin positions {name: (x, y)}."""
        # greedy nearest matching, same label only, within the gate
        pairs: list[tuple[float, str, int]] = []
        for name, t in self.tracks.items():
            for i, d in enumerate(dets):
                if d.label == t.label:
                    dist = math.dist((t.x, t.y), (d.x, d.y))
                    if dist <= GATE_CM:
                        pairs.append((dist, name, i))
        used_t: set[str] = set()
        used_d: set[int] = set()
        for _, name, i in sorted(pairs):
            if name in used_t or i in used_d:
                continue
            used_t.add(name)
            used_d.add(i)
            t, d = self.tracks[name], dets[i]
            t.seen += 1
            if t.seen >= self.confirm_frames:
                t.confirmed = True
            if t.confirmed:
                t.x = round(self.alpha * d.x + (1 - self.alpha) * t.x, 2)
                t.y = round(self.alpha * d.y + (1 - self.alpha) * t.y, 2)
        for name, t in self.tracks.items():
            if name not in used_t:
                t.seen = 0  # must re-confirm after a miss; position holds meanwhile
        # Unseeded detections ("Add object"): start a provisional track for each
        # one no existing track claimed. It joins `tracks` unconfirmed, so the
        # greedy match above associates later frames with it; it is returned
        # only after `confirm_frames` sightings (a miss resets the count).
        for i, d in enumerate(dets):
            if i in used_d:
                continue
            name = d.label
            if name in self.tracks:
                k = 2
                while f"{d.label} {k}" in self.tracks:
                    k += 1
                name = f"{d.label} {k}"
            self.tracks[name] = Track(name, d.label, d.x, d.y, seen=1,
                                      confirmed=self.confirm_frames <= 1)  # fmt: skip
        return {n: (t.x, t.y) for n, t in self.tracks.items() if t.confirmed}

    def rate_ok(self, timestamps: list[float], min_hz: float = 2.0) -> bool:
        """Whether a stream of twin_state timestamps meets the live-rate target."""
        if len(timestamps) < 2:
            return False
        span = timestamps[-1] - timestamps[0]
        return span > 0 and (len(timestamps) - 1) / span >= min_hz
