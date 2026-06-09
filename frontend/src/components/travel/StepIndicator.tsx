import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

// ── Step indicator ────────────────────────────────────────────────────────

export function StepIndicator({ step }: { step: 1 | 2 | 3 }) {
  const steps = [
    { n: 1, label: 'Trip Details' },
    { n: 2, label: 'Activities' },
    { n: 3, label: 'Your Planner' },
  ]
  return (
    <div className="flex items-center gap-2">
      {steps.map((s, i) => (
        <div key={s.n} className="flex items-center gap-2">
          <div className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-semibold transition-all',
            step === s.n
              ? 'bg-brand-500 text-white shadow-sm shadow-brand-500/30'
              : step > s.n
                ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400'
                : 'bg-slate-100 dark:bg-white/5 text-slate-400 dark:text-white/30',
          )}>
            {step > s.n
              ? <Check size={11} />
              : <span className={cn('w-4 h-4 rounded-full text-center leading-4 text-[10px]',
                  step === s.n ? 'bg-white/30' : 'bg-current/20'
                )}>{s.n}</span>
            }
            <span className="hidden sm:inline">{s.label}</span>
          </div>
          {i < steps.length - 1 && (
            <div className={cn('w-6 h-px', step > s.n ? 'bg-emerald-300 dark:bg-emerald-700/50' : 'bg-slate-200 dark:bg-white/10')} />
          )}
        </div>
      ))}
    </div>
  )
}
