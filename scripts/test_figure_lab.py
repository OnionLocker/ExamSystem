#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_lab import CATALOG, build, cube_faces, fig_compose, fit_iso, iso_inside, voxel_corners
from oblique_section import sample, render_svg
from abc_section import make


class FigureLabTest(unittest.TestCase):
    def test_iso_cube_shows_three_faces(self):
        faces = cube_faces(0, 0, 0, 200, 200, 80)
        pts = []
        for name in ("south", "east", "top"):
            self.assertEqual(len(faces[name]), 4)
            pts.extend(faces[name])
        uniq = {(round(x, 2), round(y, 2)) for x, y in pts}
        self.assertEqual(len(uniq), 7)

    def test_catalog_writes_every_svg(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp)
            catalog = build(dest)
            self.assertGreaterEqual(len(CATALOG), 50)
            files = {item["file"] for g in catalog["groups"] for item in g["items"]}
            self.assertEqual(len(files), len(CATALOG))
            for name in files:
                text = (dest / name).read_text(encoding="utf-8")
                self.assertTrue(text.startswith("<svg"))
                self.assertIn('fill="#ffffff"', text)
                self.assertNotIn("#1e90ff", text)
                self.assertNotIn("rgb(", text)

    def test_compose_skips_origin_circle(self):
        svg = fig_compose({"elements": [
            {"type": "circle", "c": [0, 0], "r": 24},
            {"type": "circle", "c": [400, 280], "r": 24},
            {"type": "text", "p": [0, 0], "text": "X"},
            {"type": "text", "p": [400, 200], "text": "A"},
        ]})
        body = "".join(svg.buf)
        self.assertIn('cx="400"', body)
        self.assertNotIn('cx="0"', body)
        self.assertIn(">A<", body)
        self.assertNotIn(">X<", body)

    def test_fit_iso_keeps_stack_inside_canvas(self):
        voxels = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)}
        w, h = 1100, 560
        ox, oy, sc = fit_iso(voxel_corners(voxels), (40, 80, 1020, 400), pad=16)
        self.assertTrue(iso_inside(voxel_corners(voxels), ox, oy, sc, w, h, margin=4))
        self.assertGreater(sc, 40)

    def test_oblique_section_fits_canvas(self):
        s, meta = render_svg(*sample(11, 10))
        self.assertTrue(meta["ok"])
        self.assertGreaterEqual(meta["cuts"], 3)
        self.assertEqual((s.w, s.h), (1100, 560))

    def test_abc_section_quiz_has_four_options(self):
        quiz = make(6, 7)
        self.assertIn(quiz["answer"], "ABCD")
        self.assertEqual(len(quiz["options"]), 4)
        self.assertTrue(all(opt for opt in quiz["options"]))
        self.assertGreaterEqual(quiz["n_edge"], 4)


if __name__ == "__main__":
    unittest.main()
