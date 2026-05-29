import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, ChevronRight, X, PartyPopper } from 'lucide-react'
import { Link } from 'react-router-dom'
import { profileApi, outfitHistoryApi } from '@/lib/api'
import { useApp } from '@/store'
import { cn } from '@/lib/utils'

const AI_CHAT_TRIED_KEY = 'ch_ai_chat_tried'

function checklistDismissedKey(userId: string) {
  return `ch_checklist_dismissed_${userId}`
}

interface Step {
  id: string
  label: string
  hint: string
  done: boolean
  href: string
}

export default function OnboardingChecklist() {
  const { closetItems, currentUser } = useApp()
  const [profileDone, setProfileDone] = useState(false)
  const [outfitDone, setOutfitDone] = useState(false)
  const [aiChatDone, setAiChatDone] = useState(false)
  const [dismissed, setDismissed] = useState(false)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    if (!currentUser) return

    if (localStorage.getItem(checklistDismissedKey(currentUser.id)) === '1') {
      setDismissed(true)
      setReady(true)
      return
    }

    let cancelled = false

    Promise.all([
      profileApi.getOnboardingStatus().catch(() => null),
      outfitHistoryApi.list(1, 0).catch(() => null),
    ]).then(([profile, outfits]) => {
      if (cancelled) return
      if (profile) setProfileDone(profile.onboarding_completed)
      if (outfits) setOutfitDone(outfits.count > 0)
      setAiChatDone(localStorage.getItem(AI_CHAT_TRIED_KEY) === '1')
      setReady(true)
    })

    return () => { cancelled = true }
  }, [currentUser])

  const itemsDone = closetItems.length >= 5

  const steps: Step[] = [
    {
      id: 'profile',
      label: 'Complete your style profile',
      hint: 'Unlocks personalised outfit recommendations',
      done: profileDone,
      href: '/onboarding/style-profile',
    },
    {
      id: 'items',
      label: 'Add 5 items to your closet',
      hint: `${Math.min(closetItems.length, 5)} of 5 added`,
      done: itemsDone,
      href: '/upload',
    },
    {
      id: 'outfit',
      label: 'Build your first outfit',
      hint: 'Mix and match in the outfit builder',
      done: outfitDone,
      href: '/outfit-builder',
    },
    {
      id: 'ai',
      label: 'Chat with FANI, your AI stylist',
      hint: 'Get personalised fashion advice',
      done: aiChatDone,
      href: '/ai-stylist',
    },
  ]

  const completedCount = steps.filter(s => s.done).length
  const allDone = completedCount === steps.length
  const progress = Math.round((completedCount / steps.length) * 100)

  // Don't render until data is loaded, or if dismissed
  if (!ready || dismissed) return null

  const dismiss = () => {
    if (currentUser) {
      try { localStorage.setItem(checklistDismissedKey(currentUser.id), '1') } catch { /* ignore */ }
    }
    setDismissed(true)
  }

  return (
    <div className="relative rounded-3xl border border-brand-200/70 bg-gradient-to-br from-brand-50/90 via-white/60 to-brand-50/80 p-5 dark:border-brand-500/20 dark:from-brand-900/40 dark:via-slate-900/20 dark:to-brand-900/30">

      {/* Dismiss */}
      <button
        onClick={dismiss}
        aria-label="Dismiss checklist"
        className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 transition-colors hover:bg-black/5 hover:text-slate-600 dark:hover:bg-white/[0.06] dark:hover:text-white/60"
      >
        <X size={14} />
      </button>

      {/* Header */}
      <div className="mb-4 pr-6">
        {allDone ? (
          <div className="flex items-center gap-2">
            <PartyPopper size={18} className="text-brand-500" />
            <div>
              <h3 className="font-display font-bold text-slate-800 dark:text-white">You're all set!</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">Your wardrobe is ready. Dismiss this whenever.</p>
            </div>
          </div>
        ) : (
          <div>
            <h3 className="font-display font-bold text-slate-800 dark:text-white">Get started</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {completedCount} of {steps.length} steps complete
            </p>
          </div>
        )}
      </div>

      {/* Progress bar */}
      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/40">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-600 transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      {/* Steps */}
      <div className="space-y-1">
        {steps.map(step => (
          step.done ? (
            <div
              key={step.id}
              className="flex items-center gap-3 rounded-2xl px-3 py-2.5 opacity-50"
            >
              <CheckCircle2 size={17} className="flex-shrink-0 text-emerald-500" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-400 line-through dark:text-white/30">
                  {step.label}
                </p>
              </div>
            </div>
          ) : (
            <Link
              key={step.id}
              to={step.href}
              className="group flex items-center gap-3 rounded-2xl px-3 py-2.5 transition-all hover:bg-white/70 dark:hover:bg-white/[0.05]"
            >
              <Circle size={17} className="flex-shrink-0 text-brand-300 dark:text-brand-600" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-700 dark:text-white">{step.label}</p>
                <p className="text-xs text-slate-400 dark:text-white/40">{step.hint}</p>
              </div>
              <ChevronRight
                size={14}
                className="flex-shrink-0 text-slate-300 transition-colors group-hover:text-brand-500 dark:text-white/20 dark:group-hover:text-brand-400"
              />
            </Link>
          )
        ))}
      </div>
    </div>
  )
}
