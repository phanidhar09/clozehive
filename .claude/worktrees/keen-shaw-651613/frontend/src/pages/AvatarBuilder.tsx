import { useState } from 'react'
import { Download, RefreshCw } from 'lucide-react'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'

const SKIN_TONES = [
  { label: 'Fair',    value: '#FDDBB4' },
  { label: 'Light',   value: '#F0C27F' },
  { label: 'Medium',  value: '#C68642' },
  { label: 'Tan',     value: '#A0522D' },
  { label: 'Brown',   value: '#7B3F00' },
  { label: 'Deep',    value: '#3D1C02' },
]

const HAIR_COLORS = [
  { label: 'Black',   value: '#1a1a1a' },
  { label: 'Brown',   value: '#6B3A2A' },
  { label: 'Blonde',  value: '#D4A017' },
  { label: 'Red',     value: '#8B2500' },
  { label: 'Gray',    value: '#9E9E9E' },
  { label: 'White',   value: '#F5F5F5' },
]

const HAIR_STYLES = ['Short', 'Medium', 'Long', 'Curly', 'Wavy', 'Bun']
const BODY_TYPES  = ['Slim', 'Athletic', 'Average', 'Curvy', 'Plus']
const OUTFITS     = ['Casual', 'Business', 'Formal', 'Sport', 'Evening']

interface AvatarConfig {
  skinTone: string
  hairColor: string
  hairStyle: string
  bodyType: string
  outfit: string
}

function AvatarSVG({ config }: { config: AvatarConfig }) {
  const { skinTone, hairColor, hairStyle, bodyType } = config
  const bodyWidth = bodyType === 'Plus' ? 70 : bodyType === 'Curvy' ? 64 : bodyType === 'Athletic' ? 58 : bodyType === 'Slim' ? 50 : 56
  const bodyX = (200 - bodyWidth) / 2

  const hairPaths: Record<string, string> = {
    Short:   'M68 72 Q100 48 132 72 Q128 55 100 50 Q72 55 68 72Z',
    Medium:  'M65 75 Q100 45 135 75 Q138 95 135 115 Q100 130 65 115 Q62 95 65 75Z',
    Long:    'M62 75 Q100 42 138 75 Q145 115 138 155 Q100 170 62 155 Q55 115 62 75Z',
    Curly:   'M65 78 Q85 45 100 50 Q115 45 135 78 Q145 75 140 95 Q135 70 120 68 Q100 55 80 68 Q65 70 60 95 Q55 75 65 78Z',
    Wavy:    'M62 80 Q82 48 100 52 Q118 48 138 80 Q142 100 138 130 Q118 148 100 150 Q82 148 62 130 Q58 100 62 80Z',
    Bun:     'M70 75 Q100 52 130 75 Q130 65 100 58 Q70 65 70 75Z M100 48 A12 12 0 1 1 100.1 48Z',
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
      {/* Background glow */}
      <defs>
        <radialGradient id="bgGlow" cx="50%" cy="60%" r="50%">
          <stop offset="0%" stopColor="#EEEDFE" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#F5F4F0" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="100" cy="220" rx="70" ry="20" fill="url(#bgGlow)" />

      {/* Shadow */}
      <ellipse cx="100" cy="265" rx="45" ry="8" fill="#00000015" />

      {/* Body */}
      <rect x={bodyX} y="155" width={bodyWidth} height={bodyType === 'Plus' ? 95 : 90} rx="16" fill={colors.top} />
      <rect x={bodyX + 8} y="210" width={bodyWidth - 16} height={40} rx="10" fill={colors.bottom} />

      {/* Neck */}
      <rect x="92" y="140" width="16" height="22" rx="6" fill={skinTone} />

      {/* Head */}
      <ellipse cx="100" cy="110" rx="35" ry="40" fill={skinTone} />

      {/* Hair */}
      <path d={hairPaths[hairStyle] ?? hairPaths.Short} fill={hairColor} />

      {/* Eyes */}
      <circle cx="88" cy="108" r="4.5" fill="white" />
      <circle cx="112" cy="108" r="4.5" fill="white" />
      <circle cx="89" cy="109" r="2.5" fill="#2C3E50" />
      <circle cx="113" cy="109" r="2.5" fill="#2C3E50" />
      <circle cx="90" cy="108" r="1" fill="white" />
      <circle cx="114" cy="108" r="1" fill="white" />

      {/* Eyebrows */}
      <path d="M83 101 Q88 98 93 101" stroke="#5C4033" strokeWidth="1.8" fill="none" strokeLinecap="round" />
      <path d="M107 101 Q112 98 117 101" stroke="#5C4033" strokeWidth="1.8" fill="none" strokeLinecap="round" />

      {/* Nose */}
      <path d="M98 114 Q100 120 102 114" stroke={skinTone === '#FDDBB4' ? '#d4966a' : '#00000040'} strokeWidth="1.5" fill="none" strokeLinecap="round" />

      {/* Smile */}
      <path d="M90 126 Q100 133 110 126" stroke="#C0604A" strokeWidth="1.8" fill="none" strokeLinecap="round" />

      {/* Ears */}
      <ellipse cx="65" cy="112" rx="5" ry="7" fill={skinTone} />
      <ellipse cx="135" cy="112" rx="5" ry="7" fill={skinTone} />

      {/* Arms */}
      <rect x={bodyX - 16} y="160" width="18" height="60" rx="9" fill={colors.top} />
      <rect x={bodyX + bodyWidth - 2} y="160" width="18" height="60" rx="9" fill={colors.top} />

      {/* Hands */}
      <ellipse cx={bodyX - 7} cy="224" rx="9" ry="7" fill={skinTone} />
      <ellipse cx={bodyX + bodyWidth + 7} cy="224" rx="9" ry="7" fill={skinTone} />
    </svg>
  )
}

function OptionPill({ label, selected, onClick }: { label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all',
        selected ? 'bg-brand-600 text-white shadow-sm' : 'bg-cream-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-cream-200 dark:hover:bg-slate-600',
      )}
    >
      {label}
    </button>
  )
}

function ColorSwatch({ color, label, selected, onClick }: { color: string; label: string; selected: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      title={label}
      className={cn('w-8 h-8 rounded-full border-2 transition-all', selected ? 'border-brand-500 scale-110 shadow-md' : 'border-transparent hover:scale-105')}
      style={{ backgroundColor: color }}
    />
  )
}

export default function AvatarBuilder() {
  const [config, setConfig] = useState<AvatarConfig>({
    skinTone: '#FDDBB4',
    hairColor: '#1a1a1a',
    hairStyle: 'Medium',
    bodyType: 'Athletic',
    outfit: 'Casual',
  })

  const update = (key: keyof AvatarConfig, value: string) => setConfig(c => ({ ...c, [key]: value }))

  const randomise = () => setConfig({
    skinTone: SKIN_TONES[Math.floor(Math.random() * SKIN_TONES.length)].value,
    hairColor: HAIR_COLORS[Math.floor(Math.random() * HAIR_COLORS.length)].value,
    hairStyle: HAIR_STYLES[Math.floor(Math.random() * HAIR_STYLES.length)],
    bodyType: BODY_TYPES[Math.floor(Math.random() * BODY_TYPES.length)],
    outfit: OUTFITS[Math.floor(Math.random() * OUTFITS.length)],
  })

  return (
    <div className="max-w-4xl animate-slide-up">
      <div className="mb-5">
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100">Avatar Builder</h2>
        <p className="text-sm text-slate-400 mt-0.5">Customise your digital style persona</p>
      </div>

      <div className="grid md:grid-cols-5 gap-6">
        {/* Controls */}
        <div className="md:col-span-3 space-y-5">
          {/* Body type */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Body type</p>
            <div className="flex flex-wrap gap-2">
              {BODY_TYPES.map(b => <OptionPill key={b} label={b} selected={config.bodyType === b} onClick={() => update('bodyType', b)} />)}
            </div>
          </div>

          {/* Skin tone */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Skin tone</p>
            <div className="flex gap-2 flex-wrap">
              {SKIN_TONES.map(s => <ColorSwatch key={s.value} color={s.value} label={s.label} selected={config.skinTone === s.value} onClick={() => update('skinTone', s.value)} />)}
            </div>
          </div>

          {/* Hair style */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Hair style</p>
            <div className="flex flex-wrap gap-2">
              {HAIR_STYLES.map(h => <OptionPill key={h} label={h} selected={config.hairStyle === h} onClick={() => update('hairStyle', h)} />)}
            </div>
          </div>

          {/* Hair color */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Hair color</p>
            <div className="flex gap-2 flex-wrap items-center">
              {HAIR_COLORS.map(h => <ColorSwatch key={h.value} color={h.value} label={h.label} selected={config.hairColor === h.value} onClick={() => update('hairColor', h.value)} />)}
            </div>
          </div>

          {/* Outfit */}
          <div className="card p-4 space-y-3">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">Default outfit style</p>
            <div className="flex flex-wrap gap-2">
              {OUTFITS.map(o => <OptionPill key={o} label={o} selected={config.outfit === o} onClick={() => update('outfit', o)} />)}
            </div>
          </div>

          <div className="flex gap-3">
            <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={randomise}>Randomise</Button>
            <Button icon={<Download size={14} />}>Save Avatar</Button>
          </div>
        </div>

        {/* Preview */}
        <div className="md:col-span-2">
          <div className="card p-4 sticky top-4">
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4 text-center">Live preview</p>
            <div className="bg-gradient-to-b from-brand-50 to-cream-100 dark:from-brand-900/20 dark:to-slate-800 rounded-2xl p-4 aspect-square max-w-[280px] mx-auto">
              <AvatarSVG config={config} />
            </div>
            <div className="mt-4 space-y-2">
              {[
                { label: 'Body', value: config.bodyType },
                { label: 'Hair', value: `${config.hairStyle}` },
                { label: 'Outfit', value: config.outfit },
              ].map(s => (
                <div key={s.label} className="flex justify-between text-xs">
                  <span className="text-slate-400">{s.label}</span>
                  <span className="font-medium text-slate-700 dark:text-slate-300">{s.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
