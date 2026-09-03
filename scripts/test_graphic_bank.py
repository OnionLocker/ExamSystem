#!/usr/bin/env python3
"""Deterministic graphic renderers: answer is computed, then drawn."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from graphic_bank import (
    NET_CORRECT,
    SECTION_RECIPES,
    SPACE_MOVES,
    VIEW_RECIPES,
    _section_wrongs,
    build_graphic_paper,
    front_view,
    section_of_stack,
    top_view,
    valid_visible_triple,
    write_spatial_batch,
)
from image_kinds import GRAPHIC_KIND_BY_MOVE, PROGRAM, draw_mode
from panduan_pack import GRAPHIC_EXAM_MOVES, select_panduan_paper
import random


class ImageKindsTest(unittest.TestCase):
    def test_graphic_moves_are_programmatic(self):
        for moves in GRAPHIC_EXAM_MOVES.values():
            for move in moves:
                kind = GRAPHIC_KIND_BY_MOVE[move]
                self.assertEqual(draw_mode(kind), PROGRAM, move)


class SectionMathTest(unittest.TestCase):
    def test_horizontal_cut_is_bottom_footprint(self):
        voxels = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0), (0, 0, 1)}
        self.assertEqual(section_of_stack(voxels, "z=0.5"), {(0, 0), (1, 0), (0, 1), (1, 1)})
        self.assertEqual(section_of_stack({(0, 0, 0), (1, 0, 0), (0, 1, 0)}, "z=0.5"), {(0, 0), (1, 0), (0, 1)})

    def test_section_wrongs_are_unique(self):
        shapes = [section_of_stack(r["voxels"], r["plane"]) for r in SECTION_RECIPES]
        shapes.extend(top_view(r["voxels"]) if r["mode"] == "top" else front_view(r["voxels"]) for r in VIEW_RECIPES)
        for truth in shapes:
            wrongs = _section_wrongs(truth)
            self.assertEqual(len(wrongs), 3)
            self.assertEqual(len({frozenset(item) for item in wrongs}), 3)
            self.assertNotIn(truth, wrongs)

    def test_top_view_ignores_height(self):
        voxels = {(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1)}
        self.assertEqual(top_view(voxels), {(0, 0), (1, 0), (0, 1)})
        self.assertNotIn((1, 1), top_view(voxels))
        self.assertEqual(front_view(voxels), {(0, 0), (1, 0), (0, 1)})


class CubeNetMathTest(unittest.TestCase):
    def test_keyed_triples_are_right_handed(self):
        for visible in NET_CORRECT:
            self.assertTrue(valid_visible_triple(visible["south"], visible["top"], visible["east"]), visible)

    def test_opposite_faces_cannot_share_a_corner(self):
        self.assertFalse(valid_visible_triple("2", "5", "1"))
        self.assertFalse(valid_visible_triple("2", "6", "3"))


class SpatialDrillTest(unittest.TestCase):
    def test_ten_items_split_and_option_images(self):
        kinds = [GRAPHIC_KIND_BY_MOVE[move] for move, *_ in SPACE_MOVES]
        self.assertEqual(kinds.count("cube_net"), 4)
        self.assertEqual(kinds.count("cube_section"), 3)
        self.assertEqual(kinds.count("cube_views"), 3)
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            questions = write_spatial_batch(batch_dir, "space_demo", "空间专项")
            self.assertEqual(len(questions), 10)
            self.assertEqual([q["answer"] for q in questions], [row[2] for row in SPACE_MOVES])
            for question in questions:
                stem = batch_dir / question["stem_images"][0]
                self.assertTrue(stem.is_file())
                self.assertGreater(stem.stat().st_size, 1000)
                self.assertEqual(len(question["options"]), 4)
                hashes = []
                for option in question["options"]:
                    self.assertTrue(option.get("images"))
                    path = batch_dir / option["images"][0]
                    self.assertTrue(path.is_file())
                    hashes.append(path.read_bytes())
                self.assertEqual(len(set(hashes)), 4, question["external_id"])


class BuildPaperTest(unittest.TestCase):
    def test_five_pngs_and_keyed_letters(self):
        letters = list("ABCD" * 5)
        slots = [
            slot
            for slot in select_panduan_paper({}, {}, letters=letters, rng=random.Random("g1"))
            if slot["section"] == "graphic"
        ]
        with tempfile.TemporaryDirectory() as temp:
            batch_dir = Path(temp)
            questions = build_graphic_paper(slots, batch_dir, "demo")
            self.assertEqual(len(questions), 5)
            for slot, question in zip(slots, questions):
                self.assertEqual(question["answer"], slot["answer"])
                self.assertTrue((batch_dir / question["stem_images"][0]).is_file())
                self.assertGreater((batch_dir / question["stem_images"][0]).stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
