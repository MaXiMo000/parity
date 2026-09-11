import { useEffect, useState } from 'react'
import { getNodeHistory, type Node, type NodeHistoryEntry, type SendResult, type Workspace } from '../api'
import { nodeLabel } from '../lib/nodeLabel'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'
import { RequestBuilder } from './RequestBuilder'

export function DetailPanel({ workspace, node, status, onClose, onSent }: {
  workspace: Workspace | null
  node: Node | null
  status: DriftStatus
  onClose: () => void
  onSent: (nodeId: string, result: SendResult) => void
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  const [result, setResult] = useState<SendResult | null>(null)
  const [history, setHistory] = useState<NodeHistoryEntry[]>([])

  useEffect(() => {
    setResult(null)
    if (workspace && node) {
      getNodeHistory(workspace.id, node.id).then(setHistory).catch(() => setHistory([]))
    } else {
      setHistory([])
    }
  }, [node?.id, workspace?.id])

  if (!node || !workspace) return null

  function handleSent(sendResult: SendResult) {
    setResult(sendResult)
    onSent(node!.id, sendResult)
    getNodeHistory(workspace!.id, node!.id).then(setHistory).catch(() => {})
  }

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{nodeLabel(node).eyebrow}</p>
        <h3 id="detail-title" className="dive__title">{nodeLabel(node).title}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>

        <RequestBuilder workspace={workspace} node={node} onSent={handleSent} />

        {result && (
          <div className="dive__result">
            <p className="dive__label">Response ({result.response.status_code})</p>
            <pre className="dive__schema">{JSON.stringify(result.response.body, null, 2)}</pre>
            <p className={`dive__status dive__status--${result.drift_finding.status}`}>
              {result.drift_finding.status}
            </p>
            <p className="dive__detail">{result.drift_finding.detail}</p>
          </div>
        )}

        {node.declared_request_schema && (
          <>
            <p className="dive__label">Declared request</p>
            <pre className="dive__schema">{JSON.stringify(node.declared_request_schema, null, 2)}</pre>
          </>
        )}
        {node.declared_response_schema && (
          <>
            <p className="dive__label">Declared response</p>
            <pre className="dive__schema">{JSON.stringify(node.declared_response_schema, null, 2)}</pre>
          </>
        )}

        {history.length > 0 && (
          <>
            <p className="dive__label">History</p>
            <ul className="dive__history">
              {history.map((h) => (
                <li key={h.id} className={`dive__status dive__status--${h.status}`}>
                  {h.status} · {new Date(h.created_at).toLocaleString()}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  )
}
