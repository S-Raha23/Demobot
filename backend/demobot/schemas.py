"""Core data contracts (docs/02 "Core data contracts"). Units: table cm, seconds, USD.

Table frame: origin at the centre of marker 0, +x towards marker 1, +y towards marker 3 (the
robot and camera side). Seen from above with the robot at the bottom, +x is right and +y is down.
"""

import math
from typing import Literal

from pydantic import BaseModel, Field

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


class IngestInfo(BaseModel):
    source_name: str
    width: int  # of display.mp4 / analysis.mp4 (rotation applied)
    height: int
    raw_duration_s: float
    trim_start_s: float  # into the raw clip; every later time is relative to this
    trim_end_s: float
    duration_s: float
    analysis_fps: float
    analysis_frames: int
    has_audio: bool
    keyframes: list[str]  # paths relative to the run's artifacts dir
    keyframe_times: list[float]


class MarkerPose(BaseModel):
    id: int
    center_cm: Vec2
    theta_rad: float
    corners_cm: list[Vec2]  # TL, TR, BR, BL as ArUco orders them
    corners_px: list[Vec2]  # the detected (median) image corners


class CameraPose(BaseModel):
    focal_px: float
    principal_px: Vec2
    focal_source: Literal["intrinsics", "homography", "default_fov"]
    position_cm: Vec3  # x, y in the table frame; z = height above the table
    look_dir: Vec3  # unit vector, table frame with z up
    tilt_deg: float  # 0 = straight down
    nadir_cm: Vec2
    rvec: Vec3  # OpenCV world->camera, world = (x, y, z_down)
    tvec: Vec3


class Rect(BaseModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0


class Calibration(BaseModel):
    image_size: tuple[int, int]  # width, height
    H_img_to_table: list[list[float]]
    markers: list[MarkerPose]
    work_area: Rect
    robot_base_cm: Vec2
    camera: CameraPose
    method: Literal["markers_bundle", "markers_plus_intrinsics"]
    reprojection_px: float
    frames_used: int
    rectify_px_per_cm: float = 10.0
    rectify_origin_cm: Vec2 = (0.0, 0.0)  # table point at rectified pixel (0, 0)
    rectify_size: tuple[int, int] = (0, 0)
    reference_t: float = 0.0  # time of the last clean frame, whose pose `camera` and H are
    frames_total: int = 0
    frames_blurred: int = 0
    frames_interpolated: int = 0
    max_motion_px: float = 0.0  # handheld drift of the work-area centre over the clip
    warnings: list[str] = Field(default_factory=list)


class FrameCam(BaseModel):
    """The camera in one analysis frame (the phone is handheld, so it moves)."""

    t: float
    H_img_to_table: list[list[float]]
    rvec: Vec3
    tvec: Vec3
    nadir_cm: Vec2
    height_cm: float
    markers_seen: int
    reproj_px: float | None  # None when interpolated
    sharpness: float
    blurred: bool
    interpolated: bool


class CameraTrack(BaseModel):
    fps: float
    focal_px: float
    principal_px: Vec2
    frames: list[FrameCam]


# ---------- scene objects, layouts and the goal DSL ----------
Role = Literal["moved", "container", "reference", "distractor"]
Shape = Literal["box", "cylinder", "sphere"]


class SceneObject(BaseModel):
    """One object: in a layout, in a grounded state or in a simulated final state.
    x, y, z are the centre in table cm (z above the table top); yaw in degrees."""

    name: str
    kind: str
    role: Role = "moved"
    shape: Shape = "box"
    x: float
    y: float
    z: float = 0.0
    yaw: float = 0.0
    w: float  # cm along x at yaw 0
    d: float  # cm along y at yaw 0
    h: float
    color: str = "#9aa3ad"
    texture: str | None = None
    hollow: bool = False  # an open box or cup, whatever its role in this task

    @property
    def is_container(self) -> bool:
        return self.role == "container"

    @property
    def is_open(self) -> bool:
        """Built as an open container (a floor and walls) that stays put in the sim."""
        return self.role == "container" or self.hollow

    def extents(self) -> tuple[float, float]:
        """Half-extents of the axis-aligned footprint at this yaw (cylinders ignore yaw)."""
        if self.shape in ("cylinder", "sphere"):
            r = max(self.w, self.d) / 2
            return r, r
        c, s = abs(math.cos(math.radians(self.yaw))), abs(math.sin(math.radians(self.yaw)))
        return (self.w * c + self.d * s) / 2, (self.w * s + self.d * c) / 2


class Layout(BaseModel):
    id: str = "demo"
    source: str = "demo"  # demo | redteam:<persona> | random | user
    description: str = ""
    seed: int | None = None
    objects: list[SceneObject]
    work_area: Rect
    robot_base_cm: Vec2

    def by_name(self) -> dict[str, SceneObject]:
        return {o.name: o for o in self.objects}


Quant = Literal["the", "all", "pair"]
Pred = Literal[
    "inside", "left_of", "right_of", "in_front_of", "behind", "near", "collinear", "swapped"
]


class Selector(BaseModel):
    name: str | None = None
    kind: str | None = None
    role: Role | None = None
    names: list[str] | None = None


class GoalClause(BaseModel):
    quant: Quant
    select: Selector
    pred: Pred
    target: Selector | None = None
    point_cm: Vec2 | None = None
    order_by: Literal["x", "y"] | None = None
    order: list[str] | None = None


class ClauseResult(BaseModel):
    clause: GoalClause
    holds: bool
    code: str | None = None  # EMPTY_SELECTION, TARGET_MISSING, ... when it cannot be evaluated
    objects: list[str] = Field(default_factory=list)
    measured: dict[str, float | bool | str] = Field(default_factory=dict)
    detail: str = ""


class SkillCall(BaseModel):
    skill: str
    args: dict[str, object] = Field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    t: float = 0.0  # sim seconds at the start of the call


class SimResult(BaseModel):
    ok: bool
    error: str | None = None
    error_type: str | None = None
    layout_id: str = "demo"
    skill_calls: list[SkillCall] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    final_state: list[SceneObject] = Field(default_factory=list)
    goal_results: list[ClauseResult] = Field(default_factory=list)
    goal_ok: bool = False
    collisions: list[str] = Field(default_factory=list)
    renders: dict[str, str] = Field(default_factory=dict)
    twin_trajectory: str | None = None
    duration_s: float = 0.0  # simulated seconds
    wall_s: float = 0.0


# ---------- understanding (Listen, Watch) ----------
class Segment(BaseModel):
    t0: float
    t1: float
    text: str


class Transcript(BaseModel):
    text: str
    language: str = "unknown"  # English | Hindi | Bengali | ...
    languages: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    source: Literal["narration", "correction", "none"] = "narration"


class SpecObject(BaseModel):
    name: str  # a short noun phrase SAM can segment, unique in the clip
    kind: str
    alt_names: list[str] = Field(default_factory=list)
    role: Role
    color: str = ""
    est_height_cm: float = 3.0
    est_size_cm: tuple[float, float] = (5.0, 5.0)


class Step(BaseModel):
    action: Literal["place_in", "place_next_to", "place_at"]
    object: str
    target: str | None = None
    relation: Literal["left_of", "right_of", "in_front_of", "behind"] | None = None
    t_start: float
    t_end: float
    evidence: str = ""


class TaskSpec(BaseModel):
    summary: str
    objects: list[SpecObject]
    steps: list[Step]
    goal: list[GoalClause]
    generalization: str
    uncertainties: list[str] = Field(default_factory=list)


# ---------- perception (Perceive, Ground) ----------
class TrackFrame(BaseModel):
    t: float
    bbox_px: tuple[float, float, float, float] | None  # x0, y0, x1, y1 (analysis pixels)
    centroid_px: Vec2 | None = None
    poly_px: list[Vec2] | None = None  # mask outline in stabilised display pixels
    score: float | None = None
    area_px: float | None = None


class Track(BaseModel):
    name: str
    phrase: str
    track_id: str | None = None
    quality: float
    frames: list[TrackFrame]
    flags: list[str] = Field(default_factory=list)


class Contact(BaseModel):
    t: float
    type: Literal["grasp", "release"]
    object: str


class MotionSegment(BaseModel):
    object: str
    t0: float
    t1: float
    from_cm: Vec2
    to_cm: Vec2


class StepMatch(BaseModel):
    step: int
    segment: int | None
    confidence: float
    timing_delta_s: float | None = None


class GroundedDemo(BaseModel):
    initial: list[SceneObject]
    final: list[SceneObject]
    segments: list[MotionSegment]
    contacts: list[Contact]
    matches: list[StepMatch]
    real_world: list[ClauseResult] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


# ---------- programs, verification, agents ----------
class Program(BaseModel):
    version: int
    parent_version: int | None = None
    code: str
    explanation: str = ""
    author: Literal["wonder", "wonder-harden", "wonder-correction", "spark-open-draft", "human"]
    diff_from_parent: str = ""
    synthesis_trace_id: str | None = None
    passed_demo: bool = False


class JudgeVerdict(BaseModel):
    same_goal_achieved: bool
    confidence: float
    differences: list[str] = Field(default_factory=list)
    suspected_error: str = ""


class CheckResult(BaseModel):
    ok: bool
    clauses: list[ClauseResult] = Field(default_factory=list)
    detail: str = ""
    inconclusive: bool = False  # nothing contradicts the goal, but the evidence is incomplete


class Verification(BaseModel):
    program_version: int
    symbolic: CheckResult
    real_world: CheckResult
    perceptual: CheckResult
    judge: JudgeVerdict | None = None
    agree: bool
    failure_class: (
        Literal["spec_mismatch", "program_bug", "perception_gap", "judge_dissent"] | None
    ) = None
    accepted_caveat: str | None = None  # the supervisor accepted the run despite a failed check
    masks: dict[str, list[dict[str, object]]] = Field(
        default_factory=dict
    )  # SAM outlines: real, camera
    renders: dict[str, str] = Field(default_factory=dict)  # real, camera, top (artifact paths)


class AgentDecision(BaseModel):
    agent: Literal["supervisor", "coder", "redteam", "arbiter"]
    step: int
    observation: str
    reasoning_summary: str  # one sentence, never a chain of thought
    tool: str
    args: dict[str, object] = Field(default_factory=dict)
    result: str = ""
    cost_usd: float = 0.0


class StressCase(BaseModel):
    layout: Layout
    persona: str
    rationale: str = ""
    before: SimResult | None = None
    after: SimResult | None = None


class StressReport(BaseModel):
    cases: list[StressCase]
    robustness_before: float
    robustness_after: float | None = None
    clusters: list[dict[str, object]] = Field(default_factory=list)
    program_before: int
    program_after: int | None = None


class SkillCard(BaseModel):
    skill_id: str
    title: str
    description: str
    image: str | None = None  # card.png from Muse Image, or None (the UI shows the final frame)
    goal_text: str
    program_version: int
    robustness: float | None = None
    cost_to_learn_usd: float
    run_id: str
