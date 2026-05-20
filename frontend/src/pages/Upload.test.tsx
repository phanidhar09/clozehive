import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { vi } from 'vitest'
import Upload from '@/pages/Upload'
import * as Api from '@/lib/api'
import { MockAppProvider } from '@/test/utils'

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    closetApi: {
      ...actual.closetApi,
      analyzePreview: vi.fn(),
      confirmPreview: vi.fn(),
      delete: vi.fn(),
    },
  }
})

describe('Upload', () => {
  it('renders the upload hub and category options for Add to Closet', () => {
    render(
      <MockAppProvider value={{ fetchClosetItems: vi.fn() }}>
        <Upload />
      </MockAppProvider>,
    )

    expect(screen.getByRole('heading', { name: /Upload Clothing Item/i })).toBeInTheDocument()
    expect(
      screen.getByText(/review and confirm before anything is added/i),
    ).toBeInTheDocument()

    expect(
      screen.getByText(/Nothing is saved until you confirm/i),
    ).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: /Analyze/i })).not.toBeInTheDocument()
  })

  it('calls analyzePreview then confirmPreview on preview → save (no legacy upload)', async () => {
    const user = userEvent.setup()
    const fetchClosetItems = vi.fn()
    const previewItem = {
      slot_index: 0,
      temp_id: 'tid-1',
      detected_item_id: 'did-uuid-001',
      name: 'Blue top',
      category: 'tops',
      season: [] as string[],
      occasions: [] as string[],
      confidence: 0.9,
      original_image_url: '/uploads/o.jpg',
      preview_image_url: '/uploads/p.jpg',
      background_removed: false,
      style_tags: [] as string[],
    }
    vi.mocked(Api.closetApi.analyzePreview).mockResolvedValue({
      preview_session_id: '00000000-0000-0000-0000-00000000aaaa',
      items: [previewItem],
      scan_id: 'scan-1',
      pipeline_cached: false,
    })
    vi.mocked(Api.closetApi.confirmPreview).mockResolvedValue({ saved: [], total_saved: 1 })

    render(
      <MockAppProvider value={{ fetchClosetItems }}>
        <Upload />
      </MockAppProvider>,
    )

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([10, 20, 30])], 'shirt.jpg', { type: 'image/jpeg' })
    await user.upload(input, file)

    await user.click(screen.getByRole('button', { name: /Analyze with FANI/i }))
    expect(Api.closetApi.analyzePreview).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: /Save selected items from this photo/i }))
    expect(Api.closetApi.confirmPreview).toHaveBeenCalledTimes(1)
    // Confirm payload must include detected_item_id so backend can validate image↔metadata correlation.
    const confirmCall = vi.mocked(Api.closetApi.confirmPreview).mock.calls[0][0]
    expect(confirmCall.items[0].detected_item_id).toBe('did-uuid-001')
    expect(fetchClosetItems).toHaveBeenCalled()
  })

  it('renders two items from multi-item detection with distinct React keys', async () => {
    const user = userEvent.setup()
    const shirtItem = {
      slot_index: 0,
      temp_id: 'tid-shirt',
      detected_item_id: 'did-shirt-aaa',
      name: 'Black Shirt',
      category: 'tops',
      season: [] as string[],
      occasions: [] as string[],
      confidence: 0.92,
      original_image_url: '/uploads/orig.jpg',
      preview_image_url: '/uploads/shirt-crop.jpg',
      background_removed: true,
      style_tags: [] as string[],
    }
    const pantsItem = {
      slot_index: 1,
      temp_id: 'tid-pants',
      detected_item_id: 'did-pants-bbb',
      name: 'Blue Jeans',
      category: 'bottoms',
      season: [] as string[],
      occasions: [] as string[],
      confidence: 0.88,
      original_image_url: '/uploads/orig.jpg',
      preview_image_url: '/uploads/pants-crop.jpg',
      background_removed: false,
      style_tags: [] as string[],
    }
    vi.mocked(Api.closetApi.analyzePreview).mockResolvedValue({
      preview_session_id: '00000000-0000-0000-0000-00000000bbbb',
      items: [shirtItem, pantsItem],
      scan_id: 'scan-2',
      pipeline_cached: false,
    })
    vi.mocked(Api.closetApi.confirmPreview).mockResolvedValue({ saved: [], total_saved: 2 })

    render(
      <MockAppProvider value={{ fetchClosetItems: vi.fn() }}>
        <Upload />
      </MockAppProvider>,
    )

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([10, 20, 30])], 'outfit.jpg', { type: 'image/jpeg' })
    await user.upload(input, file)
    await user.click(screen.getByRole('button', { name: /Analyze with FANI/i }))

    // Both items should appear in the preview.
    expect(screen.getByText('Black Shirt')).toBeInTheDocument()
    expect(screen.getByText('Blue Jeans')).toBeInTheDocument()

    // Save the group.
    await user.click(screen.getByRole('button', { name: /Save selected items from this photo/i }))
    const confirmCall = vi.mocked(Api.closetApi.confirmPreview).mock.calls[0][0]

    // Each item in the confirm payload must carry its own detected_item_id.
    const payloadIds = confirmCall.items.map((i: { detected_item_id?: string }) => i.detected_item_id)
    expect(payloadIds).toContain('did-shirt-aaa')
    expect(payloadIds).toContain('did-pants-bbb')
    // IDs must be distinct.
    expect(new Set(payloadIds).size).toBe(2)
  })
})
