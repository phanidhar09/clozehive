import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { initColorSchemeBeforeRender } from '@/store'
import { initObservability } from './observability'
import './index.css'

initColorSchemeBeforeRender()
// Fire-and-forget: error/perf tracking, no-op unless VITE_SENTRY_DSN is set.
void initObservability()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
