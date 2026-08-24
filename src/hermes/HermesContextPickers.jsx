import { useState } from 'react';
import { createPortal } from 'react-dom';
import {
  ChevronRight, Loader2, RefreshCw, ScanSearch, Target, Upload, X,
} from 'lucide-react';

const fmtSec = (sec) => {
  const total = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
};

const fmtDateTime = (raw) => {
  if (!raw) return '';
  const date = new Date(String(raw).includes('T') ? raw : `${String(raw).replace(' ', 'T')}Z`);
  if (Number.isNaN(date.getTime())) return String(raw);
  return date.toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  });
};

const ModalShell = ({ children }) => (
  <div className="fixed inset-0 z-[9998] flex items-center justify-center p-4">
    {children}
  </div>
);

export default function HermesContextPickers({
  showReview,
  setShowReview,
  reviewsLoading,
  examReviews,
  attachExamReview,
  showUploads,
  setShowUploads,
  uploadsLoading,
  uploadFiles,
  attachUpload,
  showPicker,
  setShowPicker,
  runsLoading,
  practiceRuns,
  attachPractice,
  attaching,
  loadPracticeRuns,
  maxDraftAttach,
}) {
  const [reviewKind, setReviewKind] = useState('zhenti');
  const shownReviews = examReviews.filter((r) => (r.kind || 'zhenti') === reviewKind);

  return (
    <>
      {showReview && createPortal(
        <ModalShell>
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowReview(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <ScanSearch size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  带进当前对话
                </span>
              </div>
              <button
                onClick={() => setShowReview(false)}
                className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="px-5 pt-3 flex gap-2">
              {[
                { id: 'zhenti', label: '真题' },
                { id: 'taoti', label: '套题' },
              ].map((k) => (
                <button
                  key={k.id}
                  type="button"
                  onClick={() => setReviewKind(k.id)}
                  className={`px-4 py-1.5 rounded-full text-[11px] font-black tracking-tight transition-all ${
                    reviewKind === k.id
                      ? 'bg-[#1a1a1a] text-white'
                      : 'bg-[#e8d5b0]/60 text-slate-500 hover:bg-[#e8d5b0]'
                  }`}
                >
                  {k.label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {reviewsLoading && shownReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!reviewsLoading && shownReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有处理完的{reviewKind === 'taoti' ? '套题' : '真题'}复盘。<br />
                  去侧栏「录屏复盘」选好类型再上传录屏。这里不能上传。
                </p>
              )}
              {shownReviews.map((review) => (
                <button
                  key={review.id}
                  onClick={() => attachExamReview(review.id)}
                  disabled={attaching}
                  className="w-full text-left px-3.5 py-3 rounded-2xl bg-[#faf9f6] hover:bg-[#1a1a1a] hover:text-white transition-colors group disabled:opacity-50"
                >
                  <div className="flex items-center gap-2">
                    <div className="text-xs font-black italic truncate">{review.title}</div>
                    <span className="shrink-0 text-[9px] font-black tracking-widest text-[#8d7348] group-hover:text-white/50">
                      {review.kind === 'taoti' ? '套题' : '真题'}
                    </span>
                  </div>
                  <div className="text-[10px] font-bold text-[#bbb] group-hover:text-white/50 mt-0.5">
                    {review.exam_date} · {Math.round((review.duration_sec || 0) / 60)} 分钟
                    {review.stats?.questions ? ` · ${review.stats.questions} 题` : ''}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-5 py-3 border-t border-black/5">
              <p className="text-[10px] font-bold text-[#bbb] leading-relaxed">
                不是上传。选一场已完成的复盘，会带上一份 md，不占输入框。发送后还在这个会话里接着聊。
              </p>
            </div>
          </div>
        </ModalShell>,
        document.body,
      )}

      {showUploads && createPortal(
        <ModalShell>
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowUploads(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <Upload size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  挑一份上传资料复盘
                </span>
              </div>
              <button
                onClick={() => setShowUploads(false)}
                className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {uploadsLoading && uploadFiles.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!uploadsLoading && uploadFiles.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有上传资料。<br />去「资料上传」丢一份练习 PDF。
                </p>
              )}
              {uploadFiles.map((file) => (
                <button
                  key={`${file.date}/${file.type}/${file.name}`}
                  onClick={() => attachUpload(file)}
                  className="w-full text-left px-3.5 py-3 rounded-2xl bg-[#faf9f6] hover:bg-[#1a1a1a] hover:text-white transition-colors group"
                >
                  <div className="text-xs font-black italic truncate">{file.name}</div>
                  <div className="text-[10px] font-bold text-[#bbb] group-hover:text-white/50 mt-0.5">
                    {file.date} · {file.type}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-5 py-3 border-t border-black/5">
              <p className="text-[10px] font-bold text-[#bbb] leading-relaxed">
                会把这份文件的绝对路径装进输入框，Hermes 直接打开，不再满盘搜索。
              </p>
            </div>
          </div>
        </ModalShell>,
        document.body,
      )}

      {showPicker && createPortal(
        <ModalShell>
          <button
            type="button"
            aria-label="关闭"
            onClick={() => setShowPicker(false)}
            className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
          />
          <div className="relative w-full max-w-lg max-h-[80vh] flex flex-col rounded-3xl bg-white shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-black/5">
              <div className="flex items-center space-x-2">
                <Target size={15} className="text-[#6b5428]" />
                <span className="text-xs font-black uppercase tracking-widest text-[#1a1a1a]">
                  选择一次 AI 练题复盘
                </span>
              </div>
              <div className="flex items-center space-x-1">
                <button
                  onClick={loadPracticeRuns}
                  title="刷新"
                  className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
                >
                  {runsLoading
                    ? <Loader2 size={13} className="animate-spin" />
                    : <RefreshCw size={13} />}
                </button>
                <button
                  onClick={() => setShowPicker(false)}
                  className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
                >
                  <X size={14} />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {runsLoading && practiceRuns.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!runsLoading && practiceRuns.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有可复盘的 AI 练题记录。<br />去「AI 练题」完成一套并交卷后，这里会自动出现。
                </p>
              )}
              {practiceRuns.map((run) => (
                <button
                  key={run.id}
                  onClick={() => attachPractice(run.id)}
                  disabled={attaching}
                  className="w-full text-left px-4 py-3 rounded-2xl border border-black/5 hover:border-[#6b5428] hover:bg-[#f4e6c8] transition-colors flex items-center gap-3 disabled:opacity-50"
                >
                  <span className="flex-1 min-w-0">
                    <span className="block text-xs font-black truncate">{run.display_title || run.category || '未命名批次'}</span>
                    <span className="block text-[10px] font-bold text-[#bbb] mt-0.5">
                      {fmtDateTime(run.ended_at)} · 对 {run.correct}/{run.total} · 错 {run.wrong_count} · 用时 {fmtSec(run.duration_sec)}
                      {run.draft_count > 0 && ` · ${run.draft_count} 张草稿`}
                    </span>
                  </span>
                  <ChevronRight size={14} className="shrink-0 text-[#ccc]" />
                </button>
              ))}
            </div>

            <p className="px-5 py-3 border-t border-black/5 text-[10px] font-bold text-[#ccc] leading-relaxed">
              选中后会生成一份可预览的 Markdown 附件，并带上最多 {maxDraftAttach} 张复盘重点草稿纸（含正确但慢的题），不占输入框。
            </p>
          </div>
        </ModalShell>,
        document.body,
      )}
    </>
  );
}
