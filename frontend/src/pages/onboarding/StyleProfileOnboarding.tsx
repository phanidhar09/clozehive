/**
 * StyleProfileOnboarding — v2 premium 6-step wizard.
 *
 * Steps:
 *  1. Style Identity   — pick your vibe (multi-select style cards)
 *  2. Lifestyle        — occasions you dress for
 *  3. Fit & Comfort    — preferred fits + things you avoid
 *  4. Colors & Patterns — colour swatches + pattern picks
 *  5. Styling Goal     — what you're building
 *  6. About You        — optional body / climate context
 *
 * On submit → POST /profile/onboarding/submit → AI derives archetype + context
 * → redirect to /onboarding/result
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { ArrowLeft, ArrowRight, Check, Loader2, Sparkles, X } from 'lucide-react'
import { profileApi } from '@/lib/api'
import { cn } from '@/lib/utils'

// ─── Types ────────────────────────────────────────────────────────────────────

interface OnboardingPayload {
  style_preferences: string[]
  occasion_preferences: string[]
  fit_preferences: string[]
  avoidances: string[]
  favorite_colors: string[]
  avoided_colors: string[]
  pattern_preferences: string[]
  styling_goals: string[]
  gender: string | null
  body_types: string[]
  age_range: string | null
  climate_preferences: string[]
}

const emptyPayload = (): OnboardingPayload => ({
  style_preferences: [],
  occasion_preferences: [],
  fit_preferences: [],
  avoidances: [],
  favorite_colors: [],
  avoided_colors: [],
  pattern_preferences: [],
  styling_goals: [],
  gender: null,
  body_types: [],
  age_range: null,
  climate_preferences: [],
})

// ─── Step data ────────────────────────────────────────────────────────────────

const STEPS = [
  'style',
  'lifestyle',
  'fit',
  'colors',
  'goals',
  'body',
] as const
type StepId = (typeof STEPS)[number]

interface CardOption {
  id: string
  emoji: string
  label: string
  desc?: string
}

const STYLE_VIBES: CardOption[] = [
  { id: 'minimal',    emoji: '🤍', label: 'Minimalist',    desc: 'Clean lines, neutral palette, less is more' },
  { id: 'streetwear', emoji: '🧢', label: 'Streetwear',    desc: 'Bold graphics, sneakers, urban energy' },
  { id: 'boho',       emoji: '🌸', label: 'Boho',          desc: 'Flowing fabrics, earth tones, free spirit' },
  { id: 'corporate',  emoji: '💼', label: 'Corporate',     desc: 'Polished, tailored, boardroom-ready' },
  { id: 'casual',     emoji: '👕', label: 'Casual Comfort', desc: 'Everyday ease, relaxed and effortless' },
  { id: 'romantic',   emoji: '🌹', label: 'Romantic',      desc: 'Feminine details, soft colours, elegance' },
  { id: 'sporty',     emoji: '⚡', label: 'Athleisure',    desc: 'Performance meets style, always ready' },
  { id: 'vintage',    emoji: '🎞️', label: 'Vintage',       desc: 'Timeless classics, retro silhouettes' },
  { id: 'eclectic',   emoji: '🎨', label: 'Eclectic',      desc: 'Mix & match, bold patterns, no rules' },
  { id: 'outdoor',    emoji: '🏕️', label: 'Outdoorsy',     desc: 'Durable, functional, adventure-ready' },
]

const OCCASION_OPTIONS: CardOption[] = [
  { id: 'work',          emoji: '💻', label: 'Work / Office',    desc: 'Mon–Fri professional looks' },
  { id: 'casual',        emoji: '☕', label: 'Casual Everyday',  desc: 'Errands, coffee runs, weekends' },
  { id: 'social',        emoji: '🎉', label: 'Nights Out',       desc: 'Bars, dinners, parties' },
  { id: 'formal',        emoji: '🥂', label: 'Formal Events',    desc: 'Galas, weddings, celebrations' },
  { id: 'gym',           emoji: '🏋️', label: 'Gym & Sport',     desc: 'Workouts, runs, classes' },
  { id: 'travel',        emoji: '✈️', label: 'Travel',           desc: 'Airports, hotels, exploring' },
  { id: 'date',          emoji: '💖', label: 'Dates',            desc: 'Romantic, put-together looks' },
  { id: 'homewear',      emoji: '🏠', label: 'Homewear',         desc: 'Comfort at home / remote work' },
]

const FIT_OPTIONS: CardOption[] = [
  { id: 'slim',      emoji: '📐', label: 'Slim / Fitted',  desc: 'Close to the body, sharp silhouette' },
  { id: 'regular',   emoji: '✅', label: 'Regular',        desc: 'Classic, neither tight nor baggy' },
  { id: 'relaxed',   emoji: '😌', label: 'Relaxed',        desc: 'Comfortable room to move' },
  { id: 'oversized', emoji: '🌊', label: 'Oversized',      desc: 'Roomy, relaxed, trending' },
  { id: 'tailored',  emoji: '🪡', label: 'Tailored',       desc: 'Structured, precise, polished' },
]

const AVOID_OPTIONS: CardOption[] = [
  { id: 'tight',        emoji: '😬', label: 'Too tight',        desc: '' },
  { id: 'baggy',        emoji: '😅', label: 'Baggy / shapeless', desc: '' },
  { id: 'synthetic',    emoji: '🧪', label: 'Synthetic fabrics', desc: '' },
  { id: 'loud_prints',  emoji: '🔇', label: 'Loud prints',      desc: '' },
  { id: 'short_hems',   emoji: '📏', label: 'Very short hems',  desc: '' },
  { id: 'high_heels',   emoji: '👠', label: 'High heels',       desc: '' },
  { id: 'formal',       emoji: '🚫', label: 'Overly formal',    desc: '' },
  { id: 'revealing',    emoji: '🙈', label: 'Revealing cuts',   desc: '' },
]

const COLOR_SWATCHES = [
  { id: 'black',    hex: '#1a1a1a', label: 'Black'    },
  { id: 'white',    hex: '#f5f5f5', label: 'White'    },
  { id: 'navy',     hex: '#1e3a5f', label: 'Navy'     },
  { id: 'grey',     hex: '#9ca3af', label: 'Grey'     },
  { id: 'beige',    hex: '#d4b896', label: 'Beige'    },
  { id: 'brown',    hex: '#8b6040', label: 'Brown'    },
  { id: 'tan',      hex: '#c4a882', label: 'Tan'      },
  { id: 'olive',    hex: '#6b7c45', label: 'Olive'    },
  { id: 'burgundy', hex: '#722f37', label: 'Burgundy' },
  { id: 'red',      hex: '#dc2626', label: 'Red'      },
  { id: 'orange',   hex: '#ea580c', label: 'Orange'   },
  { id: 'yellow',   hex: '#eab308', label: 'Yellow'   },
  { id: 'green',    hex: '#16a34a', label: 'Green'    },
  { id: 'teal',     hex: '#0d9488', label: 'Teal'     },
  { id: 'blue',     hex: '#2563eb', label: 'Blue'     },
  { id: 'sky',      hex: '#0ea5e9', label: 'Sky Blue' },
  { id: 'purple',   hex: '#7c3aed', label: 'Purple'   },
  { id: 'pink',     hex: '#ec4899', label: 'Pink'     },
  { id: 'lilac',    hex: '#c4b5fd', label: 'Lilac'    },
  { id: 'cream',    hex: '#fefce8', label: 'Cream'    },
]

const PATTERN_OPTIONS: CardOption[] = [
  { id: 'solid',    emoji: '⬜', label: 'Solid / Plain',  desc: '' },
  { id: 'stripes',  emoji: '〰️', label: 'Stripes',       desc: '' },
  { id: 'plaid',    emoji: '🟦', label: 'Plaid / Check',  desc: '' },
  { id: 'floral',   emoji: '🌺', label: 'Floral',         desc: '' },
  { id: 'abstract', emoji: '🎭', label: 'Abstract',       desc: '' },
  { id: 'animal',   emoji: '🐆', label: 'Animal Print',   desc: '' },
  { id: 'geo',      emoji: '🔷', label: 'Geometric',      desc: '' },
  { id: 'camo',     emoji: '🎄', label: 'Camo',           desc: '' },
]

const GOAL_OPTIONS: CardOption[] = [
  { id: 'capsule',     emoji: '💎', label: 'Build a capsule wardrobe', desc: 'Essential pieces that work for everything' },
  { id: 'refresh',     emoji: '🔄', label: 'Refresh my style',         desc: 'New direction, modernise my looks' },
  { id: 'polished',    emoji: '✨', label: 'Look polished daily',       desc: 'Elevated everyday outfits' },
  { id: 'express',     emoji: '🎨', label: 'Express my personality',    desc: 'Clothes that say something about me' },
  { id: 'conscious',   emoji: '🌿', label: 'Shop more consciously',     desc: 'Quality over quantity, sustainable choices' },
  { id: 'occasion',    emoji: '📅', label: 'Dress for key occasions',   desc: 'Specific events I want to nail' },
]

const GENDER_OPTIONS: CardOption[] = [
  { id: 'male',              emoji: '👔', label: 'Male',              desc: '' },
  { id: 'female',            emoji: '👗', label: 'Female',            desc: '' },
  { id: 'non_binary',        emoji: '🌈', label: 'Non-binary',        desc: '' },
  { id: 'prefer_not_to_say', emoji: '🤐', label: 'Prefer not to say', desc: '' },
]

const BODY_TYPE_OPTIONS: CardOption[] = [
  { id: 'slim',       emoji: '📏', label: 'Slim',        desc: '' },
  { id: 'athletic',   emoji: '💪', label: 'Athletic',    desc: '' },
  { id: 'average',    emoji: '🙂', label: 'Average',     desc: '' },
  { id: 'curvy',      emoji: '🌊', label: 'Curvy',       desc: '' },
  { id: 'plus',       emoji: '✨', label: 'Plus size',   desc: '' },
  { id: 'petite',     emoji: '🌸', label: 'Petite',      desc: '' },
  { id: 'tall',       emoji: '🦒', label: 'Tall',        desc: '' },
  { id: 'broad',      emoji: '🏔️', label: 'Broad build', desc: '' },
]

const AGE_RANGES = ['Under 20', '20–24', '25–29', '30–34', '35–44', '45–54', '55–64', '65+']

const CLIMATE_OPTIONS: CardOption[] = [
  { id: 'tropical',    emoji: '☀️', label: 'Hot & Humid',    desc: '' },
  { id: 'warm',        emoji: '🌤️', label: 'Warm',           desc: '' },
  { id: 'temperate',   emoji: '🍂', label: 'Four seasons',   desc: '' },
  { id: 'cold',        emoji: '❄️', label: 'Cold winters',   desc: '' },
  { id: 'variable',    emoji: '🌦️', label: 'Unpredictable',  desc: '' },
]

// ─── Animations ───────────────────────────────────────────────────────────────

const STEP_VARIANTS = {
  enter:  (dir: number) => ({ x: dir > 0 ? 60 : -60, opacity: 0, scale: 0.97 }),
  center: { x: 0, opacity: 1, scale: 1 },
  exit:   (dir: number) => ({ x: dir > 0 ? -60 : 60, opacity: 0, scale: 0.97 }),
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function StyleCard({
  option,
  selected,
  onClick,
  compact = false,
}: {
  option: CardOption
  selected: boolean
  onClick: () => void
  compact?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'relative flex flex-col items-start gap-1 rounded-2xl border p-4 text-left transition-all duration-200',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500',
        compact ? 'p-3 gap-0.5' : 'p-4',
        selected
          ? 'border-brand-500 bg-brand-50 dark:bg-brand-500/15 shadow-md shadow-brand-500/10'
          : 'border-cream-200 dark:border-white/10 bg-white/80 dark:bg-white/[0.04] hover:border-brand-300 dark:hover:border-white/20',
      )}
    >
      {selected && (
        <span className="absolute top-2.5 right-2.5 flex h-5 w-5 items-center justify-center rounded-full bg-brand-500">
          <Check size={11} className="text-white" />
        </span>
      )}
      <span className={compact ? 'text-xl' : 'text-2xl'}>{option.emoji}</span>
      <span className={cn(
        'font-semibold leading-tight',
        compact ? 'text-xs' : 'text-sm',
        selected ? 'text-brand-700 dark:text-brand-300' : 'text-slate-800 dark:text-white',
      )}>
        {option.label}
      </span>
      {option.desc && !compact && (
        <span className="text-xs text-slate-500 dark:text-slate-400 leading-snug">{option.desc}</span>
      )}
    </button>
  )
}

function ColorSwatch({
  swatch,
  selected,
  avoided,
  onFav,
  onAvoid,
}: {
  swatch: { id: string; hex: string; label: string }
  selected: boolean
  avoided: boolean
  onFav: () => void
  onAvoid: () => void
}) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        className="relative w-11 h-11 rounded-full border-2 shadow-sm cursor-pointer transition-transform hover:scale-110"
        style={{
          backgroundColor: swatch.hex,
          borderColor: selected ? '#6366f1' : avoided ? '#ef4444' : 'transparent',
        }}
        title={swatch.label}
      >
        {selected && (
          <button
            type="button"
            onClick={onFav}
            className="absolute inset-0 flex items-center justify-center rounded-full"
          >
            <Check size={14} className="text-white drop-shadow" />
          </button>
        )}
        {avoided && (
          <button
            type="button"
            onClick={onAvoid}
            className="absolute inset-0 flex items-center justify-center rounded-full"
          >
            <X size={14} className="text-white drop-shadow" />
          </button>
        )}
        {!selected && !avoided && (
          <button
            type="button"
            onClick={onFav}
            className="absolute inset-0 rounded-full"
            title={`Add ${swatch.label} as favourite`}
          />
        )}
      </div>
      <span className="text-[10px] text-slate-500 dark:text-slate-400 text-center leading-none">
        {swatch.label}
      </span>
      {/* Avoid toggle below swatch */}
      {selected && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onFav() }}
          className="text-[9px] text-brand-500 hover:text-brand-700"
        >
          ✓ fave
        </button>
      )}
      {!selected && !avoided && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onAvoid() }}
          className="text-[9px] text-slate-400 hover:text-red-500"
        >
          avoid
        </button>
      )}
      {avoided && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onAvoid() }}
          className="text-[9px] text-red-400 hover:text-red-600"
        >
          ✗ avoid
        </button>
      )}
    </div>
  )
}

// ─── Step content renderers ───────────────────────────────────────────────────

function StepStyle({
  form,
  toggle,
}: {
  form: OnboardingPayload
  toggle: (key: keyof OnboardingPayload, val: string) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Your Style Vibe</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Pick everything that resonates — you can mix and match.
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {STYLE_VIBES.map(opt => (
          <StyleCard
            key={opt.id}
            option={opt}
            selected={form.style_preferences.includes(opt.id)}
            onClick={() => toggle('style_preferences', opt.id)}
          />
        ))}
      </div>
    </div>
  )
}

function StepLifestyle({
  form,
  toggle,
}: {
  form: OnboardingPayload
  toggle: (key: keyof OnboardingPayload, val: string) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Your Lifestyle</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Where do you wear your clothes most? Select all that apply.
        </p>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {OCCASION_OPTIONS.map(opt => (
          <StyleCard
            key={opt.id}
            option={opt}
            selected={form.occasion_preferences.includes(opt.id)}
            onClick={() => toggle('occasion_preferences', opt.id)}
          />
        ))}
      </div>
    </div>
  )
}

function StepFit({
  form,
  toggle,
}: {
  form: OnboardingPayload
  toggle: (key: keyof OnboardingPayload, val: string) => void
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Fit & Comfort</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Tell me how you like your clothes to fit — and what to avoid.
        </p>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Preferred fits</p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {FIT_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.fit_preferences.includes(opt.id)}
              onClick={() => toggle('fit_preferences', opt.id)}
            />
          ))}
        </div>
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Things I avoid</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {AVOID_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.avoidances.includes(opt.id)}
              onClick={() => toggle('avoidances', opt.id)}
              compact
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function StepColors({
  form,
  setForm,
}: {
  form: OnboardingPayload
  setForm: React.Dispatch<React.SetStateAction<OnboardingPayload>>
}) {
  const toggleFav = (id: string) => {
    setForm(f => ({
      ...f,
      favorite_colors: f.favorite_colors.includes(id)
        ? f.favorite_colors.filter(c => c !== id)
        : [...f.favorite_colors, id],
      avoided_colors: f.avoided_colors.filter(c => c !== id),
    }))
  }
  const toggleAvoid = (id: string) => {
    setForm(f => ({
      ...f,
      avoided_colors: f.avoided_colors.includes(id)
        ? f.avoided_colors.filter(c => c !== id)
        : [...f.avoided_colors, id],
      favorite_colors: f.favorite_colors.filter(c => c !== id),
    }))
  }
  const toggle = (key: keyof OnboardingPayload, val: string) => {
    setForm(f => {
      const arr = f[key] as string[]
      return {
        ...f,
        [key]: arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val],
      }
    })
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Your Colour Story</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Click a swatch to mark it as a favourite. Hit "avoid" to exclude it from recommendations.
        </p>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Colours</p>
        <div className="flex flex-wrap gap-4">
          {COLOR_SWATCHES.map(sw => (
            <ColorSwatch
              key={sw.id}
              swatch={sw}
              selected={form.favorite_colors.includes(sw.id)}
              avoided={form.avoided_colors.includes(sw.id)}
              onFav={() => toggleFav(sw.id)}
              onAvoid={() => toggleAvoid(sw.id)}
            />
          ))}
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Patterns I love</p>
        <div className="grid grid-cols-4 sm:grid-cols-8 gap-3">
          {PATTERN_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.pattern_preferences.includes(opt.id)}
              onClick={() => toggle('pattern_preferences', opt.id)}
              compact
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function StepGoals({
  form,
  toggle,
}: {
  form: OnboardingPayload
  toggle: (key: keyof OnboardingPayload, val: string) => void
}) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Your Styling Goal</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          What are you trying to achieve? Pick one or more.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {GOAL_OPTIONS.map(opt => (
          <StyleCard
            key={opt.id}
            option={opt}
            selected={form.styling_goals.includes(opt.id)}
            onClick={() => toggle('styling_goals', opt.id)}
          />
        ))}
      </div>
    </div>
  )
}

function StepBody({
  form,
  setForm,
  toggle,
}: {
  form: OnboardingPayload
  setForm: React.Dispatch<React.SetStateAction<OnboardingPayload>>
  toggle: (key: keyof OnboardingPayload, val: string) => void
}) {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-slate-900 dark:text-white">A Little About You</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Optional — but it helps us suggest the best fits and silhouettes for your body.
        </p>
      </div>

      {/* Gender */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">I shop in the</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {GENDER_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.gender === opt.id}
              onClick={() => setForm(f => ({ ...f, gender: f.gender === opt.id ? null : opt.id }))}
              compact
            />
          ))}
        </div>
      </div>

      {/* Body type */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Body type</p>
        <div className="grid grid-cols-4 sm:grid-cols-8 gap-3">
          {BODY_TYPE_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.body_types.includes(opt.id)}
              onClick={() => toggle('body_types', opt.id)}
              compact
            />
          ))}
        </div>
      </div>

      {/* Age range */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">Age range</p>
        <div className="flex flex-wrap gap-2">
          {AGE_RANGES.map(range => (
            <button
              key={range}
              type="button"
              onClick={() => setForm(f => ({ ...f, age_range: f.age_range === range ? null : range }))}
              className={cn(
                'rounded-full border px-4 py-1.5 text-sm font-medium transition',
                form.age_range === range
                  ? 'border-brand-500 bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300'
                  : 'border-cream-200 dark:border-white/10 text-slate-600 dark:text-slate-300 hover:border-brand-300',
              )}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Climate */}
      <div>
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-400 mb-3">My climate</p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {CLIMATE_OPTIONS.map(opt => (
            <StyleCard
              key={opt.id}
              option={opt}
              selected={form.climate_preferences.includes(opt.id)}
              onClick={() => toggle('climate_preferences', opt.id)}
              compact
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Main Component ───────────────────────────────────────────────────────────

const STEP_META: Record<StepId, { title: string; subtitle: string; icon: string }> = {
  style:     { title: 'Style',     subtitle: 'Your vibe',          icon: '🎨' },
  lifestyle: { title: 'Lifestyle', subtitle: 'Your occasions',     icon: '📅' },
  fit:       { title: 'Fit',       subtitle: 'Your comfort zone',  icon: '✂️' },
  colors:    { title: 'Colours',   subtitle: 'Your palette',       icon: '🎨' },
  goals:     { title: 'Goals',     subtitle: 'What you want',      icon: '🎯' },
  body:      { title: 'About You', subtitle: 'Optional context',   icon: '👤' },
}

export default function StyleProfileOnboarding() {
  const navigate = useNavigate()
  const [stepIdx, setStepIdx] = useState(0)
  const [direction, setDirection] = useState(1)
  const [form, setForm] = useState<OnboardingPayload>(emptyPayload())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const prevIdx = useRef(0)

  const step = STEPS[stepIdx]!

  // Pre-fill if profile exists
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const existing = await profileApi.getStyleProfile()
        if (cancelled || !existing) return
        setForm(f => ({
          ...f,
          style_preferences:    existing.style_preferences    ?? [],
          occasion_preferences: existing.occasion_preferences ?? [],
          fit_preferences:      existing.fit_preferences      ?? [],
          favorite_colors:      existing.favorite_colors      ?? [],
          avoided_colors:       existing.avoided_colors       ?? [],
          gender:               existing.gender               ?? null,
          body_types:           existing.body_types           ?? [],
          age_range:            existing.age_range            ?? null,
          climate_preferences:  existing.climate_preferences  ?? [],
          styling_goals:        (existing as { styling_goals?: string[] }).styling_goals      ?? [],
          avoidances:           (existing as { avoidances?: string[] }).avoidances            ?? [],
          pattern_preferences:  (existing as { pattern_preferences?: string[] }).pattern_preferences ?? [],
        }))
      } catch {
        /* silent */
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const toggle = (key: keyof OnboardingPayload, val: string) => {
    setForm(f => {
      const arr = f[key] as string[]
      return {
        ...f,
        [key]: arr.includes(val) ? arr.filter(v => v !== val) : [...arr, val],
      }
    })
  }

  const goTo = (idx: number) => {
    setDirection(idx > prevIdx.current ? 1 : -1)
    prevIdx.current = idx
    setStepIdx(idx)
  }

  const goNext = () => {
    if (stepIdx < STEPS.length - 1) {
      goTo(stepIdx + 1)
    }
  }

  const goPrev = () => {
    if (stepIdx > 0) goTo(stepIdx - 1)
  }

  const handleSkip = async () => {
    setSaving(true)
    try {
      await profileApi.completeOnboarding(true)
      navigate('/closet')
    } catch {
      navigate('/closet')
    } finally {
      setSaving(false)
    }
  }

  const handleSubmit = async () => {
    setSaving(true)
    setError(null)
    try {
      const profile = await profileApi.submitOnboarding(form as unknown as Record<string, unknown>)
      // Store derived data in sessionStorage for the result page
      sessionStorage.setItem('onboarding_result', JSON.stringify({
        style_archetype:    (profile as unknown as { style_archetype?: string }).style_archetype,
        style_summary:      profile.style_preferences,
        style_preferences:  profile.style_preferences,
        occasion_preferences: profile.occasion_preferences,
        styling_goals:      form.styling_goals,
      }))
      navigate('/onboarding/result')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Please try again.')
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
      </div>
    )
  }

  const isLast = stepIdx === STEPS.length - 1

  return (
    <div className="min-h-screen flex flex-col">
      {/* Fixed top bar */}
      <header className="sticky top-0 z-20 bg-white/80 dark:bg-slate-950/80 backdrop-blur border-b border-cream-200 dark:border-white/[0.06]">
        <div className="mx-auto max-w-4xl px-4 py-3 flex items-center gap-4">
          {/* Logo */}
          <span className="flex items-center gap-2 font-bold text-brand-600 dark:text-brand-400 text-base shrink-0">
            <Sparkles size={18} />
            ClozeHive
          </span>

          {/* Progress dots */}
          <div className="flex-1 flex items-center justify-center gap-2">
            {STEPS.map((s, i) => (
              <button
                key={s}
                type="button"
                onClick={() => i < stepIdx && goTo(i)}
                className={cn(
                  'rounded-full transition-all duration-300',
                  i === stepIdx
                    ? 'w-6 h-2.5 bg-brand-500'
                    : i < stepIdx
                    ? 'w-2.5 h-2.5 bg-brand-300 hover:bg-brand-400 cursor-pointer'
                    : 'w-2.5 h-2.5 bg-cream-300 dark:bg-slate-700 cursor-default',
                )}
                aria-label={STEP_META[s].title}
              />
            ))}
          </div>

          {/* Step count + skip */}
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-xs text-slate-400 dark:text-slate-500">
              {stepIdx + 1} / {STEPS.length}
            </span>
            <button
              type="button"
              onClick={handleSkip}
              disabled={saving}
              className="text-xs text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition"
            >
              Skip
            </button>
          </div>
        </div>
      </header>

      {/* Step content */}
      <main className="flex-1 mx-auto w-full max-w-4xl px-4 py-8 overflow-hidden">
        <AnimatePresence mode="wait" custom={direction}>
          <motion.div
            key={step}
            custom={direction}
            variants={STEP_VARIANTS}
            initial="enter"
            animate="center"
            exit="exit"
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
          >
            {step === 'style' && (
              <StepStyle form={form} toggle={toggle} />
            )}
            {step === 'lifestyle' && (
              <StepLifestyle form={form} toggle={toggle} />
            )}
            {step === 'fit' && (
              <StepFit form={form} toggle={toggle} />
            )}
            {step === 'colors' && (
              <StepColors form={form} setForm={setForm} />
            )}
            {step === 'goals' && (
              <StepGoals form={form} toggle={toggle} />
            )}
            {step === 'body' && (
              <StepBody form={form} setForm={setForm} toggle={toggle} />
            )}
          </motion.div>
        </AnimatePresence>

        {/* Error */}
        {error && (
          <div className="mt-4 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-700/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}
      </main>

      {/* Bottom navigation */}
      <footer className="sticky bottom-0 bg-white/80 dark:bg-slate-950/80 backdrop-blur border-t border-cream-200 dark:border-white/[0.06]">
        <div className="mx-auto max-w-4xl px-4 py-4 flex items-center justify-between gap-4">
          {/* Back */}
          <button
            type="button"
            onClick={goPrev}
            disabled={stepIdx === 0 || saving}
            className={cn(
              'flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition',
              stepIdx === 0
                ? 'invisible'
                : 'text-slate-600 dark:text-slate-300 hover:bg-cream-100 dark:hover:bg-white/[0.06]',
            )}
          >
            <ArrowLeft size={16} />
            Back
          </button>

          {/* Step label */}
          <div className="text-center">
            <p className="text-xs text-slate-400 dark:text-slate-500">{STEP_META[step].subtitle}</p>
          </div>

          {/* Next / Finish */}
          {isLast ? (
            <button
              type="button"
              onClick={handleSubmit}
              disabled={saving}
              className="flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 active:bg-brand-700 text-white px-6 py-2.5 text-sm font-semibold shadow-md shadow-brand-500/25 transition disabled:opacity-60"
            >
              {saving ? (
                <><Loader2 size={15} className="animate-spin" /> Building profile…</>
              ) : (
                <><Sparkles size={15} /> Build My Profile</>
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={goNext}
              className="flex items-center gap-2 rounded-xl bg-brand-500 hover:bg-brand-600 active:bg-brand-700 text-white px-6 py-2.5 text-sm font-semibold shadow-md shadow-brand-500/25 transition"
            >
              Next
              <ArrowRight size={16} />
            </button>
          )}
        </div>
      </footer>
    </div>
  )
}
