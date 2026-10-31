"""Live Twin tracker (F2 core): confirmation, smoothing, gating, rate check."""

from demobot.live import Detection, LiveTracker, Track


def _tracker() -> LiveTracker:
    t = LiveTracker(confirm_frames=3, alpha=0.5)
    t.seed([("pen", "pen", 10.0, 10.0), ("box", "box", 30.0, 20.0)])
    return t


def test_seeded_objects_are_confirmed_and_hold_on_miss() -> None:
    t = _tracker()
    assert t.update([]) == {"pen": (10.0, 10.0), "box": (30.0, 20.0)}


def test_update_smooths_toward_detection() -> None:
    t = _tracker()
    out = t.update([Detection("pen", 14.0, 10.0)])
    assert out["pen"] == (12.0, 10.0)  # halfway with alpha 0.5
    assert out["box"] == (30.0, 20.0)


def test_wrong_label_and_far_detections_are_ignored() -> None:
    t = _tracker()
    out = t.update([Detection("mug", 11.0, 10.0), Detection("pen", 50.0, 35.0)])
    assert out["pen"] == (10.0, 10.0)  # mug is another label; pen at 50,35 is outside the gate


def test_unseeded_detection_needs_confirmation() -> None:
    t = LiveTracker(confirm_frames=3)
    t.seed([])
    t.tracks["pen"] = Track("pen", "pen", 10.0, 10.0, seen=0, confirmed=False)
    assert t.update([Detection("pen", 10.0, 10.0)]) == {}
    t.update([Detection("pen", 10.0, 10.0)])
    assert t.update([Detection("pen", 12.0, 10.0)])["pen"] == (11.0, 10.0)


def test_unseeded_detection_creates_track_after_confirm_frames() -> None:
    t = LiveTracker(confirm_frames=3, alpha=0.5)
    t.seed([("pen", "pen", 10.0, 10.0)])
    det = [Detection("pen", 10.0, 10.0), Detection("mug", 40.0, 30.0)]
    assert "mug" not in t.update(det)
    assert "mug" not in t.update(det)
    out = t.update([Detection("pen", 10.0, 10.0), Detection("mug", 42.0, 30.0)])
    assert out["mug"] == (41.0, 30.0)  # smoothed halfway on the confirming frame
    assert out["pen"] == (10.0, 10.0)


def test_unseeded_detection_miss_resets_confirmation() -> None:
    t = LiveTracker(confirm_frames=3)
    t.seed([])
    t.update([Detection("mug", 40.0, 30.0)])
    t.update([Detection("mug", 40.0, 30.0)])
    t.update([])  # a miss before confirmation restarts the count
    assert t.update([Detection("mug", 40.0, 30.0)]) == {}
    assert t.update([Detection("mug", 40.0, 30.0)]) == {}
    assert t.update([Detection("mug", 40.0, 30.0)])["mug"] == (40.0, 30.0)


def test_second_unseeded_same_label_gets_its_own_track() -> None:
    t = LiveTracker(confirm_frames=2)
    t.seed([("pen", "pen", 10.0, 10.0)])
    frame = [Detection("pen", 10.0, 10.0), Detection("pen", 40.0, 10.0)]
    t.update(frame)
    out = t.update(frame)
    assert out["pen"] == (10.0, 10.0) and out["pen 2"] == (40.0, 10.0)


def test_rate_ok() -> None:
    t = _tracker()
    assert t.rate_ok([0.0, 0.4, 0.8, 1.2])  # 2.5 Hz
    assert not t.rate_ok([0.0, 1.0, 2.0])  # 1 Hz
    assert not t.rate_ok([1.0])
