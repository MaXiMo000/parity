import { useEffect, useState } from 'react'
import { getWorkspaceRequests, type RequestHistoryEntry, type Workspace } from '../api'
import { nodeLabel } from '../lib/nodeLabel'

export function HistoryPanel({ workspace, onClose }: { workspace: Workspace; onClose: () => void }) {
  const [requests, setRequests] = useState<RequestHistoryEntry[]>([])
  const [filterNodeId, setFilterNodeId] = useState('')

  useEffect(() => {
    getWorkspaceRequests(workspace.id).then(setRequests).catch(() => setRequests([]))
  }, [workspace.id])

  const nodeLabelById = new Map(workspace.nodes.map((n) => [n.id, nodeLabel(n).title]))
  const matchedNodeIds = [...new Set(requests.map((r) => r.node_id).filter((id): id is string => id !== null))]
  const filtered = filterNodeId ? requests.filter((r) => r.node_id === filterNodeId) : requests

  return (
    <div className="history-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="history-panel" role="dialog" aria-modal="true" aria-label="Request history">
        <button type="button" className="dive__close" onClick={onClose} aria-label="Close history">Close ✕</button>
        <h3 className="dive__title">History</h3>
        <select
          className="history-panel__filter" value={filterNodeId}
          onChange={(e) => setFilterNodeId(e.target.value)} aria-label="Filter by node"
        >
          <option value="">All nodes</option>
          {matchedNodeIds.map((id) => (
            <option key={id} value={id}>{nodeLabelById.get(id) ?? id}</option>
          ))}
        </select>
        <ul className="history-panel__list">
          {filtered.map((r) => (
            <li key={r.id}>
              <span className="dive__label">{r.method}</span> {r.url}
              <span className="dive__detail"> — {new Date(r.sent_at).toLocaleString()}</span>
            </li>
          ))}
          {filtered.length === 0 && <li className="dive__detail">No requests sent yet.</li>}
        </ul>
      </div>
    </div>
  )
}
