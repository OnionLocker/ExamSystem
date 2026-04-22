import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

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
  plugins: [react(), tailwindcss(), forceUtf8Plugin()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
      },
    },
  },
})
