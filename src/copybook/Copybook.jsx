import { useState } from 'react';
import { PenTool, Image, Sparkles, Download, CheckCircle2, RefreshCw, Layers } from 'lucide-react';

const HANDWRITING_TARGETS = [
  { char: '百', pinyin: 'bǎi', focus: '横画水平', tip: '首横宜长且平，中间日字收紧，多横间距平分' },
  { char: '中', pinyin: 'zhōng', focus: '悬针竖支撑', tip: '口字扁平居中，悬针竖贯穿中轴，坚挺直立' },
  { char: '人', pinyin: 'rén', focus: '撇捺舒展', tip: '撇如长刀，捺如翅膀，向右下重按舒展成底座' },
  { char: '建', pinyin: 'jiàn', focus: '建字底拖底', tip: '内部律字紧凑，建字底平捺长长拖住全字重心' },
  { char: '国', pinyin: 'guó', focus: '全包围结构', tip: '外框平正微收，内部玉字居中充实，四周留均匀缝隙' },
  { char: '复', pinyin: 'fù', focus: '上紧下松', tip: '𠂉与日收紧扁平，下部夊撇捺大张，脚踩实地' },
];

export default function Copybook() {
  const [selectedChar, setSelectedChar] = useState(HANDWRITING_TARGETS[0]);
  const [activeModel, setActiveModel] = useState('all'); // 'all', 'image2', 'banana2'
  const [promptText, setPromptText] = useState('高清书法字帖，米字格硬笔临摹，字迹工整横平竖直，规范楷书硬笔书法，高分辨率白底黑字');
  const [generating, setGenerating] = useState(false);

  const handleGenerate = async () => {
    setGenerating(true);
    setTimeout(() => {
      setGenerating(false);
    }, 1200);
  };

  return (
    <div className="space-y-8 pb-12">
      {/* 顶部 Banner */}
      <div className="bg-gradient-to-r from-[#1a1a1a] to-[#2d2d2d] text-white p-8 rounded-[2.5rem] shadow-xl relative overflow-hidden">
        <div className="absolute right-0 top-0 bottom-0 w-1/3 bg-white/5 skew-x-12 transform origin-bottom-right pointer-events-none" />
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center space-x-3 mb-2">
              <span className="px-3 py-1 rounded-full bg-[#fbc02d]/20 text-[#fbc02d] text-xs font-black uppercase tracking-widest flex items-center gap-1.5">
                <PenTool size={14} /> 申论卷面专项
              </span>
              <span className="text-xs font-bold text-white/50">阅卷及格分提升计划</span>
            </div>
            <h2 className="text-3xl font-black italic tracking-tight">申论硬笔字帖与 AI 图像对比</h2>
            <p className="text-sm font-medium text-white/60 mt-2 max-w-2xl">
              规范卷面不求龙飞凤舞，但求<strong>横平竖直、上紧下松、字字独立</strong>。结合 Image2 与 Banana2 多模态图像生成，实时比对字帖训练效果。
            </p>
          </div>
          <button
            onClick={handleGenerate}
            disabled={generating}
            className="px-6 py-4 rounded-2xl bg-[#fbc02d] text-black font-black text-xs uppercase tracking-widest hover:brightness-110 active:scale-95 transition-all flex items-center space-x-2 shadow-lg shadow-[#fbc02d]/20 disabled:opacity-50"
          >
            {generating ? <RefreshCw className="animate-spin" size={16} /> : <Sparkles size={16} />}
            <span>{generating ? '字帖模型生成中...' : '一键比对 Image2 & Banana2'}</span>
          </button>
        </div>
      </div>

      {/* 核心字库选择 */}
      <div className="space-y-4">
        <h3 className="text-lg font-black italic flex items-center space-x-2 text-[#1a1a1a]">
          <Layers size={18} className="text-[#fbc02d]" />
          <span>申论必练核心基础字</span>
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
          {HANDWRITING_TARGETS.map((item) => {
            const isSelected = selectedChar.char === item.char;
            return (
              <button
                key={item.char}
                onClick={() => setSelectedChar(item)}
                className={`p-4 rounded-2xl border transition-all text-center flex flex-col items-center justify-between space-y-2 ${
                  isSelected
                    ? 'border-[#1a1a1a] bg-[#1a1a1a] text-white shadow-lg scale-105'
                    : 'border-[#f2f0e9] bg-white hover:border-slate-300 text-[#1a1a1a]'
                }`}
              >
                <span className={`text-[10px] font-bold uppercase ${isSelected ? 'text-[#fbc02d]' : 'text-slate-400'}`}>
                  {item.pinyin}
                </span>
                <span className="text-3xl font-black font-serif my-1">{item.char}</span>
                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${isSelected ? 'bg-white/10 text-white/80' : 'bg-[#f2f0e9] text-slate-500'}`}>
                  {item.focus}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 选定字的要领说明 & 标准米字格渲染 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* 左侧要领卡片 */}
        <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-6 space-y-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-black uppercase tracking-widest text-slate-400">书写结构剖析</span>
              <span className="text-2xl font-serif font-black text-[#fbc02d]">{selectedChar.char}</span>
            </div>
            <h4 className="text-base font-black italic mb-2 text-[#1a1a1a]">核心重点：{selectedChar.focus}</h4>
            <p className="text-xs font-medium text-slate-600 leading-relaxed bg-[#f2f0e9]/50 p-4 rounded-xl border border-[#f2f0e9]">
              {selectedChar.tip}
            </p>
          </div>

          <div className="space-y-2 text-xs font-bold text-slate-500 border-t border-[#f2f0e9] pt-4">
            <p className="flex items-center gap-1.5 text-slate-700">
              <CheckCircle2 size={14} className="text-emerald-500" />
              <span>格子占位控制在 70% ~ 80%</span>
            </p>
            <p className="flex items-center gap-1.5 text-slate-700">
              <CheckCircle2 size={14} className="text-emerald-500" />
              <span>撇捺收笔要有送力重按感</span>
            </p>
          </div>
        </div>

        {/* 右侧标准矢量米字格字帖 */}
        <div className="lg:col-span-2 bg-white rounded-[2rem] border border-[#f2f0e9] p-6 flex flex-col items-center justify-center space-y-4 shadow-sm">
          <div className="w-full flex items-center justify-between">
            <span className="text-xs font-black uppercase tracking-widest text-slate-400">高清矢量米字格临摹</span>
            <span className="text-xs font-bold text-slate-400">支持直接打印练字</span>
          </div>

          {/* SVG 米字格渲染 */}
          <div className="w-full max-w-lg grid grid-cols-4 gap-2 bg-[#fdfbf7] p-4 rounded-2xl border border-red-200 shadow-inner">
            {[1, 2, 3, 4].map((idx) => (
              <div key={idx} className="relative aspect-square border-2 border-red-400 bg-white flex items-center justify-center overflow-hidden">
                <svg className="absolute inset-0 w-full h-full stroke-red-200 stroke-1 pointer-events-none" viewBox="0 0 100 100">
                  <line x1="0" y1="50" x2="100" y2="50" strokeDasharray="3,3" />
                  <line x1="50" y1="0" x2="50" y2="100" strokeDasharray="3,3" />
                  <line x1="0" y1="0" x2="100" y2="100" strokeDasharray="2,2" />
                  <line x1="100" y1="0" x2="0" y2="100" strokeDasharray="2,2" />
                </svg>
                <span className={`text-6xl font-serif select-none ${idx === 1 ? 'text-black font-black' : 'text-red-300 font-normal'}`}>
                  {selectedChar.char}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Image2 vs Banana2 模型字帖生成对比 */}
      <div className="bg-white rounded-[2rem] border border-[#f2f0e9] p-8 space-y-6">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <h3 className="text-lg font-black italic text-[#1a1a1a] flex items-center gap-2">
              <Image size={20} className="text-[#fbc02d]" />
              <span>AI 生成模型效果比对 (Image2 vs Banana2)</span>
            </h3>
            <p className="text-xs text-slate-400 font-medium mt-1">
              通过 Prompt 优化对比 OpenAI GPT-Image-2 (Image2) 与 Gemini Image (Banana2) 的硬笔字帖生成质量
            </p>
          </div>
          <div className="flex items-center space-x-2 bg-[#f2f0e9] p-1 rounded-xl">
            <button
              onClick={() => setActiveModel('all')}
              className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all ${activeModel === 'all' ? 'bg-white text-black shadow-sm' : 'text-slate-500'}`}
            >
              全部显示
            </button>
            <button
              onClick={() => setActiveModel('image2')}
              className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all ${activeModel === 'image2' ? 'bg-white text-black shadow-sm' : 'text-slate-500'}`}
            >
              Image2
            </button>
            <button
              onClick={() => setActiveModel('banana2')}
              className={`px-3 py-1.5 rounded-lg text-xs font-black transition-all ${activeModel === 'banana2' ? 'bg-white text-black shadow-sm' : 'text-slate-500'}`}
            >
              Banana2
            </button>
          </div>
        </div>

        {/* Prompt 输入与优化 */}
        <div className="space-y-2">
          <label className="text-xs font-black uppercase tracking-widest text-slate-400">Prompt 提示词指令</label>
          <div className="flex gap-2">
            <input
              type="text"
              value={promptText}
              onChange={(e) => setPromptText(e.target.value)}
              className="flex-1 bg-[#f2f0e9]/50 border border-[#f2f0e9] rounded-xl px-4 py-2.5 text-xs font-bold focus:outline-none focus:ring-2 focus:ring-[#fbc02d]"
            />
            <button
              onClick={handleGenerate}
              className="px-5 py-2.5 bg-[#1a1a1a] text-white rounded-xl text-xs font-black hover:bg-[#fbc02d] hover:text-black transition-colors"
            >
              生成测试
            </button>
          </div>
        </div>

        {/* 双模型渲染结果比对 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
          {(activeModel === 'all' || activeModel === 'image2') && (
            <div className="border border-[#f2f0e9] rounded-2xl p-5 space-y-4 bg-gradient-to-b from-white to-[#f9f8f6]">
              <div className="flex items-center justify-between">
                <span className="px-3 py-1 bg-blue-50 text-blue-600 rounded-full text-xs font-black">
                  Model A: Image2 (GPT-Image-2)
                </span>
                <span className="text-[10px] text-slate-400 font-bold">API: /v1/images/generations</span>
              </div>
              
              <div className="aspect-video bg-[#f2f0e9] rounded-xl flex flex-col items-center justify-center border border-dashed border-slate-300 relative overflow-hidden group">
                <div className="text-center space-y-2 p-6">
                  <div className="w-16 h-16 rounded-full bg-white flex items-center justify-center mx-auto shadow-md">
                    <span className="text-3xl font-serif font-black text-slate-800">{selectedChar.char}</span>
                  </div>
                  <p className="text-xs font-black text-slate-700">【Image2 生成模拟样张】</p>
                  <p className="text-[10px] text-slate-400">特点：线条极其规范，结构严谨，适合练习标准规矩</p>
                </div>
              </div>

              <div className="text-xs font-medium text-slate-600 bg-white p-3 rounded-xl border border-[#f2f0e9] space-y-1">
                <p className="font-black text-[#1a1a1a]">测试结论：</p>
                <p>生成字形极为工整，笔画粗细一致，适合打基础与矫正歪斜。</p>
              </div>
            </div>
          )}

          {(activeModel === 'all' || activeModel === 'banana2') && (
            <div className="border border-[#f2f0e9] rounded-2xl p-5 space-y-4 bg-gradient-to-b from-white to-[#f9f8f6]">
              <div className="flex items-center justify-between">
                <span className="px-3 py-1 bg-purple-50 text-purple-600 rounded-full text-xs font-black">
                  Model B: Banana2 (Gemini Image)
                </span>
                <span className="text-[10px] text-slate-400 font-bold">API: /v1/chat/completions</span>
              </div>

              <div className="aspect-video bg-[#f2f0e9] rounded-xl flex flex-col items-center justify-center border border-dashed border-slate-300 relative overflow-hidden group">
                <div className="text-center space-y-2 p-6">
                  <div className="w-16 h-16 rounded-full bg-white flex items-center justify-center mx-auto shadow-md">
                    <span className="text-3xl font-serif font-black text-slate-900">{selectedChar.char}</span>
                  </div>
                  <p className="text-xs font-black text-slate-700">【Banana2 生成模拟样张】</p>
                  <p className="text-[10px] text-slate-400">特点：带有轻微墨韵与书法风骨，视觉舒展感更强</p>
                </div>
              </div>

              <div className="text-xs font-medium text-slate-600 bg-white p-3 rounded-xl border border-[#f2f0e9] space-y-1">
                <p className="font-black text-[#1a1a1a]">测试结论：</p>
                <p>笔画呼应更自然，长捺舒展到位，适合冲刺申论卷面视觉分。</p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
