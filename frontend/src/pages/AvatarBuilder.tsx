import { useState } from 'react'
import { Download, Loader2, RefreshCw } from 'lucide-react'
import Button from '@/components/ui/Button'
import GlassCard from '@/components/ui/GlassCard'
import AvatarEditor, {
  AVATAR_DEFAULTS, BODY_TYPES, HAIR_COLORS, HAIR_STYLES, OUTFITS, SKIN_TONES,
  withAvatarDefaults,
} from '@/components/profile/AvatarEditor'
import { useApp } from '@/store'
import { authApi } from '@/lib/api'
import type { AvatarConfig } from '@/types'

function pick<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)]
}

export default function AvatarBuilder() {
  const { currentUser, updateCurrentUser } = useApp()
  const [config, setConfig] = useState<AvatarConfig>(
    () => withAvatarDefaults(currentUser?.avatar_config),
  )
  const [saving, setSaving] = useState(false)

  const randomise = () =>
    setConfig({
      skin_tone:  pick(SKIN_TONES).value,
      hair_color: pick(HAIR_COLORS).value,
      hair_style: pick(HAIR_STYLES),
      body_type:  pick(BODY_TYPES),
      outfit:     pick(OUTFITS),
    })

  const reset = () => setConfig(AVATAR_DEFAULTS)

  const save = async () => {
    setSaving(true)
    try {
      const updated = await authApi.updateProfile({ avatar_config: config })
      updateCurrentUser({ avatar_config: updated.avatar_config })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-4xl space-y-5">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-white">Avatar Builder</h2>
        <p className="text-sm text-slate-400 mt-0.5">Customise your digital style persona — saved to your profile.</p>
      </div>

      <GlassCard padding="md">
        <AvatarEditor config={config} onChange={setConfig} />
      </GlassCard>

      <div className="flex flex-wrap gap-3">
        <Button variant="secondary" icon={<RefreshCw size={14} />} onClick={randomise}>Randomise</Button>
        <Button variant="ghost" onClick={reset}>Reset</Button>
        <Button
          icon={saving ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />}
          onClick={save}
          disabled={saving}
        >
          {saving ? 'Saving…' : 'Save Avatar'}
        </Button>
      </div>
    </div>
  )
}
