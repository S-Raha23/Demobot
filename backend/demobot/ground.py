"""Stage 6: Ground. SAM pixels to table centimetres to motion segments and contact events
(docs/04 §6; the algorithm of the first repo's spec §7.5). The phone is handheld: every frame is
mapped through its own homography, with parallax corrected for that frame's camera pose."""

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from demobot import calibrate, goal_dsl
from demobot.camera import apply_h, parallax_correct
from demobot.schemas import (
    Calibration,
    CameraTrack,
    Contact,
    GoalClause,
    GroundedDemo,
    MotionSegment,
    SceneObject,
    StepMatch,
    TaskSpec,
    Track,
)  # fmt: skip

MOVE_CM, MOVE_FRAMES = 1.5, 3
SETTLE_CM, SETTLE_FRAMES = 0.4, 4
MEDIAN = 3
AREA_JUMP = 0.4
OCCL_IOU = 0.3
MATCH_WINDOW_S = 3.0
LATE_START_S = 0.5  # first seen later than this, already moving: start position unknown
MIN_SEGMENT_CM = 3.0
CONTACT_WINDOW_S = 1.0
ROUND_KINDS = {
    "mug",
    "cup",
    "glass",
    "bottle",
    "glue bottle",
    "can",
    "jar",
    "bowl",
    "tape",
    "roll",
    "candle",
}
BALL_KINDS = {"ball", "tennis ball", "orange", "apple", "lime", "egg"}


@dataclass
class Series:
    name: str
    t: np.ndarray
    xy: np.ndarray  # (n, 2) cm; NaN where dropped
    clean: np.ndarray  # bool
    quality: float
    flags: list[str] = field(default_factory=list)


def _iou(a: tuple[float, ...] | None, b: tuple[float, ...] | None) -> float:
    if a is None or b is None:
        return 0.0
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _overlap(a: tuple[float, ...] | None, b: tuple[float, ...] | None, pad: float = 10) -> bool:
    if a is None or b is None:
        return False
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def to_cm(px: tuple[float, float], k: int, track: CameraTrack, h_cm: float) -> np.ndarray:
    """A pixel in analysis frame k to table cm, for a point h_cm above the table."""
    f = track.frames[min(k, len(track.frames) - 1)]
    p = apply_h(np.array(f.H_img_to_table), np.array([px]))[0]
    return parallax_correct(p, f.nadir_cm, f.height_cm, h_cm)


def series(t: Track, hand: Track, cam: CameraTrack, h_cm: float) -> Series:
    """cm positions per frame with occlusion and area-jump cleaning, then a 3-frame median."""
    n = len(t.frames)
    xy = np.full((n, 2), np.nan)
    clean = np.zeros(n, bool)
    areas: list[float] = []
    for k, fr in enumerate(t.frames):
        if fr.centroid_px is None or fr.bbox_px is None:
            continue
        hb = hand.frames[k].bbox_px if k < len(hand.frames) else None
        jump = (
            bool(areas)
            and fr.area_px is not None
            and abs(fr.area_px - float(np.median(areas[-5:])))
            > AREA_JUMP * float(np.median(areas[-5:]))
        )
        occluded = _iou(fr.bbox_px, hb) > OCCL_IOU or (
            hb is not None and _overlap(fr.bbox_px, hb, 0) and _iou(fr.bbox_px, hb) > 0.1
        )
        if fr.area_px is not None and not occluded:
            areas.append(fr.area_px)
        if occluded or jump:
            continue
        xy[k] = to_cm(fr.centroid_px, k, cam, h_cm)
        clean[k] = True
    sm = xy.copy()
    idx = np.nonzero(clean)[0]
    for j, kk in enumerate(idx):
        k = int(kk)
        lo, hi = max(0, j - MEDIAN // 2), min(len(idx), j + MEDIAN // 2 + 1)
        sm[k] = np.median(xy[idx[lo:hi]], axis=0)
    return Series(t.name, np.array([f.t for f in t.frames]), sm, clean, t.quality, list(t.flags))


def segments(s: Series) -> list[tuple[int, int]]:
    """(start frame, end frame) of each motion: anchor/settle logic, plus carries hidden by the
    hand (a gap between two clean positions that differ by more than MOVE_CM)."""
    idx = [int(v) for v in np.nonzero(s.clean)[0]]
    if len(idx) < 2:
        return []
    out: list[tuple[int, int]] = []
    anchor = s.xy[idx[0]]
    j = 0
    while j < len(idx):
        k = idx[j]
        if (
            j > 0
            and idx[j] - idx[j - 1] > 1
            and np.linalg.norm(s.xy[k] - s.xy[idx[j - 1]]) > MOVE_CM
        ):
            # a carry hidden by the hand: from the last clean frame before to the first after,
            # extended until the object settles
            start = idx[j - 1]
            e = j
            while (
                e + SETTLE_FRAMES < len(idx)
                and max(
                    np.linalg.norm(s.xy[idx[e + q + 1]] - s.xy[idx[e + q]])
                    for q in range(SETTLE_FRAMES)
                )
                > SETTLE_CM
            ):
                e += 1
            out.append((start, idx[e]))
            anchor = s.xy[idx[e]]
            j = e + 1
            continue
        far = [
            np.linalg.norm(s.xy[idx[q]] - anchor) > MOVE_CM
            for q in range(j, min(j + MOVE_FRAMES, len(idx)))
        ]
        if len(far) == MOVE_FRAMES and all(far):
            e = j
            still = 0
            while e + 1 < len(idx) and still < SETTLE_FRAMES:
                still = (
                    still + 1 if np.linalg.norm(s.xy[idx[e + 1]] - s.xy[idx[e]]) < SETTLE_CM else 0
                )
                e += 1
            out.append((k, idx[e]))
            anchor = s.xy[idx[e]]
            j = e + 1
            continue
        j += 1
    good = []
    for a, b in out:
        before = _median_near(s, a, before=True)
        after = _median_near(s, b, before=False)
        if np.linalg.norm(after - before) >= MIN_SEGMENT_CM:
            good.append((a, b))
    return good


def _median_near(s: Series, k: int, before: bool, n: int = 5) -> np.ndarray:
    idx = np.nonzero(s.clean)[0]
    sel = idx[idx <= k][-n:] if before else idx[idx >= k][:n]
    if not len(sel):
        sel = idx[:n] if before else idx[-n:]
    return np.median(s.xy[sel], axis=0)


def contacts(t: Track, hand: Track, seg: tuple[int, int], fps: float) -> list[Contact]:
    w = round(CONTACT_WINDOW_S * fps)
    a, b = seg
    near = [k for k in range(max(0, a - w), min(len(t.frames), b + w + 1))
            if k < len(hand.frames) and _overlap(t.frames[k].bbox_px or _last_box(t, k), hand.frames[k].bbox_px)]  # fmt: skip
    if not near:
        return []
    return [Contact(t=round(near[0] / fps, 2), type="grasp", object=t.name),
            Contact(t=round(near[-1] / fps, 2), type="release", object=t.name)]  # fmt: skip


def _last_box(t: Track, k: int) -> tuple[float, float, float, float] | None:
    for j in range(k, -1, -1):
        if t.frames[j].bbox_px is not None:
            return t.frames[j].bbox_px
    return None


def footprint(
    t: Track, k: int, cam: CameraTrack, h_cm: float, final_poly: list[Any] | None = None
) -> tuple[float, float, float]:
    """(w, d, yaw°) from a mask outline mapped to cm at mid-height (min-area rectangle)."""
    poly = final_poly or (t.frames[k].poly_px if k < len(t.frames) else None)
    if not poly or len(poly) < 3:
        return 0.0, 0.0, 0.0
    pts = np.array([to_cm(tuple(p), k, cam, h_cm / 2) for p in poly], np.float32)
    (_, _), (w, d), ang = cv2.minAreaRect(pts)
    if w < d:
        w, d, ang = d, w, ang + 90
    return float(w), float(d), float(ang % 180)


def shape_of(kind: str, w: float, d: float, h: float) -> str:
    k = kind.lower()
    if any(b in k for b in BALL_KINDS):
        return "sphere"
    if any(r == k or k.endswith(" " + r) for r in ROUND_KINDS):
        return "cylinder"
    return "box"


def _hand_covered(t: Track, hand: Track, k: int, pad: float = 30.0) -> bool:
    """The hand's box (padded) overlapped where object `t` first appears, in a frame before `k`."""
    box = t.frames[k].bbox_px
    if box is None:
        return False
    for f in hand.frames[:k]:
        h = f.bbox_px
        if (
            h is not None
            and h[0] - pad < box[2]
            and box[0] < h[2] + pad
            and h[1] - pad < box[3]
            and box[1] < h[3] + pad
        ):
            return True
    return False


def fill_goal(
    goal: list[GoalClause], initial: list[SceneObject], final: list[SceneObject]
) -> list[GoalClause]:
    """Watch cannot know table centimetres: a `near` clause with neither target nor point gets the
    measured end position; a `turned` clause without yaw gets the measured end yaw (and its start
    point, so it means "turned in place")."""
    end = {o.name: o for o in final}
    start = {o.name: o for o in initial}
    out = []
    for c in goal:
        name = c.select.name
        if c.pred == "near" and c.target is None and c.point_cm is None and name in end:
            c = c.model_copy(update={"point_cm": (round(end[name].x, 1), round(end[name].y, 1))})
        elif c.pred == "turned" and c.yaw_deg is None and name in end:
            c = c.model_copy(update={"yaw_deg": round(end[name].yaw, 1),
                                     "point_cm": (round(start[name].x, 1), round(start[name].y, 1))})  # fmt: skip
        out.append(c)
    return out


def ground(spec: TaskSpec, tracks: list[Track], final_masks: dict[str, Any], cal: Calibration, cam: CameraTrack,
           fps: float, art: Path | None = None) -> GroundedDemo:  # fmt: skip
    by = {t.name: t for t in tracks}
    hand = by.get("hand") or Track(name="hand", phrase="hand", quality=0, frames=[])
    flags: list[str] = []
    init_objs, final_objs = [], []
    all_segments: list[MotionSegment] = []
    seg_obj: list[tuple[str, int, int]] = []
    contact_list: list[Contact] = []
    ref_k = round(cal.reference_t * fps)
    unseen_start: set[str] = set()
    from demobot import registry

    entries = registry.load()
    for o in spec.objects:
        t = by.get(o.name)
        ent = registry.entry_for(o.name, entries)
        h = float(ent.size_cm[2]) if ent else float(min(20.0, max(1.0, o.est_height_cm)))
        if t is None or "not_found" in t.flags:
            flags.append(f"{o.name}: not tracked")
            continue
        s = series(t, hand, cam, h / 2)
        if not s.clean.any():
            flags.append(f"{o.name}: never seen clearly")
            continue
        start = _median_near(s, int(np.nonzero(s.clean)[0][0]), before=False)
        end = _median_near(s, int(np.nonzero(s.clean)[0][-1]), before=True)
        fm = final_masks.get(o.name)
        if fm:  # the reference frame's segmentation is the most precise final position
            end = to_cm(tuple(fm["centroid"]), ref_k, cam, h / 2)
        first_clean = int(np.nonzero(s.clean)[0][0])
        w, d, yaw = footprint(t, first_clean, cam, h)
        if w < 2 or d < 2 or w > 3 * max(o.est_size_cm) + 5:
            w, d = max(2.0, o.est_size_cm[0]), max(2.0, o.est_size_cm[1])
        w, d = max(2.0, w), max(2.0, d)
        shape = shape_of(o.kind, w, d, h)
        if shape != "box":
            w = d = max(
                2.0, min(w, d) if o.role == "container" or shape == "sphere" else (w + d) / 2
            )
            yaw = 0.0
        if (
            ent is not None
        ):  # the registry knows this object: its true shape and size; position and yaw are measured
            shape, w, d = ent.shape, float(ent.size_cm[0]), float(ent.size_cm[1])
            if shape != "box":
                yaw = 0.0
        is_open = o.role == "container" or o.kind.lower() in {
            "box",
            "bowl",
            "mug",
            "cup",
            "tray",
            "basket",
            "tub",
            "container",
            "jar",
        }
        base = SceneObject(name=o.name, kind=o.kind, role=o.role, shape=shape, x=round(float(start[0]), 2),
                           y=round(float(start[1]), 2), yaw=round(yaw if shape == "box" else 0.0, 1),
                           w=round(w, 1), d=round(d, 1), h=round(h, 1), color=_color(o.color), hollow=is_open)  # fmt: skip
        init_objs.append(base)
        end_yaw = base.yaw
        if (
            fm and fm.get("poly") and shape == "box"
        ):  # the final mask's long axis: turns are measurable
            _, _, end_yaw = footprint(t, ref_k, cam, h, final_poly=fm["poly"])
        final_objs.append(
            base.model_copy(
                update={
                    "x": round(float(end[0]), 2),
                    "y": round(float(end[1]), 2),
                    "yaw": round(float(end_yaw), 1),
                }
            )
        )
        segs = segments(s)
        first_seen = next(
            (k for k, f in enumerate(t.frames) if f.centroid_px is not None), first_clean
        )
        if first_seen / fps > LATE_START_S and _hand_covered(t, hand, first_seen):
            # hidden under the hand until then: its start position was never seen
            unseen_start.add(o.name)
            flags.append(f"{o.name}: start not seen (hidden until {first_seen / fps:.1f} s)")
        for a, b in segs:
            fr, to = _median_near(s, a, True), _median_near(s, b, False)
            all_segments.append(MotionSegment(object=o.name, t0=round(a / fps, 2), t1=round(b / fps, 2),
                                              from_cm=(round(float(fr[0]), 2), round(float(fr[1]), 2)),
                                              to_cm=(round(float(to[0]), 2), round(float(to[1]), 2))))  # fmt: skip
            seg_obj.append((o.name, a, b))
            contact_list += contacts(t, hand, (a, b), fps)
        if s.quality < 0.5:
            flags.append(f"{o.name}: low tracking quality {s.quality:.2f}")
    matches: list[StepMatch] = []
    used: set[int] = set()
    q = {t.name: t.quality for t in tracks}
    for i, st in enumerate(spec.steps):
        lo, hi = st.t_start - MATCH_WINDOW_S, st.t_end + MATCH_WINDOW_S
        best, best_ov = None, 0.0
        for j, sg in enumerate(all_segments):
            if j in used or sg.object != st.object:
                continue
            ov = min(hi, sg.t1) - max(lo, sg.t0)
            if ov > best_ov:
                best, best_ov = j, ov
        if best is None:
            matches.append(StepMatch(step=i, segment=None, confidence=0.0))
            flags.append(f"step {i}: no motion found for {st.object}")
            continue
        used.add(best)
        sg = all_segments[best]
        inter = max(0.0, min(st.t_end, sg.t1) - max(st.t_start, sg.t0))
        union = max(st.t_end, sg.t1) - min(st.t_start, sg.t0)
        conf = round((inter / union if union > 0 else 0.0) * q.get(st.object, 0.0), 3)
        matches.append(StepMatch(step=i, segment=best, confidence=conf,
                                 timing_delta_s=round(max(abs(st.t_start - sg.t0), abs(st.t_end - sg.t1)), 2)))  # fmt: skip
    final_objs = _settle_into_containers(spec, final_objs)
    goal = fill_goal(spec.goal, init_objs, final_objs)
    real = goal_dsl.evaluate(goal, goal_dsl.to_state(final_objs), goal_dsl.to_state(init_objs))
    grounded = {o.name for o in init_objs}
    spec_state = {o.name: o for o in spec.objects}
    for r in real:  # an untracked object must not make a clause hold vacuously
        sel = r.clause.select
        wanted = [o for o in spec_state.values()
                  if (sel.name in (None, o.name)) and (sel.kind in (None, o.kind)) and (sel.role in (None, o.role))
                  and (not sel.names or o.name in sel.names)]  # fmt: skip
        missing = [o.name for o in wanted if o.name not in grounded]
        if missing:
            r.holds, r.code = False, "NOT_TRACKED"
            r.detail = f"cannot check: {', '.join(missing)} not tracked"
        elif not r.holds and r.clause.pred == "swapped" and unseen_start & set(r.objects):
            r.code = "START_UNSEEN"
            r.detail += f"; {', '.join(sorted(unseen_start & set(r.objects)))} was hidden at the start, so this is inconclusive"
    gd = GroundedDemo(initial=init_objs, final=final_objs, segments=all_segments,
                      contacts=sorted(contact_list, key=lambda c: c.t), matches=matches,
                      real_world=real, flags=flags, goal=goal)  # fmt: skip
    if art is not None:
        _crops(gd, art, cal, cam)
    return gd


def _settle_into_containers(spec: TaskSpec, final: list[SceneObject]) -> list[SceneObject]:
    """An object whose last step put it into a container ends inside that container. Things in
    a container often stand up (pens in a mug), so their mask centroid is far above the table
    and the flat-object parallax correction overshoots; clamp the measured end into the
    container's interior (shrunk by 1.5 cm): a point outside it goes to the container's centre."""
    last: dict[str, str] = {}
    for st in spec.steps:
        if st.action == "place_in" and st.target:
            last[st.object] = st.target
        else:
            last.pop(st.object, None)
    by = {o.name: o for o in final}
    out = []
    for o in final:
        c = by.get(last.get(o.name, ""))
        if c is None:
            out.append(o)
            continue
        ex, ey = c.extents()
        mx, my = max(0.0, ex - 1.5), max(0.0, ey - 1.5)
        inside = abs(o.x - c.x) <= mx and abs(o.y - c.y) <= my
        x, y = (o.x, o.y) if inside else (c.x, c.y)
        out.append(o.model_copy(update={"x": round(x, 2), "y": round(y, 2)}))
    return out


_COLORS = {"white": "#eeeeea", "black": "#2a2b2e", "teal": "#178f8f", "blue": "#3b6fd6", "red": "#cf2f2f",
           "green": "#2f9e48", "yellow": "#e3d43a", "orange": "#e8893a", "gray": "#9aa0a6", "grey": "#9aa0a6",
           "silver": "#b9bec4", "steel": "#b9bec4", "brown": "#8b5a2b", "pink": "#f19bb0", "purple": "#7a3db8"}  # fmt: skip


def _color(word: str) -> str:
    for k, v in _COLORS.items():
        if k in word.lower():
            return v
    return "#9aa3ad"


def _crops(gd: GroundedDemo, art: Path, cal: Calibration, cam: CameraTrack) -> None:
    """Top-down texture crops of each object from the first frame (rectified with its own H)."""
    cap = cv2.VideoCapture(str(art / "analysis.mp4"))
    ok, frame = cap.read()
    cap.release()
    if not ok:
        return
    rect = calibrate.rectify(frame, cal, np.array(cam.frames[0].H_img_to_table))
    s = cal.rectify_px_per_cm
    ox, oy = cal.rectify_origin_cm
    (art / "crops").mkdir(exist_ok=True)
    for o in gd.initial:
        ex, ey = o.extents()
        x0, x1 = round((o.x - ex - ox) * s), round((o.x + ex - ox) * s)
        y0, y1 = round((o.y - ey - oy) * s), round((o.y + ey - oy) * s)
        if (
            x1 - x0 < 4
            or y1 - y0 < 4
            or x0 < 0
            or y0 < 0
            or x1 > rect.shape[1]
            or y1 > rect.shape[0]
        ):
            continue
        crop = rect[y0:y1, x0:x1]
        name = o.name.replace(" ", "_") + ".png"
        cv2.imwrite(str(art / "crops" / name), crop)
        if o.is_open:  # a container's top-down crop is mostly its dark inside: keep a plain colour
            continue
        if min(o.w, o.d) < 3.0:  # a thin object's crop is mostly table: use its centre colour
            ch, cw = crop.shape[:2]
            centre = (
                crop[ch // 2 - 1 : ch // 2 + 2, cw // 2 - 1 : cw // 2 + 2]
                .reshape(-1, 3)
                .mean(axis=0)
            )
            o.color = f"#{int(centre[2]):02x}{int(centre[1]):02x}{int(centre[0]):02x}"
            continue
        mean = crop.reshape(-1, 3).mean(axis=0)
        o.texture = f"artifacts/crops/{name}"
        o.color = f"#{int(mean[2]):02x}{int(mean[1]):02x}{int(mean[0]):02x}"
    look = {o.name: o for o in gd.initial}
    for f in gd.final:
        f.texture, f.color = look[f.name].texture, look[f.name].color
    _ = math
