#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_lab import CATALOG, build, cube_faces


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


if __name__ == "__main__":
    unittest.main()
