#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import figure_flash_ops as ops
from draw_agent import draw_figure


class ParseDecisionTest(unittest.TestCase):
    def test_accepts_json_and_fences(self):
        raw = """```json
{"action":"render_kind","kind":"circuit","params":{"left":"R1"},"reason":"换电路图种"}
```"""
        got = ops.parse_decision(raw)
        self.assertEqual(got["action"], "render_kind")
        self.assertEqual(got["kind"], "circuit")
        self.assertEqual(got["params"]["left"], "R1")

    def test_unknown_action_falls_to_fallback(self):
        got = ops.parse_decision({"action": "redraw", "kind": "front"})
        self.assertEqual(got["action"], "fallback")


class ApplyDecisionTest(unittest.TestCase):
    def test_regen_does_not_draw(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"
            out = ops.apply_decision(
                {"action": "regen", "kind": "", "params": {}, "reason": "题干无法出图，需改题"},
                {"stem": "无法对应的装置"},
                dest,
            )
            self.assertTrue(out["regen"])
            self.assertFalse(out["ok"])
            self.assertFalse(dest.is_file())

    def test_render_kind_uses_injected_renderer(self):
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"
            called = []
            def renderer(fig, path):
                called.append(fig["kind"])
                path.write_bytes(b"png")
            out = ops.apply_decision(
                {"action": "render_kind", "kind": "circuit", "params": {}, "reason": "换电路"},
                {"stem": "如图电路", "kind_hint": "front"},
                dest,
                renderer,
            )
            self.assertEqual(called, ["circuit"])
            self.assertFalse(out.get("regen"))
            self.assertTrue(dest.is_file())


class DrawAgentOpsTest(unittest.TestCase):
    def test_inspect_fail_then_flash_regen_raises(self):
        request = {
            "stem": "如图所示为无法画出的装置。",
            "tags": ["科学推理-物理-电路故障"],
            "kind_hint": "circuit",
            "must_show": ["甲", "乙"],
        }
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"
            dest.write_bytes(b"png")
            with mock.patch("draw_agent.render_kind", return_value={"ok": True, "kind": "circuit"}), \
                 mock.patch("draw_agent.inspect_figure", return_value={"ok": False, "issues": ["缺少导线"]}), \
                 mock.patch("draw_agent.decide", return_value={
                     "action": "regen", "kind": "", "params": {}, "reason": "题干无法出图，需改题"
                 }), \
                 mock.patch.dict("os.environ", {"DRAW_AGENT": "0", "DRAW_FLASH_OPS": "1"}):
                with self.assertRaises(RuntimeError) as ctx:
                    draw_figure(request, dest, batch_dir=Path(temp))
            self.assertIn("FIGURE_REGEN", str(ctx.exception))

    def test_inspect_fail_then_flash_switches_kind(self):
        request = {
            "stem": "如图杠杆，支点 O，左侧钩码。",
            "tags": ["科学推理-物理-杠杆"],
            "kind_hint": "circuit",
            "must_show": ["O"],
        }
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"

            def fake_render(kind, params, dest, renderer=None):
                dest.write_bytes(b"png")
                dest.with_suffix(".svg").write_text("<svg></svg>", encoding="utf-8")
                return {"ok": True, "kind": kind}

            inspect_calls = {"n": 0}
            def fake_inspect(request, dest, root, vision=False):
                inspect_calls["n"] += 1
                if inspect_calls["n"] == 1:
                    return {"ok": False, "issues": ["电路图画成了杠杆"]}
                return {"ok": True, "issues": []}

            with mock.patch("draw_agent.render_kind", side_effect=fake_render), \
                 mock.patch("draw_agent.inspect_figure", side_effect=fake_inspect), \
                 mock.patch("draw_agent.check_with_flash", create=True), \
                 mock.patch("draw_agent.decide", return_value={
                     "action": "render_kind", "kind": "lever", "params": {}, "reason": "考点是杠杆"
                 }), \
                 mock.patch("figure_flash_qa.review_figure_issues", return_value=[]), \
                 mock.patch.dict("os.environ", {"DRAW_AGENT": "0", "DRAW_FLASH_OPS": "1"}):
                out = draw_figure(request, dest, batch_dir=Path(temp))
            self.assertTrue(out["ok"])
            self.assertEqual(out["kind"], "lever")

    def test_locked_kind_does_not_switch_or_compose(self):
        request = {
            "stem": "circuit R1=R2=R3",
            "tags": ["科学推理-电学-串并联"],
            "kind_hint": "circuit",
            "kind_locked": True,
            "must_show": ["甲", "乙"],
        }
        with tempfile.TemporaryDirectory() as temp:
            dest = Path(temp) / "q.png"

            def fake_render(kind, params, dest, renderer=None):
                dest.write_bytes(b"png")
                dest.with_suffix(".svg").write_text("<svg><text>R1</text></svg>", encoding="utf-8")
                return {"ok": True, "kind": kind}

            chat = mock.Mock(return_value={"content": "", "tool_calls": []})
            with mock.patch("draw_agent.render_kind", side_effect=fake_render), mock.patch("draw_agent.inspect_figure", return_value={"ok": False, "issues": ["missing"]}), mock.patch("draw_agent.decide", return_value={"action": "render_kind", "kind": "lever", "params": {}, "reason": "switch"}), mock.patch("draw_tools.compose_svg") as compose, mock.patch.dict("os.environ", {"DRAW_AGENT": "1", "DRAW_FLASH_OPS": "1"}):
                out = draw_figure(request, dest, batch_dir=Path(temp), llm=chat)
            self.assertTrue(out["ok"])
            self.assertEqual(out["kind"], "circuit")
            self.assertTrue(out.get("locked"))
            self.assertEqual(chat.call_count, 0)
            compose.assert_not_called()



if __name__ == "__main__":
    unittest.main()
