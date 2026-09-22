import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

export default function DebtDashboard() {
  const [debts, setDebts] = useState([]);
  const [summary, setSummary] = useState({ open: 0, clearedThisWeek: 0 });
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadDebts();
  }, []);

  async function loadDebts() {
    try {
      const res = await fetch('/api/kaodian/debts');
      const data = await res.json();
      setDebts(data.debts || []);
      setSummary(data.summary || { open: 0, clearedThisWeek: 0 });
    } catch (error) {
      console.error('Failed to load debts:', error);
    } finally {
      setLoading(false);
    }
  }

  async function generateVariant(kaodian, module) {
    setGenerating(kaodian);
    try {
      const response = await fetch('/api/quiz/lite', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          module,
          tag: kaodian,
          count: 5
        })
      });
      if (response.ok) {
        const result = await response.json();
        if (result.sessionId) {
          navigate(`/practice/${result.sessionId}`);
        }
      } else {
        alert('出题失败，请稍后重试');
      }
    } catch (error) {
      console.error('Failed to generate quiz:', error);
      alert('出题失败，请稍后重试');
    } finally {
      setGenerating(null);
    }
  }

  if (loading) {
    return <div className="debt-dashboard loading">加载中...</div>;
  }

  return (
    <div className="debt-dashboard">
      <div className="debt-summary">
        <span className="open-count">未清 {summary.open} 笔</span>
        <span className="cleared-count">本周清掉 {summary.clearedThisWeek} 笔</span>
      </div>

      {debts.length === 0 ? (
        <div className="empty-state">暂无知识债务</div>
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
                onClick={() => generateVariant(debt.kaodian, debt.module)}
                disabled={generating === debt.kaodian}
              >
                {generating === debt.kaodian ? '出题中...' : '出这个考点的变式卷'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
