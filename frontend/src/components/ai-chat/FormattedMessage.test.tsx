import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import FormattedMessage from './FormattedMessage'

describe('FormattedMessage', () => {
  it('renders bold and inline code', () => {
    const { container } = render(
      <FormattedMessage content="Try a **navy blazer** with `chinos`." />,
    )
    expect(container.querySelector('strong')?.textContent).toBe('navy blazer')
    expect(container.querySelector('code')?.textContent).toBe('chinos')
  })

  it('renders bullet lists', () => {
    render(<FormattedMessage content={'Options:\n- White tee\n- Black jeans'} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(2)
    expect(items[0].textContent).toBe('White tee')
  })

  it('renders numbered lists as an ordered list', () => {
    const { container } = render(
      <FormattedMessage content={'1. First\n2. Second'} />,
    )
    expect(container.querySelector('ol')).not.toBeNull()
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
  })

  it('renders links with safe rel attributes', () => {
    render(<FormattedMessage content="See [the guide](https://example.com)." />)
    const link = screen.getByRole('link', { name: 'the guide' })
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('leaves plain text intact', () => {
    render(<FormattedMessage content="Just a simple sentence." />)
    expect(screen.getByText('Just a simple sentence.')).toBeInTheDocument()
  })
})
