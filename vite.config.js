import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import basicSsl from '@vitejs/plugin-basic-ssl'

// 强制所有文本响应带 charset=utf-8，避免浏览器按系统默认编码（GBK 等）解码
const forceUtf8Plugin = () => ({
  name: 'force-utf8-charset',
  configureServer(server) {
    server.middlewares.use((req, res, next) => {
      const origSetHeader = res.setHeader.bind(res)
      res.setHeader = (name, value) => {
        if (typeof name === 'string' && name.toLowerCase() === 'content-type' && typeof value === 'string') {
          const lower = value.toLowerCase()
          const isText =
            lower.startsWith('text/') ||
            lower.includes('javascript') ||
            lower.includes('json') ||
            lower.includes('xml') ||
            lower.includes('css') ||
            lower.includes('html')
          if (isText && !lower.includes('charset=')) {
            value = `${value}; charset=utf-8`
          }
        }
        return origSetHeader(name, value)
      }
      next()
    })
  },
})

export default defineConfig({
  plugins: [react(), tailwindcss(), forceUtf8Plugin(), basicSsl()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // 启用 HTTPS（由 basicSsl 插件提供自签证书）
    // 启用后需要通过 https://<host>:5173 访问；
    // 首次访问会有证书警告，点击"高级 → 继续访问"即可。
    // 这是使用 Document Picture-in-Picture（无边框悬浮小窗）的必要条件。
    https: true,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
})
