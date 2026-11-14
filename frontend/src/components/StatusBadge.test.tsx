import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { StatusBadge } from './StatusBadge'

// Without vitest globals, Testing Library can't unmount between tests by itself.
afterEach(cleanup)

describe('StatusBadge', () => {
  it('shows the status with its colour', () => {
    render(<StatusBadge status="approved" />)

    const badge = screen.getByText('approved')
    expect(badge.className).toContain('bg-green-100')
  })

  it('falls back to grey for a status it does not know', () => {
    render(<StatusBadge status="archived" />)

    const badge = screen.getByText('archived')
    expect(badge.className).toContain('bg-gray-100')
  })
})
