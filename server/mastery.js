const PRIOR_CORRECT = 2;
const PRIOR_WRONG = 2;
const HALF_LIFE_DAYS = 21;
const CONFIDENCE_SCALE = 8;

const SOURCE_WEIGHTS = {
  practice: 1,
  hermes: 0.7,
  manual: 0.4,
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function ageDays(value, now) {
  const time = Date.parse(String(value || ''));
  if (!Number.isFinite(time)) return 0;
  return Math.max(0, (now - time) / 86400000);
}

export function calculateMastery(events, now = Date.now()) {
  let effectiveSamples = 0;
  let weightedCorrect = 0;

  for (const event of events) {
    const source = SOURCE_WEIGHTS[event.evidence_type] ? event.evidence_type : 'hermes';
    const suppliedWeight = Number(event.evidence_weight);
    const evidenceWeight = Number.isFinite(suppliedWeight)
      ? clamp(suppliedWeight, 0.1, 1.5)
      : 1;
    const recencyWeight = 0.5 ** (ageDays(event.answered_at, now) / HALF_LIFE_DAYS);
    const weight = SOURCE_WEIGHTS[source] * evidenceWeight * recencyWeight;
    effectiveSamples += weight;
    weightedCorrect += weight * (event.is_correct ? 1 : 0);
  }

  if (effectiveSamples <= 0) return null;

  // Beta(2, 2) prevents one lucky answer from becoming 100% mastery.
  const estimate = (PRIOR_CORRECT + weightedCorrect)
    / (PRIOR_CORRECT + PRIOR_WRONG + effectiveSamples);
  const confidence = 1 - Math.exp(-effectiveSamples / CONFIDENCE_SCALE);
  return {
    mastery: Math.round(clamp(estimate * 100, 0, 100)),
    mastery_confidence: Math.round(clamp(confidence * 100, 0, 100)),
    mastery_samples: Math.round(effectiveSamples * 100) / 100,
  };
}

export function recomputeMastery(db, kaodian = null) {
  const profiles = kaodian
    ? db.prepare("SELECT kaodian FROM kaodian_profile WHERE kaodian = ? AND mastery_source != 'manual'").all(kaodian)
    : db.prepare("SELECT kaodian FROM kaodian_profile WHERE mastery_source != 'manual'").all();
  const events = db.prepare(`
    SELECT is_correct, answered_at, evidence_type, evidence_weight
      FROM kaodian_events
     WHERE kaodian = ?
     ORDER BY answered_at ASC, id ASC
  `);
  const update = db.prepare(`
    UPDATE kaodian_profile
     SET mastery = @mastery,
           mastery_confidence = @mastery_confidence,
           mastery_samples = @mastery_samples,
           mastery_source = 'auto',
           mastery_updated_at = datetime('now'),
           updated_at = datetime('now')
     WHERE kaodian = @kaodian
       AND (mastery IS NOT @mastery
         OR mastery_confidence IS NOT @mastery_confidence
         OR mastery_samples IS NOT @mastery_samples
         OR mastery_source IS NOT 'auto')
  `);

  const run = db.transaction((rows) => {
    for (const profile of rows) {
      const score = calculateMastery(events.all(profile.kaodian));
      if (score) update.run({ ...score, kaodian: profile.kaodian });
    }
  });
  run(profiles);
}
