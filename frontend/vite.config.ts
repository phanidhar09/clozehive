import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import path from 'path'

export default defineConfig(async ({ mode }) => {
  // Load root .env and frontend .env (root takes precedence for shared vars)
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const localEnv = loadEnv(mode, __dirname, '')
  const env = { ...localEnv, ...rootEnv }

  const backendUrl = env.VITE_API_URL || env.BACKEND_URL || `http://localhost:${env.API_GATEWAY_PORT || 8000}`
  const frontendPort = parseInt(env.FRONTEND_PORT || '3000')

  // Optional Sentry source-map upload — only when an auth token is provided, so
  // normal/CI builds without Sentry are unaffected. Loaded dynamically so the
  // plugin isn't a hard build dependency.
  const sentryPlugins = []
  if (env.SENTRY_AUTH_TOKEN && env.SENTRY_ORG && env.SENTRY_PROJECT) {
    try {
      const { sentryVitePlugin } = await import('@sentry/vite-plugin')
      sentryPlugins.push(
        sentryVitePlugin({
          org: env.SENTRY_ORG,
          project: env.SENTRY_PROJECT,
          authToken: env.SENTRY_AUTH_TOKEN,
        }),
      )
    } catch {
      // Plugin not installed — skip upload, build still succeeds.
    }
  }

  return {
    build: {
      // Generate source maps but don't reference them in the bundle; uploaded to
      // Sentry for symbolication, never served to users.
      sourcemap: 'hidden',
      rollupOptions: {
        output: {
          // Split large, stable vendor libs into their own long-cacheable chunks
          // so an app-code change doesn't bust the whole vendor bundle, and so
          // heavy libs load in parallel / only where used.
          manualChunks: {
            'react-vendor': ['react', 'react-dom', 'react-router-dom'],
            'motion-vendor': ['framer-motion'],
            'charts-vendor': ['recharts'],
            'dnd-vendor': ['@dnd-kit/core', '@dnd-kit/sortable', '@dnd-kit/utilities'],
          },
        },
      },
    },
    plugins: [
      react(),
      ...sentryPlugins,
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
          // Never let the SPA navigation fallback (index.html) hijack top-level
          // navigations to backend routes. Without this, clicking "Continue with
          // Google" navigates to /api/v1/auth/google/login and the service worker
          // serves index.html instead of letting it reach the backend, so the
          // OAuth redirect silently bounces back to /login.
          navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//, /^\/oauth\//],
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
