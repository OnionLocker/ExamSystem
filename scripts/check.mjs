// Local regressions only: temporary learner data, no live model calls or publishing.
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const separate = new Set(['test-hermes-staging.mjs', 'test-web-publish.mjs']);
const tests = readdirSync(join(root, 'scripts')).filter(name =>
  /^test[-_].*\.(mjs|py)$/.test(name) && !separate.has(name)).sort();
let passed = 0;
for (const name of tests) {
  const temp = mkdtempSync(join(tmpdir(), 'examsystem-test-'));
  try {
    const result = spawnSync(name.endsWith('.py') ? 'python3' : process.execPath,
      [join(root, 'scripts', name)], {
        cwd: root, encoding: 'utf8', timeout: 120000,
        env: { ...process.env, EXAM_DB: join(temp, 'exam.db'),
          EXAM_DRAFT_DIR: join(temp, 'drafts'), EXAM_PRACTICE_REVIEW_DIR: join(temp, 'reviews'),
          POLICY_LIVE_REVIEW: '0' },
      });
    if (result.status === 0) {
      passed++;
      console.log(`PASS ${name}`);
    } else {
      process.exitCode = 1;
      console.error(`FAIL ${name}\n${result.stdout || ''}${result.stderr || ''}${result.error || ''}`);
    }
  } finally { rmSync(temp, { recursive: true, force: true }); }
}
console.log(`${passed}/${tests.length} local test scripts passed.`);
