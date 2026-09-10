import type { Node } from '../api'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'

export function DetailPanel({ node, status, onClose }: {
  node: Node | null
  status: DriftStatus
  onClose: () => void
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  if (!node) return null

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{node.method} · {node.path_template}</p>
        <h3 id="detail-title" className="dive__title">{node.operation_id}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>
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
      </div>
    </div>
  )
}
