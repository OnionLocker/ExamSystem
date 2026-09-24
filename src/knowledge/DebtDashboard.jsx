import { useEffect, useState } from 'react';
import { api } from '../api.js';

export default function DebtDashboard({ onSeedHermes, active = true }) {
  const [debts, setDebts] = useState([]);
  const [summary, setSummary] = useState({ open: 0, cleared: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    async function loadDebts() {
      setLoading(true);
      setError('');
      try {
        const data = await api('/api/kaodian/debts');
        if (cancelled) return;
        setDebts(data.debts || []);
        setSummary(data.summary || { open: 0, cleared: 0 });
      } catch (err) {
        if (!cancelled) setError(err.message || '加载失败');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    const timer = setTimeout(loadDebts, 0);
    const onVisible = () => {
      if (document.visibilityState === 'visible') setReload((n) => n + 1);
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [active, reload]);

  function handleGenerateQuiz(debt) {
    // 创建Hermes seed并切换到Hermes tab
    const instruction = `#出题清债#
考点: ${debt.kaodian}
模块: ${debt.module}
累计错误: ${debt.wrongCount}次
连对进度: ${debt.recoveryProgress}
掌握等级: ${debt.assessment?.label || '待评估'}${debt.assessment?.review_due ? '（待复测）' : ''}
熟练度: ${debt.assessment?.fluency_label || '待评估'}

请针对该考点出5道题，难度分布：easy 2题, mid 2题, hard 1题。题目要覆盖该考点的不同变式，不要重复同一场景只换数字。`;

    // 使用App.jsx提供的seedHermes函数
    if (onSeedHermes) {
      onSeedHermes({ debtInstruction: instruction });
    }
  }

  const debtsByModule = debts.reduce((groups, debt) => {
    const module = debt.module || '未分类';
    (groups[module] ||= []).push(debt);
    return groups;
  }, {});

  if (loading) {
    return (
      <div className="debt-dashboard">
        <div className="debt-loading">加载知识债数据中...</div>
      </div>
    );
  }

  if (error) return (
    <div className="debt-dashboard" role="alert">
      <p>知识债加载失败：{error}</p>
      <button type="button" className="generate-variant-btn" onClick={() => setReload((n) => n + 1)}>重新加载</button>
    </div>
  );

  return (
    <div className="debt-dashboard">
      <div className="debt-summary">
        <span className="open-count">知识债 {summary.open || 0} 笔</span>
        <span className="reinforce-count">待巩固 {summary.reinforce || 0} 个</span>
        <span className="learning-count">学习中 {summary.learning || 0} 个</span>
        <span className="cleared-count">已清偿 {summary.cleared || 0} 笔</span>
      </div>

      <p className="text-sm text-[#746b5b] leading-relaxed">未学不算债。在知识点页确认“我已学过”后，新增错题才计入知识债；同一考法连对两次清偿。旧作答记录保留。</p>
      {debts.length === 0 ? (
        <div className="empty-state">还没有已登记的学习进度。选择一个知识点，点击“开始学习”即可。</div>
      ) : (
        <div className="debt-list">
          {Object.entries(debtsByModule).map(([module, moduleDebts], index) => (
            <details key={module} className="debt-group" open={index === 0}>
              <summary className="debt-group-title">
                <span>{module}</span>
                <span className="debt-group-count">{moduleDebts.length} 个考点</span>
              </summary>
              <div className="debt-group-list">
                {moduleDebts.map((debt) => (
                  <div key={debt.kaodian} className={`debt-card debt-card-${debt.status}`}>
                    <div className="debt-header">
                      <h3 className="debt-kaodian">{debt.kaodian}</h3>
                      <span className="debt-module">{{ debt: '知识债', learning: '学习中', reinforce: '待巩固', learned: '已学 · 待检验', cleared: '已清偿' }[debt.status]}</span>
                    </div>

                    {(debt.status === 'debt' || debt.status === 'cleared') && <div className="debt-stats">
                      <div className="debt-stat">
                        <span className="stat-label">累计错</span>
                        <span className="stat-value error-count">{debt.wrongCount}</span>
                      </div>
                      <div className="debt-stat">
                        <span className="stat-label">连对进度</span>
                        <span className="stat-value recovery-progress">
                          {debt.recoveryProgress}
                          <span className="progress-bar">
                            <span
                              className="progress-fill"
                              style={{ width: `${debt.recoveryStreak * 50}%` }}
                            />
                          </span>
                        </span>
                      </div>
                      <div className="debt-stat">
                        <span className="stat-label">最近错误</span>
                        <span className="stat-value">{debt.daysSinceWrong == null ? '尚无错题' : `${debt.daysSinceWrong} 天前`}</span>
                      </div>
                      <div className="debt-stat">
                        <span className="stat-label">掌握度</span>
                        <span className="stat-value">
                          {debt.assessment?.label || '待评估'}
                          {debt.assessment?.review_due && <span className="confidence">（待复测）</span>}
                        </span>
                      </div>
                    </div>}

                    {debt.status === 'debt' && <button
                      className="generate-variant-btn"
                      onClick={() => handleGenerateQuiz(debt)}
                    >
                      让 Hermes 出这个考点的题
                    </button>}
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      )}
    </div>
  );
}
