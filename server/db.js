import Database from 'better-sqlite3';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, '..', 'data');
const dbPath = process.env.EXAM_DB
  ? path.resolve(process.env.EXAM_DB)
  : path.join(dataDir, 'exam.db');
const dbDir = path.dirname(dbPath);
if (!fs.existsSync(dbDir)) fs.mkdirSync(dbDir, { recursive: true });
const db = new Database(dbPath);

db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

// ---------- Schema ----------
db.exec(`
CREATE TABLE IF NOT EXISTS questions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id        TEXT UNIQUE,              -- 批次内唯一 ID，用于幂等导入
  category           TEXT    NOT NULL,
  sub_category       TEXT,
  question_type      TEXT    DEFAULT 'single', -- single / multi / judge
  content            TEXT    NOT NULL,         -- 题干文本（可含 LaTeX）
  stem_images        TEXT,                     -- JSON: ['/q-images/...']
  options            TEXT,                     -- JSON: [{ key, text, images? }]
  correct_answer     TEXT    NOT NULL,         -- 'A' / 'AC' / 'T' / 'F'
  explanation        TEXT,
  explanation_images TEXT,                     -- JSON: ['/q-images/...']
  difficulty         INTEGER DEFAULT 2,        -- 1~5
  tags               TEXT,                     -- JSON: ['xxx']
  source             TEXT,                     -- 来源：年份、套卷
  year               INTEGER,
  region             TEXT,                     -- '广东-县级' / '广东-乡镇' 等
  material_id        INTEGER,                  -- 资料分析组题引用 materials.id
  batch_id           TEXT,                     -- 导入批次（用于回滚/管理）
  created_at         TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_questions_category ON questions(category);
CREATE INDEX IF NOT EXISTS idx_questions_sub      ON questions(sub_category);

-- 真题参考库：只供出题时检索风格，不进入 AI 练题、错题本或学习画像。
CREATE TABLE IF NOT EXISTS reference_questions (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id        TEXT NOT NULL UNIQUE,
  category           TEXT NOT NULL,
  sub_category       TEXT NOT NULL,
  question_type      TEXT NOT NULL DEFAULT 'single',
  content            TEXT NOT NULL,
  stem_images        TEXT,
  options            TEXT,
  correct_answer     TEXT NOT NULL,
  explanation        TEXT,
  explanation_images TEXT,
  difficulty         INTEGER NOT NULL DEFAULT 2,
  tags               TEXT,
  source             TEXT NOT NULL,
  year               INTEGER,
  region             TEXT,
  source_url         TEXT,
  imported_by        TEXT NOT NULL DEFAULT 'agent',
  created_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at         TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reference_category
  ON reference_questions(category, sub_category);
CREATE INDEX IF NOT EXISTS idx_reference_year
  ON reference_questions(year);

-- 真题风格内化台账：source row 保持原样，用内容哈希判断新增/修改题是否需要重新处理。
CREATE TABLE IF NOT EXISTS reference_digest_items (
  external_id      TEXT PRIMARY KEY,
  content_hash     TEXT NOT NULL,
  digest_version   TEXT NOT NULL,
  status           TEXT NOT NULL,             -- accepted / holdout / excluded
  source_tier      TEXT NOT NULL,
  note             TEXT,
  generation_uses  INTEGER NOT NULL DEFAULT 0,
  evaluation_uses  INTEGER NOT NULL DEFAULT 0,
  last_used_at     TEXT,
  processed_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (external_id) REFERENCES reference_questions(external_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_reference_digest_status
  ON reference_digest_items(digest_version, status);

-- 每次为 Hermes 组装的参考包都留痕，AI 生成批次可在 manifest 中反向引用。
CREATE TABLE IF NOT EXISTS reference_context_runs (
  context_id       TEXT PRIMARY KEY,
  role             TEXT NOT NULL,             -- generate / evaluate
  digest_version   TEXT NOT NULL,
  target           TEXT NOT NULL,             -- JSON
  reference_ids    TEXT NOT NULL,             -- JSON
  batch_id         TEXT,
  created_at       TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_reference_context_created
  ON reference_context_runs(created_at);

CREATE TABLE IF NOT EXISTS materials (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  external_id TEXT UNIQUE,
  content     TEXT    NOT NULL,
  images      TEXT,                             -- JSON: ['/q-images/...']
  source      TEXT,
  year        INTEGER,
  region      TEXT,
  batch_id    TEXT,
  created_at  TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_materials_batch ON materials(batch_id);
`);

// ---------- Migration: 给已存在的旧 DB 补齐新字段 ----------
const qCols = new Set(
  db.prepare(`PRAGMA table_info(questions)`).all().map((r) => r.name)
);
const addCol = (name, decl) => {
  if (!qCols.has(name)) db.exec(`ALTER TABLE questions ADD COLUMN ${name} ${decl}`);
};
addCol('external_id',        'TEXT');
addCol('question_type',      "TEXT DEFAULT 'single'");
addCol('stem_images',        'TEXT');
addCol('explanation_images', 'TEXT');
addCol('year',               'INTEGER');
addCol('region',             'TEXT');
addCol('material_id',        'INTEGER');
addCol('batch_id',           'TEXT');
// 依赖新列的索引必须放在 migration 之后
// 注意：UPSERT (ON CONFLICT) 不支持部分索引，所以这里用完整 UNIQUE
// SQLite 对 NULL 不视为重复，老数据（external_id=NULL）安全
// 先 DROP 再建，避免历史上可能存在的 partial index 残留
db.exec(`
  DROP INDEX IF EXISTS uniq_questions_external_id;
  CREATE UNIQUE INDEX uniq_questions_external_id ON questions(external_id);
  CREATE INDEX IF NOT EXISTS idx_questions_material ON questions(material_id);
  CREATE INDEX IF NOT EXISTS idx_questions_batch    ON questions(batch_id);
`);

db.exec(`

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

-- 草稿纸：一次练习里每道题留一张「题目 + 我的圈划 + 演算过程」的合成图。
-- 图片落盘（data/draft-images/<uuid>.png），库里只存文件名，跟 review_images 一个路子。
CREATE TABLE IF NOT EXISTS practice_drafts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id  INTEGER NOT NULL,
  question_id INTEGER NOT NULL,
  filename    TEXT    NOT NULL,
  mime        TEXT    DEFAULT 'image/png',
  bytes       INTEGER DEFAULT 0,
  updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (session_id, question_id),
  FOREIGN KEY (session_id)  REFERENCES practice_sessions(id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(id)         ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_drafts_session ON practice_drafts(session_id);

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

-- 通用 KV 存储:用于跨设备同步前端的学习数据
-- (study_log / 数资历史 / 段位 / 倒计时 / 闪卡 / 小游戏 / 模考 / 番茄钟 等)
-- 每条数据本质是一段 JSON,整段读、整段写,前端逻辑不需要改动
CREATE TABLE IF NOT EXISTS user_kv (
  k          TEXT PRIMARY KEY,
  v          TEXT NOT NULL,                   -- JSON 字符串
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_plans (
  plan_date    TEXT PRIMARY KEY,
  items        TEXT NOT NULL,                 -- JSON: [{module,target,count,done,status}]
  source       TEXT NOT NULL DEFAULT 'hermes',
  snapshot_at  TEXT,
  created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 复习模块：每个模块是一组图片（知识点/错题截图等）
CREATE TABLE IF NOT EXISTS review_modules (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT    NOT NULL,
  sort_order INTEGER DEFAULT 0,
  created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_images (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id  INTEGER NOT NULL,
  filename   TEXT    NOT NULL,               -- 磁盘文件名（uuid.ext）
  orig_name  TEXT,                           -- 原始文件名
  mime       TEXT    DEFAULT 'image/jpeg',
  sort_order INTEGER DEFAULT 0,
  created_at TEXT    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (module_id) REFERENCES review_modules(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_review_images_module ON review_images(module_id);

-- 错题本：交卷时自动入本，不用手动收集。
-- 连对 correct_streak 次才算掌握，跟数资那边的错题池一个规矩：
-- 一次蒙对不等于会了。
CREATE TABLE IF NOT EXISTS mistakes (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  question_id    INTEGER NOT NULL UNIQUE,
  wrong_count    INTEGER DEFAULT 1,
  correct_streak INTEGER DEFAULT 0,
  last_wrong_at  TEXT    DEFAULT CURRENT_TIMESTAMP,
  mastered       INTEGER DEFAULT 0,
  note           TEXT,
  FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_mistakes_open ON mistakes(mastered, last_wrong_at);

-- 考点画像：questions.tags 里的每个 knowledge_point 单独记账，
-- 这样"哪个考点老是错"能直接查出来，而不是只知道"判断推理错得多"。
CREATE TABLE IF NOT EXISTS kaodian_profile (
  kaodian      TEXT PRIMARY KEY,
  module       TEXT NOT NULL,
  subtype      TEXT,
  attempts     INTEGER NOT NULL DEFAULT 0,
  correct      INTEGER NOT NULL DEFAULT 0,
  total_ms     INTEGER NOT NULL DEFAULT 0,
  last_seen    TEXT,
  streak       INTEGER NOT NULL DEFAULT 0,   -- 正数=连对，负数=连错
  note         TEXT,
  mastery      INTEGER,                      -- 统计估计值 0~100
  mastery_note TEXT,
  mastery_confidence INTEGER,
  mastery_samples REAL,
  mastery_source TEXT NOT NULL DEFAULT 'auto',
  mastery_updated_at TEXT,
  updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kp_module   ON kaodian_profile(module);
CREATE INDEX IF NOT EXISTS idx_kp_lastseen ON kaodian_profile(last_seen);

CREATE TABLE IF NOT EXISTS kaodian_events (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kaodian     TEXT NOT NULL,
  question_id INTEGER,
  session_id  INTEGER,
  is_correct  INTEGER NOT NULL,
  elapsed_ms  INTEGER,
  evidence_type TEXT NOT NULL DEFAULT 'hermes',
  evidence_weight REAL NOT NULL DEFAULT 1.0,
  answered_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_ke_kaodian ON kaodian_events(kaodian, answered_at);

-- 历史短标签/同义词到规范考点的映射。事件原文保留，画像按 canonical 汇总。
CREATE TABLE IF NOT EXISTS kaodian_aliases (
  alias       TEXT PRIMARY KEY,
  canonical   TEXT NOT NULL,
  module      TEXT NOT NULL,
  subtype     TEXT,
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kaodian_alias_canonical
  ON kaodian_aliases(canonical);

-- 知识债按规范考点清偿；不同变式题也能累计连续答对，不被 question_id 绑死。
CREATE TABLE IF NOT EXISTS kaodian_debts (
  kaodian          TEXT PRIMARY KEY,
  wrong_count      INTEGER NOT NULL DEFAULT 1,
  recovery_streak  INTEGER NOT NULL DEFAULT 0,
  last_wrong_at    TEXT,
  last_seen_at     TEXT,
  mastered         INTEGER NOT NULL DEFAULT 0,
  updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_kaodian_debts_open
  ON kaodian_debts(mastered, last_wrong_at);

-- 真题复盘：一次模考的录屏 + 答案 PDF，后台跑完存下行为画像。
-- 录屏原件几个 GB，磁盘存不下也没必要留：转码成小样本后原件立刻删，
-- 小样本用完也能手动删，库里只留分析结果。
CREATE TABLE IF NOT EXISTS exam_analyses (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  title         TEXT    NOT NULL,
  kind          TEXT    NOT NULL DEFAULT 'zhenti', -- zhenti / taoti
  exam_date     TEXT,                       -- YYYY-MM-DD，挂热力图用
  status        TEXT    NOT NULL DEFAULT 'queued',  -- queued/running/done/failed
  stage         TEXT,                       -- 当前步骤的人话描述
  progress      INTEGER DEFAULT 0,          -- 0~100
  video_file    TEXT,                       -- 转码后的小样本文件名
  video_bytes   INTEGER DEFAULT 0,
  video_deleted INTEGER DEFAULT 0,
  raw_bytes     INTEGER DEFAULT 0,          -- 原始录屏大小，只做展示
  duration_sec  INTEGER DEFAULT 0,          -- 原始时长
  speed         INTEGER DEFAULT 3,          -- 转码倍速，还原时间轴要用
  pdf_file      TEXT,
  pdf_chars     INTEGER DEFAULT 0,
  segments      TEXT,                       -- JSON: 每段的原始分析
  result        TEXT,                       -- JSON: 汇总画像与建议
  error         TEXT,
  created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
  updated_at    TEXT    DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_exam_analyses_date ON exam_analyses(exam_date);
`);

// mistakes 表在 Python 侧先建过，缺 correct_streak，这里补齐
const mCols = new Set(db.prepare('PRAGMA table_info(mistakes)').all().map((r) => r.name));
if (!mCols.has('correct_streak')) {
  db.exec('ALTER TABLE mistakes ADD COLUMN correct_streak INTEGER DEFAULT 0');
}

const examCols = new Set(db.prepare('PRAGMA table_info(exam_analyses)').all().map((r) => r.name));
if (!examCols.has('kind')) {
  db.exec("ALTER TABLE exam_analyses ADD COLUMN kind TEXT NOT NULL DEFAULT 'zhenti'");
}

const kpCols = new Set(db.prepare('PRAGMA table_info(kaodian_profile)').all().map((r) => r.name));
if (!kpCols.has('mastery')) {
  db.exec('ALTER TABLE kaodian_profile ADD COLUMN mastery INTEGER');
}
if (!kpCols.has('mastery_note')) {
  db.exec('ALTER TABLE kaodian_profile ADD COLUMN mastery_note TEXT');
}
if (!kpCols.has('mastery_confidence')) {
  db.exec('ALTER TABLE kaodian_profile ADD COLUMN mastery_confidence INTEGER');
}
if (!kpCols.has('mastery_samples')) {
  db.exec('ALTER TABLE kaodian_profile ADD COLUMN mastery_samples REAL');
}
if (!kpCols.has('mastery_source')) {
  db.exec("ALTER TABLE kaodian_profile ADD COLUMN mastery_source TEXT NOT NULL DEFAULT 'auto'");
}
if (!kpCols.has('mastery_updated_at')) {
  db.exec('ALTER TABLE kaodian_profile ADD COLUMN mastery_updated_at TEXT');
}

const keCols = new Set(db.prepare('PRAGMA table_info(kaodian_events)').all().map((r) => r.name));
if (!keCols.has('evidence_type')) {
  db.exec("ALTER TABLE kaodian_events ADD COLUMN evidence_type TEXT NOT NULL DEFAULT 'hermes'");
}
if (!keCols.has('evidence_weight')) {
  db.exec('ALTER TABLE kaodian_events ADD COLUMN evidence_weight REAL NOT NULL DEFAULT 1.0');
}
if (!keCols.has('session_id')) {
  db.exec('ALTER TABLE kaodian_events ADD COLUMN session_id INTEGER');
}
db.exec(`
  CREATE UNIQUE INDEX IF NOT EXISTS uniq_ke_practice_evidence
    ON kaodian_events(kaodian, question_id, session_id, evidence_type)
    WHERE session_id IS NOT NULL;
  UPDATE kaodian_profile
     SET mastery = CAST(ROUND(correct * 100.0 / attempts) AS INTEGER)
   WHERE mastery IS NULL AND attempts > 0
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
