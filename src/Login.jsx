import { useState } from 'react';
import { Lock, LogIn } from 'lucide-react';
import { login, setToken } from './api.js';

export default function Login({ onAuthed }) {
  const [password, setPassword] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!password) return;
    setLoading(true);
    setErr('');
    try {
      const { token } = await login(password);
      setToken(token);
      onAuthed();
    } catch (e) {
      setErr(e.message || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="h-screen w-screen bg-[#f2f0e9] flex items-center justify-center p-6 font-sans text-[#1a1a1a]">
      <div className="w-full max-w-md bg-white rounded-[2.5rem] shadow-2xl shadow-black/5 border border-white p-10">
        <div className="flex items-center space-x-3 mb-8">
          <div className="w-12 h-12 bg-[#1a1a1a] rounded-2xl flex items-center justify-center text-[#fbc02d] font-black italic text-lg">
            考
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tighter uppercase">BE.SMART</h1>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">省考练习系统</p>
          </div>
        </div>

        <h2 className="text-2xl font-black italic mb-2">请输入访问密码</h2>
        <p className="text-sm font-medium text-slate-400 mb-8">
          这是私人练习空间，仅供本人使用。
        </p>

        <form onSubmit={submit} className="space-y-5">
          <div className="relative">
            <Lock size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="访问密码"
              className="w-full bg-[#f2f0e9]/60 border border-transparent rounded-2xl py-4 pl-12 pr-4 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
            />
          </div>

          {err && (
            <div className="text-xs font-bold text-[#ff6b6b] bg-[#ff6b6b]/10 rounded-xl px-4 py-3">
              {err}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || !password}
            className="w-full flex items-center justify-center space-x-2 bg-[#1a1a1a] text-white font-black py-4 rounded-2xl hover:bg-[#fbc02d] hover:text-black transition-all uppercase tracking-widest text-xs disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <LogIn size={16} />
            <span>{loading ? '校验中...' : '进入系统'}</span>
          </button>
        </form>
      </div>
    </div>
  );
}
