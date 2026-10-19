"""Numerical inverse kinematics for the nozzle (position + spray direction).

Input: a target nozzle position and spray direction in base_link, an optional warm-start seed.
Output: an IKResult with joint angles clamped to the URDF limits and the leftover position and angle error.
Must never: return joint angles outside the URDF limits, or hide the leftover error.

Damped least squares on the five arm joints with a finite-difference Jacobian.
The task has 5 independent constraints (3 for position, 2 for the direction of
the round spray cone; roll about the nozzle axis is free), which matches the
5 arm joints. Because the nozzle sits on the wrist-roll axis, the spray
direction always lies in the arm's vertical plane through the shoulder pan.
That means the arm can only hold the nozzle exactly perpendicular to a tilted
panel along part of it; the solver reports the leftover angle error rather
than hiding it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

from .so101 import ARM_JOINTS, NozzleTool, apply, clamp_to_limits, link_frames, nozzle_pose, rotate  # noqa: F401

# Seeds used when no warm start is given. Several elbow configurations so the
# first point of a path finds a sensible branch.
SEEDS: List[List[float]] = [
    [0.0, 0.0, 0.0, 1.2, 0.0],
    [0.0, 0.5, -0.5, 1.4, 0.0],
    [0.0, -0.5, 0.5, 1.4, 0.0],
    [0.0, 0.8, 0.2, 0.8, 0.0],
    [0.0, -0.8, 1.2, 0.8, 0.0],
    [0.0, 0.3, 0.9, -0.6, 0.0],
    [0.0, -0.3, -0.9, 1.6, 0.0],
]


@dataclass
class IKResult:
    q: List[float]
    pos_error: float  # metres
    angle_error: float  # radians between achieved and wanted spray direction
    iterations: int


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _solve(a: List[List[float]], b: List[float]) -> List[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        if abs(m[c][c]) < 1e-15:
            continue
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-15 else 0.0 for i in range(n)]


def angle_between(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return math.acos(max(-1.0, min(1.0, dot / (na * nb))))


def solve(
    target_pos: Sequence[float],
    target_dir: Sequence[float],
    tool: NozzleTool = NozzleTool(),
    seed: Optional[Sequence[float]] = None,
    max_iter: int = 200,
    tol: float = 1e-6,
    w_dir: float = 0.1,
    damping: float = 1e-3,
) -> IKResult:
    """Solve for joint angles. With ``seed`` it refines from there (warm start);
    without it, it tries every entry in SEEDS and keeps the best."""
    n = math.sqrt(sum(v * v for v in target_dir))
    target_dir = [v / n for v in target_dir]
    if seed is None:
        best = None
        for s in SEEDS:
            r = solve(target_pos, target_dir, tool, s, max_iter, tol, w_dir, damping)
            score = r.pos_error + 0.01 * r.angle_error
            if best is None or score < best[0] - 1e-9:
                best = (score, r)
        return best[1]

    q = clamp_to_limits(seed)
    it = 0
    for it in range(1, max_iter + 1):
        frames = link_frames(q)
        head = frames[-1]
        p = apply(head, tool.tip_local())
        d = rotate(head, tool.axis_local())
        e = [target_pos[i] - p[i] for i in range(3)] + [w_dir * v for v in _cross(d, target_dir)]
        if math.sqrt(sum(v * v for v in e)) < tol:
            break
        # Geometric Jacobian: joint j turns about world axis z_j through o_j.
        cols = []
        for joint, f in zip(ARM_JOINTS, frames):
            z = rotate(f, joint.axis)
            o = (f[0][3], f[1][3], f[2][3])
            dp = _cross(z, [p[i] - o[i] for i in range(3)])
            dd = _cross(z, d)
            # d(error_dir)/dq = d(d x t)/dq = dd x t ; the error is defined so that
            # a step along +e reduces it, hence the sign flip below.
            de = _cross(dd, target_dir)
            cols.append(list(dp) + [-w_dir * v for v in de])
        jtj = [[sum(cols[a][i] * cols[b][i] for i in range(6)) + (damping if a == b else 0.0)
                for b in range(5)] for a in range(5)]
        jte = [sum(cols[a][i] * e[i] for i in range(6)) for a in range(5)]
        dq = _solve(jtj, jte)
        step = max(abs(v) for v in dq)
        if step > 0.2:  # keep steps small so the solver stays on one branch
            dq = [v * 0.2 / step for v in dq]
        q = clamp_to_limits([q[j] + dq[j] for j in range(5)])
        if step < 1e-10:
            break
    p, d = nozzle_pose(q, tool)
    pos_err = math.sqrt(sum((target_pos[i] - p[i]) ** 2 for i in range(3)))
    return IKResult(q=q, pos_error=pos_err, angle_error=angle_between(d, target_dir), iterations=it)


__all__ = ["IKResult", "solve", "angle_between", "SEEDS", "ARM_JOINTS"]
