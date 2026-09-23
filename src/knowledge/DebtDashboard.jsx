import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function DebtDashboard() {
  const [debts, setDebts] = useState([]);
  const [summary, setSummary] = useState({ open: 0, clearedThisWeek: 0 });
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadDebts();
  }, []);

  async function loadDebts() {
    try {
      const res = await fetch('/api/kaodian/debts');
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const data = await res.json();
      setDebts(data.debts || []);
      setSummary(data.summary || { open: 0, clearedThisWeek: 0 });
    } catch (error) {
      console.error('Failed to load debts:', error);
      setDebts([]);
      setSummary({ open: 0, clearedThisWeek: 0 });
    } finally {
      setLoading(false);
    }
  }

  function handleGenerateQuiz(debt) {
    // 跳转到 Hermes 并发送出题指令
    const instruction = `#出题清债#
考点: ${debt.kaodian}
模块: ${debt.module}
累计错误: ${debt.wrongCount}次
连对进度: ${debt.recoveryProgress}
掌握度: ${debt.mastery != null ? debt.mastery + '%' : '未评估'}

请针对该考点出5道题，难度分布：easy 2题, mid 2题, hard 1题。题目要覆盖该考点的不同变式，不要重复同一场景只换数字。`;

    // 跳转到 Hermes 页面并传递指令
    navigate('/hermes', { state: { initialMessage: instruction } });
  }

  if (loading) {
    return (
      <div className="debt-dashboard">
        <div className="debt-loading">加载知识债数据中...</div>
      </div>
    );
  }

  return (
    <div className="debt-dashboard">
      <div className="debt-summary">
        <span className="open-count">未清 {summary.open} 笔</span>
        <span className="cleared-count">本周清掉 {summary.clearedThisWeek} 笔</span>
      </div>

      {debts.length === 0 ? (
        <div className="empty-state">🎉 暂无知识债务，继续保持！</div>
      ) : (
        <div className="debt-list">
          {debts.map((debt) => (
            <div key={debt.kaodian} className="debt-card">
              <div className="debt-header">
                <h3 className="debt-kaodian">{debt.kaodian}</h3>
                <span className="debt-module">{debt.module}</span>
              </div>

              <div className="debt-stats">
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
                  <span className="stat-value">{debt.daysSinceWrong} 天前</span>
                </div>
                <div className="debt-stat">
                  <span className="stat-label">掌握度</span>
                  <span className="stat-value">
                    {debt.mastery != null ? `${debt.mastery}%` : '—'}
                    {debt.confidence > 0 && (
                      <span className="confidence"> (置信 {debt.confidence}%)</span>
                    )}
                  </span>
                </div>
              </div>

              <button
                className="generate-variant-btn"
                onClick={() => handleGenerateQuiz(debt)}
              >
                让 Hermes 出这个考点的题
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
