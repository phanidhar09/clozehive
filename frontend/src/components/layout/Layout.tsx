import { Outlet } from 'react-router-dom'
import Sidebar from './Sidebar'
import Navbar from './Navbar'
import BottomNav from './BottomNav'
import ToastContainer from '@/components/ui/ToastContainer'

/**
 * Three-layer depth system:
 *  1. Background — fixed animated gradient orbs + faint grid
 *  2. Surface    — glass cards (via .card / .glass-card classes)
 *  3. Floating   — hover-lift shadows (via .card-hover)
 */
export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden">

      {/* ── Layer 1: Animated background ───────────────────────────────────── */}
      <div className="fixed inset-0 -z-10 pointer-events-none overflow-hidden">
        {/* Base: light mode cream, dark mode deep slate */}
        <div className="absolute inset-0 bg-cream-100 dark:bg-slate-950" />

        {/* Orb 1 — indigo, top-left */}
        <div className="absolute -top-32 -left-32 w-[560px] h-[560px] rounded-full
                        bg-brand-400/10 dark:bg-brand-500/12
                        blur-[120px] animate-float-1" />

        {/* Orb 2 — violet, bottom-right */}
        <div className="absolute -bottom-32 -right-32 w-[520px] h-[520px] rounded-full
                        bg-brand-400/8 dark:bg-brand-500/10
                        blur-[110px] animate-float-2" />

        {/* Orb 3 — cyan, center-ish */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[400px] h-[400px] rounded-full
                        bg-sky-400/5 dark:bg-cyan-500/6
                        blur-[140px] animate-float-3" />

        {/* Subtle grid — dark mode only */}
        <div
          className="absolute inset-0 hidden dark:block opacity-[0.025]"
          style={{
            backgroundImage: [
              'linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px)',
              'linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)',
            ].join(', '),
            backgroundSize: '72px 72px',
          }}
        />
      </div>

      {/* ── Layer 2 & 3: Shell ─────────────────────────────────────────────── */}
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 lg:ml-[260px]">
        <Navbar />
        <main className="flex-1 overflow-y-auto overflow-x-hidden p-4 pb-24 lg:p-6 animate-fade-in">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom tab bar — hidden on desktop */}
      <BottomNav />

      {/* Real-time toast notifications — bottom-left, above everything */}
      <ToastContainer />
    </div>
  )
}
