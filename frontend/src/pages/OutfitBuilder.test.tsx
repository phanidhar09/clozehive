import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import OutfitBuilder, { AIAnalysisPanel } from '@/pages/OutfitBuilder'
import { MockAppProvider } from '@/test/utils'
import type { ClosetItem, OutfitAnalysis } from '@/types'

const canvasItem = (i: number): ClosetItem => ({
  id: `00000000-0000-0000-0000-${String(i).padStart(12, '0')}`,
  user_id: 'ffffffff-ffff-ffff-ffff-ffffffffffff',
  name: `Item ${i}`,
  category: 'tops',
  tags: [],
  wear_count: 0,
  occasion: [],
  created_at: new Date().toISOString(),
})

const analysisFixture = (): OutfitAnalysis => ({
  outfit: {
    items: {
      top: { id: '1', name: 'Shirt', category: 'tops' },
      bottom: null,
      footwear: null,
      outerwear: null,
      accessories: [],
    },
    matching_score: 82,
    confidence: 0.88,
    fit_confidence: 91,
    score_breakdown: {
      color: 20,
      occasion: 22,
      fit: 16,
      style: 12,
      weather: 8,
      preference: 4,
    },
    recommendations: {
      issues: ['Add contrast'],
      improvements: ['Try a belt'],
      styling_tips: ['Cuff the sleeves'],
    },
    reasoning: 'Balanced casual look.',
    occasion_match: 'High',
    style_match: 'Medium',
  },
  missing_pieces: [],
  style_tips: ['Layer with a light jacket'],
})

describe('AIAnalysisPanel', () => {
  it('shows matching score, fit confidence, and recommendations', async () => {
    const user = userEvent.setup()
    render(<AIAnalysisPanel analysis={analysisFixture()} onClose={vi.fn()} />)

    expect(screen.getByText('AI Outfit Analysis')).toBeInTheDocument()
    expect(screen.getAllByText(/^82$/)[0]).toBeInTheDocument()
    expect(screen.getByText(/Fit confidence/i)).toBeInTheDocument()
    expect(screen.getByText('91%')).toBeInTheDocument()
    expect(screen.getByText('Add contrast')).toBeInTheDocument()
    expect(screen.getByText('Try a belt')).toBeInTheDocument()
    expect(screen.getByText('Cuff the sleeves')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Show general style tips/i }))
    expect(screen.getByText('Layer with a light jacket')).toBeInTheDocument()
  })
})

describe('OutfitBuilder', () => {
  it('gates the canvas until the closet reaches five items', () => {
    const few = Array.from({ length: 4 }, (_, i) => canvasItem(i + 1))
    render(
      <MemoryRouter>
        <MockAppProvider value={{ closetItems: few }}>
          <OutfitBuilder />
        </MockAppProvider>
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /You need at least 5 items/i })).toBeInTheDocument()
  })

  it('shows the canvas and helper copy once enough pieces exist', () => {
    const many = Array.from({ length: 6 }, (_, i) => canvasItem(i + 1))
    render(
      <MemoryRouter>
        <MockAppProvider value={{ closetItems: many }}>
          <OutfitBuilder />
        </MockAppProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: 'Outfit Builder' })).toBeInTheDocument()
    expect(screen.getByLabelText(/Outfit canvas/i)).toBeInTheDocument()
  })
})
