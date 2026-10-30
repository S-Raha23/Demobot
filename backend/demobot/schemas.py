"""Core data contracts (docs/02 "Core data contracts"). Units: table cm, seconds, USD.

Table frame: origin at the centre of marker 0, +x towards marker 1, +y towards marker 3 (the
robot and camera side). Seen from above with the robot at the bottom, +x is right and +y is down.
"""

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
    warnings: list[str] = Field(default_factory=list)
