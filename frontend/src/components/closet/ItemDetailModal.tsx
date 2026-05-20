import { useState } from 'react'
import { Heart, Leaf, Tag, Shirt, Trash2, Pencil } from 'lucide-react'
import type { ClosetItem } from '@/types'
import Modal from '@/components/ui/Modal'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import SimilarItems from '@/components/closet/SimilarItems'
import EditItemModal from '@/components/closet/EditItemModal'
import { ecoScoreBg, formatDate } from '@/lib/utils'

interface Props {
  item: ClosetItem | null
  open: boolean
  onClose: () => void
  onDelete?: (item: ClosetItem) => void
  onSaved?: (updated: ClosetItem) => void
}

export default function ItemDetailModal({ item, open, onClose, onDelete, onSaved }: Props) {
  const [editOpen, setEditOpen] = useState(false)
  const [current, setCurrent] = useState<ClosetItem | null>(item)

  // Sync with parent-supplied item when it changes (e.g. modal re-opened for a different item)
  if (item && item.id !== current?.id) setCurrent(item)

  if (!current) return null

  const handleSaved = (updated: ClosetItem) => {
    setCurrent(updated)
    onSaved?.(updated)
  }

  return (
    <>
      <Modal open={open} onClose={onClose} size="lg" title="">
        <div className="flex flex-col sm:flex-row gap-6">
          {/* Image */}
          <div className="sm:w-56 flex-shrink-0">
            <div className="aspect-[3/4] rounded-xl overflow-hidden bg-cream-100 dark:bg-slate-800">
              {current.image_url ? (
                <img src={current.image_url} alt={current.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-5xl">
                  {current.category === 'shoes' ? '👟' : current.category === 'dresses' ? '👗' : '👕'}
                </div>
              )}
            </div>
          </div>

          {/* Details */}
          <div className="flex-1 min-w-0 space-y-4">
            <div>
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-display font-bold text-xl text-slate-800 dark:text-white">{current.name}</h2>
                {current.is_favorite && <Heart size={18} className="text-pink-500 fill-pink-500 flex-shrink-0 mt-1" />}
              </div>
              {current.brand && <p className="text-sm text-slate-400 mt-0.5">{current.brand}</p>}
            </div>

            {/* Attribute grid */}
            <div className="grid grid-cols-2 gap-3">
              {[
                { icon: <Shirt size={13} />, label: 'Category', value: current.category },
                { icon: <Tag size={13} />, label: 'Color',    value: current.color },
                { icon: <Tag size={13} />, label: 'Fabric',   value: current.fabric },
                { icon: <Tag size={13} />, label: 'Pattern',  value: current.pattern },
                { icon: <Tag size={13} />, label: 'Season',   value: current.season },
                { icon: <Tag size={13} />, label: 'Size',     value: current.size },
              ].filter(a => a.value).map(attr => (
                <div key={attr.label} className="bg-cream-50 dark:bg-slate-800 rounded-xl p-2.5">
                  <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide mb-0.5 flex items-center gap-1">
                    {attr.icon}{attr.label}
                  </p>
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200 capitalize">{attr.value}</p>
                </div>
              ))}
            </div>

            {/* Eco score */}
            {current.eco_score && (
              <div className="flex items-center gap-2">
                <Leaf size={14} className="text-emerald-500" />
                <span className="text-sm font-medium text-slate-600 dark:text-slate-300">Eco Score:</span>
                <span className={`badge text-xs ${ecoScoreBg(current.eco_score)}`}>{current.eco_score}/10</span>
              </div>
            )}

            {/* Occasions */}
            {current.occasion.length > 0 && (
              <div>
                <p className="text-xs font-medium text-slate-400 uppercase tracking-wide mb-2">Occasions</p>
                <div className="flex gap-1.5 flex-wrap">
                  {current.occasion.map(o => <Badge key={o} variant="purple">{o}</Badge>)}
                </div>
              </div>
            )}

            {/* Stats */}
            <div className="flex items-center gap-4 pt-2 border-t border-cream-300 dark:border-slate-700">
              <div className="text-center">
                <p className="text-lg font-bold text-brand-600">{current.wear_count}</p>
                <p className="text-[11px] text-slate-400">Times worn</p>
              </div>
              {current.last_worn && (
                <div className="text-center">
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">{formatDate(current.last_worn)}</p>
                  <p className="text-[11px] text-slate-400">Last worn</p>
                </div>
              )}
              {current.price && (
                <div className="text-center ml-auto">
                  <p className="text-lg font-bold text-slate-800 dark:text-slate-100">${current.price}</p>
                  <p className="text-[11px] text-slate-400">Purchase price</p>
                </div>
              )}
            </div>

            {/* Notes */}
            {current.notes && (
              <div className="bg-amber-50 dark:bg-amber-900/20 rounded-xl p-3">
                <p className="text-xs text-amber-700 dark:text-amber-300">{current.notes}</p>
              </div>
            )}

            {/* Similar items */}
            <SimilarItems itemId={current.id} />

            {/* Actions */}
            <div className="flex gap-2 pt-1">
              <Button
                variant="secondary"
                size="sm"
                icon={<Pencil size={13} />}
                className="flex-1"
                onClick={() => setEditOpen(true)}
              >
                Edit Item
              </Button>
              {onDelete && (
                <Button
                  variant="danger"
                  size="sm"
                  icon={<Trash2 size={14} />}
                  onClick={() => { onClose(); onDelete(current) }}
                >
                  Remove
                </Button>
              )}
            </div>
          </div>
        </div>
      </Modal>

      {/* Edit modal — sits on top of detail modal */}
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
