import { regradeExisting } from '../server/examWorker.js';

const id = Number(process.argv[2]);
if (!id) {
  console.error('用法：node scripts/regrade_exam_pdf.mjs <exam_analyses.id>');
  process.exit(1);
}

const grade = await regradeExisting(id);
console.log(JSON.stringify({
  id,
  total: grade.total,
  correct: grade.correct,
  wrong: grade.wrong,
  blank: grade.blank,
}, null, 2));
