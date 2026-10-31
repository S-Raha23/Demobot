# DemoBot skill API

A DemoBot program is plain Python defining `run(scene, robot)`. To run it on any robot, implement
the objects below on top of your perception and motion stack. Units are centimetres in the table
frame: the origin is the centre of marker 0, +x points to marker 1 (right), +y points to marker 3
(towards the robot); z is up from the table; angles are degrees.

- `scene` reads the live state of the table (from your perception), so positions are current
  after every move.
- `robot` needs six primitives: `pick`, `place_at`, `place_in`, `place_next_to`, `move` (pick then
  place_at) and `home`, plus `can_reach`. Every place lets go of the held object.
- Errors are exceptions with clear messages; programs must not catch them.

```python
class Obj:
    # A read-only snapshot of one object. Get a fresh one from `scene` after moving things.
    # name, kind, role ("moved" | "container" | "reference" | "distractor");
    # x, y, z: centre in cm (z above the table); w, d, h: size in cm along x, y, z; yaw: degrees.
class Scene:
    # The table as it is now.
    def bounds() -> tuple[float, float, float, float]
        # The work area (x0, y0, x1, y1) in cm. Keep placements inside it.
    def containers() -> list[Obj]
        # Every container, sorted left to right.
    def distance(a: Obj, b: Obj) -> float
        # Centre-to-centre distance in cm on the table plane.
    def free_spot(near: Obj | None = None, side: str | None = None, size: tuple[float, float] = (6, 6), clearance: float = 2.0, avoid: list[tuple[float, float, float, float]] | None = None) -> tuple[float, float]
        # A clear, reachable (x, y) for an object of `size` (w, d) cm, at least `clearance` cm
        # from everything else and inside the work area. Objects taller than 5 cm get 6 cm more
        # room, because the gripper hand is wide. `avoid` lists extra regions (x, y, w, d) to keep
        # clear, e.g. slots you are about to fill. With `near`, the closest such spot to that
        # object; with `side` too ("left_of" | "right_of" | "in_front_of" | "behind"), only spots
        # fully on that side of it. Without `near`, the clear spot nearest the work-area centre.
        # Raises NoFreeSpot.
    def get(name: str) -> Obj
        # The object with this exact name; raises NoSuchObject.
    def is_inside(obj: Obj, container: Obj) -> bool
        # True if obj (fresh snapshot) sits inside the container.
    def objects() -> list[Obj]
        # Every object in this layout.
    def of_kind(kind: str) -> list[Obj]
        # Every object of this kind, sorted left to right (by x).
    def with_role(role: str) -> list[Obj]
        # Every object with this role, sorted left to right.
class Robot:
    # A Franka Panda arm that picks from above and places gently.
    def can_reach(x: float, y: float) -> bool
        # True if the gripper can reach (x, y) from above.
    def home() -> None
        # Return the arm to its rest pose.
    def move(obj: Obj, x: float, y: float) -> None
        # pick(obj) then place_at(x, y).
    def pick(obj: Obj) -> None
        # Grasp `obj` from above and lift it. Raises AlreadyHolding or NotReachable.
    def place_at(x: float, y: float, yaw: float | None = None) -> None
        # Put the held object down with its centre at (x, y) and let go. The gripper keeps the
        # object's orientation (`yaw` is accepted for compatibility and ignored).
    def place_in(container: Obj) -> None
        # Drop the held object into the container, centred over it.
    def place_next_to(ref: Obj, side: str, gap: float = 2.0) -> None
        # Put the held object `gap` cm beside `ref`: side is "left_of" (−x), "right_of" (+x),
        # "in_front_of" (+y, towards the robot) or "behind" (−y).
def log(msg: str) -> None  # a line in the run log, shown in the UI
# Errors: NotReachable, NothingHeld, AlreadyHolding, NoFreeSpot, Collision, NoSuchObject, PlaceFailed, TooManySkillCalls (each with a clear message)
```

## Goal

`goal.json` states what must be true at the end, in the goal DSL (quantifier, selector,
predicate, target). Use it to check the result on your robot.
