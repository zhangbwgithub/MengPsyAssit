import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// VITE_API_BASE 覆盖：为 S5 部署留口，默认走本地代理
const apiBase = process.env.VITE_API_BASE || 'http://127.0.0.1:8660'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: apiBase,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  preview: {
    port: 5199,
    proxy: {
      '/api': {
        target: apiBase,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
