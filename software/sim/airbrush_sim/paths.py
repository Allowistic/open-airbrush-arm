"""Scripted shape paths in canvas coordinates.

A path is a list of strokes. Each stroke is a list of (u_mm, v_mm, standoff_mm)
waypoints sprayed in order; the simulator inserts the travel moves (spray off)
between strokes. Shapes are deterministic: same settings, same path.
"""

from __future__ import annotations

import math
from typing import List, Sequence, Tuple

from .config import SHAPES, Shape

Waypoint = Tuple[float, float, float]
Stroke = List[Waypoint]


def circle(cu: float, cv: float, diameter: float, standoff: float, segments: int = 120) -> List[Stroke]:
    r = diameter / 2.0
    pts = [(cu + r * math.cos(2 * math.pi * k / segments), cv + r * math.sin(2 * math.pi * k / segments), standoff)
           for k in range(segments + 1)]
    return [pts]


def polygon(cu: float, cv: float, side: float, sides: int, standoff: float, rotation: float = 0.0) -> List[Stroke]:
    r = side / (2.0 * math.sin(math.pi / sides))  # circumradius
    pts = []
    for k in range(sides + 1):
        a = rotation + 2 * math.pi * k / sides
        pts.append((cu + r * math.cos(a), cv + r * math.sin(a), standoff))
    return [pts]


def line(cu: float, cv: float, length: float, standoff: float) -> List[Stroke]:
    return [[(cu - length / 2, cv, standoff), (cu + length / 2, cv, standoff)]]


def standoff_ladder(cu: float, cv: float, length: float, standoffs: Sequence[float], spacing: float) -> List[Stroke]:
    """Parallel lines, each at a different standoff: the classic airbrush
    distance test card. Lines run left to right, stacked along v."""
    n = len(standoffs)
    first = cv - spacing * (n - 1) / 2.0
    return [[(cu - length / 2, first + i * spacing, s), (cu + length / 2, first + i * spacing, s)]
            for i, s in enumerate(standoffs)]


def build(shape: Shape, standoff: float) -> List[Stroke]:
    cu, cv = shape.center_mm
    s = shape.size_mm
    if shape.kind == "circle":
        return circle(cu, cv, s, standoff)
    if shape.kind == "square":
        return polygon(cu, cv, s, 4, standoff, rotation=math.pi / 4)
    if shape.kind == "triangle":
        return polygon(cu, cv, s, 3, standoff, rotation=math.pi / 2)
    if shape.kind == "line":
        return line(cu, cv, s, standoff)
    if shape.kind == "standoff_ladder":
        return standoff_ladder(cu, cv, s, shape.ladder_standoffs_mm, shape.ladder_spacing_mm)
    raise ValueError(f"unknown shape {shape.kind!r}; choose one of {', '.join(SHAPES)}")


def resample(points: Sequence[Waypoint], step: float) -> List[Waypoint]:
    """Evenly spaced points along a polyline (step in mm, by u/v arc length;
    standoff is interpolated along with it)."""
    out = [tuple(points[0])]
    carry = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-9:
            continue
        d = step - carry
        while d <= seg + 1e-9:
            t = d / seg
            out.append(tuple(a[i] + t * (b[i] - a[i]) for i in range(3)))
            d += step
        carry = seg - (d - step)
    if math.hypot(out[-1][0] - points[-1][0], out[-1][1] - points[-1][1]) > 1e-6:
        out.append(tuple(points[-1]))
    return out  # type: ignore


def length(points: Sequence[Waypoint]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))
