// Publish the entry page only after all its assets exist. Keep old hashes for open tabs.
import { build } from 'vite';
import { mkdtemp, readdir, cp, rename, rm, mkdir, copyFile, stat, link, unlink } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const output = await mkdtemp(join(tmpdir(), 'examsystem-build-'));
const dist = resolve(root, 'dist');

// Hashed files are cached for a year. A direct copy lets a request read the
// destination while it is still growing, and the browser then keeps that
// truncated script forever. Write the full file, then link it into place.
async function publishAssets(srcDir, destDir) {
  await mkdir(destDir, { recursive: true });
  for (const name of await readdir(srcDir)) {
    const from = join(srcDir, name);
    const to = join(destDir, name);
    if ((await stat(from)).isDirectory()) {
      await publishAssets(from, to);
      continue;
    }
    if (existsSync(to)) continue;
    const tmp = join(destDir, `.${name}.${process.pid}.tmp`);
    await copyFile(from, tmp);
    try {
      await link(tmp, to);
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
    } finally {
      await unlink(tmp).catch(() => {});
    }
  }
}

try {
  await build({ root, build: { outDir: output, emptyOutDir: true } });
  await mkdir(dist, { recursive: true });
  for (const name of await readdir(output)) {
    if (name === 'index.html') continue;
    if (name === 'assets') await publishAssets(join(output, name), join(dist, name));
    else await cp(join(output, name), join(dist, name), { recursive: true, force: true });
  }
  const pending = join(dist, `.index-${process.pid}.html`);
  await cp(join(output, 'index.html'), pending);
  await rename(pending, join(dist, 'index.html'));
  console.log('Published dist/index.html; existing asset hashes preserved.');
} finally { await rm(output, { recursive: true, force: true }); }
