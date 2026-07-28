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

// Vite 的 defineConfig 支持传入函数，参数里有 command（'serve' | 'build'）和 mode
export default defineConfig(async ({ command }) => {
  const plugins = [react(), tailwindcss(), forceUtf8Plugin()]

  // 只有开发服务器（vite / vite dev）才加载 basicSsl → HTTPS
  // build 和 preview 不加载 → 纯 HTTP，不会有"不安全"警告
  if (command === 'serve') {
    const { default: basicSsl } = await import('@vitejs/plugin-basic-ssl')
    plugins.push(basicSsl())
  }

  return {
    plugins,
    server: {
      // 开发模式：HTTPS + 5173（PiP 悬浮小窗需要 HTTPS）
      host: '0.0.0.0',
      port: 5173,
      https: true,
      proxy: {
        '/api': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          // Hermes 对话页走 /api/hermes/ws，需要代理 WebSocket
          ws: true,
        },
      },
    },
    preview: {
      // 生产预览：纯 HTTP + 4173（外网访问用这个，无"不安全"红标）
      host: '0.0.0.0',
      port: 4173,
      proxy: {
        '/api': {
          target: 'http://localhost:3001',
          changeOrigin: true,
          ws: true,
        },
      },
    },
  }
})
