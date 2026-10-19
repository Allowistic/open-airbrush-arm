"""Turn a shape into a timed, sampled arm trajectory and check it.

For each sample the simulator solves IK for the commanded nozzle pose, then
works out everything from the *achieved* pose (forward kinematics): where the
spray axis actually hits the panel, the true standoff, the simulated ToF
reading and whether the spray gate would allow spraying. Paint is only drawn
where the gate allows it, so a path the arm cannot follow shows up distorted or
missing instead of looking perfect.
"""

from __future__ import annotations

import math
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import ik, paths
from .config import ASSUMPTIONS, SimConfig
from .so101 import ARM_JOINTS, JOINT_NAMES, apply, link_frames, nozzle_pose, rotate, skeleton_points

BRANCH_JUMP_RAD = 0.25  # a joint moving more than this in one sample means the IK switched branch
NEAR_LIMIT_RAD = math.radians(3.0)


def _segment(a: Sequence[float], b: Sequence[float], step: float) -> List[Tuple[float, float, float]]:
    """Points from a to b (exclusive of a) every ``step`` mm, in (u, v, standoff) space."""
    dist = math.sqrt(sum((b[i] - a[i]) ** 2 for i in range(3)))
    n = max(1, int(math.ceil(dist / step - 1e-9)))
    return [tuple(a[i] + (b[i] - a[i]) * k / n for i in range(3)) for k in range(1, n + 1)]  # type: ignore


def build_timeline(cfg: SimConfig) -> List[Dict[str, Any]]:
    """Commanded samples: phase, target (u, v, standoff), air, needle."""
    step = cfg.speed_mm_s * cfg.dt_s
    strokes = paths.build(cfg.shape, cfg.standoff_mm)
    out: List[Dict[str, Any]] = []

    def add(phase, p, air, needle, stroke):
        out.append({"phase": phase, "target": tuple(p), "air": air, "needle": needle, "stroke": stroke})

    def dwell(phase, p, seconds, air, needle, stroke):
        for _ in range(int(round(seconds / cfg.dt_s))):
            add(phase, p, air, needle, stroke)

    cur: Optional[Tuple[float, float, float]] = None
    for si, stroke in enumerate(strokes):
        start = stroke[0]
        hover = (start[0], start[1], start[2] + cfg.travel_lift_mm)
        if cur is None:
            add("hover", hover, False, 0.0, si)
        else:
            for p in _segment(cur, hover, step):
                add("travel", p, False, 0.0, si)
        for p in _segment(hover, start, step):
            add("approach", p, False, 0.0, si)
        dwell("air_on", start, cfg.air_lead_s, True, 0.0, si)
        pts = paths.resample(stroke, step)
        for p in pts[1:]:
            add("stroke", p, True, cfg.needle_open, si)
        end = stroke[-1]
        dwell("air_off", end, cfg.air_tail_s, True, 0.0, si)
        lift = (end[0], end[1], end[2] + cfg.travel_lift_mm)
        for p in _segment(end, lift, step):
            add("retract", p, False, 0.0, si)
        cur = lift
    for i, s in enumerate(out):
        s["t"] = round(i * cfg.dt_s, 6)
    return out


def simulate(cfg: SimConfig) -> Dict[str, Any]:
    rng = random.Random(cfg.seed)
    canvas = cfg.canvas
    _, _, n = canvas.axes()
    spray_dir = tuple(-c for c in n)
    timeline = build_timeline(cfg)
    pos_tol = cfg.pos_tol_mm / 1000.0
    ang_tol = math.radians(cfg.angle_tol_deg)

    samples = []
    q_prev: Optional[List[float]] = None
    prev_reached = True
    since_restart = 0
    for s in timeline:
        u, v, so = s["target"]
        target = canvas.to_world(u, v, so)
        res = ik.solve(target, spray_dir, cfg.tool, seed=q_prev, max_iter=60 if q_prev else 200)
        since_restart += 1
        if q_prev is not None and (res.pos_error > pos_tol or res.angle_error > ang_tol) \
                and (prev_reached or since_restart >= 10):
            # Warm start failed: try every seed, but only when we just lost the
            # path or every 10th sample while lost (keeps unreachable runs fast).
            since_restart = 0
            fresh = ik.solve(target, spray_dir, cfg.tool, max_iter=80)
            if fresh.pos_error + 0.01 * fresh.angle_error < res.pos_error + 0.01 * res.angle_error - 1e-6:
                res = fresh
        q = res.q
        frames = link_frames(q)
        head = frames[-1]
        tip = apply(head, cfg.tool.tip_local())
        d = rotate(head, cfg.tool.axis_local())
        tof_origin = apply(head, cfg.tool.tof_local())

        hit = canvas.ray_hit(tip, d)
        tof = canvas.ray_hit(tof_origin, d)
        tof_reading = None
        if tof is not None and canvas.contains(tof[1], tof[2]):
            tof_reading = tof[0] + (rng.gauss(0.0, cfg.tof_noise_mm) if cfg.tof_noise_mm > 0 else 0.0)
        on_panel = hit is not None and canvas.contains(hit[1], hit[2])
        gate_ok = (tof_reading is not None and cfg.gate_min_mm - 1e-3 <= tof_reading <= cfg.gate_max_mm + 1e-3 and on_panel)
        wants_paint = s["air"] and s["needle"] > 0
        reached = res.pos_error <= pos_tol and res.angle_error <= ang_tol
        samples.append({
            "t": s["t"],
            "phase": s["phase"],
            "stroke": s["stroke"],
            "target_uvs": [round(u, 3), round(v, 3), round(so, 3)],
            "q": [round(a, 6) for a in q],
            "tip": [round(c, 6) for c in tip],
            "dir": [round(c, 6) for c in d],
            "skeleton": [[round(c, 5) for c in p] for p in skeleton_points(q, cfg.tool)],
            "hit_uv": [round(hit[1], 3), round(hit[2], 3)] if hit else None,
            "standoff_actual_mm": round(hit[0], 3) if hit else None,
            "tof_mm": round(tof_reading, 3) if tof_reading is not None else None,
            "pos_error_mm": round(res.pos_error * 1000.0, 4),
            "angle_error_deg": round(math.degrees(res.angle_error), 4),
            "reached": reached,
            "air": s["air"],
            "needle": s["needle"],
            "gate_ok": gate_ok,
            "painting": bool(wants_paint and gate_ok),
            "blocked": bool(wants_paint and not gate_ok),
            "spot_mm": round(cfg.spray_width_ratio * hit[0], 3) if hit else None,
        })
        q_prev = q
        prev_reached = reached

    summary, warnings = _summarise(cfg, samples)
    u_ax, v_ax, n_ax = canvas.axes()
    w, h = canvas.width_mm / 2, canvas.height_mm / 2
    corners = [canvas.to_world(a, b) for a, b in ((-w, -h), (w, -h), (w, h), (-w, h))]
    return {
        "version": 1,
        "config": cfg.to_dict(),
        "assumptions": [{"item": a, "basis": b, "kind": k} for a, b, k in ASSUMPTIONS],
        "joints": [{"name": j.name, "lower": j.lower, "upper": j.upper} for j in ARM_JOINTS],
        "canvas": {"corners": corners, "u": u_ax, "v": v_ax, "n": n_ax,
                   "width_mm": canvas.width_mm, "height_mm": canvas.height_mm},
        "strokes": paths.build(cfg.shape, cfg.standoff_mm),
        "samples": samples,
        "summary": summary,
        "warnings": warnings,
    }


def _summarise(cfg: SimConfig, samples: List[Dict[str, Any]]):
    stroke = [s for s in samples if s["phase"] == "stroke"]
    sprayed = [s for s in samples if s["air"] and s["needle"] > 0]
    max_speed = [0.0] * 5
    jumps = 0
    for a, b in zip(samples, samples[1:]):
        for j in range(5):
            dq = abs(b["q"][j] - a["q"][j])
            max_speed[j] = max(max_speed[j], dq / cfg.dt_s)
            if dq > BRANCH_JUMP_RAD:
                jumps += 1
    margins = [min(min(s["q"][j] - jt.lower, jt.upper - s["q"][j]) for s in samples) for j, jt in enumerate(ARM_JOINTS)]
    actual = [s["standoff_actual_mm"] for s in stroke if s["standoff_actual_mm"] is not None]
    # Clearance of the arm's joints (not the nozzle tip) above the panel plane,
    # counted only where the joint is over the panel; and above the table (z = 0).
    clearance = None
    table = None
    for smp in samples:
        for p in smp["skeleton"][2:-1]:
            u, v, h = cfg.canvas.to_canvas(tuple(p))
            if cfg.canvas.contains(u, v):
                clearance = h if clearance is None else min(clearance, h)
            table = p[2] * 1000.0 if table is None else min(table, p[2] * 1000.0)
    summary = {
        "duration_s": round(samples[-1]["t"] + cfg.dt_s, 3) if samples else 0.0,
        "samples": len(samples),
        "stroke_samples": len(stroke),
        "unreached_stroke_samples": sum(1 for s in stroke if not s["reached"]),
        "unreached_samples": sum(1 for s in samples if not s["reached"]),
        "blocked_spray_samples": sum(1 for s in sprayed if s["blocked"]),
        "painting_samples": sum(1 for s in sprayed if s["painting"]),
        "max_pos_error_mm": round(max((s["pos_error_mm"] for s in stroke), default=0.0), 3),
        "max_angle_error_deg": round(max((s["angle_error_deg"] for s in stroke), default=0.0), 3),
        "standoff_actual_min_mm": round(min(actual), 2) if actual else None,
        "standoff_actual_max_mm": round(max(actual), 2) if actual else None,
        "max_joint_speed_rad_s": {JOINT_NAMES[j]: round(max_speed[j], 3) for j in range(5)},
        "min_joint_margin_deg": {JOINT_NAMES[j]: round(math.degrees(margins[j]), 2) for j in range(5)},
        "branch_jumps": jumps,
        "min_joint_clearance_over_panel_mm": round(clearance, 1) if clearance is not None else None,
        "min_joint_height_above_table_mm": round(table, 1) if table is not None else None,
    }

    warnings: List[str] = []
    if summary["unreached_stroke_samples"]:
        pct = 100.0 * summary["unreached_stroke_samples"] / max(1, len(stroke))
        warnings.append(f"{pct:.0f}% of the stroke is outside what the arm can reach with the nozzle square to the panel "
                        f"(worst miss {summary['max_pos_error_mm']} mm, {summary['max_angle_error_deg']} deg). "
                        "Move the shape, the panel or the standoff.")
    standoffs = sorted({round(s["target_uvs"][2], 3) for s in stroke})
    below_gate = [x for x in standoffs if x < cfg.gate_min_mm]
    if below_gate:
        warnings.append(f"Standoff {', '.join(f'{x:g}' for x in below_gate)} mm is inside the plan's 2-8 cm painting range "
                        f"but below its {cfg.gate_min_mm:g} mm spray gate, so the gate blocks it. The plan needs to settle "
                        "which limit wins.")
    outside_paint = [x for x in standoffs if not cfg.paint_range_min_mm <= x <= cfg.paint_range_max_mm]
    if outside_paint:
        warnings.append(f"Standoff {', '.join(f'{x:g}' for x in outside_paint)} mm is outside the plan's "
                        f"{cfg.paint_range_min_mm:g}-{cfg.paint_range_max_mm:g} mm airbrush range.")
    blocked_other = summary["blocked_spray_samples"] - sum(
        1 for s in sprayed if s["blocked"] and s["target_uvs"][2] < cfg.gate_min_mm)
    if blocked_other > 0:
        warnings.append(f"The spray gate blocked {blocked_other} other spray samples (ToF off the panel or out of range).")
    fast = {k: v for k, v in summary["max_joint_speed_rad_s"].items() if v > cfg.joint_speed_limit_rad_s}
    if fast:
        worst = max(fast.values())
        warnings.append(f"Joint speed reaches {worst:.2f} rad/s ({', '.join(fast)}), above the "
                        f"{cfg.joint_speed_limit_rad_s:g} rad/s cap. Try about "
                        f"{cfg.speed_mm_s * cfg.joint_speed_limit_rad_s / worst:.0f} mm/s.")
    near = [k for k, m in summary["min_joint_margin_deg"].items() if m < math.degrees(NEAR_LIMIT_RAD)]
    if near:
        warnings.append(f"Joint at or within 3 deg of its limit: {', '.join(near)}.")
    if jumps:
        warnings.append(f"The IK switched arm configuration {jumps} time(s) mid-path (sudden joint jump).")
    if (clearance is not None and clearance < 10.0) or (table is not None and table < 0.0):
        warnings.append("An arm joint comes within 10 mm of the panel or below the table. The sim checks joint points "
                        "only, not link or housing shapes, so treat this as a likely collision.")
    off = [s for s in stroke if not cfg.canvas.contains(s["target_uvs"][0], s["target_uvs"][1])]
    if off:
        warnings.append(f"{len(off)} stroke samples are off the panel.")
    return summary, warnings


def reach_map(cfg: SimConfig, step_mm: float = 20.0) -> Dict[str, Any]:
    """Which points of the panel the nozzle can reach, square to the panel, at
    cfg.standoff_mm. Status per cell: 2 = reached within tolerance, 1 = close
    (within 3 mm and 10 deg), 0 = no."""
    canvas = cfg.canvas
    _, _, n = canvas.axes()
    spray_dir = tuple(-c for c in n)
    nu = int(canvas.width_mm // step_mm) + 1
    nv = int(canvas.height_mm // step_mm) + 1
    us = [-canvas.width_mm / 2 + i * canvas.width_mm / (nu - 1) for i in range(nu)]
    vs = [-canvas.height_mm / 2 + j * canvas.height_mm / (nv - 1) for j in range(nv)]
    pos_tol, ang_tol = cfg.pos_tol_mm / 1000.0, math.radians(cfg.angle_tol_deg)
    grid = [[0] * nu for _ in range(nv)]
    q_prev = None
    for j, v in enumerate(vs):
        order = range(nu) if j % 2 == 0 else range(nu - 1, -1, -1)  # serpentine for warm starts
        for i in order:
            target = canvas.to_world(us[i], v, cfg.standoff_mm)
            res = None
            if q_prev is not None:
                res = ik.solve(target, spray_dir, cfg.tool, seed=q_prev, max_iter=40)
            if res is None or res.pos_error > pos_tol or res.angle_error > ang_tol:
                for s in ik.SEEDS[:4]:
                    r = ik.solve(target, spray_dir, cfg.tool, seed=s, max_iter=80)
                    if res is None or r.pos_error + 0.01 * r.angle_error < res.pos_error + 0.01 * res.angle_error:
                        res = r
                    if res.pos_error <= pos_tol and res.angle_error <= ang_tol:
                        break
            if res.pos_error <= pos_tol and res.angle_error <= ang_tol:
                grid[j][i] = 2
                q_prev = res.q
            elif res.pos_error <= 0.003 and res.angle_error <= math.radians(10):
                grid[j][i] = 1
    return {"u_mm": us, "v_mm": vs, "status": grid, "standoff_mm": cfg.standoff_mm, "step_mm": step_mm}
