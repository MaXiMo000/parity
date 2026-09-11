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
  nodes: Node[]
  edges: Edge[]
}

export interface WorkspaceSummary {
  id: string
  name: string
  schema_kind: Workspace['schema_kind']
}

export interface SendResult {
  request: { node_id: string; method: string; url: string }
  response: { status_code: number; body: unknown }
  drift_finding: { status: 'matched' | 'violated'; detail: string }
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
  }).then((res) => json<{ id: string; name: string; schema_kind: string; node_count: number }>(res))
}

export function listWorkspaces(): Promise<WorkspaceSummary[]> {
  return fetch('/api/workspaces').then((res) => json<WorkspaceSummary[]>(res))
}

export function getWorkspace(id: string): Promise<Workspace> {
  return fetch(`/api/workspaces/${encodeURIComponent(id)}`).then((res) => json<Workspace>(res))
}

export function sendRequest(workspaceId: string, nodeId: string): Promise<SendResult> {
  return fetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/requests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ node_id: nodeId }),
  }).then((res) => json<SendResult>(res))
}
