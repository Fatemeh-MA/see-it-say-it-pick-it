#!/usr/bin/env python3
"""Load a scene and turn a pixel into a UR5 robot coordinate.

No Zivid SDK needed: only numpy and opencv-python.

    from scene_io import load_scene, pixel_to_robot
    scene = load_scene("dataset/scene_03")
    scene.rgb            # [H, W, 3] uint8, RGB
    scene.xyz            # [H, W, 3] float32 mm, camera frame, NaN = no depth
    scene.depth_mm       # [H, W] uint16 mm, 0 = no depth
    scene.instructions   # list of (instruction_id, category, text)
    pixel_to_robot(scene, u=412, v=285)   # -> array([x, y, z]) in mm, robot base frame (table plane for 2D data)

From the command line, to check one pixel:

    python starter/scene_io.py dataset/scene_03 412 285

Pixel convention: u = column (x, to the right), v = row (y, down), origin top-left,
exactly as in the image and in target_pixel of the output schema.
"""
from __future__ import annotations

import json, sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Scene:
    name: str
    rgb: np.ndarray
    depth_mm: np.ndarray | None
    xyz: np.ndarray | None
    K: np.ndarray
    base_T_camera: np.ndarray | None
    gripper_max_opening_mm: float | None
    instructions: list

    @property
    def size(self):
        return self.rgb.shape[1], self.rgb.shape[0]


def _instructions(path: Path, scene: str):
    out = []
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        cat, _, text = line.partition("\t")
        if not text:
            cat, text = "simple", cat
        if text.strip():
            out.append((f"{scene}_i{len(out) + 1}", cat.strip(), text.strip()))
    return out


def calibration_path(folder) -> Path:
    """The scene's own calibration.json, else the one shared by the whole dataset (its parent folder)."""
    d = Path(folder)
    return d / "calibration.json" if (d / "calibration.json").exists() else d.parent / "calibration.json"


def load_scene(folder) -> Scene:
    d = Path(folder)
    calib = json.loads(calibration_path(d).read_text())
    rgb = cv2.cvtColor(cv2.imread(str(d / "rgb.png"), cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
    depth = cv2.imread(str(d / "depth.png"), cv2.IMREAD_UNCHANGED) if (d / "depth.png").exists() else None
    xyz = np.load(d / "xyz.npy") if (d / "xyz.npy").exists() else None
    T = calib.get("base_T_camera")
    return Scene(
        name=d.name,
        rgb=rgb,
        depth_mm=depth,
        xyz=xyz,
        K=np.array(calib["camera"]["intrinsics"]["K"], dtype=float),
        base_T_camera=np.array(T, dtype=float) if T is not None else None,
        gripper_max_opening_mm=calib.get("gripper_max_opening_mm"),
        instructions=_instructions(d / "instructions.txt", d.name),
    )


def pixel_to_camera(scene: Scene, u: int, v: int, window: int = 5) -> np.ndarray:
    """3D point in the camera frame, mm. Median of valid points in a (2*window+1)^2 patch,
    so a pixel that lands on a small hole or an object edge still returns a sensible point."""
    w, h = scene.size
    if not (0 <= u < w and 0 <= v < h):
        raise ValueError(f"pixel ({u}, {v}) is outside the {w}x{h} image")
    v0, v1, u0, u1 = max(0, v - window), min(h, v + window + 1), max(0, u - window), min(w, u + window + 1)
    if scene.xyz is not None:
        patch = scene.xyz[v0:v1, u0:u1].reshape(-1, 3)
        patch = patch[~np.isnan(patch).any(axis=1)]
        if len(patch):
            return np.median(patch, axis=0)
    # fallback: back-project depth with K (ignores lens distortion: a few mm at the image edge)
    if scene.depth_mm is None:
        raise ValueError(f"{scene.name} is a 2D-only capture: no depth, so no 3D point")
    z = scene.depth_mm[v0:v1, u0:u1].astype(float)
    z = z[z > 0]
    if not len(z):
        raise ValueError(f"no depth within {window} px of ({u}, {v})")
    z = float(np.median(z))
    fx, fy, cx, cy = scene.K[0, 0], scene.K[1, 1], scene.K[0, 2], scene.K[1, 2]
    return np.array([(u - cx) * z / fx, (v - cy) * z / fy, z])


TABLE_Z_MM = 4.0  # table surface in the UR5 base frame


def pixel_to_table(scene: Scene, u: float, v: float, table_z_mm: float = TABLE_Z_MM) -> np.ndarray:
    """2D-only data: where the camera ray through pixel (u, v) meets the table plane, UR5 base frame, mm.
    Exact for flat objects; for a tall object it is off by roughly height x (distance from image centre / 1 m)."""
    if scene.base_T_camera is None:
        raise ValueError(f"{scene.name}: calibration.json has no base_T_camera")
    R, t = scene.base_T_camera[:3, :3], scene.base_T_camera[:3, 3]
    ray = R @ np.linalg.inv(scene.K) @ np.array([u, v, 1.0])
    s = (table_z_mm - t[2]) / ray[2]
    return t + s * ray


def pixel_to_robot(scene: Scene, u: int, v: int, window: int = 5) -> np.ndarray:
    """Point in the UR5 base frame, mm: measured depth when the scene has it, else the table plane."""
    if scene.base_T_camera is None:
        raise ValueError(f"{scene.name}: calibration.json has no base_T_camera")
    if scene.xyz is None and scene.depth_mm is None:
        return pixel_to_table(scene, u, v)
    p = np.append(pixel_to_camera(scene, u, v, window), 1.0)
    return (scene.base_T_camera @ p)[:3]


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: python scene_io.py <scene_folder> <u> <v>")
    s = load_scene(sys.argv[1])
    u, v = int(sys.argv[2]), int(sys.argv[3])
    print(f"{s.name}  pixel (u={u}, v={v})")
    if s.xyz is not None or s.depth_mm is not None:
        cam = pixel_to_camera(s, u, v)
        print(f"  camera frame  [mm]  x={cam[0]:8.1f}  y={cam[1]:8.1f}  z={cam[2]:8.1f}")
    if s.base_T_camera is not None:
        rb = pixel_to_robot(s, u, v)
        print(f"  UR5 base      [mm]  x={rb[0]:8.1f}  y={rb[1]:8.1f}  z={rb[2]:8.1f}")
