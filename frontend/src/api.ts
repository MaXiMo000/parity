import type { DriftStatus } from './lib/severity'

export interface Node {
  id: string
  kind: 'rest_operation' | 'graphql_field'
  method: string | null
  path_template: string | null
  operation_id: string | null
  type_name: string | null
  field_name: string | null
  declared_request_schema: Record<string, unknown> | null
  declared_response_schema: Record<string, unknown> | null
  call_count: number
}

export interface Edge {
  from_node: string
  to_node: string
}

// Non-persisted, view-only graph landmarks (SPEC.md §8.3: "Query and
// Mutation as roots, fields fanning out to the types they return") --
// never a real, sendable API operation, so deliberately kept out of
// `Node`/`nodes` rather than shoehorned in with null REST/GraphQL fields.
// Always empty for an OpenAPI workspace.
export interface VirtualNode {
  id: string
  label: string
  kind: 'graphql_root' | 'graphql_type'
}

export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
  base_path: string
  schema_source: string
  has_credential: boolean
  credential_header_name: string | null
  nodes: Node[]
  edges: Edge[]
  virtual_nodes: VirtualNode[]
}

export interface WorkspaceSummary {
  id: string
  name: string
  schema_kind: Workspace['schema_kind']
}

export interface SendResult {
  request: { id: string; node_id: string | null; method: string; url: string }
  response: { id: string; status_code: number; body: unknown; latency_ms: number }
  drift_finding: { id: string; status: DriftStatus; detail: string | null }
}

export interface CurlParseResult {
  method: string
  url: string
  headers: Record<string, string>
  body: string | null
}

export interface NodeHistoryEntry {
  id: string
  status: DriftStatus
  detail: string | null
  created_at: string
}

export interface RequestHistoryEntry {
  id: string
  node_id: string | null
  method: string
  url: string
  sent_at: string
}

export interface CurrentUser {
  id: string
  username: string
  csrf_token: string
}

// Split-origin deploys (frontend and backend on different real domains,
// per SPEC.md's own deploy-readiness goal, Phase 3c) need an absolute
// backend URL -- same-origin local dev keeps working unchanged because
// an empty prefix plus Vite's dev-server proxy (vite.config.ts) resolves
// '/api/...' exactly as before. Set VITE_API_BASE_URL at build time (see
// DEPLOY.md) for a real split-origin deploy; leave it unset for local dev.
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export const GITHUB_LOGIN_URL = `${API_BASE}/api/auth/github/login`

// The anti-CSRF double-submit token (2026-09-18 security-hardening plan,
// backend/app/auth/dependencies.py::require_csrf): the backend's session
// cookie is SameSite=None in production (required for this split-origin
// deploy), which removes the CSRF protection SameSite=Lax would
// otherwise give for free -- every mutating route now requires this
// header to match the value the session itself carries. Held in module
// state, not React state: every api.ts function needs it, and it has no
// UI of its own to re-render for. Set once per real login (getCurrentUser),
// cleared on logout so a stale value never outlives its session.
let csrfToken: string | null = null

function csrfHeaders(): Record<string, string> {
  return csrfToken ? { 'X-CSRF-Token': csrfToken } : {}
}

export function getCurrentUser(): Promise<CurrentUser | null> {
  return fetch(`${API_BASE}/api/auth/me`, { credentials: 'include' }).then((res) => {
    if (res.status === 401) { csrfToken = null; return null }
    return json<CurrentUser>(res).then((user) => { csrfToken = user.csrf_token; return user })
  })
}

export function logout(): Promise<void> {
  return fetch(`${API_BASE}/api/auth/logout`, {
    method: 'POST', credentials: 'include', headers: csrfHeaders(),
  }).then(() => { csrfToken = null })
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status} ${detail}`)
  }
  return res.json() as Promise<T>
}

export function createWorkspace(
  name: string,
  kind: 'openapi' | 'graphql',
  source: { url: string } | { rawSchema: object | string },
): Promise<{ id: string; name: string; schema_kind: string; node_count: number }> {
  const body =
    'url' in source
      ? { name, schema_kind: kind, schema_source_url: source.url }
      : { name, schema_kind: kind, raw_schema: source.rawSchema }
  return fetch(`${API_BASE}/api/workspaces`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify(body),
    credentials: 'include',
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
}

export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch(`${API_BASE}/api/workspaces`, { credentials: 'include' }).then((res) => json<WorkspaceSummary[]>(res))
}

export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(id)}`, { credentials: 'include' }).then((res) => json<Workspace>(res))
}

export function sendRequest(
  workspaceId: string,
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string | null,
): Promise<SendResult> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify({ method, url, headers, body }),
    credentials: 'include',
  }).then((res) => json<SendResult>(res))
}

export function curlParse(curl: string): Promise<CurlParseResult> {
  return fetch(`${API_BASE}/api/curl-parse`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ curl }),
    credentials: 'include',
  }).then((res) => json<CurlParseResult>(res))
}

export function getNodeHistory(workspaceId: string, nodeId: string): Promise<NodeHistoryEntry[]> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/nodes/${encodeURIComponent(nodeId)}/history`, { credentials: 'include' })
    .then((res) => json<NodeHistoryEntry[]>(res))
}

export function getWorkspaceRequests(workspaceId: string): Promise<RequestHistoryEntry[]> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, { credentials: 'include' })
    .then((res) => json<RequestHistoryEntry[]>(res))
}

export function setCredential(workspaceId: string, headerName: string, value: string): Promise<void> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/credential`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...csrfHeaders() },
    body: JSON.stringify({ header_name: headerName, value }),
    credentials: 'include',
  }).then((res) => json<{ status: string }>(res)).then(() => undefined)
}

export function clearCredential(workspaceId: string): Promise<void> {
  return fetch(`${API_BASE}/api/workspaces/${encodeURIComponent(workspaceId)}/credential`, {
    method: 'DELETE',
    headers: csrfHeaders(),
    credentials: 'include',
  }).then((res) => json<{ status: string }>(res)).then(() => undefined)
}
