# Lessons

Things that cost effort to learn and cannot be read from the code: bugs, surprises, decisions and why-nots. Read this before you change the area it mentions. Add an entry in the same commit as the fix that taught it, and delete entries that stop being true. Record only what actually happened; never add a lesson, a measurement or a test result that did not occur.

Format: date, area, what happened, how it was found, the rule.

Open design questions are not lessons; they stay in `AGENTS.md` (Rules, item 4) and `docs/TASKS.md` until the owners decide them.

## 2026-10-19 · tests · The URDF cross-check skips silently without the submodule

- **What:** `test_embedded_joints_match_urdf` in `software/sim/tests/test_kinematics.py` is decorated with `skipUnless(URDF.exists())`. Without `git submodule update --init`, unittest still prints `OK` (with `skipped=1`), so a run can look green while the embedded joint table is never compared with the upstream URDF.
- **Found:** reading the test while setting up CI.
- **Rule:** `tools/verify.sh` fails if the URDF file is missing or if any test is skipped, and the CI workflow checks out submodules.

## 2026-10-19 · tooling · blast-check `--changed` checks nothing on a clean checkout

- **What:** `tools/blast-check.sh --changed` lists files with `git diff --name-only HEAD`, which only sees uncommitted changes. On a fresh checkout, which is what CI has, the list is empty, so the contract check passes without checking any file. The orphan, wiring and `.desc` checks still scan the whole tree. Reproduced locally on a clean tree on this date.
- **Found:** running the script locally in both modes before adding it.
- **Rule:** treat the advisory PR comment from `blast-check.yml` as weak evidence for contracts. The blocking gate runs `blast-check.sh` over the whole of `software/sim` in strict mode inside `tools/verify.sh`.

## 2026-10-19 · CI · The advisory check is skipped on the PR that adds it

- **What:** `blast-check.yml` loads `tools/blast-check.sh` from the PR's base branch, on purpose, so a PR cannot change the checker that judges it. On any PR whose base does not have the script yet, including the one that adds it, the check skips its steps.
- **Found:** reading the workflow before adding it.
- **Rule:** expect no blast-check comment until the script is on the base branch. `sim-tests.yml` runs from the PR branch, so it does run on that PR.
