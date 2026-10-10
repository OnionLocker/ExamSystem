import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  ROOT,
  buildDailyPack,
  collectKnownWords,
  commitPack,
  duplicateNameWarnings,
  normalizeWordName,
  parseYmd,
  runAddVocab,
  shanghaiStamp,
} from './add_vocab.mjs';

assert.equal(normalizeWordName(' 诉\u3000说 '), '诉说');
assert.equal(normalizeWordName('自测\uff21'), '自测A');
assert.equal(normalizeWordName('日\u200b追加'), '日追加');
assert.equal(parseYmd('20260231'), null);
assert.equal(parseYmd('20260228').iso, '2026-02-28');
assert.equal(shanghaiStamp(new Date('2026-10-09T16:30:00Z')).ymd, '20261010');
assert.equal(shanghaiStamp(new Date('2026-10-09T15:30:00Z')).ymd, '20261009');

const { known, errors } = collectKnownWords(ROOT);
assert.deepEqual(errors, []);
assert(known.has('诉说'));
assert(known.has('运筹帷幄'));
assert(known.has('有的放矢'));
assert(known.has('前所未有'));
assert(known.has('明日黄花'));
assert(known.get('诉说').hits.some((h) => h.label.includes('word-foundation')));
assert(known.get('运筹帷幄').hits.some((h) => h.label === '单列成语'));
assert(known.get('有的放矢').hits.some((h) => h.label === '辨析组'));
assert(known.get('前所未有').hits.some((h) => h.label === '讲义'));
for (const key of known.keys()) assert(!key.includes('。'), key);

const handout = JSON.parse(readFileSync(join(ROOT, 'src/studyBoost/idiomHandout.json'), 'utf8'));
for (const entry of handout.entries) assert(known.has(normalizeWordName(entry.word)), entry.word);

const merged = buildDailyPack({
  date: { ymd: '20991231', iso: '2099-12-31' },
  existing: {
    pack_id: 'daily-20991231',
    generator: 'add_vocab.mjs',
    created_at: '2099-12-31',
    mode: 'append',
    notes: '保留原注',
    entries: [{ id: 'daily-20991231:已有日词', word: '已有日词', wordType: 'word', explanation: '旧释义' }],
  },
  incoming: [
    { word: '已有日词', wordType: 'word', explanation: '新释义不应覆盖' },
    { word: '另一日词', wordType: 'idiom', explanation: '新释义' },
  ],
  known: new Map(),
});
assert.equal(merged.ok, true);
assert.deepEqual(merged.added, ['另一日词']);
assert.equal(merged.skipped[0].reason, '词名已存在');
assert.equal(merged.pack.notes, '保留原注');
assert.equal(merged.pack.mode, 'append');
assert.equal(merged.pack.entries[0].explanation, '旧释义');
assert.equal(merged.pack.entries[1].id, 'daily-20991231:另一日词');
assert.equal(merged.pack.entries[1].wordType, 'idiom');

const sameName = duplicateNameWarnings({
  mode: 'append',
  entries: [
    { id: 'x:诉说', word: '诉说', explanation: 'x' },
    { id: 'x:日追加自测甲', word: '日追加自测甲', explanation: 'x' },
    { id: 'x:日追加自测甲-2', word: '日追加自测甲', explanation: 'y' },
  ],
}, '/tmp/not-a-vocab-pack.json', known).filter((w) => w.includes('同名'));
assert(sameName.some((w) => w.includes('诉说')));
assert(!sameName.some((w) => w.includes('日追加自测甲')));
assert.deepEqual(duplicateNameWarnings({ mode: 'enrich', entries: [{ word: '诉说' }] }, '/tmp/x.json', known), []);

const target = join(ROOT, 'src/studyBoost/vocab-packs/daily-20991231.json');
const dir = mkdtempSync(join(tmpdir(), 'add-vocab-'));
try {
  assert.equal(existsSync(target), false);
  const input = join(dir, 'entries.json');
  writeFileSync(input, JSON.stringify([
    { word: '诉说', wordType: 'word', explanation: '不应写入' },
    { word: '运筹帷幄', wordType: 'idiom', explanation: '不应写入' },
    {
      word: ' 日追加自测甲 ',
      wordType: 'word',
      explanation: '自测用，不落盘。',
      usage: '只用于脚本自测。',
      cloze: ['会上把流程____了一遍。'],
      exampleSource: '原创例句',
    },
    { word: '日追加自测乙', wordType: 'idiom', explanation: '自测用，不落盘。' },
    { word: '日\u3000追加自测甲', wordType: 'word', explanation: '与上一条是同一个词' },
    { word: '诉\u3000说', wordType: 'word', explanation: '与主库同名的另一种写法' },
  ]));
  const dry = spawnSync(process.execPath, [
    'scripts/add_vocab.mjs', input, '--date', '20991231', '--dry-run', '--build', '--commit',
  ], { cwd: ROOT, encoding: 'utf8' });
  assert.equal(dry.status, 0, `${dry.stdout}\n${dry.stderr}`);
  const lines = dry.stdout.trim().split('\n');
  assert.equal(lines.length, 1);
  const summary = JSON.parse(lines[0]);
  assert.equal(summary.ok, true);
  assert.equal(summary.dryRun, true);
  assert.equal(summary.wrote, false);
  assert.equal(summary.file, 'src/studyBoost/vocab-packs/daily-20991231.json');
  assert.deepEqual(summary.added, ['日追加自测甲', '日追加自测乙']);
  const byWord = (word) => summary.skipped.filter((item) => item.word === word);
  assert.deepEqual(byWord('诉说').map((item) => item.reason), ['词名已存在', '输入内重复']);
  assert(byWord('诉说')[0].sources.some((s) => s.includes('word-foundation')));
  assert.equal(byWord('运筹帷幄')[0].reason, '词名已存在');
  assert(byWord('运筹帷幄')[0].sources.includes('单列成语'));
  assert.deepEqual(byWord('日追加自测甲').map((item) => item.reason), ['输入内重复']);
  assert.equal(summary.build.skipped, true);
  assert.equal(summary.commit.pushed, false);
  assert.equal(existsSync(target), false);

  const direct = runAddVocab([input, '--date', '20991231', '--dry-run']);
  assert.equal(direct.code, 0);
  assert.deepEqual(direct.summary.added, summary.added);

  const bad = join(dir, 'bad.json');
  writeFileSync(bad, JSON.stringify([
    { word: '日追加自测丙', wordType: 'word', explanation: '坏例子', cloze: ['日追加自测丙不该出现在____里。'] },
    { word: '日追加自测丁', wordType: 'noun', explanation: '坏类型' },
  ]));
  const failed = spawnSync(process.execPath, ['scripts/add_vocab.mjs', bad, '--date', '20991231'], {
    cwd: ROOT, encoding: 'utf8',
  });
  assert.notEqual(failed.status, 0);
  const failedSummary = JSON.parse(failed.stdout.trim());
  assert.equal(failedSummary.ok, false);
  assert.equal(failedSummary.wrote, false);
  assert.match(failedSummary.error, /cloze 不得含答案/);
  assert.match(failedSummary.error, /wordType/);
  assert.equal(existsSync(target), false);

  const dupPack = join(dir, 'append-dup.json');
  writeFileSync(dupPack, JSON.stringify({
    pack_id: 'tmp-dup-check',
    generator: 'test',
    mode: 'append',
    entries: [
      { id: 'tmp:诉说', word: '诉说', explanation: '不应阻断', wordType: 'word' },
      { id: 'tmp:日追加自测甲', word: '日追加自测甲', explanation: '新', wordType: 'word' },
    ],
  }));
  const validated = spawnSync(process.execPath, ['scripts/validate-vocab-pack.mjs', dupPack], {
    cwd: ROOT, encoding: 'utf8',
  });
  assert.equal(validated.status, 0, validated.stderr);
  assert.match(validated.stdout, /校验通过/);
  assert.match(validated.stdout, /诉说/);
  assert.match(validated.stdout, /同名/);
  assert.doesNotMatch(validated.stdout, /日追加自测甲/);
} finally {
  rmSync(dir, { recursive: true, force: true });
  if (existsSync(target)) rmSync(target);
}

const repo = mkdtempSync(join(tmpdir(), 'add-vocab-git-'));
try {
  const origin = join(repo, 'origin.git');
  const work = join(repo, 'work');
    const git = (cwd, args) => {
      const result = spawnSync('git', args, { cwd, encoding: 'utf8' });
      assert.equal(result.status, 0, `${args.join(' ')}\n${result.stderr || ''}${result.stdout || ''}`);
      return (result.stdout || '').replace(/\n$/, '');
    };
  git(repo, ['init', '--bare', '-b', 'main', origin]);
  git(repo, ['init', '-b', 'main', work]);
  git(work, ['config', 'user.email', 'vocab-test@example.com']);
  git(work, ['config', 'user.name', 'vocab-test']);
  writeFileSync(join(work, 'README'), 'base\n');
  git(work, ['add', '--', 'README']);
  git(work, ['commit', '-m', 'init']);
  git(work, ['remote', 'add', 'origin', origin]);
  git(work, ['push', '-u', 'origin', 'main']);
  writeFileSync(join(work, 'keep-me.txt'), '别人已暂存、不应进这次提交\n');
  git(work, ['add', '--', 'keep-me.txt']);
  writeFileSync(join(work, 'README'), 'base\n别人未暂存的修改\n');
  const rel = 'src/studyBoost/vocab-packs/daily-20991231.json';
  mkdirSync(join(work, 'src/studyBoost/vocab-packs'), { recursive: true });
  writeFileSync(join(work, rel), '{"pack_id":"daily-20991231","mode":"append","entries":[]}\n');
  const committed = commitPack(rel, 1, work);
  assert.equal(committed.ok, true);
  assert.equal(committed.pushed, true);
  assert.equal(git(work, ['show', '--name-only', '--pretty=format:', 'HEAD']), rel);
  assert.equal(git(work, ['rev-parse', 'HEAD']), git(origin, ['rev-parse', 'main']));
  const status = git(work, ['status', '--porcelain']).split('\n').sort();
  assert.deepEqual(status, [' M README', 'A  keep-me.txt']);
} finally {
  rmSync(repo, { recursive: true, force: true });
}

console.log('add_vocab 词名去重、dry-run 跳过已有词、新建词包可单独提交：通过');
