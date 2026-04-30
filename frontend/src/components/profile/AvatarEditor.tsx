import { cn } from '@/lib/utils'
import type { AvatarConfig } from '@/types'

export const SKIN_TONES = [
  { label: 'Fair',    value: '#FDDBB4' },
  { label: 'Light',   value: '#F0C27F' },
  { label: 'Medium',  value: '#C68642' },
  { label: 'Tan',     value: '#A0522D' },
  { label: 'Brown',   value: '#7B3F00' },
  { label: 'Deep',    value: '#3D1C02' },
] as const

export const HAIR_COLORS = [
  { label: 'Black',   value: '#1a1a1a' },
  { label: 'Brown',   value: '#6B3A2A' },
  { label: 'Blonde',  value: '#D4A017' },
  { label: 'Red',     value: '#8B2500' },
  { label: 'Gray',    value: '#9E9E9E' },
  { label: 'White',   value: '#F5F5F5' },
] as const

export const HAIR_STYLES = ['Short', 'Medium', 'Long', 'Curly', 'Wavy', 'Bun'] as const
export const BODY_TYPES  = ['Slim', 'Athletic', 'Average', 'Curvy', 'Plus'] as const
export const OUTFITS     = ['Casual', 'Business', 'Formal', 'Sport', 'Evening'] as const

export interface FullAvatarConfig {
  skin_tone: string
  hair_color: string
  hair_style: string
  body_type: string
  outfit: string
}

export const AVATAR_DEFAULTS: FullAvatarConfig = {
  skin_tone:  '#FDDBB4',
  hair_color: '#1a1a1a',
  hair_style: 'Medium',
  body_type:  'Athletic',
  outfit:     'Casual',
}

export function withAvatarDefaults(c: AvatarConfig | null | undefined): FullAvatarConfig {
  return {
    skin_tone:  c?.skin_tone  ?? AVATAR_DEFAULTS.skin_tone,
    hair_color: c?.hair_color ?? AVATAR_DEFAULTS.hair_color,
    hair_style: c?.hair_style ?? AVATAR_DEFAULTS.hair_style,
    body_type:  c?.body_type  ?? AVATAR_DEFAULTS.body_type,
    outfit:     c?.outfit     ?? AVATAR_DEFAULTS.outfit,
  }
}

export function AvatarSVG({ config }: { config: FullAvatarConfig }) {
  const { skin_tone, hair_color, hair_style, body_type } = config
  const bodyWidth =
    body_type === 'Plus' ? 70 :
    body_type === 'Curvy' ? 64 :
    body_type === 'Athletic' ? 58 :
    body_type === 'Slim' ? 50 : 56
  const bodyX = (200 - bodyWidth) / 2

  const hairPaths: Record<string, string> = {
    Short:  'M68 72 Q100 48 132 72 Q128 55 100 50 Q72 55 68 72Z',
    Medium: 'M65 75 Q100 45 135 75 Q138 95 135 115 Q100 130 65 115 Q62 95 65 75Z',
    Long:   'M62 75 Q100 42 138 75 Q145 115 138 155 Q100 170 62 155 Q55 115 62 75Z',
    Curly:  'M65 78 Q85 45 100 50 Q115 45 135 78 Q145 75 140 95 Q135 70 120 68 Q100 55 80 68 Q65 70 60 95 Q55 75 65 78Z',
    Wavy:   'M62 80 Q82 48 100 52 Q118 48 138 80 Q142 100 138 130 Q118 148 100 150 Q82 148 62 130 Q58 100 62 80Z',
    Bun:    'M70 75 Q100 52 130 75 Q130 65 100 58 Q70 65 70 75Z M100 48 A12 12 0 1 1 100.1 48Z',
  }

  const outfitColors: Record<string, { top: string; bottom: string }> = {
    Casual:   { top: '#6B8EC4', bottom: '#3B5998' },
    Business: { top: '#FFFFFF', bottom: '#2C3E50' },
    Formal:   { top: '#2C3E50', bottom: '#1A1A2E' },
    Sport:    { top: '#E74C3C', bottom: '#2C3E50' },
    Evening:  { top: '#8E44AD', bottom: '#2C3E50' },
  }
  const colors = outfitColors[config.outfit] ?? outfitColors.Casual

  return (
    <svg viewBox="0 0 200 280" xmlns="http://www.w3.org/2000/svg" className="w-full h-full">
      <defs>
        <radialGradient id="bgGlow" cx="50%" cy="60%" r="50%">
          <stop offset="0%" stopColor="#EEEDFE" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#F5F4F0" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="100" cy="220" rx="70" ry="20" fill="url(#bgGlow)" />
      <ellipse cx="100" cy="265" rx="45" ry="8" fill="#00000015" />
      <rect x={bodyX} y="155" width={bodyWidth} height={body_type === 'Plus' ? 95 : 90} rx="16" fill={colors.top} />
      <rect x={bodyX + 8} y="210" width={bodyWidth - 16} height={40} rx="10" fill={colors.bottom} />
      <rect x="92" y="140" width="16" height="22" rx="6" fill={skin_tone} />
      <ellipse cx="100" cy="110" rx="35" ry="40" fill={skin_tone} />
      <path d={hairPaths[hair_style] ?? hairPaths.Short} fill={hair_color} />
      <circle cx="88"  cy="108" r="4.5" fill="white" />
      <circle cx="112" cy="108" r="4.5" fill="white" />
      <circle cx="89"  cy="109" r="2.5" fill="#2C3E50" />
      <circle cx="113" cy="109" r="2.5" fill="#2C3E50" />
      <circle cx="90"  cy="108" r="1" fill="white" />
      <circle cx="114" cy="108" r="1" fill="white" />
      <path d="M83 101 Q88 98 93 101"   stroke="#5C4033" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M107 101 Q112 98 117 101" stroke="#5C4033" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M98 114 Q100 120 102 114" stroke={skin_tone === '#FDDBB4' ? '#d4966a' : '#00000040'} strokeWidth="1.5" fill="none" strokeLinecap="round" />
      <path d="M90 126 Q100 133 110 126" stroke="#C0604A" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <ellipse cx="65"  cy="112" rx="5" ry="7" fill={skin_tone} />
      <ellipse cx="135" cy="112" rx="5" ry="7" fill={skin_tone} />
      <rect x={bodyX - 16} y="160" width="18" height="60" rx="9" fill={colors.top} />
      <rect x={bodyX + bodyWidth - 2} y="160" width="18" height="60" rx="9" fill={colors.top} />
      <ellipse cx={bodyX - 7} cy="224" rx="9" ry="7" fill={skin_tone} />
      <ellipse cx={bodyX + bodyWidth + 7} cy="224" rx="9" ry="7" fill={skin_tone} />
    </svg>
  )
}

function Pill({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
        selected
          ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-glow-sm'
          : 'bg-cream-100 dark:bg-white/[0.06] text-slate-600 dark:text-white/70 hover:bg-cream-200 dark:hover:bg-white/[0.10]',
      )}
    >
      {label}
    </button>
  )
}

function Swatch({ color, label, selected, onClick }: { color: string; label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={cn(
        'w-8 h-8 rounded-full border-2 transition-all',
        selected ? 'border-indigo-500 scale-110 shadow-md' : 'border-transparent hover:scale-105',
      )}
      style={{ backgroundColor: color }}
    />
  )
}

interface AvatarEditorProps {
  config: AvatarConfig | null | undefined
  onChange: (next: AvatarConfig) => void
  /** Compact mode hides labels and reduces padding for embedding in Profile. */
  compact?: boolean
}

export default function AvatarEditor({ config, onChange, compact = false }: AvatarEditorProps) {
  const c = withAvatarDefaults(config)
  const set = (patch: Partial<AvatarConfig>) => onChange({ ...c, ...patch })

  return (
    <div className={cn('grid gap-4', compact ? 'md:grid-cols-2' : 'md:grid-cols-5')}>
      <div className={cn('space-y-3', compact ? '' : 'md:col-span-3')}>
        <Section title="Body type">
          <div className="flex flex-wrap gap-2">
            {BODY_TYPES.map(b => <Pill key={b} label={b} selected={c.body_type === b} onClick={() => set({ body_type: b })} />)}
          </div>
        </Section>
        <Section title="Skin tone">
          <div className="flex gap-2 flex-wrap">
            {SKIN_TONES.map(s => <Swatch key={s.value} color={s.value} label={s.label} selected={c.skin_tone === s.value} onClick={() => set({ skin_tone: s.value })} />)}
          </div>
        </Section>
        <Section title="Hair style">
          <div className="flex flex-wrap gap-2">
            {HAIR_STYLES.map(h => <Pill key={h} label={h} selected={c.hair_style === h} onClick={() => set({ hair_style: h })} />)}
          </div>
        </Section>
        <Section title="Hair color">
          <div className="flex gap-2 flex-wrap">
            {HAIR_COLORS.map(h => <Swatch key={h.value} color={h.value} label={h.label} selected={c.hair_color === h.value} onClick={() => set({ hair_color: h.value })} />)}
          </div>
        </Section>
        <Section title="Default outfit style">
          <div className="flex flex-wrap gap-2">
            {OUTFITS.map(o => <Pill key={o} label={o} selected={c.outfit === o} onClick={() => set({ outfit: o })} />)}
          </div>
        </Section>
      </div>

      <div className={cn(compact ? '' : 'md:col-span-2')}>
        <div className="rounded-2xl bg-gradient-to-b from-indigo-50 to-cream-100 dark:from-indigo-500/[0.08] dark:to-white/[0.02] border border-cream-200 dark:border-white/[0.06] p-4 aspect-square max-w-[280px] mx-auto">
          <AvatarSVG config={c} />
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-500 dark:text-white/50 mb-1.5">{title}</p>
      {children}
    </div>
  )
}
