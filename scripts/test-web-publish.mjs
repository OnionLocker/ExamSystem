// Runs the real publisher and checks that open tabs keep their original assets.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../', import.meta.url));
const dist = resolve(root, 'dist');
const build = () => {
  try {
    execFileSync(process.execPath, ['scripts/build-web.mjs'], { cwd: root, encoding: 'utf8', stdio: 'pipe' });
  } catch (error) {
    process.stderr.write(String(error.stdout || '') + String(error.stderr || ''));
    throw error;
  }
};
if (!existsSync(resolve(dist, 'assets'))) build();
const before = new Map(readdirSync(resolve(dist, 'assets')).filter(name =>
  statSync(resolve(dist, 'assets', name)).isFile()).map(name => {
  const path = resolve(dist, 'assets', name);
  const { ino, mtimeMs, size } = statSync(path);
  return [path, { ino, mtimeMs, size }];
}));
build();
for (const [path, prior] of before) {
  const { ino, mtimeMs, size } = statSync(path);
  assert.deepEqual({ ino, mtimeMs, size }, prior, `Replaced an asset used by open tabs: ${path}`);
}

// Follow the published entry, lazy chunks, stylesheets and font URLs.
const entry = readFileSync(resolve(dist, 'index.html'), 'utf8');
const pending = [...entry.matchAll(/(?:src|href)="(\/assets\/[^"\s]+)"/g)].map(m => resolve(dist, `.${m[1]}`));
const visited = new Set();
while (pending.length) {
  const path = pending.pop();
  if (visited.has(path)) continue;
  visited.add(path);
  assert(existsSync(path), `Missing published dependency: ${path}`);
  if (!/\.(js|css)$/.test(path)) continue;
  const source = readFileSync(path, 'utf8');
  for (const match of source.matchAll(/["'`(]((?:\/?assets\/|\.\/)[^"'`()\s]+\.(?:js|css|woff2?|ttf))["'`)]/g)) {
    const ref = match[1];
    pending.push(ref.startsWith('./') ? resolve(dirname(path), ref) : resolve(dist, ref.replace(/^\//, '')));
  }
}
const entryStyles = [...entry.matchAll(/href="(\/assets\/[^"\s]+\.css)"/g)]
  .map(m => readFileSync(resolve(dist, `.${m[1]}`), 'utf8')).join('\n');
assert(entryStyles.includes('.katex'), 'Formula styles must load with the entry page');
for (const path of visited) {
  if (path.endsWith('.js')) assert(!/assets\/katex-fix-[\w-]+\.css/.test(readFileSync(path, 'utf8')),
    'Page switching must not depend on a separate formula stylesheet');
}
console.log(`Web publish passed: ${before.size} old assets untouched; ${visited.size} current dependencies present; formulas styled at entry.`);
