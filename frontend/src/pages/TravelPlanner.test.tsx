import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import TravelPlanner from '@/pages/TravelPlanner'
import { MockAppProvider } from '@/test/utils'
import type { AppState } from '@/store'
import type { ClosetItem, PackingPlan, Trip } from '@/types'
import * as Api from '@/lib/api'

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    tripsApi: {
      ...actual.tripsApi,
      list: vi.fn(() => Promise.resolve([])),
      listSaved: vi.fn(() => Promise.resolve([])),
      getPackingPlan: vi.fn(),
    },
  }
})

const sampleItem = (): ClosetItem => ({
  id: 'cccccccc-cccc-cccc-cccc-cccccccccccc',
  user_id: 'dddddddd-dddd-dddd-dddd-dddddddddddd',
  name: 'Coat',
  category: 'outerwear',
  tags: [],
  wear_count: 0,
  occasion: [],
  created_at: new Date().toISOString(),
})

/** Render TravelPlanner inside a memory router so react-router hooks resolve. */
function renderTravelPlanner(value?: Partial<AppState>) {
  return render(
    <MemoryRouter>
      <MockAppProvider value={value}>
        <TravelPlanner />
      </MockAppProvider>
    </MemoryRouter>,
  )
}

describe('TravelPlanner', () => {
  beforeEach(() => {
    vi.mocked(Api.tripsApi.list).mockResolvedValue([])
    vi.mocked(Api.tripsApi.listSaved).mockResolvedValue([])
    vi.mocked(Api.tripsApi.getPackingPlan).mockReset()
  })

  it('surfaces wardrobe empty messaging when packing has no closet context', () => {
    renderTravelPlanner({ closetItems: [] })
    expect(screen.getByRole('heading', { name: /Travel Packing/i })).toBeInTheDocument()
    expect(screen.getByText(/Build your wardrobe first/i)).toBeInTheDocument()
  })

  it('shows packing purpose options once the traveler has wardrobe items', () => {
    renderTravelPlanner({ closetItems: [sampleItem()] })
    expect(screen.getByRole('option', { name: /Leisure/i })).toBeInTheDocument()
  })

  it('does not crash when loading saved planners fails', async () => {
    const user = userEvent.setup()
    vi.mocked(Api.tripsApi.listSaved).mockRejectedValueOnce(new Error('network'))

    renderTravelPlanner({ closetItems: [sampleItem()] })

    await user.click(screen.getByRole('button', { name: /^Saved$/i }))
    await waitFor(() => {
      expect(vi.mocked(Api.tripsApi.listSaved)).toHaveBeenCalled()
    })

    // Falls back to the empty state instead of crashing
    expect(await screen.findByText(/No saved planners yet/i)).toBeInTheDocument()
  })

  it('lists saved planners tab with an empty-state when none exist yet', async () => {
    const user = userEvent.setup()
    renderTravelPlanner({ closetItems: [sampleItem()] })

    await user.click(screen.getByRole('button', { name: /^Saved$/i }))

    await waitFor(() => {
      expect(vi.mocked(Api.tripsApi.listSaved)).toHaveBeenCalled()
    })

    expect(await screen.findByText(/No saved planners yet/i)).toBeInTheDocument()
  })

  it('loads packing plan when opening a saved planner', async () => {
    const user = userEvent.setup()
    const savedTrip: Trip = {
      id: 'eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee',
      user_id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
      destination: 'Lisbon',
      start_date: '2026-07-01',
      end_date: '2026-07-08',
      purpose: 'leisure',
      notes: null,
      is_saved: true,
      activities: [],
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    }
    const plan: PackingPlan = {
      id: '11111111-1111-1111-1111-111111111111',
      trip_id: savedTrip.id,
      user_id: savedTrip.user_id,
      take_from_your_closet: [],
      you_might_still_need: [],
      daily_plan: [],
      packing_list: [],
      missing_items: [],
      alerts: [],
      activities: [],
      day_plans_rich: [],
      rewear_strategy: [],
      packing_checklist: [],
      checklist_state: {},
      is_saved: true,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-02T00:00:00Z',
    }
    vi.mocked(Api.tripsApi.listSaved).mockResolvedValue([savedTrip])
    vi.mocked(Api.tripsApi.getPackingPlan).mockResolvedValue(plan)

    renderTravelPlanner({ closetItems: [sampleItem()] })

    await user.click(screen.getByRole('button', { name: /^Saved$/i }))
    await waitFor(() => expect(vi.mocked(Api.tripsApi.listSaved)).toHaveBeenCalled())

    await user.click(screen.getByRole('button', { name: /View Planner/i }))
    await waitFor(() => {
      expect(vi.mocked(Api.tripsApi.getPackingPlan)).toHaveBeenCalledWith(savedTrip.id)
    })
    expect(await screen.findByRole('heading', { name: /Lisbon/i })).toBeInTheDocument()
  })
})
