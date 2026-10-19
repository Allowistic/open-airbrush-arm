# Input: simulate, build_timeline and reach_map with test configs.
# Output: unittest results for standoff, spray gate, warnings and reach.
# Must never: loosen a check or tolerance just to make a change pass.

import math
import unittest

from airbrush_sim.config import SimConfig, config_from_params
from airbrush_sim.simulate import build_timeline, reach_map, simulate


def cfg(**params):
    return config_from_params({k: str(v) for k, v in params.items()})


class TestDefaultCircle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = simulate(SimConfig())

    def test_reached_and_sprayed(self):
        s = self.r["summary"]
        self.assertEqual(s["unreached_samples"], 0)
        self.assertEqual(s["blocked_spray_samples"], 0)
        self.assertEqual(s["branch_jumps"], 0)
        self.assertGreater(s["painting_samples"], 0)
        self.assertEqual(self.r["warnings"], [])

    def test_standoff_held(self):
        for smp in self.r["samples"]:
            if smp["phase"] == "stroke":
                self.assertAlmostEqual(smp["standoff_actual_mm"], 40.0, delta=0.5)
                self.assertAlmostEqual(smp["tof_mm"], 40.0, delta=0.5)

    def test_paint_follows_the_circle(self):
        for smp in self.r["samples"]:
            if smp["painting"]:
                u, v = smp["hit_uv"]
                self.assertAlmostEqual(math.hypot(u - 0.0, v + 40.0), 40.0, delta=0.6)

    def test_spray_sequence_order(self):
        phases = [s["phase"] for s in self.r["samples"]]
        first = {p: phases.index(p) for p in ("approach", "air_on", "stroke", "air_off", "retract")}
        self.assertLess(first["approach"], first["air_on"])
        self.assertLess(first["air_on"], first["stroke"])
        self.assertLess(first["stroke"], first["air_off"])
        self.assertLess(first["air_off"], first["retract"])
        for s in self.r["samples"]:
            if s["phase"] in ("air_on", "air_off"):
                self.assertTrue(s["air"])
                self.assertEqual(s["needle"], 0.0)  # needle shut whenever the air is cycling
            if s["phase"] in ("hover", "travel", "approach", "retract"):
                self.assertFalse(s["air"])
                self.assertFalse(s["painting"])

    def test_joint_speed_within_cap(self):
        for v in self.r["summary"]["max_joint_speed_rad_s"].values():
            self.assertLessEqual(v, 2.0)

    def test_deterministic(self):
        self.assertEqual(simulate(SimConfig())["samples"], self.r["samples"])


class TestChecks(unittest.TestCase):
    def test_gate_blocks_below_30mm_and_says_so(self):
        r = simulate(cfg(shape="line", standoff=20, size=60))
        self.assertGreater(r["summary"]["blocked_spray_samples"], 0)
        self.assertEqual(r["summary"]["painting_samples"], 0)
        self.assertTrue(any("spray gate" in w for w in r["warnings"]))

    def test_ladder_mixes_blocked_and_painted(self):
        r = simulate(cfg(shape="standoff_ladder", size=60))
        by_standoff = {}
        for s in r["samples"]:
            if s["phase"] == "stroke":
                by_standoff.setdefault(s["target_uvs"][2], set()).add(s["painting"])
        self.assertEqual(by_standoff[20.0], {False})
        self.assertIn(True, by_standoff[40.0])

    def test_out_of_reach_shape_is_flagged(self):
        r = simulate(cfg(shape="circle", size=60, u=170, v=110))
        self.assertGreater(r["summary"]["unreached_stroke_samples"], 0)
        self.assertTrue(any("outside what the arm can reach" in w for w in r["warnings"]))

    def test_fast_path_trips_speed_cap(self):
        r = simulate(cfg(shape="line", size=120, speed=300))
        self.assertTrue(any("rad/s cap" in w for w in r["warnings"]))

    def test_tof_noise_is_seeded(self):
        a = simulate(cfg(shape="line", size=40, tof_noise=2))
        b = simulate(cfg(shape="line", size=40, tof_noise=2))
        self.assertEqual([s["tof_mm"] for s in a["samples"]], [s["tof_mm"] for s in b["samples"]])
        self.assertNotEqual({s["tof_mm"] for s in a["samples"] if s["phase"] == "stroke"}, {40.0})

    def test_bad_params_rejected(self):
        for bad in ({"standoff": "0"}, {"shape": "spiral"}, {"size": "5000"}, {"tilt": "95"}):
            with self.assertRaises(ValueError):
                config_from_params(bad)

    def test_timeline_dwell_lengths(self):
        c = SimConfig()
        t = build_timeline(c)
        self.assertEqual(sum(1 for s in t if s["phase"] == "air_on"), round(c.air_lead_s / c.dt_s))


class TestReachMap(unittest.TestCase):
    def test_flat_panel_band_and_tilted_centre_line(self):
        flat = reach_map(cfg(standoff=40), step_mm=40)
        cells = [c for row in flat["status"] for c in row]
        self.assertGreater(cells.count(2), 0)
        self.assertLess(cells.count(2), len(cells))  # an A3 panel is bigger than the reachable band
        # Tilted panel: the nozzle can only stay square to it along the centre line
        # (spray axis is on the wrist-roll axis, so it stays in the arm's vertical plane).
        tilted = reach_map(cfg(standoff=40, tilt=20), step_mm=30)
        for row in tilted["status"]:
            for u, c in zip(tilted["u_mm"], row):
                if c == 2:
                    self.assertLess(abs(u), 31.0)


if __name__ == "__main__":
    unittest.main()
