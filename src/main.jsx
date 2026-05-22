import { Component, StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import PopupPractice from './practice/PopupPractice.jsx'

// 顶层错误边界：哪怕子树渲染抛错，也别让整页变白
class RootErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('[RootErrorBoundary]', error, info)
    this.setState({ info })
  }
  render() {
    if (this.state.error) {
      const msg = String(this.state.error?.stack || this.state.error?.message || this.state.error)
      const compStack = this.state.info?.componentStack || ''
      return (
        <div style={{
          minHeight: '100vh',
          padding: '24px 20px',
          background: '#fff7e6',
          color: '#1a1a1a',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          fontSize: 13,
          lineHeight: 1.5,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}>
          <div style={{ fontWeight: 800, fontSize: 16, marginBottom: 12 }}>
            页面渲染错误（已被错误边界捕获，请把以下内容发给开发者）
          </div>
          <div style={{ marginBottom: 12 }}>{msg}</div>
          {compStack && (
            <div style={{ opacity: 0.7, fontSize: 12 }}>
              <div style={{ fontWeight: 700, marginBottom: 4 }}>componentStack:</div>
              {compStack}
            </div>
          )}
          <button
            onClick={() => location.reload()}
            style={{
              marginTop: 16,
              padding: '8px 16px',
              fontWeight: 800,
              border: 'none',
              borderRadius: 8,
              background: '#1a1a1a',
              color: '#fbc02d',
              cursor: 'pointer',
            }}
          >
            刷新重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

// 根据 URL 参数决定入口：?popup=1 时启动"小窗练习"独立页
const isPopup = new URLSearchParams(window.location.search).get('popup') === '1'
const Root = isPopup ? PopupPractice : App

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RootErrorBoundary>
      <Root />
    </RootErrorBoundary>
  </StrictMode>,
)
