#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from figure_lab import fig_motion
from figure_qa import check_question


class FigureQaTest(unittest.TestCase):
    def test_rejects_tiny_png_and_missing_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            png = root / "images" / "q.png"
            png.parent.mkdir(parents=True)
            Image.new("RGB", (200, 200), "white").save(png)
            png.with_suffix(".svg").write_text(
                '<svg width="200" height="200"><text font-size="13">峰</text></svg>',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q1",
                    "stem": "图中虚线甲、乙分别对应不同部位。",
                    "stem_images": ["images/q.png"],
                },
            )
        self.assertTrue(any("像素过低" in item for item in issues))
        self.assertTrue(any("字号" in item for item in issues))
        self.assertTrue(any("甲乙" in item for item in issues))
        self.assertTrue(any("虚线" in item for item in issues))

    def test_rejects_rotation_without_net(self):
        issues = check_question(
            Path("."),
            {
                "external_id": "Q2",
                "stem": "如图所示为一个带标记的正方体立体图。下列哪一项是旋转后得到的？",
                "stem_images": [],
            },
        )
        self.assertTrue(any("展开图" in item for item in issues))

    def test_rejects_front_stem_on_contour_map(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            png = root / "images" / "q.png"
            png.parent.mkdir(parents=True)
            Image.new("RGB", (1400, 700), "white").save(png)
            png.with_suffix(".svg").write_text(
                '<svg width="1100" height="620"><text font-size="24">等高线（单位：m，等高距 50m）</text>'
                '<text font-size="40">甲</text></svg>',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q3",
                    "stem": "如图所示为某锋面天气系统剖面示意图。",
                    "tags": ["科学推理-地理-锋面天气"],
                    "stem_images": ["images/q.png"],
                },
            )
        self.assertTrue(any("锋面题配了等高线图" in item for item in issues))
        self.assertTrue(any("气团标注" in item for item in issues))

    def test_accepts_front_cross_section(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            png = root / "images" / "q.png"
            png.parent.mkdir(parents=True)
            Image.new("RGB", (1400, 700), "white").save(png)
            png.with_suffix(".svg").write_text(
                '<svg width="1100" height="620"><text font-size="32">冷气团</text>'
                '<text font-size="32">暖气团</text><text font-size="26">锋面剖面示意图</text></svg>',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q4",
                    "stem": "如图所示为某锋面天气系统剖面示意图。",
                    "tags": ["科学推理-地理-锋面天气"],
                    "stem_images": ["images/q.png"],
                },
            )
        self.assertFalse(any("锋面" in item or "气团" in item for item in issues), issues)

    def _write_png_svg(self, root: Path, svg: str) -> None:
        png = root / "images" / "q.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (1400, 700), "white").save(png)
        png.with_suffix(".svg").write_text(svg, encoding="utf-8")

    def test_rejects_spec_without_ticks_or_crossing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_png_svg(
                root,
                '<svg width="1100" height="620">'
                '<text font-size="32">甲</text><text font-size="32">乙</text>'
                '<text font-size="26">s</text><text font-size="26">t</text>'
                '<polyline points="80,420 320,280 600,200 900,140"/>'
                '<polyline points="80,500 360,470 720,360 900,340"/>'
                "</svg>",
            )
            (root / "image-specs.json").write_text(
                '{"questions":[{"question_id":"Q1","image_facts":'
                '["坐标系 t/s 范围0至4，s/m 范围0至6，甲(0, 6)到(4, 0)，乙(0, 0)到(4, 6)，交于(2, 3)"],'
                '"image_only_facts":["两线在t=2相交"],"must_derive":["相遇"]}]}',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q1",
                    "category": "科学推理",
                    "stem": "甲、乙两车 s-t 图像如图。",
                    "stem_images": ["images/q.png"],
                    "tags": ["科学推理-力学-运动图像"],
                },
            )
        self.assertTrue(any("刻度" in item for item in issues), issues)
        self.assertTrue(any("交点" in item for item in issues), issues)

    def test_rejects_reflex_food_web_and_extra_iron(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_png_svg(
                root,
                '<svg width="1100" height="620"><text font-size="28">草</text>'
                '<text font-size="28">兔</text><text font-size="28">铁块</text></svg>',
            )
            (root / "image-specs.json").write_text(
                '{"questions":[{"question_id":"Q4","image_facts":'
                '["缩手反射弧①②③④⑤，①感受器②传入神经③神经中枢④传出神经⑤效应器"],'
                '"image_only_facts":["①为感受器"],"must_derive":["传导方向"]}]}',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q4",
                    "category": "科学推理",
                    "stem": "如图为缩手反射弧，①–⑤分别是。",
                    "stem_images": ["images/q.png"],
                    "tags": ["科学推理-生物-反射弧"],
                },
            )
        self.assertTrue(any("①–⑤" in item or "①" in item for item in issues), issues)
        self.assertTrue(any("食物网" in item for item in issues), issues)
        self.assertTrue(any("铁块" in item for item in issues), issues)

    def test_rejects_front_answer_leak(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_png_svg(
                root,
                '<svg width="1100" height="620"><text font-size="32">冷气团</text>'
                '<text font-size="32">暖气团</text><text font-size="26">冷锋剖面示意图</text></svg>',
            )
            (root / "image-specs.json").write_text(
                '{"questions":[{"question_id":"Q2","image_facts":["冷气团楔、暖气团、雨区"],'
                '"image_only_facts":["雨区在锋后"],"must_derive":["该锋面为冷锋"]}]}',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q2",
                    "category": "科学推理",
                    "stem": "如图所示为某锋面天气系统剖面示意图。",
                    "stem_images": ["images/q.png"],
                    "tags": ["科学推理-地理-锋面天气"],
                },
            )
        self.assertTrue(any("must_derive" in item and "冷锋" in item for item in issues), issues)

    def test_negated_fact_is_forbidden_not_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_png_svg(
                root,
                '<svg width="1100" height="620"><text font-size="32">①</text>'
                '<text font-size="32">②</text><text font-size="32">③</text>'
                '<text font-size="32">④</text><text font-size="32">⑤</text>'
                '<text font-size="24">神经节</text></svg>',
            )
            (root / "image-specs.json").write_text(
                '{"questions":[{"question_id":"Q4","image_facts":'
                '["标注①②③④⑤，不出现感受器、效应器等汉字名称，②上有神经节"],'
                '"image_only_facts":["仅以①~⑤标注"],"must_derive":["①为感受器"]}]}',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q4",
                    "category": "科学推理",
                    "stem": "人体膝跳反射的反射弧如图，①–⑤是。",
                    "stem_images": ["images/q.png"],
                    "tags": ["科学推理-生物-人体调节"],
                },
            )
        self.assertFalse(any("感受器" in item and "清单有" in item for item in issues), issues)
        self.assertFalse(any("must_derive" in item for item in issues), issues)

    def test_accepts_motion_matching_spec(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            png = root / "images" / "q.png"
            png.parent.mkdir(parents=True)
            Image.new("RGB", (1400, 700), "white").save(png)
            fig_motion().write(png.with_suffix(".svg"))
            (root / "image-specs.json").write_text(
                '{"questions":[{"question_id":"Q1","image_facts":'
                '["坐标系 t/s 范围0至4，s/m 范围0至6，甲(0, 6)到(4, 0)，乙(0, 0)到(4, 6)，交于(2, 3)"],'
                '"image_only_facts":["两线在t=2相交"],"must_derive":["相遇"]}]}',
                encoding="utf-8",
            )
            issues = check_question(
                root,
                {
                    "external_id": "Q1",
                    "category": "科学推理",
                    "stem": "甲、乙两车 s-t 图像如图。",
                    "stem_images": ["images/q.png"],
                    "tags": ["科学推理-力学-运动图像"],
                },
            )
        self.assertFalse(any("刻度" in item or "交点" in item or "清单有" in item for item in issues), issues)

    def test_issue_strings_map_to_fig_classes(self):
        from quality_ledger import classify_figure_issue

        self.assertEqual(classify_figure_issue("Q1: 清单有 甲、乙，图上没有"), "fig_missing_label")
        self.assertEqual(classify_figure_issue("Q1: 清单要求交点，图上折线不相交"), "fig_no_intersection")
        self.assertEqual(classify_figure_issue("Q1: 图上多了清单/题干没有的「木块」"), "fig_extra_object")
        self.assertEqual(classify_figure_issue("Q1: 锋面题配了等高线图"), "fig_kind_mismatch")
        self.assertEqual(classify_figure_issue("Q1: 反射弧题配了食物网"), "fig_kind_mismatch")
        self.assertEqual(classify_figure_issue("Q1: 图上写了 must_derive 的「冷锋」"), "fig_leak_answer")
        self.assertEqual(classify_figure_issue("Q1: 像素过低 1280x720（至少 1400x500）"), "fig_low_res")


if __name__ == "__main__":
    unittest.main()
