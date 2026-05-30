import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

export default defineConfig(({ mode }) => {
  // Load root .env and frontend .env (root takes precedence for shared vars)
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const localEnv = loadEnv(mode, __dirname, '')
  const env = { ...localEnv, ...rootEnv }

  const backendUrl = env.VITE_API_URL || env.BACKEND_URL || `http://localhost:${env.API_GATEWAY_PORT || 8000}`
  const frontendPort = parseInt(env.FRONTEND_PORT || '3000')

  return {
    plugins: [
      react(),
      VitePWA({
        registerType: 'autoUpdate',
        includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
        manifest: {
          name: 'ClozéHive — AI Wardrobe Stylist',
          short_name: 'ClozéHive',
          description: 'AI-powered wardrobe management and outfit recommendations',
          theme_color: '#14B8A6',
          background_color: '#F5F4F0',
          display: 'standalone',
          orientation: 'portrait',
          scope: '/',
          start_url: '/dashboard',
          icons: [
            {
              src: '/icons/icon-192x192.png',
              sizes: '192x192',
              type: 'image/png',
            },
            {
              src: '/icons/icon-512x512.png',
              sizes: '512x512',
              type: 'image/png',
            },
            {
              src: '/icons/icon-maskable-512x512.png',
              sizes: '512x512',
              type: 'image/png',
              purpose: 'maskable',
            },
          ],
        },
        workbox: {
          // Cache static assets aggressively, network-first for API calls
          globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/fonts\.googleapis\.com/,
              handler: 'StaleWhileRevalidate',
              options: { cacheName: 'google-fonts-stylesheets' },
            },
            {
              urlPattern: /^https:\/\/fonts\.gstatic\.com/,
              handler: 'CacheFirst',
              options: {
                cacheName: 'google-fonts-webfonts',
                expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
              },
            },
            {
              // Network-first for all API calls — never serve stale API data
              urlPattern: /\/api\//,
              handler: 'NetworkOnly',
            },
          ],
        },
        devOptions: {
          enabled: false,
        },
      }),
    ],
    resolve: {
      alias: { '@': path.resolve(__dirname, './src') },
    },
    server: {
      port: frontendPort,
      proxy: {
        // WebSocket must be listed before the general /api catch-all so Vite
        // applies the ws:true upgrade before the plain HTTP proxy takes over.
        '/api/v1/ws': { target: backendUrl, changeOrigin: true, ws: true },
        '/api':       { target: backendUrl, changeOrigin: true },
        '/uploads':   { target: backendUrl, changeOrigin: true },
      },
    },
  }
})
