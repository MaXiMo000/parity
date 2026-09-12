import { useCallback, useEffect, useState } from 'react'
import { createWorkspace, getCurrentUser, getWorkspace, logout, type CurrentUser, type SendResult, type Workspace, GITHUB_LOGIN_URL } from './api'
import { CredentialPanel } from './components/CredentialPanel'
import { DetailPanel } from './components/DetailPanel'
import { HistoryPanel } from './components/HistoryPanel'
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
  const [showHistory, setShowHistory] = useState(false)
  const [showCredential, setShowCredential] = useState(false)
  const [currentUser, setCurrentUser] = useState<CurrentUser | null | undefined>(undefined)

  useEffect(() => {
    getCurrentUser()
      .then(setCurrentUser)
      .catch((e) => { setError(String(e)); setCurrentUser(null) })
  }, [])

  const handleClose = useCallback(() => setSelectedId(null), [])
  const handleCloseHistory = useCallback(() => setShowHistory(false), [])
  const handleCloseCredential = useCallback(() => setShowCredential(false), [])

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

  function handleLogout() {
    logout().then(() => {
      setCurrentUser(null)
      setWorkspace(null)
      setStatuses({})
      setSelectedId(null)
      setError(null)
      setShowHistory(false)
      setShowCredential(false)
    })
  }

  const selected = workspace?.nodes.find((n) => n.id === selectedId) ?? null

  if (currentUser === undefined) {
    return <div className="app auth-loading">Loading…</div>
  }

  if (currentUser === null) {
    return (
      <div className="app auth-gate">
        <div className="brand">parity<span>.</span></div>
        {error && <p className="idle-hint idle-hint--error">{error}</p>}
        <a className="auth-gate__button" href={GITHUB_LOGIN_URL}>Sign in with GitHub</a>
      </div>
    )
  }

  return (
    <div className="app">
      <div className="scene-root">
        <div className="hud-top">
          <div className="brand">parity<span>.</span></div>
          <span className="auth-user">{currentUser.username}</span>
          <button type="button" className="auth-logout" onClick={handleLogout}>Log out</button>
          <WorkspaceList onLoad={handleLoad} refreshKey={refreshKey} currentId={workspace?.id ?? null} busy={busy} />
          {workspace && (
            <button type="button" className="history-toggle" onClick={() => setShowHistory(true)}>
              History
            </button>
          )}
          {workspace && (
            <button type="button" className="history-toggle" onClick={() => setShowCredential(true)}>
              Credential
            </button>
          )}
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
      <DetailPanel key={selected?.id ?? 'none'} workspace={workspace} node={selected} status={selectedId ? (statuses[selectedId] ?? 'unverified_no_schema') : 'unverified_no_schema'} onClose={handleClose} onSent={handleSent} />
      {workspace && showHistory && (
        <HistoryPanel workspace={workspace} onClose={handleCloseHistory} />
      )}
      {workspace && showCredential && (
        <CredentialPanel
          workspace={workspace}
          onClose={handleCloseCredential}
          onSaved={(updated) => setWorkspace(updated)}
        />
      )}
    </div>
  )
}
