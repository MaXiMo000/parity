import { useState } from 'react'

/** The real "give it a schema" entry point (SPEC.md §6 step 1) — a real
 * OpenAPI or GraphQL URL, submitted for real parsing. This form only
 * supports a URL today; raw-schema/SDL paste (`createWorkspace`'s
 * `rawSchema` branch) is a real, supported backend capability with no UI
 * yet. */
export function WorkspaceForm({ onCreate, busy }: {
  onCreate: (name: string, kind: 'openapi' | 'graphql', url: string) => void
  busy: boolean
}) {
  const [name, setName] = useState('')
  const [kind, setKind] = useState<'openapi' | 'graphql'>('openapi')
  const [url, setUrl] = useState('')

  return (
    <form
      className="workspace-form"
      onSubmit={(e) => {
        e.preventDefault()
        if (name.trim() && url.trim()) onCreate(name.trim(), kind, url.trim())
      }}
    >
      <input
        type="text" placeholder="Workspace name" value={name}
        onChange={(e) => setName(e.target.value)} disabled={busy} aria-label="Workspace name"
      />
      <select
        value={kind} onChange={(e) => setKind(e.target.value as 'openapi' | 'graphql')}
        disabled={busy} aria-label="Schema kind"
      >
        <option value="openapi">OpenAPI</option>
        <option value="graphql">GraphQL</option>
      </select>
      <input
        type="text"
        placeholder={kind === 'openapi' ? 'https://api.example.com/openapi.json' : 'https://api.example.com/graphql'}
        value={url}
        onChange={(e) => setUrl(e.target.value)} disabled={busy} aria-label="Schema URL"
      />
      <button type="submit" disabled={busy || !name.trim() || !url.trim()}>
        {busy ? 'Parsing…' : 'Create'}
      </button>
    </form>
  )
}
