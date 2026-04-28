import { useState } from 'react'
import { Plane, AlertTriangle, CheckCircle2, Package, Calendar, MapPin, Loader2 } from 'lucide-react'
import Button from '@/components/ui/Button'
import Input, { Select } from '@/components/ui/Input'
import Badge from '@/components/ui/Badge'
import { useApp } from '@/store'
import { streamPackingList } from '@/lib/api'
import type { PackingResult } from '@/types'
import { weatherIcon } from '@/lib/utils'

const PURPOSE_OPTIONS = [
  { value: 'leisure', label: '🌴 Leisure / Holiday' },
  { value: 'business', label: '💼 Business' },
  { value: 'beach', label: '🏖️ Beach / Resort' },
  { value: 'formal', label: '🎩 Formal Event' },
  { value: 'adventure', label: '🏔️ Adventure / Hiking' },
]

export default function TravelPlanner() {
  const { closetItems } = useApp()
  const [form, setForm] = useState({ destination: '', start_date: '', end_date: '', purpose: 'leisure' })
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<PackingResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'packing' | 'daily' | 'weather'>('packing')

  // Streaming state
  const [streamStatus, setStreamStatus] = useState('')
  const [streamText, setStreamText] = useState('')

  const submit = async () => {
    if (!form.destination || !form.start_date || !form.end_date) return
    setLoading(true)
    setError(null)
    setResult(null)
    setStreamStatus('Initialising…')
    setStreamText('')

    await streamPackingList(
      {
        destination: form.destination,
        start_date: form.start_date,
        end_date: form.end_date,
        purpose: form.purpose,
      },
      {
        onStatus: (msg) => setStreamStatus(msg),
        onToken: (token) => setStreamText(t => t + token),
        onResult: (data) => {
          setResult(data)
          setActiveTab('packing')
        },
        onError: (err) => {
          setError(`Could not generate packing list: ${err}. Make sure the backend and AI service are running.`)
          setLoading(false)
          setStreamStatus('')
        },
        onDone: () => {
          setLoading(false)
          setStreamStatus('')
        },
      },
    )
  }

  return (
    <div className="max-w-4xl space-y-6 animate-slide-up">
      <div>
        <h2 className="font-display font-bold text-xl text-slate-800 dark:text-slate-100 flex items-center gap-2">
          <Plane size={20} className="text-brand-500" /> Travel Planner
        </h2>
        <p className="text-sm text-slate-400 mt-0.5">
          {closetItems.length > 0
            ? `AI generates a smart packing list from your ${closetItems.length} wardrobe items`
            : 'AI generates a smart packing list based on weather + your wardrobe'}
        </p>
      </div>

      {closetItems.length === 0 && (
        <div className="card p-3 bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300 text-sm flex items-center gap-2">
          <AlertTriangle size={15} />
          Your wardrobe is empty. The AI will generate a list of items you should buy.
        </div>
      )}

      {/* Form */}
      <div className="card p-6 space-y-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <Input
            label="Destination"
            placeholder="e.g. Bali, Indonesia"
            value={form.destination}
            onChange={e => setForm(f => ({ ...f, destination: e.target.value }))}
            leftIcon={<MapPin size={14} />}
          />
          <Select
            label="Trip purpose"
            options={PURPOSE_OPTIONS}
            value={form.purpose}
            onChange={e => setForm(f => ({ ...f, purpose: e.target.value }))}
          />
        </div>
        <div className="grid sm:grid-cols-2 gap-4">
          <Input label="Start date" type="date" value={form.start_date} onChange={e => setForm(f => ({ ...f, start_date: e.target.value }))} leftIcon={<Calendar size={14} />} />
          <Input label="End date" type="date" value={form.end_date} onChange={e => setForm(f => ({ ...f, end_date: e.target.value }))} leftIcon={<Calendar size={14} />} />
        </div>
        <Button
          className="w-full sm:w-auto"
          onClick={submit}
          loading={loading}
          icon={<Plane size={15} />}
          disabled={!form.destination || !form.start_date || !form.end_date}
        >
          Generate Packing List
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="card p-3 bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm flex items-start gap-2">
          <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {/* Live streaming panel */}
      {loading && (
        <div className="card p-6 space-y-4">
          {/* Status line */}
          <div className="flex items-center gap-3 text-slate-500 dark:text-slate-400">
            <Loader2 size={18} className="animate-spin text-brand-500 flex-shrink-0" />
            <span className="text-sm font-medium">{streamStatus || 'Working…'}</span>
          </div>

          {/* Streaming AI text (packing insights) */}
          {streamText && (
            <div className="relative rounded-xl bg-brand-50 dark:bg-brand-900/20 border border-brand-200 dark:border-brand-800 p-4">
              <p className="text-xs font-semibold text-brand-600 dark:text-brand-400 mb-2 uppercase tracking-wide">
                ✨ AI Packing Insights
              </p>
              <p className="text-sm text-slate-700 dark:text-slate-300 leading-relaxed" style={{ whiteSpace: 'pre-wrap' }}>
                {streamText}
                {/* Blinking cursor */}
                <span className="inline-block w-0.5 h-4 bg-brand-500 ml-0.5 animate-pulse align-middle" />
              </p>
            </div>
          )}

          {/* Progress steps */}
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {['Fetching weather', 'Matching wardrobe', 'AI insights'].map((step, i) => {
              const reached =
                (i === 0 && streamStatus.includes('weather')) ||
                (i === 0 && streamStatus.includes('Matching')) ||
                (i === 0 && streamStatus.includes('AI')) ||
                (i === 1 && (streamStatus.includes('Matching') || streamStatus.includes('AI'))) ||
                (i === 2 && streamStatus.includes('AI'))
              return (
                <span key={step} className={`flex items-center gap-1 ${reached ? 'text-brand-600 dark:text-brand-400' : ''}`}>
                  {reached ? '✓' : '○'} {step}
                  {i < 2 && <span className="text-slate-300 dark:text-slate-600 mx-1">→</span>}
                </span>
              )
            })}
          </div>
        </div>
      )}

      {/* Result */}
      {result && !loading && (
        <div className="space-y-4 animate-slide-up">
          {/* Alerts */}
          <div className="space-y-2">
            {result.alerts.map((alert, i) => {
              const isWarning = alert.includes('⚠️') || alert.includes('🌧')
              return (
                <div key={i} className={`flex items-start gap-3 p-3 rounded-xl text-sm ${isWarning ? 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300' : 'bg-brand-50 dark:bg-brand-900/20 text-brand-700 dark:text-brand-300'}`}>
                  {isWarning ? <AlertTriangle size={15} className="flex-shrink-0 mt-0.5" /> : <CheckCircle2 size={15} className="flex-shrink-0 mt-0.5" />}
                  {alert}
                </div>
              )
            })}
          </div>

          {/* Weather summary */}
          <div className="card p-4">
            <div className="flex items-center gap-3 mb-3">
              <div className="text-2xl">{weatherIcon(result.weather_summary.dominant_condition)}</div>
              <div>
                <p className="font-semibold text-slate-800 dark:text-slate-100">{result.destination}</p>
                <p className="text-sm text-slate-400">{result.duration_days} days · {result.trip_type}</p>
              </div>
              <div className="ml-auto text-right">
                <p className="font-bold text-lg text-slate-800 dark:text-slate-100">{result.weather_summary.avg_high}°C</p>
                <p className="text-xs text-slate-400">avg high</p>
              </div>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 bg-cream-50 dark:bg-slate-800 rounded-lg p-2.5">{result.weather_summary.recommendation}</p>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 bg-cream-100 dark:bg-slate-800 p-1 rounded-xl w-fit">
            {(['packing', 'daily', 'weather'] as const).map(tab => (
              <button key={tab} onClick={() => setActiveTab(tab)} className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-all capitalize ${activeTab === tab ? 'bg-white dark:bg-slate-700 text-slate-800 dark:text-white shadow-sm' : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'}`}>
                {tab === 'packing' ? '🧳 Packing List' : tab === 'daily' ? '📅 Daily Plan' : '🌤️ Weather'}
              </button>
            ))}
          </div>

          {/* Packing list */}
          {activeTab === 'packing' && (
            <div className="grid sm:grid-cols-2 gap-4 animate-fade-in">
              <div className="card p-4 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <CheckCircle2 size={15} className="text-emerald-500" />
                  <p className="font-semibold text-sm text-slate-700 dark:text-slate-300">From your closet</p>
                  <Badge variant="green">{result.packing_list.length} items</Badge>
                </div>
                {result.packing_list.length === 0 ? (
                  <p className="text-sm text-slate-400 text-center py-4">No matching items in your wardrobe</p>
                ) : (
                  result.packing_list.map((item, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/20">
                      <CheckCircle2 size={14} className="text-emerald-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{item.name}</p>
                        <p className="text-[11px] text-slate-400">{item.reason}</p>
                      </div>
                      <Package size={12} className="text-emerald-400 flex-shrink-0" />
                    </div>
                  ))
                )}
              </div>

              <div className="card p-4 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <AlertTriangle size={15} className="text-red-500" />
                  <p className="font-semibold text-sm text-slate-700 dark:text-slate-300">Need to buy</p>
                  <Badge variant={result.missing_items.length > 0 ? 'red' : 'green'}>
                    {result.missing_items.length} missing
                  </Badge>
                </div>
                {result.missing_items.length === 0 ? (
                  <p className="text-sm text-emerald-600 text-center py-4">✓ Your wardrobe has everything!</p>
                ) : (
                  result.missing_items.map((item, i) => (
                    <div key={i} className="flex items-center gap-3 p-2 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800">
                      <AlertTriangle size={14} className="text-red-400 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-red-700 dark:text-red-300 truncate">{item.name}</p>
                        <p className="text-[11px] text-red-400">{item.reason}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Daily plan */}
          {activeTab === 'daily' && (
            <div className="space-y-3 animate-fade-in">
              {result.daily_plan.length === 0 ? (
                <div className="card p-8 text-center text-slate-400">No daily plan generated</div>
              ) : (
                result.daily_plan.map((day, i) => (
                  <div key={i} className="card p-4 flex gap-4">
                    <div className="text-center flex-shrink-0 w-14">
                      <div className="text-2xl mb-1">{weatherIcon(day.weather.condition)}</div>
                      <p className="text-[10px] text-slate-400 font-medium">{new Date(day.date).toLocaleDateString('en', { month: 'short', day: 'numeric' })}</p>
                      <p className="text-xs font-bold text-slate-700 dark:text-slate-300">{day.weather.temp_high}°</p>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-xs text-slate-400 mb-1">{day.weather.description}</p>
                      <p className="text-sm text-slate-700 dark:text-slate-200">{day.outfit_suggestion}</p>
                      <div className="flex gap-1 flex-wrap mt-2">
                        {day.items_needed.map(item => <Badge key={item} variant="purple">{item}</Badge>)}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Weather grid */}
          {activeTab === 'weather' && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 animate-fade-in">
              {result.daily_plan.map((day, i) => (
                <div key={i} className="card p-3 text-center space-y-1">
                  <p className="text-xs text-slate-400">{new Date(day.date).toLocaleDateString('en', { weekday: 'short' })}</p>
                  <div className="text-2xl">{weatherIcon(day.weather.condition)}</div>
                  <p className="font-bold text-slate-800 dark:text-slate-100">{day.weather.temp_high}°</p>
                  <p className="text-[11px] text-slate-400">{day.weather.temp_low}° low</p>
                  <p className="text-[10px] text-slate-500 capitalize">{day.weather.condition.replace('_', ' ')}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
