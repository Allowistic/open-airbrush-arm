# Input: paths.build and the shape generators.
# Output: unittest results for shape geometry.
# Must never: loosen a check or tolerance just to make a change pass.

import math
import unittest

from airbrush_sim import paths
from airbrush_sim.config import Shape


class TestPaths(unittest.TestCase):
    def test_circle_is_closed_and_round(self):
        (stroke,) = paths.build(Shape(kind="circle", center_mm=(10, -20), size_mm=80), 40)
        self.assertAlmostEqual(stroke[0][0], stroke[-1][0])
        self.assertAlmostEqual(stroke[0][1], stroke[-1][1])
        for u, v, s in stroke:
            self.assertAlmostEqual(math.hypot(u - 10, v + 20), 40.0, places=9)
            self.assertEqual(s, 40)

    def test_polygon_sides(self):
        for kind, n in (("square", 4), ("triangle", 3)):
            (stroke,) = paths.build(Shape(kind=kind, size_mm=60), 30)
            self.assertEqual(len(stroke), n + 1)
            for a, b in zip(stroke, stroke[1:]):
                self.assertAlmostEqual(math.hypot(b[0] - a[0], b[1] - a[1]), 60.0, places=9)

    def test_ladder_has_one_line_per_standoff(self):
        shape = Shape(kind="standoff_ladder", size_mm=100, ladder_standoffs_mm=(20, 40, 60), ladder_spacing_mm=15)
        strokes = paths.build(shape, 40)
        self.assertEqual([s[0][2] for s in strokes], [20, 40, 60])
        self.assertAlmostEqual(strokes[1][0][1] - strokes[0][0][1], 15)

    def test_resample_spacing(self):
        pts = paths.resample([(0, 0, 40), (100, 0, 40), (100, 50, 40)], 0.8)
        gaps = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:])]
        self.assertLessEqual(max(gaps), 0.8 + 1e-9)
        self.assertEqual(pts[-1], (100, 50, 40))
        self.assertAlmostEqual(paths.length(pts), 150.0, delta=0.6)  # corner cut by at most one step

    def test_unknown_shape(self):
        with self.assertRaises(ValueError):
            paths.build(Shape(kind="spiral"), 40)


if __name__ == "__main__":
    unittest.main()
