import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { initColorSchemeBeforeRender } from '@/store'
import './index.css'

initColorSchemeBeforeRender()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
