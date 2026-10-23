import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { Check, Cpu, Eye, Mic, Image as ImageIcon, KeyRound, RefreshCw, Loader2 } from 'lucide-react';

const CAP = {
  supports_vision: { icon: Eye, label: '视觉', cls: 'text-emerald-700 bg-emerald-100 border-emerald-200' },
  supports_audio: { icon: Mic, label: '语音', cls: 'text-sky-700 bg-sky-100 border-sky-200' },
  supports_image_output: { icon: ImageIcon, label: '图片生成', cls: 'text-violet-700 bg-violet-100 border-violet-200' },
};

export default function ModelSettings() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [applying, setApplying] = useState('');
  const [note, setNote] = useState('');

  const load = async ({ reset = false } = {}) => {
    if (reset) setError('');
    try {
      setData(await api('/api/model'));
    } catch (e) {
      setError(e.message || '加载模型配置失败');
    }
  };
  useEffect(() => {
    api('/api/model')
      .then(setData)
      .catch((e) => setError(e.message || '加载模型配置失败'));
  }, []);

  const active = data?.active || '';
  const profiles = useMemo(() => data?.profiles || [], [data]);

  const apply = async (id) => {
    if (applying) return;
    setApplying(id);
    setNote('');
    setError('');
    try {
      const r = await api('/api/model/select', { method: 'POST', body: { profile: id } });
      setNote(`已切换到 ${r.label}（${r.model}）。${r.note || ''}`);
      await load({ reset: true });
    } catch (e) {
      setError(e.message || '切换模型失败');
    } finally {
      setApplying('');
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-xl font-black flex items-center gap-2">
            <Cpu size={20} /> 模型选择
          </h3>
          <p className="text-sm text-slate-500 font-medium mt-1">
            在这里切换整个系统的模型：Hermes 对话、出题、审核、资料分析、录屏复盘、语音全部跟随。
          </p>
        </div>
        <button
          onClick={() => void load({ reset: true })}
          className="flex items-center gap-1.5 px-4 py-2 rounded-2xl bg-white border border-[#e8d5b0] text-sm font-bold text-[#6b5428] hover:bg-[#e8d5b0]/40 transition-colors"
        >
          <RefreshCw size={15} /> 刷新
        </button>
      </div>

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-2xl px-4 py-3 text-sm font-semibold">
          {error}
        </div>
      )}
      {note && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-2xl px-4 py-3 text-sm font-semibold">
          {note}
        </div>
      )}

      {!data && !error ? (
        <div className="flex items-center gap-2 text-slate-400 text-sm font-semibold py-8 justify-center">
          <Loader2 size={16} className="animate-spin" /> 加载模型配置…
        </div>
      ) : (
        <div className="grid gap-4">
          {profiles.map((p) => {
            const isActive = p.id === active;
            const keySet = Boolean(p.key_set);
            return (
              <div
                key={p.id}
                className={`rounded-[1.75rem] p-5 border transition-all ${
                  isActive
                    ? 'bg-[#1a1a1a] text-white border-transparent shadow-lg shadow-black/10'
                    : 'bg-white border-[#e8d5b0]'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-black text-lg truncate">{p.label}</span>
                      {isActive && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-white/15 text-white text-[11px] font-black uppercase tracking-widest">
                          <Check size={12} /> 当前
                        </span>
                      )}
                    </div>
                    <p className={`text-sm font-mono mt-1 truncate ${isActive ? 'text-white/70' : 'text-slate-500'}`}>
                      {p.model}
                    </p>
                    <p className={`text-xs font-mono truncate mt-0.5 ${isActive ? 'text-white/50' : 'text-slate-400'}`}>
                      {p.base_url}
                    </p>

                    <div className="flex items-center gap-2 mt-3 flex-wrap">
                      {Object.entries(CAP).map(([key, cap]) => {
                        const on = Boolean(p[key]);
                        const Icon = cap.icon;
                        return (
                          <span
                            key={key}
                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold border ${
                              isActive
                                ? on
                                  ? 'bg-white/15 text-white border-white/20'
                                  : 'bg-white/5 text-white/40 border-white/10'
                                : on
                                  ? cap.cls
                                  : 'bg-slate-50 text-slate-300 border-slate-200'
                            }`}
                          >
                            <Icon size={12} /> {cap.label}
                          </span>
                        );
                      })}
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-bold border ${
                          isActive
                            ? keySet ? 'bg-white/15 text-white border-white/20' : 'bg-red-400/20 text-red-200 border-red-300/30'
                            : keySet ? 'bg-slate-50 text-slate-500 border-slate-200' : 'bg-red-50 text-red-500 border-red-200'
                        }`}
                        title={`API key 从 ~/.hermes/.env 的 ${p.api_key_env || ''} 读取`}
                      >
                        <KeyRound size={12} /> {keySet ? 'Key 已配置' : 'Key 未配置'}
                      </span>
                    </div>

                    {!keySet && (
                      <p className={`text-xs font-semibold mt-2 ${isActive ? 'text-red-200' : 'text-red-500'}`}>
                        ⚠️ 该模型的 API key 未配置：请在服务器 ~/.hermes/.env 中填写 {p.api_key_env || ''}。
                      </p>
                    )}
                  </div>

                  <div className="flex-shrink-0">
                    {isActive ? (
                      <span className="inline-flex items-center gap-1 px-4 py-2 rounded-2xl text-sm font-bold text-white/50 border border-white/15 cursor-default">
                        <Check size={15} /> 使用中
                      </span>
                    ) : (
                      <button
                        onClick={() => void apply(p.id)}
                        disabled={Boolean(applying)}
                        className="px-5 py-2.5 rounded-2xl bg-[#6b5428] text-white font-black text-sm hover:brightness-110 transition-all disabled:opacity-60 disabled:cursor-wait"
                      >
                        {applying === p.id ? '切换中…' : '应用'}
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="rounded-2xl bg-white/70 border border-[#e8d5b0] px-5 py-4 text-xs font-medium text-slate-500 leading-5">
        <p className="font-black text-slate-600 mb-1">说明</p>
        <p>· 切换后<b>新会话</b>立即使用新模型；进行中的会话保持原模型直到重新开始，不会被掐断。</p>
        <p>· 不支持的能力（如 DeepSeek 无视觉/语音）会在对应功能处明确提示，不会静默失败。</p>
        <p>· 配置文件：{data?.router_path || '~/.hermes/model-router.json'}（API key 统一放在 ~/.hermes/.env，不在配置里落明文）。</p>
      </div>
    </div>
  );
}
