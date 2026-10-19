"""Command line: ``python3 -m airbrush_sim {serve,run}``.

Input: command-line arguments.
Output: printed checks, optional JSON, CSV and HTML files, and the exit code.
Must never: exit 0 under --check when a stroke point is unreached or spray is blocked.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

from .config import SHAPES, config_from_params
from .simulate import reach_map, simulate
from .so101 import JOINT_NAMES


def _add_shape_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--shape", choices=SHAPES, default="circle")
    p.add_argument("--size", type=float, help="mm: circle diameter, polygon side, line length (default 80)")
    p.add_argument("--u", type=float, help="shape centre, mm right of the panel centre (default 0)")
    p.add_argument("--v", type=float, help="shape centre, mm from the panel centre away from the arm (default -40)")
    p.add_argument("--standoff", type=float, help="nozzle-to-panel distance in mm (default 40)")
    p.add_argument("--speed", type=float, help="tool speed in mm/s (default 40)")
    p.add_argument("--tilt", type=float, help="panel tilt in degrees, 0 = flat (default 0)")
    p.add_argument("--canvas-x", dest="canvas_x", type=float, help="panel centre x in mm from the base (default 230)")
    p.add_argument("--canvas-y", dest="canvas_y", type=float, help="panel centre y in mm (default 0)")
    p.add_argument("--canvas-z", dest="canvas_z", type=float, help="panel surface height in mm (default 5)")
    p.add_argument("--nozzle-depth", dest="nozzle_depth", type=float, help="nozzle tip past the wrist-roll joint, mm (default 98)")
    p.add_argument("--spray-ratio", dest="spray_ratio", type=float, help="spot diameter / standoff (default 0.25, uncalibrated)")
    p.add_argument("--gate-min", dest="gate_min", type=float, help="spray gate minimum ToF reading, mm (default 30)")
    p.add_argument("--gate-max", dest="gate_max", type=float, help="spray gate maximum ToF reading, mm (default 250)")
    p.add_argument("--tof-noise", dest="tof_noise", type=float, help="simulated ToF noise, mm 1-sigma (default 0)")


def _params(args: argparse.Namespace) -> dict:
    keys = ("shape", "size", "u", "v", "standoff", "speed", "tilt", "canvas_x", "canvas_y", "canvas_z",
            "nozzle_depth", "spray_ratio", "gate_min", "gate_max", "tof_noise")
    return {k: str(getattr(args, k)) for k in keys if getattr(args, k, None) is not None}


def write_csv(result: dict, path: Path) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "phase", "air", "needle"] + [f"{n}_deg" for n in JOINT_NAMES]
                   + ["target_u_mm", "target_v_mm", "target_standoff_mm", "standoff_actual_mm", "tof_mm",
                      "reached", "painting", "blocked"])
        for s in result["samples"]:
            w.writerow([s["t"], s["phase"], int(s["air"]), s["needle"]]
                       + [round(math.degrees(a), 4) for a in s["q"]]
                       + s["target_uvs"] + [s["standoff_actual_mm"], s["tof_mm"],
                                            int(s["reached"]), int(s["painting"]), int(s["blocked"])])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python3 -m airbrush_sim",
                                 description="Kinematic simulation of the SO-101 airbrush arm (idealised spray).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("serve", help="open the interactive viewer in a browser")
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--no-browser", action="store_true")

    rp = sub.add_parser("run", help="simulate one shape and print the checks")
    _add_shape_args(rp)
    rp.add_argument("--json", type=Path, help="write the full result as JSON")
    rp.add_argument("--csv", type=Path, help="write the joint trajectory as CSV (URDF joint angles, degrees)")
    rp.add_argument("--html", type=Path, help="write a self-contained viewer with this run (playback only)")
    rp.add_argument("--reach", action="store_true", help="also compute the panel reach map (slower)")
    rp.add_argument("--check", action="store_true",
                    help="exit 1 if any stroke point is unreached or any spray is blocked by the gate")

    args = ap.parse_args(argv)
    if args.cmd == "serve":
        from .server import serve
        serve(args.host, args.port, not args.no_browser)
        return 0

    try:
        cfg = config_from_params(_params(args))
    except ValueError as exc:
        ap.error(str(exc))
    result = simulate(cfg)
    reach = reach_map(cfg) if (args.reach or args.html) else None
    s = result["summary"]
    print(f"{cfg.shape.kind}: {cfg.shape.size_mm:g} mm at ({cfg.shape.center_mm[0]:g}, {cfg.shape.center_mm[1]:g}) mm, "
          f"standoff {cfg.standoff_mm:g} mm, {cfg.speed_mm_s:g} mm/s, panel tilt {cfg.canvas.tilt_deg:g} deg")
    print(f"  duration {s['duration_s']} s, {s['stroke_samples']} stroke samples, "
          f"{s['unreached_stroke_samples']} unreached, {s['blocked_spray_samples']} spray samples blocked by the gate")
    print(f"  worst miss {s['max_pos_error_mm']} mm / {s['max_angle_error_deg']} deg; "
          f"actual standoff {s['standoff_actual_min_mm']}-{s['standoff_actual_max_mm']} mm")
    print("  max joint speed rad/s: " + ", ".join(f"{k} {v}" for k, v in s["max_joint_speed_rad_s"].items()))
    print("  min joint margin deg:  " + ", ".join(f"{k} {v}" for k, v in s["min_joint_margin_deg"].items()))
    if reach:
        cells = [c for row in reach["status"] for c in row]
        print(f"  reach map: {100.0 * cells.count(2) / len(cells):.0f}% of the panel reachable square-on at "
              f"{cfg.standoff_mm:g} mm")
    for w in result["warnings"]:
        print("  WARNING: " + w)
    if args.json:
        args.json.write_text(json.dumps({"result": result, "reach": reach}))
    if args.csv:
        write_csv(result, args.csv)
    if args.html:
        from .server import export_html
        export_html(result, reach, args.html)
        print(f"  wrote {args.html}")
    if args.check and (s["unreached_stroke_samples"] or s["blocked_spray_samples"]):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
