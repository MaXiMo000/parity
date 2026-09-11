import { useEffect, useState } from 'react'
import { listWorkspaces, type WorkspaceSummary } from '../api'

/** The real "reopen a workspace you already built" affordance -- named
 * and deferred as a gap since Phase 1a, closed here. Lists this user's
 * persisted workspaces and loads whichever one is picked. Re-fetches
 * whenever `refreshKey` changes (App.tsx bumps it after a successful
 * create) so a brand-new workspace shows up without a page reload. */
export function WorkspaceList({ onLoad, refreshKey, currentId, busy }: {
  onLoad: (id: string) => void
  refreshKey: number
  currentId: string | null
  busy: boolean
}) {
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([])

  useEffect(() => {
    listWorkspaces().then(setWorkspaces).catch(() => setWorkspaces([]))
  }, [refreshKey])

  if (workspaces.length === 0) return null

  return (
    <select
      className="workspace-list"
      value={currentId ?? ''}
      onChange={(e) => { if (e.target.value) onLoad(e.target.value) }}
      disabled={busy}
      aria-label="Load existing workspace"
    >
      <option value="" disabled>Load existing…</option>
      {workspaces.map((w) => (
        <option key={w.id} value={w.id}>{w.name} ({w.schema_kind})</option>
      ))}
    </select>
  )
}
