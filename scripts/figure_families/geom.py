"""几何小件：整数向量、24 个保向旋转、Rodrigues 旋转、按弧长取点与形状比对。"""

from __future__ import annotations

import itertools
import math

import numpy as np


def neg(v):
    return tuple(-c for c in v)


def add(a, b):
    return tuple(x + y for x, y in zip(a, b))


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def apply(m, v):
    return tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3))


def _rotations():
    out = []
    for perm in itertools.permutations(range(3)):
        for signs in itertools.product((1, -1), repeat=3):
            m = [[0] * 3 for _ in range(3)]
            for row, col in enumerate(perm):
                m[row][col] = signs[row]
            cols = [tuple(m[i][j] for i in range(3)) for j in range(3)]
            if dot(cols[0], cross(cols[1], cols[2])) == 1:
                out.append(tuple(tuple(row) for row in m))
    return tuple(out)


ROTATIONS = _rotations()
assert len(ROTATIONS) == 24


def rodrigues(p, a0, axis, angle):
    v = np.array(p, float) - a0
    k = np.array(axis, float)
    rotated = v * math.cos(angle) + np.cross(k, v) * math.sin(angle) + k * k.dot(v) * (1 - math.cos(angle))
    return rotated + a0


def sample(polys, step=0.03):
    """[(points, closed)] -> 沿线按弧长均匀取点，不受顶点疏密影响。"""
    out = []
    for points, closed in polys:
        seq = list(points) + [points[0]] if closed else list(points)
        for (x1, y1), (x2, y2) in zip(seq, seq[1:]):
            n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / step))
            t = np.arange(n) / n
            out.append(np.stack([x1 + (x2 - x1) * t, y1 + (y2 - y1) * t], axis=1))
        out.append(np.array([seq[-1]], float))
    return np.concatenate(out) if out else np.zeros((0, 2))


def chamfer(a, b):
    if not len(a) or not len(b):
        return 9.0
    d = np.sqrt(((a[:, None, :] - b[None, :, :]) ** 2).sum(-1))
    return float((d.min(1).mean() + d.min(0).mean()) / 2)
