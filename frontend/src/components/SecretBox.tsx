import { useState } from 'react'

// Shows a signing secret with a copy button. Used on create and on reveal.
export function SecretBox({ title, secret, note }: { title: string; secret: string; note: string }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    await navigator.clipboard.writeText(secret)
    setCopied(true)
  }

  return (
    <div className="bg-amber-50 border border-amber-200 rounded px-4 py-3 text-sm space-y-2">
      <p className="font-medium text-amber-900">{title}</p>
      <div className="flex items-center gap-2">
        <code className="bg-white border border-amber-200 rounded px-2 py-1 font-mono text-xs break-all flex-1">
          {secret}
        </code>
        <button
          type="button"
          onClick={copy}
          className="text-xs border border-amber-300 rounded px-2 py-1 hover:bg-amber-100"
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <p className="text-amber-800 text-xs">{note}</p>
    </div>
  )
}
