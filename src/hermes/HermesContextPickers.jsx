import { createPortal } from 'react-dom';
import {
  ChevronRight, Loader2, RefreshCw, ScanSearch, Target, Upload, X,
} from 'lucide-react';

const fmtSec = (sec) => {
  const total = Math.max(0, Math.floor(sec || 0));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
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
                  挑一场模考复盘
                </span>
              </div>
              <button
                onClick={() => setShowReview(false)}
                className="p-1.5 rounded-lg text-[#bbb] hover:text-[#1a1a1a] hover:bg-black/5 transition-colors"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {reviewsLoading && examReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb]">加载中…</p>
              )}
              {!reviewsLoading && examReviews.length === 0 && (
                <p className="px-1 py-6 text-center text-[11px] font-bold text-[#bbb] leading-relaxed">
                  还没有处理完的复盘。<br />去「真题复盘」传一场模考的录屏和答案 PDF。
                </p>
              )}
              {examReviews.map((review) => (
                <button
                  key={review.id}
                  onClick={() => attachExamReview(review.id)}
                  disabled={attaching}
                  className="w-full text-left px-3.5 py-3 rounded-2xl bg-[#faf9f6] hover:bg-[#1a1a1a] hover:text-white transition-colors group disabled:opacity-50"
                >
                  <div className="text-xs font-black italic truncate">{review.title}</div>
                  <div className="text-[10px] font-bold text-[#bbb] group-hover:text-white/50 mt-0.5">
                    {review.exam_date} · {Math.round((review.duration_sec || 0) / 60)} 分钟
                    {review.stats?.questions ? ` · ${review.stats.questions} 题` : ''}
                  </div>
                </button>
              ))}
            </div>
            <div className="px-5 py-3 border-t border-black/5">
              <p className="text-[10px] font-bold text-[#bbb] leading-relaxed">
                会把整份复盘报告装进输入框，你可以再补一句想问的再发。
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
                  挑一场练习来复盘
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
                  还没有交过卷的练习。<br />去「AI 练题」做一套并交卷，草稿纸会自动存下来。
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
                    <span className="block text-xs font-black truncate">{run.category || '未命名批次'}</span>
                    <span className="block text-[10px] font-bold text-[#bbb] mt-0.5">
                      对 {run.correct}/{run.total} · 错 {run.wrong_count} · 用时 {fmtSec(run.duration_sec)}
                      {run.draft_count > 0 && ` · ${run.draft_count} 张草稿`}
                    </span>
                  </span>
                  <ChevronRight size={14} className="shrink-0 text-[#ccc]" />
                </button>
              ))}
            </div>

            <p className="px-5 py-3 border-t border-black/5 text-[10px] font-bold text-[#ccc] leading-relaxed">
              会把错题明细和最多 {maxDraftAttach} 张草稿纸装进输入框，你可以再补一句话再发。
            </p>
          </div>
        </ModalShell>,
        document.body,
      )}
    </>
  );
}
