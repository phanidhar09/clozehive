import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
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
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the upload hub and category options for Add to Closet', () => {
    render(
      <MemoryRouter>
        <MockAppProvider value={{ fetchClosetItems: vi.fn() }}>
          <Upload />
        </MockAppProvider>
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: /Add to Your Closet/i })).toBeInTheDocument()
    expect(
      screen.getByText(/review each one and save/i),
    ).toBeInTheDocument()

    expect(
      screen.getByText(/Nothing is saved until you press Save/i),
    ).toBeInTheDocument()

    // The Analyze CTA only appears after a photo is selected
    expect(screen.queryByRole('button', { name: /Analyze/i })).not.toBeInTheDocument()
  })

  it('calls analyzePreview then confirmPreview on preview → save (no legacy upload)', async () => {
    const user = userEvent.setup()
    const fetchClosetItems = vi.fn().mockResolvedValue(undefined)
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
      <MemoryRouter>
        <MockAppProvider value={{ fetchClosetItems }}>
          <Upload />
        </MockAppProvider>
      </MemoryRouter>,
    )

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([10, 20, 30])], 'shirt.jpg', { type: 'image/jpeg' })
    await user.upload(input, file)

    await user.click(screen.getByRole('button', { name: /Analyze with FANI/i }))
    expect(Api.closetApi.analyzePreview).toHaveBeenCalledTimes(1)

    // Persistent save bar shows "Save 1" (one selected item) and confirms the preview
    await user.click(screen.getByRole('button', { name: /^Save 1$/ }))
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
      <MemoryRouter>
        <MockAppProvider value={{ fetchClosetItems: vi.fn().mockResolvedValue(undefined) }}>
          <Upload />
        </MockAppProvider>
      </MemoryRouter>,
    )

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File([new Uint8Array([10, 20, 30])], 'outfit.jpg', { type: 'image/jpeg' })
    await user.upload(input, file)
    await user.click(screen.getByRole('button', { name: /Analyze with FANI/i }))

    // The wizard reviews one item at a time; "Review all" reveals the full list.
    await user.click(await screen.findByRole('button', { name: /Review all/i }))
    expect(screen.getAllByText('Black Shirt').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Blue Jeans').length).toBeGreaterThanOrEqual(1)

    // Save the group (both items selected → "Save 2").
    await user.click(screen.getByRole('button', { name: /^Save 2$/ }))
    const confirmCall = vi.mocked(Api.closetApi.confirmPreview).mock.calls[0][0]

    // Each item in the confirm payload must carry its own detected_item_id.
    const payloadIds = confirmCall.items.map((i: { detected_item_id?: string }) => i.detected_item_id)
    expect(payloadIds).toContain('did-shirt-aaa')
    expect(payloadIds).toContain('did-pants-bbb')
    // IDs must be distinct.
    expect(new Set(payloadIds).size).toBe(2)
  })

  it('"Add more" appends a second photo to the selection instead of replacing it', async () => {
    const user = userEvent.setup()
    // Real browsers hand back a unique blob URL per call; the global test mock returns a
    // constant. Make it unique here so appended previews get distinct React keys.
    let blobN = 0
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:http://localhost/mock-${blobN++}`)

    render(
      <MemoryRouter>
        <MockAppProvider value={{ fetchClosetItems: vi.fn() }}>
          <Upload />
        </MockAppProvider>
      </MemoryRouter>,
    )

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const first = new File([new Uint8Array([1, 2, 3])], 'first.jpg', { type: 'image/jpeg' })
    const second = new File([new Uint8Array([4, 5, 6])], 'second.jpg', { type: 'image/jpeg' })

    await user.upload(input, first)
    expect(screen.getByText(/1 of 20 photo selected/i)).toBeInTheDocument()

    // A second selection (what "+ Add more" triggers) must accumulate, not overwrite.
    await user.upload(input, second)
    expect(screen.getByText(/2 of 20 photos selected/i)).toBeInTheDocument()

    // Re-picking an already-selected file is a no-op (de-duped by name+size).
    await user.upload(input, first)
    expect(screen.getByText(/2 of 20 photos selected/i)).toBeInTheDocument()
  })
})
