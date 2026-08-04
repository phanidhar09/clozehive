/**
 * Plan-editing UI: outfit swap/remove/add, checklist add/remove, closet
 * suggestions, and the pinned-day badge.
 *
 * These assert the *contract with the API layer* — every edit sends the right
 * operation and ids — because the server re-derives the whole plan and returns
 * it, so a wrong payload is the only way the UI can get this wrong.
 */

import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import { DayPlanCard } from '@/components/travel/DayPlanCard'
import { PackingChecklistPanel } from '@/components/travel/PackingChecklistPanel'
import { ClosetItemPicker } from '@/components/travel/ClosetItemPicker'
import type { ClosetItem, ClosetSuggestion, PackingChecklistItem, RichDayPlan } from '@/types'

const day = (): RichDayPlan => ({
  day_number: 3,
  date: '2026-08-03',
  weather_note: 'Mild',
  activities: ['Sightseeing'],
  outfits: [
    {
      slot: 'morning',
      activity: 'Sightseeing',
      outfit_name: 'City walk',
      items: [
        { closet_item_id: 't1', item_name: 'White Oxford Shirt', category: 'tops', source: 'from_closet' },
        { closet_item_id: null, item_name: 'Panama Hat', category: 'accessories', source: 'missing_recommended' },
      ],
      styling_notes: 'Tuck the shirt.',
    },
  ],
})

const closet = (): ClosetItem[] => ([
  {
    id: 't2', user_id: 'u1', name: 'Navy Linen Tee', category: 'tops',
    tags: [], wear_count: 0, occasion: [], created_at: new Date().toISOString(),
  },
  {
    id: 'o1', user_id: 'u1', name: 'Rain Jacket', category: 'outerwear',
    tags: [], wear_count: 0, occasion: [], created_at: new Date().toISOString(),
  },
])

// ── Day plan editing ──────────────────────────────────────────────────────

test('swapping an outfit item reports the item being replaced', async () => {
  const onEdit = vi.fn()
  render(<DayPlanCard day={day()} editable onEdit={onEdit} />)

  await userEvent.click(screen.getByRole('button', { name: /swap white oxford shirt/i }))

  expect(onEdit).toHaveBeenCalledWith({
    dayNumber: 3, slot: 'morning', operation: 'swap', targetItemId: 't1', targetCategory: 'tops',
  })
})

test('removing an outfit item reports the item to drop', async () => {
  const onEdit = vi.fn()
  render(<DayPlanCard day={day()} editable onEdit={onEdit} />)

  await userEvent.click(screen.getByRole('button', { name: /remove white oxford shirt/i }))

  expect(onEdit).toHaveBeenCalledWith({
    dayNumber: 3, slot: 'morning', operation: 'remove', targetItemId: 't1',
  })
})

test('adding to an outfit reports the day and slot with no target', async () => {
  const onEdit = vi.fn()
  render(<DayPlanCard day={day()} editable onEdit={onEdit} />)

  await userEvent.click(screen.getByRole('button', { name: /add item/i }))

  expect(onEdit).toHaveBeenCalledWith({ dayNumber: 3, slot: 'morning', operation: 'add' })
})

test('a "buy this" placeholder offers no edit controls — there is no id to act on', () => {
  render(<DayPlanCard day={day()} editable onEdit={vi.fn()} />)
  expect(screen.queryByRole('button', { name: /swap panama hat/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /remove panama hat/i })).not.toBeInTheDocument()
})

test('edit controls are absent unless the card is editable', () => {
  render(<DayPlanCard day={day()} />)
  expect(screen.queryByRole('button', { name: /swap/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /add item/i })).not.toBeInTheDocument()
})

test('a pinned day is badged so the user knows a regenerate will spare it', () => {
  const { rerender } = render(<DayPlanCard day={day()} editable pinned />)
  expect(screen.getByTitle(/regenerating keeps it as-is/i)).toBeInTheDocument()

  rerender(<DayPlanCard day={day()} editable pinned={false} />)
  expect(screen.queryByTitle(/regenerating keeps it as-is/i)).not.toBeInTheDocument()
})

test('an edited outfit warns that its styling notes are now outdated', () => {
  const edited = day()
  edited.outfits[0].notes_stale = true
  render(<DayPlanCard day={edited} editable />)
  expect(screen.getByText(/written for the original pieces/i)).toBeInTheDocument()
})

// ── Checklist editing ─────────────────────────────────────────────────────

const checklistItem = (over: Partial<PackingChecklistItem> = {}): PackingChecklistItem => ({
  item_name: 'White Oxford Shirt',
  category: 'tops',
  closet_item_id: 't1',
  source: 'from_closet',
  quantity: 1,
  planned_days: ['Day 1'],
  activities: [],
  rewear_count: 1,
  is_packed: false,
  ...over,
})

test('removing a checklist row does not also toggle its packed checkbox', async () => {
  const onRemoveItem = vi.fn()
  const onToggle = vi.fn()
  render(
    <PackingChecklistPanel
      items={[checklistItem()]}
      packedState={{}}
      onToggle={onToggle}
      editable
      onRemoveItem={onRemoveItem}
    />,
  )

  await userEvent.click(screen.getByRole('button', { name: /remove white oxford shirt from the list/i }))

  expect(onRemoveItem).toHaveBeenCalledWith('t1')
  // The control lives inside the row's <label>; without preventDefault the
  // click would also flip the checkbox.
  expect(onToggle).not.toHaveBeenCalled()
})

test('a user-added item is labelled as theirs, not as an AI pick', () => {
  render(
    <PackingChecklistPanel
      items={[checklistItem({ item_name: 'Rain Jacket', closet_item_id: 'o1', source: 'user_added', planned_days: [] })]}
      packedState={{}}
      onToggle={vi.fn()}
      editable
    />,
  )
  expect(screen.getByText('You added')).toBeInTheDocument()
})

test('closet suggestions can be packed in one click', async () => {
  const onAddSuggestion = vi.fn()
  const suggestions: ClosetSuggestion[] = [
    { closet_item_id: 'o1', item_name: 'Rain Jacket', category: 'outerwear', reason: 'Room in your bag' },
  ]
  render(
    <PackingChecklistPanel
      items={[checklistItem()]}
      packedState={{}}
      onToggle={vi.fn()}
      editable
      suggestions={suggestions}
      onAddSuggestion={onAddSuggestion}
    />,
  )

  await userEvent.click(screen.getByRole('button', { name: /pack rain jacket/i }))
  expect(onAddSuggestion).toHaveBeenCalledWith('o1')
})

test('the suggestions strip is hidden when the plan has no gaps', () => {
  render(
    <PackingChecklistPanel items={[checklistItem()]} packedState={{}} onToggle={vi.fn()} editable suggestions={[]} />,
  )
  expect(screen.queryByText(/also in your closet/i)).not.toBeInTheDocument()
})

// ── Picker ────────────────────────────────────────────────────────────────

test('picker returns the chosen item id', async () => {
  const onConfirm = vi.fn()
  render(
    <ClosetItemPicker
      open
      title="Swap for…"
      closetItems={closet()}
      onConfirm={onConfirm}
      onClose={vi.fn()}
    />,
  )

  await userEvent.click(screen.getByRole('button', { name: /navy linen tee/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Add' }))

  expect(onConfirm).toHaveBeenCalledWith(['t2'])
})

test('items already packed cannot be picked again', async () => {
  const onConfirm = vi.fn()
  render(
    <ClosetItemPicker
      open
      title="Add"
      closetItems={closet()}
      excludeIds={['t2']}
      onConfirm={onConfirm}
      onClose={vi.fn()}
    />,
  )

  const tile = screen.getByRole('button', { name: /navy linen tee/i })
  expect(tile).toBeDisabled()
  expect(within(tile).getByText(/already packed/i)).toBeInTheDocument()
})

test('single-select replaces the previous choice — a swap takes exactly one item', async () => {
  const onConfirm = vi.fn()
  const { unmount } = render(
    <ClosetItemPicker open title="Swap" closetItems={closet()} onConfirm={onConfirm} onClose={vi.fn()} />,
  )
  await userEvent.click(screen.getByRole('button', { name: /navy linen tee/i }))
  await userEvent.click(screen.getByRole('button', { name: /rain jacket/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Add' }))

  expect(onConfirm).toHaveBeenCalledWith(['o1'])
  unmount()
})

test('multi-select accumulates, and re-clicking deselects', async () => {
  const onConfirm = vi.fn()
  render(
    <ClosetItemPicker
      open
      multiple
      title="Add"
      confirmLabel="Add to list"
      closetItems={closet()}
      onConfirm={onConfirm}
      onClose={vi.fn()}
    />,
  )
  await userEvent.click(screen.getByRole('button', { name: /navy linen tee/i }))
  await userEvent.click(screen.getByRole('button', { name: /rain jacket/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Add to list' }))
  expect(onConfirm).toHaveBeenLastCalledWith(['t2', 'o1'])

  await userEvent.click(screen.getByRole('button', { name: /rain jacket/i }))
  await userEvent.click(screen.getByRole('button', { name: 'Add to list' }))
  expect(onConfirm).toHaveBeenLastCalledWith(['t2'])
})

test('a closed picker renders nothing', () => {
  const { container } = render(
    <ClosetItemPicker open={false} title="x" closetItems={closet()} onConfirm={vi.fn()} onClose={vi.fn()} />,
  )
  expect(container).toBeEmptyDOMElement()
})
