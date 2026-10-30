"""Simulator constants (docs/06). Sim positions are metres; table positions are cm.

Ported from the first repo, where the IK settings were tuned."""

import math

# physics
GRAVITY = -9.81
TIME_STEP = 1.0 / 240.0

# table: a static box whose top is z = 0, sized to the work area plus this margin
TABLE_MARGIN_M = 0.15
TABLE_THICKNESS_M = 0.04

# Panda
PANDA_URDF = "franka_panda/panda.urdf"
PANDA_YAW = math.pi / 2
ARM_JOINTS = list(range(7))
FINGER_JOINTS = [9, 10]
EE_LINK = 11
REST_POSE = [0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785]
ARM_FORCE = 240.0
FINGER_FORCE = 40.0
FINGER_OPEN = 0.04
# 9 entries: the 7 arm joints, then the 2 finger joints
LL = [-2.8973, -1.7628, -2.8973, -3.0718, -2.8973, -0.0175, -2.8973, 0.0, 0.0]
UL = [2.8973, 1.7628, 2.8973, -0.0698, 2.8973, 3.7525, 2.8973, 0.04, 0.04]
JR = [u - lo for lo, u in zip(LL, UL, strict=True)]
REST = [*REST_POSE, FINGER_OPEN, FINGER_OPEN]
EE_DOWN_EULER = (math.pi, 0.0, 0.0)

# skills (metres above the table)
Z_SAFE = 0.20
GRASP_OFFSET = 0.01
IK_TOLERANCE_M = 0.01
# IK refinement: damped least squares seeded by PyBullet's IK, the current pose and a bank of
# sampled top-down poses (PyBullet's IK alone leaves cm-level residuals near the base)
# working limits for the IK: physical limits, but joints 1, 3 and 5 kept near a canonical
# top-down posture so consecutive solutions stay in one family and interpolation stays high
IK_LL = [-1.6, LL[1], -0.8, LL[3], -1.2, LL[5], LL[6]]
IK_UL = [1.6, UL[1], 0.8, UL[3], 1.2, UL[5], UL[6]]
IK_BANK_SAMPLES = 30000
IK_BANK_SEED = 7
IK_BANK_NEAREST = 8
IK_ITERATIONS = 300
IK_DAMPING = 0.03
IK_ORN_WEIGHT = 0.3  # full pose: position and pointing down
IK_ORN_WEIGHT_TILT = 0.02  # fallback when the exact pose is out of reach: position first
IK_POS_DONE_M = 2e-4  # stop iterating
IK_ORN_DONE_RAD = 2e-3
IK_POS_OK_M = 1e-3  # accept as an exact top-down solution
IK_ORN_OK_RAD = 0.01
IK_MAX_STEP_RAD = 0.2
IK_REST_GAIN = 0.05
MOVE_HOLD_MAX_STEPS = 60  # after the interpolation, hold until the joints arrive
MOVE_HOLD_TOL_RAD = 2e-3
REACH_MIN_M = 0.25  # top-down grasps nearer the base need contorted poses
REACH_MAX_M = 0.80
SETTLE_STEPS = 120
SCENE_SETTLE_STEPS = 120

# stand-ins
OBJECT_DENSITY_KG_M3 = 400.0
OBJECT_MASS_MIN_KG = 0.05
OBJECT_MASS_MAX_KG = 0.2
LATERAL_FRICTION = 0.9
RESTITUTION = 0.0
CONTAINER_WALL_M = 0.004  # floor and wall thickness
CYLINDER_WALLS = 8

# the twin recording
TWIN_FPS = 30
STEPS_PER_TWIN_FRAME = 8  # 240 Hz physics / 30 fps

# skill results (cm)
DISPLACED_CM = 1.0
DROPPED_CM = 5.0
MAX_SKILL_CALLS = 40

# fixed RGBA table keyed by colour name; unknown colours fall back to grey
COLOURS: dict[str, tuple[float, float, float, float]] = {
    "red": (0.86, 0.15, 0.15, 1.0),
    "green": (0.18, 0.65, 0.25, 1.0),
    "blue": (0.15, 0.35, 0.85, 1.0),
    "yellow": (0.95, 0.85, 0.15, 1.0),
    "orange": (0.95, 0.55, 0.10, 1.0),
    "purple": (0.55, 0.25, 0.70, 1.0),
    "pink": (0.95, 0.55, 0.70, 1.0),
    "white": (0.95, 0.95, 0.95, 1.0),
    "black": (0.10, 0.10, 0.10, 1.0),
    "brown": (0.55, 0.35, 0.20, 1.0),
    "grey": (0.55, 0.55, 0.55, 1.0),
    "gray": (0.55, 0.55, 0.55, 1.0),
}
DEFAULT_RGBA = COLOURS["grey"]
TABLE_RGBA = (0.80, 0.70, 0.55, 1.0)


# the default work area when there is no calibration: markers at 60 × 40 cm, shrunk by 4 cm
DEFAULT_WORK_AREA = (4.0, 4.0, 56.0, 36.0)
ROBOT_BEHIND_FRONT_CM = 28.0
