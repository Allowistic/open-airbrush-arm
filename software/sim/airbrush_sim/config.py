"""Simulation settings. Every number here is either from the repo or an assumption.

Input: viewer or CLI parameters as strings.
Output: a validated SimConfig (with Canvas, Shape and NozzleTool) and the ASSUMPTIONS table.
Must never: add or change a number without a matching ASSUMPTIONS row that says whether it is a source or an assumption.

``ASSUMPTIONS`` lists each setting with where it came from, so the viewer and
the exported JSON can show it next to the results.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field, fields
from typing import Any, Dict, Tuple

from .so101 import NozzleTool, Vec3

SHAPES = ("circle", "square", "triangle", "line", "standoff_ladder")


@dataclass
class Canvas:
    """The panel being painted, in the arm's base_link frame.

    Canvas coordinates (u, v) are in mm from the panel centre: u runs to the
    right as seen from behind the arm, v runs away from the arm (and up the
    easel when tilted). The panel normal points out of the paint side.
    """

    width_mm: float = 420.0  # A3 landscape (Build Plan v3: ~A3 / 12x16 in panel)
    height_mm: float = 297.0
    center_m: Vec3 = (0.23, 0.0, 0.005)  # ASSUMPTION: near edge ~8 cm from the base origin, 5 mm board on the table
    tilt_deg: float = 0.0  # 0 = flat on the table (plan v1); positive tilts the far edge up, toward an easel

    def axes(self) -> Tuple[Vec3, Vec3, Vec3]:
        t = math.radians(self.tilt_deg)
        u = (0.0, -1.0, 0.0)
        v = (math.cos(t), 0.0, math.sin(t))
        n = (-math.sin(t), 0.0, math.cos(t))
        return u, v, n

    def to_world(self, u_mm: float, v_mm: float, standoff_mm: float = 0.0) -> Vec3:
        u, v, n = self.axes()
        c = self.center_m
        a, b, s = u_mm / 1000.0, v_mm / 1000.0, standoff_mm / 1000.0
        return tuple(c[i] + a * u[i] + b * v[i] + s * n[i] for i in range(3))  # type: ignore

    def to_canvas(self, p: Vec3) -> Tuple[float, float, float]:
        """World point -> (u_mm, v_mm, height above the panel in mm)."""
        u, v, n = self.axes()
        d = [p[i] - self.center_m[i] for i in range(3)]
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        return dot(d, u) * 1000.0, dot(d, v) * 1000.0, dot(d, n) * 1000.0

    def ray_hit(self, origin: Vec3, direction: Vec3):
        """Distance (mm) along a ray to the panel plane and the (u, v) hit point.
        Returns None if the ray points away from the plane."""
        _, _, n = self.axes()
        denom = sum(direction[i] * n[i] for i in range(3))
        if denom >= -1e-9:
            return None
        h = sum((origin[i] - self.center_m[i]) * n[i] for i in range(3))
        t = -h / denom
        hit = tuple(origin[i] + t * direction[i] for i in range(3))
        hu, hv, _ = self.to_canvas(hit)  # type: ignore
        return t * 1000.0, hu, hv

    def contains(self, u_mm: float, v_mm: float, margin_mm: float = 0.0) -> bool:
        return (abs(u_mm) <= self.width_mm / 2 - margin_mm) and (abs(v_mm) <= self.height_mm / 2 - margin_mm)


@dataclass
class Shape:
    kind: str = "circle"
    center_mm: Tuple[float, float] = (0.0, -40.0)  # canvas (u, v); default sits in the reachable band of a flat A3 panel
    size_mm: float = 80.0  # circle diameter, square/triangle side, line length, ladder line length
    ladder_standoffs_mm: Tuple[float, ...] = (20.0, 30.0, 40.0, 50.0, 60.0, 80.0)
    ladder_spacing_mm: float = 20.0


@dataclass
class SimConfig:
    shape: Shape = field(default_factory=Shape)
    canvas: Canvas = field(default_factory=Canvas)
    tool: NozzleTool = field(default_factory=NozzleTool)

    standoff_mm: float = 40.0  # nozzle-to-panel distance while spraying
    travel_lift_mm: float = 30.0  # extra height for moves with the spray off
    speed_mm_s: float = 40.0  # tool-tip speed along strokes and travel moves
    dt_s: float = 0.02  # sample period (50 Hz)

    # Spray sequence from Build Plan v3: air on -> needle back -> stroke -> needle home -> air off.
    air_lead_s: float = 0.2  # ASSUMPTION: hold still with air on before opening the needle
    air_tail_s: float = 0.2  # ASSUMPTION: hold still with air on after closing the needle
    needle_open: float = 0.6  # 0..1 command to the needle servo; flow mapping is unmeasured (Stage 1)

    # Idealised spray cone. NOT calibrated: spot diameter = ratio * standoff.
    spray_width_ratio: float = 0.25

    # Limits from Build Plan v3 "Software" section; the plan's two distance
    # ranges disagree, so both are kept and reported, not merged.
    gate_min_mm: float = 30.0  # "spray only with ToF 3-25 cm"
    gate_max_mm: float = 250.0
    paint_range_min_mm: float = 20.0  # "map it to the airbrush's 2-8 cm range" (Stage 2 scaling)
    paint_range_max_mm: float = 80.0
    tof_noise_mm: float = 0.0  # simulated sensor noise (1 sigma); real VL53L4CX behaviour is not modelled
    seed: int = 0

    joint_speed_limit_rad_s: float = 2.0  # 20% of the URDF velocity (10 rad/s), per the plan's ~20% bring-up cap

    # What counts as "reached" in the model. These are solver tolerances, not
    # arm accuracy: the real SO-101 is mm-level with backlash (plan, Gotcha 3).
    pos_tol_mm: float = 0.5
    angle_tol_deg: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


ASSUMPTIONS = [
    ("Arm geometry and joint limits", "SO-101 URDF so101_new_calib.urdf (submodule a758567)", "source"),
    ("Nozzle on the wrist-roll axis", "Build Plan v3, 'For Clay' item 1", "source"),
    ("Nozzle 98 mm past the wrist-roll joint", "Stand-in: upstream gripper TCP depth. Measure the real housing.", "assumption"),
    ("ToF sensor 18 mm beside the nozzle, parallel", "Placeholder until the bracket is designed", "assumption"),
    ("A3 panel, flat or slightly tilted", "Build Plan v3, v1 scope", "source"),
    ("Panel position (centre 23 cm in front of the base)", "Placeholder until arm-to-canvas registration (Stage 3)", "assumption"),
    ("Spray gate 30-250 mm", "Build Plan v3 'spray only with ToF 3-25 cm'", "source"),
    ("Painting range 20-80 mm", "Build Plan v3 Stage 2 scaling ('2-8 cm range')", "source"),
    ("Gate and painting range conflict below 30 mm", "Unresolved in the plan; the sim reports it and blocks spray there", "open question"),
    ("Spot diameter = 0.25 x standoff", "Idealised cone, not calibrated. Measure with a test card.", "assumption"),
    ("Joint speed cap 2 rad/s", "20% of the URDF velocity value (a generic number, not a servo spec)", "assumption"),
    ("No dynamics, backlash, payload sag, hose drag, air lag or collisions", "Kinematics only", "limitation"),
]


def config_from_params(params: Dict[str, Any]) -> SimConfig:
    """Build a SimConfig from flat string params (query string / CLI)."""
    cfg = SimConfig()
    f = lambda k, d: float(params[k]) if k in params and params[k] not in ("", None) else d
    kind = params.get("shape", cfg.shape.kind)
    if kind not in SHAPES:
        raise ValueError(f"unknown shape {kind!r}; choose one of {', '.join(SHAPES)}")
    cfg.shape.kind = kind
    cfg.shape.center_mm = (f("u", cfg.shape.center_mm[0]), f("v", cfg.shape.center_mm[1]))
    cfg.shape.size_mm = f("size", cfg.shape.size_mm)
    cfg.standoff_mm = f("standoff", cfg.standoff_mm)
    cfg.speed_mm_s = f("speed", cfg.speed_mm_s)
    cfg.canvas.tilt_deg = f("tilt", cfg.canvas.tilt_deg)
    cx, cy, cz = cfg.canvas.center_m
    cfg.canvas.center_m = (f("canvas_x", cx * 1000) / 1000, f("canvas_y", cy * 1000) / 1000, f("canvas_z", cz * 1000) / 1000)
    cfg.tool = NozzleTool(depth=f("nozzle_depth", cfg.tool.depth * 1000) / 1000, tof_offset=cfg.tool.tof_offset)
    cfg.spray_width_ratio = f("spray_ratio", cfg.spray_width_ratio)
    cfg.gate_min_mm = f("gate_min", cfg.gate_min_mm)
    cfg.gate_max_mm = f("gate_max", cfg.gate_max_mm)
    cfg.tof_noise_mm = f("tof_noise", cfg.tof_noise_mm)
    cfg.joint_speed_limit_rad_s = f("joint_speed_limit", cfg.joint_speed_limit_rad_s)
    validate(cfg)
    return cfg


def validate(cfg: SimConfig) -> None:
    if not 1.0 <= cfg.standoff_mm <= 300.0:
        raise ValueError("standoff must be between 1 and 300 mm")
    if not 1.0 <= cfg.speed_mm_s <= 500.0:
        raise ValueError("speed must be between 1 and 500 mm/s")
    if not 1.0 <= cfg.shape.size_mm <= 400.0:
        raise ValueError("size must be between 1 and 400 mm")
    if not -80.0 <= cfg.canvas.tilt_deg <= 80.0:
        raise ValueError("tilt must be between -80 and 80 degrees")
    if not 0.02 <= cfg.tool.depth <= 0.3:
        raise ValueError("nozzle_depth must be between 20 and 300 mm")


__all__ = ["Canvas", "Shape", "SimConfig", "ASSUMPTIONS", "SHAPES", "config_from_params", "validate", "fields"]
