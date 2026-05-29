import { ReactNode } from 'react'
import { Sparkles, UserPlus, Shirt, Wand2, Check } from 'lucide-react'

/**
 * Shared split-screen shell for the auth pages.
 *
 * The left brand panel surfaces the *actual* product workflow:
 *   1. Create your free account     → /signup
 *   2. Set up your style profile     → /onboarding/style-profile  (runs right after signup)
 *   3. Get AI outfits from your closet
 *
 * `activeStep` highlights where the user currently is so the journey is transparent.
 */

const STEPS = [
  { icon: UserPlus, title: 'Create your account', desc: 'Free — no credit card needed' },
  { icon: Shirt,    title: 'Set up your style profile', desc: 'A 2-minute onboarding to learn your taste' },
  { icon: Wand2,    title: 'Get AI outfits & insights', desc: 'Daily looks from clothes you own' },
]

interface AuthShellProps {
  /** Hero heading on the brand panel (supports an accent <span>). */
  brandHeading: ReactNode
  brandSub: string
  /** 1-based step to highlight (0 = none, e.g. login). */
  activeStep?: number
  /** Right-side content (the form card). */
  children: ReactNode
}

export default function AuthShell({ brandHeading, brandSub, activeStep = 0, children }: AuthShellProps) {
  return (
    <div className="min-h-screen lg:h-screen lg:overflow-hidden flex bg-white dark:bg-slate-900">
      {/* ── Left brand panel ─────────────────────────────────── */}
      <div
        className="hidden lg:flex lg:w-[46%] lg:h-screen relative overflow-hidden flex-col justify-between p-12"
        style={{ background: 'linear-gradient(150deg, #0B3B38 0%, #0D9488 52%, #059669 100%)' }}
      >
        {/* Ambient glows */}
        <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full bg-white/5 blur-2xl" />
        <div className="absolute -bottom-32 -left-16 w-96 h-96 rounded-full bg-emerald-300/10 blur-3xl" />
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 w-64 h-64 rounded-full bg-teal-300/10 blur-2xl" />

        {/* Logo */}
        <div className="relative flex items-center gap-3">
          <div className="w-11 h-11 rounded-2xl bg-white/15 backdrop-blur flex items-center justify-center shadow-lg border border-white/20">
            <Sparkles size={22} className="text-white" />
          </div>
          <div>
            <div className="font-display font-bold text-xl text-white">ClozéHive</div>
            <div className="text-xs text-white/55 font-medium tracking-wide">AI-Powered Wardrobe</div>
          </div>
        </div>

        {/* Hero + workflow */}
        <div className="relative space-y-8">
          <div>
            <h1 className="font-display font-bold text-[2.5rem] leading-[1.1] text-white mb-3">
              {brandHeading}
            </h1>
            <p className="text-white/65 text-base leading-relaxed max-w-sm">{brandSub}</p>
          </div>

          {/* Workflow stepper — communicates the real flow */}
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-white/45 mb-3">
              How it works
            </p>
            {STEPS.map((s, i) => {
              const stepNum = i + 1
              const done = activeStep > stepNum
              const current = activeStep === stepNum
              const Icon = done ? Check : s.icon
              return (
                <div key={s.title} className="flex items-start gap-3.5 py-2">
                  <div className="relative flex flex-col items-center">
                    <div
                      className={[
                        'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 transition-all border',
                        current
                          ? 'bg-white text-emerald-700 border-white shadow-lg shadow-black/10'
                          : done
                          ? 'bg-white/25 text-white border-white/30'
                          : 'bg-white/10 text-white/70 border-white/15',
                      ].join(' ')}
                    >
                      <Icon size={16} />
                    </div>
                    {i < STEPS.length - 1 && (
                      <div className="w-px h-5 bg-white/15 mt-1" />
                    )}
                  </div>
                  <div className="pt-1">
                    <p className={`text-sm font-semibold ${current ? 'text-white' : 'text-white/80'}`}>
                      {s.title}
                    </p>
                    <p className="text-xs text-white/45 leading-snug mt-0.5">{s.desc}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Quote */}
        <blockquote className="relative text-white/50 text-sm italic border-l-2 border-white/20 pl-4">
          &ldquo;Getting dressed has never been this effortless.&rdquo;
        </blockquote>
      </div>

      {/* ── Right content panel ──────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 lg:h-screen lg:overflow-y-auto">
        <div className="w-full max-w-md py-6 animate-slide-up">
          {/* Mobile logo */}
          <div className="lg:hidden flex items-center gap-2 mb-8">
            <div className="w-9 h-9 rounded-xl bg-gradient-brand flex items-center justify-center">
              <Sparkles size={18} className="text-white" />
            </div>
            <span className="font-display font-bold text-lg text-slate-800 dark:text-slate-100">ClozéHive</span>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}
