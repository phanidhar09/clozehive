import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import OutfitRecommendationCard from './OutfitRecommendationCard'
import type { RecommendedOutfit } from '@/types'

vi.mock('@/services/aiChatApi', () => ({
  logOutfitWorn: vi.fn().mockResolvedValue(undefined),
  saveRecommendedOutfit: vi.fn().mockResolvedValue({}),
  submitOutfitFeedback: vi.fn().mockResolvedValue({}),
}))

import { logOutfitWorn, submitOutfitFeedback } from '@/services/aiChatApi'

function _outfit(): RecommendedOutfit {
  return {
    title: 'Casual Friday',
    items: [
      { id: 'a', name: 'Navy Tee', category: 'tops' },
      { id: 'b', name: 'Chinos', category: 'bottoms' },
    ],
    matching_score: 82,
    reasoning: 'Balanced, seasonal.',
    fashion_rules_used: [],
    improvement_tips: [],
  }
}

describe('OutfitRecommendationCard — feedback capture', () => {
  beforeEach(() => vi.clearAllMocks())

  it('thumbs-up sends a positive rating to the learning loop', async () => {
    render(<OutfitRecommendationCard outfit={_outfit()} rank={0} />)
    fireEvent.click(screen.getByTitle('Love this outfit'))
    await waitFor(() =>
      expect(submitOutfitFeedback).toHaveBeenCalledWith(
        expect.objectContaining({ closet_item_ids: ['a', 'b'], rating: 5 }),
      ),
    )
  })

  it('wearing an outfit both logs wear AND reinforces the pairing (was_worn)', async () => {
    render(<OutfitRecommendationCard outfit={_outfit()} rank={0} />)
    fireEvent.click(screen.getByText('Wear this today'))

    await waitFor(() => expect(logOutfitWorn).toHaveBeenCalledWith(['a', 'b']))
    // The genuine gap this wiring closes: wear must reach the pair-learning loop.
    await waitFor(() =>
      expect(submitOutfitFeedback).toHaveBeenCalledWith({ closet_item_ids: ['a', 'b'], was_worn: true }),
    )
  })
})
