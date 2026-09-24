export const LEARNING_KEY = 'idiom_learning_v2';
export const emptyLearning = () => ({ learned: [], favorites: [], answers: {} });

export function learningState(saved, oldMarked = [], words = []) {
  const initial = emptyLearning();
  if (saved && typeof saved === 'object') return { learned: Array.isArray(saved.learned) ? saved.learned : [],
    favorites: Array.isArray(saved.favorites) ? saved.favorites : [], answers: saved.answers && typeof saved.answers === 'object' ? saved.answers : {} };
  const marked = new Set(Array.isArray(oldMarked) ? oldMarked.map(String) : []);
  initial.learned = words.filter(w => (w.legacyIds || [w.id]).some(id => marked.has(String(id)))).map(w => w.word);
  return initial;
}

export function recordAnswer(state, question, selected, now = new Date().toISOString()) {
  const previous = state.answers[question.id] || { right: 0, wrong: 0 };
  return { ...state, answers: { ...state.answers, [question.id]: {
    right: previous.right + Number(selected === question.answer), wrong: previous.wrong + Number(selected !== question.answer),
    lastCorrect: selected === question.answer, lastAt: now, word: question.answer, groupId: question.groupId,
  } } };
}

export function groupQuestion(group, lookup = () => null, rand = Math.random, previousId = null) {
  const quizzes = [group.quiz, ...(group.quizzes || [])].map((quiz, i) => ({ ...quiz, id: i ? `group:${group.id}:${i}` : `group:${group.id}` }));
  const candidates = quizzes.filter(q => q.id !== previousId);
  const choices = candidates.length ? candidates : quizzes;
  const quiz = choices[Math.floor(rand() * choices.length)];
  const options = [...(quiz.options || group.members.map(m => m[0]))];
  for (let i = options.length - 1; i > 0; i--) {
    const j = Math.floor(rand() * (i + 1));
    [options[i], options[j]] = [options[j], options[i]];
  }
  const entries = new Map(group.members.map(m => [m[0], { word: m[0], explanation: m[1], usage: m[2], examples: [m[3]] }]));
  return { id: quiz.id, stem: quiz.stem, promptLabel: '结合题意选择最恰当的词', kindLabel: '成组辨析 · 原创', answer: quiz.answer,
    options: options.map(word => ({ id: `${quiz.id}:${word}`, text: word, correct: word === quiz.answer, word: entries.get(word) || lookup(word) || { word } })),
    reason: quiz.reason, groupId: group.id, label: '成组辨析 · 原创', target: entries.get(quiz.answer) };
}

export function groupProgress(state, groupId) {
  return Object.entries(state.answers).filter(([id, a]) => a.groupId === groupId || id === `group:${groupId}`)
    .reduce((sum, [, a]) => ({ right: sum.right + (a.right || 0), wrong: sum.wrong + (a.wrong || 0) }), { right: 0, wrong: 0 });
}

// Preserve attempts on duplicate legacy cards without inventing a combined streak.
export function mergeLegacyStats(saved, words) {
  const stats = { ...saved };
  for (const word of words) {
    const ids = [...new Set([word.id, ...(word.legacyIds || [])].map(String))];
    const records = ids.map(id => saved[id]).filter(Boolean);
    if (!records.length) continue;
    stats[word.id] = records.reduce((sum, r) => ({
      right: sum.right + (r.right || 0), wrong: sum.wrong + (r.wrong || 0),
      streak: records.length === 1 ? (r.streak || 0) : 0,
    }), { right: 0, wrong: 0, streak: 0 });
    for (const id of ids) if (id !== String(word.id)) delete stats[id];
  }
  return stats;
}
