"""SO-101 follower kinematics, taken from the upstream URDF.

Input: joint angles (URDF radians) and a NozzleTool offset; the upstream URDF file for the cross-check.
Output: link frames, nozzle position and spray direction, joint-limit checks, parsed URDF joints.
Must never: change the embedded URDF numbers without the URDF cross-check test passing, or treat angles as calibrated LeRobot motor units.

The joint origins, axes and limits below are the numbers in
``third_party/SO-ARM100/Simulation/SO101/so101_new_calib.urdf`` at submodule
commit a758567 (TheRobotStudio, Apache-2.0). They are embedded as data so the
simulator runs without the submodule checked out; ``load_urdf_joints`` reads the
real file and ``tests/test_so101.py`` checks the two still agree.

Angles are URDF joint angles in radians ("new calibration": zero is the middle
of each joint's range). They are NOT LeRobot motor units and are not calibrated
against a physical arm.

The gripper is replaced by the airbrush head. The nozzle frame is an
assumption (see ``NozzleTool``) until the head housing is designed and measured.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

Vec3 = Tuple[float, float, float]
Mat4 = List[List[float]]

UPSTREAM_URDF = "third_party/SO-ARM100/Simulation/SO101/so101_new_calib.urdf"
UPSTREAM_COMMIT = "a758567"


@dataclass(frozen=True)
class Joint:
    name: str
    parent: str
    child: str
    xyz: Vec3
    rpy: Vec3
    axis: Vec3
    lower: float
    upper: float
    velocity: float  # rad/s, as written in the URDF (generic value, not a measured servo spec)


# Chain order: base -> wrist roll. The gripper joint is dropped (it becomes the needle servo).
ARM_JOINTS: Tuple[Joint, ...] = (
    Joint("shoulder_pan", "base_link", "shoulder_link",
          (0.0388353, -8.97657e-09, 0.0624), (3.14159, 4.18253e-17, -3.14159), (0, 0, 1),
          -1.91986, 1.91986, 10.0),
    Joint("shoulder_lift", "shoulder_link", "upper_arm_link",
          (-0.0303992, -0.0182778, -0.0542), (-1.5708, -1.5708, 0.0), (0, 0, 1),
          -1.74533, 1.74533, 10.0),
    Joint("elbow_flex", "upper_arm_link", "lower_arm_link",
          (-0.11257, -0.028, 1.73763e-16), (-3.63608e-16, 8.74301e-16, 1.5708), (0, 0, 1),
          -1.69, 1.69, 10.0),
    Joint("wrist_flex", "lower_arm_link", "wrist_link",
          (-0.1349, 0.0052, 3.62355e-17), (4.02456e-15, 8.67362e-16, -1.5708), (0, 0, 1),
          -1.65806, 1.65806, 10.0),
    Joint("wrist_roll", "wrist_link", "gripper_link",
          (5.55112e-17, -0.0611, 0.0181), (1.5708, 0.0486795, 3.14159), (0, 0, 1),
          -2.74385, 2.84121, 10.0),
)

JOINT_NAMES: Tuple[str, ...] = tuple(j.name for j in ARM_JOINTS)

# Upstream gripper TCP ("gripper_frame_joint", fixed, child of gripper_link).
# Used only as the reference length for the default nozzle offset.
UPSTREAM_GRIPPER_FRAME_XYZ: Vec3 = (-0.0079, -0.000218121, -0.0981274)


@dataclass(frozen=True)
class NozzleTool:
    """Where the nozzle tip sits in the ``gripper_link`` frame (metres).

    ASSUMPTION, not measured. Build Plan v3 says the housing puts the "nozzle on
    the wrist axis", i.e. on the wrist-roll axis (gripper_link z). Spray leaves
    along -z of gripper_link, the same side as the upstream gripper TCP. The
    default depth (0.098 m) reuses the upstream gripper TCP depth as a stand-in
    until the head housing is modelled and the real nozzle position is measured.
    The ToF sensor sits beside the nozzle, parallel to it, at ``tof_offset``.
    """

    depth: float = 0.098
    tof_offset: Vec3 = (0.018, 0.0, 0.0)  # assumption: 18 mm beside the nozzle, in the head frame

    def tip_local(self) -> Vec3:
        return (0.0, 0.0, -self.depth)

    def axis_local(self) -> Vec3:
        return (0.0, 0.0, -1.0)

    def tof_local(self) -> Vec3:
        x, y, z = self.tof_offset
        return (x, y, -self.depth + z)


# --- small 4x4 helpers (pure Python, no numpy) ---------------------------------

def mat_mul(a: Mat4, b: Mat4) -> Mat4:
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def rpy_xyz(xyz: Sequence[float], rpy: Sequence[float]) -> Mat4:
    """URDF origin transform: R = Rz(yaw) Ry(pitch) Rx(roll), then translate."""
    r, p, y = rpy
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    return [
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr, xyz[0]],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr, xyz[1]],
        [-sp, cp * sr, cp * cr, xyz[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def axis_angle(axis: Sequence[float], q: float) -> Mat4:
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(q), math.sin(q)
    t = 1 - c
    return [
        [t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0.0],
        [t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0.0],
        [t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def apply(m: Mat4, p: Sequence[float]) -> Vec3:
    return tuple(m[i][0] * p[0] + m[i][1] * p[1] + m[i][2] * p[2] + m[i][3] for i in range(3))  # type: ignore


def rotate(m: Mat4, v: Sequence[float]) -> Vec3:
    return tuple(m[i][0] * v[0] + m[i][1] * v[1] + m[i][2] * v[2] for i in range(3))  # type: ignore


_ORIGINS = [rpy_xyz(j.xyz, j.rpy) for j in ARM_JOINTS]


def _compose_rz(t: Mat4, origin: Mat4, q: float) -> Mat4:
    """t * origin * Rz(q), unrolled (every SO-101 arm joint turns about its z axis)."""
    m = [[t[i][0] * origin[0][j] + t[i][1] * origin[1][j] + t[i][2] * origin[2][j] + (t[i][3] if j == 3 else 0.0)
          for j in range(4)] for i in range(3)]
    c, s = math.cos(q), math.sin(q)
    return [[r[0] * c + r[1] * s, -r[0] * s + r[1] * c, r[2], r[3]] for r in m] + [[0.0, 0.0, 0.0, 1.0]]


def link_frames(q: Sequence[float], joints: Sequence[Joint] = ARM_JOINTS) -> List[Mat4]:
    """World (base_link) transforms of each child link, in chain order."""
    origins = _ORIGINS if joints is ARM_JOINTS else [rpy_xyz(j.xyz, j.rpy) for j in joints]
    t: Mat4 = [[1.0 if i == j else 0.0 for j in range(4)] for i in range(4)]
    frames = []
    for joint, origin, angle in zip(joints, origins, q):
        if tuple(joint.axis) == (0, 0, 1):
            t = _compose_rz(t, origin, angle)
        else:
            t = mat_mul(mat_mul(t, origin), axis_angle(joint.axis, angle))
        frames.append(t)
    return frames


def nozzle_pose(q: Sequence[float], tool: NozzleTool = NozzleTool()) -> Tuple[Vec3, Vec3]:
    """Nozzle tip position and unit spray direction in the base frame."""
    head = link_frames(q)[-1]
    return apply(head, tool.tip_local()), rotate(head, tool.axis_local())


def skeleton_points(q: Sequence[float], tool: NozzleTool = NozzleTool()) -> List[Vec3]:
    """Joint origins from base to nozzle tip, for drawing a stick-figure arm."""
    pts: List[Vec3] = [(0.0, 0.0, 0.0)]
    for f in link_frames(q):
        pts.append((f[0][3], f[1][3], f[2][3]))
    pts.append(nozzle_pose(q, tool)[0])
    return pts


def within_limits(q: Sequence[float], margin: float = 0.0) -> bool:
    return all(j.lower + margin <= a <= j.upper - margin for j, a in zip(ARM_JOINTS, q))


def clamp_to_limits(q: Sequence[float]) -> List[float]:
    return [min(max(a, j.lower), j.upper) for j, a in zip(ARM_JOINTS, q)]


def load_urdf_joints(path: Path) -> Dict[str, Joint]:
    """Parse revolute joints from an SO-101 URDF (used to verify the embedded table)."""
    root = ET.parse(path).getroot()
    out: Dict[str, Joint] = {}
    for el in root.findall("joint"):
        if el.get("type") != "revolute":
            continue
        origin = el.find("origin")
        limit = el.find("limit")
        axis = el.find("axis")
        out[el.get("name")] = Joint(
            name=el.get("name"),
            parent=el.find("parent").get("link"),
            child=el.find("child").get("link"),
            xyz=tuple(float(v) for v in origin.get("xyz").split()),
            rpy=tuple(float(v) for v in origin.get("rpy").split()),
            axis=tuple(float(v) for v in axis.get("xyz").split()),
            lower=float(limit.get("lower")),
            upper=float(limit.get("upper")),
            velocity=float(limit.get("velocity")),
        )
    return out
