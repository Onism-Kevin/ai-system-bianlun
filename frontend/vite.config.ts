import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    proxy: {
      // 鉴权方案 A（Cookie，permissions §6.3 / sse_events §9）：dev 环境
      // /api 同源反代到后端开发服务器（uvicorn 默认 8000）——同源下
      // axios 与 EventSource 零配置且自动携带 httpOnly Cookie。
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
