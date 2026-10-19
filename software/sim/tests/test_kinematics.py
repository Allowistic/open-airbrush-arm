import math
import random
import unittest
from pathlib import Path

from airbrush_sim import ik
from airbrush_sim.so101 import (ARM_JOINTS, UPSTREAM_GRIPPER_FRAME_XYZ, NozzleTool, apply, axis_angle, link_frames,
                                load_urdf_joints, mat_mul, nozzle_pose, rpy_xyz, within_limits)

REPO = Path(__file__).resolve().parents[3]
URDF = REPO / "third_party/SO-ARM100/Simulation/SO101/so101_new_calib.urdf"


class TestUpstreamGeometry(unittest.TestCase):
    @unittest.skipUnless(URDF.exists(), "submodule not checked out (git submodule update --init)")
    def test_embedded_joints_match_urdf(self):
        real = load_urdf_joints(URDF)
        for j in ARM_JOINTS:
            r = real[j.name]
            self.assertEqual((j.parent, j.child), (r.parent, r.child))
            for a, b in zip(j.xyz + j.rpy + j.axis, r.xyz + r.rpy + r.axis):
                self.assertAlmostEqual(a, b, places=6, msg=j.name)
            self.assertAlmostEqual(j.lower, r.lower, places=5)
            self.assertAlmostEqual(j.upper, r.upper, places=5)

    def test_fast_fk_matches_generic_fk(self):
        rng = random.Random(1)
        for _ in range(100):
            q = [rng.uniform(j.lower, j.upper) for j in ARM_JOINTS]
            t = [[1.0 if i == k else 0.0 for k in range(4)] for i in range(4)]
            for j, a in zip(ARM_JOINTS, q):
                t = mat_mul(mat_mul(t, rpy_xyz(j.xyz, j.rpy)), axis_angle(j.axis, a))
            fast = link_frames(q)[-1]
            for i in range(4):
                for k in range(4):
                    self.assertAlmostEqual(fast[i][k], t[i][k], places=12)

    def test_zero_pose_reaches_forward(self):
        tip, d = nozzle_pose([0.0] * 5)
        self.assertGreater(tip[0], 0.35)  # arm stretched out along +x
        self.assertAlmostEqual(d[0], 1.0, places=3)
        # default nozzle sits on the roll axis at the upstream gripper TCP depth
        tcp = apply(link_frames([0.0] * 5)[-1], UPSTREAM_GRIPPER_FRAME_XYZ)
        self.assertLess(math.dist(tip, tcp), 0.009)

    def test_nozzle_depth_moves_tip_along_axis(self):
        q = [0.1, 0.2, 0.3, 0.4, 0.5]
        a, d = nozzle_pose(q, NozzleTool(depth=0.10))
        b, _ = nozzle_pose(q, NozzleTool(depth=0.13))
        for i in range(3):
            self.assertAlmostEqual(b[i] - a[i], 0.03 * d[i], places=9)


class TestIK(unittest.TestCase):
    def test_round_trip_from_known_poses(self):
        rng = random.Random(7)
        solved = 0
        for _ in range(25):
            q = [rng.uniform(j.lower * 0.6, j.upper * 0.6) for j in ARM_JOINTS]
            p, d = nozzle_pose(q)
            r = ik.solve(p, d, seed=[a + rng.uniform(-0.05, 0.05) for a in q])
            self.assertTrue(within_limits(r.q))
            if r.pos_error < 1e-5 and r.angle_error < 1e-4:
                solved += 1
        self.assertGreaterEqual(solved, 24)

    def test_cold_start_finds_point_over_panel(self):
        r = ik.solve((0.19, 0.0, 0.045), (0, 0, -1))
        self.assertLess(r.pos_error, 1e-4)
        self.assertLess(r.angle_error, math.radians(0.1))

    def test_out_of_reach_reports_error(self):
        r = ik.solve((0.8, 0.0, 0.05), (0, 0, -1))
        self.assertGreater(r.pos_error, 0.2)
        self.assertTrue(within_limits(r.q))


if __name__ == "__main__":
    unittest.main()
