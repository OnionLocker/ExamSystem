#!/usr/bin/env python3
"""图形推理·空间类题型族回归：六面体、三视图、立体拼接。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from figure_families.testing import family_suite  # noqa: E402

SpatialTest = family_suite(("cube_net", "voxel_views", "voxel_assembly"))

if __name__ == "__main__":
    unittest.main()
