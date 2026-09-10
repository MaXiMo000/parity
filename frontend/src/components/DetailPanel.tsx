import { useState, useEffect } from 'react'
import type { Node, SendResult } from '../api'
import type { DriftStatus } from '../lib/severity'
import { useModalPanel } from '../lib/useModalPanel'

export function DetailPanel({ node, status, onClose, onSend }: {
  node: Node | null
  status: DriftStatus
  onClose: () => void
  onSend: (nodeId: string) => Promise<SendResult>
}) {
  const closeRef = useModalPanel(node !== null, onClose)
  const [result, setResult] = useState<SendResult | null>(null)
  const [sending, setSending] = useState(false)

  useEffect(() => {
    setResult(null)
    setSending(false)
  }, [node?.id])

  if (!node) return null

  async function handleSend() {
    setSending(true)
    try {
      const r = await onSend(node!.id)
      setResult(r)
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="dive-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dive" role="dialog" aria-modal="true" aria-labelledby="detail-title">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close detail panel">
          Close ✕
        </button>
        <p className="eyebrow">{node.method} · {node.path_template}</p>
        <h3 id="detail-title" className="dive__title">{node.operation_id}</h3>
        <p className={`dive__status dive__status--${status}`}>{status}</p>

        <button type="button" className="dive__send" onClick={handleSend} disabled={sending}>
          {sending ? 'Sending…' : 'Send'}
        </button>

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
      </div>
    </div>
  )
}
