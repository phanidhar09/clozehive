import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, beforeAll } from 'vitest'

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = globalThis.ResizeObserver ?? ResizeObserverStub

// jsdom ships a scrollTo that throws "Not implemented"; @tanstack/react-virtual
// (Closet grid) calls it during layout effects. Override with a no-op.
const noopScrollTo = () => {}
globalThis.scrollTo = noopScrollTo as typeof globalThis.scrollTo
if (typeof window !== 'undefined') {
  window.scrollTo = noopScrollTo as typeof window.scrollTo
  window.Element.prototype.scrollTo = noopScrollTo as typeof window.Element.prototype.scrollTo
}

beforeAll(() => {
  if (typeof globalThis.URL.createObjectURL !== 'function') {
    globalThis.URL.createObjectURL = () => 'blob:http://localhost/mock-object-url'
  }
  if (typeof globalThis.URL.revokeObjectURL !== 'function') {
    globalThis.URL.revokeObjectURL = () => {}
  }
})

afterEach(() => {
  cleanup()
})
