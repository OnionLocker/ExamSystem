#!/usr/bin/env python3
import re
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
        self.assertIn("甲", text)
        self.assertIn("乙", text)
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
        self.assertNotIn("小球", text)
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
        self.assertNotIn('x1="980"', text)

    def test_reflex_has_numbered_parts(self):
        dest = Path(tempfile.mkdtemp()) / "rx.svg"
        build_svg({"kind": "reflex"}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("①", text)
        self.assertIn("⑤", text)
        self.assertIn("<circle", text)
        self.assertNotIn("感受器", text)
        self.assertNotIn("神经节", text)


    def test_stem_coerces_wrong_kind_and_labels(self):
        from program_figure import coerce_kepui_figure, build_svg
        tank = coerce_kepui_figure(
            "水平桌面上放有圆柱形容器甲和乙，两容器内盛有相同深度的水。",
            {"kind": "motion", "ylabel": "pH"},
        )
        self.assertEqual(tank["kind"], "tank")
        dest = Path(tempfile.mkdtemp()) / "t.svg"
        build_svg(tank).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertNotIn("小球", text)
        circuit = coerce_kepui_figure(
            "电路中定值电阻 R1 与 R2 并联。电流表 A1 在 R1 支路，电流表 A 位于干路。",
            {"kind": "circuit", "left": "L1", "right": "L2", "meter": "V"},
        )
        self.assertEqual(circuit["left"], "R1")
        dest = Path(tempfile.mkdtemp()) / "c.svg"
        build_svg(circuit).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("R1", text)
        self.assertIn("A1", text)
        self.assertNotIn("L1", text)
        lever = coerce_kepui_figure(
            "轻质杠杆可绕支点 O。左侧第 2 格处挂 3 个钩码，右侧第 3 格处挂 2 个钩码。",
            {"kind": "lever"},
        )
        self.assertEqual(lever["right_n"], 2)
        dest = Path(tempfile.mkdtemp()) / "l.svg"
        build_svg(lever).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("3个钩码", text)
        self.assertIn("2个钩码", text)
        self.assertNotIn("L1", text)
        self.assertNotIn("L2", text)
        hook_y = [float(y) for y in re.findall(r'<rect x="[^"]+" y="([^"]+)"', text)]
        self.assertTrue(hook_y and all(y > 220 for y in hook_y), hook_y)
        front = coerce_kepui_figure("锋面天气系统的垂直剖面示意图", {"kind": "contour"})
        breeze = coerce_kepui_figure("锋面天气系统的垂直剖面示意图", {"kind": "breeze"}, "科学推理-地理-海陆风")
        self.assertEqual(front["kind"], "front")
        self.assertEqual(breeze["kind"], "breeze")
        dest = Path(tempfile.mkdtemp()) / "breeze.svg"
        build_svg({"kind": "breeze"}).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("陆地", text)
        self.assertIn("海洋", text)
        self.assertNotIn("冷气团", text)


    def test_tank_same_base_and_sink(self):
        from program_figure import coerce_kepui_figure, build_svg
        tank = coerce_kepui_figure(
            "水平桌面上放有两个底面积相同的柱形容器甲和乙。木块在甲中漂浮，在乙中下沉至容器底部。",
            {"kind": "tank"},
        )
        self.assertEqual(tank["widths"], [1.0, 1.0])
        self.assertEqual(tank["states"], ["float", "sink"])
        dest = Path(tempfile.mkdtemp()) / "same.svg"
        build_svg(tank).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)

    def test_climate_pair_from_stem(self):
        from program_figure import coerce_kepui_figure, build_svg
        fig = coerce_kepui_figure(
            "如图为我国东部甲地和乙地的月均温与降水量分布图。",
            {"kind": "earth"},
            "科学推理-地理-气候",
        )
        self.assertEqual(fig["kind"], "climate")
        dest = Path(tempfile.mkdtemp()) / "cl.svg"
        build_svg(fig).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)


    def test_region_geo_tag_not_swallowed_by_climate_stem(self):
        from program_figure import coerce_kepui_figure
        fig = coerce_kepui_figure(
            "如图为我国东部甲地和乙地的月均温与降水量分布图。",
            {"kind": "earth"},
            "科学推理-地理-区域地理",
        )
        self.assertEqual(fig["kind"], "climate")


    def test_locked_slot_figures_match_exam_facts(self):
        from program_figure import coerce_kepui_figure, build_svg
        circuit = coerce_kepui_figure(
            "三个定值电阻 R1=R2=R3。开关S1闭合、S2断开。",
            {"kind": "circuit"},
            "科学推理-电学-串并联",
        )
        self.assertEqual(circuit["topology"], "series_parallel")
        dest = Path(tempfile.mkdtemp()) / "c.svg"
        build_svg(circuit).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("R3", text)
        self.assertIn("S1", text)
        self.assertIn("S2", text)

        tank = coerce_kepui_figure(
            "甲为圆柱形，乙为上细下粗的锥形容器，底面积相同。",
            {"kind": "tank"},
            "科学推理-压强与浮力-液体压强",
        )
        self.assertEqual(tank["shapes"], ["cylinder", "wide_bottom"])
        dest = Path(tempfile.mkdtemp()) / "t.svg"
        build_svg(tank).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertIn("<ellipse", text)
        self.assertIn("<polyline", text)

        force = coerce_kepui_figure(
            "水平传送带正以恒定速度v运转，物块轻放在左端。",
            {"kind": "force"},
            "科学推理-力学-摩擦与惯性",
        )
        self.assertTrue(force.get("conveyor"))
        dest = Path(tempfile.mkdtemp()) / "f.svg"
        build_svg(force).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("传送带", text)
        self.assertIn("物块", text)
        self.assertIn("<circle", text)

        breeze = coerce_kepui_figure(
            "白天热力环流剖面，①②近地面，③④高空。",
            {"kind": "breeze"},
            "科学推理-地理-海陆风",
        )
        self.assertTrue(breeze.get("numbered"))
        dest = Path(tempfile.mkdtemp()) / "b.svg"
        build_svg(breeze).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("陆地", text)
        self.assertIn("海洋", text)
        self.assertIn("①", text)
        self.assertIn("④", text)

        food = coerce_kepui_figure(
            "温带草原食物网简图。",
            {"kind": "food"},
            "科学推理-生物-食物网",
            extra="绿色植物 昆虫 鼠 蜘蛛 青蛙 蛇 鹰",
        )
        self.assertIn(food["names"][0], ("农作物", "绿色植物"))
        dest = Path(tempfile.mkdtemp()) / "w.svg"
        build_svg(food).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("绿色植物", text)
        self.assertIn("鹰", text)
        self.assertGreaterEqual(text.count("<line"), 5)


    def test_latlon_region_geo(self):
        from program_figure import coerce_kepui_figure, build_svg, kind_from_stem
        self.assertEqual(kind_from_stem("地球表面经纬网局部示意图"), "latlon")
        fig = coerce_kepui_figure(
            "如图所示为地球表面经纬网局部示意图，甲、乙两地。",
            {"kind": "earth"},
            "科学推理-地理-区域地理",
        )
        self.assertEqual(fig["kind"], "latlon")
        dest = Path(tempfile.mkdtemp()) / "g.svg"
        build_svg(fig).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("经纬网", text)
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertIn("20", text)
        self.assertIn("50", text)
        climate = coerce_kepui_figure(
            "如图为我国东部甲地和乙地的月均温与降水量分布图。",
            {"kind": "earth"},
            "科学推理-地理-区域地理",
        )
        self.assertEqual(climate["kind"], "climate")


    def test_force_cart_from_stem(self):
        from program_figure import coerce_kepui_figure, build_svg
        fig = coerce_kepui_figure(
            "如图所示，水平地面上有一辆小车，小车水平底板上放置着一个物块。",
            {"kind": "force"},
            "科学推理-力学-摩擦与惯性",
        )
        self.assertTrue(fig.get("cart"))
        dest = Path(tempfile.mkdtemp()) / "cart.svg"
        build_svg(fig).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("小车", text)
        self.assertIn("物块", text)
        self.assertNotIn("传送带", text)



    def test_breeze_jia_yi_labels(self):
        from program_figure import coerce_kepui_figure, build_svg
        fig = coerce_kepui_figure(
            "如图所示为沿海热力环流。图中甲位于陆地近地面，乙位于海洋近地面，丙处和丁处分别位于甲、乙的正上方。",
            {"kind": "breeze"},
            "科学推理-地理-海陆风",
        )
        self.assertEqual(fig.get("names"), ["甲", "乙", "丙", "丁"])
        dest = Path(tempfile.mkdtemp()) / "b.svg"
        build_svg(fig).write(dest)
        text = dest.read_text(encoding="utf-8")
        self.assertIn("甲", text)
        self.assertIn("乙", text)
        self.assertIn("丙", text)
        self.assertIn("丁", text)
        self.assertIn("陆地", text)
        self.assertNotIn("等高线", text)

    def test_current_kepui_stems_draw_exam_facts(self):
        from program_figure import coerce_kepui_figure, build_svg
        circuit = coerce_kepui_figure(
            "电流表 A₁ 测 R₁，电流表 A₂ 测干路。电压保持不变。",
            {"kind": "circuit"},
            "科学推理-电学-串并联",
            extra="U S R_1 R_2 A_1 A_2",
        )
        self.assertEqual(circuit["left"], "R1")
        self.assertEqual(circuit["main_meter"], "A2")
        text = "".join(build_svg(circuit).buf)
        self.assertIn("R1", text)
        self.assertIn("A2", text)
        self.assertNotIn("L1", text)

        tank = coerce_kepui_figure(
            "细线系住合金块，甲中浸没未接触容器底，乙中沉入容器底部。",
            {"kind": "tank"},
            "科学推理-压强与浮力-容器底部受力",
        )
        self.assertEqual(tank["object"], "合金块")
        self.assertEqual(tank["states"], ["suspend", "sink"])
        text = "".join(build_svg(tank).buf)
        self.assertIn("合金块", text)
        self.assertGreaterEqual(text.count("合金块"), 2)

        food = coerce_kepui_figure(
            "如图所示为某森林生态系统的食物网简图。",
            {"kind": "food"},
            "科学推理-生物-生态系统与能量",
            extra="绿色植物 昆虫 兔 鼠 食虫鸟 蛇 鹰",
        )
        self.assertEqual(food["names"][:3], ["绿色植物", "昆虫", "兔"])
        text = "".join(build_svg(food).buf)
        self.assertIn("绿色植物", text)
        self.assertIn("食虫鸟", text)
        self.assertGreaterEqual(text.count("<line"), 6)

        force = coerce_kepui_figure(
            "水平地面上有一辆小车，底板上放置物块，水平拉力作用。",
            {"kind": "force"},
            "科学推理-力学-摩擦与惯性",
        )
        text = "".join(build_svg(force).buf)
        self.assertIn('y="322"', text)
        self.assertNotIn('y="246"', text)



if __name__ == "__main__":
    unittest.main()
