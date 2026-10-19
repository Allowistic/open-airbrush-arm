# Airbrush arm simulator

A kinematic simulator for the v1 desktop unit: the SO-101 arm with the airbrush head, painting simple shapes on an A3 panel. Use it to try nozzle distance, shape size and placement, speed, and panel position before the arm is built, and to have a scripted baseline to compare against later.

It answers three questions for a path:

1. Can the arm reach every point with the nozzle square to the panel, inside the URDF joint limits?
2. Does the nozzle hold the standoff you asked for, and would the plan's spray gate let it spray there?
3. Do the joints stay under the bring-up speed cap?

It does **not** model paint. The spray is drawn as an idealised cone (spot diameter = 0.25 × standoff, a placeholder), and nothing here has been checked against the real arm, a real airbrush or a real sensor.

## Run it

Python 3.9 or newer. No packages to install; it uses only the standard library.

```bash
git submodule update --init          # optional: lets the tests check the geometry against the upstream URDF
cd software/sim
python3 -m airbrush_sim serve        # opens http://127.0.0.1:8765 in your browser
```

The viewer has:

- **Arm and panel (3D):** the SO-101 stick model from the URDF, the airbrush head in orange, the panel, the planned path, the spray cone and the paint so far. Drag to orbit, scroll to zoom, double-click to reset.
- **Panel from above:** the reach map (green: reachable square-on; amber: within 3 mm and 10 degrees), the planned path, the paint and blocked spray in red.
- **Standoff over time:** commanded, actual and simulated ToF reading, against the spray gate band and the plan's painting range.
- **Playback, checks and assumptions:** joint angles and errors at each moment, the warnings for the run, and every assumption with its source.

Change any setting and it reruns. The reach map takes a few seconds.

Without a browser, or for scripts and CI:

```bash
python3 -m airbrush_sim run --shape circle --size 80 --standoff 40
python3 -m airbrush_sim run --shape standoff_ladder --reach
python3 -m airbrush_sim run --shape square --json out.json --csv out.csv --html out.html
python3 -m airbrush_sim run --shape line --standoff 20 --check   # exits 1 if anything is unreached or blocked
python3 -m airbrush_sim run --help
```

`--html` writes one self-contained file with that run baked in. It opens in any browser with no server, for playback only, so it is handy for sharing a result.

`--csv` writes the joint trajectory in URDF joint angles (degrees). These are **not** LeRobot motor positions; mapping them to a calibrated arm is a separate task (see `docs/TASKS.md`).

## Shapes

| Shape | Size means | Notes |
|---|---|---|
| `circle` | diameter | one closed stroke |
| `square` | side | axis-aligned, one stroke |
| `triangle` | side | equilateral, one stroke |
| `line` | length | left to right |
| `standoff_ladder` | line length | six lines at 20, 30, 40, 50, 60 and 80 mm standoff, 20 mm apart. The distance test card: paint it for real in Stage 1 to calibrate spot size against distance. |

Shapes are placed by their centre in panel coordinates: `u` is millimetres right of the panel centre (seen from behind the arm) and `v` is millimetres away from the arm. Each stroke runs: hover, approach, air on, needle open and move, needle closed, air off, retract. That is the order the build plan gives.

## Tests

```bash
cd software/sim
python3 -m unittest discover -s tests -v
```

About 15 seconds, 30 tests. They check the embedded joint table against the upstream URDF (skipped if the submodule is not checked out), forward and inverse kinematics round trips, the shape geometry, that the default circle is fully reached at a steady 40 mm, the spray sequence order, the spray gate, speed and reach warnings, determinism, the CLI outputs and the web API.

## What it assumes

| Item | Basis |
|---|---|
| Arm geometry and joint limits | Upstream `so101_new_calib.urdf` (submodule commit a758567), embedded in `airbrush_sim/so101.py` and checked by a test |
| Nozzle on the wrist-roll axis, spraying away from the wrist | Build Plan v3, "For Clay" item 1 |
| Nozzle tip 98 mm past the wrist-roll joint | **Assumption.** Borrowed from the upstream gripper tip depth. Measure the real housing and set `--nozzle-depth`. |
| ToF sensor 18 mm beside the nozzle, parallel | **Assumption.** Placeholder until the bracket exists. |
| A3 panel (420 × 297 mm), flat, centre 230 mm in front of the base, 5 mm thick | Size from the plan; position is an **assumption** until arm-to-canvas registration (Stage 3) |
| Spray gate: ToF reading 30 to 250 mm and the spray point on the panel | Build Plan v3, Software limits ("3–25 cm") |
| Painting range 20 to 80 mm | Build Plan v3, Stage 2 scaling ("2–8 cm") |
| Spot diameter = 0.25 × standoff | **Assumption**, uncalibrated |
| Joint speed cap 2 rad/s | **Assumption**: 20% of the URDF velocity value, following the plan's ~20% bring-up cap. The URDF value is generic, not a servo spec. |

The plan's two distance ranges disagree below 30 mm. The simulator does not pick a winner: it applies the 30 mm gate, blocks the spray there, and says so in the warnings. Settle it in the plan, then change `gate_min_mm` in `config.py` (or `--gate-min`).

## What it leaves out

- Dynamics, gravity sag, servo backlash and compliance. The real arm is mm-level with backlash (Build Plan, Gotcha 3), so sub-millimetre numbers here are solver precision, not arm accuracy.
- Payload and hose drag at the wrist.
- Air lag and the end-of-stroke puff from the air volume between the base valve and the nozzle (Gotcha 4).
- Real paint: flow vs needle position, overspray, build-up, drips, the paint cup's orientation.
- The real VL53L4CX sensor's behaviour (field of view, minimum range, noise model). Optional Gaussian noise only.
- Collisions. It only warns if a joint point comes within 10 mm of the panel or below the table; link and housing shapes are not modelled.
- The 500 ms watchdog, the workspace box and the maximum spray time from the plan's limits. Those belong in `paint_service.py` and the controller firmware.

## What the first runs show

These come from the model and its assumptions above, so treat them as things to check on the real arm, not results.

- **A flat A3 panel is only partly reachable square-on.** At 40 mm standoff, 56% of the panel is reachable, from the near edge to about 64 mm past the centre. The far third, more than about 29 cm from the base origin, is out. At 80 mm standoff it drops to 24%. Start shapes in the near half (the default circle sits at v = -40 mm).
- **Pointing straight down puts the wrist near its limit.** On the default circle the wrist flex runs from 76 to 81 degrees while painting and reaches about 89 degrees while hovering 30 mm higher, against a 95 degree limit. Higher standoffs and points closer to the base push it further. A longer or shorter head changes that, so measure the real nozzle depth early.
- **Tilting the panel costs square-on reach fast.** Because the nozzle is on the wrist-roll axis, the spray direction always stays in the arm's vertical plane. The arm can only stay exactly square to a tilted panel along its centre line: at 10 degrees of tilt, 11% of the panel is reachable square-on, but 64% more is within 10 degrees and 3 mm. So a slight tilt (to keep the gravity cup level) may be fine if a few degrees of nozzle tilt are acceptable. A steep easel is not, unless the head is redesigned (for example, a nozzle offset from the roll axis so the roll joint adds a pointing direction).
- **Standoffs under 30 mm are blocked** by the plan's own spray gate, as above.

## Code map

| File | What |
|---|---|
| `airbrush_sim/so101.py` | Joint table from the URDF, forward kinematics, the nozzle tool frame, a URDF parser for checks |
| `airbrush_sim/ik.py` | Damped least-squares IK for nozzle position + direction |
| `airbrush_sim/config.py` | All settings, panel geometry, the assumptions list, parameter parsing and validation |
| `airbrush_sim/paths.py` | Shape generators and resampling |
| `airbrush_sim/simulate.py` | Timeline (spray sequence), per-sample IK, ToF, spray gate, summary and warnings, reach map |
| `airbrush_sim/server.py` | Local web server and the static HTML export |
| `airbrush_sim/web/index.html` | The viewer (plain JavaScript and canvas, no libraries) |
| `airbrush_sim/__main__.py` | Command line |
| `tests/` | `unittest` tests |

All maths runs in Python; the browser only draws. So the viewer, the CLI and the tests always agree.
