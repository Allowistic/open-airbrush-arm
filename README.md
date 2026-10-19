# Open Airbrush Arm

An open-source desktop airbrush painting arm, a **Fiction Factory** project made with partner **Risk Rock**.

It starts from the open [SO-101 arm](https://github.com/TheRobotStudio/SO-ARM100) (TheRobotStudio, run through [LeRobot](https://huggingface.co/docs/lerobot/en/so101)). The gripper is swapped for a built-in airbrush head: a stripped Master G22-style body, with the gripper servo driving the needle. A solenoid switches the air, a laser distance sensor holds the standoff, a camera gives visual feedback, and an agent control layer drives it all.

**Stage 2** records artists with Meta Quest motion capture and teaches the arm to reproduce their strokes. The first session is spray-can capture with Risk Rock.

## Layout
| Path | What |
|---|---|
| `docs/` | Build plan, sources, design notes |
| `hardware/cad`, `hardware/stl`, `hardware/bom` | CAD, printable parts, bill of materials |
| `firmware/` | Controller firmware (valve, sensors) |
| `software/` | Agent control layer, LeRobot integration |
| `software/sim/` | Kinematic simulator with a browser viewer: shapes, standoff, reach ([README](software/sim/README.md)) |
| `mocap/` | Quest / WebXR capture and retargeting |
| `third_party/SO-ARM100` | Upstream SO-101 arm (git submodule, Apache-2.0) |

Get the upstream arm with `git submodule update --init`.

## Status
Early planning. See [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) and [hardware/bom/BOM.csv](hardware/bom/BOM.csv). A kinematic simulator for simple shapes and nozzle distance is in [software/sim](software/sim/README.md); nothing has been tested on hardware yet. Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), [AGENTS.md](AGENTS.md) and the task list in [docs/TASKS.md](docs/TASKS.md).

## Safety
Paint mist and solvents need ventilation and a respirator. Keep air pressure inside the airbrush's rated range, and keep hands clear of the arm while it's powered.

## License
- Code (firmware, software, mocap): [Apache-2.0](LICENSE)
- Hardware (CAD, STL, BOM, drawings under `hardware/`): [CERN-OHL-S-2.0](hardware/LICENSE)
- `third_party/SO-ARM100` keeps its own Apache-2.0 license from TheRobotStudio.

© Fiction Factory and contributors.
