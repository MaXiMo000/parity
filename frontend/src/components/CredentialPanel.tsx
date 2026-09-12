import { useState } from 'react'
import { clearCredential, setCredential, type Workspace } from '../api'
import { useModalPanel } from '../lib/useModalPanel'

/** A write-only credential form: once saved, the real value is never
 * shown again (matching real secret-manager UI conventions) -- only
 * whether one is currently set, and under which header name. */
export function CredentialPanel({ workspace, onClose, onSaved }: {
  workspace: Workspace
  onClose: () => void
  onSaved: (workspace: Workspace) => void
}) {
  const closeRef = useModalPanel(true, onClose)
  const [headerName, setHeaderName] = useState(workspace.credential_header_name ?? 'Authorization')
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSave() {
    setBusy(true)
    setError(null)
    try {
      await setCredential(workspace.id, headerName, value)
      onSaved({ ...workspace, has_credential: true, credential_header_name: headerName })
      setValue('')
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  async function handleClear() {
    setBusy(true)
    setError(null)
    try {
      await clearCredential(workspace.id)
      onSaved({ ...workspace, has_credential: false, credential_header_name: null })
    } catch (e) {
      setError(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="history-backdrop" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className="history-panel" role="dialog" aria-modal="true" aria-label="Workspace credential">
        <button type="button" className="dive__close" onClick={onClose} ref={closeRef} aria-label="Close credential panel">Close ✕</button>
        <h3 className="dive__title">Credential</h3>

        <p className="dive__detail">
          {workspace.has_credential
            ? `A credential is stored for the "${workspace.credential_header_name}" header. Save a new value to replace it, or clear it below.`
            : 'No credential stored yet. It will be sent automatically on every request that doesn’t already set the same header.'}
        </p>

        <label className="credential-panel__label" htmlFor="credential-header-name">Header name</label>
        <input
          id="credential-header-name" type="text" value={headerName}
          onChange={(e) => setHeaderName(e.target.value)} disabled={busy}
        />

        <label className="credential-panel__label" htmlFor="credential-value">Value</label>
        <input
          id="credential-value" type="password" value={value} placeholder="Paste the real credential value"
          onChange={(e) => setValue(e.target.value)} disabled={busy}
        />

        {error && <p className="dive__detail" style={{ color: 'var(--violate)' }}>{error}</p>}

        <div className="credential-panel__actions">
          <button type="button" className="dive__send" onClick={handleSave} disabled={busy || !headerName.trim() || !value.trim()}>
            {busy ? 'Saving…' : 'Save'}
          </button>
          {workspace.has_credential && (
            <button type="button" className="history-toggle" onClick={handleClear} disabled={busy}>
              Clear stored credential
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
