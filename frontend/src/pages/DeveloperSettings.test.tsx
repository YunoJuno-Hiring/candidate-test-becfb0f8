import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import DeveloperSettings from './DeveloperSettings'
import * as api from '../api/webhooks'

// The page's API calls are replaced with fakes, so these tests need no backend.
vi.mock('../api/webhooks')

afterEach(() => {
  cleanup()
  vi.resetAllMocks()
})

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DeveloperSettings />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DeveloperSettings', () => {
  it('shows the signing secret once an endpoint is created', async () => {
    vi.mocked(api.fetchWebhookEndpoints).mockResolvedValue([])
    vi.mocked(api.createWebhookEndpoint).mockResolvedValue({
      id: 1,
      url: 'https://example.com/hook',
      status: 'active',
      last_delivery: null,
      secret: 'whsec_shown_once',
    })
    renderPage()

    fireEvent.change(screen.getByLabelText('Destination URL'), { target: { value: 'https://example.com/hook' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect(await screen.findByText('whsec_shown_once')).toBeTruthy()
    expect(api.createWebhookEndpoint).toHaveBeenCalledWith('https://example.com/hook')
  })

  it("shows the API's reason when a URL is rejected", async () => {
    const { ApiError } = await vi.importActual<typeof import('../api/client')>('../api/client')
    vi.mocked(api.fetchWebhookEndpoints).mockResolvedValue([])
    vi.mocked(api.createWebhookEndpoint).mockRejectedValue(
      new ApiError(400, { url: ['Webhook URLs must use https.'] }),
    )
    renderPage()

    fireEvent.change(screen.getByLabelText('Destination URL'), { target: { value: 'http://example.com/hook' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save endpoint' }))

    expect((await screen.findByRole('alert')).textContent).toBe('Webhook URLs must use https.')
  })
})
