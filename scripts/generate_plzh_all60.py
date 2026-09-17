#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键后台批量生成排列组合与概率 6 大考法（各 10 题，共 60 题）全景入库脚本。"""

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUIZ_LITE = ROOT / "scripts" / "quiz_lite.py"

TASKS = [
    {
        "name": "相邻不相邻与位置限制",
        "tag": "数量关系-数学运算-排列组合问题-相邻不相邻与位置限制",
        "batch_id": "20260916_hermes_plzh_xianglin_01",
        "brief": "题型变异覆盖：1-2题标准捆绑与插空；3-4题特殊位置优限法（排头/正中间/排尾受限）；5-7题双重限制反面两行剥离法（不相邻+首末受限）；8-10题相邻区域涂色染色及复合变式。禁止同场景换数字，禁止退化成简单全排列。",
    },
    {
        "name": "分堆分配与隔板模型",
        "tag": "数量关系-数学运算-排列组合问题-分堆分配与定序消序",
        "batch_id": "20260916_hermes_plzh_fendui_01",
        "brief": "题型变异覆盖：1-2题标准隔板法（每份至少1个）；3-4题允许为0借还隔板法与至少k个预留隔板法；5-7题不同元素平均分堆消序（完全均等/部分均等除以全排列）与定向分配；8-10题定序消序及混合分配。禁止同场景换数字，区分相同元素与不同元素。",
    },
    {
        "name": "错位重排与环形圆桌",
        "tag": "数量关系-数学运算-排列组合问题-错位重排与环形圆桌",
        "batch_id": "20260916_hermes_plzh_cuowei_01",
        "brief": "题型变异覆盖：1-3题全错位重排常数（3人2种/4人9种/5人44种）；4-5题部分错位（指定k人不错位其余错位）；6-8题圆桌环形排列破环法(n-1)!与相对就坐；9-10题手镯翻转除以2及复合排列。禁止同场景换数字。",
    },
    {
        "name": "古典概型与定位秒杀",
        "tag": "数量关系-数学运算-概率问题-古典概型与定位秒杀",
        "batch_id": "20260916_hermes_plzh_gudian_01",
        "brief": "题型变异覆盖：1-3题古典概型标准比值m/n与组合抽样；4-5题正难则反对立事件概率1-P(反)（见至少）；6-8题两人同组/同班定位法秒杀（一人先定座后人挑空位一步出分式）；9-10题抽签原理先后等概率与无放回摸球。禁止同场景换数字。",
    },
    {
        "name": "分步独立与赛制决胜",
        "tag": "数量关系-数学运算-概率问题-分步独立与赛制决胜",
        "batch_id": "20260916_hermes_plzh_saizhi_01",
        "brief": "题型变异覆盖：1-3题独立重复试验伯努利模型C(n,k)*p^k*(1-p)^(n-k)；4-6题多轮闯关与分步胜率累乘累加；7-10题三局两胜/五局三胜提前终止决胜赛制（决胜局必胜定死，严禁机械算全排列）。禁止同场景换数字。",
    },
    {
        "name": "基础计数与网格路径",
        "tag": "数量关系-数学运算-排列组合问题-基础原理与几何概型",
        "batch_id": "20260916_hermes_plzh_jichu_01",
        "brief": "题型变异覆盖：1-3题分类加法与分步乘法原理综合判定；4-6题定序消序与组合数公式变形；7-10题平面网格最短路径避障公式流C(a+b,a)两行公式秒杀。禁止同场景换数字。",
    },
]


def main():
    print(f"=== 开始生成排列组合与概率 6 大考法（共 60 题）===")
    total_started = time.monotonic()
    results = []

    for i, task in enumerate(TASKS, 1):
        print(f"\n[{i}/6] 正在生成考点：【{task['name']}】（10 题）...")
        blueprint = {
            "slots": [
                {
                    "tag": task["tag"],
                    "count": 10,
                    "difficulty": "hard",
                    "brief": task["brief"],
                }
            ]
        }
        cmd = [
            sys.executable,
            str(QUIZ_LITE),
            "--module",
            "数量关系",
            "--batch-id",
            task["batch_id"],
            "--blueprint",
            json.dumps(blueprint, ensure_ascii=False),
        ]
        start_t = time.monotonic()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.monotonic() - start_t

        if proc.returncode == 0:
            print(f"  ✓ 批次 {task['batch_id']} 入库成功！耗时: {elapsed:.1f}s")
            results.append({"task": task["name"], "batch_id": task["batch_id"], "status": "ok", "elapsed": elapsed})
        else:
            print(f"  ✗ 批次 {task['batch_id']} 失败！退出码: {proc.returncode}")
            print(f"STDOUT:\n{proc.stdout}")
            print(f"STDERR:\n{proc.stderr}")
            results.append({"task": task["name"], "batch_id": task["batch_id"], "status": "failed", "error": proc.stderr})

    total_elapsed = time.monotonic() - total_started
    print(f"\n=== 全部批次处理完成，总用时: {total_elapsed:.1f}s ===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
