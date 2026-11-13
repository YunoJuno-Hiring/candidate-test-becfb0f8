const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-slate-100 text-slate-600',
  submitted: 'bg-yellow-100 text-yellow-800',
  approved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  active: 'bg-indigo-100 text-indigo-800',
  closed: 'bg-slate-100 text-slate-500',
  // Webhook endpoints and deliveries
  paused: 'bg-slate-100 text-slate-600',
  disabled: 'bg-red-100 text-red-800',
  created: 'bg-slate-100 text-slate-600',
  queued: 'bg-yellow-100 text-yellow-800',
  delivered: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
}

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium capitalize ${cls}`}>
      {status}
    </span>
  )
}
