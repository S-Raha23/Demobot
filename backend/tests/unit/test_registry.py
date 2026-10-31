"""The table registry renames Watch's objects; a cutter called a pen stops being one (Fix 0, 1 and 4)."""

from demobot import registry
from demobot.schemas import GoalClause, Selector, SpecObject, Step, TaskSpec, Track, TrackFrame


def _track(name: str, x: float) -> Track:
    return Track(
        name=name,
        phrase=name,
        quality=1.0,
        frames=[TrackFrame(t=0, bbox_px=(x, 0, x + 10, 10), centroid_px=(x + 5, 5))],
    )


def test_cutter_called_a_pen_is_renamed_and_leaves_the_pen_goal() -> None:
    entries = registry.load(registry.DEFAULT)
    spec = TaskSpec(
        summary="The person put the left light blue pen and the right light blue pen in the white plastic tub.",
        objects=[SpecObject(name=n, kind="pen", role="moved") for n in ("left light blue pen", "middle light blue pen", "right light blue pen")]
        + [SpecObject(name="white plastic tub", kind="tub", role="container")],
        steps=[Step(action="place_in", object="left light blue pen", target="white plastic tub", t_start=1, t_end=2)],
        goal=[GoalClause(quant="all", select=Selector(kind="pen"), pred="inside", target=Selector(name="white plastic tub"))],
        generalization="",
    )  # fmt: skip
    tracks = [
        _track("left light blue pen", 10),
        _track("middle light blue pen", 50),
        _track("right light blue pen", 90),
        _track("white plastic tub", 200),
    ]
    labels = {"left light blue pen": ("teal box cutter", 0.9), "middle light blue pen": ("teal pen", 0.9),
              "right light blue pen": ("teal pen", 0.95), "white plastic tub": ("white tub", 0.99)}  # fmt: skip
    plan = registry.plan_renames(spec, tracks, labels, entries)
    names = registry.new_names(spec, tracks, plan)
    out = registry.apply(spec, plan, names)
    assert [(o.name, o.kind) for o in out.objects] == [
        ("teal box cutter", "box cutter"),
        ("left teal pen", "pen"),
        ("right teal pen", "pen"),
        ("white tub", "tub"),
    ]
    assert out.goal[0].select.kind == "pen" and out.goal[0].target.name == "white tub"
    assert out.steps[0].object == "teal box cutter" and "white tub" in out.summary
    assert sum(o.kind == "pen" for o in out.objects) == 2


def test_an_object_seen_more_often_than_it_exists_keeps_the_most_confident_match() -> None:
    entries = registry.load(registry.DEFAULT)
    spec = TaskSpec(summary="", generalization="", steps=[], goal=[],
                    objects=[SpecObject(name="a", kind="pen", role="moved"), SpecObject(name="b", kind="spoon", role="distractor")])  # fmt: skip
    plan = registry.plan_renames(spec, [_track("a", 0), _track("b", 50)],
                                 {"a": ("teal box cutter", 0.85), "b": ("teal box cutter", 0.96)}, entries)  # fmt: skip
    assert plan["a"] is None and plan["b"] is not None and plan["b"].name == "teal box cutter"
