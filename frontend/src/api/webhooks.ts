import { api, CreatedWebhookEndpoint, WebhookDelivery, WebhookEndpoint, WebhookEndpointStatus } from './client'

const BASE = '/api/webhook-endpoints'

export function fetchWebhookEndpoints(): Promise<WebhookEndpoint[]> {
  return api.get(`${BASE}/`)
}

export function fetchWebhookEndpoint(id: number): Promise<WebhookEndpoint> {
  return api.get(`${BASE}/${id}/`)
}

export function createWebhookEndpoint(url: string): Promise<CreatedWebhookEndpoint> {
  return api.post(`${BASE}/`, { url })
}

// Admins can change the URL, or pause/resume; only the system sets 'disabled'.
export function updateWebhookEndpoint(
  id: number,
  changes: { url?: string; status?: Exclude<WebhookEndpointStatus, 'disabled'> },
): Promise<WebhookEndpoint> {
  return api.patch(`${BASE}/${id}/`, changes)
}

export function deleteWebhookEndpoint(id: number): Promise<void> {
  return api.delete(`${BASE}/${id}/`)
}

// Returns a new secret; the old one keeps signing for 24 hours so the receiver can switch over.
export function rotateWebhookSecret(id: number): Promise<{ secret: string }> {
  return api.post(`${BASE}/${id}/rotate-secret/`, {})
}

export function sendTestEvent(id: number): Promise<{ id: number }> {
  return api.post(`${BASE}/${id}/test/`, {})
}

export function fetchWebhookDeliveries(id: number): Promise<WebhookDelivery[]> {
  return api.get(`${BASE}/${id}/deliveries/`)
}
