import { useCallback, useState, useMemo } from 'react';
import { BookOpen, Search, CheckCircle2, ArrowRight, ChevronDown, Trophy, XCircle, Target } from 'lucide-react';
import { cloudGet, cloudSet } from '../cloudStorage.js';
import { addEntry } from '../studyLog/studyLog.js';
import {
  ALL_WORDS,
  QUIZ_POOL,
  lookupWord,
  QUESTION_KINDS,
  MASTERY_STREAK,
  PACK_DIAGNOSTICS,
  buildQuestion,
  kindAvailability,
  pickNextTarget,
  summarizeProgress,
} from './vocabQuiz.js';
import { IDIOM_GROUPS } from './idiomGroups.js';
import { LEARNING_KEY, groupQuestion, groupProgress, learningState, recordAnswer, mergeLegacyStats } from './idiomLearning.js';
import idiomEvidence from './idiomEvidence.json';
import './idiomStudy.css';

const MASTERED_KEY = 'vocab_mastered_ids_v1';

// Only count appearances with a traceable paper and question number.
const ZHENTI_CAT = '__zhenti';
const GD_CAT = '__gd';
const CURATED_CAT = '__curated';
const GROUPED_WORDS = new Set(IDIOM_GROUPS.flatMap(g => g.members.map(m => m[0])));
const zhentiHits = (w) => w.references?.length || 0;
const STATS_KEY = 'vocab_stats_v1';
const KINDS_KEY = 'vocab_enabled_kinds_v1';

function WordSources({ word }) {
  if (!word?.references?.length && !word?.publicSources?.length) return null;
  return <details className="idiom-source">
    <summary className="cursor-pointer">查看来源{word.references?.length ? ` · ${word.references.length} 条选项记录` : ''}</summary>
    <ul className="mt-2 space-y-1 leading-relaxed">
      {word.references?.map((r, i) => <li key={i}>{r.paper} · 第 {r.number} 题{r.recalled && !r.paper.includes('回忆') ? '（回忆版）' : ''}</li>)}
      {word.publicSources?.map(s => <li key={s.url}><a href={s.url} target="_blank" rel="noreferrer" className="underline hover:text-slate-900">{s.title}</a>（选词参考）</li>)}
    </ul>
  </details>;
}

export default function StudyBoost() {
  const [learningMode, setLearningMode] = useState('groups');
  const [learning, setLearning] = useState(() => learningState(cloudGet(LEARNING_KEY, null), cloudGet(MASTERED_KEY, []), ALL_WORDS));
  const [masteredIds, setMasteredIds] = useState(() => cloudGet(MASTERED_KEY, []));
  // Practice history is not a validated estimate of exam mastery.
  const [stats, setStats] = useState(() => mergeLegacyStats(cloudGet(STATS_KEY, {}), ALL_WORDS));
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCat, setSelectedCat] = useState(CURATED_CAT);
  const [groupFilter, setGroupFilter] = useState('all');
  const [groupScope, setGroupScope] = useState(null);
  const [testMode, setTestMode] = useState(false);
  const [userChoice, setUserChoice] = useState(null);
  const [showExplanation, setShowExplanation] = useState(false);
  // 本轮统计
  const [round, setRound] = useState({ asked: 0, right: 0 });
  const [recentIds, setRecentIds] = useState([]);
  const [question, setQuestion] = useState(null);
  const saveLearning = useCallback((next) => { setLearning(next); cloudSet(LEARNING_KEY, next); }, []);

  // 题型列表来自注册表，且只显示当前词库真能出的那些。
  // 后续 pack 补上 usage/trap/examples 等字段，对应题型会自动出现。
  const availability = useMemo(() => kindAvailability(QUIZ_POOL).filter((k) => k.count > 0), []);
  const [enabledKinds, setEnabledKinds] = useState(() => {
    const saved = cloudGet(KINDS_KEY, null);
    const valid = QUESTION_KINDS.map((k) => k.id);
    if (Array.isArray(saved) && saved.length) return saved.filter((k) => valid.includes(k));
    return valid;
  });

  // 分类列表
  const categories = useMemo(() => {
    const counts = new Map();
    for (const w of ALL_WORDS) counts.set(w.category, (counts.get(w.category) || 0) + 1);
    const zhentiCount = ALL_WORDS.filter((w) => zhentiHits(w) > 0).length;
    return [
      { id: CURATED_CAT, name: '重点整理', count: ALL_WORDS.filter(w => w.curated).length },
      { id: 'all', name: '全部积累', count: ALL_WORDS.length },
      { id: '__standalone', name: '未分组词语', count: ALL_WORDS.filter(w => !GROUPED_WORDS.has(w.word)).length },
      { id: GD_CAT, name: '广东近年选项词', count: ALL_WORDS.filter(w => w.references.some(r => r.region === '广东')).length },
      ...(zhentiCount ? [{ id: ZHENTI_CAT, name: '近年真题选项词', count: zhentiCount }] : []),
      ...[...counts.entries()]
        .filter(([name]) => name)
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({ id: name, name, count })),
    ];
  }, []);

  // 过滤词汇列表（浏览用，含无法出题的条目）
  const filteredWords = useMemo(() => {
    const list = ALL_WORDS.filter(w => {
      const matchCat = selectedCat === 'all'
        || (selectedCat === CURATED_CAT ? w.curated : selectedCat === '__standalone' ? !GROUPED_WORDS.has(w.word) : selectedCat === GD_CAT ? w.references.some(r => r.region === '广东')
          : selectedCat === ZHENTI_CAT ? zhentiHits(w) > 0 : w.category === selectedCat);
      const q = searchQuery.trim();
      const matchSearch = !q || [w.word, w.explanation, w.usage, ...(w.rivals || [])].some(text => text?.includes(q));
      return matchCat && matchSearch;
    });
    // 真题视图按考频降序，先背考得最多的
    return [GD_CAT, ZHENTI_CAT].includes(selectedCat)
      ? [...list].sort((a, b) => zhentiHits(b) - zhentiHits(a))
      : list;
  }, [selectedCat, searchQuery]);

  // 出题池：只用可出题的词条，并跟随分类筛选
  const quizPool = filteredWords;

  const progress = useMemo(() => summarizeProgress(stats, QUIZ_POOL), [stats]);
  const filteredGroups = useMemo(() => IDIOM_GROUPS.filter(g => {
    const match = [g.title, g.axis, ...g.members.flat()].some(text => text.includes(searchQuery.trim()));
    const p = groupProgress(learning, g.id);
    return match && (groupFilter === 'all'
      || groupFilter === 'gd' && g.members.some(([word]) => lookupWord(word)?.references.some(r => r.region === '广东'))
      || groupFilter === 'new' && p.right + p.wrong === 0
      || groupFilter === 'wrong' && p.wrong > 0);
  }), [searchQuery, groupFilter, learning]);

  // 抽下一题：按掌握权重选词，题型由引擎在该词支持的范围内加权挑选
  const drawQuestion = useCallback((recent) => {
    for (let i = 0; i < 12; i++) {
      const target = pickNextTarget(quizPool, stats, recent);
      if (!target) break;
      const q = buildQuestion(target, enabledKinds, QUIZ_POOL);
      if (q) return q;
    }
    return null;
  }, [enabledKinds, quizPool, stats]);

  const nextGroupQuestion = useCallback(() => {
    if (groupScope) {
      const group = IDIOM_GROUPS.find(g => g.id === groupScope);
      setQuestion(groupQuestion(group, lookupWord, Math.random, question?.id));
      setUserChoice(null); setShowExplanation(false);
      return;
    }
    const candidates = filteredGroups.filter(g => g.id !== question?.groupId);
    const available = candidates.length ? candidates : filteredGroups;
    const q = available.length ? groupQuestion(available[Math.floor(Math.random() * available.length)], lookupWord) : null;
    setQuestion(q); setUserChoice(null); setShowExplanation(false);
  }, [question?.groupId, question?.id, groupScope, filteredGroups]);

  const nextQuestion = useCallback(() => {
    if (learningMode === 'groups') return nextGroupQuestion();
    const q = drawQuestion(recentIds);
    setQuestion(q); setUserChoice(null); setShowExplanation(false);
    if (q) setRecentIds(prev => [q.target.id, ...prev].slice(0, 20));
  }, [drawQuestion, recentIds, learningMode, nextGroupQuestion]);

  const startTest = () => {
    setGroupScope(null);
    setTestMode(true); setRound({ asked: 0, right: 0 }); setUserChoice(null); setShowExplanation(false);
    const q = learningMode === 'groups'
      ? (filteredGroups.length ? groupQuestion(filteredGroups[Math.floor(Math.random() * filteredGroups.length)], lookupWord) : null)
      : drawQuestion([]);
    setQuestion(q);
    setRecentIds(q && !q.groupId ? [q.target.id] : []);
  };

  const practiceGroup = group => {
    setGroupScope(group.id); setTestMode(true); setRound({ asked: 0, right: 0 });
    setQuestion(groupQuestion(group, lookupWord)); setUserChoice(null); setShowExplanation(false);
  };
  const practiceWord = item => {
    setLearningMode('single');
    const q = buildQuestion(item, ['reverse'], QUIZ_POOL);
    setQuestion(q); setTestMode(true); setUserChoice(null); setShowExplanation(false);
    setRound({ asked: 0, right: 0 }); setRecentIds(q ? [item.id] : []);
  };

  const handleChoice = (option) => {
    if (showExplanation || !question) return;
    setUserChoice(option);
    setShowExplanation(true);
    const correct = option.correct;
    setRound(r => ({ asked: r.asked + 1, right: r.right + (correct ? 1 : 0) }));

    addEntry({ type: 'vocab', module: '词汇练习', count: 1, correct: correct ? 1 : 0 });
    if (question.groupId) {
      const next = recordAnswer(learning, question, question.options.find(o => o.id === option.id)?.text);
      saveLearning(next);
      return;
    }
    const id = question.target.id;
    setStats(prev => {
      const cur = prev[id] || { right: 0, wrong: 0, streak: 0 };
      const next = {
        ...prev,
        [id]: correct
          ? { right: cur.right + 1, wrong: cur.wrong, streak: (cur.streak || 0) + 1 }
          : { right: cur.right, wrong: cur.wrong + 1, streak: 0 },
      };
      cloudSet(STATS_KEY, next);
      return next;
    });
  };

  const toggleMastered = (item) => {
    const ids = new Set((item.legacyIds || [item.id]).map(String));
    const next = masteredIds.some(id => ids.has(String(id)))
      ? masteredIds.filter(id => !ids.has(String(id)))
      : [...masteredIds, item.id];
    setMasteredIds(next);
    cloudSet(MASTERED_KEY, next);
  };

  const toggleKind = (kind) => {
    setEnabledKinds(prev => {
      // 至少保留一种题型
      const next = prev.includes(kind)
        ? (prev.length === 1 ? prev : prev.filter(k => k !== kind))
        : [...prev, kind];
      cloudSet(KINDS_KEY, next);
      return next;
    });
  };

  return (
    <div className="idiom-study space-y-8 pb-12">
      <div className="space-y-6">
          {/* 扩展包装载诊断：生成的 pack 有问题时立刻可见，避免静默失败 */}
          {(PACK_DIAGNOSTICS.errors.length > 0 || PACK_DIAGNOSTICS.warnings.length > 0) && (
            <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 space-y-1.5">
              <p className="text-xs font-black text-amber-800">
                词库扩展包提示（已生效 {PACK_DIAGNOSTICS.packs.length} 个）
              </p>
              {PACK_DIAGNOSTICS.errors.slice(0, 5).map((e, i) => (
                <p key={`e${i}`} className="text-[11px] font-bold text-rose-600">✗ {e}</p>
              ))}
              {PACK_DIAGNOSTICS.warnings.slice(0, 5).map((w, i) => (
                <p key={`w${i}`} className="text-[11px] text-amber-700">⚠ {w}</p>
              ))}
              {PACK_DIAGNOSTICS.errors.length + PACK_DIAGNOSTICS.warnings.length > 10 && (
                <p className="text-[10px] text-slate-400">
                  其余 {PACK_DIAGNOSTICS.errors.length + PACK_DIAGNOSTICS.warnings.length - 10} 条见浏览器控制台
                </p>
              )}
            </div>
          )}

          <div className="idiom-toolbar">
            <div role="group" aria-label="学习方式" className="idiom-switch">
              {[['groups', '成组辨析'], ['single', '单词学习']].map(([mode, label]) => (
                <button key={mode} aria-pressed={learningMode === mode}
                  onClick={() => { setLearningMode(mode); setTestMode(false); setSearchQuery(''); }}
                  >{label}</button>
              ))}
            </div>
            <button onClick={() => testMode ? setTestMode(false) : startTest()}
              className="idiom-action">
              {testMode ? <BookOpen size={16} /> : <Trophy size={16} />}
              {testMode ? '返回词库' : learningMode === 'groups' ? '开始成组练习' : '开始单词练习'}
            </button>
          </div>

          {/* 模式一：考场真题秒杀模式 */}
          {testMode ? (
            <div className="idiom-quiz space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#e8d5b0] pb-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="w-3 h-3 rounded-full bg-[#2c261c]" />
                  <h3 className="text-lg font-black">{learningMode === 'groups' ? '成组语境辨析' : '单词回忆练习'} · 第 {round.asked + (showExplanation ? 0 : 1)} 题</h3>
                  {question && (
                    <span className="text-[10px] font-black px-2 py-1 rounded-md bg-[#1a1a1a] text-white">
                      {question.kindLabel}
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {/* 题型开关：来自注册表，词库补了新字段就会自动多出选项 */}
                  {learningMode === 'single' && <div className="flex flex-wrap items-center gap-1 bg-[#e8cf9f] p-1 rounded-xl border border-[#e8d5b0]">
                    {availability.map(({ id, label, count }) => (
                      <button
                        key={id}
                        onClick={() => toggleKind(id)}
                        title={`${label} · 可出 ${count} 题`}
                        className={`px-2.5 py-1.5 rounded-lg text-[10px] font-black transition-all ${
                          enabledKinds.includes(id)
                            ? 'bg-[#1a1a1a] text-white'
                            : 'text-slate-400 hover:text-slate-600'
                        }`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>}
                  <span className="text-xs font-black px-3 py-1.5 bg-amber-50 text-amber-600 rounded-full tabular-nums">
                    本轮 {round.right} / {round.asked}
                  </span>
                </div>
              </div>

              {!question ? (
                <div className="py-16 text-center space-y-3">
                  <p className="text-sm font-black text-slate-400">当前筛选下没有足够的词条出题</p>
                  <button
                    onClick={() => { setSelectedCat('all'); setSearchQuery(''); setTestMode(false); }}
                    className="px-5 py-2.5 bg-[#1a1a1a] text-white rounded-xl text-xs font-black"
                  >
                    返回全部词条
                  </button>
                </div>
              ) : (
              <>
              {/* 题目展示 */}
              <div className="space-y-4">
                <div className="idiom-prompt p-5 rounded-2xl">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400 block mb-2">
                    {question.promptLabel}
                  </span>
                  <p className={`font-bold text-[#1a1a1a] leading-relaxed ${
                    question.bigPrompt ? 'text-3xl font-black tracking-tight' : 'text-base'
                  }`}>
                    {question.groupId ? question.stem : (question.quotePrompt ? `“${question.prompt}”` : question.prompt)}
                  </p>
                  <div className="mt-3 flex items-center space-x-2">
                    <span className="text-[10px] font-black px-2.5 py-1 rounded-md bg-[#1a1a1a] text-white">
                      {question.groupId ? '成语辨析组' : `陷阱归类：${question.target.category}`}
                    </span>
                    {question.target?.page && (
                      <span className="text-[10px] font-bold text-slate-400">原书 P{question.target.page}</span>
                    )}
                  </div>
                </div>

                {/* 4 个选项 */}
                <div className={`grid gap-3 pt-2 ${
                  question.wideOptions ? 'grid-cols-1' : 'grid-cols-1 md:grid-cols-2'
                }`}>
                  {question.options.map((opt, i) => {
                    const isSelected = userChoice && userChoice.id === opt.id;
                    const isCorrect = opt.correct;
                    let btnStyle = 'border-[#e8d5b0] bg-white hover:border-slate-300 text-[#1a1a1a]';

                    if (showExplanation) {
                      if (isCorrect) btnStyle = 'border-emerald-500 bg-emerald-50 text-emerald-900 font-black';
                      else if (isSelected) btnStyle = 'border-rose-500 bg-rose-50 text-rose-900 font-black';
                      else btnStyle = 'border-[#e8d5b0] bg-white text-slate-400';
                    }

                    return (
                      <button
                        key={`${opt.id}-${i}`}
                        disabled={showExplanation}
                        onClick={() => handleChoice(opt)}
                        data-result={showExplanation ? (isCorrect ? 'correct' : isSelected ? 'wrong' : 'other') : undefined}
                        className={`idiom-option p-5 rounded-2xl border text-left transition-all flex items-start justify-between gap-3 ${btnStyle}`}
                      >
                        <span className="flex items-start gap-3">
                          <span className="text-xs font-black text-slate-400 mt-0.5">{'ABCD'[i]}</span>
                          <span className={question.wideOptions ? 'text-sm font-bold leading-relaxed' : 'text-lg font-black'}>
                            {opt.text}
                          </span>
                        </span>
                        {showExplanation && isCorrect && <CheckCircle2 size={18} className="text-emerald-600 flex-shrink-0" />}
                        {showExplanation && isSelected && !isCorrect && <XCircle size={18} className="text-rose-500 flex-shrink-0" />}
                      </button>
                    );
                  })}
                </div>
              </div>
              </>
              )}

              {/* 答后解析：核心是把 4 个选项逐一辨析清楚。
                  原来这里展示 misunderstanding/correct_usage/hot_topic_link，
                  但 523/527 条都是同一套模板文字，看了学不到东西，故不再展示。 */}
              {showExplanation && question && (
                <div className="idiom-explanation p-5 rounded-2xl space-y-4 animate-fadeIn">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <h4 className="text-sm font-black flex items-center gap-2">
                      {userChoice?.correct ? (
                        <>
                          <CheckCircle2 size={16} className="text-emerald-600" />
                          <span className="text-emerald-900">答对了 · {question.target.word}</span>
                        </>
                      ) : (
                        <>
                          <XCircle size={16} className="text-rose-500" />
                          <span className="text-rose-900">
                            答错 · 正确答案是 {question.target.word}
                          </span>
                        </>
                      )}
                      {(stats[question.target.id]?.streak || 0) >= MASTERY_STREAK && (
                        <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-emerald-600 text-white">
                          已连对 {stats[question.target.id].streak} 次
                        </span>
                      )}
                    </h4>
                    <button
                      onClick={nextQuestion}
                      autoFocus
                      className="idiom-action"
                    >
                      <span>{groupScope && !IDIOM_GROUPS.find(g => g.id === groupScope)?.quizzes?.length ? '再练一次' : '下一题'}</span>
                      <ArrowRight size={14} />
                    </button>
                  </div>

                  {question.reason && <p className="text-sm leading-relaxed text-slate-700">{question.reason}</p>}

                  {/* 逐项辨析：这才是真正能学到词的地方 */}
                  <div className="space-y-2 bg-[#efddba] p-4 rounded-xl border border-emerald-100">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center gap-1.5">
                      <Target size={12} /> {question.options.length} 个选项逐一辨析
                    </p>
                    {question.options.map((opt, i) => {
                      const w = opt.word;
                      return (
                        <div
                          key={`ex-${opt.id}-${i}`}
                          className={`text-xs leading-relaxed p-2.5 rounded-lg border ${
                            opt.correct
                              ? 'border-emerald-200 bg-emerald-50/70'
                              : userChoice?.id === opt.id
                                ? 'border-rose-200 bg-rose-50/70'
                                : 'border-[#e8d5b0] bg-[#e8cf9f]'
                          }`}
                        >
                          <span className="font-black text-[#1a1a1a]">{w.word}</span>
                          {opt.correct && <span className="ml-1.5 text-[10px] font-black text-emerald-600">✓ 本题答案</span>}
                          {userChoice?.id === opt.id && !opt.correct && (
                            <span className="ml-1.5 text-[10px] font-black text-rose-500">✗ 你选的</span>
                          )}
                          <span className="text-slate-600">
                            {w.explanation ? `：${w.explanation}` : '：（书中作为对比词出现，无独立释义）'}
                          </span>
                        </div>
                      );
                    })}
                  </div>

                  {/* 补充信息：词条上有哪些就展示哪些。
                      pack 补上 trap/usage/examples 后会自动出现在这里。 */}
                  {(() => {
                    const t = question.target;
                    const extras = [
                      t.trap && { key: 'trap', label: '典型误用陷阱', text: t.trap },
                      t.usage && { key: 'usage', label: '用法要点', text: t.usage },
                      t.antonyms?.length && { key: 'ant', label: '反义词', text: t.antonyms.join('、') },
                      // 当前题就是挖空题时不重复展示同一句
                      question.kind !== 'cloze' && t.cloze?.length && {
                        key: 'cloze', label: '原书例句',
                        text: t.cloze[0].replace(/____/g, t.word),
                      },
                      question.kind !== 'example' && t.examples?.length && {
                        key: 'ex', label: '例句', text: t.examples[0],
                      },
                    ].filter(Boolean);
                    if (!extras.length) return null;
                    return (
                      <div className="space-y-1.5 bg-[#efddba] p-3 rounded-xl border border-emerald-100">
                        {extras.map((x) => (
                          <p key={x.key} className="text-xs text-slate-700 leading-relaxed">
                            <strong className="text-slate-800">【{x.label}】</strong>
                            <em>{x.text}</em>
                          </p>
                        ))}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          ) : learningMode === 'groups' ? (
            <div className="space-y-4">
              <div className="idiom-toolbar">
                <label className="idiom-search">
                  <Search size={16} />
                  <input aria-label="搜索辨析组" placeholder="搜索成语或辨析重点…" value={searchQuery}
                    onChange={e => setSearchQuery(e.target.value)} />
                </label>
                <p className="idiom-muted">{IDIOM_GROUPS.length} 组 · {GROUPED_WORDS.size} 个词 · 按辨析关系分组，不固定词数</p>
              </div>
              <div className="idiom-filters" role="group" aria-label="辨析组筛选">
                {[['all', '全部辨析'], ['gd', '含广东真题词'], ['new', '尚未练习'], ['wrong', '有过错题']].map(([id, label]) =>
                  <button key={id} className="idiom-filter" aria-pressed={groupFilter === id} onClick={() => setGroupFilter(id)}>{label}</button>)}
                <span className="idiom-muted">显示 {filteredGroups.length} 组 · 点击卡片展开对照</span>
              </div>
              <div className="idiom-catalog">
                {filteredGroups.map(group => {
                  const p = groupProgress(learning, group.id);
                  const gd = group.members.some(([word]) => lookupWord(word)?.references.some(r => r.region === '广东'));
                  return <article key={group.id} className="idiom-group">
                    <details name="idiom-group-detail">
                      <summary>
                        <div className="idiom-overline"><span>{gd ? '广东真题选项词 · 辨析整理' : '易混词辨析'}</span><span>{group.members.length} 词</span></div>
                        <h3>{group.title}</h3>
                        <div className="idiom-chips">{group.members.map(([word]) => <span key={word}>{word}</span>)}</div>
                        <p className="idiom-axis">{group.axis}</p>
                        <div className="idiom-detail-hint"><span>展开词义、搭配与例句</span><ChevronDown className="idiom-chevron" size={16} /></div>
                      </summary>
                      <div className="idiom-comparison" data-count={group.members.length}>
                        {group.members.map(([word, explanation, usage, example]) => <section key={word} className="idiom-member">
                          <h4>{word}</h4><p>{explanation}</p><p className="idiom-key">{usage}</p>
                          <p className="idiom-example">例：{example}</p>
                          <WordSources word={lookupWord(word)} />
                          <button className="idiom-link mt-3" onClick={() => practiceWord(lookupWord(word))}>单独练这个词</button>
                        </section>)}
                      </div>
                    </details>
                    <div className="idiom-footer">
                      <span className="idiom-muted">{p.right + p.wrong ? `答对 ${p.right} · 答错 ${p.wrong}` : '尚未练习'} · {1 + (group.quizzes?.length || 0)} 道小测</span>
                      <button className="idiom-action" onClick={() => practiceGroup(group)}>练这一组 <ArrowRight size={14} /></button>
                    </div>
                  </article>;
                })}
              </div>
              {!filteredGroups.length && <p className="py-12 text-center idiom-muted">没有找到相应辨析组，试试单词学习或其他关键词。</p>}
              <p className="idiom-muted">小测为原创学习练习，按实际词数出题；少选项练习和重复答题不代表考试掌握度。</p>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="idiom-toolbar">
                <label className="idiom-search">
                  <Search size={16} />
                  <input aria-label="搜索单词" placeholder="搜索词语或释义..." value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
                </label>
                <p className="idiom-muted">已练 {progress.total - progress.untouched} / {progress.total} 词<br />仅为本页练习记录，不代表考试掌握度</p>
              </div>
              <div className="idiom-filters" role="group" aria-label="词库筛选">
                {categories.map(c => <button key={c.id} className="idiom-filter" aria-pressed={selectedCat === c.id} onClick={() => setSelectedCat(c.id)}>{c.name} <span className="opacity-70">{c.count}</span></button>)}
              </div>
              <details className="idiom-source">
                <summary>收录与来源说明 · 当前显示 {filteredWords.length} 个词</summary>
                <p>{idiomEvidence.scope}。重点整理包含成组词与单独补充词；不是完整考纲清单。</p>
                <p>已收集广东卷的 {idiomEvidence.gdCoverage?.candidates} 个四字及以上选项词、完整联句已收录；此统计不代表覆盖全部公考词汇。</p>
              </details>
              <div className="idiom-catalog">
                {filteredWords.map(item => {
                  const isMarked = (item.legacyIds || [item.id]).some(id => masteredIds.map(String).includes(String(id)));
                  const st = stats[item.id];
                  const rivals = [...new Set([...(item.rivals || []), ...(item.rivals_weak || [])])];
                  return <article key={item.id} className="idiom-word-card">
                    <div className="idiom-overline">
                      <span>{item.references.some(r => r.region === '广东') ? '广东真题选项词' : item.curated ? '重点整理' : '扩展积累'}{zhentiHits(item) > 0 ? ` · ${zhentiHits(item)} 条记录` : ''}</span>
                      <button onClick={() => toggleMastered(item)} aria-pressed={isMarked} title={isMarked ? '取消已读标记' : '标记已读（不计入掌握度）'}><CheckCircle2 size={17} className={isMarked ? 'text-[#5d7138]' : 'text-[#947b58]'} /></button>
                    </div>
                    <h3>{item.word}</h3>
                    {item.variants?.length > 0 && <p className="idiom-muted">又作：{item.variants.join('、')}</p>}
                    <p className="idiom-definition">{item.explanation}</p>
                    {item.usage && <p className="idiom-key text-sm leading-relaxed mt-3">{item.usage}</p>}
                    <details>
                      <summary>例句、易混词与出处</summary>
                      <div className="space-y-3 mt-3 text-sm leading-relaxed">
                        {item.trap && <p className="idiom-key">注意：{item.trap}</p>}
                        {item.examples?.map((e, i) => <p className="idiom-example" key={i}>例：{e}</p>)}
                        {!item.examples?.length && item.cloze?.map((e, i) => <p key={i}>例：{e.replace(/____/g, item.word)}</p>)}
                        {rivals.length > 0 && <div><p className="idiom-muted mb-1">相关易混词</p>{rivals.map(r => <p key={r}><strong>{r}</strong>{lookupWord(r)?.explanation ? `：${lookupWord(r).explanation}` : '（待补释义）'}</p>)}</div>}
                        <WordSources word={item} />
                        {item.page && <p className="idiom-muted">原书 P{item.page}</p>}
                      </div>
                    </details>
                    <div className="idiom-footer">
                      <span className="idiom-muted">{st ? `答对 ${st.right} · 答错 ${st.wrong}` : isMarked ? '已读 · 未练' : '未练习'}</span>
                      <button className="idiom-action" onClick={() => practiceWord(item)}>练这个词 <ArrowRight size={14} /></button>
                    </div>
                  </article>;
                })}
              </div>
              {!filteredWords.length && <p className="py-12 text-center idiom-muted">没有找到词语，可切换到全部积累或调整关键词。</p>}
            </div>
          )}
        </div>
    </div>
  );
}
