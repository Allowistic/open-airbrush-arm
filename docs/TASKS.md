# Task list

Clearly scoped tasks for people and agents. Read `AGENTS.md` first. Each task says why it matters, what it needs, what to do and how to tell it is done. Update the status line in the same PR that does the work.

Status key: **open**, **blocked** (waiting on a measurement or decision), **in progress** (with branch), **done**.

## Simulation

### T1. Set the real nozzle and sensor position
- **Status:** blocked (needs the head housing CAD or a caliper measurement)
- **Why:** the nozzle depth (98 mm past the wrist-roll joint) and ToF position (18 mm beside the nozzle) are placeholders. Reach and wrist-limit results depend on them.
- **Inputs:** head housing CAD in `hardware/cad/` or measured distances from the wrist-roll joint to the nozzle tip and to the ToF window.
- **Do:** update `NozzleTool` defaults in `so101.py`, including any lateral offset or angle from the roll axis. Change the two rows in `ASSUMPTIONS` to `source` with the CAD file or measurement. Rerun the reach numbers in `software/sim/README.md` ("What the first runs show").
- **Done when:** tests pass, the README numbers match a fresh run, and the PR lists the old and new reach percentages at 40 mm.

### T2. Settle the spray-gate vs painting-range conflict
- **Status:** blocked (needs a human decision)
- **Why:** Build Plan v3 gates spray at a 3–25 cm ToF reading but maps strokes to a 2–8 cm airbrush range. The sim blocks everything under 30 mm.
- **Inputs:** a decision from the project owners, and ideally the VL53L4CX's usable minimum range on the real bracket.
- **Do:** update `docs/BUILD_PLAN.md`, then `gate_min_mm` / `paint_range_*` in `config.py` and the `ASSUMPTIONS` rows. Adjust `tests/test_simulate.py` (`test_gate_blocks_below_30mm_and_says_so`) to the new limit.
- **Done when:** plan and sim agree, and the warning text no longer reports a conflict for standoffs inside the agreed range.

### T3. Calibrate spot size against standoff
- **Status:** blocked (needs the Stage 1 bench test)
- **Why:** the spot diameter is 0.25 × standoff, a guess.
- **Inputs:** a real `standoff_ladder` test card: run `python3 -m airbrush_sim run --shape standoff_ladder --csv ladder.csv`, paint it with water or thin paint at a fixed needle setting, and measure line widths at each standoff (photo with a ruler is fine).
- **Do:** replace `spray_width_ratio` with a small measured table (standoff mm to line width mm, linear interpolation) in `config.py`, store the raw measurements in `docs/` with the date, pressure, paint and needle setting, and change the `ASSUMPTIONS` row to `source`.
- **Done when:** the viewer's spot sizes match the measured table and a test checks the interpolation.

### T4. Load the panel position from registration
- **Status:** open (format), blocked (real data waits on Stage 3)
- **Why:** the panel pose (centre 230 mm in front of the base, flat) is assumed. Stage 3 registers the panel by touching its four corners.
- **Do:** add `--canvas-file panel.json` to the CLI and server with this format: `{"corners_m": [[x,y,z] x4 in base_link, order: near-left, near-right, far-right, far-left], "source": "...", "date": "YYYY-MM-DD"}`. Fit the panel centre, axes, size and tilt from the corners (allow a small non-planarity, warn above 2 mm). Keep the current defaults when no file is given.
- **Done when:** a test round-trips a known panel through the file, and the README documents the format.

### T5. Model air lag and the end-of-stroke puff
- **Status:** open (model), needs Stage 1 numbers to be useful
- **Why:** the air volume between the base valve and the nozzle delays spray start and stop and puffs at the end (Build Plan, Gotcha 4).
- **Do:** add `air_start_delay_s` and `air_stop_delay_s` (default 0) to `SimConfig`; paint should start and stop that much after the commanded valve change. Show the delayed spray in the chart. Do not invent default values; leave them at 0 until measured.
- **Done when:** with non-zero delays the paint trail visibly shifts in the viewer and a test checks the shift.

### T6. Check arm parts against the panel and table
- **Status:** open
- **Why:** the sim only checks joint points for clearance. The links and the head housing can still hit the panel.
- **Do:** approximate each link and the head as capsules or boxes (dimensions from the upstream STEP files or measured), and check them against the panel and table each sample. Label the shapes as approximations.
- **Done when:** a pose known to collide is flagged in a test and the warning names the link.

### T7. Head layout study for tilted panels
- **Status:** open
- **Why:** with the nozzle on the wrist-roll axis the spray stays in the arm's vertical plane, so the arm can stay square to a tilted panel only along its centre line. An easel (to keep the gravity cup level) needs either tolerance for nozzle tilt or a different head layout.
- **Do:** add an optional nozzle angle relative to the roll axis in `NozzleTool` and compare reach maps at 0, 10 and 20 degree panel tilt for 0, 30 and 45 degree nozzle angles. Write the table into `docs/` with the assumptions.
- **Done when:** the comparison table exists and the default behaviour is unchanged.

### T8. Run the tests in CI
- **Status:** in progress (`process/blast-radius-gate`)
- **Do:** add `.github/workflows/sim-tests.yml` running `git submodule update --init` and `python3 -m unittest discover -s tests` in `software/sim` on Python 3.9 and 3.12. Pushing a workflow file needs a token with the `workflow` permission. (The workflow runs `tools/verify.sh`, which does both plus a headless `--check` run and the contract check.)
- **Done when:** the workflow runs green on a PR.

## Toward the real arm

### T9. Map simulated joint angles to the calibrated SO-101
- **Status:** blocked (needs Stage 0: arm built and calibrated in LeRobot)
- **Why:** the CSV export is in URDF joint angles, not LeRobot `so101_follower` positions.
- **Do:** write a converter from the CSV to LeRobot follower positions using the arm's calibration file, with a dry-run printout. Do not drive the arm from it until T10's limits exist.
- **Done when:** for three poses the converter output matches the arm's reported positions within a stated tolerance, measured on the real arm.

### T10. `paint_service.py` with a simulator backend
- **Status:** open
- **Why:** the plan's control layer (`move_to`, `set_distance`, `spray`, `stroke`, `status`, `stop`) can be built and tested against the simulator before hardware exists.
- **Do:** create `software/paint_service/` exposing those calls over a simple local API, backed by `airbrush_sim`. Implement the plan's limits in the service: workspace box, speed cap, spray gate, 500 ms watchdog (needle home + valve closed) and maximum spray time. Note in the README that the controller firmware must also close the valve on its own if the PC goes quiet.
- **Done when:** tests cover each limit tripping, including the watchdog.

## Not now

Colour switching and purging, remote paint feed, ML policy training, the Quest capture pipeline and large surfaces (murals, car panels) are later stages. Add tasks for them here when the project owners decide to start them.
