# 06. Simulation, skill API and the digital twin

## Scene (`sim/scene.py`, ported from the first repo)

PyBullet runs in DIRECT mode, with one client per simulation so runs can go in parallel. Gravity is −9.81 and the timestep 1/240 s.

**Table:** a box whose top is at z = 0, sized to the work area plus a 15 cm margin. Its top texture is the rectified table image if available (this looks great in the twin), otherwise light grey.

**Robot:** `pybullet_data/franka_panda/panda.urdf`, fixed base.
- Base position: x = the work-area centre, y = **work-area front edge + 28 cm**, z = 0, facing −y.
- This placement comes from the first repo: top-down grasps closer than about 0.25–0.28 m to the base needed contorted poses, so we keep every target ≥ 0.28 m away. The far corners of a 60 × 40 cm area are then within about 0.75 m, inside the Panda's ~0.85 m reach.
- If the human's marker rectangle is larger, `check_reach` marks unreachable cells. Layouts and the red team avoid them, and the UI shows the reach map as a faint overlay.

**Objects:** stand-ins.
- Box or cylinder, with footprint and height from Ground.
- Mass 0.05–0.2 kg (scaled by volume); lateral friction 0.9.
- Top-face texture = the real crop (`changeVisualShape` with `textureUniqueId`). Sides take the mean colour.

**Containers:** open boxes or cylinders built from a floor plus 4–8 walls, 0.4 cm thick, using the real footprint and height. Objects placed inside must not intersect the walls.

## Skills (`sim/skills.py`, ported; keep the proven IK)

IK is PyBullet `calculateInverseKinematics` followed by **damped-least-squares refinement**; PyBullet alone leaves centimetre residuals. Grasping uses a fixed constraint created when the fingers close around the object, which is reliable and fast. All motions are interpolated in joint space, collision-checked at the waypoints, and recorded for the twin at 30 fps.

## The skill API exposed to generated programs (`program/api.py`)

This is a contract. It is documented in `skill_api.md` (exported), and the docstrings are inserted into Wonder's prompt.

```python
class Obj:              # read-only snapshot
    name: str; kind: str; role: str          # role: moved | container | reference | distractor
    x: float; y: float; z: float             # cm, table frame, centre
    w: float; d: float; h: float; yaw: float # cm, degrees

class Scene:
    def objects(self) -> list[Obj]                     # all objects in this layout
    def get(self, name: str) -> Obj                     # raises NoSuchObject
    def of_kind(self, kind: str) -> list[Obj]           # sorted left to right (x)
    def with_role(self, role: str) -> list[Obj]
    def containers(self) -> list[Obj]
    def bounds(self) -> tuple[float, float, float, float]   # x0, y0, x1, y1 (work area)
    def free_spot(self, near: Obj | None = None, side: str | None = None,
                  size: tuple[float, float] = (6, 6), clearance: float = 2.0) -> tuple[float, float]
    def is_inside(self, obj: Obj, container: Obj) -> bool
    def distance(self, a: Obj, b: Obj) -> float

class Robot:
    def can_reach(self, x: float, y: float) -> bool
    def pick(self, obj: Obj) -> None
    def place_at(self, x: float, y: float, yaw: float | None = None) -> None   # releases the held object
    def place_in(self, container: Obj) -> None                                  # held object into container
    def place_next_to(self, ref: Obj, side: str, gap: float = 2.0) -> None     # left_of|right_of|in_front_of|behind
    def move(self, obj: Obj, x: float, y: float) -> None                        # pick + place_at
    def home(self) -> None

def log(msg: str) -> None
```

**Errors are exceptions with clear messages:** `NotReachable`, `NothingHeld`, `AlreadyHolding`, `NoFreeSpot`, `Collision`, `NoSuchObject`. The sandbox returns them to Wonder as tool output.

`Scene` reads the **live** state, so positions are always current after moves.

## Rendering (`sim/render.py`)

- **Top-down:** an orthographic-like render with a long focal length from high above. 10 px/cm, the same framing as the rectified real image. Used for the UI and the red-team grid.
- **Camera-pose render:** PyBullet `getCameraImage` with the view and projection built from the calibrated camera pose and focal length, at the analysis resolution. **Matches the real camera's viewpoint, so it is comparable side by side and SAM can segment it** (perceptual verification).
- `sim.mp4` (optional, used by the demo video): rendered from the camera pose at 15 fps, encoded with ffmpeg.

Renders use `ER_TINY_RENDERER` (CPU) so they work in Docker and on Modal.

## Digital-twin export (`sim/twin_export.py`)

`twin_trajectory.json`, frames at 30 fps:

```json
{"fps": 30, "robot": {"urdf": "/assets/franka_panda/panda.urdf", "base": [x, y, z, yaw]},
 "objects": [{"name": "white mug", "shape": "cylinder", "size": [8, 8, 9.5], "texture": "crops/white_mug.png", "color": "#e8e6e1"}],
 "frames": [{"t": 0.0, "q": [7 joint angles + 2 finger], "poses": {"white mug": [x, y, z, qx, qy, qz, qw]}, "event": null}],
 "events": [{"t": 3.2, "type": "grasp", "object": "blue pen"}, {"t": 5.9, "type": "release", "object": "blue pen"}]}
```

- Positions are in metres in the PyBullet world. The frontend converts to the three.js frame (Y-up).
- Serve the Panda URDF and its OBJ meshes from `pybullet_data/franka_panda/` as static assets (they ship with pybullet, `meshes/visual/*.obj`). `urdf-loader` loads them in the browser.

## Layouts (`sim/layouts.py`)

- `from_grounded(demo)`: the demo layout.
- `random(seed, n_extra=0)`: a valid random rearrangement of the same objects.
- `validate(layout)`: checks reach, overlaps and work-area bounds (shared with the red team).
- `apply_user_edit(layout, moves)`: used by `try-layout` (the judge drags objects).

## Performance targets

- One demo-layout simulation including the twin export: < 8 s on a laptop CPU.
- 12 stress layouts: < 40 s using Modal Sandboxes in parallel, or < 90 s on a local process pool.
