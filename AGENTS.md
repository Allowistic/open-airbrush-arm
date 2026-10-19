# Notes for agents and new contributors

Read this first if you are an AI agent (or a person) picking up work in this repo. It says what exists, how to run and test it, the rules to follow, and where the next tasks are.

## What this repo is

Open Airbrush Arm: an SO-101 desktop arm with its gripper replaced by an airbrush head, painting on an A3 panel (v1). Later stages add Meta Quest motion capture of artists. The full plan is `docs/BUILD_PLAN.md` (Build Plan v3). The parts list is `hardware/bom/BOM.csv`.

Current state (October 2026):

| Area | State |
|---|---|
| `docs/BUILD_PLAN.md`, `hardware/bom/BOM.csv` | Written. The plan is the source of truth for design decisions. |
| `software/sim/` | **Working.** Kinematic simulator with a browser viewer, CLI and tests. See `software/sim/README.md`. |
| `hardware/cad`, `hardware/stl`, `firmware/`, `mocap/`, rest of `software/` | Placeholders. Nothing built yet. |
| `third_party/SO-ARM100` | Upstream arm, git submodule (Apache-2.0). Run `git submodule update --init`. |

No part of this has been tested on hardware. Nobody has measured the head, the nozzle position, spray width or air lag yet.

## Set up and test

```bash
git clone https://github.com/Allowistic/open-airbrush-arm.git
cd open-airbrush-arm
git submodule update --init            # needed for the URDF cross-check test
cd software/sim
python3 -m unittest discover -s tests -v    # ~15 s, all should pass
python3 -m airbrush_sim run --shape circle  # quick headless check
python3 -m airbrush_sim serve               # browser viewer at http://127.0.0.1:8765
```

Python 3.9+, standard library only. There is no CI yet (task T8), so run the tests yourself before you push and paste the result in the PR.

## Rules

1. **Keep the simulator dependency-free** (standard library Python, plain JavaScript in the viewer). If a task truly needs a package, say why in the PR and keep it optional.
2. **Every number needs a source or an "assumption" label.** Put sourced and assumed settings in `software/sim/airbrush_sim/config.py`, and add or update the matching row in `ASSUMPTIONS` (it is shown in the viewer and exported in the JSON). When a measurement replaces an assumption, change its kind to `source` and cite the measurement or CAD file.
3. **Never claim hardware validation the repo does not have.** The spray cone is idealised. Sub-millimetre errors are solver precision, not arm accuracy.
4. **Do not silently resolve open design questions.** Flag them and leave the decision to the humans. Current ones:
   - Spray gate (3–25 cm) vs painting range (2–8 cm) conflict below 3 cm (Build Plan, Software vs Stage 2).
   - Paint type, water-based or solvent, and where it runs (Build Plan open question 3).
   - Airbrush-only v1 vs spray cans (the plan keeps cans out of v1; SO-101 payload).
   - Gravity-cup orientation when the nozzle points down at a flat panel.
5. **Do not copy upstream SO-ARM100 files** into this repo; reference the submodule (see `CONTRIBUTING.md`). Embedding a few cited numbers, as `so101.py` does, is fine, and a test checks them against the URDF.
6. **Safety-relevant changes** (air pressure, valve, motion or speed limits, spray gate, watchdog) must be called out in the PR description.
7. **Small PRs on a branch**, one task per PR, with how you tested. Name branches `<area>/<short-name>`, e.g. `sim/nozzle-frame`.
8. **Out of scope for now:** colour switching and purging, ML policy training, mural or car-panel scale. They are later goals; do not build them until a task here says so.

## How the simulator fits together

`software/sim/airbrush_sim/`:

- `so101.py`: URDF joint table, forward kinematics, `NozzleTool` (where the nozzle and ToF sit on the head).
- `ik.py`: damped least-squares IK for nozzle position + spray direction (5 constraints, 5 joints).
- `config.py`: `SimConfig`, `Canvas` (panel pose and u/v coordinates), `Shape`, `ASSUMPTIONS`, parameter parsing.
- `paths.py`: shapes as lists of strokes of `(u_mm, v_mm, standoff_mm)` waypoints.
- `simulate.py`: builds the timed spray sequence, solves every sample, computes the achieved standoff, ToF reading, spray gate, warnings and the reach map.
- `server.py` + `web/index.html`: local viewer; `__main__.py`: CLI.

Conventions: the base frame is the URDF `base_link` (metres, z up, x forward). Panel coordinates are millimetres from the panel centre, u to the right seen from behind the arm, v away from the arm. Joint angles are URDF radians (degrees in the CSV), not LeRobot motor units.

To add a shape: add a generator in `paths.py`, register it in `paths.build` and `config.SHAPES`, add the option to the `<select id="shape">` in `web/index.html`, and add a geometry test in `tests/test_paths.py`.

The result JSON (`simulate()` return value, also `--json`) has `config`, `assumptions`, `joints`, `canvas`, `strokes`, `samples` (one per 20 ms: phase, target, joint angles, tip pose, hit point, actual standoff, ToF, gate, errors, painting/blocked) and `summary` + `warnings`. Keep these keys stable or bump `version`.

## Picking up work

Tasks are in `docs/TASKS.md`, each with its inputs, what to do and when it is done. Take the first open task whose dependencies are met, set its status to "in progress" with your branch name in your PR, and to "done" when it merges. If a task needs a measurement or a decision that does not exist yet, stop and ask rather than inventing the number.
