#!/usr/bin/env python3
"""图形推理·规律类题型族回归：黑白块。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from figure_families.testing import family_suite  # noqa: E402

PatternTest = family_suite(("bw_grid",))

if __name__ == "__main__":
    unittest.main()
