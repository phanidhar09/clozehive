import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router-dom'
import {
  Search, Users, UserCheck, Loader2, Edit3, Check, Shirt,
  User as UserIcon, Ruler, Palette, Brain, MapPin, Calendar, Sparkles,
} from 'lucide-react'
import { useApp } from '@/store'
import { socialApi, authApi } from '@/lib/api'
import type {
  AuthUser, AvatarConfig, BodyProfile, ClosetItem, SocialUser,
  StyleProfile, StyleTag, UserPermissions, UserPreferences,
} from '@/types'
import UserCard from '@/components/ui/UserCard'
import GlassCard from '@/components/ui/GlassCard'
import AvatarEditor, { withAvatarDefaults } from '@/components/profile/AvatarEditor'
import { analyzeCloset } from '@/lib/closetInsights'
import { requestGeolocation } from '@/hooks/useWeather'
import { cn } from '@/lib/utils'
import { hideNonMvpUi } from '@/config/features'

type Tab = 'overview' | 'avatar' | 'body' | 'style' | 'insights' | 'social' | 'settings'

const STYLE_TAGS: { value: StyleTag; label: string; emoji: string }[] = [
  { value: 'casual',     label: 'Casual',      emoji: '👕' },
  { value: 'formal',     label: 'Formal',      emoji: '🎩' },
  { value: 'streetwear', label: 'Streetwear',  emoji: '🧢' },
  { value: 'sporty',     label: 'Sporty',      emoji: '🏃' },
  { value: 'minimal',    label: 'Minimal',     emoji: '⬜' },
  { value: 'business',   label: 'Business',    emoji: '💼' },
  { value: 'boho',       label: 'Boho',        emoji: '🌸' },
  { value: 'vintage',    label: 'Vintage',     emoji: '📻' },
  { value: 'preppy',     label: 'Preppy',      emoji: '⛵' },
  { value: 'elegant',    label: 'Elegant',     emoji: '🥂' },
]

const BODY_TYPES: BodyProfile['body_type'][] = ['slim', 'athletic', 'average', 'broad', 'curvy', 'plus']
const FITS: BodyProfile['preferred_fit'][] = ['slim', 'regular', 'oversized']

// ─────────────────────────────────────────────────────────────────────────────

export default function Profile() {
  const { currentUser, updateCurrentUser, closetItems } = useApp()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const raw = (searchParams.get('tab') as Tab) || 'overview'
    if (hideNonMvpUi() && (raw === 'avatar' || raw === 'social')) return 'overview'
    return raw
  })

  const [profile, setProfile] = useState<SocialUser | null>(null)
  const [profileLoading, setProfileLoading] = useState(true)

  useEffect(() => {
    if (!currentUser) return
    setProfileLoading(true)
    socialApi.getProfile(currentUser.id)
      .then(setProfile)
      .catch(console.error)
      .finally(() => setProfileLoading(false))
  }, [currentUser])

  const profileDisplayLabel = currentUser?.display_name || currentUser?.username || ''
  const initials = useMemo(() => {
    return profileDisplayLabel
      ? profileDisplayLabel.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
      : 'U'
  }, [profileDisplayLabel])

  const insight = useMemo(() => analyzeCloset(closetItems), [closetItems])

  const TABS = useMemo(() => {
    const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
      { id: 'overview', label: 'Overview',    icon: <UserIcon size={14} /> },
      { id: 'avatar',   label: 'Avatar',      icon: <Sparkles size={14} /> },
      { id: 'body',     label: 'Body & Size', icon: <Ruler size={14} /> },
      { id: 'style',    label: 'Style',       icon: <Palette size={14} /> },
      { id: 'insights', label: 'Insights',    icon: <Brain size={14} /> },
      { id: 'social',   label: 'Social',      icon: <Users size={14} /> },
      { id: 'settings', label: 'Settings',    icon: <Edit3 size={14} /> },
    ]
    return hideNonMvpUi() ? tabs.filter(t => t.id !== 'social' && t.id !== 'avatar') : tabs
  }, [])

  if (!currentUser) {
    return <div className="p-8 text-slate-400">Sign in to view your profile.</div>
  }

  return (
    <div className="max-w-5xl space-y-6">

      {searchParams.get('onboarding') === '1' && (
        <div className="rounded-2xl border border-indigo-200 dark:border-indigo-500/35 bg-indigo-50/90 dark:bg-indigo-950/35 p-4 text-sm text-slate-700 dark:text-slate-200">
          <p className="font-semibold mb-2">Welcome — finish your setup</p>
          <ol className="list-decimal list-inside space-y-1 text-slate-600 dark:text-slate-300">
            <li>Add your body profile and style preferences using the tabs below.</li>
            <li><Link className="text-brand-600 dark:text-brand-400 font-medium" to="/upload">Upload wardrobe photos</Link>.</li>
            <li>Open your <Link className="text-brand-600 dark:text-brand-400 font-medium" to="/dashboard">dashboard</Link> when you are ready.</li>
          </ol>
          <button
            type="button"
            className="mt-3 text-xs text-slate-500 dark:text-slate-400 underline"
            onClick={() => navigate('/profile', { replace: true })}
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Header card ──────────────────────────────────────── */}
      <GlassCard padding="none" className="overflow-hidden">
        <div className="h-28 bg-gradient-to-r from-indigo-600 via-violet-600 to-fuchsia-500 relative">
          <div className="absolute inset-0 opacity-[0.07]"
               style={{ backgroundImage: 'radial-gradient(rgba(255,255,255,0.6) 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
        </div>

        <div className="px-5 pb-5">
          <div className="-mt-10 mb-3 flex items-end justify-between">
            <div className="w-20 h-20 rounded-full ring-4 ring-white dark:ring-slate-950
                            bg-gradient-to-br from-indigo-500 to-violet-600
                            flex items-center justify-center text-2xl font-bold text-white
                            shadow-glow-md overflow-hidden">
              {currentUser.avatar_url
                ? <img src={currentUser.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
                : initials}
            </div>
            <button
              onClick={() => setActiveTab('settings')}
              className="btn-ghost text-xs gap-1.5"
            >
              <Edit3 size={13} /> Edit profile
            </button>
          </div>

          <div className="space-y-0.5 mb-3">
            <h2 className="font-display font-bold text-xl text-slate-900 dark:text-white">
              {currentUser.display_name || currentUser.username}
            </h2>
            <p className="text-sm text-slate-400 dark:text-white/50">@{currentUser.username}</p>
            <p className="text-sm text-slate-500 dark:text-white/60 mt-1">
              {currentUser.bio || <span className="italic">No bio yet</span>}
            </p>
          </div>

          {profileLoading ? (
            <div className="h-12 bg-cream-100 dark:bg-white/[0.04] rounded-xl animate-pulse" />
          ) : (
            <div className="flex gap-6">
              {[
                { label: 'Items',     value: profile?.item_count ?? 0,      tab: 'overview' as Tab },
                ...(hideNonMvpUi()
                  ? []
                  : [
                      { label: 'Followers', value: profile?.follower_count ?? 0, tab: 'social' as Tab },
                      { label: 'Following', value: profile?.following_count ?? 0, tab: 'social' as Tab },
                    ]),
              ].map(s => (
                <button key={s.label} onClick={() => setActiveTab(s.tab)} className="text-center hover:opacity-80">
                  <div className="font-bold text-lg text-slate-900 dark:text-white">{s.value}</div>
                  <div className="text-xs text-slate-400 dark:text-white/40">{s.label}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </GlassCard>

      {/* ── Tabs ─────────────────────────────────────────────── */}
      <div className="flex gap-1 bg-cream-100 dark:bg-white/[0.04] p-1 rounded-xl overflow-x-auto">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setActiveTab(t.id)}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-all whitespace-nowrap flex-shrink-0',
              activeTab === t.id
                ? 'bg-white dark:bg-white/[0.10] text-slate-800 dark:text-white shadow-sm'
                : 'text-slate-500 dark:text-white/50 hover:text-slate-700 dark:hover:text-white/80',
            )}
          >
            {t.icon}{t.label}
          </button>
        ))}
      </div>

      {/* ── Tab content ──────────────────────────────────────── */}

      {activeTab === 'overview' && (
        <OverviewTab profile={profile} closetItems={closetItems} insight={insight} onJump={setActiveTab} currentUser={currentUser} />
      )}

      {activeTab === 'avatar' && (
        <AvatarTab
          config={currentUser.avatar_config}
          onSave={async cfg => {
            const u = await authApi.updateProfile({ avatar_config: cfg })
            updateCurrentUser({ avatar_config: u.avatar_config })
          }}
        />
      )}

      {activeTab === 'body' && (
        <BodyTab
          value={currentUser.body_profile ?? null}
          onSave={async patch => {
            const merged: BodyProfile = { ...(currentUser.body_profile ?? {}), ...patch }
            const u = await authApi.updateProfile({ body_profile: merged })
            updateCurrentUser({ body_profile: u.body_profile })
          }}
        />
      )}

      {activeTab === 'style' && (
        <StyleTab
          value={currentUser.style_profile ?? null}
          insight={insight}
          onSave={async patch => {
            const merged: StyleProfile = {
              selected_styles: [],
              favorite_colors: [],
              avoid_colors: [],
              ...(currentUser.style_profile ?? {}),
              ...patch,
            }
            const u = await authApi.updateProfile({ style_profile: merged })
            updateCurrentUser({ style_profile: u.style_profile })
          }}
        />
      )}

      {activeTab === 'insights' && (
        <InsightsTab insight={insight} closetItems={closetItems} />
      )}

      {activeTab === 'social' && (
        <SocialTab currentUserId={currentUser.id} onProfileChange={setProfile} profile={profile} navigate={navigate} />
      )}

      {activeTab === 'settings' && (
        <SettingsTab
          name={currentUser.display_name}
          username={currentUser.username}
          bio={currentUser.bio ?? ''}
          permissions={currentUser.permissions ?? null}
          preferences={currentUser.preferences ?? null}
          onSaveBio={async (display_name, bio) => {
            const updated = await authApi.updateProfile({
              display_name: display_name.trim(),
              bio: bio.trim() || undefined,
            })
            updateCurrentUser({ display_name: updated.display_name, bio: updated.bio })
            setProfile(p => p ? { ...p, display_name: updated.display_name, bio: updated.bio ?? null } : p)
          }}
          onSavePermissions={async perms => {
            const u = await authApi.updateProfile({ permissions: perms })
            updateCurrentUser({ permissions: u.permissions })
          }}
          onSavePreferences={async prefs => {
            const u = await authApi.updateProfile({ preferences: prefs })
            updateCurrentUser({ preferences: u.preferences })
          }}
        />
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Overview
// ─────────────────────────────────────────────────────────────────────────────

function OverviewTab({
  profile, closetItems, insight, onJump, currentUser,
}: {
  profile: SocialUser | null
  closetItems: ClosetItem[]
  insight: ReturnType<typeof analyzeCloset>
  onJump: (t: Tab) => void
  currentUser: AuthUser
}) {
  const dominant = insight.dominantStyle
  const navigate = useNavigate()

  const hasBodyProfile = Boolean(
    currentUser.body_profile?.body_type
    || currentUser.body_profile?.height_cm
    || currentUser.body_profile?.shirt_size
    || currentUser.body_profile?.pant_size
    || currentUser.body_profile?.shoe_size
  )
  const hasStyleProfile = Boolean(
    (currentUser.style_profile?.selected_styles?.length ?? 0) > 0
    || currentUser.onboarding_completed
  )
  const hasLocation = Boolean(currentUser.permissions?.location)

  return (
    <div className="grid md:grid-cols-2 gap-4 animate-fade-in">
      <GlassCard padding="md">
        <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3 flex items-center gap-2">
          <Brain size={14} className="text-indigo-500" /> Personalization status
        </h3>
        <ul className="space-y-2 text-sm">
          <StatusRow label="Avatar"          done={false} cta="Edit" onAction={() => onJump('avatar')} optional />
          <StatusRow label="Body & sizes"    done={hasBodyProfile} cta={hasBodyProfile ? 'Edit' : 'Add'} onAction={() => onJump('body')} />
          <StatusRow label="Style Profile (AI)" done={hasStyleProfile} cta="Edit" onAction={() => navigate('/onboarding/style-profile')} />
          <StatusRow label="Location access" done={hasLocation} cta={hasLocation ? 'Change' : 'Enable'} onAction={() => onJump('settings')} optional />
        </ul>
      </GlassCard>

      <GlassCard padding="md">
        <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3 flex items-center gap-2">
          <Sparkles size={14} className="text-violet-500" /> Wardrobe pulse
        </h3>
        {insight.totalItems === 0 ? (
          <p className="text-sm text-slate-400 dark:text-white/40">
            Add items to unlock style intelligence.
          </p>
        ) : (
          <div className="space-y-2 text-sm">
            <Stat label="Items"      value={insight.totalItems} />
            <Stat label="Categories" value={insight.topCategories.length} />
            <Stat label="Top color"  value={insight.topColors[0]?.color ?? '—'} />
            <Stat label="Vibe"       value={dominant ? `${dominant}${insight.confident ? '' : ' (early)'}` : '—'} />
          </div>
        )}
      </GlassCard>

      <GlassCard padding="md" className="md:col-span-2">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 flex items-center gap-2">
            <Shirt size={14} className="text-emerald-500" /> Closet preview
          </h3>
          <button onClick={() => navigate('/closet')} className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
            View all{profile?.item_count ? ` (${profile.item_count})` : ''}
          </button>
        </div>
        {closetItems.length === 0 ? (
          <div className="text-center py-6 text-slate-400 dark:text-white/40 text-sm">
            No items yet — <button className="underline" onClick={() => navigate('/upload')}>upload your first piece</button>.
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-2">
            {closetItems.slice(0, 6).map(item => (
              <button key={item.id} onClick={() => navigate('/closet')} className="aspect-square rounded-xl overflow-hidden bg-cream-100 dark:bg-white/[0.04] border border-cream-200 dark:border-white/[0.06]">
                {item.image_url
                  ? <img src={item.image_url} alt={item.name} className="w-full h-full object-cover hover:scale-105 transition-transform" />
                  : <div className="w-full h-full flex items-center justify-center text-2xl">👕</div>}
              </button>
            ))}
          </div>
        )}
      </GlassCard>
    </div>
  )
}

function StatusRow({
  label, done, cta, onAction, optional,
}: { label: string; done: boolean; cta: string; onAction: () => void; optional?: boolean }) {
  return (
    <li className="flex items-center justify-between">
      <span className={cn('flex items-center gap-2', done && 'text-slate-400 line-through')}>
        <span className={cn('w-1.5 h-1.5 rounded-full', done ? 'bg-emerald-500' : 'bg-amber-500')} />
        {label} {optional && <span className="text-[10px] text-slate-400">optional</span>}
      </span>
      <button onClick={onAction} className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline">
        {cta}
      </button>
    </li>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-slate-500 dark:text-white/50">{label}</span>
      <span className="font-semibold text-slate-800 dark:text-white capitalize">{String(value)}</span>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Avatar tab
// ─────────────────────────────────────────────────────────────────────────────

function AvatarTab({
  config, onSave,
}: { config: AvatarConfig | null | undefined; onSave: (cfg: AvatarConfig) => Promise<void> }) {
  const [draft, setDraft] = useState<AvatarConfig>(() => withAvatarDefaults(config))
  const [saving, setSaving] = useState(false)

  useEffect(() => { setDraft(withAvatarDefaults(config)) }, [config])

  const save = async () => {
    setSaving(true)
    try { await onSave(draft) } finally { setSaving(false) }
  }

  return (
    <GlassCard padding="md" className="animate-fade-in">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-base text-slate-800 dark:text-white">Your avatar</h3>
        <button onClick={save} disabled={saving} className="btn-primary text-xs gap-1.5">
          {saving ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />}
          {saving ? 'Saving…' : 'Save avatar'}
        </button>
      </div>
      <AvatarEditor config={draft} onChange={setDraft} />
    </GlassCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Body & Size tab
// ─────────────────────────────────────────────────────────────────────────────

function BodyTab({
  value, onSave,
}: { value: BodyProfile | null; onSave: (patch: BodyProfile) => Promise<void> }) {
  const [draft, setDraft] = useState<BodyProfile>(() => value ?? {})
  const [saving, setSaving] = useState(false)

  useEffect(() => setDraft(value ?? {}), [value])

  const set = <K extends keyof BodyProfile>(k: K, v: BodyProfile[K]) =>
    setDraft(d => ({ ...d, [k]: v }))

  const save = async () => {
    setSaving(true)
    try { await onSave(draft) } finally { setSaving(false) }
  }

  return (
    <GlassCard padding="md" className="space-y-5 animate-fade-in">
      <div>
        <h3 className="font-semibold text-base text-slate-800 dark:text-white">Body & sizes</h3>
        <p className="text-xs text-slate-500 dark:text-white/50 mt-1">
          The AI uses this to match items that genuinely fit you. Skip anything you don&apos;t want to share.
        </p>
      </div>

      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Height (cm)">
          <input type="number" className="input w-full" value={draft.height_cm ?? ''} min={80} max={260}
                 onChange={e => set('height_cm', e.target.value ? Number(e.target.value) : null)} />
        </Field>
        <Field label="Weight (kg) — optional">
          <input type="number" className="input w-full" value={draft.weight_kg ?? ''} min={25} max={300}
                 onChange={e => set('weight_kg', e.target.value ? Number(e.target.value) : null)} />
        </Field>
      </div>

      <Field label="Body type">
        <PillRow
          options={BODY_TYPES.map(b => ({ value: b!, label: b! }))}
          value={draft.body_type ?? null}
          onChange={v => set('body_type', v as BodyProfile['body_type'])}
        />
      </Field>

      <Field label="Preferred fit">
        <PillRow
          options={FITS.map(f => ({ value: f!, label: f! }))}
          value={draft.preferred_fit ?? null}
          onChange={v => set('preferred_fit', v as BodyProfile['preferred_fit'])}
        />
      </Field>

      <div className="grid sm:grid-cols-3 gap-4">
        <Field label="Shirt size">
          <input type="text" className="input w-full" placeholder="e.g. M / 40"
                 value={draft.shirt_size ?? ''} onChange={e => set('shirt_size', e.target.value)} />
        </Field>
        <Field label="Pant size">
          <input type="text" className="input w-full" placeholder="e.g. 32x32"
                 value={draft.pant_size ?? ''} onChange={e => set('pant_size', e.target.value)} />
        </Field>
        <Field label="Shoe size">
          <input type="text" className="input w-full" placeholder="e.g. US 10"
                 value={draft.shoe_size ?? ''} onChange={e => set('shoe_size', e.target.value)} />
        </Field>
      </div>

      <button onClick={save} disabled={saving} className="btn-primary text-sm gap-2">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
        {saving ? 'Saving…' : 'Save body profile'}
      </button>
    </GlassCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Style tab
// ─────────────────────────────────────────────────────────────────────────────

function StyleTab({
  value, insight, onSave,
}: {
  value: StyleProfile | null
  insight: ReturnType<typeof analyzeCloset>
  onSave: (patch: Partial<StyleProfile>) => Promise<void>
}) {
  const [selected, setSelected] = useState<StyleTag[]>(value?.selected_styles ?? [])
  const [favoriteColors, setFavoriteColors] = useState<string>(((value?.favorite_colors ?? []).join(', ')))
  const [avoidColors, setAvoidColors] = useState<string>(((value?.avoid_colors ?? []).join(', ')))
  const [saving, setSaving] = useState(false)

  const toggle = (t: StyleTag) =>
    setSelected(arr => arr.includes(t) ? arr.filter(x => x !== t) : [...arr, t].slice(0, 8))

  const save = async () => {
    setSaving(true)
    try {
      await onSave({
        selected_styles: selected,
        favorite_colors: favoriteColors.split(',').map(c => c.trim()).filter(Boolean),
        avoid_colors:    avoidColors.split(',').map(c => c.trim()).filter(Boolean),
      })
    } finally { setSaving(false) }
  }

  const adoptLearned = async () => {
    if (!insight.dominantStyle) return
    setSaving(true)
    try {
      await onSave({
        learned_style: insight.dominantStyle,
        learned_at: new Date().toISOString(),
      })
    } finally { setSaving(false) }
  }

  return (
    <GlassCard padding="md" className="space-y-5 animate-fade-in">
      <div>
        <h3 className="font-semibold text-base text-slate-800 dark:text-white">Style preferences</h3>
        <p className="text-xs text-slate-500 dark:text-white/50 mt-1">
          Pick the looks you wear most. After ~10 closet items the AI also learns from your wardrobe.
        </p>
      </div>

      <Field label="Preferred styles (pick up to 8)">
        <div className="flex flex-wrap gap-2">
          {STYLE_TAGS.map(t => (
            <button
              key={t.value}
              onClick={() => toggle(t.value)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
                selected.includes(t.value)
                  ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-glow-sm'
                  : 'bg-cream-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/70 hover:bg-cream-200 dark:hover:bg-white/[0.10]',
              )}
            >
              {t.emoji} {t.label}
            </button>
          ))}
        </div>
      </Field>

      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="Favorite colors">
          <input className="input w-full" placeholder="navy, cream, olive"
                 value={favoriteColors} onChange={e => setFavoriteColors(e.target.value)} />
        </Field>
        <Field label="Avoid colors">
          <input className="input w-full" placeholder="neon, pastel pink"
                 value={avoidColors} onChange={e => setAvoidColors(e.target.value)} />
        </Field>
      </div>

      {/* Behavioural learning panel */}
      {insight.totalItems > 0 && (
        <div className="rounded-xl p-3 bg-indigo-50/60 dark:bg-indigo-500/[0.08] border border-indigo-200/60 dark:border-indigo-500/20">
          <p className="text-xs font-semibold text-indigo-700 dark:text-indigo-300 mb-1">Closet-derived style</p>
          <p className="text-sm text-slate-700 dark:text-white/80">
            Based on {insight.totalItems} item{insight.totalItems === 1 ? '' : 's'},
            your wardrobe leans <strong className="capitalize">{insight.dominantStyle ?? '—'}</strong>
            {!insight.confident && <span className="text-xs text-slate-500 dark:text-white/50"> (low confidence — add more items)</span>}.
          </p>
          {insight.dominantStyle && (
            <button onClick={adoptLearned} disabled={saving}
                    className="mt-2 text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline disabled:opacity-40">
              Use this as my learned style →
            </button>
          )}
          {value?.learned_style && (
            <p className="text-[11px] text-slate-500 dark:text-white/40 mt-1">
              Currently saved: <span className="capitalize">{value.learned_style}</span>
            </p>
          )}
        </div>
      )}

      <button onClick={save} disabled={saving} className="btn-primary text-sm gap-2">
        {saving ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
        {saving ? 'Saving…' : 'Save style preferences'}
      </button>
    </GlassCard>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Insights tab
// ─────────────────────────────────────────────────────────────────────────────

function InsightsTab({
  insight, closetItems,
}: { insight: ReturnType<typeof analyzeCloset>; closetItems: ClosetItem[] }) {
  if (closetItems.length === 0) {
    return (
      <GlassCard padding="lg" className="text-center text-slate-500 dark:text-white/50 animate-fade-in">
        <Brain size={32} className="mx-auto mb-3 opacity-30" />
        <p className="font-semibold">Add items to unlock closet insights.</p>
        <p className="text-sm mt-1">We analyze your wardrobe entirely on-device.</p>
      </GlassCard>
    )
  }

  const ranked = (Object.entries(insight.scores) as [string, number][]).sort((a, b) => b[1] - a[1])
  const max = Math.max(1, ...ranked.map(([, v]) => v))

  const missing = detectMissingEssentials(closetItems)

  return (
    <div className="space-y-4 animate-fade-in">
      <GlassCard padding="md">
        <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3 flex items-center gap-2">
          <Brain size={14} className="text-indigo-500" /> Style breakdown
        </h3>
        {!insight.confident && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mb-2">
            Confidence improves once you have 10+ items (currently {insight.totalItems}).
          </p>
        )}
        <div className="space-y-1.5">
          {ranked.length === 0 && <p className="text-sm text-slate-400">No matches yet.</p>}
          {ranked.map(([style, score]) => (
            <div key={style} className="space-y-0.5">
              <div className="flex justify-between text-xs">
                <span className="capitalize text-slate-700 dark:text-white/80">{style}</span>
                <span className="text-slate-400 dark:text-white/40">{score}</span>
              </div>
              <div className="h-1.5 rounded-full bg-cream-200 dark:bg-white/[0.06] overflow-hidden">
                <div className="h-full bg-gradient-to-r from-indigo-500 to-violet-500" style={{ width: `${(score / max) * 100}%` }} />
              </div>
            </div>
          ))}
        </div>
      </GlassCard>

      <div className="grid md:grid-cols-2 gap-4">
        <GlassCard padding="md">
          <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3">Top colors</h3>
          {insight.topColors.length === 0 ? (
            <p className="text-sm text-slate-400">No color data.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {insight.topColors.map(c => (
                <li key={c.color} className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full border border-cream-300 dark:border-white/[0.08]" style={{ backgroundColor: c.color }} />
                  <span className="capitalize flex-1 text-slate-700 dark:text-white/80">{c.color}</span>
                  <span className="text-xs text-slate-400">{c.count}</span>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>

        <GlassCard padding="md">
          <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-3">Top categories</h3>
          {insight.topCategories.length === 0 ? (
            <p className="text-sm text-slate-400">No category data.</p>
          ) : (
            <ul className="space-y-1.5 text-sm">
              {insight.topCategories.map(c => (
                <li key={c.category} className="flex items-center justify-between">
                  <span className="capitalize text-slate-700 dark:text-white/80">{c.category}</span>
                  <span className="text-xs text-slate-400">{c.count}</span>
                </li>
              ))}
            </ul>
          )}
        </GlassCard>
      </div>

      {missing.length > 0 && (
        <GlassCard padding="md">
          <h3 className="font-semibold text-sm text-slate-700 dark:text-white/80 mb-2 flex items-center gap-2">
            <Sparkles size={14} className="text-amber-500" /> Missing essentials
          </h3>
          <p className="text-xs text-slate-500 dark:text-white/50 mb-3">
            Adding these would unlock more outfit combinations.
          </p>
          <div className="flex flex-wrap gap-2">
            {missing.map(m => (
              <span key={m} className="px-2.5 py-1 rounded-lg text-xs bg-amber-100/70 dark:bg-amber-500/[0.12] text-amber-700 dark:text-amber-300 capitalize">
                {m}
              </span>
            ))}
          </div>
        </GlassCard>
      )}
    </div>
  )
}

function detectMissingEssentials(items: ClosetItem[]): string[] {
  const have = new Set(items.map(i => i.category.toLowerCase()))
  const essentials = ['tops', 'bottoms', 'shoes', 'outerwear']
  return essentials.filter(e => !have.has(e))
}

// ─────────────────────────────────────────────────────────────────────────────
// Social tab (followers / following / discover)
// ─────────────────────────────────────────────────────────────────────────────

function SocialTab({
  currentUserId, profile, onProfileChange, navigate,
}: {
  currentUserId: string
  profile: SocialUser | null
  onProfileChange: (p: SocialUser | null | ((p: SocialUser | null) => SocialUser | null)) => void
  navigate: ReturnType<typeof useNavigate>
}) {
  type SubTab = 'followers' | 'following' | 'discover'
  const [sub, setSub] = useState<SubTab>('followers')
  const [followers, setFollowers] = useState<SocialUser[]>([])
  const [following, setFollowing] = useState<SocialUser[]>([])
  const [discover, setDiscover] = useState<SocialUser[]>([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<SocialUser[]>([])
  const [searchLoading, setSearchLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      if (sub === 'followers') setFollowers(await socialApi.getFollowers(currentUserId))
      else if (sub === 'following') setFollowing(await socialApi.getFollowing(currentUserId))
      else setDiscover(await socialApi.searchUsers())
    } catch { /* ignore */ }
    finally { setLoading(false) }
  }, [sub, currentUserId])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!searchQuery.trim()) { setSearchResults([]); return }
    const t = setTimeout(async () => {
      setSearchLoading(true)
      try { setSearchResults(await socialApi.searchUsers(searchQuery)) } catch {
        /* debounced search: ignore transient errors */
      }
      finally { setSearchLoading(false) }
    }, 400)
    return () => clearTimeout(t)
  }, [searchQuery])

  const list =
    sub === 'followers' ? followers
    : sub === 'following' ? following
    : (searchQuery ? searchResults : discover)
  const listLoading = loading || (sub === 'discover' && searchLoading)

  return (
    <div className="space-y-3 animate-fade-in">
      <div className="flex gap-1 bg-cream-50 dark:bg-white/[0.04] p-1 rounded-xl w-fit">
        {(['followers', 'following', 'discover'] as SubTab[]).map(s => (
          <button key={s} onClick={() => setSub(s)}
                  className={cn('px-3 py-1 rounded-lg text-xs font-semibold capitalize transition-all',
                    sub === s ? 'bg-white dark:bg-white/[0.10] text-slate-800 dark:text-white shadow-sm'
                              : 'text-slate-500 dark:text-white/50 hover:text-slate-700 dark:hover:text-white/80')}>
            {s}
            {s === 'followers' && profile?.follower_count !== undefined && ` (${profile.follower_count})`}
            {s === 'following' && profile?.following_count !== undefined && ` (${profile.following_count})`}
          </button>
        ))}
      </div>

      {sub === 'discover' && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input className="input w-full pl-9" placeholder="Search by name or username…"
                 value={searchQuery} onChange={e => setSearchQuery(e.target.value)} />
        </div>
      )}

      {listLoading ? (
        <GlassCard padding="md" className="py-8 text-center text-slate-400 dark:text-white/40 text-sm">
          <Loader2 size={16} className="animate-spin inline mr-2" /> Loading…
        </GlassCard>
      ) : list.length === 0 ? (
        <GlassCard padding="lg" className="text-center text-slate-400 dark:text-white/40">
          <Users size={28} className="mx-auto mb-2 opacity-30" />
          <p className="text-sm">
            {sub === 'discover' && searchQuery ? 'No users found'
              : sub === 'followers' ? 'No followers yet'
              : sub === 'following' ? 'Not following anyone yet'
              : 'No users to discover'}
          </p>
        </GlassCard>
      ) : (
        <GlassCard padding="none" className="divide-y divide-cream-200 dark:divide-white/[0.06]">
          {list.map(u => (
            <UserCard
              key={u.id} user={u} compact
              onClick={() => navigate(`/profile?uid=${u.id}`)}
              onFollowChange={(uid, isFollowing, count) => {
                const upd = (l: SocialUser[]) => l.map(x => x.id === uid ? { ...x, is_following: isFollowing, follower_count: count } : x)
                setFollowers(upd); setFollowing(upd); setDiscover(upd); setSearchResults(upd)
                onProfileChange(p => p ? { ...p, following_count: p.following_count + (isFollowing ? 1 : -1) } : p)
              }}
            />
          ))}
        </GlassCard>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings tab
// ─────────────────────────────────────────────────────────────────────────────

function SettingsTab({
  name, username, bio, permissions, preferences,
  onSaveBio, onSavePermissions, onSavePreferences,
}: {
  name: string
  username: string
  bio: string
  permissions: UserPermissions | null
  preferences: UserPreferences | null
  onSaveBio: (name: string, bio: string) => Promise<void>
  onSavePermissions: (p: UserPermissions) => Promise<void>
  onSavePreferences: (p: UserPreferences) => Promise<void>
}) {
  const [editName, setEditName] = useState(name)
  const [editBio, setEditBio] = useState(bio)
  const [savingBio, setSavingBio] = useState(false)

  const [perms, setPerms] = useState<UserPermissions>(() => permissions ?? {
    location: false, calendar: false,
  })
  const [savingPerms, setSavingPerms] = useState(false)

  const [prefs, setPrefs] = useState<UserPreferences>(() => preferences ?? {
    occasion_focus: [], avoid_categories: [], notes: '',
  })
  const [savingPrefs, setSavingPrefs] = useState(false)

  useEffect(() => { if (!savingBio) setEditName(name) }, [name, savingBio])
  useEffect(() => { if (!savingBio) setEditBio(bio) }, [bio, savingBio])
  useEffect(() => setPerms(permissions ?? { location: false, calendar: false }), [permissions])
  useEffect(() => setPrefs(preferences ?? { occasion_focus: [], avoid_categories: [], notes: '' }), [preferences])

  const saveBio = async () => {
    setSavingBio(true)
    try { await onSaveBio(editName, editBio) } finally { setSavingBio(false) }
  }

  const toggleLocation = async () => {
    setSavingPerms(true)
    try {
      if (!perms.location) {
        const got = await requestGeolocation()
        if (!got) {
          await onSavePermissions({ ...perms, location: false })
          alert('Location permission was denied or unavailable.')
          return
        }
        const next: UserPermissions = {
          ...perms,
          location: true,
          location_coords: { lat: got.lat, lon: got.lon },
          location_label: got.label,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        }
        setPerms(next)
        await onSavePermissions(next)
        alert('Location saved. Outfit suggestions will now factor in your local weather.')
      } else {
        const next: UserPermissions = { ...perms, location: false, location_coords: null, location_label: null }
        setPerms(next)
        await onSavePermissions(next)
      }
    } finally { setSavingPerms(false) }
  }

  const toggleCalendar = async () => {
    setSavingPerms(true)
    try {
      // Calendar access in the browser requires OAuth (Google/Apple). We capture
      // the toggle now and treat events as user-supplied notes elsewhere.
      const next: UserPermissions = { ...perms, calendar: !perms.calendar }
      setPerms(next)
      await onSavePermissions(next)
    } finally { setSavingPerms(false) }
  }

  const savePrefs = async () => {
    setSavingPrefs(true)
    try { await onSavePreferences(prefs) } finally { setSavingPrefs(false) }
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Basic */}
      <GlassCard padding="md" className="space-y-4">
        <h3 className="font-semibold text-base text-slate-800 dark:text-white">Edit profile</h3>
        <Field label="Display name">
          <input className="input w-full" value={editName} onChange={e => setEditName(e.target.value)} />
        </Field>
        <Field label="Username">
          <input className="input w-full opacity-50 cursor-not-allowed" value={`@${username}`} disabled />
        </Field>
        <Field label="Bio">
          <textarea className="input w-full resize-none" rows={3} value={editBio} onChange={e => setEditBio(e.target.value)} />
        </Field>
        <button onClick={saveBio} disabled={savingBio || !editName.trim()} className="btn-primary text-sm gap-2">
          {savingBio ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          {savingBio ? 'Saving…' : 'Save changes'}
        </button>
      </GlassCard>

      {/* Permissions */}
      <GlassCard padding="md" className="space-y-3">
        <h3 className="font-semibold text-base text-slate-800 dark:text-white flex items-center gap-2">
          Location & Weather
          {savingPerms && <Loader2 size={14} className="animate-spin text-slate-400" />}
        </h3>
        <Toggle
          icon={<MapPin size={16} className="text-emerald-500" />}
          title="Enable weather-aware outfit suggestions"
          desc="Used to fetch local weather and adjust outfits to current conditions."
          checked={perms.location}
          onChange={toggleLocation}
          extra={perms.location_label ? `Current location: ${perms.location_label}` : undefined}
        />
        <Toggle
          icon={<Calendar size={16} className="text-indigo-500" />}
          title="Calendar"
          desc="Future: read events to plan outfits around meetings & travel."
          checked={perms.calendar}
          onChange={toggleCalendar}
        />
      </GlassCard>

      {/* Preferences */}
      <GlassCard padding="md" className="space-y-4">
        <h3 className="font-semibold text-base text-slate-800 dark:text-white">Preferences</h3>
        <Field label="Occasion focus (comma separated)">
          <input className="input w-full" placeholder="business, weekend, gym"
                 value={prefs.occasion_focus.join(', ')}
                 onChange={e => setPrefs(p => ({ ...p, occasion_focus: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))} />
        </Field>
        <Field label="Avoid categories">
          <input className="input w-full" placeholder="formal, dresses"
                 value={prefs.avoid_categories.join(', ')}
                 onChange={e => setPrefs(p => ({ ...p, avoid_categories: e.target.value.split(',').map(s => s.trim()).filter(Boolean) }))} />
        </Field>
        <Field label="Notes for the AI">
          <textarea className="input w-full resize-none" rows={2} placeholder="I prefer earth tones and avoid logos."
                    value={prefs.notes ?? ''} onChange={e => setPrefs(p => ({ ...p, notes: e.target.value }))} />
        </Field>
        <button onClick={savePrefs} disabled={savingPrefs} className="btn-primary text-sm gap-2">
          {savingPrefs ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
          {savingPrefs ? 'Saving…' : 'Save preferences'}
        </button>
      </GlassCard>
    </div>
  )
}

function Toggle({
  icon, title, desc, checked, onChange, extra,
}: { icon: React.ReactNode; title: string; desc: string; checked: boolean; onChange: () => void; extra?: string }) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-xl bg-cream-50 dark:bg-white/[0.03] border border-cream-200 dark:border-white/[0.06]">
      <div className="mt-0.5">{icon}</div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-slate-800 dark:text-white">{title}</p>
        <p className="text-xs text-slate-500 dark:text-white/50">{desc}</p>
        {extra && <p className="text-[11px] text-slate-400 dark:text-white/40 mt-1">{extra}</p>}
      </div>
      <button
        onClick={onChange}
        role="switch"
        aria-checked={checked}
        className={cn(
          'relative w-10 h-6 rounded-full transition-colors flex-shrink-0',
          checked ? 'bg-gradient-to-r from-indigo-500 to-violet-600' : 'bg-cream-300 dark:bg-white/[0.10]',
        )}
      >
        <span className={cn(
          'absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform',
          checked && 'translate-x-4',
        )} />
      </button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared bits
// ─────────────────────────────────────────────────────────────────────────────

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-semibold text-slate-600 dark:text-white/60">{label}</span>
      {children}
    </label>
  )
}

function PillRow({
  options, value, onChange,
}: { options: { value: string; label: string }[]; value: string | null; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            'px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-all',
            value === o.value
              ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-glow-sm'
              : 'bg-cream-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/70 hover:bg-cream-200 dark:hover:bg-white/[0.10]',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// Suppress unused import warning — UserCheck is reserved for a future "verified" badge in Overview.
void UserCheck
