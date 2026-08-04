// AI 练题 — 批次列表首页
//
// 展示 Hermes 出完题并 import 进库的所有批次，含历史做题数据。

import { useEffect, useState } from 'react';
import { Target, RefreshCw, ChevronRight, BookOpen, Loader2, Sparkles, Clock, Trash2 } from 'lucide-react';
import { api } from '../api.js';
import AIQuizSession from './AIQuizSession.jsx';

// 相对时间（"3天前" 等）
const relTime = (iso) => {
  if (!iso) return null;
  const diff = Date.now() - new Date(iso + (iso.endsWith('Z') ? '' : 'Z')).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h} 小时前`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d} 天前`;
  return `${Math.floor(d / 30)} 个月前`;
};

// 正确率文字颜色
const accColor = (rate) => {
  if (rate >= 0.8) return 'text-green-600';
  if (rate >= 0.6) return 'text-[#fbc02d]';
  return 'text-red-500';
};

// 展示用的题组名。batch_id 是入库时的技术标识（路径/主键那一类），
// 不该露到界面上；真正给人看的是 Hermes 出题时写的题集名（source）。
// 这两个字段语义不同，这里只是在 source 缺失时退回 batch_id，免得卡片没标题。
const nameOf = (b) => b.source || b.batch_id;

const AIQuizHome = ({ onAnalyzeWithHermes }) => {
  const [batches, setBatches] = useState([]);
  const [loading, setLoading] = useState(true);
  // 正在打开的题组：{ batchId, reviewSessionId }。
  // reviewSessionId 不为空 = 这组以前交过卷，点进去先看当时的做题情况
  const [active, setActive] = useState(null);
  const [deleting, setDeleting] = useState(null);   // 正在删除的 batch_id
  const [errMsg, setErrMsg] = useState('');

  const reload = () => {
    setLoading(true);
    fetchBatches();
  };

  const fetchBatches = () => {
    let cancelled = false;
    (async () => {
      try {
        const rows = await api('/api/questions/meta/batches');
        if (!cancelled) setBatches(Array.isArray(rows) ? rows : []);
      } catch {
        if (!cancelled) setBatches([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  };

  useEffect(fetchBatches, []);

  // 删除整个题组（题目 + 作答记录一起删，练废的测试批次不该留着占列表）
  const handleDelete = async (b, e) => {
    // 卡片本身是「进入做题」的按钮，删除按钮嵌在里面，必须掐掉冒泡
    e.stopPropagation();
    e.preventDefault();
    if (deleting) return;

    const hasData = b.attempt_count > 0;
    const warn = hasData
      ? `确定删除题组「${nameOf(b)}」？\n\n这会一起删掉 ${b.count} 道题和 ${b.attempt_count} 条作答记录，不可恢复。`
      : `确定删除题组「${nameOf(b)}」？\n\n共 ${b.count} 道题，不可恢复。`;
    if (!confirm(warn)) return;

    setDeleting(b.batch_id);
    setErrMsg('');
    try {
      await api(`/api/questions/batch/${encodeURIComponent(b.batch_id)}`, { method: 'DELETE' });
      // 本地先摘掉，不等整表刷新，列表立刻少一行
      setBatches((prev) => prev.filter((x) => x.batch_id !== b.batch_id));
    } catch (err) {
      setErrMsg(err?.message || '删除失败');
    } finally {
      setDeleting(null);
    }
  };

  if (active) {
    return (
      <AIQuizSession
        batchId={active.batchId}
        batchName={nameOf(batches.find((b) => b.batch_id === active.batchId) || { batch_id: active.batchId })}
        reviewSessionId={active.reviewSessionId}
        onExit={() => { setActive(null); reload(); }}
        onAnalyzeWithHermes={onAnalyzeWithHermes}
      />
    );
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* 页头 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-[#1a1a1a] text-[#fbc02d] flex items-center justify-center">
            <Target size={18} />
          </div>
          <div>
            <h3 className="text-base font-black tracking-tight">AI 专项练题</h3>
            <p className="text-[11px] text-slate-400 font-medium">
              让 Hermes 出完题，在这里刷
            </p>
          </div>
        </div>
        <button
          onClick={reload}
          disabled={loading}
          className="flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-black text-[#999] hover:bg-black/5 hover:text-[#1a1a1a] transition-colors disabled:opacity-40"
          title="刷新"
        >
          {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
          <span>刷新</span>
        </button>
      </div>

      {errMsg && (
        <div className="px-4 py-2 rounded-xl bg-red-50 border border-red-200 text-xs font-bold text-red-700 flex justify-between">
          <span>{errMsg}</span>
          <button onClick={() => setErrMsg('')} className="ml-3 text-red-400 hover:text-red-700">✕</button>
        </div>
      )}

      {/* 批次列表 */}
      {loading && batches.length === 0 ? (
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-[#f2f0e9]">
          <Loader2 size={24} className="mx-auto text-[#fbc02d] animate-spin mb-3" />
          <p className="text-sm font-black uppercase tracking-widest text-slate-400">加载中…</p>
        </div>
      ) : batches.length === 0 ? (
        <div className="bg-white rounded-[2rem] p-10 text-center shadow-sm border border-[#f2f0e9]">
          <div className="w-14 h-14 mx-auto rounded-2xl bg-[#f2f0e9] text-slate-400 flex items-center justify-center mb-4">
            <Sparkles size={24} />
          </div>
          <h3 className="text-lg font-black italic mb-2">还没有 AI 出题批次</h3>
          <p className="text-sm text-slate-500 leading-relaxed mb-5 max-w-xs mx-auto">
            去 <strong>Hermes</strong> 对话框，输入你想练习的知识点，Hermes 会自动出题、验证并入库。
          </p>
          <div className="bg-[#f2f0e9] rounded-2xl p-4 text-left text-xs font-mono text-slate-600 mb-5">
            <p className="font-black text-[#1a1a1a] mb-1">示例指令（在 Hermes 里输入）：</p>
            <p>/quiz-pipeline 出5道翻译推理题，题集名 20260803_翻译推理强化一</p>
          </div>
          <button onClick={reload}
            className="bg-[#1a1a1a] text-white font-black px-6 py-3 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs">
            刷新检查
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {batches.map((b) => {
            const hasDone = b.done_count > 0;
            const acc = b.attempt_count > 0 ? b.correct_count / b.attempt_count : null;
            const progress = b.count > 0 ? b.done_count / b.count : 0;
            const timeStr = relTime(b.last_answered_at);

            const isDeleting = deleting === b.batch_id;
            // 做过的点进去是复盘，没做过的直接开做
            const open = { batchId: b.batch_id, reviewSessionId: b.last_session_id || null };

            return (
              // 卡片原来是 <button>，但删除按钮必须是真的 <button>，而 button 不能嵌
              // button（HTML 非法 + 点击行为打架）。所以外层降级成 div + role/键盘处理。
              <div
                key={b.batch_id}
                role="button"
                tabIndex={0}
                onClick={() => { if (!isDeleting) setActive(open); }}
                onKeyDown={(e) => {
                  if (isDeleting) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    setActive(open);
                  }
                }}
                className={`w-full text-left bg-white rounded-[1.75rem] p-6 shadow-sm border border-[#f2f0e9] transition-all group cursor-pointer focus:outline-none focus-visible:border-[#fbc02d] focus-visible:ring-2 focus-visible:ring-[#fbc02d]/40 ${
                  isDeleting ? 'opacity-40 pointer-events-none' : 'hover:border-[#fbc02d] hover:shadow-md'
                }`}
              >
                {/* 上行：图标 + 名称 + 删除 + 箭头 */}
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center space-x-3 min-w-0">
                    <div className="w-10 h-10 rounded-xl bg-[#f2f0e9] group-hover:bg-[#fbc02d] text-[#1a1a1a] flex items-center justify-center transition-colors flex-shrink-0">
                      <BookOpen size={16} />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-black truncate">{nameOf(b)}</p>
                    </div>
                  </div>
                  <div className="flex items-center flex-shrink-0 ml-3">
                    {/* 删除题组：测试用的批次留在列表里很碍事。
                        iPad 没有 hover，所以按钮常驻显示，不做 hover 才出现。 */}
                    <button
                      type="button"
                      onClick={(e) => handleDelete(b, e)}
                      disabled={isDeleting}
                      title="删除这个题组"
                      aria-label={`删除题组 ${nameOf(b)}`}
                      className="p-2 -m-0.5 rounded-xl text-[#ccc] hover:bg-red-50 hover:text-[#ef5350] active:bg-red-100 transition-colors disabled:opacity-50"
                    >
                      {isDeleting
                        ? <Loader2 size={15} className="animate-spin" />
                        : <Trash2 size={15} />}
                    </button>
                    <ChevronRight size={16} className="text-[#ccc] group-hover:text-[#1a1a1a] transition-colors ml-1" />
                  </div>
                </div>

                {/* 进度条 */}
                <div className="h-1 bg-[#f2f0e9] rounded-full overflow-hidden mb-3">
                  <div
                    className="h-full bg-[#fbc02d] rounded-full transition-all"
                    style={{ width: `${progress * 100}%` }}
                  />
                </div>

                {/* 下行：统计数据 */}
                <div className="flex items-center space-x-4 text-[11px] font-black">
                  {/* 题数/进度 */}
                  <span className="text-slate-400">
                    {hasDone ? (
                      <><span className="text-[#1a1a1a]">{b.done_count}</span> / {b.count} 题</>
                    ) : (
                      <span>{b.count} 题 · 未开始</span>
                    )}
                  </span>

                  {/* 正确率 */}
                  {acc !== null && (
                    <>
                      <span className="text-slate-200">·</span>
                      <span className={accColor(acc)}>
                        正确率 {Math.round(acc * 100)}%
                      </span>
                      <span className="text-slate-200">·</span>
                      <span className="text-slate-400">共答 {b.attempt_count} 次</span>
                    </>
                  )}

                  {/* 点进去会发生什么，先说清楚 */}
                  <span className="ml-auto pl-2 text-[10px] uppercase tracking-widest text-[#ccc] group-hover:text-[#1a1a1a] transition-colors shrink-0">
                    {b.last_session_id ? '点开复盘' : '开始做题'}
                  </span>

                  {/* 上次练习时间 */}
                  {timeStr && (
                    <>
                      <span className="text-slate-200">·</span>
                      <span className="flex items-center space-x-1 text-slate-400">
                        <Clock size={10} />
                        <span>{timeStr}</span>
                      </span>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {batches.length > 0 && (
        <p className="text-center text-[10px] font-black uppercase tracking-widest text-slate-300">
          共 {batches.length} 个批次 · 每次随机抽30题
        </p>
      )}
    </div>
  );
};

export default AIQuizHome;
