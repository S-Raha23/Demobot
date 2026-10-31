"""Stage 5: Perceive. SAM 3.1 tracks every TaskSpec object and the hand through the analysis clip
(one phrase per request, sequentially), and segments the reference frame for the real final state
(docs/04 §5)."""

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from demobot import gateway, providers
from demobot.config import sam_cost, settings
from demobot.errors import DemoBotError
from demobot.events import RunContext
from demobot.llm import output_text
from demobot.schemas import IngestInfo, TaskSpec, Track, TrackFrame

MIN_QUALITY = 0.5
ORDINALS = {"left", "right", "front", "back", "near", "far", "first", "second", "third", "middle",
            "top", "bottom", "leftmost", "rightmost", "other"}  # fmt: skip
HAND = "hand"


@dataclass
class Instance:
    """One SAM instance in one frame (analysis pixels)."""

    object_id: str
    box: tuple[float, float, float, float]
    area: float
    centroid: tuple[float, float]
    poly: list[tuple[float, float]]


def parse_sam(text: str, media: str) -> dict[int, list[Instance]]:
    """frame index (0 for an image) -> instances, via Meta's meta_sam_parser."""
    from meta_sam_parser import (
        CompletedOutcome,
        decode_mask_to_raster,
        image_segmentation_format,
        video_segmentation_format,
    )

    fmt = image_segmentation_format() if media == "image" else video_segmentation_format()
    parser = fmt.create_parser()
    parser.push(text, emit=False)
    res = parser.finish(CompletedOutcome()).result
    boxes: dict[tuple[int, str], tuple[float, float, float, float]] = {}
    masks: dict[tuple[int, str], Any] = {}
    for r in res.records:
        frame = getattr(getattr(r, "frame", None), "frame_index", None) or 0
        key = (int(frame), str(getattr(r, "object_id", "")))
        if r.kind == "box":
            boxes[key] = (float(r.left), float(r.top), float(r.right), float(r.bottom))
        elif r.kind == "mask":
            masks[key] = r
    out: dict[int, list[Instance]] = {}
    for key, box in boxes.items():
        m = masks.get(key)
        area, cen, poly = (
            (box[2] - box[0]) * (box[3] - box[1]),
            ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
            [],
        )
        if m is not None:
            try:
                raster = np.frombuffer(decode_mask_to_raster(m.mask), np.uint8).reshape(
                    m.mask.height, m.mask.width
                )
            except Exception:  # an undecodable mask: keep the box
                raster = None
            if raster is not None and raster.any():
                ys, xs = np.nonzero(raster)
                ox, oy = float(m.bounds.left), float(m.bounds.top)
                area = float(len(xs))
                cen = (ox + float(xs.mean()), oy + float(ys.mean()))
                cs, _ = cv2.findContours(
                    raster.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                )
                if cs:
                    big = cv2.approxPolyDP(max(cs, key=cv2.contourArea), 1.5, True).reshape(-1, 2)
                    poly = [(ox + float(x), oy + float(y)) for x, y in big]
        out.setdefault(key[0], []).append(Instance(key[1], box, area, cen, poly))
    return out


def base_phrase(name: str) -> str:
    """'left teal pen' and 'teal pen 2' share the SAM phrase 'teal pen'."""
    words = [
        w for w in re.split(r"\s+", name.lower().strip()) if w not in ORDINALS and not w.isdigit()
    ]
    return " ".join(words) or name.lower()


async def sam_video(
    ctx: RunContext, clip: Path, clip_sha: str, phrase: str
) -> dict[int, list[Instance]]:
    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        fid = await providers.upload_file(clip, clip_sha)
        inp: Any = [{"role": "user", "content": [{"type": "input_text", "text": phrase},
                                                 {"type": "input_video", "file_id": fid}]}]  # fmt: skip
        resp = (
            await providers.client("meta")
            .with_options(timeout=timeout)
            .responses.create(model=settings.model_sam, input=inp)
        )
        d = providers.dump(resp)
        frames = int((d.get("usage") or {}).get("video_frames_processed") or 0)
        return (
            {"text": output_text(d), "frames": frames},
            sam_cost(frames=frames),
            {"frames": frames},
        )

    raw = await gateway.cached_call(
        ctx=ctx, purpose=f"track:{phrase}", provider="meta", model=settings.model_sam,
        request={"stage": "track", "clip": clip_sha, "phrase": phrase},
        estimate_usd=0.1, call=call, validate=gateway.passthrough,
    )  # fmt: skip
    return parse_sam(raw["text"], "video")


async def sam_image(ctx: RunContext, image: Path, phrase: str) -> list[Instance]:
    img = cv2.imread(str(image))
    if img is None:
        raise DemoBotError("MEDIA_ERROR", f"cannot read {image.name}", stage="perceive")
    _, buf = cv2.imencode(
        ".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 92]
    )  # full size: pixel coords stay
    url = "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode()

    async def call(timeout: float) -> tuple[Any, float, dict[str, Any]]:
        inp: Any = [{"role": "user", "content": [{"type": "input_text", "text": phrase},
                                                 {"type": "input_image", "image_url": url}]}]  # fmt: skip
        resp = (
            await providers.client("meta")
            .with_options(timeout=timeout)
            .responses.create(model=settings.model_sam, input=inp)
        )
        return {"text": output_text(providers.dump(resp))}, sam_cost(images=1), {"images": 1}

    raw = await gateway.cached_call(
        ctx=ctx, purpose=f"segment_image:{phrase}", provider="meta", model=settings.model_sam,
        request={"stage": "segment_image", "image": gateway.sha256_file(image), "phrase": phrase, "enc": "jpeg92"},
        estimate_usd=0.01, call=call, validate=gateway.passthrough,
    )  # fmt: skip
    return parse_sam(raw["text"], "image").get(0, [])


def split_tracks(
    frames: dict[int, list[Instance]], n_frames: int
) -> dict[str, dict[int, Instance]]:
    """object_id -> frame -> instance."""
    out: dict[str, dict[int, Instance]] = {}
    for k, insts in frames.items():
        if 0 <= k < n_frames:
            for inst in insts:
                out.setdefault(inst.object_id, {})[k] = inst
    return out


def quality(track: dict[int, Instance], n_frames: int) -> float:
    return round(len(track) / max(1, n_frames), 3)


def _stabilise(
    poly: list[tuple[float, float]], M: list[list[float]] | None
) -> list[tuple[float, float]]:
    if not poly or M is None:
        return [(round(x, 1), round(y, 1)) for x, y in poly]
    pts = cv2.perspectiveTransform(np.array([poly], float), np.array(M))[0]
    return [(round(float(x), 1), round(float(y), 1)) for x, y in pts]


def to_track(name: str, phrase: str, oid: str, inst: dict[int, Instance], n_frames: int,
             fps: float, stab: list[list[list[float]]] | None, flags: list[str]) -> Track:  # fmt: skip
    frames = []
    for k in range(n_frames):
        i = inst.get(k)
        M = stab[min(len(stab) - 1, round(k / fps * 30))] if stab else None
        if i is None:
            frames.append(TrackFrame(t=round(k / fps, 2), bbox_px=None))
            continue
        frames.append(TrackFrame(t=round(k / fps, 2), bbox_px=tuple(round(v, 1) for v in i.box),
                                 centroid_px=(round(i.centroid[0], 1), round(i.centroid[1], 1)),
                                 poly_px=_stabilise(i.poly, M), score=1.0, area_px=round(i.area)))  # fmt: skip
    return Track(
        name=name,
        phrase=phrase,
        track_id=oid,
        quality=quality(inst, n_frames),
        frames=frames,
        flags=flags,
    )


def _first_x(track: dict[int, Instance]) -> float:
    k = min(track)
    return track[k].centroid[0]


async def perceive(
    ctx: RunContext, art: Path, info: IngestInfo, spec: TaskSpec
) -> tuple[list[Track], dict[str, Any]]:
    """Tracks for every TaskSpec object plus the hand, and the reference-frame segmentation."""
    ctx = ctx.at("perceive")
    clip = art / "analysis.mp4"
    clip_sha = gateway.sha256_file(clip)
    n = info.analysis_frames
    fps = info.analysis_fps
    stab_path = art / "stabilise.json"
    stab = json.loads(stab_path.read_text())["M"] if stab_path.exists() else None
    groups: dict[str, list[str]] = {}
    for o in spec.objects:
        groups.setdefault(base_phrase(o.name), []).append(o.name)
    alts = {o.name: o.alt_names for o in spec.objects}
    specs = {o.name: o for o in spec.objects}
    tracks: list[Track] = []
    for phrase, names in groups.items():
        tried = [phrase]
        per = split_tracks(await sam_video(ctx, clip, clip_sha, phrase), n)

        def good(
            tracks_: dict[str, dict[int, Instance]], k: int = len(names)
        ) -> list[tuple[str, dict[int, Instance]]]:
            ranked = sorted(tracks_.items(), key=lambda kv: -quality(kv[1], n))[:k]
            return [kv for kv in ranked if quality(kv[1], n) >= MIN_QUALITY]

        best = good(per)
        if len(best) < len(names):  # retry with the members' alternative names
            alt_phrases: list[str] = []
            for nm in names:
                for alt in alts.get(nm, [])[:2]:
                    bp = base_phrase(alt)
                    if bp not in tried and bp not in alt_phrases:
                        alt_phrases.append(bp)
            # last resorts: the bare kind, then "<colour> object"
            for nm in names:
                so = specs[nm]
                for bp in (so.kind.lower(), f"{so.color.lower()} object" if so.color else ""):
                    if bp and bp not in tried and bp not in alt_phrases:
                        alt_phrases.append(bp)
            for alt in alt_phrases[:5]:
                tried.append(alt)
                ctx.emit(
                    "log",
                    payload={
                        "message": f"SAM found {len(best)}/{len(names)} for '{phrase}'; retrying as '{alt}'"
                    },
                )
                cand = good(split_tracks(await sam_video(ctx, clip, clip_sha, alt), n))
                if len(cand) > len(best):
                    best, phrase = cand, alt
                if len(best) >= len(names):
                    break
        if not best:  # keep the weak tracks rather than nothing, flagged
            best = sorted(per.items(), key=lambda kv: -quality(kv[1], n))[: len(names)]
        flags = [] if len(names) == 1 else ["ambiguous_ordinal"]
        best = sorted(best, key=lambda kv: _first_x(kv[1]))  # left to right
        ordered = sorted(names, key=_ordinal_key)
        for name, (oid, inst) in zip(ordered, best, strict=False):
            f = list(flags) + (["low_quality"] if quality(inst, n) < MIN_QUALITY else [])
            tracks.append(to_track(name, phrase, oid, inst, n, fps, stab, f))
        for name in ordered[len(best) :]:
            tracks.append(Track(name=name, phrase=phrase, quality=0.0, flags=["not_found", *flags],
                                frames=[TrackFrame(t=round(k / fps, 2), bbox_px=None) for k in range(n)]))  # fmt: skip
            ctx.emit(
                "log", payload={"message": f"SAM did not find {name} (tried {', '.join(tried)})"}
            )
    _dedupe(ctx, tracks)
    # the hand: every instance per frame, merged into one box
    hand = split_tracks(await sam_video(ctx, clip, clip_sha, HAND), n)
    merged: dict[int, Instance] = {}
    for inst in hand.values():
        for k, i in inst.items():
            if k in merged:
                a, b = merged[k].box, i.box
                box = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                merged[k] = Instance(
                    "hand",
                    box,
                    merged[k].area + i.area,
                    merged[k].centroid,
                    merged[k].poly + i.poly,
                )
            else:
                merged[k] = Instance("hand", i.box, i.area, i.centroid, i.poly)
    tracks.append(to_track(HAND, HAND, "hand", merged, n, fps, stab, []))
    # the real final state: image mode on the reference (last clean) frame
    final: dict[str, Any] = {}
    ref = art / "reference_frame.jpg"
    if ref.exists():
        last_c = {
            t.name: next((f.centroid_px for f in reversed(t.frames) if f.centroid_px), None)
            for t in tracks
        }
        for phrase, names in groups.items():
            used_phrase = next((t.phrase for t in tracks if t.name == names[0]), phrase)
            insts = await sam_image(ctx, ref, used_phrase)
            for name in names:
                c = last_c.get(name)
                if c is None or not insts:
                    continue
                best_i = min(
                    insts, key=lambda i: (i.centroid[0] - c[0]) ** 2 + (i.centroid[1] - c[1]) ** 2
                )
                if np.hypot(best_i.centroid[0] - c[0], best_i.centroid[1] - c[1]) < 80:
                    final[name] = {
                        "box": best_i.box,
                        "centroid": best_i.centroid,
                        "area": best_i.area,
                        "poly": best_i.poly,
                    }
                    insts.remove(best_i)
    missing = [t.name for t in tracks if "not_found" in t.flags]
    if len(missing) == len(spec.objects):
        raise DemoBotError("TRACKING_FAILED", "SAM found none of the objects", stage="perceive")
    return tracks, final


def _ordinal_key(name: str) -> tuple[int, str]:
    w = name.lower()
    for i, word in enumerate(
        ("leftmost", "left", "first", "middle", "second", "right", "rightmost", "third")
    ):
        if re.search(rf"\b{word}\b", w):
            return (i, name)
    digits = re.findall(r"\d+", w)
    return (int(digits[0]) if digits else 0, name)


def _box_iou(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _dedupe(ctx: RunContext, tracks: list[Track]) -> None:
    """Two objects must not share one SAM instance: when two tracks overlap heavily in most
    shared frames, keep the better one and mark the other not found (visible in the log)."""
    for i, a in enumerate(tracks):
        for b in tracks[i + 1 :]:
            if "not_found" in a.flags or "not_found" in b.flags:
                continue
            ious = [_box_iou(fa.bbox_px, fb.bbox_px) for fa, fb in zip(a.frames, b.frames, strict=False)
                    if fa.bbox_px is not None and fb.bbox_px is not None]  # fmt: skip
            if len(ious) >= 5 and float(np.median(ious)) > 0.6:
                loser = b if a.quality >= b.quality else a
                winner = a if loser is b else b
                loser.flags.append("not_found")
                loser.flags.append(f"duplicate_of:{winner.name}")
                loser.quality = 0.0
                for f in loser.frames:
                    f.bbox_px = f.centroid_px = f.area_px = None
                    f.poly_px = None
                ctx.emit("log", payload={"message": f"SAM's '{loser.phrase}' found the same thing as "
                                                    f"'{winner.phrase}'; {loser.name} is left out"})  # fmt: skip
