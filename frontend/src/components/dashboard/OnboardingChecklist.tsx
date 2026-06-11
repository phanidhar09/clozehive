import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, ChevronRight, X, PartyPopper } from 'lucide-react'
import { Link } from 'react-router-dom'
import { profileApi, outfitHistoryApi, tripsApi } from '@/lib/api'
import { useApp } from '@/store'

const AI_CHAT_TRIED_KEY = 'ch_ai_chat_tried'

function checklistDismissedKey(userId: string) {
  return `ch_checklist_dismissed_${userId}`
}

interface Stage {
  id: string
  title: string
  description: string
  done: boolean
  href: string
}

export default function OnboardingChecklist() {
  const { closetItems, currentUser } = useApp()
  const [profileDone, setProfileDone] = useState(false)
  const [outfitDone, setOutfitDone] = useState(false)
  const [aiChatDone, setAiChatDone] = useState(false)
  const [planningDone, setPlanningDone] = useState(false)
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
      outfitHistoryApi.list(50, 0).catch(() => null),
      tripsApi.listSaved().catch(() => []),
    ]).then(([profile, outfits, savedTrips]) => {
      if (cancelled) return
      if (profile) setProfileDone(profile.onboarding_completed)
      if (outfits) {
        setOutfitDone(outfits.count > 0)
        setPlanningDone((outfits.results ?? []).some(r => r.was_saved) || (savedTrips?.length ?? 0) > 0)
      } else {
        setPlanningDone((savedTrips?.length ?? 0) > 0)
      }
      setAiChatDone(localStorage.getItem(AI_CHAT_TRIED_KEY) === '1')
      setReady(true)
    })

    return () => { cancelled = true }
  }, [currentUser])

  const stages: Stage[] = [
    {
      id: 'account_setup',
      title: 'Set up your style profile',
      description: 'Tell FANI your taste — takes about 2 minutes',
      done: profileDone,
      href: '/onboarding/style-profile',
    },
    {
      id: 'closet_bootstrapping',
      title: 'Add your first 5 items',
      description: 'Snap photos and FANI detects and tags them for you',
      done: closetItems.length >= 5,
      href: '/upload',
    },
    {
      id: 'outfit_creation',
      title: 'Build your first outfit',
      description: 'Mix and match pieces from your own closet',
      done: outfitDone,
      href: '/outfit-builder',
    },
    {
      id: 'ai_assistance',
      title: 'Ask FANI anything',
      description: 'Get styling advice from your AI stylist',
      done: aiChatDone,
      href: '/ai-stylist',
    },
    {
      id: 'planning_extensions',
      title: 'Plan a trip or save a look',
      description: 'Packing plans and saved outfits for later',
      done: planningDone,
      href: '/travel',
    },
  ]

  const completedCount = stages.filter(s => s.done).length
  const allDone = completedCount === stages.length
  const progress = Math.round((completedCount / stages.length) * 100)

  if (!ready || dismissed) return null

  const dismiss = () => {
    if (currentUser) {
      try { localStorage.setItem(checklistDismissedKey(currentUser.id), '1') } catch { /* ignore */ }
    }
    setDismissed(true)
  }

  return (
    <div className="relative rounded-3xl border border-brand-200/70 bg-gradient-to-br from-brand-50/90 via-white/60 to-brand-50/80 p-5 dark:border-brand-500/20 dark:from-brand-900/40 dark:via-slate-900/20 dark:to-brand-900/30">
      <button
        onClick={dismiss}
        aria-label="Dismiss checklist"
        className="absolute right-4 top-4 rounded-lg p-1 text-slate-400 transition-colors hover:bg-black/5 hover:text-slate-600 dark:hover:bg-white/[0.06] dark:hover:text-white/60"
      >
        <X size={14} />
      </button>

      <div className="mb-4 pr-6">
        {allDone ? (
          <div className="flex items-center gap-2">
            <PartyPopper size={18} className="text-brand-500" />
            <div>
              <h3 className="font-display font-bold text-slate-800 dark:text-white">You're all set!</h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">You've explored everything ClozéHive can do.</p>
            </div>
          </div>
        ) : (
          <div>
            <h3 className="font-display font-bold text-slate-800 dark:text-white">Get started with ClozéHive</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {completedCount} of {stages.length} done
            </p>
          </div>
        )}
      </div>

      <div className="mb-4 h-1.5 overflow-hidden rounded-full bg-brand-100 dark:bg-brand-900/40">
        <div
          className="h-full rounded-full bg-gradient-to-r from-brand-600 to-brand-600 transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="space-y-1">
        {stages.map(step => (
          step.done ? (
            <div key={step.id} className="flex items-center gap-3 rounded-2xl px-3 py-2.5">
              <CheckCircle2 size={17} className="flex-shrink-0 text-emerald-500" />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-slate-500 line-through dark:text-white/50">{step.title}</p>
                <p className="text-[11px] text-slate-400 dark:text-white/35">{step.description}</p>
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
                <p className="text-sm font-semibold text-slate-700 dark:text-white">{step.title}</p>
                <p className="text-xs text-slate-400 dark:text-white/40">{step.description}</p>
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
