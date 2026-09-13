import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // loadEnv makes .env-file values visible to the dev server (process.env
  // only sees exported shell vars), so VITE_PORT / VITE_API_URL /
  // VITE_API_PREFIX honor the same .env.example contract as client code.
  const env = loadEnv(mode, process.cwd(), '')
  const apiPrefix = env.VITE_API_PREFIX || '/api'
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: Number(env.VITE_PORT || 3000),
      proxy: {
        [apiPrefix]: {
          target: env.VITE_API_URL || 'http://localhost:8000',
          changeOrigin: true,
        }
      }
    }
  }
})

