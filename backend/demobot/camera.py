"""Pinhole camera maths shared by calibration, grounding, the synthetic generator and rendering.

The 3D frame here is W = (x, y, z_down): table x and y, and z = x × y, which points *into* the
table (right-handed). A point h cm above the table has z = -h. Reported heights are positive.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]


def K_matrix(f: float, cx: float, cy: float) -> F64:
    return np.array([[f, 0, cx], [0, f, cy], [0, 0, 1]], float)


@dataclass
class Camera:
    K: F64
    R: F64  # world -> camera
    t: F64
    width: int
    height: int

    @property
    def center(self) -> F64:
        return -self.R.T @ self.t

    def table_to_image(self) -> F64:
        """Homography mapping table points (x, y, 1) at z = 0 to image pixels."""
        G = self.K @ np.column_stack([self.R[:, 0], self.R[:, 1], self.t])
        return G / G[2, 2]

    def project(self, pts: F64) -> F64:
        """World points (N, 3) in (x, y, z_down) -> pixels (N, 2)."""
        cam = (self.R @ np.asarray(pts, float).T).T + self.t
        uv = (self.K @ cam.T).T
        return uv[:, :2] / uv[:, 2:3]


def look_at(
    position_cm: tuple[float, float, float],
    target_cm: tuple[float, float],
    f: float,
    width: int,
    height: int,
) -> Camera:
    """A camera at (x, y, height) looking at a table point, with image-down towards +y (the
    robot side at the bottom of the image, as when a phone stands on the robot side)."""
    C = np.array([position_cm[0], position_cm[1], -position_cm[2]], float)
    T = np.array([target_cm[0], target_cm[1], 0.0])
    z = T - C
    z /= np.linalg.norm(z)
    ydir = np.array([0.0, 1.0, 0.0])
    y = ydir - (ydir @ z) * z
    y /= np.linalg.norm(y)
    x = np.cross(y, z)
    R = np.stack([x, y, z])
    return Camera(K_matrix(f, width / 2, height / 2), R, -R @ C, width, height)


def focal_from_homography(G: F64, cx: float, cy: float) -> float | None:
    """Zhang's single-view constraints with square pixels, zero skew and a known principal
    point. None when the view is too close to fronto-parallel to tell."""
    Gp = np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]], float) @ G
    a1, b1, c1 = Gp[:, 0]
    a2, b2, c2 = Gp[:, 1]
    A = np.array([a1 * a2 + b1 * b2, a1**2 + b1**2 - a2**2 - b2**2])
    C = np.array([c1 * c2, c1**2 - c2**2])
    scale = np.abs(A).max()
    if scale == 0:
        return None
    # A/f² + C = 0  ->  u = 1/f²; weight both equations alike
    u = -(A @ C) / (A @ A)
    if u <= 0 or not np.isfinite(u):
        return None
    f = float(1 / np.sqrt(u))
    # conditioning: the c terms vanish for a fronto-parallel view
    if np.abs(C).max() * f**2 < 0.02 * scale:
        return None
    return f


def pose_from_homography(G: F64, K: F64) -> tuple[F64, F64]:
    """(R, t) of the camera from the table->image homography and K."""
    M = np.linalg.inv(K) @ G
    lam = 2 / (np.linalg.norm(M[:, 0]) + np.linalg.norm(M[:, 1]))
    M = M * lam
    if M[2, 2] < 0:  # the table must be in front of the camera
        M = -M
    r1, r2, t = M[:, 0], M[:, 1], M[:, 2]
    R = np.column_stack([r1, r2, np.cross(r1, r2)])
    U, _, Vt = np.linalg.svd(R)
    R = U @ Vt
    if np.linalg.det(R) < 0:
        R = U @ np.diag([1, 1, -1]) @ Vt
    return R, t


def camera_from_homography(G: F64, f: float, cx: float, cy: float, w: int, h: int) -> Camera:
    K = K_matrix(f, cx, cy)
    R, t = pose_from_homography(G, K)
    return Camera(K, R, t, w, h)


def apply_h(H: F64, pts: F64) -> F64:
    pts = np.asarray(pts, float).reshape(-1, 2)
    return cv2.perspectiveTransform(pts[None], H)[0]


def parallax_correct(p_plane: F64, nadir: tuple[float, float], cam_height: float, h: float) -> F64:
    """A point seen at p_plane on the table plane but really h cm above it lies at
    c + (p_plane − c)·(H_cam − h)/H_cam, c the nadir (docs/04 "Parallax correction")."""
    c = np.asarray(nadir, float)
    return c + (np.asarray(p_plane, float) - c) * (cam_height - h) / cam_height
