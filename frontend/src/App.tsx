import { useEffect, useState } from 'react'
import { getWorkspace, type Workspace } from './api'
import { DetailPanel } from './components/DetailPanel'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

const FIXTURE_ID = 'phase0-fixture-workspace'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses] = useState<Record<string, DriftStatus>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    getWorkspace(FIXTURE_ID).then(setWorkspace)
  }, [])

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
        </div>
        {workspace && (
          <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={setSelectedId} />
        )}
      </div>
      <DetailPanel node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified') : 'unverified'} onClose={() => setSelectedId(null)} />
    </div>
  )
}
