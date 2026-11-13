import { useState, FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchWebhookEndpoints, createWebhookEndpoint } from '../api/webhooks'
import { CreatedWebhookEndpoint, fieldError, WebhookAttempt } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { SecretBox } from '../components/SecretBox'

function LastDelivery({ attempt }: { attempt: WebhookAttempt | null }) {
  if (!attempt) return <span className="text-slate-400">—</span>
  const result = attempt.response_code ? `HTTP ${attempt.response_code}` : 'No response'
  return (
    <span className={attempt.status === 'delivered' ? 'text-green-700' : 'text-red-700'}>
      {result} · {new Date(attempt.at).toLocaleString()}
    </span>
  )
}

export default function DeveloperSettings() {
  const [url, setUrl] = useState('')
  // Held only in memory: leaving the page drops it, matching "copy it now".
  const [created, setCreated] = useState<CreatedWebhookEndpoint | null>(null)
  const queryClient = useQueryClient()

  const endpointsQuery = useQuery({
    queryKey: ['webhook-endpoints'],
    queryFn: fetchWebhookEndpoints,
  })

  const createMutation = useMutation({
    mutationFn: () => createWebhookEndpoint(url),
    onSuccess: (endpoint) => {
      queryClient.invalidateQueries({ queryKey: ['webhook-endpoints'] })
      setCreated(endpoint)
      setUrl('')
    },
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setCreated(null)
    createMutation.mutate()
  }

  return (
    <div className="space-y-8 max-w-3xl">
      <div>
        <h1 className="text-xl font-semibold text-slate-900 mb-1">Developer settings</h1>
        <p className="text-slate-500 text-sm">
          Webhook endpoints receive signed event notifications from YunoJuno, such as a new contract.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-6">
        <h2 className="text-base font-medium text-slate-800 mb-4">Add webhook destination</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label htmlFor="webhook-url" className="block text-sm font-medium text-slate-700 mb-1">
              Destination URL
            </label>
            <input
              id="webhook-url"
              type="url"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
              placeholder="https://example.com/webhook"
              className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <p className="text-slate-400 text-xs mt-1">
              Must be https. For local testing, use{' '}
              <code className="bg-slate-100 px-1 rounded">http://localhost:8027/hook</code>
            </p>
          </div>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="bg-indigo-600 text-white text-sm px-4 py-2 rounded hover:bg-indigo-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {createMutation.isPending ? 'Saving…' : 'Save endpoint'}
          </button>
        </form>

        {createMutation.isError && (
          <div role="alert" className="mt-4 bg-red-50 border border-red-200 text-red-700 text-sm rounded px-3 py-2">
            {fieldError(createMutation.error, 'url', 'Failed to save endpoint. Please try again.')}
          </div>
        )}
        {created && (
          <div className="mt-4">
            <SecretBox
              title="Endpoint saved. Copy its signing secret now"
              secret={created.secret}
              note="Use it to verify the webhook-signature header. It won't be shown on this page again. We've sent a test event: its result appears under Last delivery."
            />
          </div>
        )}
      </div>

      <div>
        <h2 className="text-base font-medium text-slate-800 mb-3">Configured endpoints</h2>

        {endpointsQuery.isLoading ? (
          <p className="text-slate-500 text-sm">Loading…</p>
        ) : endpointsQuery.isError ? (
          <p className="text-red-600 text-sm">Failed to load endpoints.</p>
        ) : !endpointsQuery.data || endpointsQuery.data.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-lg px-6 py-10 text-center">
            <p className="text-slate-500 text-sm">No webhook endpoints configured yet.</p>
          </div>
        ) : (
          <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 border-b border-slate-200">
                <tr>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">URL</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Status</th>
                  <th className="text-left px-4 py-3 font-medium text-slate-600">Last delivery</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {endpointsQuery.data.map((ep) => (
                  <tr key={ep.id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 text-slate-700 font-mono text-xs break-all">{ep.url}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={ep.status} />
                    </td>
                    <td className="px-4 py-3 text-xs">
                      <LastDelivery attempt={ep.last_delivery} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link to={`/developers/webhooks/${ep.id}`} className="text-indigo-600 hover:text-indigo-800 text-xs">
                        Manage →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
