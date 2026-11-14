import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WebhookEndpointDetail from './WebhookEndpointDetail'
import * as api from '../api/webhooks'
import { WebhookDelivery, WebhookEndpoint } from '../api/client'

// The page's API calls are replaced with fakes, so these tests need no backend.
vi.mock('../api/webhooks')

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.resetAllMocks()
})

const ENDPOINT: WebhookEndpoint = { id: 1, url: 'https://example.com/hook', status: 'active', last_delivery: null }

function renderPage(endpoint: WebhookEndpoint = ENDPOINT, deliveries: WebhookDelivery[] = []) {
  vi.mocked(api.fetchWebhookEndpoint).mockResolvedValue(endpoint)
  vi.mocked(api.fetchWebhookDeliveries).mockResolvedValue(deliveries)
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/developers/webhooks/1']}>
        <Routes>
          <Route path="/developers/webhooks/:id" element={<WebhookEndpointDetail />} />
          <Route path="/developers" element={<p>List page</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('WebhookEndpointDetail', () => {
  it('only deletes once the admin confirms', async () => {
    vi.mocked(api.deleteWebhookEndpoint).mockResolvedValue()
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Delete' }))
    expect(api.deleteWebhookEndpoint).not.toHaveBeenCalled()

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }))
    expect(await screen.findByText('List page')).toBeTruthy() // back to the list once deleted
    expect(api.deleteWebhookEndpoint).toHaveBeenCalledWith(1)
  })

  it('only rotates the secret once the admin confirms, then shows the new one', async () => {
    vi.mocked(api.rotateWebhookSecret).mockResolvedValue({ secret: 'whsec_new' })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: 'Rotate secret' }))
    expect(api.rotateWebhookSecret).not.toHaveBeenCalled()

    confirm.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: 'Rotate secret' }))
    expect(await screen.findByText('whsec_new')).toBeTruthy()
    expect(api.rotateWebhookSecret).toHaveBeenCalledWith(1)
  })

  it('shows each attempt and its error when a delivery is expanded', async () => {
    renderPage(ENDPOINT, [
      {
        id: 7,
        event_id: 'evt_0123456789abcdef',
        event_type: 'contract.created',
        status: 'failed',
        created_at: '2026-11-13T16:00:00Z',
        next_attempt_at: '2026-11-13T16:01:00Z',
        attempts: [
          {
            attempt: 1,
            status: 'failed',
            response_code: null,
            error: 'Connection refused',
            url: 'https://old.example.com/hook',
            at: '2026-11-13T16:00:01Z',
          },
        ],
      },
    ])

    fireEvent.click(await screen.findByText('contract.created'))

    expect(screen.getByText('Attempt 1')).toBeTruthy()
    expect(screen.getByText('Connection refused')).toBeTruthy()
    expect(screen.getByText('https://old.example.com/hook')).toBeTruthy() // where that attempt went
  })

  it('offers no test event while paused', async () => {
    renderPage({ ...ENDPOINT, status: 'paused' })

    expect(await screen.findByRole('button', { name: 'Resume' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Send test event' })).toBeNull()
  })
})
