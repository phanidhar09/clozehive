/**
 * ItemDetailModal — premium tabbed detail view for a closet item.
 * Tabs: Overview (attributes, stats, notes) | Similar Items (similarity panel)
 */

import { useState } from 'react'
import {
  Heart, Leaf, Tag, Shirt, Trash2, Pencil,
  BarChart2, Layers, Calendar, DollarSign,
} from 'lucide-react'
import type { ClosetItem } from '@/types'
import Modal from '@/components/ui/Modal'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import SimilarItems from '@/components/closet/SimilarItems'
import EditItemModal from '@/components/closet/EditItemModal'
import { ecoScoreBg, formatDate } from '@/lib/utils'
import { cn } from '@/lib/utils'

interface Props {
  item: ClosetItem | null
  open: boolean
  onClose: () => void
  onDelete?: (item: ClosetItem) => void
  onSaved?: (updated: ClosetItem) => void
}

type Tab = 'overview' | 'similar'

const CATEGORY_EMOJI: Record<string, string> = {
  shoes: '👟',
  dresses: '👗',
  accessories: '👜',
  outerwear: '🧥',
  bottoms: '👖',
  tops: '👕',
}

export default function ItemDetailModal({ item, open, onClose, onDelete, onSaved }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [current, setCurrent] = useState<ClosetItem | null>(item)
  const [activeTab, setActiveTab] = useState<Tab>('overview')

  // Sync when parent opens a different item
  if (item && item.id !== current?.id) {
    setCurrent(item)
    setActiveTab('overview')
  }

  if (!current) return null

  const handleSaved = (updated: ClosetItem) => {
    setCurrent(updated)
    onSaved?.(updated)
  }

  const categoryEmoji = CATEGORY_EMOJI[current.category] ?? '👕'

  const attrs = [
    { icon: <Shirt size={12} />, label: 'Category', value: current.category },
    { icon: <Tag size={12} />, label: 'Color', value: current.color },
    { icon: <Tag size={12} />, label: 'Fabric', value: current.fabric },
    { icon: <Tag size={12} />, label: 'Pattern', value: current.pattern },
    { icon: <Calendar size={12} />, label: 'Season', value: Array.isArray(current.season) ? current.season.join(', ') : current.season },
    { icon: <Tag size={12} />, label: 'Size', value: current.size },
    { icon: <Tag size={12} />, label: 'Brand', value: current.brand },
  ].filter(a => a.value)

  return (
    <>
      <Modal open={open} onClose={onClose} size="lg" title="">
        <div className="flex flex-col sm:flex-row gap-0 -m-4 sm:-m-6">

          {/* ── Left column: image ───────────────────────────────────────── */}
          <div className="sm:w-52 flex-shrink-0 bg-cream-50 dark:bg-slate-800/60 sm:rounded-l-2xl overflow-hidden">
            <div className="relative aspect-[3/4] sm:h-full sm:aspect-auto">
              {current.image_url ? (
                <img
                  src={current.image_url}
                  alt={current.name}
                  className="w-full h-full object-contain"
                  onError={e => { (e.target as HTMLImageElement).style.display = 'none' }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-6xl min-h-[200px]">
                  {categoryEmoji}
                </div>
              )}
              {/* Favourite overlay */}
              {current.is_favorite && (
                <div className="absolute top-3 right-3 w-7 h-7 rounded-full bg-white/80 dark:bg-black/50 backdrop-blur-sm flex items-center justify-center shadow-sm">
                  <Heart size={14} className="text-pink-500 fill-pink-500" />
                </div>
              )}
            </div>
          </div>

          {/* ── Right column: content ────────────────────────────────────── */}
          <div className="flex-1 min-w-0 flex flex-col p-4 sm:p-5">

            {/* Header */}
            <div className="mb-3">
              <h2 className="font-display font-bold text-lg sm:text-xl text-slate-800 dark:text-white leading-tight">
                {current.name}
              </h2>
              {current.brand && (
                <p className="text-sm text-slate-400 dark:text-slate-500 mt-0.5">{current.brand}</p>
              )}
            </div>

            {/* Tab bar */}
            <div className="flex gap-1 mb-4 p-1 rounded-xl bg-slate-100 dark:bg-white/[0.06] self-start">
              {([
                { id: 'overview' as Tab, label: 'Overview' },
                { id: 'similar' as Tab, label: 'Similar Items' },
              ]).map(tab => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150',
                    activeTab === tab.id
                      ? 'bg-white dark:bg-white/[0.12] text-slate-800 dark:text-white shadow-sm'
                      : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200',
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* ── Overview tab ─────────────────────────────────────────── */}
            {activeTab === 'overview' && (
              <div className="flex-1 space-y-4 overflow-y-auto">

                {/* Attribute chips */}
                {attrs.length > 0 && (
                  <div className="grid grid-cols-2 gap-2">
                    {attrs.map(attr => (
                      <div
                        key={attr.label}
                        className="bg-cream-50 dark:bg-slate-800/80 rounded-xl p-2.5 border border-cream-200 dark:border-white/[0.06]"
                      >
                        <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide mb-0.5 flex items-center gap-1">
                          {attr.icon}
                          {attr.label}
                        </p>
                        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 capitalize truncate">
                          {attr.value}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {/* Occasions */}
                {current.occasion && current.occasion.length > 0 && (
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400 dark:text-white/30 mb-1.5">
                      Occasions
                    </p>
                    <div className="flex gap-1.5 flex-wrap">
                      {current.occasion.map(o => (
                        <Badge key={o} variant="purple">{o}</Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Stats row */}
                <div className="flex items-center gap-3 pt-3 border-t border-cream-200 dark:border-white/[0.07]">
                  <div className="flex items-center gap-2 flex-1">
                    <div className="w-8 h-8 rounded-xl bg-brand-50 dark:bg-brand-900/30 flex items-center justify-center">
                      <BarChart2 size={14} className="text-brand-500" />
                    </div>
                    <div>
                      <p className="text-base font-bold text-brand-600 dark:text-brand-400 leading-none">
                        {current.wear_count ?? 0}
                      </p>
                      <p className="text-[10px] text-slate-400 mt-0.5">Times worn</p>
                    </div>
                  </div>

                  {current.last_worn && (
                    <div className="flex items-center gap-2 flex-1">
                      <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-white/[0.06] flex items-center justify-center">
                        <Calendar size={14} className="text-slate-400" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 leading-none">
                          {formatDate(current.last_worn)}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">Last worn</p>
                      </div>
                    </div>
                  )}

                  {current.price && (
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-xl bg-emerald-50 dark:bg-emerald-900/20 flex items-center justify-center">
                        <DollarSign size={14} className="text-emerald-500" />
                      </div>
                      <div>
                        <p className="text-base font-bold text-slate-800 dark:text-slate-100 leading-none">
                          ${current.price}
                        </p>
                        <p className="text-[10px] text-slate-400 mt-0.5">Paid</p>
                      </div>
                    </div>
                  )}
                </div>

                {/* Eco score */}
                {current.eco_score && (
                  <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-emerald-50 dark:bg-emerald-900/10 border border-emerald-200 dark:border-emerald-700/30">
                    <Leaf size={13} className="text-emerald-500 flex-shrink-0" />
                    <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">Eco Score</span>
                    <span className={cn('badge text-xs ml-auto', ecoScoreBg(current.eco_score))}>
                      {current.eco_score}/10
                    </span>
                  </div>
                )}

                {/* Notes */}
                {current.notes && (
                  <div className="bg-amber-50 dark:bg-amber-900/10 border border-amber-200 dark:border-amber-700/30 rounded-xl p-3">
                    <p className="text-xs font-medium text-amber-600 dark:text-amber-400 mb-1">Notes</p>
                    <p className="text-sm text-amber-700 dark:text-amber-300 leading-relaxed">{current.notes}</p>
                  </div>
                )}

                {/* Action buttons */}
                <div className="flex gap-2 pt-1">
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Pencil size={13} />}
                    className="flex-1"
                    onClick={() => setEditOpen(true)}
                  >
                    Edit
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    icon={<Layers size={13} />}
                    onClick={() => setActiveTab('similar')}
                  >
                    Similar
                  </Button>
                  {onDelete && (
                    <Button
                      variant="danger"
                      size="sm"
                      icon={<Trash2 size={13} />}
                      onClick={() => { onClose(); onDelete(current) }}
                    />
                  )}
                </div>
              </div>
            )}

            {/* ── Similar Items tab ─────────────────────────────────────── */}
            {activeTab === 'similar' && (
              <div className="flex-1 overflow-y-auto">
                <SimilarItems
                  itemId={current.id}
                  onViewItem={viewId => {
                    // Close this modal and let the parent handle navigation if needed
                    // For now, just close — parent can wire up onViewItem if desired
                    onClose()
                    void viewId // suppress unused-var lint
                  }}
                />
              </div>
            )}
          </div>
        </div>
      </Modal>

      {/* Edit modal sits on top */}
      {editOpen && (
        <EditItemModal
          item={current}
          open={editOpen}
          onClose={() => setEditOpen(false)}
          onSaved={handleSaved}
        />
      )}
    </>
  )
}
