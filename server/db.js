import Database from 'better-sqlite3';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, '..', 'data');
if (!fs.existsSync(dataDir)) fs.mkdirSync(dataDir, { recursive: true });

const dbPath = path.join(dataDir, 'exam.db');
const db = new Database(dbPath);

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// ---------- Schema ----------
db.exec(`
CREATE TABLE IF NOT EXISTS questions (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  category       TEXT    NOT NULL,
  sub_category   TEXT,
  content        TEXT    NOT NULL,
  options        TEXT,                   -- JSON: [{ key:'A', text:'...' }, ...]
  correct_answer TEXT    NOT NULL,
  explanation    TEXT,
  difficulty     INTEGER DEFAULT 2,      -- 1~5
  tags           TEXT,                   -- JSON: [ 'xxx' ]
  source         TEXT,                   -- 来源：年份、套卷
  created_at     TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);

CREATE TABLE IF NOT EXISTS practice_sessions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  category     TEXT,
  total        INTEGER DEFAULT 0,
  correct      INTEGER DEFAULT 0,
  duration_sec INTEGER DEFAULT 0,
  started_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
  ended_at     TEXT
);

CREATE TABLE IF NOT EXISTS practice_answers (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id     INTEGER NOT NULL,
  question_id    INTEGER NOT NULL,
  user_answer    TEXT,
  is_correct     INTEGER NOT NULL DEFAULT 0,
  time_spent_sec INTEGER DEFAULT 0,
  answered_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (session_id)  REFERENCES practice_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(id)          ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_answers_session  ON practice_answers(session_id);
CREATE INDEX IF NOT EXISTS idx_answers_question ON practice_answers(question_id);

CREATE TABLE IF NOT EXISTS mistakes (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id   INTEGER NOT NULL UNIQUE,
  wrong_count   INTEGER DEFAULT 1,
  last_wrong_at TEXT    DEFAULT CURRENT_TIMESTAMP,
  mastered      INTEGER DEFAULT 0,
  note          TEXT,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  title      TEXT    NOT NULL,
  exam_date  TEXT,
  score      TEXT,
  status     TEXT    DEFAULT '待复盘',   -- 待复盘 / 进行中 / 已复盘
  notes      TEXT,
  file_path  TEXT,
  created_at TEXT    DEFAULT CURRENT_TIMESTAMP
);
`);

// ---------- Seed（仅在库为空时注入示例数据） ----------
const { count } = db.prepare('SELECT COUNT(*) AS count FROM questions').get();
if (count === 0) {
  const insertQ = db.prepare(`
    INSERT INTO questions (category, sub_category, content, options, correct_answer, explanation, difficulty, source, tags)
    VALUES (@category, @sub_category, @content, @options, @correct_answer, @explanation, @difficulty, @source, @tags)
  `);

  const seed = [
    {
      category: '数量关系',
      sub_category: '行程问题',
      content:
        '甲乙两人从相距 60 公里的两地同时出发相向而行，甲每小时走 12 公里，乙每小时走 8 公里，几小时后相遇？',
      options: JSON.stringify([
        { key: 'A', text: '2 小时' },
        { key: 'B', text: '3 小时' },
        { key: 'C', text: '4 小时' },
        { key: 'D', text: '5 小时' },
      ]),
      correct_answer: 'B',
      explanation: '相遇时间 = 总距离 / 速度和 = 60 / (12 + 8) = 3 小时。',
      difficulty: 1,
      source: '示例题',
      tags: JSON.stringify(['相遇', '基础']),
    },
    {
      category: '资料分析',
      sub_category: '增长率',
      content:
        '某省 2022 年 GDP 为 10000 亿元，2023 年 GDP 为 10800 亿元。2023 年 GDP 同比增长率约为？',
      options: JSON.stringify([
        { key: 'A', text: '6%' },
        { key: 'B', text: '7%' },
        { key: 'C', text: '8%' },
        { key: 'D', text: '9%' },
      ]),
      correct_answer: 'C',
      explanation: '(10800 - 10000) / 10000 = 8%。',
      difficulty: 1,
      source: '示例题',
      tags: JSON.stringify(['增长率', '基础']),
    },
    {
      category: '判断推理',
      sub_category: '图形推理',
      content:
        '按给定元素的变化规律，? 处应填入的是：（示例，仅描述）三个图形依次为：正方形、圆、三角形，后面跟着正方形、圆，问下一个是？',
      options: JSON.stringify([
        { key: 'A', text: '三角形' },
        { key: 'B', text: '五边形' },
        { key: 'C', text: '正方形' },
        { key: 'D', text: '圆' },
      ]),
      correct_answer: 'A',
      explanation: '按"正方形 → 圆 → 三角形"的顺序循环。',
      difficulty: 2,
      source: '示例题',
      tags: JSON.stringify(['循环']),
    },
  ];

  const tx = db.transaction((rows) => {
    for (const r of rows) insertQ.run(r);
  });
  tx(seed);
  console.log(`[db] seeded ${seed.length} sample questions`);
}

export default db;
