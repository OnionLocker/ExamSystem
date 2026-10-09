import { useState } from 'react';
import { Target, BookOpen, Loader2, Check, X } from 'lucide-react';
import { getToken } from '../api.js';

const InfoExtract = () => {
  const [type, setType] = useState('ziliao'); // 'ziliao' or 'yanyu'
  const [loading, setLoading] = useState(false);
  const [material, setMaterial] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [results, setResults] = useState(null);

  const generate = async () => {
    setLoading(true);
    setResults(null);
    setAnswers({});
    try {
      const res = await fetch('/api/info-extract/generate', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${getToken()}`,
        },
        body: JSON.stringify({ type }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setMaterial(data.material);
      setQuestions(data.questions);
    } catch (error) {
      alert('生成失败: ' + error.message);
    } finally {
      setLoading(false);
    }
  };

  const submit = () => {
    const checked = questions.map((q, i) => {
      const userAnswer = (answers[i] || '').trim();
      const correct = userAnswer === q.answer;
      return { ...q, userAnswer, correct };
    });
    setResults(checked);
  };

  const reset = () => {
    setMaterial(null);
    setQuestions([]);
    setAnswers({});
    setResults(null);
  };

  return (
    <div className="min-h-screen bg-[#e8d5b0] p-6">
      <div className="max-w-4xl mx-auto">
        <div className="bg-[#f6edd8] rounded-2xl shadow-sm border border-[#d6b987] p-8 mb-6">
          <div className="flex items-center gap-3 mb-6">
            <Target className="w-8 h-8 text-slate-700" />
            <h1 className="text-3xl font-bold text-slate-800">信息提取训练</h1>
          </div>

          <p className="text-slate-600 mb-6">
            针对资料分析/言语理解长文发呆问题，训练笔尖锚点定位能力
          </p>

          <div className="flex gap-4 mb-6">
            <button
              onClick={() => setType('ziliao')}
              className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${
                type === 'ziliao'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'bg-[#e8cf9f] text-[#3b3024] hover:bg-[#e0c48e]'
              }`}
            >
              资料分析材料
            </button>
            <button
              onClick={() => setType('yanyu')}
              className={`flex-1 py-3 px-6 rounded-xl font-medium transition-all ${
                type === 'yanyu'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'bg-[#e8cf9f] text-[#3b3024] hover:bg-[#e0c48e]'
              }`}
            >
              言语理解长文
            </button>
          </div>

          <button
            onClick={generate}
            disabled={loading}
            className="w-full py-3 px-6 bg-slate-800 text-white rounded-xl font-medium hover:bg-slate-900 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                生成中...
              </>
            ) : (
              <>
                <BookOpen className="w-5 h-5" />
                生成材料
              </>
            )}
          </button>
        </div>

        {material && (
          <>
            <div className="bg-[#f6edd8] rounded-2xl shadow-sm border border-[#d6b987] p-8 mb-6">
              <h2 className="text-xl font-bold text-slate-800 mb-4">材料</h2>
              <div className="text-[#3b3024] leading-relaxed whitespace-pre-wrap bg-[#efe2c4] p-6 rounded-xl border border-[#d6b987]">
                {material}
              </div>
            </div>

            <div className="bg-[#f6edd8] rounded-2xl shadow-sm border border-[#d6b987] p-8 mb-6">
              <h2 className="text-xl font-bold text-slate-800 mb-4">问题</h2>
              {questions.map((q, i) => (
                <div key={i} className="mb-6 last:mb-0">
                  <div className="flex items-start gap-3 mb-3">
                    <span className="flex-shrink-0 w-8 h-8 bg-[#e8cf9f] text-[#3b3024] rounded-full flex items-center justify-center font-bold">
                      {i + 1}
                    </span>
                    <div className="flex-1">
                      <p className="text-slate-800 font-medium mb-2">{q.question}</p>
                      <span className="text-xs text-[#736049] bg-[#e8cf9f] px-2 py-1 rounded">
                        {q.type}
                      </span>
                    </div>
                  </div>

                  <input
                    type="text"
                    value={answers[i] || ''}
                    onChange={(e) => setAnswers({ ...answers, [i]: e.target.value })}
                    placeholder="输入答案"
                    disabled={results !== null}
                    className="w-full px-4 py-3 bg-[#fbf6ea] border border-[#d6b987] rounded-xl focus:border-[#946034] focus:outline-none disabled:bg-[#efe2c4] disabled:cursor-not-allowed"
                  />

                  {results && results[i] && (
                    <div className={`mt-3 p-4 rounded-xl ${results[i].correct ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'}`}>
                      <div className="flex items-center gap-2 mb-2">
                        {results[i].correct ? (
                          <>
                            <Check className="w-5 h-5 text-green-600" />
                            <span className="font-bold text-green-700">正确</span>
                          </>
                        ) : (
                          <>
                            <X className="w-5 h-5 text-red-600" />
                            <span className="font-bold text-red-700">错误</span>
                          </>
                        )}
                      </div>
                      {!results[i].correct && (
                        <>
                          <p className="text-sm text-slate-700 mb-1">
                            <span className="font-medium">你的答案：</span>{results[i].userAnswer || '(未填写)'}
                          </p>
                          <p className="text-sm text-slate-700 mb-1">
                            <span className="font-medium">正确答案：</span>{results[i].answer}
                          </p>
                        </>
                      )}
                      <p className="text-sm text-slate-600">
                        <span className="font-medium">定位：</span>{results[i].location}
                      </p>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="flex gap-4">
              {!results ? (
                <button
                  onClick={submit}
                  className="flex-1 py-3 px-6 bg-slate-800 text-white rounded-xl font-medium hover:bg-slate-900 transition-all"
                >
                  提交答案
                </button>
              ) : (
                <button
                  onClick={reset}
                  className="flex-1 py-3 px-6 bg-slate-600 text-white rounded-xl font-medium hover:bg-slate-700 transition-all"
                >
                  重新开始
                </button>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default InfoExtract;
