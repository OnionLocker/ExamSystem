import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import PopupPractice from './practice/PopupPractice.jsx'

// 根据 URL 参数决定入口：?popup=1 时启动"小窗练习"独立页
const isPopup = new URLSearchParams(window.location.search).get('popup') === '1'
const Root = isPopup ? PopupPractice : App

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
