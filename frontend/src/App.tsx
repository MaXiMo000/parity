import { useEffect, useState } from 'react'
import { getWorkspace, type Workspace } from './api'
import type { DriftStatus } from './lib/severity'
import { Graph } from './scene/Graph'

const FIXTURE_ID = 'phase0-fixture-workspace'

export function App() {
  const [workspace, setWorkspace] = useState<Workspace | null>(null)
  const [statuses] = useState<Record<string, DriftStatus>>({})

  useEffect(() => {
    getWorkspace(FIXTURE_ID).then(setWorkspace)
  }, [])

  return (
    <div className="app">
      <div className="hud-top">
        <div className="brand">parity<span>.</span></div>
      </div>
      {workspace && (
        <Graph nodes={workspace.nodes} edges={workspace.edges} statuses={statuses} onSelect={() => {}} />
      )}
    </div>
  )
}
