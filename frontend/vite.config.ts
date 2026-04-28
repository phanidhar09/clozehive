import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load root .env and frontend .env (root takes precedence for shared vars)
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const localEnv = loadEnv(mode, __dirname, '')
  const env = { ...localEnv, ...rootEnv }

  const backendUrl = env.VITE_API_URL || env.BACKEND_URL || `http://localhost:${env.API_GATEWAY_PORT || 8000}`
  const frontendPort = parseInt(env.FRONTEND_PORT || '3000')

  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
      port: frontendPort,
      proxy: {
        '/api':     { target: backendUrl, changeOrigin: true },
        '/uploads': { target: backendUrl, changeOrigin: true },
      },
    },
  }
})
