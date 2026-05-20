import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Use Docker service name in containerized dev, fallback to localhost for host dev
const API_URL = process.env.API_URL || 'http://localhost:8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: API_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
