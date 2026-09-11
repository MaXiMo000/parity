import { useState } from 'react'

/** The real "give it a schema" entry point (SPEC.md §6 step 1) — a real
 * OpenAPI URL, submitted for real parsing. Pasting a raw spec is the v1
 * stand-in for real file upload (SPEC.md §3's own "either is fine, don't
 * block on this" spirit, applied here to upload vs. paste). */
export function WorkspaceForm({ onCreate, busy }: {
  onCreate: (name: string, url: string) => void
  busy: boolean
}) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')

  return (
    <form
      className="workspace-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && url.trim()) onCreate(name.trim(), url.trim())
      }}
    >
      <input
        type="text" placeholder="Workspace name" value={name}
        onChange={(e) => setName(e.target.value)} disabled={busy} aria-label="Workspace name"
      />
      <input
        type="text" placeholder="https://api.example.com/openapi.json" value={url}
        onChange={(e) => setUrl(e.target.value)} disabled={busy} aria-label="OpenAPI URL"
      />
      <button type="submit" disabled={busy || !name.trim() || !url.trim()}>
        {busy ? 'Parsing…' : 'Create'}
      </button>
    </form>
  )
}
