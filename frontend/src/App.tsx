import { useCallback, useState } from 'react'
import { createWorkspace, getWorkspace, type SendResult, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import { WorkspaceForm } from './components/WorkspaceForm'
import { WorkspaceList } from './components/WorkspaceList'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses, setStatuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const handleClose = useCallback(() => setSelectedId(null), [])

  function handleCreate(name: string, kind: 'openapi' | 'graphql', url: string) {
    setBusy(true)
    setError(null)
    createWorkspace(name, kind, { url })
      .then((created) => getWorkspace(created.id))
      .then((ws) => { setWorkspace(ws); setStatuses({}); setRefreshKey((k) => k + 1) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }

  function handleLoad(id: string) {
    setBusy(true)
    setError(null)
    getWorkspace(id)
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }

  function handleSent(nodeId: string, result: SendResult) {
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
  }

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
          <WorkspaceList onLoad={handleLoad} refreshKey={refreshKey} currentId={workspace?.id ?? null} busy={busy} />
          <WorkspaceForm onCreate={handleCreate} busy={busy} />
        </div>

        {!workspace && !error && (
          <p className="idle-hint">Paste a real OpenAPI or GraphQL URL above to build its 3D map.</p>
        )}
        {error && <p className="idle-hint idle-hint--error">{error}</p>}

        {workspace && (
          <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={setSelectedId} />
        )}
      </div>
      <DetailPanel workspace={workspace} node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSent={handleSent} />
    </div>
  )
}
