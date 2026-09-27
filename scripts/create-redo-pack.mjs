import fs from 'node:fs';
import { createRedoPack } from '../server/routes/practice.js';

try {
  const result = createRedoPack(JSON.parse(fs.readFileSync(0, 'utf8')));
  console.log(JSON.stringify(result));
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
