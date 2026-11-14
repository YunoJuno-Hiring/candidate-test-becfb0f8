import { useState, FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  deleteWebhookEndpoint,
  fetchWebhookDeliveries,
  fetchWebhookEndpoint,
  rotateWebhookSecret,
  sendTestEvent,
  updateWebhookEndpoint,
} from '../api/webhooks'
import { fieldError, WebhookDelivery } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { SecretBox } from '../components/SecretBox'

const LOG_REFRESH_MS = 5000 // the log updates itself, so retries can be watched as they happen

function UrlForm({ id, currentUrl }: { id: number; currentUrl: string }) {
  const [url, setUrl] = useState(currentUrl)
  const queryClient = useQueryClient()
  const save = useMutation({
    mutationFn: () => updateWebhookEndpoint(id, { url }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['webhook-endpoint', id] }),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    save.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <label htmlFor="endpoint-url" className="block text-sm font-medium text-slate-700">
        Destination URL
      </label>
      <div className="flex gap-2">
        <input
          id="endpoint-url"
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 border border-slate-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <button
          type="submit"
          disabled={save.isPending || url === currentUrl}
          className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60"
        >
          {save.isPending ? 'Saving…' : 'Save'}
        </button>
      </div>
      {save.isError && (
        <p role="alert" className="text-red-700 text-sm">
          {fieldError(save.error, 'url', 'Failed to save the URL.')}
        </p>
      )}
      {save.isSuccess && <p className="text-green-700 text-sm">URL saved. Send a test event to check it.</p>}
    </form>
  )
}

function DeliveryRow({ delivery }: { delivery: WebhookDelivery }) {
  const [open, setOpen] = useState(false)
  const retrying = delivery.status === 'failed' && delivery.next_attempt_at
  return (
    <>
      <tr className="hover:bg-slate-50 cursor-pointer" onClick={() => setOpen(!open)}>
        <td className="px-4 py-3 font-mono text-xs text-slate-700">
          {open ? '▾' : '▸'} {delivery.event_id.slice(0, 12)}…
        </td>
        <td className="px-4 py-3 text-xs text-slate-700">{delivery.event_type}</td>
        <td className="px-4 py-3 text-xs text-slate-500">{new Date(delivery.created_at).toLocaleString()}</td>
        <td className="px-4 py-3 text-xs">
          <StatusBadge status={delivery.status} />
          {retrying && (
            <span className="ml-2 text-slate-500">
              retrying {new Date(delivery.next_attempt_at as string).toLocaleTimeString()}
            </span>
          )}
          {delivery.status === 'failed' && !delivery.next_attempt_at && (
            <span className="ml-2 text-red-700">gave up</span>
          )}
        </td>
        <td className="px-4 py-3 text-xs text-slate-700 text-right">{delivery.attempts.length}</td>
      </tr>
      {open &&
        delivery.attempts.map((a) => (
          <tr key={a.attempt} className="bg-slate-50 text-xs">
            <td className="pl-10 pr-4 py-2 text-slate-500">Attempt {a.attempt}</td>
            <td className="px-4 py-2 text-slate-500">{new Date(a.at).toLocaleString()}</td>
            <td className="px-4 py-2" colSpan={3}>
              <StatusBadge status={a.status} />{' '}
              <span className="text-slate-600">{a.response_code ? `HTTP ${a.response_code}` : a.error || 'No response'}</span>
            </td>
          </tr>
        ))}
      {open && delivery.attempts.length === 0 && (
        <tr className="bg-slate-50 text-xs">
          <td className="pl-10 py-2 text-slate-500" colSpan={5}>
            {delivery.status === 'created' ? 'Saved while the endpoint was paused or disabled; not sent.' : 'Waiting for the worker.'}
          </td>
        </tr>
      )}
    </>
  )
}

export default function WebhookEndpointDetail() {
  const id = Number(useParams<{ id: string }>().id)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [secret, setSecret] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const endpointQuery = useQuery({ queryKey: ['webhook-endpoint', id], queryFn: () => fetchWebhookEndpoint(id) })
  const deliveriesQuery = useQuery({
    queryKey: ['webhook-deliveries', id],
    queryFn: () => fetchWebhookDeliveries(id),
    refetchInterval: LOG_REFRESH_MS,
  })

  // Every action refetches what it changed rather than guessing the result (no optimistic updates).
  function refresh() {
    queryClient.invalidateQueries({ queryKey: ['webhook-endpoint', id] })
    queryClient.invalidateQueries({ queryKey: ['webhook-deliveries', id] })
    queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
  }

  const setStatus = useMutation({
    mutationFn: (status: 'active' | 'paused') => updateWebhookEndpoint(id, { status }),
    onSuccess: refresh,
  })
  const test = useMutation({
    mutationFn: () => sendTestEvent(id),
    onSuccess: () => {
      setNotice('Test event queued. It will appear in the log below.')
      refresh()
    },
  })
  const rotate = useMutation({ mutationFn: () => rotateWebhookSecret(id), onSuccess: (data) => setSecret(data.secret) })
  const remove = useMutation({
    mutationFn: () => deleteWebhookEndpoint(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
      navigate('/developers')
    },
  })

  function handleDelete() {
    if (window.confirm('Delete this endpoint and its delivery history? This cannot be undone.')) remove.mutate()
  }

  function handleRotate() {
    if (window.confirm('Generate a new signing secret? The current one keeps working for 24 hours.')) rotate.mutate()
  }

  if (endpointQuery.isLoading) return <p className="text-slate-500">Loading…</p>
  if (endpointQuery.isError || !endpointQuery.data) {
    return (
      <div className="bg-red-50 border border-red-200 text-red-700 rounded px-4 py-3 text-sm">
        Endpoint not found or you don't have access.
      </div>
    )
  }
  const endpoint = endpointQuery.data
  const button = 'text-sm border border-slate-300 rounded px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50'

  return (
    <div className="space-y-8 max-w-4xl">
      <div>
        <Link to="/developers" className="text-indigo-600 hover:text-indigo-800 text-sm">
          ← Developer settings
        </Link>
        <div className="flex items-center gap-3 mt-2">
          <h1 className="text-xl font-semibold text-slate-900">Webhook endpoint</h1>
          <StatusBadge status={endpoint.status} />
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-6 space-y-5">
        {/* key resets the form when the saved URL changes */}
        <UrlForm key={endpoint.url} id={id} currentUrl={endpoint.url} />

        {endpoint.status === 'disabled' && (
          <p className="bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
            Disabled after 7 days of failed deliveries. Fix the destination, then send a test event: a successful
            delivery re-enables it.
          </p>
        )}

        <div className="flex flex-wrap gap-2">
          {endpoint.status === 'active' && (
            <button className={button} disabled={setStatus.isPending} onClick={() => setStatus.mutate('paused')}>
              Pause
            </button>
          )}
          {endpoint.status === 'paused' && (
            <button className={button} disabled={setStatus.isPending} onClick={() => setStatus.mutate('active')}>
              Resume
            </button>
          )}
          {endpoint.status !== 'paused' && (
            <button className={button} disabled={test.isPending} onClick={() => test.mutate()}>
              Send test event
            </button>
          )}
          <button className={button} disabled={rotate.isPending} onClick={handleRotate}>
            Rotate secret
          </button>
          <button
            className="text-sm border border-red-300 text-red-700 rounded px-3 py-1.5 hover:bg-red-50 disabled:opacity-50 ml-auto"
            disabled={remove.isPending}
            onClick={handleDelete}
          >
            Delete
          </button>
        </div>

        {endpoint.status === 'paused' && (
          <p className="text-slate-500 text-xs">
            Paused: new events are saved but not sent, deliveries already queued or retrying fail without being
            sent, and test events are off. Resuming sends only the most recent saved event.
          </p>
        )}
        {notice && <p className="text-green-700 text-sm">{notice}</p>}
        {(setStatus.isError || test.isError || rotate.isError || remove.isError) && (
          <p role="alert" className="text-red-700 text-sm">
            Something went wrong. Please try again.
          </p>
        )}
        {secret && (
          <SecretBox
            title="New signing secret. Copy it now"
            secret={secret}
            note="It won't be shown again. Deliveries are signed with both secrets for 24 hours, then only this one."
          />
        )}
      </div>

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-3">Delivery log</h2>
        {deliveriesQuery.isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : deliveriesQuery.isError ? (
          <p className="text-red-600 text-sm">Failed to load deliveries.</p>
        ) : !deliveriesQuery.data || deliveriesQuery.data.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
            <p className="text-slate-500 text-sm">Nothing sent yet. Send a test event to try it.</p>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Event</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Type</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Fired</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
                  <th className="text-right px-4 py-3 font-medium text-slate-600">Attempts</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {deliveriesQuery.data.map((d) => (
                  <DeliveryRow key={d.id} delivery={d} />
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="text-slate-400 text-xs mt-2">The 20 most recent deliveries. Refreshes every 5 seconds.</p>
      </div>
    </div>
  )
}
