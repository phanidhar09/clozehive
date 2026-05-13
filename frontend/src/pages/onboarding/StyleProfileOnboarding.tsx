import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Loader2,
  Sparkles,
} from 'lucide-react'
import type { StyleGender, UserStyleProfile } from '@/types'
import { profileApi } from '@/lib/api'
import {
  AGE_RANGES,
  CLIMATE_PREFS,
  OCCASION_PREFS,
  STYLE_IDENTITY_OPTIONS,
  STYLE_TAGS,
  optionsForGender,
  type StyleIdentityKey,
} from '@/config/styleProfileOptions'

const STEPS = [
  'welcome',
  'basic',
  'body',
  'fit',
  'sizes',
  'style',
  'colors',
  'occasions',
  'climate',
  'review',
] as const

type StepId = (typeof STEPS)[number]

const emptyForm = (): Partial<UserStyleProfile> => ({
  gender: null,
  custom_gender: null,
  height_value: null,
  height_unit: 'cm',
  weight_value: null,
  weight_unit: 'lb',
  age_range: null,
  body_types: [],
  custom_body_type: null,
  fit_preferences: [],
  custom_fit_notes: null,
  size_profile: {},
  custom_size_notes: null,
  style_preferences: [],
  favorite_colors: [],
  avoided_colors: [],
  neutral_color_preference: null,
  bold_color_preference: null,
  occasion_preferences: [],
  climate_preferences: [],
})

function Chip({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-2xl border px-3 py-2 text-left text-sm font-medium transition ${
        active
          ? 'border-brand-500 bg-brand-50 text-brand-800 dark:bg-brand-500/15 dark:text-brand-200'
          : 'border-cream-200 bg-white/80 text-slate-700 hover:border-brand-300 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200'
      }`}
    >
      {children}
    </button>
  )
}

export default function StyleProfileOnboarding() {
  const navigate = useNavigate()
  const [stepIdx, setStepIdx] = useState(0)
  const [form, setForm] = useState<Partial<UserStyleProfile>>(emptyForm)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [colorIn, setColorIn] = useState({ fav: '', avoid: '' })

  const step: StepId = STEPS[stepIdx] ?? 'welcome'

  const identityKey: StyleIdentityKey = useMemo(() => {
    const g = form.gender
    if (g === 'male' || g === 'female' || g === 'non_binary' || g === 'prefer_not_to_say' || g === 'custom')
      return g
    return 'prefer_not_to_say'
  }, [form.gender])

  const dynamic = useMemo(() => optionsForGender(identityKey), [identityKey])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const existing = await profileApi.getStyleProfile()
        if (cancelled) return
        if (existing) {
          setForm({
            ...emptyForm(),
            ...existing,
            size_profile: { ...existing.size_profile },
          })
        }
      } catch {
        /* ignore */
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const persistPatch = useCallback(async (patch: Partial<UserStyleProfile>) => {
    setSaving(true)
    setError(null)
    try {
      const next = await profileApi.patchStyleProfile(patch as Record<string, unknown>)
      setForm(f => ({ ...f, ...next, size_profile: { ...next.size_profile } }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save')
    } finally {
      setSaving(false)
    }
  }, [])

  const goNext = async () => {
    const patch: Record<string, unknown> = {}
    if (step === 'basic') {
      if (form.gender) patch.gender = form.gender
      if (form.custom_gender) patch.custom_gender = form.custom_gender
      if (form.height_value != null && form.height_unit) {
        patch.height_value = form.height_value
        patch.height_unit = form.height_unit
      }
      if (form.weight_value != null && form.weight_unit) {
        patch.weight_value = form.weight_value
        patch.weight_unit = form.weight_unit
      }
      if (form.age_range) patch.age_range = form.age_range
    }
    if (step === 'body') {
      patch.body_types = form.body_types ?? []
      patch.custom_body_type = form.custom_body_type
    }
    if (step === 'fit') {
      patch.fit_preferences = form.fit_preferences ?? []
      patch.custom_fit_notes = form.custom_fit_notes
    }
    if (step === 'sizes') {
      patch.size_profile = form.size_profile ?? {}
      patch.custom_size_notes = form.custom_size_notes
    }
    if (step === 'style') patch.style_preferences = form.style_preferences ?? []
    if (step === 'colors') {
      patch.favorite_colors = form.favorite_colors ?? []
      patch.avoided_colors = form.avoided_colors ?? []
      patch.neutral_color_preference = form.neutral_color_preference
      patch.bold_color_preference = form.bold_color_preference
    }
    if (step === 'occasions') patch.occasion_preferences = form.occasion_preferences ?? []
    if (step === 'climate') patch.climate_preferences = form.climate_preferences ?? []

    if (Object.keys(patch).length) await persistPatch(patch)

    if (stepIdx < STEPS.length - 1) setStepIdx(stepIdx + 1)
  }

  const goBack = () => {
    if (stepIdx <= 0) return
    setStepIdx(stepIdx - 1)
  }

  const finish = async (skipped: boolean) => {
    setSaving(true)
    setError(null)
    try {
      if (step === 'review' && !skipped) {
        await persistPatch({
          ...form,
          gender: form.gender ?? undefined,
        } as UserStyleProfile)
      }
      try {
        await profileApi.completeOnboarding(skipped)
      } catch {
        /* best-effort — navigate regardless so the user is never stuck */
      }
      // Pass state so Dashboard skips its own onboarding redirect check.
      navigate('/dashboard', { replace: true, state: { onboardingJustDone: true, skipped } })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not complete')
      // Always escape on skip — never trap the user here.
      if (skipped) navigate('/dashboard', { replace: true, state: { onboardingJustDone: true, skipped: true } })
    } finally {
      setSaving(false)
    }
  }

  const toggleMulti = (field: 'body_types' | 'fit_preferences' | 'style_preferences' | 'occasion_preferences' | 'climate_preferences', value: string) => {
    setForm(f => {
      const cur = new Set(f[field] ?? [])
      if (cur.has(value)) cur.delete(value)
      else cur.add(value)
      return { ...f, [field]: [...cur] }
    })
  }

  const progress = Math.round(((stepIdx + 1) / STEPS.length) * 100)

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-cream-50 dark:bg-slate-950">
        <Loader2 className="h-8 w-8 animate-spin text-brand-500" />
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-cream-50 via-white to-brand-50/30 px-4 py-10 dark:from-slate-950 dark:via-slate-900 dark:to-slate-950">
      <div className="mx-auto max-w-lg">
        <div className="mb-8">
          <div className="mb-2 flex items-center justify-between text-xs font-medium text-slate-500 dark:text-slate-400">
            <span>Style Profile</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
            <div
              className="h-full rounded-full bg-gradient-to-r from-brand-500 to-violet-500 transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        <div className="rounded-3xl border border-cream-200 bg-white/90 p-6 shadow-card dark:border-white/10 dark:bg-slate-900/90">
          {error && (
            <div className="mb-4 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
              {error}
            </div>
          )}

          {step === 'welcome' && (
            <div className="space-y-4 text-center">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-500/10 text-brand-600 dark:text-brand-400">
                <Sparkles size={28} />
              </div>
              <h1 className="font-display text-2xl font-bold text-slate-900 dark:text-white">
                Build Your Style Profile
              </h1>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                This helps CLOZEHIVE recommend outfits that match your fit, comfort, style, and occasions.
                You can update it anytime.
              </p>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                This information is used only to personalize outfit and packing recommendations. You can
                skip it now and update it anytime.
              </p>
              <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:justify-center">
                <button type="button" className="btn-primary w-full sm:w-auto" onClick={() => setStepIdx(1)}>
                  Start
                </button>
                <button
                  type="button"
                  className="btn-secondary w-full sm:w-auto"
                  disabled={saving}
                  onClick={() => finish(true)}
                >
                  Skip for now
                </button>
              </div>
            </div>
          )}

          {step === 'basic' && (
            <div className="space-y-4">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Basic profile</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                These details help the AI recommend outfits that match your fit, comfort, and style preferences.
              </p>
              <div>
                <p className="mb-2 text-xs font-semibold text-slate-600 dark:text-slate-300">Gender / style identity</p>
                <div className="flex flex-wrap gap-2">
                  {STYLE_IDENTITY_OPTIONS.map(opt => (
                    <Chip
                      key={opt.id}
                      active={form.gender === opt.id}
                      onClick={() => setForm(f => ({ ...f, gender: opt.id as StyleGender }))}
                    >
                      {opt.label}
                    </Chip>
                  ))}
                </div>
              </div>
              {form.gender === 'custom' && (
                <input
                  className="input"
                  placeholder="Describe your gender / style identity"
                  value={form.custom_gender ?? ''}
                  onChange={e => setForm(f => ({ ...f, custom_gender: e.target.value }))}
                />
              )}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Height value</label>
                  <input
                    type="number"
                    className="input"
                    value={form.height_value ?? ''}
                    onChange={e =>
                      setForm(f => ({
                        ...f,
                        height_value: e.target.value === '' ? null : parseFloat(e.target.value),
                      }))
                    }
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Unit</label>
                  <select
                    className="input"
                    value={form.height_unit ?? 'cm'}
                    onChange={e =>
                      setForm(f => ({ ...f, height_unit: e.target.value as UserStyleProfile['height_unit'] }))
                    }
                  >
                    <option value="cm">Centimeters</option>
                    <option value="ft_in">Feet / inches</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Weight value</label>
                  <input
                    type="number"
                    className="input"
                    value={form.weight_value ?? ''}
                    onChange={e =>
                      setForm(f => ({
                        ...f,
                        weight_value: e.target.value === '' ? null : parseFloat(e.target.value),
                      }))
                    }
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-slate-500">Unit</label>
                  <select
                    className="input"
                    value={form.weight_unit ?? 'lb'}
                    onChange={e =>
                      setForm(f => ({ ...f, weight_unit: e.target.value as UserStyleProfile['weight_unit'] }))
                    }
                  >
                    <option value="lb">Pounds</option>
                    <option value="kg">Kilograms</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-500">Age range (optional)</label>
                <select
                  className="input"
                  value={form.age_range ?? ''}
                  onChange={e => setForm(f => ({ ...f, age_range: e.target.value || null }))}
                >
                  <option value="">—</option>
                  {AGE_RANGES.map(a => (
                    <option key={a.id} value={a.id}>
                      {a.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          )}

          {step === 'body' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Body type</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Optional — select any that apply. You can customize these anytime.</p>
              <div className="flex flex-wrap gap-2">
                {dynamic.bodyTypes.map(b => (
                  <Chip
                    key={b}
                    active={form.body_types?.includes(b) ?? false}
                    onClick={() => toggleMulti('body_types', b)}
                  >
                    {b}
                  </Chip>
                ))}
              </div>
              <input
                className="input"
                placeholder="Custom body type (optional)"
                value={form.custom_body_type ?? ''}
                onChange={e => setForm(f => ({ ...f, custom_body_type: e.target.value || null }))}
              />
            </div>
          )}

          {step === 'fit' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Fit preferences</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">Optional — pick as many as you like.</p>
              <div className="flex flex-wrap gap-2">
                {dynamic.fitPreferences.map(b => (
                  <Chip
                    key={b}
                    active={form.fit_preferences?.includes(b) ?? false}
                    onClick={() => toggleMulti('fit_preferences', b)}
                  >
                    {b}
                  </Chip>
                ))}
              </div>
              <textarea
                className="input min-h-20"
                placeholder="Custom fit notes (optional)"
                value={form.custom_fit_notes ?? ''}
                onChange={e => setForm(f => ({ ...f, custom_fit_notes: e.target.value || null }))}
              />
            </div>
          )}

          {step === 'sizes' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Size details</h2>
              <p className="text-xs text-slate-500 dark:text-slate-400">US sizing by default — all optional.</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {dynamic.sizeFields.map(sf => (
                  <div key={sf.key}>
                    <label className="mb-1 block text-xs font-medium text-slate-500">
                      {sf.label}
                      {sf.optional ? ' (optional)' : ''}
                    </label>
                    <input
                      className="input"
                      placeholder={sf.placeholder}
                      value={form.size_profile?.[sf.key] ?? ''}
                      onChange={e =>
                        setForm(f => ({
                          ...f,
                          size_profile: { ...f.size_profile, [sf.key]: e.target.value },
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
              <textarea
                className="input min-h-20"
                placeholder="Custom size notes (optional)"
                value={form.custom_size_notes ?? ''}
                onChange={e => setForm(f => ({ ...f, custom_size_notes: e.target.value || null }))}
              />
            </div>
          )}

          {step === 'style' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Style preferences</h2>
              <div className="flex flex-wrap gap-2">
                {STYLE_TAGS.map(b => (
                  <Chip
                    key={b}
                    active={form.style_preferences?.includes(b) ?? false}
                    onClick={() => toggleMulti('style_preferences', b)}
                  >
                    {b}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          {step === 'colors' && (
            <div className="space-y-4">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Color preferences</h2>
              <div className="flex gap-2">
                <input
                  className="input"
                  placeholder="Add a favourite colour"
                  value={colorIn.fav}
                  onChange={e => setColorIn(c => ({ ...c, fav: e.target.value }))}
                />
                <button
                  type="button"
                  className="btn-secondary shrink-0"
                  onClick={() => {
                    const v = colorIn.fav.trim()
                    if (!v) return
                    setForm(f => ({ ...f, favorite_colors: [...(f.favorite_colors ?? []), v] }))
                    setColorIn(c => ({ ...c, fav: '' }))
                  }}
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {(form.favorite_colors ?? []).map(c => (
                  <button
                    key={c}
                    type="button"
                    className="rounded-full bg-emerald-100 px-3 py-1 text-xs dark:bg-emerald-500/20"
                    onClick={() =>
                      setForm(f => ({
                        ...f,
                        favorite_colors: (f.favorite_colors ?? []).filter(x => x !== c),
                      }))
                    }
                  >
                    {c} ✕
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                <input
                  className="input"
                  placeholder="Colour to avoid"
                  value={colorIn.avoid}
                  onChange={e => setColorIn(c => ({ ...c, avoid: e.target.value }))}
                />
                <button
                  type="button"
                  className="btn-secondary shrink-0"
                  onClick={() => {
                    const v = colorIn.avoid.trim()
                    if (!v) return
                    setForm(f => ({ ...f, avoided_colors: [...(f.avoided_colors ?? []), v] }))
                    setColorIn(c => ({ ...c, avoid: '' }))
                  }}
                >
                  Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {(form.avoided_colors ?? []).map(c => (
                  <button
                    key={c}
                    type="button"
                    className="rounded-full bg-rose-100 px-3 py-1 text-xs dark:bg-rose-500/20"
                    onClick={() =>
                      setForm(f => ({
                        ...f,
                        avoided_colors: (f.avoided_colors ?? []).filter(x => x !== c),
                      }))
                    }
                  >
                    {c} ✕
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(form.neutral_color_preference)}
                    onChange={e => setForm(f => ({ ...f, neutral_color_preference: e.target.checked }))}
                  />
                  Prefer neutrals
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={Boolean(form.bold_color_preference)}
                    onChange={e => setForm(f => ({ ...f, bold_color_preference: e.target.checked }))}
                  />
                  Like bold colours
                </label>
              </div>
            </div>
          )}

          {step === 'occasions' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Occasions</h2>
              <div className="flex flex-wrap gap-2">
                {OCCASION_PREFS.map(b => (
                  <Chip
                    key={b}
                    active={form.occasion_preferences?.includes(b) ?? false}
                    onClick={() => toggleMulti('occasion_preferences', b)}
                  >
                    {b}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          {step === 'climate' && (
            <div className="space-y-3">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Climate & comfort</h2>
              <div className="flex flex-wrap gap-2">
                {CLIMATE_PREFS.map(b => (
                  <Chip
                    key={b}
                    active={form.climate_preferences?.includes(b) ?? false}
                    onClick={() => toggleMulti('climate_preferences', b)}
                  >
                    {b}
                  </Chip>
                ))}
              </div>
            </div>
          )}

          {step === 'review' && (
            <div className="space-y-3 text-sm text-slate-600 dark:text-slate-300">
              <h2 className="font-display text-lg font-bold text-slate-900 dark:text-white">Review your profile</h2>
              <ul className="space-y-2.5 divide-y divide-slate-100 dark:divide-slate-800">
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Identity: </span>
                  {(form.gender === 'custom' ? form.custom_gender : form.gender) || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Age range: </span>
                  {form.age_range || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Height: </span>
                  {form.height_value ? `${form.height_value} ${form.height_unit ?? ''}` : '—'}
                  {'  ·  '}
                  <span className="font-semibold text-slate-800 dark:text-white">Weight: </span>
                  {form.weight_value ? `${form.weight_value} ${form.weight_unit ?? ''}` : '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Body types: </span>
                  {(form.body_types ?? []).join(', ') || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Fit preferences: </span>
                  {(form.fit_preferences ?? []).join(', ') || '—'}
                </li>
                {form.size_profile && Object.keys(form.size_profile).length > 0 && (
                  <li className="pt-2">
                    <span className="font-semibold text-slate-800 dark:text-white">Sizes: </span>
                    {Object.entries(form.size_profile)
                      .filter(([, v]) => v)
                      .map(([k, v]) => `${k}: ${v}`)
                      .join(' · ') || '—'}
                  </li>
                )}
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Styles: </span>
                  {(form.style_preferences ?? []).join(', ') || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Favourite colours: </span>
                  {(form.favorite_colors ?? []).join(', ') || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Colours to avoid: </span>
                  {(form.avoided_colors ?? []).join(', ') || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Occasions: </span>
                  {(form.occasion_preferences ?? []).join(', ') || '—'}
                </li>
                <li className="pt-2">
                  <span className="font-semibold text-slate-800 dark:text-white">Climate: </span>
                  {(form.climate_preferences ?? []).join(', ') || '—'}
                </li>
              </ul>
            </div>
          )}

          {step !== 'welcome' && (
            <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-6 dark:border-slate-800">
              <button
                type="button"
                className="btn-ghost flex items-center gap-1 text-sm"
                onClick={goBack}
                disabled={saving}
              >
                <ArrowLeft size={16} /> Back
              </button>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn-secondary text-sm"
                  disabled={saving}
                  onClick={() => finish(true)}
                >
                  Skip for now
                </button>
                {step !== 'review' ? (
                  <button
                    type="button"
                    className="btn-primary flex items-center gap-1 text-sm"
                    disabled={saving}
                    onClick={goNext}
                  >
                    {saving ? <Loader2 className="animate-spin" size={16} /> : <>Next <ArrowRight size={16} /></>}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="btn-primary flex items-center gap-1 text-sm"
                    disabled={saving}
                    onClick={() => finish(false)}
                  >
                    {saving ? <Loader2 className="animate-spin" size={16} /> : <><Check size={16} /> Save & Continue</>}
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500">
          You can customize these anytime in Profile settings.
        </p>
      </div>
    </div>
  )
}
