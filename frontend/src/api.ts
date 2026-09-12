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

export interface Workspace {
  id: string
  name: string
  schema_kind: 'openapi' | 'graphql'
  base_path: string
  schema_source: string
  nodes: Node[]
  edges: Edge[]
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
}

export const GITHUB_LOGIN_URL = '/api/auth/github/login'

export function getCurrentUser(): Promise<CurrentUser | null> {
  return fetch('/api/auth/me', { credentials: 'include' }).then((res) => {
    if (res.status === 401) return null
    return json<CurrentUser>(res)
  })
}

export function logout(): Promise<void> {
  return fetch('/api/auth/logout', { method: 'POST', credentials: 'include' }).then(() => undefined)
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
  return fetch('/api/workspaces', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    credentials: 'include',
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
}

export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch('/api/workspaces', { credentials: 'include' }).then((res) => json<WorkspaceSummary[]>(res))
}

export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`/api/workspaces/${encodeURIComponent(id)}`, { credentials: 'include' }).then((res) => json<Workspace>(res))
}

export function sendRequest(
  workspaceId: string,
  method: string,
  url: string,
  headers: Record<string, string>,
  body: string | null,
): Promise<SendResult> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ method, url, headers, body }),
    credentials: 'include',
  }).then((res) => json<SendResult>(res))
}

export function curlParse(curl: string): Promise<CurlParseResult> {
  return fetch('/api/curl-parse', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ curl }),
    credentials: 'include',
  }).then((res) => json<CurlParseResult>(res))
}

export function getNodeHistory(workspaceId: string, nodeId: string): Promise<NodeHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/nodes/${encodeURIComponent(nodeId)}/history`, { credentials: 'include' })
    .then((res) => json<NodeHistoryEntry[]>(res))
}

export function getWorkspaceRequests(workspaceId: string): Promise<RequestHistoryEntry[]> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, { credentials: 'include' })
    .then((res) => json<RequestHistoryEntry[]>(res))
}
