import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import Tabs, { type TabItem } from './Tabs'

const ITEMS: TabItem[] = [
  { value: 'one', label: 'One' },
  { value: 'two', label: 'Two' },
  { value: 'three', label: 'Three' },
]

function Harness() {
  const [value, setValue] = useState('one')
  return <Tabs items={ITEMS} value={value} onChange={setValue} label="Sections" idPrefix="t" />
}

describe('Tabs', () => {
  it('renders an accessible tablist with the selected tab marked', () => {
    render(<Harness />)
    expect(screen.getByRole('tablist', { name: 'Sections' })).toBeInTheDocument()
    const first = screen.getByRole('tab', { name: 'One' })
    expect(first).toHaveAttribute('aria-selected', 'true')
    expect(first).toHaveAttribute('aria-controls', 't-panel-one')
  })

  it('selects a tab on click', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('tab', { name: 'Two' }))
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'false')
  })

  it('moves selection with arrow keys (roving focus)', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const first = screen.getByRole('tab', { name: 'One' })
    first.focus()
    await user.keyboard('{ArrowRight}')
    expect(screen.getByRole('tab', { name: 'Two' })).toHaveAttribute('aria-selected', 'true')
    await user.keyboard('{Home}')
    expect(screen.getByRole('tab', { name: 'One' })).toHaveAttribute('aria-selected', 'true')
  })
})
