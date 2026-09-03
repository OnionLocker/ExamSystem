#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from program_figure import build_svg, is_program_kind


class ProgramFigureTest(unittest.TestCase):
    def test_kinds(self):
        self.assertTrue(is_program_kind("cube_iso"))
        self.assertTrue(is_program_kind("lever"))
        self.assertTrue(is_program_kind("motion_graph"))
        self.assertTrue(is_program_kind("front"))
        self.assertTrue(is_program_kind("reflex"))
        self.assertFalse(is_program_kind("table"))

    def test_cube_svg_has_three_faces(self):
        svg = build_svg({"kind": "cube_iso", "marks": {"top": "plus", "south": "x", "east": "circle"}})
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "c.svg"
            svg.write(dest)
            text = dest.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<svg"))
        self.assertGreaterEqual(text.count("<polygon"), 3)
        self.assertNotIn("#1e90ff", text)

    def test_voxels_and_views(self):
        a = build_svg({"kind": "voxels", "voxels": [[0, 0, 0], [1, 0, 0], [0, 0, 1]]})
        b = build_svg({"kind": "views", "left": [[0, 0]], "front": [[0, 0], [1, 0]], "top": [[0, 0]]})
        self.assertGreater(a.w, 100)
        self.assertGreater(b.w, 100)
        dest = Path(tempfile.mkdtemp()) / "v.svg"
        b.write(dest)
        self.assertIn('font-size="36"', dest.read_text(encoding="utf-8"))
        self.assertIn("左视图", dest.read_text(encoding="utf-8"))

    def test_front_svg_has_air_masses_not_contours(self):
        svg = build_svg({"kind": "front", "front": "cold"})
        dest = Path(tempfile.mkdtemp()) / "front.svg"
        svg.write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("冷气团", text)
        self.assertIn("暖气团", text)
        self.assertIn("锋面剖面", text)
        self.assertNotIn("冷锋", text)
        self.assertNotIn("等高线", text)
        self.assertNotIn("等高距", text)

    def test_motion_has_ticks_and_crossing(self):
        dest = Path(tempfile.mkdtemp()) / "st.svg"
        build_svg({"kind": "motion"}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertIn(">2<", text)
        self.assertIn(">6<", text)
        self.assertIn("t/s", text)
        self.assertGreaterEqual(text.count("<polyline"), 2)

    def test_tank_default_is_cylinder_wood_only(self):
        dest = Path(tempfile.mkdtemp()) / "tank.svg"
        build_svg({"kind": "tank"}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("<ellipse", text)
        self.assertIn("木块", text)
        self.assertNotIn("铁块", text)

    def test_tank_pair_labels_jia_yi(self):
        dest = Path(tempfile.mkdtemp()) / "pair.svg"
        build_svg({"kind": "tank", "names": ["甲", "乙"]}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertIn("小球", text)
        self.assertIn("<ellipse", text)

    def test_circuit_resistors(self):
        dest = Path(tempfile.mkdtemp()) / "r.svg"
        build_svg(
            {"kind": "circuit", "left": "R1", "right": "R2", "meter": "A1", "main_meter": "A", "voltmeter": False}
        ).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("R1", text)
        self.assertIn("R2", text)
        self.assertIn("A1", text)
        self.assertNotIn("L1", text)

    def test_reflex_has_numbered_parts(self):
        dest = Path(tempfile.mkdtemp()) / "rx.svg"
        build_svg({"kind": "reflex"}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("①", text)
        self.assertIn("⑤", text)
        self.assertIn("<circle", text)
        self.assertNotIn("感受器", text)
        self.assertNotIn("神经节", text)


if __name__ == "__main__":
    unittest.main()
