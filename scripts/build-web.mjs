// Publish the entry page only after all its assets exist. Keep old hashes for open tabs.
import { build } from 'vite';
import { mkdtemp, readdir, cp, rename, rm, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const root = fileURLToPath(new URL('../', import.meta.url));
const output = await mkdtemp(join(tmpdir(), 'examsystem-build-'));
const dist = resolve(root, 'dist');
try {
  await build({ root, build: { outDir: output, emptyOutDir: true } });
  await mkdir(dist, { recursive: true });
  for (const name of await readdir(output)) {
    // Hashed assets are immutable: replacing an existing file can interrupt an
    // in-flight response between stat() and read(), even when bytes are identical.
    if (name !== 'index.html') await cp(join(output, name), join(dist, name), {
      recursive: true, force: name !== 'assets',
    });
  }
  const pending = join(dist, `.index-${process.pid}.html`);
  await cp(join(output, 'index.html'), pending);
  await rename(pending, join(dist, 'index.html'));
  console.log('Published dist/index.html; existing asset hashes preserved.');
} finally { await rm(output, { recursive: true, force: true }); }
