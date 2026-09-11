import { useCallback, useState } from 'react'
import { createWorkspace, getWorkspace, sendRequest, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import { WorkspaceForm } from './components/WorkspaceForm'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses, setStatuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleClose = useCallback(() => setSelectedId(null), [])

  function handleCreate(name: string, kind: 'openapi' | 'graphql', url: string) {
    setBusy(true)
    setError(null)
    createWorkspace(name, kind, { url })
      .then((created) => getWorkspace(created.id))
      .then((ws) => { setWorkspace(ws); setStatuses({}) })
      .catch((e) => setError(String(e)))
      .finally(() => setBusy(false))
  }

  async function handleSend(nodeId: string) {
    if (!workspace) throw new Error('no workspace loaded')
    const result = await sendRequest(workspace.id, nodeId)
    setStatuses((prev) => ({ ...prev, [nodeId]: result.drift_finding.status }))
    return result
  }

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
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
      <DetailPanel node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSend={handleSend} />
    </div>
  )
}
