import { afterEach, describe, expect, it, vi } from 'vitest'

describe('resolveUploadUrl', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
    vi.stubGlobal('window', undefined)
    vi.resetModules()
  })

  it('prefixes /uploads with window origin when VITE is unset', async () => {
    vi.stubEnv('VITE_API_URL', '')
    vi.stubGlobal('window', { location: { origin: 'http://localhost:3001' } } as Window)
    vi.resetModules()
    const { resolveUploadUrl } = await import('./api')
    expect(resolveUploadUrl('/uploads/a.jpg')).toBe('http://localhost:3001/uploads/a.jpg')
  })

  it('rewrites loopback absolute /uploads to page origin when VITE is unset', async () => {
    vi.stubEnv('VITE_API_URL', '')
    vi.stubGlobal('window', { location: { origin: 'http://localhost:3001' } } as Window)
    vi.resetModules()
    const { resolveUploadUrl } = await import('./api')
    expect(resolveUploadUrl('http://localhost:8000/uploads/a.jpg')).toBe('http://localhost:3001/uploads/a.jpg')
  })

  it('keeps loopback absolute URL when VITE_API_URL is set (explicit API host)', async () => {
    vi.stubEnv('VITE_API_URL', 'http://localhost:8000')
    vi.stubGlobal('window', { location: { origin: 'http://localhost:3001' } } as Window)
    vi.resetModules()
    const { resolveUploadUrl } = await import('./api')
    expect(resolveUploadUrl('http://localhost:8000/uploads/a.jpg')).toBe('http://localhost:8000/uploads/a.jpg')
  })

  it('normalizes uploads/ without leading slash before resolving', async () => {
    vi.stubEnv('VITE_API_URL', '')
    vi.stubGlobal('window', { location: { origin: 'http://127.0.0.1:3001' } } as Window)
    vi.resetModules()
    const { resolveUploadUrl } = await import('./api')
    expect(resolveUploadUrl('uploads/x.png')).toBe('http://127.0.0.1:3001/uploads/x.png')
  })
})
