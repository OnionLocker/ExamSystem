import { useCallback, useState, useMemo } from 'react';
import { BookOpen, Search, CheckCircle2, Zap, ArrowRight, Trophy, Sparkles, ShieldAlert, Lightbulb, XCircle, RotateCcw, Target } from 'lucide-react';
import { cloudGet, cloudSet } from '../cloudStorage.js';
import {
  addEntryOncePerDay,
  bumpDailyCount,
  QUALITATIVE,
} from '../studyLog/studyLog.js';
import {
  ALL_WORDS,
  QUIZ_POOL,
  QUESTION_KINDS,
  MASTERY_STREAK,
  PACK_DIAGNOSTICS,
  buildQuestion,
  kindAvailability,
  pickNextTarget,
  summarizeProgress,
} from './vocabQuiz.js';

const MASTERED_KEY = 'vocab_mastered_ids_v1';
const STATS_KEY = 'vocab_stats_v1';
const KINDS_KEY = 'vocab_enabled_kinds_v1';

export default function StudyBoost() {
  const [activeSubTab, setActiveSubTab] = useState('vocab'); // 'vocab'
  const [masteredIds, setMasteredIds] = useState(() => cloudGet(MASTERED_KEY, []));
  // { [id]: { right, wrong, streak } } —— 答对才算掌握的依据
  const [stats, setStats] = useState(() => cloudGet(STATS_KEY, {}));
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCat, setSelectedCat] = useState('all');
  const [testMode, setTestMode] = useState(false);
  const [userChoice, setUserChoice] = useState(null);
  const [showExplanation, setShowExplanation] = useState(false);
  const [expandedWordId, setExpandedWordId] = useState(null);
  // 本轮统计
  const [round, setRound] = useState({ asked: 0, right: 0 });
  const [recentIds, setRecentIds] = useState([]);
  const [question, setQuestion] = useState(null);

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
    return [
      { id: 'all', name: '全部积累', count: ALL_WORDS.length },
      ...[...counts.entries()]
        .filter(([name]) => name)
        .sort((a, b) => b[1] - a[1])
        .map(([name, count]) => ({ id: name, name, count })),
    ];
  }, []);

  // 过滤词汇列表（浏览用，含无法出题的条目）
  const filteredWords = useMemo(() => {
    return ALL_WORDS.filter(w => {
      const matchCat = selectedCat === 'all' || w.category === selectedCat;
      const q = searchQuery.trim();
      const matchSearch = !q || w.word.includes(q) || (w.explanation || '').includes(q);
      return matchCat && matchSearch;
    });
  }, [selectedCat, searchQuery]);

  // 出题池：只用可出题的词条，并跟随分类筛选
  const quizPool = useMemo(() => {
    const p = selectedCat === 'all' ? QUIZ_POOL : QUIZ_POOL.filter(w => w.category === selectedCat);
    // 某个分类词太少凑不出 4 个选项时，回落到全库
    return p.length >= 4 ? p : QUIZ_POOL;
  }, [selectedCat]);

  const progress = useMemo(() => summarizeProgress(stats, QUIZ_POOL), [stats]);

  // 抽下一题：按掌握权重选词，题型由引擎在该词支持的范围内加权挑选
  const drawQuestion = useCallback((recent) => {
    for (let i = 0; i < 12; i++) {
      const target = pickNextTarget(quizPool, stats, recent);
      if (!target) break;
      const q = buildQuestion(target, enabledKinds, quizPool);
      if (q) return q;
    }
    return null;
  }, [enabledKinds, quizPool, stats]);

  const nextQuestion = useCallback(() => {
    const q = drawQuestion(recentIds);
    setQuestion(q);
    setUserChoice(null);
    setShowExplanation(false);
    if (q) setRecentIds(prev => [q.target.id, ...prev].slice(0, 20));
  }, [drawQuestion, recentIds]);

  const startTest = () => {
    setTestMode(true);
    setRound({ asked: 0, right: 0 });
    setUserChoice(null);
    setShowExplanation(false);
    const q = drawQuestion([]);
    setQuestion(q);
    setRecentIds(q ? [q.target.id] : []);
  };

  const handleChoice = (option) => {
    if (showExplanation || !question) return;
    setUserChoice(option);
    setShowExplanation(true);
    const correct = option.correct;
    const id = question.target.id;
    setRound(r => ({ asked: r.asked + 1, right: r.right + (correct ? 1 : 0) }));

    // 当天累计答满门槛题数，给一次定性热力（同一天只记一次）
    const answeredToday = bumpDailyCount('vocab');
    if (answeredToday >= QUALITATIVE.vocab.minCount) {
      addEntryOncePerDay('vocab', {
        module: QUALITATIVE.vocab.label,
        count: answeredToday,
        score: QUALITATIVE.vocab.score,
      });
    }
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

  const toggleMastered = (id) => {
    const next = masteredIds.includes(id)
      ? masteredIds.filter(i => i !== id)
      : [...masteredIds, id];
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

  const resetStats = () => {
    setStats({});
    cloudSet(STATS_KEY, {});
    setRound({ asked: 0, right: 0 });
  };

  // 掌握度以「答对才算」为准，不再用手动打勾的数量
  const masteredRate = progress.total
    ? Math.round((progress.mastered / progress.total) * 100)
    : 0;

  return (
    <div className="space-y-8 pb-12">
      {/* 子模块切换导航 */}
      <div className="flex items-center space-x-2 bg-white p-2 rounded-2xl border border-[#f2f0e9] w-fit">
        <button
          onClick={() => setActiveSubTab('vocab')}
          className={`px-6 py-3 rounded-xl text-xs font-black transition-all flex items-center space-x-2 ${
            activeSubTab === 'vocab' ? 'bg-[#1a1a1a] text-white shadow-md' : 'text-slate-500 hover:bg-[#f2f0e9]'
          }`}
        >
          <BookOpen size={16} />
          <span>言语理解词语高频考点库 ({QUIZ_POOL.length} 可考词条)</span>
        </button>
      </div>

      {activeSubTab === 'vocab' && (
        <div className="space-y-8">
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

          {/* 顶部 Header Banner */}
          <div className="bg-gradient-to-r from-[#1a1a1a] via-[#2a2a2a] to-[#3a2e0a] text-white p-8 rounded-[2.5rem] shadow-xl relative overflow-hidden">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <span className="px-3 py-1 rounded-full bg-[#fbc02d]/20 text-[#fbc02d] text-xs font-black uppercase tracking-widest flex items-center gap-1.5">
                    <Zap size={14} /> 三种考法 · 形近词强干扰
                  </span>
                  <span className="text-xs font-bold text-white/50">释义→选词 / 词→选释义 / 语境填空</span>
                </div>
                <h2 className="text-3xl font-black italic tracking-tight">言语理解 · 词语高频考点库</h2>
                <p className="text-sm font-medium text-white/60 mt-2 max-w-2xl">
                  干扰项一律取<strong>同字数的形近易混词</strong>（度过／渡过、情投意合／臭味相投），数字数猜不出答案；
                  <strong>连续答对 2 次</strong>才算真掌握，错过的词会加权重现。
                </p>
              </div>
              
              <div className="flex items-center space-x-4">
                <div className="bg-white/10 backdrop-blur-md px-5 py-3 rounded-2xl border border-white/10 flex items-center gap-4">
                  <div className="text-center">
                    <p className="text-[10px] font-black uppercase tracking-widest text-white/60">真掌握</p>
                    <p className="text-2xl font-black italic text-[#fbc02d] tabular-nums">{progress.mastered}</p>
                  </div>
                  <div className="w-px h-8 bg-white/15" />
                  <div className="text-center">
                    <p className="text-[10px] font-black uppercase tracking-widest text-white/60">待巩固</p>
                    <p className="text-2xl font-black italic text-rose-300 tabular-nums">{progress.shaky}</p>
                  </div>
                  <div className="w-px h-8 bg-white/15" />
                  <div className="text-center">
                    <p className="text-[10px] font-black uppercase tracking-widest text-white/60">未接触</p>
                    <p className="text-2xl font-black italic text-white/70 tabular-nums">{progress.untouched}</p>
                  </div>
                </div>
                <button
                  onClick={() => (testMode ? setTestMode(false) : startTest())}
                  className={`px-6 py-4 rounded-2xl font-black text-xs uppercase tracking-widest transition-all flex items-center space-x-2 shadow-lg ${
                    testMode ? 'bg-white text-black hover:bg-slate-200' : 'bg-[#fbc02d] text-black hover:brightness-110 shadow-[#fbc02d]/20'
                  }`}
                >
                  {testMode ? <BookOpen size={16} /> : <Trophy size={16} />}
                  <span>{testMode ? '返回考场卡片' : '开启秒杀考场刷题'}</span>
                </button>
              </div>
            </div>
          </div>

          {/* 模式一：考场真题秒杀模式 */}
          {testMode ? (
            <div className="bg-white rounded-[2.5rem] border border-[#f2f0e9] p-8 space-y-6 shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#f2f0e9] pb-4">
                <div className="flex items-center space-x-3">
                  <span className="w-3 h-3 rounded-full bg-[#fbc02d]" />
                  <h3 className="text-lg font-black italic">考场黑魔法速练 · 第 {round.asked + (showExplanation ? 0 : 1)} 题</h3>
                  {question && (
                    <span className="text-[10px] font-black px-2 py-1 rounded-md bg-[#1a1a1a] text-white">
                      {question.kindLabel}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {/* 题型开关：来自注册表，词库补了新字段就会自动多出选项 */}
                  <div className="flex items-center gap-1 bg-[#f9f8f6] p-1 rounded-xl border border-[#f2f0e9]">
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
                  </div>
                  <span className="text-xs font-black px-3 py-1.5 bg-amber-50 text-amber-600 rounded-full tabular-nums">
                    本轮 {round.right} / {round.asked}
                  </span>
                </div>
              </div>

              {!question ? (
                <div className="py-16 text-center space-y-3">
                  <p className="text-sm font-black text-slate-400">当前筛选下没有足够的词条出题</p>
                  <button
                    onClick={() => { setSelectedCat('all'); startTest(); }}
                    className="px-5 py-2.5 bg-[#1a1a1a] text-white rounded-xl text-xs font-black"
                  >
                    切回全部词条
                  </button>
                </div>
              ) : (
              <>
              {/* 题目展示 */}
              <div className="space-y-4">
                <div className="bg-[#f9f8f6] p-6 rounded-2xl border border-[#f2f0e9]">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400 block mb-2">
                    {question.promptLabel}
                  </span>
                  <p className={`font-bold text-[#1a1a1a] leading-relaxed ${
                    question.bigPrompt ? 'text-3xl font-black tracking-tight' : 'text-base'
                  }`}>
                    {question.quotePrompt ? `“${question.prompt}”` : question.prompt}
                  </p>
                  <div className="mt-3 flex items-center space-x-2">
                    <span className="text-[10px] font-black px-2.5 py-1 rounded-md bg-[#1a1a1a] text-white">
                      陷阱归类：{question.target.category}
                    </span>
                    {question.target.page && (
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
                    let btnStyle = 'border-[#f2f0e9] bg-white hover:border-slate-300 text-[#1a1a1a]';

                    if (showExplanation) {
                      if (isCorrect) btnStyle = 'border-emerald-500 bg-emerald-50 text-emerald-900 font-black';
                      else if (isSelected) btnStyle = 'border-rose-500 bg-rose-50 text-rose-900 font-black';
                      else btnStyle = 'border-[#f2f0e9] bg-white text-slate-400';
                    }

                    return (
                      <button
                        key={`${opt.id}-${i}`}
                        disabled={showExplanation}
                        onClick={() => handleChoice(opt)}
                        className={`p-5 rounded-2xl border text-left transition-all flex items-start justify-between gap-3 ${btnStyle}`}
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
                <div className="bg-emerald-50/60 border border-emerald-200/80 p-6 rounded-2xl space-y-4 animate-fadeIn">
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
                      className="px-5 py-2.5 bg-[#1a1a1a] text-white rounded-xl text-xs font-black hover:bg-[#fbc02d] hover:text-black transition-colors flex items-center space-x-1.5"
                    >
                      <span>下一题</span>
                      <ArrowRight size={14} />
                    </button>
                  </div>

                  {/* 逐项辨析：这才是真正能学到词的地方 */}
                  <div className="space-y-2 bg-white p-4 rounded-xl border border-emerald-100">
                    <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 flex items-center gap-1.5">
                      <Target size={12} /> 四个选项逐一辨析
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
                                : 'border-[#f2f0e9] bg-[#f9f8f6]'
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
                      <div className="space-y-1.5 bg-white p-3 rounded-xl border border-emerald-100">
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
          ) : (
            /* 模式二：分类浏览与富化卡片 */
            <div className="space-y-6">
              {/* 分类 Tabs & 搜索框 */}
              <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-4">
                {/* 搜索框 */}
                <div className="relative flex-1 max-w-md">
                  <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="搜索词语或释义..."
                    className="w-full bg-white border border-[#f2f0e9] rounded-2xl pl-11 pr-4 py-3 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
                  />
                </div>

                {/* 掌握度进度：以「答对才算」的真掌握为准 */}
                <div className="flex items-center space-x-3 bg-white px-5 py-3 rounded-2xl border border-[#f2f0e9]">
                  <span className="text-xs font-black text-slate-400">真掌握进度:</span>
                  <div className="w-32 h-2.5 bg-[#f2f0e9] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-[#fbc02d] to-[#ff6b6b] transition-all duration-500"
                      style={{ width: `${masteredRate}%` }}
                    />
                  </div>
                  <span className="text-xs font-black tabular-nums text-[#1a1a1a]">{masteredRate}%</span>
                  {round.asked === 0 && progress.mastered + progress.shaky > 0 && (
                    <button
                      onClick={resetStats}
                      title="清空答题记录，重新统计掌握度"
                      className="p-1.5 rounded-lg text-slate-300 hover:text-rose-500 hover:bg-rose-50 transition-colors"
                    >
                      <RotateCcw size={13} />
                    </button>
                  )}
                </div>
              </div>

              {/* 分类选择 Button Grid */}
              <div className="flex items-center gap-2 overflow-x-auto pb-2 scrollbar-none">
                {categories.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelectedCat(c.id)}
                    className={`px-4 py-2.5 rounded-xl text-xs font-black whitespace-nowrap transition-all flex items-center space-x-1.5 ${
                      selectedCat === c.id
                        ? 'bg-[#1a1a1a] text-white shadow-md'
                        : 'bg-white border border-[#f2f0e9] text-slate-600 hover:border-slate-300'
                    }`}
                  >
                    <span>{c.name}</span>
                    <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${selectedCat === c.id ? 'bg-white/20 text-white' : 'bg-[#f2f0e9] text-slate-500'}`}>
                      {c.count}
                    </span>
                  </button>
                ))}
              </div>

              {/* 词语列表 Cards Grid */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredWords.map((item) => {
                  const isMastered = masteredIds.includes(item.id);
                  const isExpanded = expandedWordId === item.id;
                  const st = stats[item.id];
                  const trulyMastered = (st?.streak || 0) >= MASTERY_STREAK;
                  const rivals = [...(item.rivals || []), ...(item.rivals_weak || [])];
                  return (
                    <div
                      key={item.id}
                      className={`p-5 rounded-2xl border transition-all flex flex-col justify-between space-y-3 bg-white hover:border-slate-300 ${
                        trulyMastered || isMastered ? 'border-emerald-200 bg-emerald-50/20' : 'border-[#f2f0e9]'
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-[#1a1a1a]/5 text-slate-500">
                            {item.category}
                          </span>
                          <div className="flex items-center gap-1">
                            {st && (st.right > 0 || st.wrong > 0) && (
                              <span
                                className="text-[10px] font-black tabular-nums px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-500"
                                title={`答对 ${st.right} 次 / 答错 ${st.wrong} 次`}
                              >
                                {st.right}✓ {st.wrong}✗
                              </span>
                            )}
                            <button
                              onClick={() => toggleMastered(item.id)}
                              className={`p-1.5 rounded-lg transition-colors ${
                                isMastered ? 'text-emerald-600 bg-emerald-100' : 'text-slate-300 hover:text-emerald-500'
                              }`}
                              title={isMastered ? '取消手动标记' : '手动标记为已记住'}
                            >
                              <CheckCircle2 size={16} />
                            </button>
                          </div>
                        </div>

                        <h4 className="text-xl font-black text-[#1a1a1a] tracking-tight">
                          {item.word}
                          {item.variants && item.variants.length > 0 && (
                            <span className="ml-1.5 text-xs font-bold text-slate-400">[{item.variants.join('/')}]</span>
                          )}
                        </h4>
                        <p className="text-xs font-medium text-slate-600 mt-2 leading-relaxed bg-[#f9f8f6] p-3 rounded-xl border border-[#f2f0e9]">
                          <strong>【释义】：</strong>{item.explanation}
                        </p>

                        {/* 展开：词条上有的信息都展示。
                            pack 补的 trap/usage/examples 会自动出现在这里，无需改 UI。 */}
                        {(rivals.length > 0 || item.cloze || item.trap || item.usage
                          || item.examples?.length || item.antonyms?.length || item.usable === false) && (
                          <div className="mt-3 space-y-2">
                            <button
                              onClick={() => setExpandedWordId(isExpanded ? null : item.id)}
                              className="w-full flex items-center justify-between text-[11px] font-black text-amber-700 bg-amber-50 px-3 py-2 rounded-xl hover:bg-amber-100 transition-colors"
                            >
                              <span className="flex items-center gap-1.5">
                                <Sparkles size={13} /> 易混辨析与例句
                              </span>
                              <span>{isExpanded ? '收起 ▲' : '展开 ▼'}</span>
                            </button>

                            {isExpanded && (
                              <div className="space-y-2.5 p-3 rounded-xl bg-amber-50/40 border border-amber-200/60 text-[11px] leading-relaxed animate-fadeIn">
                                {rivals.length > 0 && (
                                  <div className="space-y-1">
                                    <p className="font-black text-rose-600 flex items-center gap-1">
                                      <ShieldAlert size={12} /> 【易混词 · 考场最爱挖的坑】
                                    </p>
                                    <p className="text-slate-700">
                                      {rivals.map((r) => (
                                        <span key={r} className="inline-block mr-2 px-1.5 py-0.5 rounded bg-white border border-rose-200 font-black">
                                          {r}
                                        </span>
                                      ))}
                                    </p>
                                  </div>
                                )}

                                {item.trap && (
                                  <div className="space-y-1">
                                    <p className="font-black text-rose-600 flex items-center gap-1">
                                      <ShieldAlert size={12} /> 【典型误用陷阱】
                                    </p>
                                    <p className="text-slate-700">{item.trap}</p>
                                  </div>
                                )}

                                {item.usage && (
                                  <div className="space-y-1">
                                    <p className="font-black text-sky-700 flex items-center gap-1">
                                      <Target size={12} /> 【用法要点】
                                    </p>
                                    <p className="text-slate-700">{item.usage}</p>
                                  </div>
                                )}

                                {(item.cloze?.length || item.examples?.length) && (
                                  <div className="space-y-1">
                                    <p className="font-black text-emerald-700 flex items-center gap-1">
                                      <Lightbulb size={12} /> 【例句 · 〔〕内即本词】
                                    </p>
                                    {(item.cloze || []).map((c, ci) => (
                                      <p key={`c${ci}`} className="text-slate-700 italic">
                                        {c.replace(/____/g, `〔${item.word}〕`)}
                                      </p>
                                    ))}
                                    {(item.examples || []).map((e, ei) => (
                                      <p key={`e${ei}`} className="text-slate-700 italic">{e}</p>
                                    ))}
                                  </div>
                                )}

                                {item.antonyms?.length > 0 && (
                                  <p className="text-slate-700">
                                    <strong className="text-slate-800">【反义】</strong>{item.antonyms.join('、')}
                                  </p>
                                )}

                                {item.enriched_by?.length > 0 && (
                                  <p className="text-[10px] text-slate-400 pt-1 border-t border-amber-200/50">
                                    内容补充来源：{item.enriched_by.join('、')}
                                  </p>
                                )}

                                {item.usable === false && (
                                  <p className="text-[10px] text-slate-400 pt-1 border-t border-amber-200/50">
                                    该条目在原始 PDF 中解析不完整，已排除出题范围。
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="pt-2 border-t border-[#f2f0e9] flex items-center justify-between text-[10px] font-bold text-slate-400">
                        <span>原书 P{item.page}</span>
                        <span className="italic">
                          {trulyMastered ? `✓ 真掌握（连对${MASTERY_STREAK}次）` : st ? '待巩固' : '未接触'}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
