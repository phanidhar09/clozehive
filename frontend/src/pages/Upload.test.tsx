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

    await user.click(screen.getByRole('button', { name: /Analyze with Vision AI/i }))
    expect(Api.closetApi.analyzePreview).toHaveBeenCalledTimes(1)

    await user.click(screen.getByRole('button', { name: /Save selected items from this photo/i }))
    expect(Api.closetApi.confirmPreview).toHaveBeenCalledTimes(1)
    expect(fetchClosetItems).toHaveBeenCalled()
  })
})
