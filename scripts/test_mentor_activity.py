"""The mentor records activity without inventing time or deleting valid zero-score activity."""
import datetime as dt
import json
import sqlite3
import tempfile
from pathlib import Path
import daily_mentor_eval as mentor

result = mentor.normalize_eval({"valid_study": True, "score": 50, "minutes": 180, "summary": "练题复盘"})
assert result["valid_study"] and result["score"] == result["minutes"] == 0
assert not mentor.normalize_eval({"valid_study": "false", "score": 50})["valid_study"]
with tempfile.TemporaryDirectory() as directory:
    mentor.EXAM_DB = str(Path(directory) / "test.db")
    conn = sqlite3.connect(mentor.EXAM_DB)
    conn.execute("CREATE TABLE user_kv(k TEXT PRIMARY KEY, v TEXT, updated_at TEXT)")
    conn.close()
    day = dt.datetime.now(mentor.TZ).strftime("%Y-%m-%d")
    assert mentor.update_study_log(day, "练题复盘", 0, 0, ["数量关系"])
    assert mentor.update_study_log(day, "练题复盘", 50, 180, ["数量关系"])
    conn = sqlite3.connect(mentor.EXAM_DB)
    records = json.loads(conn.execute("SELECT v FROM user_kv").fetchone()[0])
    assert len(records) == 1 and records[0]["valid_study"]
    assert records[0]["minutes"] == records[0]["score"] == 0
    conn.close()
print("mentor activity: ok")
