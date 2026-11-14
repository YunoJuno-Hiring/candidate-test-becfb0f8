export type UserRole = 'admin' | 'freelancer' | 'unknown'

export interface AuthUser {
  id: number
  email: string
  role: UserRole
}

export interface Company {
  id: number
  name: string
  billing_email: string
}

export interface FreelancerProfile {
  id: number
  name: string
}

export interface Contract {
  id: number
  company: Company
  freelancer: FreelancerProfile
  daily_rate: string
  start_date: string
  end_date: string
  status: 'active' | 'closed'
}

export interface TimesheetEntry {
  id: number
  contract: number
  contract_id: number
  date: string
  hours: string
  status: 'draft' | 'submitted' | 'approved' | 'rejected'
  rejection_reason: string | null
}

export interface BillingRunResult {
  run_id: string
  invoices_generated: number
  status: string
}

export interface Invoice {
  id: string | number
  [key: string]: unknown
}

export type WebhookEndpointStatus = 'active' | 'paused' | 'disabled'
export type WebhookDeliveryStatus = 'created' | 'queued' | 'delivered' | 'failed'

// One attempt to send a payload: what the destination answered, and when.
export interface WebhookAttempt {
  status: 'delivered' | 'failed'
  response_code: number | null
  error: string
  url: string // where this attempt was sent: it can differ from the endpoint's current URL
  at: string
}

export interface WebhookEndpoint {
  id: number
  url: string
  status: WebhookEndpointStatus
  last_delivery: WebhookAttempt | null
}

// Only the create response carries the secret; listings never do.
export interface CreatedWebhookEndpoint extends WebhookEndpoint {
  secret: string
}

export interface WebhookDelivery {
  id: number
  event_id: string
  event_type: string
  status: WebhookDeliveryStatus
  created_at: string
  next_attempt_at: string | null
  attempts: (WebhookAttempt & { attempt: number })[]
}

function getToken(): string | null {
  return localStorage.getItem('token')
}

function authHeaders(): HeadersInit {
  const token = getToken()
  return token ? { Authorization: `Token ${token}` } : {}
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
      ...(options.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = new ApiError(res.status, body)
    throw err
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export class ApiError extends Error {
  status: number
  data: Record<string, unknown>

  constructor(status: number, data: Record<string, unknown>) {
    super(`HTTP ${status}`)
    this.status = status
    this.data = data
  }
}

export const api = {
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'POST', body: JSON.stringify(body) }),
  get: <T>(path: string) => request<T>(path),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: 'PATCH', body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
}

// The API returns field errors as { url: ['…'] }; show the first one, or a fallback.
export function fieldError(error: unknown, field: string, fallback: string): string {
  const messages = error instanceof ApiError ? error.data[field] : undefined
  return Array.isArray(messages) && messages.length ? String(messages[0]) : fallback
}
