import { useState, useMemo } from 'react';
import { BookOpen, Search, CheckCircle2, Bookmark, Zap, ArrowRight, Trophy, Sparkles, HelpCircle, Flame, ShieldAlert, Lightbulb } from 'lucide-react';
import rawWordsData from '../copybook/words_data_enriched.json';
import { cloudGet, cloudSet } from '../cloudStorage.js';

const MASTERED_KEY = 'vocab_mastered_ids_v1';

export default function StudyBoost() {
  const [activeSubTab, setActiveSubTab] = useState('vocab'); // 'vocab'
  const [masteredIds, setMasteredIds] = useState(() => cloudGet(MASTERED_KEY, []));
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCat, setSelectedCat] = useState('all');
  const [testMode, setTestMode] = useState(false);
  const [currentQuestionIndex, setCurrentQuestionIndex] = useState(0);
  const [userChoice, setUserChoice] = useState(null);
  const [showExplanation, setShowExplanation] = useState(false);
  const [testScore, setTestScore] = useState(0);
  const [expandedWordId, setExpandedWordId] = useState(null);

  // 分类列表
  const categories = [
    { id: 'all', name: '全部积累', count: rawWordsData.length },
    { id: '望文生义陷阱', name: '⚠️ 望文生义陷阱', count: rawWordsData.filter(w => w.category === '望文生义陷阱').length },
    { id: '褒贬误用辨析', name: '⚖️ 褒贬误用辨析', count: rawWordsData.filter(w => w.category === '褒贬误用辨析').length },
    { id: '易混实词/成语辨析', name: '🔍 易混/实词辨析', count: rawWordsData.filter(w => w.category === '易混实词/成语辨析').length },
    { id: '适用对象误用', name: '🎯 适用对象误用', count: rawWordsData.filter(w => w.category === '适用对象误用').length },
    { id: '语意重复与语境限制', name: '🚫 语意重复/语境限制', count: rawWordsData.filter(w => w.category === '语意重复与语境限制').length },
  ];

  // 过滤词汇列表
  const filteredWords = useMemo(() => {
    return rawWordsData.filter(w => {
      const matchCat = selectedCat === 'all' || w.category === selectedCat;
      const matchSearch = w.word.includes(searchQuery) || w.explanation.includes(searchQuery) || (w.misunderstanding && w.misunderstanding.includes(searchQuery));
      return matchCat && matchSearch;
    });
  }, [selectedCat, searchQuery]);

  const toggleMastered = (id) => {
    let next;
    if (masteredIds.includes(id)) {
      next = masteredIds.filter(i => i !== id);
    } else {
      next = [...masteredIds, id];
    }
    setMasteredIds(next);
    cloudSet(MASTERED_KEY, next);
  };

  // 生成混淆测试题
  const generateQuestion = (index) => {
    const targetWord = filteredWords[index % filteredWords.length] || rawWordsData[0];
    const dists = rawWordsData.filter(w => w.id !== targetWord.id).sort(() => 0.5 - Math.random()).slice(0, 3);
    const options = [targetWord, ...dists].sort(() => 0.5 - Math.random());
    return { targetWord, options };
  };

  const currentQuestion = useMemo(() => generateQuestion(currentQuestionIndex), [currentQuestionIndex, filteredWords]);

  const handleChoice = (option) => {
    setUserChoice(option.id);
    setShowExplanation(true);
    if (option.id === currentQuestion.targetWord.id) {
      setTestScore(s => s + 1);
    }
  };

  const nextQuestion = () => {
    setUserChoice(null);
    setShowExplanation(false);
    setCurrentQuestionIndex(i => i + 1);
  };

  const masteredRate = Math.round((masteredIds.length / rawWordsData.length) * 100) || 0;

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
          <span>言语理解词语高频考点库 (527+ 考点)</span>
        </button>
      </div>

      {activeSubTab === 'vocab' && (
        <div className="space-y-8">
          {/* 顶部 Header Banner */}
          <div className="bg-gradient-to-r from-[#1a1a1a] via-[#2a2a2a] to-[#3a2e0a] text-white p-8 rounded-[2.5rem] shadow-xl relative overflow-hidden">
            <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
              <div>
                <div className="flex items-center space-x-3 mb-2">
                  <span className="px-3 py-1 rounded-full bg-[#fbc02d]/20 text-[#fbc02d] text-xs font-black uppercase tracking-widest flex items-center gap-1.5">
                    <Zap size={14} /> 混血王子黑魔法 · 考场实战解构
                  </span>
                  <span className="text-xs font-bold text-white/50">含【怎么误解】+【正确用法】+【时政热词】</span>
                </div>
                <h2 className="text-3xl font-black italic tracking-tight">言语理解 · 词语高频考点库</h2>
                <p className="text-sm font-medium text-white/60 mt-2 max-w-2xl">
                  不搞传统虚无词条！针对出题人挖坑逻辑，深度剖析<strong>“怎么误解”</strong>与<strong>“黑魔法破局”</strong>，结合 2025/2026 最新公考时政热词！
                </p>
              </div>
              
              <div className="flex items-center space-x-4">
                <div className="bg-white/10 backdrop-blur-md px-5 py-3 rounded-2xl text-center border border-white/10">
                  <p className="text-[10px] font-black uppercase tracking-widest text-white/60">已斩获/掌握</p>
                  <p className="text-2xl font-black italic text-[#fbc02d] tabular-nums">{masteredIds.length} <span className="text-xs text-white/50">/ {rawWordsData.length}</span></p>
                </div>
                <button
                  onClick={() => {
                    setTestMode((v) => !v);
                    setCurrentQuestionIndex(0);
                    setTestScore(0);
                    setUserChoice(null);
                    setShowExplanation(false);
                  }}
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
              <div className="flex items-center justify-between border-b border-[#f2f0e9] pb-4">
                <div className="flex items-center space-x-3">
                  <span className="w-3 h-3 rounded-full bg-[#fbc02d]" />
                  <h3 className="text-lg font-black italic">考场黑魔法速练 · 第 {currentQuestionIndex + 1} 题</h3>
                </div>
                <span className="text-xs font-black px-3 py-1 bg-amber-50 text-amber-600 rounded-full">
                  秒杀正确率：{testScore} / {currentQuestionIndex + (showExplanation ? 1 : 0)}
                </span>
              </div>

              {/* 题目展示 */}
              <div className="space-y-4">
                <div className="bg-[#f9f8f6] p-6 rounded-2xl border border-[#f2f0e9]">
                  <span className="text-xs font-black uppercase tracking-widest text-slate-400 block mb-2">【题目释义】请选择对应的正确成语/词语：</span>
                  <p className="text-base font-bold text-[#1a1a1a] leading-relaxed">
                    “{currentQuestion.targetWord.explanation}”
                  </p>
                  <div className="mt-3 flex items-center space-x-2">
                    <span className="text-[10px] font-black px-2.5 py-1 rounded-md bg-[#1a1a1a] text-white">
                      陷阱归类：{currentQuestion.targetWord.category}
                    </span>
                  </div>
                </div>

                {/* 4 个选项 */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                  {currentQuestion.options.map((opt) => {
                    const isSelected = userChoice === opt.id;
                    const isCorrect = opt.id === currentQuestion.targetWord.id;
                    let btnStyle = 'border-[#f2f0e9] bg-white hover:border-slate-300 text-[#1a1a1a]';

                    if (showExplanation) {
                      if (isCorrect) btnStyle = 'border-emerald-500 bg-emerald-50 text-emerald-900 font-black';
                      else if (isSelected) btnStyle = 'border-rose-500 bg-rose-50 text-rose-900 font-black';
                    }

                    return (
                      <button
                        key={opt.id}
                        disabled={showExplanation}
                        onClick={() => handleChoice(opt)}
                        className={`p-5 rounded-2xl border text-left transition-all flex items-center justify-between ${btnStyle}`}
                      >
                        <span className="text-lg font-black">{opt.word}</span>
                        {showExplanation && isCorrect && <CheckCircle2 size={18} className="text-emerald-600" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* 富化深度解析 */}
              {showExplanation && (
                <div className="bg-emerald-50/60 border border-emerald-200/80 p-6 rounded-2xl space-y-4 animate-fadeIn">
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-black text-emerald-900 flex items-center gap-2">
                      <CheckCircle2 size={16} className="text-emerald-600" />
                      <span>正确答案：{currentQuestion.targetWord.word}</span>
                    </h4>
                    <button
                      onClick={nextQuestion}
                      className="px-5 py-2.5 bg-[#1a1a1a] text-white rounded-xl text-xs font-black hover:bg-[#fbc02d] hover:text-black transition-colors flex items-center space-x-1.5"
                    >
                      <span>下一题</span>
                      <ArrowRight size={14} />
                    </button>
                  </div>

                  <div className="space-y-3 text-xs text-slate-700 bg-white p-4 rounded-xl border border-emerald-100">
                    <p><strong className="text-rose-600">【出题人怎么挖坑 / 常见误解】：</strong> {currentQuestion.targetWord.misunderstanding}</p>
                    <p><strong className="text-emerald-700">【考场黑魔法破局】：</strong> {currentQuestion.targetWord.correct_usage}</p>
                    <p><strong className="text-amber-700">【2025/2026 时政热词联动】：</strong> {currentQuestion.targetWord.hot_topic_link}</p>
                    <p><strong className="text-slate-800">【公考标准例句】：</strong> <em>“{currentQuestion.targetWord.example}”</em></p>
                  </div>
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
                    placeholder="搜索成语、实词、怎么误解或时政热词..."
                    className="w-full bg-white border border-[#f2f0e9] rounded-2xl pl-11 pr-4 py-3 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
                  />
                </div>

                {/* 统计进度条 */}
                <div className="flex items-center space-x-3 bg-white px-5 py-3 rounded-2xl border border-[#f2f0e9]">
                  <span className="text-xs font-black text-slate-400">掌握度进度:</span>
                  <div className="w-32 h-2.5 bg-[#f2f0e9] rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-[#fbc02d] to-[#ff6b6b] transition-all duration-500"
                      style={{ width: `${masteredRate}%` }}
                    />
                  </div>
                  <span className="text-xs font-black tabular-nums text-[#1a1a1a]">{masteredRate}%</span>
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

              {/* 词语列表 Cards Grid (富化版本) */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filteredWords.map((item) => {
                  const isMastered = masteredIds.includes(item.id);
                  const isExpanded = expandedWordId === item.id;
                  return (
                    <div
                      key={item.id}
                      className={`p-5 rounded-2xl border transition-all flex flex-col justify-between space-y-3 bg-white hover:border-slate-300 ${
                        isMastered ? 'border-emerald-200 bg-emerald-50/20' : 'border-[#f2f0e9]'
                      }`}
                    >
                      <div>
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] font-black px-2 py-0.5 rounded-md bg-[#1a1a1a]/5 text-slate-500">
                            {item.category}
                          </span>
                          <button
                            onClick={() => toggleMastered(item.id)}
                            className={`p-1.5 rounded-lg transition-colors ${
                              isMastered ? 'text-emerald-600 bg-emerald-100' : 'text-slate-300 hover:text-emerald-500'
                            }`}
                            title={isMastered ? '标记为未掌握' : '标记为已斩获'}
                          >
                            <CheckCircle2 size={16} />
                          </button>
                        </div>

                        <h4 className="text-xl font-black text-[#1a1a1a] tracking-tight">{item.word}</h4>
                        <p className="text-xs font-medium text-slate-600 mt-2 leading-relaxed bg-[#f9f8f6] p-3 rounded-xl border border-[#f2f0e9]">
                          <strong>【字典释义】：</strong>{item.explanation}
                        </p>

                        {/* 展开查看富化深度解析：怎么误解 / 正确用法 / 时政热词 */}
                        <div className="mt-3 space-y-2">
                          <button
                            onClick={() => setExpandedWordId(isExpanded ? null : item.id)}
                            className="w-full flex items-center justify-between text-[11px] font-black text-amber-700 bg-amber-50 px-3 py-2 rounded-xl hover:bg-amber-100 transition-colors"
                          >
                            <span className="flex items-center gap-1.5">
                              <Sparkles size={13} /> 考场黑魔法：怎么误解与破局
                            </span>
                            <span>{isExpanded ? '收起 ▲' : '展开 ▼'}</span>
                          </button>

                          {isExpanded && (
                            <div className="space-y-2.5 p-3 rounded-xl bg-amber-50/40 border border-amber-200/60 text-[11px] leading-relaxed animate-fadeIn">
                              <div className="space-y-1">
                                <p className="font-black text-rose-600 flex items-center gap-1">
                                  <ShieldAlert size={12} /> 【出题人怎么挖坑/常见误解】：
                                </p>
                                <p className="text-slate-700">{item.misunderstanding}</p>
                              </div>

                              <div className="space-y-1">
                                <p className="font-black text-emerald-700 flex items-center gap-1">
                                  <Lightbulb size={12} /> 【考场黑魔法破局】：
                                </p>
                                <p className="text-slate-700">{item.correct_usage}</p>
                              </div>

                              <div className="space-y-1">
                                <p className="font-black text-amber-800 flex items-center gap-1">
                                  <Flame size={12} /> 【2025/2026 公考时政热词联动】：
                                </p>
                                <p className="text-slate-700">{item.hot_topic_link}</p>
                              </div>

                              <div className="space-y-1 pt-1 border-t border-amber-200/50">
                                <p className="font-black text-slate-800">【公考例句示范】：</p>
                                <p className="text-slate-600 italic">“{item.example}”</p>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="pt-2 border-t border-[#f2f0e9] flex items-center justify-between text-[10px] font-bold text-slate-400">
                        <span>时政联想：{item.hot_topic_link.split('、')[0]}</span>
                        <span className="italic">{isMastered ? '✓ 已牢记' : '点击展开黑魔法'}</span>
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
