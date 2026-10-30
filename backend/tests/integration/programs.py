"""Hand-written robot programs for the M2 acceptance test: 4 per task family, 5 families.

Each family has a base layout (sizes of real desk items), a goal, and programs written in
different styles. They must pass on seeded random rearrangements of the layout.
"""

from demobot.schemas import GoalClause, Layout, SceneObject, Selector
from demobot.sim.layouts import default_frame

WORK, BASE = default_frame()


def obj(name: str, kind: str, w: float, d: float, h: float, role: str = "moved",
        shape: str = "box", color: str = "#888888") -> SceneObject:  # fmt: skip
    return SceneObject(name=name, kind=kind, role=role, shape=shape, x=0, y=0, w=w, d=d, h=h,
                       color=color)  # type: ignore[arg-type]  # fmt: skip


MUG = obj("white mug", "mug", 9, 9, 10, "container", "cylinder", "#e8e6e1")
BOWL = obj("blue bowl", "bowl", 15, 15, 6, "container", "cylinder", "#3a6fd8")
PEN_B = obj("blue pen", "pen", 14, 1.2, 1.2, color="#2050d0")
PEN_R = obj("red pen", "pen", 14, 1.2, 1.2, color="#d02020")
ERASER = obj("eraser", "eraser", 5, 2.5, 1.5, color="#f2f2f2")
MATCHBOX = obj("matchbox", "matchbox", 5, 3.5, 1.6, color="#c8a040")
PAD = obj("sticky notes", "sticky notes", 7.6, 7.6, 1.5, color="#f5e050")
GLUE = obj("glue stick", "glue stick", 3, 3, 9, shape="cylinder", color="#7030a0")


def layout(*objs: SceneObject) -> Layout:
    placed = [o.model_copy(update={"x": 8.0 + 10 * i, "y": 20.0}) for i, o in enumerate(objs)]
    return Layout(objects=placed, work_area=WORK, robot_base_cm=BASE)


def ref(o: SceneObject) -> SceneObject:
    return o.model_copy(update={"role": "reference"})


def dis(o: SceneObject) -> SceneObject:
    return o.model_copy(update={"role": "distractor"})


C = GoalClause
S = Selector

FAMILIES: dict[str, tuple[Layout, list[GoalClause], list[str]]] = {}

# ---------- 1. put into a container ----------
FAMILIES["place_in"] = (
    layout(MUG, PEN_B, PEN_R, dis(ERASER)),
    [C(quant="all", select=S(kind="pen"), pred="inside", target=S(kind="mug"))],
    [
        """
def run(scene, robot):
    mug = scene.containers()[0]
    for pen in scene.of_kind("pen"):
        robot.pick(pen)
        robot.place_in(mug)
""",
        """
def run(scene, robot):
    mug = scene.of_kind("mug")[0]
    pens = [o for o in scene.with_role("moved") if o.kind == "pen"]
    for pen in pens:
        robot.pick(scene.get(pen.name))
        robot.place_in(scene.get(mug.name))
    robot.home()
""",
        """
def run(scene, robot):
    mug = scene.of_kind("mug")[0]
    # nearest pen first, so the arm travels less
    pens = sorted(scene.of_kind("pen"), key=lambda p: scene.distance(p, mug))
    for pen in pens:
        if scene.is_inside(pen, mug):
            continue
        robot.pick(pen)
        robot.place_in(mug)
        log(f"{pen.name} is in the {mug.name}")
""",
        """
import math

def put_away(scene, robot, item, box):
    if not robot.can_reach(item.x, item.y):
        log(f"cannot reach {item.name}")
        return False
    robot.pick(item)
    robot.place_in(box)
    return True

def run(scene, robot):
    box = scene.containers()[0]
    done = 0
    for item in scene.of_kind("pen"):
        if put_away(scene, robot, item, box):
            done += 1
    log(f"put away {done} pens")
""",
    ],
)

# ---------- 2. place next to ----------
_CLEAR_AND_PLACE = """
def blockers(scene, x, y, w, d, skip):
    out = []
    for o in scene.objects():
        if o.name in skip:
            continue
        if abs(o.x - x) < (o.w + w) / 2 + 1.5 and abs(o.y - y) < (o.d + d) / 2 + 1.5:
            out.append(o)
    return out
"""
FAMILIES["next_to"] = (
    layout(ref(MUG), ERASER, dis(PEN_B), dis(PAD)),
    [C(quant="the", select=S(name="eraser"), pred="right_of", target=S(name="white mug"))],
    [
        _CLEAR_AND_PLACE
        + """
def run(scene, robot):
    mug = scene.get("white mug")
    eraser = scene.get("eraser")
    x = mug.x + mug.w / 2 + 2 + eraser.w / 2
    for b in blockers(scene, x, mug.y, eraser.w, eraser.d, [mug.name, eraser.name]):
        sx, sy = scene.free_spot(size=(b.w, b.d), clearance=3, avoid=[(x, mug.y, eraser.w + 4, eraser.d + 4)])
        robot.move(b, sx, sy)
    robot.pick(scene.get("eraser"))
    robot.place_next_to(scene.get("white mug"), "right_of", gap=2)
""",
        _CLEAR_AND_PLACE
        + """
def run(scene, robot):
    mug = scene.get("white mug")
    item = scene.get("eraser")
    tx = mug.x + mug.w / 2 + 3 + item.w / 2
    for b in blockers(scene, tx, mug.y, item.w, item.d, [mug.name, item.name]):
        log(f"moving {b.name} out of the way")
        robot.pick(b)
        robot.place_at(*scene.free_spot(size=(b.w, b.d), clearance=3, avoid=[(tx, mug.y, 9, 7)]))
    robot.move(scene.get(item.name), tx, mug.y)
""",
        _CLEAR_AND_PLACE
        + """
def run(scene, robot):
    target = scene.get("white mug")
    me = scene.get("eraser")
    gap = 2.5
    x = target.x + target.w / 2 + gap + me.w / 2
    y = target.y
    moved = 0
    while moved < 3:
        bs = blockers(scene, x, y, me.w, me.d, [target.name, me.name])
        if not bs:
            break
        robot.move(bs[0], *scene.free_spot(size=(bs[0].w, bs[0].d), clearance=3, avoid=[(x, y, 9, 7)]))
        moved += 1
    robot.pick(scene.get("eraser"))
    robot.place_at(x, y)
""",
        _CLEAR_AND_PLACE
        + """
def run(scene, robot):
    mug = scene.get("white mug")
    e = scene.get("eraser")
    if e.x - e.w / 2 > mug.x + mug.w / 2 and abs(e.y - mug.y) < 3 and e.x - mug.x < 12:
        log("already to the right of the mug")
        return
    tx = mug.x + mug.w / 2 + 2 + e.w / 2
    for b in blockers(scene, tx, mug.y, e.w, e.d, [mug.name, e.name]):
        robot.move(b, *scene.free_spot(size=(b.w, b.d), clearance=3, avoid=[(tx, mug.y, 9, 7)]))
    robot.pick(e)
    robot.place_next_to(mug, "right_of")
""",
    ],
)

# ---------- 3. line up ----------
_ROW = """
def slot_blockers(scene, x, y, w, d, skip):
    return [o for o in scene.objects() if o.name not in skip
            and abs(o.x - x) < (o.w + w) / 2 + 4 and abs(o.y - y) < (o.d + d) / 2 + 4]

def clear(scene, robot, x, y, w, d, skip):
    x0, y0, x1, y1 = scene.bounds()
    row = (x, y, 2 * (x1 - x0), d + 2)  # keep the whole row clear, not just this slot
    for b in slot_blockers(scene, x, y, w, d, skip):
        robot.move(b, *scene.free_spot(size=(b.w, b.d), clearance=3, avoid=[row]))
"""
FAMILIES["line_up"] = (
    layout(ERASER, MATCHBOX, PAD, dis(GLUE)),
    [C(quant="all", select=S(role="moved"), pred="collinear", order_by="x")],
    [
        _ROW
        + """
def run(scene, robot):
    items = scene.with_role("moved")
    prev = items[0]
    placed = [prev.name]
    for item in items[1:]:
        x = prev.x + prev.w / 2 + 3 + item.w / 2
        clear(scene, robot, x, prev.y, item.w, item.d, [item.name, *placed])
        placed.append(item.name)
        robot.pick(scene.get(item.name))
        robot.place_next_to(scene.get(prev.name), "right_of", gap=3)
        prev = scene.get(item.name)
""",
        _ROW
        + """
def run(scene, robot):
    items = scene.with_role("moved")
    x0, y0, x1, y1 = scene.bounds()
    y = (y0 + y1) / 2
    total = sum(o.w for o in items) + 4 * (len(items) - 1)
    x = (x0 + x1) / 2 - total / 2
    placed = []
    for item in items:
        cx = x + item.w / 2
        clear(scene, robot, cx, y, item.w, item.d, [item.name, *placed])
        robot.move(scene.get(item.name), cx, y)
        placed.append(item.name)
        x += item.w + 4
""",
        _ROW
        + """
def run(scene, robot):
    items = sorted(scene.with_role("moved"), key=lambda o: o.x)
    anchor = items[0]
    y = anchor.y
    x = anchor.x + anchor.w / 2
    placed = [anchor.name]
    for item in items[1:]:
        cx = x + 3.5 + item.w / 2
        clear(scene, robot, cx, y, item.w, item.d, [item.name, *placed])
        placed.append(item.name)
        robot.move(scene.get(item.name), cx, y)
        x = cx + item.w / 2
    log(f"lined up {len(items)} items at y = {y:.1f}")
""",
        _ROW
        + """
def run(scene, robot):
    items = scene.with_role("moved")
    x0, y0, x1, y1 = scene.bounds()
    # a row near the front of the table, left to right
    y = y1 - max(o.d for o in items) / 2 - 2
    x = x0 + 6
    placed = []
    for item in items:
        cx = x + item.w / 2
        clear(scene, robot, cx, y, item.w, item.d, [item.name, *placed])
        robot.move(scene.get(item.name), cx, y)
        placed.append(item.name)
        x = cx + item.w / 2 + 3
""",
    ],
)

# ---------- 4. sort by kind into containers ----------
FAMILIES["sort"] = (
    layout(MUG, BOWL, PEN_B, PEN_R, ERASER, MATCHBOX),
    [
        C(quant="all", select=S(kind="pen"), pred="inside", target=S(kind="mug")),
        C(quant="all", select=S(kind="eraser"), pred="inside", target=S(kind="bowl")),
        C(quant="all", select=S(kind="matchbox"), pred="inside", target=S(kind="bowl")),
    ],
    [
        """
def run(scene, robot):
    mug = scene.of_kind("mug")[0]
    bowl = scene.of_kind("bowl")[0]
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(mug if item.kind == "pen" else bowl)
""",
        """
RULES = {"pen": "mug", "eraser": "bowl", "matchbox": "bowl"}

def run(scene, robot):
    for kind, box_kind in RULES.items():
        for item in scene.of_kind(kind):
            robot.pick(item)
            robot.place_in(scene.of_kind(box_kind)[0])
""",
        """
def run(scene, robot):
    boxes = {c.kind: c for c in scene.containers()}
    todo = [o for o in scene.objects() if o.role == "moved"]
    todo.sort(key=lambda o: (o.kind != "pen", o.x))
    for item in todo:
        box = boxes["mug"] if item.kind == "pen" else boxes["bowl"]
        if scene.is_inside(item, box):
            continue
        robot.pick(item)
        robot.place_in(box)
    log("sorted")
""",
        """
def destination(scene, item):
    if item.kind == "pen":
        return scene.of_kind("mug")[0]
    return scene.of_kind("bowl")[0]

def run(scene, robot):
    n = 0
    for item in scene.with_role("moved"):
        robot.pick(item)
        robot.place_in(destination(scene, item))
        n += 1
    log(f"{n} items sorted")
""",
    ],
)

# ---------- 5. swap ----------
FAMILIES["swap"] = (
    layout(ERASER, MATCHBOX, dis(PEN_B)),
    [C(quant="pair", select=S(names=["eraser", "matchbox"]), pred="swapped")],
    [
        """
def run(scene, robot):
    a, b = scene.get("eraser"), scene.get("matchbox")
    ax, ay, bx, by = a.x, a.y, b.x, b.y
    side = max(a.w, a.d, b.w, b.d) + 1
    robot.move(a, *scene.free_spot(size=(side, side), clearance=3))
    robot.move(scene.get("matchbox"), ax, ay)
    robot.move(scene.get("eraser"), bx, by)
""",
        """
def run(scene, robot):
    first, second = scene.get("eraser"), scene.get("matchbox")
    spot = scene.free_spot(size=(8, 8), clearance=3)
    start_first = (first.x, first.y)
    start_second = (second.x, second.y)
    robot.pick(first)
    robot.place_at(spot[0], spot[1])
    robot.pick(scene.get(second.name))
    robot.place_at(start_first[0], start_first[1])
    robot.pick(scene.get(first.name))
    robot.place_at(start_second[0], start_second[1])
""",
        """
def swap(scene, robot, n1, n2):
    p1, p2 = scene.get(n1), scene.get(n2)
    a = (p1.x, p1.y)
    b = (p2.x, p2.y)
    buf = scene.free_spot(near=p1, size=(8, 8), clearance=3)
    log(f"buffer at {buf}")
    robot.move(p1, buf[0], buf[1])
    robot.move(scene.get(n2), a[0], a[1])
    robot.move(scene.get(n1), b[0], b[1])

def run(scene, robot):
    swap(scene, robot, "matchbox", "eraser")
""",
        """
def run(scene, robot):
    pair = [scene.get(n) for n in ("eraser", "matchbox")]
    starts = {o.name: (o.x, o.y) for o in pair}
    big = max(max(o.w, o.d) for o in pair) + 2
    tmp = scene.free_spot(size=(big, big), clearance=3)
    robot.move(pair[1], tmp[0], tmp[1])
    robot.move(scene.get("eraser"), starts["matchbox"][0], starts["matchbox"][1])
    robot.move(scene.get("matchbox"), starts["eraser"][0], starts["eraser"][1])
""",
    ],
)

PROGRAMS = [(fam, i) for fam, (_, _, progs) in FAMILIES.items() for i in range(len(progs))]
