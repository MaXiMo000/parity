import { useEffect, useState } from 'react'
import { curlParse, sendRequest, type Node, type SendResult, type Workspace } from '../api'

const METHODS = ['GET', 'POST', 'PUT', 'PATCH', 'DELETE']

/** Best-effort starting URL for a node's request -- a UX convenience,
 * not a security boundary (the backend's own SSRF guard is what
 * actually protects the outbound fetch regardless of what this pre-fills).
 * REST: origin(schema_source) + base_path + path_template. GraphQL: the
 * schema_source itself, since a GraphQL endpoint usually IS the API
 * (unlike OpenAPI's spec-doc-vs-API-host distinction). Falls back to an
 * empty string (the user fills it in) when schema_source isn't a real URL
 * (a pasted spec) or doesn't parse. */
export function guessUrl(workspace: Workspace, node: Node): string {
  if (!workspace.schema_source || !workspace.schema_source.startsWith('http')) return ''
  try {
    const origin = new URL(workspace.schema_source).origin
    if (node.kind === 'rest_operation' && node.path_template) {
      return `${origin}${workspace.base_path}${node.path_template}`
    }
    if (node.kind === 'graphql_field') {
      return workspace.schema_source
    }
  } catch {
    // malformed schema_source -- fall through to empty
  }
  return ''
}

export function guessBody(node: Node): string {
  if (node.kind !== 'graphql_field') return ''
  const query = node.type_name === 'Mutation' ? `mutation { ${node.field_name} }` : `{ ${node.field_name} }`
  return JSON.stringify({ query }, null, 2)
}

export function RequestBuilder({ workspace, node, onSent }: {
  workspace: Workspace
  node: Node
  onSent: (result: SendResult) => void
}) {
  const [method, setMethod] = useState(node.method ?? (node.kind === 'graphql_field' ? 'POST' : 'GET'))
  const [url, setUrl] = useState(() => guessUrl(workspace, node))
  const [headersText, setHeadersText] = useState('')
  const [body, setBody] = useState(() => guessBody(node))
  const [curlText, setCurlText] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setMethod(node.method ?? (node.kind === 'graphql_field' ? 'POST' : 'GET'))
    setUrl(guessUrl(workspace, node))
    setHeadersText('')
    setBody(guessBody(node))
    setCurlText('')
    setError(null)
  }, [node.id, workspace.id])

  function parseHeadersText(): Record<string, string> {
    const headers: Record<string, string> = {}
    for (const line of headersText.split('\n')) {
      const idx = line.indexOf(':')
      if (idx > 0) headers[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
    }
    return headers
  }

  async function handleParseCurl() {
    setError(null)
    try {
      const parsed = await curlParse(curlText)
      setMethod(parsed.method)
      setUrl(parsed.url)
      setHeadersText(Object.entries(parsed.headers).map(([k, v]) => `${k}: ${v}`).join('\n'))
      setBody(parsed.body ?? '')
    } catch (e) {
      setError(String(e))
    }
  }

  async function handleSend() {
    setSending(true)
    setError(null)
    try {
      const result = await sendRequest(workspace.id, method, url, parseHeadersText(), body || null)
      onSent(result)
    } catch (e) {
      setError(String(e))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="request-builder">
      <textarea
        className="request-builder__curl"
        placeholder="Paste a curl command…"
        value={curlText}
        onChange={(e) => setCurlText(e.target.value)}
      />
      <button type="button" className="request-builder__parse" onClick={handleParseCurl} disabled={!curlText.trim()}>
        Parse curl
      </button>

      <div className="request-builder__line">
        <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="HTTP method">
          {METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        <input
          type="text" placeholder="https://api.example.com/…" value={url}
          onChange={(e) => setUrl(e.target.value)} aria-label="Request URL"
        />
      </div>
      <textarea
        className="request-builder__headers"
        placeholder="Header: value (one per line)"
        value={headersText}
        onChange={(e) => setHeadersText(e.target.value)}
        aria-label="Request headers"
      />
      <textarea
        className="request-builder__body"
        placeholder="Request body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        aria-label="Request body"
      />

      {error && <p className="dive__detail" style={{ color: 'var(--violate)' }}>{error}</p>}

      <button type="button" className="dive__send" onClick={handleSend} disabled={sending || !url.trim()}>
        {sending ? 'Sending…' : 'Send'}
      </button>
    </div>
  )
}
