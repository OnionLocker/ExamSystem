#!/usr/bin/env python3
import subprocess
import sys
import time
from pathlib import Path

TASKS = [
    # 考法 1：古典概型与对立事件
    {
        "tag": "数量关系-数学运算-概率问题-古典概型与对立事件",
        "difficulty": "mid",
        "batch_id": "20260920_hermes_gailv_gudian_01",
        "title": "考法1·古典概型与对立事件 (Mid)",
    },
    {
        "tag": "数量关系-数学运算-概率问题-古典概型与对立事件",
        "difficulty": "hard",
        "batch_id": "20260920_hermes_gailv_gudian_02",
        "title": "考法1·古典概型与对立事件 (Hard)",
    },
    # 考法 2：定位法与同组概率
    {
        "tag": "数量关系-数学运算-概率问题-定位法与同组概率",
        "difficulty": "mid",
        "batch_id": "20260920_hermes_gailv_dingwei_01",
        "title": "考法2·定位法与同组概率 (Mid)",
    },
    {
        "tag": "数量关系-数学运算-概率问题-定位法与同组概率",
        "difficulty": "hard",
        "batch_id": "20260920_hermes_gailv_dingwei_02",
        "title": "考法2·定位法与同组概率 (Hard)",
    },
    # 考法 3：多局赛制与独立重复
    {
        "tag": "数量关系-数学运算-概率问题-多局赛制与独立重复",
        "difficulty": "mid",
        "batch_id": "20260920_hermes_gailv_saizhi_01",
        "title": "考法3·多局赛制与独立重复 (Mid)",
    },
    {
        "tag": "数量关系-数学运算-概率问题-多局赛制与独立重复",
        "difficulty": "hard",
        "batch_id": "20260920_hermes_gailv_saizhi_02",
        "title": "考法3·多局赛制与独立重复 (Hard)",
    },
    # 考法 4：抽签原理与多阶段条件
    {
        "tag": "数量关系-数学运算-概率问题-抽签原理与多阶段条件",
        "difficulty": "mid",
        "batch_id": "20260920_hermes_gailv_chouqian_01",
        "title": "考法4·抽签原理与多阶段条件 (Mid)",
    },
    {
        "tag": "数量关系-数学运算-概率问题-抽签原理与多阶段条件",
        "difficulty": "hard",
        "batch_id": "20260920_hermes_gailv_chouqian_02",
        "title": "考法4·抽签原理与多阶段条件 (Hard)",
    },
]

log_file = Path("/home/ubuntu/ExamSystem/data/gailv_batch_runner.log")
log_file.parent.mkdir(parents=True, exist_ok=True)

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line, flush=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line + "\n")

log("=== 概率问题 8 套专项出题任务正式启动 ===")

for i, task in enumerate(TASKS, 1):
    log(f"开始出第 {i}/8 套: {task['title']} (批次: {task['batch_id']})")
    cmd = [
        "python3",
        "/home/ubuntu/ExamSystem/scripts/quiz_lite.py",
        "--module", "数量关系",
        "--tag", task["tag"],
        "--count", "10",
        "--difficulty", task["difficulty"],
        "--batch-id", task["batch_id"],
    ]
    t0 = time.monotonic()
    res = subprocess.run(cmd, capture_output=True, text=True, cwd="/home/ubuntu/ExamSystem")
    dur = round(time.monotonic() - t0, 1)
    if res.returncode == 0:
        log(f"✓ 完成第 {i}/8 套: {task['title']}，耗时 {dur}s | {res.stdout.strip()[-200:]}")
    else:
        log(f"✗ 失败第 {i}/8 套: {task['title']}，耗时 {dur}s | STDERR: {res.stderr.strip()[-300:]}")

log("=== 全部 8 套概率专项题组出题任务执行完毕 ===")
